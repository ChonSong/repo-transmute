"""Structured event schema for agent interactions."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any, Union


class EventType(str, Enum):
    """Types of interaction events."""
    DELEGATION = "delegation"
    TOOL_CALL = "tool_call"
    ASSUMPTION_STATEMENT = "assumption_statement"
    BELIEF_UPDATE = "belief_update"
    SELF_CORRECTION = "self_correction"
    FAILURE = "failure"
    COMPLETION = "completion"
    QUERY = "query"
    VERIFICATION = "verification"
    UNKNOWN = "unknown"


class FailureMode(str, Enum):
    """Classifications of failure types."""
    HALLUCINATION = "hallucination"
    CONTEXT_MISS = "context_miss"
    ASSUMPTION_DRIFT = "assumption_drift"
    TOOL_ERROR = "tool_error"
    CASCADE = "cascade"
    UNKNOWN = "unknown"


@dataclass
class InteractionEvent:
    """A structured event in an agent interaction."""

    # Identity
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    task_id: str = ""

    # Temporal
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Structural
    event_type: str = EventType.UNKNOWN.value
    agent_id: str = "anonymous"

    # Content
    content: str = ""
    tool_name: Optional[str] = None

    # Context tracking
    context_available: List[str] = field(default_factory=list)
    context_used: List[str] = field(default_factory=list)
    parent_task_id: Optional[str] = None

    # Assumption tracking
    explicit_assumptions: List[str] = field(default_factory=list)
    implicit_beliefs: List[str] = field(default_factory=list)

    # Outcome
    outcome: str = "unknown"
    failure_mode: Optional[str] = None

    # Error details
    error_message: Optional[str] = None
    error_recoverable: bool = False

    # Chain tracking
    span_id: Optional[str] = None
    trace_id: Optional[str] = None

    # Free-form metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InteractionEvent":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "InteractionEvent":
        return cls.from_dict(json.loads(s))

    def flag_as_failure(
        self,
        mode: FailureMode,
        message: str,
        recoverable: bool = False,
        **metadata
    ):
        self.outcome = "failure"
        self.failure_mode = mode.value
        self.error_message = message
        self.error_recoverable = recoverable
        if metadata:
            self.metadata.update(metadata)

    def flag_as_success(self, **metadata):
        self.outcome = "success"
        if metadata:
            self.metadata.update(metadata)

    def add_assumption(self, assumption: str, implicit: bool = False):
        if implicit:
            self.implicit_beliefs.append(assumption)
        else:
            self.explicit_assumptions.append(assumption)


def emit_event(
    evaluator: "AgentEvaluator",
    event_type: Union[EventType, str],
    content: str = "",
    task_id: str = "",
    agent_id: str = "anonymous",
    **kwargs
) -> InteractionEvent:
    from repo_transmute.evaluator.interface import AgentEvaluator

    if isinstance(event_type, EventType):
        event_type = event_type.value

    event = InteractionEvent(
        event_type=event_type,
        content=content,
        task_id=task_id or getattr(evaluator, "current_task_id", ""),
        agent_id=agent_id,
        session_id=getattr(evaluator, "session_id", ""),
        **kwargs
    )
    evaluator.register(event)
    return event


def load_events(path: Path) -> List[InteractionEvent]:
    events = []
    if not path.exists():
        return events
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(InteractionEvent.from_dict(json.loads(line)))
                except Exception:
                    continue
    return events


def save_events(events: List[InteractionEvent], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
