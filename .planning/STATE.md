# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-11)

**Core value:** LLMエージェントが、静的な目的地指定だけでなく、動的に移動する主体に対しても一貫した状態遷移とイベント駆動で行動を継続できること
**Current focus:** Phase 2: Player Pursuit Commands

## Current Position

Phase: 2 of 5 (Player Pursuit Commands)
Plan: 0 of 2 in current phase
Status: Ready for planning
Last activity: 2026-03-11 — Plan 01-03 completed with aggregate-owned pursuit state, movement separation regressions, and monster alignment strategy

Progress: [███░░░░░░░] 30%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 9 min
- Total execution time: 28 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-pursuit-domain-vocabulary | 3 | 28 min | 9 min |

**Recent Trend:**
- Last 5 plans: 8 min, 6 min, 14 min
- Trend: Stable

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Initialization: v1 completed when pursuit state and events work correctly, not when guaranteed capture exists
- Initialization: v1 target scope is players and monsters only
- Initialization: pursuit failures must carry structured reasons for LLM replanning
- 01-01: Pursuit vocabulary lives under `domain/pursuit` and stays separate from player static movement fields
- 01-01: `last_known` is modeled as an explicit value object reusable by later event payloads
- 01-01: `cancelled` remains outside `PursuitFailureReason`
- 01-02: Pursuit lifecycle events use neutral `actor_id` and `target_id` fields on `BaseDomainEvent[WorldObjectId, str]`
- 01-02: `PursuitCancelledEvent` remains distinct from `PursuitFailedEvent` and carries no failure reason field
- 01-02: All pursuit lifecycle events retain `last_known` context; started events also require a visible `target_snapshot`
- 01-03: `PlayerStatusAggregate` now owns optional `pursuit_state` separately from `_current_destination`, `_planned_path`, and `goal_*`
- 01-03: Pursuit lifecycle changes stay behind aggregate methods and do not implicitly clear when movement path state changes
- 01-03: Monster `CHASE`/`SEARCH` state, `TargetSpottedEvent`, and `TargetLostEvent` are the Phase 5 alignment touchpoints for neutral pursuit vocabulary

### Pending Todos

None yet.

### Blockers/Concerns

- Busy-state timing and observation-driven movement interruption can conflict with pursuit continuation
- Async event failure visibility is weak in the current UoW/event pipeline

## Session Continuity

Last session: 2026-03-11 18:02
Stopped at: Phase 1 completed; next step is planning Phase 2 plan 02-01
Resume file: None
