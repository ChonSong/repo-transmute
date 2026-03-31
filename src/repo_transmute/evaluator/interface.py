"""Main AgentEvaluator class — coordinates events, extraction, drift, and audit."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from repo_transmute.evaluator.events import (
    InteractionEvent, EventType, FailureMode, load_events, save_events
)
from repo_transmute.evaluator.assumption_extractor import AssumptionExtractor, Assumptions
from repo_transmute.evaluator.drift_detector import DriftDetector, DriftEvent, DriftSeverity
from repo_transmute.evaluator.audit import AuditTrail, generate_audit


@dataclass
class EvaluatorConfig:
    """Configuration for the agent evaluator."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    output_dir: Path = field(default_factory=lambda: Path("./data/evaluator"))
    emit_to_jsonl: bool = True
    detect_drift_on_register: bool = True
    extract_assumptions_on_register: bool = True
    llm_fallback_enabled: bool = True

    def get_events_path(self) -> Path:
        return self.output_dir / f"{self.session_id}_events.jsonl"

    def get_audit_path(self) -> Path:
        return self.output_dir / f"{self.session_id}_audit.json"


class AgentEvaluator:
    """Main evaluator class for agentic interactions.

    Coordinates:
    - Structured event emission and persistence
    - Lightweight assumption extraction
    - Drift detection across delegation chains
    - Audit trail generation

    Usage:
        evaluator = AgentEvaluator(session_id="run-001")
        evaluator.emit(EventType.ASSUMPTION_STATEMENT, content="...", task_id="task-1")
        evaluator.emit(EventType.SELF_CORRECTION, content="...", task_id="task-1")
        drifts = evaluator.detect_drift(task_id="task-1")  # returns cached drift from emit
        audit = evaluator.generate_audit()
        print(audit.to_json())

    Integration with RepoTransmute Pipeline:
        evaluator = AgentEvaluator(session_id=pipeline_run_id)
        coordinator.evaluator = evaluator

        # In pipeline stage callbacks, emit events:
        evaluator.emit(EventType.ASSUMPTION_STATEMENT, ...)
        evaluator.emit(EventType.VERIFICATION, ...)
        evaluator.emit(EventType.FAILURE, ...)
    """

    def __init__(self, config: Optional[EvaluatorConfig] = None, **kwargs):
        self.config = config or EvaluatorConfig(**kwargs)
        self._events: List[InteractionEvent] = []
        self._extractor = AssumptionExtractor()
        self._detector = DriftDetector()
        self.current_task_id: Optional[str] = None
        self._drift_cache: Dict[str, List[DriftEvent]] = {}
        self._session_start = datetime.now(timezone.utc).isoformat()
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def session_id(self) -> str:
        return self.config.session_id

    def set_task(self, task_id: str):
        """Set the current active task context."""
        self.current_task_id = task_id

    def emit(
        self,
        event_type: str,
        content: str = "",
        task_id: Optional[str] = None,
        agent_id: str = "repo_transmute",
        tool_name: Optional[str] = None,
        explicit_assumptions: Optional[List[str]] = None,
        implicit_beliefs: Optional[List[str]] = None,
        context_available: Optional[List[str]] = None,
        context_used: Optional[List[str]] = None,
        parent_task_id: Optional[str] = None,
        outcome: str = "unknown",
        failure_mode: Optional[str] = None,
        error_message: Optional[str] = None,
        error_recoverable: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InteractionEvent:
        """Emit a structured interaction event."""
        event = InteractionEvent(
            session_id=self.config.session_id,
            task_id=task_id or self.current_task_id or "unknown",
            event_type=event_type,
            agent_id=agent_id,
            content=content,
            tool_name=tool_name,
            explicit_assumptions=explicit_assumptions or [],
            implicit_beliefs=implicit_beliefs or [],
            context_available=context_available or [],
            context_used=context_used or [],
            parent_task_id=parent_task_id,
            outcome=outcome,
            failure_mode=failure_mode,
            error_message=error_message,
            error_recoverable=error_recoverable,
            metadata=metadata or {},
        )
        self._detector.register(event)
        self._events.append(event)

        if self.config.extract_assumptions_on_register and event.content:
            assumptions = self._extractor.extract(event.content)
            for assumption_text in assumptions.explicit:
                event.add_assumption(assumption_text, implicit=False)
            for belief_text in assumptions.implicit:
                if belief_text != "[LLM_FALLBACK_NEEDED]":
                    event.add_assumption(belief_text, implicit=True)

        if self.config.detect_drift_on_register:
            drifts = self._detector.detect_drift(
                task_id=event.task_id,
                new_event=event,
            )
            if drifts:
                self._drift_cache[event.task_id] = self._drift_cache.get(event.task_id, []) + drifts

        if self.config.emit_to_jsonl:
            save_events([event], self.config.get_events_path())

        return event

    def detect_drift(
        self,
        task_id: Optional[str] = None,
        new_information: Optional[str] = None,
    ) -> List[DriftEvent]:
        """Detect drift for a specific task or all tasks.

        If task_id is provided, returns cached drift events detected during
        emit-time detection. Otherwise runs fresh detection across all tasks.
        """
        if task_id:
            if task_id in self._drift_cache:
                return self._drift_cache.get(task_id, [])
            return self._detector.detect_drift(task_id, new_information=new_information)
        return self._detector.detect_all_drifts()

    def get_drift_summary(self) -> Dict[str, Any]:
        """Get a summary of all detected drift."""
        return self._detector.get_drift_summary()

    def get_active_assumptions(self, task_id: str) -> List:
        """Get currently valid (non-invalidated) assumptions for a task."""
        return self._detector.get_active_assumptions(task_id)

    def get_invalidated_assumptions(self, task_id: str) -> List:
        """Get invalidated assumptions for a task."""
        return self._detector.get_invalidated_assumptions(task_id)

    def generate_audit(self, task_id: Optional[str] = None) -> AuditTrail:
        """Generate an audit trail for this session or a specific task."""
        events = self._events
        if task_id:
            events = [e for e in self._events if e.task_id == task_id]
        drift_events = []
        if task_id:
            drift_events = self._drift_cache.get(task_id, [])
        trail = generate_audit(
            events=events,
            session_id=self.config.session_id,
            task_id=task_id,
            drift_events=drift_events,
        )
        return trail

    def generate_markdown_audit(self, task_id: Optional[str] = None) -> str:
        """Generate a human-readable markdown audit."""
        from repo_transmute.evaluator.audit import format_audit_as_markdown
        return format_audit_as_markdown(self.generate_audit(task_id=task_id))

    def save_audit(self, path: Optional[Path] = None) -> Path:
        """Save the audit trail as JSON to disk."""
        path = path or self.config.get_audit_path()
        self.generate_audit().to_json(path)
        return path

    def events_for_task(self, task_id: str) -> List[InteractionEvent]:
        """Get all events for a specific task."""
        return [e for e in self._events if e.task_id == task_id]

    def stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        event_types: Dict[str, int] = {}
        for e in self._events:
            event_types[e.event_type] = event_types.get(e.event_type, 0) + 1
        failures = [e for e in self._events if e.outcome == "failure"]
        by_mode: Dict[str, int] = {}
        for f in failures:
            m = f.failure_mode or "unknown"
            by_mode[m] = by_mode.get(m, 0) + 1
        return {
            "session_id": self.config.session_id,
            "total_events": len(self._events),
            "event_types": event_types,
            "total_failures": len(failures),
            "failure_modes": by_mode,
            "total_drift_events": len(self._detector._drift_events),
            "drift_summary": self._detector.get_drift_summary(),
            "session_start": self._session_start,
            "events_file": str(self.config.get_events_path()),
        }

    def load_from_file(self, path: Optional[Path] = None):
        """Load events from a JSONL file into this evaluator's state."""
        path = path or self.config.get_events_path()
        if path.exists():
            loaded = load_events(path)
            for event in loaded:
                self._detector.register(event)
                self._events.append(event)


def instrument_pipeline_chunk(
    evaluator: AgentEvaluator,
    chunk_id: int,
    language: str,
    target_lang: str,
    file_count: int,
    function_count: int,
    event_type: str = "chunk_processing",
) -> InteractionEvent:
    """Emit an event for a pipeline chunk being processed."""
    return evaluator.emit(
        event_type=event_type,
        content=f"Processing chunk {chunk_id}: {file_count} files, {function_count} functions, "
                f"{language} → {target_lang}",
        task_id=f"chunk-{chunk_id}",
        context_available=[f"{language}_source", f"{target_lang}_target"],
        metadata={
            "chunk_id": chunk_id,
            "language": language,
            "target_lang": target_lang,
            "file_count": file_count,
            "function_count": function_count,
        },
    )


def instrument_transpilation_assumption(
    evaluator: AgentEvaluator,
    chunk_id: int,
    source_lang: str,
    target_lang: str,
    assumptions: List[str],
) -> InteractionEvent:
    """Emit an assumption statement event for a transpilation pass."""
    return evaluator.emit(
        event_type=EventType.ASSUMPTION_STATEMENT.value,
        content=f"Transpiling {source_lang} → {target_lang}: {', '.join(assumptions)}",
        task_id=f"chunk-{chunk_id}",
        explicit_assumptions=assumptions,
        metadata={
            "chunk_id": chunk_id,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "assumption_count": len(assumptions),
        }
    )


def instrument_validation(
    evaluator: AgentEvaluator,
    chunk_id: int,
    passed: bool,
    errors: List[str],
    warnings: List[str],
) -> InteractionEvent:
    """Emit a verification or failure event for a validation result."""
    return evaluator.emit(
        event_type=EventType.FAILURE.value if not passed else EventType.VERIFICATION.value,
        content=f"Validation {'PASSED' if passed else 'FAILED'} for chunk {chunk_id}",
        task_id=f"chunk-{chunk_id}",
        outcome="success" if passed else "failure",
        failure_mode=FailureMode.UNKNOWN.value if not passed else None,
        error_message="; ".join(errors) if errors else None,
        error_recoverable=True,
        metadata={
            "chunk_id": chunk_id,
            "errors": errors,
            "warnings": warnings,
        }
    )


def instrument_circuit_breaker_halt(
    evaluator: AgentEvaluator,
    task_id: str,
    assumption: str,
    reason: str,
) -> InteractionEvent:
    """Emit a failure event when Circuit Breaker halts a pipeline stage."""
    return evaluator.emit(
        event_type=EventType.FAILURE.value,
        content=f"Circuit Breaker HALT: {reason}",
        task_id=task_id,
        outcome="failure",
        failure_mode=FailureMode.ASSUMPTION_DRIFT.value,
        error_message=reason,
        error_recoverable=False,
        explicit_assumptions=[assumption],
        metadata={
            "halt_type": "circuit_breaker",
            "assumption": assumption,
            "reason": reason,
        }
    )
