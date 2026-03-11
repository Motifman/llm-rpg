# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-11)

**Core value:** LLMエージェントが、静的な目的地指定だけでなく、動的に移動する主体に対しても一貫した状態遷移とイベント駆動で行動を継続できること
**Current focus:** Phase 1: Pursuit Domain Vocabulary

## Current Position

Phase: 1 of 5 (Pursuit Domain Vocabulary)
Plan: 2 of 3 in current phase
Status: Ready to execute next plan
Last activity: 2026-03-11 — Plan 01-02 completed with explicit pursuit lifecycle events and payload regression coverage

Progress: [██░░░░░░░░] 17%

## Performance Metrics

**Velocity:**
- Total plans completed: 1
- Average duration: 7 min
- Total execution time: 14 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-pursuit-domain-vocabulary | 2 | 14 min | 7 min |

**Recent Trend:**
- Last 5 plans: 8 min, 6 min
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

### Pending Todos

None yet.

### Blockers/Concerns

- Pursuit state must not be collapsed into static movement path state
- Busy-state timing and observation-driven movement interruption can conflict with pursuit continuation
- Async event failure visibility is weak in the current UoW/event pipeline
- Git commits for this plan were blocked by sandbox permissions on `.git/index.lock`

## Session Continuity

Last session: 2026-03-11 17:46
Stopped at: Plan 01-02 completed; Phase 1 is ready for plan 01-03
Resume file: None
