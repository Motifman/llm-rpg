# Pitfalls Research

**Domain:** Pursuit/follow behavior in an event-driven RPG simulation
**Researched:** 2026-03-11
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Static Path Masquerading as Pursuit

**What goes wrong:**
The pursuer follows a stale path toward where the target used to be rather than where it is now.

**Why it happens:**
Current player movement stores a fixed planned path and static goal metadata, which is correct for static destinations but not for moving targets.

**How to avoid:**
Store pursuit state separately from path state and refresh target-derived movement only at controlled reconciliation points.

**Warning signs:**
Targets move every tick but followers continue to empty tiles or oscillate around old positions.

**Phase to address:**
Phase 1

---

### Pitfall 2: Losing Last-Known Position Too Early

**What goes wrong:**
On target loss, the system cannot continue to the last seen position because that coordinate is cleared before the search/stop logic uses it.

**Why it happens:**
The existing monster chase flow already shows how easy it is to clear last-known position too soon.

**How to avoid:**
Retain last-known position until explicit stop/completion, and add regression tests for visibility-loss transitions.

**Warning signs:**
`TargetLost`-style events fire, but actors immediately idle or fail without moving to the last known location.

**Phase to address:**
Phase 1

---

### Pitfall 3: Tick-Agnostic Replanning

**What goes wrong:**
The system replans too often, fights busy-state timing, or causes rubber-banding.

**Why it happens:**
Movement and world simulation already mark actors busy and skip them during parts of the tick.

**How to avoid:**
Reconcile pursuit on arrival/unblock/target-move edges or bounded intervals, not blindly every tick.

**Warning signs:**
Excessive pathfinding calls, repeated replans while actors are busy, or visually inconsistent movement.

**Phase to address:**
Phase 2

---

### Pitfall 4: Observation Interruptions Silently Erasing Pursuit

**What goes wrong:**
An unrelated observation cancels movement, but the system loses whether pursuit should stop, pause, or resume.

**Why it happens:**
The observation handler can already break movement outside the pursuit lifecycle.

**How to avoid:**
Separate pursuit-state cancellation from path cancellation and define interruption policy explicitly.

**Warning signs:**
Combat/dialogue events cause pursuit to vanish with no terminal reason event.

**Phase to address:**
Phase 2

---

### Pitfall 5: Event Loss on Pursuit Failure

**What goes wrong:**
Pursuit failure occurs, but the LLM-facing reaction never triggers because event handling silently drops or swallows failures.

**Why it happens:**
The current async event path has known fragility and suppressed failures.

**How to avoid:**
Keep correctness-critical pursuit stop/failure events synchronous where practical and add integration tests for handler failure visibility.

**Warning signs:**
Pursuit state stops correctly, but no observation or turn-trigger follows.

**Phase to address:**
Phase 3

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Encode pursuit only as movement path | Faster first implementation | No target identity or structured stop reason | Never |
| Reuse free-form error strings as failure reasons | Avoids new types/events | Brittle LLM handling and poor testability | Never |
| Replan every tick | Simple mental model | Pathfinding churn and noisy behavior | Only in tiny throwaway experiments, not here |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Movement service | Put follow/chase semantics inside generic movement API | Keep movement generic and add pursuit orchestration above it |
| Observation pipeline | Treat pursuit events as formatter-only concerns | Register proper domain events and recipients in infrastructure event registries |
| World simulation | Assume inactive spots still simulate pursuit | Declare or implement explicit inactive-spot semantics |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Replanning on every target move for many actors | Spikes in pathfinding calls per tick | Throttle replans and short-circuit near-target cases | Multi-actor pursuit in one active spot |
| Cache keyed only by static goal | Low cache hit rate for moving targets | Use event-driven invalidation and pursuit-aware refresh policy | As soon as targets move frequently |
| Cross-spot pursuit without scope control | Frozen or confusing offscreen behavior | Narrow v1 scope or define offscreen rules explicitly | When targets/followers leave active spots |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Silent event failure on pursuit stop | Loss of auditability and AI reaction correctness | Surface handler failures and test them |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent cancellation | AI/player appears to “give up” without explanation | Emit reason-coded pursuit stop/failure events |
| Rubber-banding pursuit | Behavior looks broken or inconsistent | Replan at controlled edges, not continuously |
| Unclear completion semantics | Hard to know whether pursuit succeeded, failed, or is ongoing | Model ongoing pursuit as valid state and separate terminal reasons |

## "Looks Done But Isn't" Checklist

- [ ] **Pursuit start:** Verify target identity is stored, not just path coordinates
- [ ] **Visibility loss:** Verify actor goes to last known position before terminal stop
- [ ] **Cancellation:** Verify movement cancel does not silently lose pursuit reason/state
- [ ] **Failure events:** Verify LLM-facing observation/trigger path runs from terminal pursuit events

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Stale path pursuit | MEDIUM | Add explicit pursuit state, separate from movement path, then backfill tests |
| Lost last-known position | LOW | Retain coordinate until explicit stop and add regression coverage |
| Dropped failure events | HIGH | Move key pursuit events to sync handling path or improve error surfacing, then integration-test |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Static path masquerading as pursuit | Phase 1 | Moving-target tests prove latest-known-position updates |
| Losing last-known position too early | Phase 1 | Visibility-loss regression tests pass |
| Tick-agnostic replanning | Phase 2 | Pathfinding/replan counts stay bounded in tests |
| Observation interruptions silently erasing pursuit | Phase 2 | Interruption tests preserve explicit pursuit outcome |
| Event loss on pursuit failure | Phase 3 | Integration tests confirm observation + LLM trigger path |

## Sources

- `.planning/PROJECT.md`
- `.planning/codebase/CONCERNS.md`
- `src/ai_rpg_world/application/world/services/movement_service.py`
- `src/ai_rpg_world/application/world/services/world_simulation_service.py`
- `src/ai_rpg_world/application/world/services/caching_pathfinding_service.py`
- `src/ai_rpg_world/application/observation/handlers/observation_event_handler.py`
- `src/ai_rpg_world/domain/monster/service/behavior_state_transition_service.py`
- `src/ai_rpg_world/domain/monster/aggregate/monster_aggregate.py`

---
*Pitfalls research for: pursuit/follow behavior*
*Researched: 2026-03-11*
