---
phase: 04-observation-and-llm-delivery
plan: 01
subsystem: infra
tags: [observation, pursuit, event-publisher, recipient-resolution, pytest]
requires:
  - phase: 03-pursuit-continuation-loop
    provides: pursuit lifecycle events emitted during continuation and failure paths
provides:
  - registry subscriptions for pursuit lifecycle events on the observation handler
  - dedicated pursuit recipient resolution for actor and target world objects
  - regression coverage for pursuit recipient routing and duplicate suppression
affects: [04-02, observation-formatting, llm-delivery]
tech-stack:
  added: []
  patterns: [event registry subscription via shared observation handler, strategy-based recipient resolution]
key-files:
  created:
    - src/ai_rpg_world/application/observation/services/recipient_strategies/pursuit_recipient_strategy.py
  modified:
    - src/ai_rpg_world/infrastructure/events/observation_event_handler_registry.py
    - src/ai_rpg_world/application/observation/services/observation_recipient_resolver.py
    - src/ai_rpg_world/application/observation/services/recipient_strategies/__init__.py
    - tests/application/observation/test_observation_recipient_resolver_extended_events.py
key-decisions:
  - "Pursuit lifecycle events stay on the existing async ObservationEventHandler registry path rather than adding a bypass."
  - "Pursuit recipient resolution explicitly includes the actor when resolvable and optionally the target when it resolves to a player."
patterns-established:
  - "Pursuit observation wiring uses a dedicated recipient strategy ahead of DefaultRecipientStrategy."
  - "Actor and target WorldObjectId values are translated through WorldObjectToPlayerResolver for deterministic player delivery."
requirements-completed: [OUTC-03, RUNT-03, OBSV-01, OBSV-02]
duration: 6min
completed: 2026-03-11
---

# Phase 4 Plan 1: Observation Wiring Summary

**Pursuit lifecycle events now enter the observation pipeline through the shared registry and resolve deterministic actor/target recipients for downstream formatter delivery**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-11T12:18:00Z
- **Completed:** 2026-03-11T12:23:59Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Registered pursuit started, updated, failed, and cancelled events in the shared observation handler registry.
- Added `PursuitRecipientStrategy` and composed it into `create_observation_recipient_resolver(...)` ahead of the default fallback.
- Added regression tests for actor-only delivery, actor-plus-target delivery, non-player target handling, and duplicate prevention.

## Task Commits

Each task was committed atomically:

1. **Task 1: Register pursuit lifecycle events in the observation handler registry** - `5b323a2` (feat)
2. **Task 2: Add and compose a dedicated pursuit recipient strategy** - `6fb75e0` (feat)
3. **Task 3: Add recipient regression tests for pursuit actor/target routing** - `f42a680` (test)

## Files Created/Modified
- `src/ai_rpg_world/infrastructure/events/observation_event_handler_registry.py` - Adds pursuit lifecycle events to `_OBSERVED_EVENT_TYPES`.
- `src/ai_rpg_world/application/observation/services/recipient_strategies/pursuit_recipient_strategy.py` - Resolves pursuit recipients from actor and target world objects.
- `src/ai_rpg_world/application/observation/services/recipient_strategies/__init__.py` - Exports the pursuit strategy for resolver composition.
- `src/ai_rpg_world/application/observation/services/observation_recipient_resolver.py` - Inserts pursuit handling into the strategy chain before the default fallback.
- `tests/application/observation/test_observation_recipient_resolver_extended_events.py` - Covers pursuit routing and dedup behavior.

## Decisions Made
- Pursuit observation delivery remains event-publisher-driven and reuses the existing async observation handler registration path.
- Pursuit recipient scope for this plan is intentionally narrow: actor is required when resolvable, target is included only when it resolves to a player, and no nearby observer fanout is introduced.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Test fixture setup for a non-player pursuit target needed an existing `ObjectTypeEnum` value, so the regression uses `NPC` to represent a resolvable non-player world object.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Pursuit lifecycle events can now reach the observation formatter and handler stages through the normal architecture.
- Phase 04-02 can build payload semantics on top of this wiring without revisiting registry or recipient resolution plumbing.

---
*Phase: 04-observation-and-llm-delivery*
*Completed: 2026-03-11*

## Self-Check: PASSED
