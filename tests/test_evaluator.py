"""Tests for the Agent Interaction Evaluator."""

import json
import tempfile
from pathlib import Path

import pytest

from repo_transmute.evaluator import (
    AgentEvaluator,
    EventType,
    FailureMode,
    EvaluatorConfig,
    InteractionEvent,
    AssumptionExtractor,
    DriftDetector,
    AssumptionState,
    DriftSeverity,
    generate_audit,
    format_audit_as_markdown,
    instrument_pipeline_chunk,
    instrument_transpilation_assumption,
    instrument_validation,
    instrument_circuit_breaker_halt,
    EvaluatorSearchIndex,
)


class TestInteractionEvent:
    def test_create_event(self):
        event = InteractionEvent(
            event_type=EventType.TOOL_CALL.value,
            content="Called GitHub API",
            task_id="task-1",
            agent_id="test-agent",
            tool_name="http.call",
            explicit_assumptions=["API returns JSON"],
        )
        assert event.event_type == "tool_call"
        assert event.tool_name == "http.call"
        assert "API returns JSON" in event.explicit_assumptions

    def test_serialize_roundtrip(self):
        event = InteractionEvent(
            event_type=EventType.ASSUMPTION_STATEMENT.value,
            content="Assuming types are preserved",
            task_id="task-2",
            explicit_assumptions=["types are preserved"],
        )
        data = event.to_dict()
        restored = InteractionEvent.from_dict(data)
        assert restored.event_id == event.event_id
        assert restored.content == event.content

    def test_flag_failure(self):
        event = InteractionEvent(
            event_type=EventType.FAILURE.value,
            content="Import error",
            task_id="task-1",
        )
        event.flag_as_failure(
            mode=FailureMode.TOOL_ERROR,
            message="Cannot import module",
            recoverable=True,
        )
        assert event.outcome == "failure"
        assert event.failure_mode == "tool_error"
        assert event.error_recoverable is True

    def test_flag_success(self):
        event = InteractionEvent(
            event_type=EventType.COMPLETION.value,
            content="Task done",
            task_id="task-1",
        )
        event.flag_as_success(metric="latency_ms", value=42)
        assert event.outcome == "success"
        assert event.metadata.get("value") == 42


class TestAssumptionExtractor:
    def test_explicit_assumption_patterns(self):
        extractor = AssumptionExtractor()
        text = "We are assuming the API returns JSON. Under the assumption that types are preserved."
        assumptions = extractor.extract(text)
        assert len(assumptions.explicit) >= 1
        assert assumptions.confidence > 0

    def test_given_that_pattern(self):
        extractor = AssumptionExtractor()
        text = "Given that the repository uses Python 3, we assume the asyncio module is available."
        assumptions = extractor.extract(text)
        assert any("asyncio" in a or "available" in a for a in assumptions.explicit)

    def test_empty_text(self):
        extractor = AssumptionExtractor()
        assumptions = extractor.extract("")
        assert assumptions.explicit == []
        assert assumptions.confidence == 0.0

    def test_lang_pitfalls_go(self):
        extractor = AssumptionExtractor()
        code = "func main() { if err == nil { return } }"
        assumptions = extractor.extract_from_code_chunk(code, target_lang="go")
        # Should have flagged the nil comparison pattern
        assert assumptions.confidence > 0

    def test_llm_fallback_flag(self):
        extractor = AssumptionExtractor()
        # Long text with no explicit patterns should flag LLM fallback
        long_text = (
            "After reviewing the codebase structure and analyzing the import graph, "
            "the transpiler proceeded to convert Python async functions to TypeScript "
            "promises. The error handling was mapped from try/except to try/catch."
        ) * 5
        assumptions = extractor.extract(long_text)
        if "[LLM_FALLBACK_NEEDED]" in assumptions.implicit:
            assert extractor.needs_llm_fallback(assumptions) is True


class TestDriftDetector:
    def test_register_and_detect(self):
        detector = DriftDetector()

        # Register an assumption
        event = InteractionEvent(
            event_type=EventType.ASSUMPTION_STATEMENT.value,
            content="Assuming API returns JSON",
            task_id="task-1",
            explicit_assumptions=["API returns JSON"],
        )
        detector.register(event)

        # New event with contradiction signal
        new_event = InteractionEvent(
            event_type=EventType.SELF_CORRECTION.value,
            content="Wait, actually the API returns XML, not JSON",
            task_id="task-1",
        )
        drifts = detector.detect_drift(task_id="task-1", new_event=new_event)
        assert len(drifts) > 0
        assert drifts[0].prior_assumption == "API returns JSON"

    def test_active_assumptions(self):
        detector = DriftDetector()
        event = InteractionEvent(
            event_type=EventType.ASSUMPTION_STATEMENT.value,
            content="Assuming the database is available",
            task_id="task-1",
            explicit_assumptions=["database is available"],
        )
        detector.register(event)
        active = detector.get_active_assumptions("task-1")
        assert len(active) == 1
        assert active[0].content == "database is available"

    def test_drift_summary(self):
        detector = DriftDetector()
        summary = detector.get_drift_summary()
        assert summary["total"] == 0
        assert summary["recoverable_count"] == 0


class TestAgentEvaluator:
    def test_emit_and_register(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluatorConfig(
                session_id="test-001",
                output_dir=Path(tmpdir),
                emit_to_jsonl=False,
            )
            evaluator = AgentEvaluator(config=config)
            evaluator.emit(
                event_type=EventType.TOOL_CALL.value,
                content="Called HTTP endpoint",
                task_id="task-1",
                tool_name="http.call",
            )
            assert len(evaluator._events) == 1
            assert evaluator._events[0].tool_name == "http.call"

    def test_detect_drift_via_emit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluatorConfig(
                session_id="test-002",
                output_dir=Path(tmpdir),
                emit_to_jsonl=False,
            )
            evaluator = AgentEvaluator(config=config)
            evaluator.emit(
                event_type=EventType.ASSUMPTION_STATEMENT.value,
                content="Assuming input is valid JSON",
                task_id="task-1",
                explicit_assumptions=["input is valid JSON"],
            )
            evaluator.emit(
                event_type=EventType.SELF_CORRECTION.value,
                content="Actually the input is XML, not JSON",
                task_id="task-1",
            )
            drifts = evaluator.detect_drift(task_id="task-1")  # reads from cache populated by emit-time detection
            assert len(drifts) > 0

    def test_generate_audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluatorConfig(
                session_id="test-003",
                output_dir=Path(tmpdir),
                emit_to_jsonl=False,
            )
            evaluator = AgentEvaluator(config=config)
            evaluator.emit(
                event_type=EventType.DELEGATION.value,
                content="Delegating chunk processing",
                task_id="task-1",
            )
            evaluator.emit(
                event_type=EventType.COMPLETION.value,
                content="Chunk processed",
                task_id="task-1",
                outcome="success",
            )
            audit = evaluator.generate_audit()
            assert len(audit.events) == 2
            assert audit.summary["total_events"] == 2

    def test_events_persist_to_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluatorConfig(
                session_id="test-004",
                output_dir=Path(tmpdir),
                emit_to_jsonl=True,
            )
            evaluator = AgentEvaluator(config=config)
            evaluator.emit(
                event_type=EventType.ASSUMPTION_STATEMENT.value,
                content="Assuming types",
                task_id="task-1",
            )
            events_path = config.get_events_path()
            assert events_path.exists()
            with open(events_path) as f:
                lines = f.readlines()
            assert len(lines) == 1
            event_data = json.loads(lines[0])
            assert event_data["content"] == "Assuming types"

    def test_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluatorConfig(session_id="test-005", output_dir=Path(tmpdir), emit_to_jsonl=False)
            evaluator = AgentEvaluator(config=config)
            evaluator.emit(EventType.COMPLETION.value, content="done", task_id="task-1", outcome="success")
            evaluator.emit(EventType.FAILURE.value, content="failed", task_id="task-1", failure_mode=FailureMode.TOOL_ERROR.value, outcome="failure")
            stats = evaluator.stats()
            assert stats["total_events"] == 2
            assert stats["total_failures"] == 1


class TestInstrumentHelpers:
    def test_instrument_pipeline_chunk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluatorConfig(session_id="test-pipeline", output_dir=Path(tmpdir), emit_to_jsonl=False)
            evaluator = AgentEvaluator(config=config)
            event = instrument_pipeline_chunk(
                evaluator=evaluator,
                chunk_id=3,
                language="python",
                target_lang="typescript",
                file_count=5,
                function_count=12,
            )
            assert event.event_type == "chunk_processing"
            assert event.metadata["chunk_id"] == 3
            assert event.metadata["function_count"] == 12

    def test_instrument_transpilation_assumption(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluatorConfig(session_id="test-transpile", output_dir=Path(tmpdir), emit_to_jsonl=False)
            evaluator = AgentEvaluator(config=config)
            event = instrument_transpilation_assumption(
                evaluator=evaluator,
                chunk_id=1,
                source_lang="python",
                target_lang="go",
                assumptions=["nil checks not needed", "errors are returned"],
            )
            assert event.event_type == EventType.ASSUMPTION_STATEMENT.value
            assert "nil checks not needed" in event.explicit_assumptions

    def test_instrument_validation_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluatorConfig(session_id="test-val", output_dir=Path(tmpdir), emit_to_jsonl=False)
            evaluator = AgentEvaluator(config=config)
            event = instrument_validation(
                evaluator=evaluator,
                chunk_id=2,
                passed=False,
                errors=["Missing return type annotation"],
                warnings=["Consider using interface"],
            )
            assert event.outcome == "failure"
            assert "Missing return type" in event.error_message

    def test_instrument_circuit_breaker_halt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = EvaluatorConfig(session_id="test-cb", output_dir=Path(tmpdir), emit_to_jsonl=False)
            evaluator = AgentEvaluator(config=config)
            event = instrument_circuit_breaker_halt(
                evaluator=evaluator,
                task_id="task-pipeline-1",
                assumption="types are preserved",
                reason="Type mismatch detected in pass 2",
            )
            assert event.outcome == "failure"
            assert event.failure_mode == FailureMode.ASSUMPTION_DRIFT.value
            assert event.error_recoverable is False


class TestGenerateAudit:
    def test_audit_from_events(self):
        events = [
            InteractionEvent(
                event_type=EventType.DELEGATION.value,
                content="Process chunk 1",
                task_id="task-1",
                agent_id="coordinator",
            ),
            InteractionEvent(
                event_type=EventType.FAILURE.value,
                content="Import error",
                task_id="task-1",
                agent_id="worker",
                failure_mode=FailureMode.TOOL_ERROR.value,
        outcome="failure",
                error_message="Cannot find module",
                error_recoverable=True,
            ),
        ]
        trail = generate_audit(events, session_id="audit-test-001", task_id="task-1")
        assert trail.summary["total_events"] == 2
        failure_summary = trail.get_failure_summary()
        assert failure_summary["total"] == 1

    def test_format_audit_markdown(self):
        events = [
            InteractionEvent(
                event_type=EventType.COMPLETION.value,
                content="Task done",
                task_id="task-1",
            )
        ]
        trail = generate_audit(events, session_id="audit-md-001")
        md = format_audit_as_markdown(trail)
        assert "audit-md-001" in md
        assert "## Summary" in md
