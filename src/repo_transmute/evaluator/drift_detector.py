"""Drift detection across agent interaction sequences.

Detects when an agent's stated or implied assumptions become invalid
due to new information, context changes, or prior failures.

The core mechanism:
1. Track assumption state over time per task_id
2. When new events arrive, check for contradictions with prior assumptions
3. Flag drift events with severity and recoverability
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Optional, Set, Tuple

from repo_transmute.evaluator.events import InteractionEvent, EventType, FailureMode


class DriftSeverity(str, Enum):
    """How severe the drift is."""
    LOW = "low"       # Minor context shift, easily corrected
    MEDIUM = "medium" # Agent may have acted on wrong premise, recoverable
    HIGH = "high"     # Agent definitely acted on wrong premise, needs review
    CRITICAL = "critical"  # Cascade failure likely


@dataclass
class AssumptionState:
    """Tracks the state of a single assumption over time."""
    assumption_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    invalidated: bool = False
    invalidated_at: Optional[str] = None
    invalidated_reason: Optional[str] = None
    triggered_by: Optional[str] = None  # event_id that caused invalidation
    times_used: int = 0  # How many times the agent referenced this assumption


@dataclass
class DriftEvent:
    """A detected drift incident."""
    drift_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    severity: str = DriftSeverity.MEDIUM.value
    prior_assumption: str = ""
    new_information: str = ""
    contradiction: str = ""  # What specifically contradicts what
    invalidated_assumption_ids: List[str] = field(default_factory=list)
    acted_on_invalid: bool = False  # Did the agent act before the drift was detected?
    recoverable: bool = True
    resolution: Optional[str] = None  # How it was or should be resolved
    metadata: Dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "drift_id": self.drift_id,
            "task_id": self.task_id,
            "detected_at": self.detected_at,
            "severity": self.severity,
            "prior_assumption": self.prior_assumption,
            "new_information": self.new_information,
            "contradiction": self.contradiction,
            "invalidated_assumption_ids": self.invalidated_assumption_ids,
            "acted_on_invalid": self.acted_on_invalid,
            "recoverable": self.recoverable,
            "resolution": self.resolution,
            "metadata": self.metadata,
        }


class DriftDetector:
    """Detects assumption drift in agent interaction sequences.

    Usage:
        detector = DriftDetector()

        # Register events as they happen
        detector.register(event_with_assumption)
        detector.register(event_with_new_context)
        detector.register(event_with_self_correction)

        # Check for drift after each event
        drifts = detector.detect_drift(task_id="task-123")

        # Or check all tasks
        all_drifts = detector.detect_all_drifts()
    """

    def __init__(self):
        # task_id -> list of AssumptionStates in order
        self._assumption_states: Dict[str, List[AssumptionState]] = {}
        # task_id -> event_id -> event (for looking up context)
        self._event_index: Dict[str, Dict[str, InteractionEvent]] = {}
        # All detected drift events
        self._drift_events: List[DriftEvent] = []

        # Keywords that signal a context shift (new information arrived)
        self.CONTEXT_SHIFT_KEYWORDS = {
            "but", "however", "actually", "wait", "correction",
            "on second thought", "let me reconsider", "i was wrong",
            "looking back", "re-reading", "it seems", "i notice",
            "new information", "updated", "changed", "now i see",
        }

    def register(self, event: InteractionEvent):
        """Index an event for drift detection.

        Extracts assumptions from the event and tracks them.
        """
        if event.task_id not in self._assumption_states:
            self._assumption_states[event.task_id] = []
            self._event_index[event.task_id] = {}

        self._event_index[event.task_id][event.event_id] = event

        # Extract and register explicit assumptions
        for assumption_text in event.explicit_assumptions:
            state = AssumptionState(content=assumption_text)
            self._assumption_states[event.task_id].append(state)

        # Also register implicit beliefs
        for belief_text in event.implicit_beliefs:
            if belief_text == "[LLM_FALLBACK_NEEDED]":
                continue
            state = AssumptionState(content=belief_text)
            self._assumption_states[event.task_id].append(state)

    def detect_drift(
        self,
        task_id: str,
        new_event: Optional[InteractionEvent] = None,
        new_information: Optional[str] = None,
    ) -> List[DriftEvent]:
        """Detect drift for a specific task.

        Call this after registering a new event that might have
        introduced contradictory information.

        Args:
            task_id: The task to check
            new_event: The new event to evaluate (if not yet registered)
            new_information: Free-text new information to check against

        Returns:
            List of DriftEvents detected
        """
        drifts = []

        # Check context shift keywords in new event content
        content_to_check = []
        if new_event:
            content_to_check.append(new_event.content.lower())
        if new_information:
            content_to_check.append(new_information.lower())

        for content in content_to_check:
            for keyword in self.CONTEXT_SHIFT_KEYWORDS:
                if keyword in content:
                    # Potential drift detected — find contradicting assumptions
                    for state in self._assumption_states.get(task_id, []):
                        if not state.invalidated:
                            contradiction = self._check_contradiction(
                                state.content, content, new_event
                            )
                            if contradiction:
                                drift = self._build_drift_event(
                                    task_id=task_id,
                                    state=state,
                                    new_event=new_event,
                                    new_information=new_information or content,
                                    contradiction=contradiction,
                                )
                                drifts.append(drift)
                                self._drift_events.append(drift)
                                # Mark assumption as invalidated
                                state.invalidated = True
                                state.invalidated_at = datetime.now(timezone.utc).isoformat()
                                state.invalidated_reason = contradiction
                                if new_event:
                                    state.triggered_by = new_event.event_id
                                break

        return drifts

    def detect_all_drifts(self) -> List[DriftEvent]:
        """Run drift detection across all tracked tasks."""
        all_drifts = []
        for task_id in self._assumption_states:
            drifts = self.detect_drift(task_id)
            all_drifts.extend(drifts)
        return all_drifts

    def get_active_assumptions(self, task_id: str) -> List[AssumptionState]:
        """Get assumptions that haven't been invalidated for a task."""
        return [
            s for s in self._assumption_states.get(task_id, [])
            if not s.invalidated
        ]

    def get_invalidated_assumptions(self, task_id: str) -> List[AssumptionState]:
        """Get assumptions that were invalidated for a task."""
        return [
            s for s in self._assumption_states.get(task_id, [])
            if s.invalidated
        ]

    def _check_contradiction(
        self,
        assumption: str,
        new_content: str,
        new_event: Optional[InteractionEvent]
    ) -> Optional[str]:
        """Check if new content contradicts an existing assumption.

        Uses lightweight heuristics. For full contradiction detection,
        use LLM-based comparison (not implemented here to keep it fast).

        Returns:
            A string describing the contradiction, or None if no contradiction.
        """
        assumption_lower = assumption.lower()
        new_lower = new_content.lower()

        # Direct negation patterns
        negation_patterns = [
            (f"not {assumption_lower[:30]}", assumption_lower[:30]),
            (f"doesn't {assumption_lower[:30]}", assumption_lower[:30]),
            (f"isn't {assumption_lower[:30]}", assumption_lower[:30]),
            (f"wasn't {assumption_lower[:30]}", assumption_lower[:30]),
            (f"won't {assumption_lower[:30]}", assumption_lower[:30]),
        ]

        for negation, original in negation_patterns:
            if negation in new_lower or original in new_lower:
                # Heuristic: if the new content contains the negated original
                # (but was previously stated as true), it's a contradiction
                return f"Contradiction: previous assumption '{assumption[:50]}' appears negated by new content"

        # Self-correction signals
        if new_event and new_event.event_type == EventType.SELF_CORRECTION.value:
            return f"Self-correction detected: agent revised previous assumption '{assumption[:50]}'"

        # Failure mode signals
        if new_event and new_event.event_type == EventType.FAILURE.value:
            fm = new_event.failure_mode
            if fm == FailureMode.CONTEXT_MISS.value:
                return f"Context miss: agent lacked information related to assumption '{assumption[:50]}'"
            elif fm == FailureMode.ASSUMPTION_DRIFT.value:
                return f"Explicit assumption drift flagged: '{assumption[:50]}'"

        return None

    def _build_drift_event(
        self,
        task_id: str,
        state: AssumptionState,
        new_event: Optional[InteractionEvent],
        new_information: str,
        contradiction: str,
    ) -> DriftEvent:
        """Build a DriftEvent from detected drift."""
        severity = DriftSeverity.MEDIUM

        # Determine if agent acted on the invalid assumption
        acted_on_invalid = (
            state.times_used > 0 and
            new_event is not None and
            new_event.event_type in (EventType.TOOL_CALL.value, EventType.DELEGATION.value)
        )

        if acted_on_invalid and new_event and new_event.event_type == EventType.DELEGATION.value:
            severity = DriftSeverity.HIGH
        elif new_event and new_event.event_type == EventType.SELF_CORRECTION.value:
            severity = DriftSeverity.LOW

        return DriftEvent(
            task_id=task_id,
            severity=severity.value,
            prior_assumption=state.content,
            new_information=new_information[:200],
            contradiction=contradiction,
            invalidated_assumption_ids=[state.assumption_id],
            acted_on_invalid=acted_on_invalid,
            recoverable=True,
            metadata={
                "assumption_created_at": state.created_at,
                "triggered_by_event": new_event.event_id if new_event else None,
            }
        )

    def get_drift_summary(self) -> Dict:
        """Get a summary of all drift events."""
        if not self._drift_events:
            return {"total": 0, "by_severity": {}, "recoverable_count": 0}

        by_severity = {}
        recoverable_count = 0
        for d in self._drift_events:
            by_severity[d.severity] = by_severity.get(d.severity, 0) + 1
            if d.recoverable:
                recoverable_count += 1

        return {
            "total": len(self._drift_events),
            "by_severity": by_severity,
            "recoverable_count": recoverable_count,
            "critical_count": by_severity.get(DriftSeverity.CRITICAL.value, 0),
        }
