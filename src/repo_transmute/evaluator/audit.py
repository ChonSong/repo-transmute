"""Audit trail generation for agent interactions.

Produces structured, queryable audit logs that answer:
- What did each agent decide?
- On what information did it base that decision?
- Who authorized or delegated?
- Where did failures occur and what propagated?

Integrates with the txtai semantic index for searchability.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from repo_transmute.evaluator.events import InteractionEvent, EventType
from repo_transmute.evaluator.drift_detector import DriftDetector, DriftEvent


@dataclass
class DecisionRecord:
    """A consequential decision made by an agent."""
    decision_id: str
    task_id: str
    agent_id: str
    timestamp: str
    decision: str           # What was decided
    basis: str              # What information the decision was based on
    authority: str          # Who/what authorized this decision
    outcome: str            # What resulted
    alternatives_considered: List[str] = field(default_factory=list)
    dissenting_views: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "decision_id": self.decision_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "decision": self.decision,
            "basis": self.basis,
            "authority": self.authority,
            "outcome": self.outcome,
            "alternatives_considered": self.alternatives_considered,
            "dissenting_views": self.dissenting_views,
            "metadata": self.metadata,
        }


@dataclass
class AuditTrail:
    """A complete audit trail for a session or task."""
    session_id: str
    task_id: Optional[str] = None
    decisions: List[DecisionRecord] = field(default_factory=list)
    events: List[InteractionEvent] = field(default_factory=list)
    drift_events: List[DriftEvent] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "decisions": [d.to_dict() for d in self.decisions],
            "events": [e.to_dict() for e in self.events],
            "drift_events": [d.to_dict() for d in self.drift_events],
            "generated_at": self.generated_at,
            "summary": self.summary,
        }

    def to_json(self, path: Optional[Path] = None) -> str:
        """Serialize to JSON and optionally write to file."""
        content = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return content

    def get_decision_chain(self) -> List[DecisionRecord]:
        """Return decisions in chronological order."""
        return sorted(self.decisions, key=lambda d: d.timestamp)

    def get_failure_summary(self) -> Dict[str, Any]:
        """Summarize failures across the audit trail."""
        failures = [e for e in self.events if e.outcome == "failure"]
        if not failures:
            return {"total": 0, "failure_modes": {}, "recoverable_rate": 1.0}

        by_mode: Dict[str, int] = {}
        recoverable_count = sum(1 for f in failures if f.error_recoverable)

        for f in failures:
            mode = f.failure_mode or "unknown"
            by_mode[mode] = by_mode.get(mode, 0) + 1

        return {
            "total": len(failures),
            "failure_modes": by_mode,
            "recoverable_rate": recoverable_count / len(failures),
        }


def generate_audit(
    events: List[InteractionEvent],
    session_id: str,
    task_id: Optional[str] = None,
    drift_events: Optional[List[DriftEvent]] = None,
) -> AuditTrail:
    """Generate an audit trail from a list of events.

    Args:
        events: All interaction events
        session_id: The session this audit covers
        task_id: Optional specific task to audit (vs full session)
        drift_events: Optional pre-computed drift events

    Returns:
        An AuditTrail with decisions, events, drift, and summary
    """
    trail = AuditTrail(
        session_id=session_id,
        task_id=task_id,
        events=events,
        drift_events=drift_events or [],
    )

    # Extract decision records from events
    decisions: Dict[str, DecisionRecord] = {}

    for event in events:
        if event.event_type in (
            EventType.DELEGATION.value,
            EventType.SELF_CORRECTION.value,
            EventType.COMPLETION.value,
        ):
            # Build the basis string from context
            basis_parts = []
            if event.context_used:
                basis_parts.append(f"used: {', '.join(event.context_used[:3])}")
            if event.explicit_assumptions:
                basis_parts.append(f"assumed: {', '.join(event.explicit_assumptions[:2])}")
            basis = "; ".join(basis_parts) if basis_parts else "no explicit basis recorded"

            decision = DecisionRecord(
                decision_id=f"dec-{event.event_id[:8]}",
                task_id=event.task_id,
                agent_id=event.agent_id,
                timestamp=event.timestamp,
                decision=event.content[:200] if event.content else "(no description)",
                basis=basis,
                authority=event.agent_id,
                outcome=event.outcome,
                metadata=event.metadata,
            )
            decisions[event.event_id] = decision
            trail.decisions.append(decision)

        elif event.event_type == EventType.FAILURE.value:
            # Add failure as a decision record (decision to proceed despite risk)
            decision = DecisionRecord(
                decision_id=f"dec-fail-{event.event_id[:8]}",
                task_id=event.task_id,
                agent_id=event.agent_id,
                timestamp=event.timestamp,
                decision=f"FAILURE: {event.error_message or event.failure_mode or 'unknown'}",
                basis=f"failure_mode={event.failure_mode}",
                authority=event.agent_id,
                outcome="failure",
                metadata={"recoverable": event.error_recoverable},
            )
            trail.decisions.append(decision)

    # Build summary
    event_types: Dict[str, int] = {}
    for e in events:
        event_types[e.event_type] = event_types.get(e.event_type, 0) + 1

    trail.summary = {
        "total_events": len(events),
        "event_types": event_types,
        "total_decisions": len(trail.decisions),
        "total_drift_events": len(drift_events) if drift_events else 0,
        "failure_summary": trail.get_failure_summary(),
    }

    return trail


def format_audit_as_markdown(trail: AuditTrail) -> str:
    """Format an audit trail as readable markdown."""
    lines = [
        f"# Audit Trail — Session {trail.session_id}",
        "",
        f"**Generated:** {trail.generated_at}",
        f"**Task:** {trail.task_id or 'full session'}",
        "",
        "## Summary",
    ]

    for key, val in trail.summary.items():
        lines.append(f"- **{key}:** {val}")

    if trail.decisions:
        lines.extend(["", "## Decision Chain", ""])
        for i, decision in enumerate(trail.get_decision_chain(), 1):
            lines.append(f"### {i}. {decision.decision[:80]}...")
            lines.append(f"- **Agent:** {decision.agent_id}  ")
            lines.append(f"- **Timestamp:** {decision.timestamp}")
            lines.append(f"- **Basis:** {decision.basis}")
            lines.append(f"- **Outcome:** {decision.outcome}")
            lines.append("")

    if trail.drift_events:
        lines.extend(["", "## Drift Events", ""])
        for drift in trail.drift_events:
            severity_marker = "🔴" if drift.severity == "high" else (
                "🟡" if drift.severity == "medium" else "⚪"
            )
            lines.append(f"{severity_marker} [{drift.severity.upper()}] {drift.contradiction}")
            lines.append(f"  - Prior: {drift.prior_assumption[:80]}")
            lines.append(f"  - Agent acted on invalid: {drift.acted_on_invalid}")
            lines.append("")

    failure_summary = trail.get_failure_summary()
    if failure_summary.get("total", 0) > 0:
        lines.extend(["", "## Failures", ""])
        lines.append(f"Total failures: {failure_summary['total']}")
        for mode, count in failure_summary.get("failure_modes", {}).items():
            lines.append(f"- **{mode}:** {count}")

    return "\n".join(lines)
