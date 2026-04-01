# ADR-001: Automatic Task Cascade on Blocker Completion

**Status:** Draft  
**Date:** 2026-03-29  
**Author:** Alto (via Zoul)  
**PR:** (pending)

---

## Context

ClawTeam manages task dependencies via `blocked_by` relationships. When a task is marked as completed, any tasks that were blocked by it currently remain in a `blocked` state unless manually cleared by an agent or human.

This creates a coordination gap: the `TaskWaiter` can wait for *all* tasks to complete, but it cannot automatically wake the next wave of work when a dependency clears. In a swarm of 5-10 agents, this means the leader must continuously poll and manually unblock — defeating the purpose of autonomous coordination.

---

## Decision

Introduce an **automatic task cascade** mechanism: when a task transitions to `completed`, the system will automatically check all other tasks that list it in their `blocked_by` field. If that task was the *only* remaining blocker for a dependent task, the dependent task's `blocked` status will be cleared and its status will revert to `pending`.

---

## Design

### Core Behavior

```
Task B (status=blocked, blocked_by=[task_a_id])
Task A (status=completed)

→ On Task A completion:
  → Find all tasks where blocked_by includes task_a_id
  → For each such task:
      → If all other blockers are already completed:
          → Remove task_a_id from blocked_by
          → If blocked_by becomes empty: set status = pending
          → Optionally: notify the task's owner via inbox
```

### Integration Point

The `TaskWaiter` class already polls task status in its wait loop. The cascade logic should be triggered at the same point where it checks task completion:

```python
# In TaskWaiter.wait() — step 3 (Check task status)
# After: completed = sum(1 for t in tasks if t.status == TaskStatus.completed)
# Add:
_cascade_unblock(task_store, completed_task_ids)
```

A dedicated function `_cascade_unblock(task_store, newly_completed)` keeps the logic isolated and testable.

### New Fields (optional, for observability)

No new persistent fields required. The following can be derived:
- `blocked_by` is already in `TaskItem`
- Cascade events can be logged to `task.metadata["cascade_unblocked_by"]` for debugging

### Notification (optional enhancement)

When a task is auto-unblocked, a message can be sent to its `owner` via the mailbox:

```python
if task.owner:
    mailbox.send(
        from_agent="system",
        to=task.owner,
        content=f"Task '{task.subject}' is now unblocked and ready.",
    )
```

This is **optional** and should be guarded by a config flag: `CLAWTEAM_CASCADE_NOTIFY=true/false`.

---

## Consequences

### Positive
- Agents can run autonomously in waves — no human/leader polling required between waves
- The `TaskWaiter` remains the single coordination primitive
- Backward compatible — cascade is opt-in (disabled by default via `CLAWTEAM_CASCADE_ENABLED=false`)
- Works with existing `TaskStore` interface — no store changes needed

### Negative
- If an agent marks a task `completed` prematurely, cascade may trigger work that shouldn't start yet
- Race condition possible if two blockers complete simultaneously — mitigated by atomic read-modify-write on the task store

### Alternatives Considered

| Alternative | Why Not |
|------------|---------|
| Leader-agent manually calls unblock | Defeats autonomy; requires leader to poll |
| Separate `CascadeWatcher` daemon | Extra process; TaskWaiter already polls |
| Automatic task completion detection + message | More complex; requires agent to opt in |

---

## Implementation Plan

1. **Add `_cascade_unblock()` function** in `clawteam/team/waiter.py`
2. **Wire it into `TaskWaiter.wait()`** after the task status check
3. **Add config flag** `clawteam.cascade_enabled` (default `false`)
4. **Add config flag** `clawteam.cascade_notify` (default `false`)
5. **Write tests** in `tests/test_waiter.py` covering:
   - Single blocker completion → dependent unblocked
   - Multiple blockers → only unblocks when all complete
   - No false unblock when one of many blockers remains
   - Cascade does not fire when config flag is off
6. **Update ROADMAP.md** with cascade as a completed Phase 1 item

---

## Configuration

```toml
# ~/.clawteam/config.toml
[cascade]
enabled = true       # Default: false
notify = true         # Default: false, send inbox message on unblock
```

Or via CLI:
```bash
clawteam config set cascade.enabled true
clawteam config set cascade.notify false
```

---

## Testing Scenarios

| Scenario | Input | Expected Output |
|----------|-------|-----------------|
| Single blocker done | Task B blocked_by=[A], A=completed | B.status → pending |
| All blockers done | Task C blocked_by=[A,B], A=completed, B=completed | C.status → pending |
| One blocker remains | Task D blocked_by=[A,B], A=completed, B=pending | D.status stays blocked |
| Cascade disabled | enabled=false, A=completed | No change to B |
| Task has no owner | B.owner="", B unblocked | No message sent |

---

## Open Questions

1. Should cascade firing be logged to a file or visible in `clawteam task history`?
2. Should there be a maximum cascade depth (e.g., only one wave per completion event)?
3. Should agents spawned by the cascade inherit any context from the completed blocker task?
