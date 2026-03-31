"""Agent Interaction Evaluator for RepoTransmute.

Provides structured evaluation of agentic interactions:
- Event logging (delegation, tool calls, assumption statements, self-corrections)
- Assumption extraction from LLM outputs
- Drift detection across interaction chains
- Semantic search over interaction history via txtai
- Audit trail generation

Usage:
    from repo_transmute.evaluator import AgentEvaluator, EventType, emit_event

    evaluator = AgentEvaluator(session_id="run-001")

    evaluator.emit(
        event_type=EventType.ASSUMPTION_STATEMENT,
        content="Assuming API returns valid JSON",
        task_id="task-1",
        explicit_assumptions=["API returns valid JSON"],
    )

    evaluator.emit(
        event_type=EventType.TOOL_CALL,
        content="Called GitHub API",
        task_id="task-1",
        context_used=["repo_owner", "repo_name"],
    )

    drifts = evaluator.detect_drift(task_id="task-1")
    audit = evaluator.generate_audit()
    print(audit.to_json())
"""

from repo_transmute.evaluator.events import (
    InteractionEvent,
    EventType,
    FailureMode,
    emit_event,
    load_events,
    save_events,
)
from repo_transmute.evaluator.assumption_extractor import AssumptionExtractor, Assumptions
from repo_transmute.evaluator.drift_detector import (
    DriftDetector,
    DriftEvent,
    DriftSeverity,
    AssumptionState,
)
from repo_transmute.evaluator.audit import AuditTrail, generate_audit, format_audit_as_markdown
from repo_transmute.evaluator.interface import (
    AgentEvaluator,
    EvaluatorConfig,
    instrument_pipeline_chunk,
    instrument_transpilation_assumption,
    instrument_validation,
    instrument_circuit_breaker_halt,
)
from repo_transmute.evaluator.search import EvaluatorSearchIndex

__all__ = [
    # Core events
    "InteractionEvent",
    "EventType",
    "FailureMode",
    "emit_event",
    "load_events",
    "save_events",
    # Assumption extraction
    "AssumptionExtractor",
    "Assumptions",
    # Drift detection
    "DriftDetector",
    "DriftEvent",
    "DriftSeverity",
    "AssumptionState",
    # Audit
    "AuditTrail",
    "generate_audit",
    "format_audit_as_markdown",
    # Main evaluator
    "AgentEvaluator",
    "EvaluatorConfig",
    # Instrumentation helpers
    "instrument_pipeline_chunk",
    "instrument_transpilation_assumption",
    "instrument_validation",
    "instrument_circuit_breaker_halt",
    # Search
    "EvaluatorSearchIndex",
]
