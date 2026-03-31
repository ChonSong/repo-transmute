"""Semantic search over agent interaction events via txtai.

Provides:
- Indexing of events, assumptions, drift events, and audit trails
- Semantic search across the interaction history
- Cross-repo pattern detection
- Filter by event type, agent, outcome, severity
"""

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from repo_transmute.txtai.client import TxtaiClient


class EvaluatorSearchIndex:
    """Semantic search index over agent interaction events.

    Wraps the RepoTransmute TxtaiClient with evaluator-specific schemas
    and search methods.

    Usage:
        index = EvaluatorSearchIndex(session_id="run-001")

        # Index events as they complete
        index.index_event(event)
        index.index_drift(drift_event)

        # Search across the history
        results = index.search("agent hallucinated type mapping")
        patterns = index.cross_repo_patterns()
    """

    # Document types for indexing
    DOC_TYPE_EVENT = "evaluator_event"
    DOC_TYPE_DRIFT = "drift_event"
    DOC_TYPE_AUDIT = "audit_trail"

    def __init__(
        self,
        session_id: str,
        index_path: Optional[Path] = None,
        txtai_client: Optional[TxtaiClient] = None,
    ):
        self.session_id = session_id
        self._client = txtai_client or TxtaiClient()
        self._index_path = Path(index_path) if index_path else Path(f"./data/txtai/evaluator/{session_id}")
        self._docs: List[Dict[str, Any]] = []

        # Fields that get embedded
        self._embed_fields = [
            "content",
            "event_type",
            "explicit_assumptions",
            "failure_mode",
            "outcome",
        ]

    def index_event(self, event: "InteractionEvent") -> str:
        """Index a single interaction event.

        Returns the doc UID.
        """
        doc = {
            "uid": f"event-{event.event_id}",
            "type": self.DOC_TYPE_EVENT,
            "session_id": event.session_id,
            "task_id": event.task_id,
            "agent_id": event.agent_id,
            "event_type": event.event_type,
            "content": event.content,
            "explicit_assumptions": " ".join(event.explicit_assumptions),
            "implicit_beliefs": " ".join(event.implicit_beliefs),
            "context_used": " ".join(event.context_used),
            "outcome": event.outcome,
            "failure_mode": event.failure_mode or "",
            "error_message": event.error_message or "",
            "timestamp": event.timestamp,
            "metadata": event.metadata,
        }

        uid = self._client.add(doc)
        self._docs.append(doc)
        return uid

    def index_drift(self, drift: "DriftEvent") -> str:
        """Index a drift event."""
        doc = {
            "uid": f"drift-{drift.drift_id}",
            "type": self.DOC_TYPE_DRIFT,
            "session_id": drift.task_id,  # reuse task_id as session proxy
            "task_id": drift.task_id,
            "severity": drift.severity,
            "prior_assumption": drift.prior_assumption,
            "contradiction": drift.contradiction,
            "new_information": drift.new_information,
            "acted_on_invalid": str(drift.acted_on_invalid),
            "recoverable": str(drift.recoverable),
            "resolution": drift.resolution or "",
            "detected_at": drift.detected_at,
        }

        uid = self._client.add(doc)
        self._docs.append(doc)
        return uid

    def index_audit(self, trail: "AuditTrail") -> str:
        """Index a full audit trail summary."""
        # Index summary as a single doc
        summary_text = self._summarize_trail(trail)
        doc = {
            "uid": f"audit-{trail.session_id}",
            "type": self.DOC_TYPE_AUDIT,
            "session_id": trail.session_id,
            "content": summary_text,
            "total_events": str(trail.summary.get("total_events", 0)),
            "total_decisions": str(trail.summary.get("total_decisions", 0)),
            "total_drift": str(trail.summary.get("total_drift_events", 0)),
            "failure_summary": str(trail.summary.get("failure_summary", {})),
            "generated_at": trail.generated_at,
        }

        uid = self._client.add(doc)
        self._docs.append(doc)
        return uid

    def search(
        self,
        query: str,
        limit: int = 10,
        doc_type: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search over indexed events.

        Args:
            query: Natural language query
            limit: Max results
            doc_type: Filter to event/drift/audit type
            session_id: Filter to session
            task_id: Filter to task

        Returns:
            List of matching documents with scores
        """
        filters = {}
        if doc_type:
            filters["type"] = doc_type
        if session_id:
            filters["session_id"] = session_id
        if task_id:
            filters["task_id"] = task_id

        return self._client.search(query, limit=limit, filters=filters)

    def search_events(
        self,
        query: str,
        limit: int = 10,
        **filters
    ) -> List[Dict[str, Any]]:
        """Search only events."""
        return self.search(query, limit=limit, doc_type=self.DOC_TYPE_EVENT, **filters)

    def search_drifts(
        self,
        query: str,
        limit: int = 10,
        min_severity: Optional[str] = None,
        **filters
    ) -> List[Dict[str, Any]]:
        """Search only drift events, optionally filtered by minimum severity."""
        results = self.search(query, limit=limit, doc_type=self.DOC_TYPE_DRIFT, **filters)

        if min_severity:
            severity_order = ["low", "medium", "high", "critical"]
            min_idx = severity_order.index(min_severity)
            results = [
                r for r in results
                if severity_order.index(r.get("severity", "low")) >= min_idx
            ]

        return results

    def cross_repo_patterns(
        self,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Detect cross-session/task patterns in drift and failure events.

        Returns patterns grouped by contradiction type, failure mode,
        or assumption pattern across the indexed history.
        """
        # Find all drift events
        all_drifts = self.search(
            "assumption contradiction drift",
            limit=100,
            doc_type=self.DOC_TYPE_DRIFT,
        )

        # Group by contradiction keywords
        patterns: Dict[str, List] = {}
        for drift in all_drifts:
            contradiction = drift.get("contradiction", "")
            if not contradiction:
                continue

            # Simple keyword extraction
            keywords = ["context_miss", "assumption_drift", "hallucination", "type", "import"]
            key = "other"
            for kw in keywords:
                if kw.lower() in contradiction.lower():
                    key = kw
                    break

            if key not in patterns:
                patterns[key] = []
            patterns[key].append(drift)

        return patterns

    def get_failure_hotspots(
        self,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find the most common failure patterns.

        Returns failure modes and contexts ranked by frequency.
        """
        filters = {"type": self.DOC_TYPE_EVENT, "outcome": "failure"}
        if session_id:
            filters["session_id"] = session_id

        failures = self._client.search(
            "failure error",
            limit=500,
            filters=filters,
        )

        # Tally by failure_mode and event_type
        by_mode: Dict[str, int] = {}
        by_context: Dict[str, int] = {}

        for f in failures:
            mode = f.get("failure_mode", "unknown")
            by_mode[mode] = by_mode.get(mode, 0) + 1

            # Extract context from content
            content = f.get("content", "")
            if "chunk" in content.lower():
                by_context["chunk_processing"] = by_context.get("chunk_processing", 0) + 1
            elif "transpil" in content.lower():
                by_context["transpilation"] = by_context.get("transpilation", 0) + 1
            elif "validation" in content.lower():
                by_context["validation"] = by_context.get("validation", 0) + 1

        return {
            "by_failure_mode": sorted(by_mode.items(), key=lambda x: -x[1]),
            "by_context": sorted(by_context.items(), key=lambda x: -x[1]),
        }

    def _summarize_trail(self, trail: "AuditTrail") -> str:
        """Build a text summary of an audit trail for indexing."""
        parts = [
            f"Session {trail.session_id}",
            f"Task: {trail.task_id or 'full session'}",
            f"Events: {trail.summary.get('total_events', 0)}",
            f"Decisions: {trail.summary.get('total_decisions', 0)}",
            f"Drift events: {trail.summary.get('total_drift_events', 0)}",
        ]

        for decision in trail.decisions[:5]:
            parts.append(f"Decision: {decision.decision[:100]}")

        return " | ".join(parts)

    def stats(self) -> Dict[str, Any]:
        """Return index statistics."""
        return {
            "session_id": self.session_id,
            "indexed_docs": len(self._docs),
            "index_path": str(self._index_path),
            "doc_types": {},
        }
