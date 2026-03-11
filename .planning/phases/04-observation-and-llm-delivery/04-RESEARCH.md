# Phase 4 Research: Observation And LLM Delivery

**Phase:** 04-observation-and-llm-delivery  
**Researched:** 2026-03-11  
**Focus:** planner guidance for OUTC-03, RUNT-03, OBSV-01, OBSV-02

## What The Planner Needs To Know

Phase 4 is a delivery/wiring phase. Phase 3 already emits pursuit domain events with structured outcomes; Phase 4 must connect those outcomes to the observation pipeline and make sure LLM turn resumption happens through the existing event-driven path.

Today, pursuit events are **not** connected to observation delivery. The planner should treat this phase as a three-layer integration task:

1. Register pursuit events in observation event registry.
2. Resolve recipients for pursuit events.
3. Format pursuit observations with explicit interruption/outcome semantics and proper `schedules_turn` policy.

Without all three, events are still effectively invisible to LLM.

## Requirements Translation (What Each ID Means In Code)

- `OBSV-01`: Add pursuit event types to observation registry + resolver + formatter so buffer receives entries.
- `OUTC-03`: Ensure `PursuitFailedEvent` observation contains machine-readable failure reason (enum value) and human-readable prose.
- `RUNT-03`: Explicitly distinguish:
  - movement interruption (`breaks_movement` caused by another event while pursuit may remain active)
  - pursuit interruption/end (`PursuitCancelledEvent` / `PursuitFailedEvent`)
- `OBSV-02`: Set `schedules_turn` on pursuit fail/cancel observations so existing `ObservationEventHandler -> ILlmTurnTrigger -> WorldSimulationApplicationService.tick()` flow resumes LLM turns when needed.

## Current Code Reality

### 1. Pursuit events already exist with required failure structure

`PursuitFailedEvent` already carries:
- `failure_reason: PursuitFailureReason`
- `last_known`
- `target_snapshot`

See [pursuit_events.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/pursuit/event/pursuit_events.py).

This is enough to satisfy the data side of `OUTC-03` if propagated to observation output.

### 2. Observation registry currently does not subscribe to pursuit events

`_OBSERVED_EVENT_TYPES` does not include any pursuit event.

See [observation_event_handler_registry.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/infrastructure/events/observation_event_handler_registry.py).

Result: pursuit domain events are never passed to `ObservationEventHandler`.

### 3. Recipient strategies do not support pursuit events

No strategy currently `supports(...)` pursuit event classes.

See:
- [observation_recipient_resolver.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/observation/services/observation_recipient_resolver.py)
- [default_recipient_strategy.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/observation/services/recipient_strategies/default_recipient_strategy.py)
- [monster_recipient_strategy.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/observation/services/recipient_strategies/monster_recipient_strategy.py)

Even if registry is updated, recipients would resolve to empty without a new/updated strategy.

### 4. Observation formatter does not handle pursuit events

`ObservationFormatter` imports and handles many event types, but none from `domain.pursuit.event`.

See [observation_formatter.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/observation/services/observation_formatter.py).

Even with registry+recipient wiring, output would be `None` unless formatter is extended.

### 5. LLM re-drive path already exists and should be reused unchanged

Current flow is already correct for `OBSV-02`:
- observation output with `schedules_turn=True`
- `ObservationEventHandler._maybe_schedule_turn(...)`
- `DefaultLlmTurnTrigger.schedule_turn(...)`
- end of tick: `WorldSimulationApplicationService.tick()` calls `run_scheduled_turns()`

See:
- [observation_event_handler.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/observation/handlers/observation_event_handler.py)
- [llm_turn_trigger.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/llm/services/llm_turn_trigger.py)
- [world_simulation_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_simulation_service.py)

Phase 4 should not add a second turn trigger mechanism.

### 6. Prompt and memory implications

- Immediate LLM prompt uses observation **prose** in recent events.
- Structured observation payload is used by memory extraction for stable IDs/scope.

See:
- [recent_events_formatter.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/llm/services/recent_events_formatter.py)
- [memory_extractor.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/llm/services/memory_extractor.py)

Planner implication: pursuit formatting must include both clear prose and stable structured keys.

## Standard Stack

- Keep existing event-driven stack (`EventPublisher`, async observation handler, existing LLM trigger).
- Keep `ObservationOutput` as the integration contract (`prose`, `structured`, `schedules_turn`, `breaks_movement`).
- Keep pursuit outcome enum as source of truth (`PursuitFailureReason`).

No new third-party library is needed.

## Architecture Patterns

### Pattern 1: Registry + Resolver + Formatter must move together

Treat pursuit observation support as one atomic vertical slice. Partial wiring creates silent drops.

### Pattern 2: Use dedicated pursuit recipient strategy

Add `PursuitRecipientStrategy` rather than overloading `DefaultRecipientStrategy`, because pursuit has actor/target semantics closer to combat-style relation routing.

Recommended recipient policy:
- Always include pursuing actor if actor is a player.
- Include target if target resolves to player.
- Optionally include nearby players at actor spot only if the observation is intended to be social; default to actor-only for fail/cancel to reduce noise.

### Pattern 3: Observation type schema with explicit interruption semantics

Define structured payload types for pursuit outcomes, e.g.:
- `pursuit_started`
- `pursuit_updated`
- `pursuit_failed`
- `pursuit_cancelled`

For `RUNT-03`, include explicit fields such as:
- `interruption_scope`: `"movement" | "pursuit"`
- `pursuit_status_after_event`: `"active" | "ended"`
- `failure_reason` (for failed)

This makes movement interruption vs pursuit interruption explicit in observations.

## Don’t Hand-Roll

- Do not add a new LLM trigger queue; reuse `ILlmTurnTrigger`.
- Do not bypass `ObservationEventHandler`; keep all observation delivery through resolver/formatter/buffer.
- Do not encode failure reasons as prose-only text; keep enum-backed structured field.

## Common Pitfalls

- Registering pursuit events but forgetting resolver support: no recipients, no buffer entries.
- Adding formatter logic but not registry wiring: formatter never called.
- Setting `breaks_movement=True` for pursuit failed/cancelled events: unnecessary and can cause redundant movement cancellation behavior.
- Forgetting `schedules_turn=True` on pursuit fail/cancel: LLM does not resume reliably after outcome events.
- Treating movement cancel (path clear) as pursuit end: violates `RUNT-03` and existing phase decisions.

## Recommended Plan Split

### 04-01: Pursuit Observation Wiring

Goal: satisfy `OBSV-01` by connecting pursuit events end-to-end.

Include:
- Add pursuit event classes to observation registry.
- Add `PursuitRecipientStrategy` and register it in resolver composition.
- Add resolver tests for actor/target delivery and dedupe behavior.

Primary files:
- [observation_event_handler_registry.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/infrastructure/events/observation_event_handler_registry.py)
- [observation_recipient_resolver.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/observation/services/observation_recipient_resolver.py)
- `application/observation/services/recipient_strategies/`

### 04-02: Pursuit Formatter Payloads + Turn Scheduling

Goal: satisfy `OUTC-03`, `RUNT-03`, and `OBSV-02` behaviorally.

Include:
- Add pursuit formatting methods in `ObservationFormatter`.
- Ensure `PursuitFailedEvent` structured payload includes `failure_reason` as enum `.value`.
- Encode explicit interruption distinction fields (`interruption_scope`, `pursuit_status_after_event`).
- Set `schedules_turn=True` for at least failed/cancelled pursuit outcomes.
- Keep `breaks_movement=False` for pursuit outcome events.

Primary files:
- [observation_formatter.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/observation/services/observation_formatter.py)
- [dtos.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/observation/contracts/dtos.py) (only if contract extension is truly needed)

### 04-03: Integration and Regression Validation

Goal: lock end-to-end event-driven behavior.

Include:
- Observation registry test includes pursuit event registration.
- Formatter tests for pursuit fail/cancel prose + structured fields + schedule flags.
- Event-handler tests: pursuit fail/cancel appends observation and calls `schedule_turn` for LLM-controlled players.
- Wiring integration test: publish pursuit failure event -> observation buffered -> `run_scheduled_turns()` executes.
- Runtime distinction test: movement interruption event during active pursuit does not end pursuit, and observations still differentiate movement interruption vs pursuit end.

Primary test targets:
- [test_observation_event_handler.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/observation/test_observation_event_handler.py)
- [test_observation_formatter.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/observation/test_observation_formatter.py)
- [test_observation_recipient_resolver_extended_events.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/observation/test_observation_recipient_resolver_extended_events.py)
- [test_llm_wiring_integration.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/llm/test_llm_wiring_integration.py)

## Validation Architecture

1. Registration Layer
- Assert pursuit events are subscribed in observation registry under async handlers.

2. Resolution Layer
- Assert correct recipients for pursuit actor/target combinations.

3. Formatting Layer
- Assert structured reason fidelity (`failure_reason` string values).
- Assert explicit interruption semantics fields for `RUNT-03`.
- Assert schedule/break flags are correct.

4. Event-Driven LLM Layer
- Assert pursuit fail/cancel observations schedule LLM turns via existing trigger path.

5. Runtime Distinction Layer
- Assert movement interruption can occur while pursuit remains active.
- Assert pursuit interruption/end is represented by pursuit events and clearly distinguishable in observation payloads.

## Open Questions To Resolve Early In Planning

1. Recipient scope for pursuit updates:
- actor-only vs actor+target vs nearby observers. Recommendation: actor-only for fail/cancel in v1.

2. Whether to emit observation for `PursuitUpdatedEvent`:
- It may be noisy at tick cadence. Recommendation: include started/failed/cancelled first, add updated only if explicitly needed.

3. Where to attach movement-interruption-vs-pursuit-status metadata:
- formatter-only vs handler-side augmentation from player status. Recommendation: start formatter-side for pursuit outcome events; add handler-side augmentation only if RUNT-03 tests still fail to be explicit enough.

