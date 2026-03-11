# Phase 6 Research: Player Pursuit Runtime Assembly Closure

**Phase:** 06-player-pursuit-runtime-assembly-closure  
**Researched:** 2026-03-11  
**Focus:** what the planner must know to close the non-test player pursuit runtime gap for `PURS-03`, `PURS-04`, `PURS-05`, `RUNT-01`, and `OBSV-02`

## What This Phase Actually Is

Phase 6 is not a new pursuit-behavior phase. The player pursuit command flow, continuation state machine, observation formatting, and turn-resume behavior already exist in isolated runtime seams:

- `PursuitCommandService` can start and cancel pursuit.
- `PursuitContinuationService` can refresh visible pursuit, continue toward frozen `last_known`, and fail with structured reasons.
- pursuit events are already registered in the observation pipeline.
- pursuit failed/cancelled observations already set `schedules_turn=True` and `breaks_movement=False`.

The gap is composition, not domain logic. The milestone audit is explicit: the repo still lacks a non-test runtime assembly path that wires both player pursuit start and player pursuit continuation into the same live runtime.

Planner implication: treat Phase 6 as a composition-closure phase centered on one authoritative bootstrap path, not as another round of pursuit algorithm work.

## Requirement Translation

- `PURS-03`: start pursuit must lead to actual world-tick continuation in the live runtime, not only in tests.
- `PURS-04`: losing sight of the target must still continue toward `last_known` through the live tick path.
- `PURS-05`: cancel pursuit must be exposed on the same live player path that exposes start pursuit.
- `RUNT-01`: player pursuit must be assembled into `MovementApplicationService` plus `WorldSimulationApplicationService.tick()`.
- `OBSV-02`: pursuit failure/cancel must reach the existing observation handler and schedule LLM resumption on the live path.

## Current Code Reality

### 1. The pursuit services already exist and are implementation-ready

`src/ai_rpg_world/application/world/services/pursuit_command_service.py` already owns player pursuit start/cancel. It validates actor placement, current visibility, target kind, and writes aggregate state inside its own unit of work.

Key seam:
- `start_pursuit(...)` and `cancel_pursuit(...)` at `src/ai_rpg_world/application/world/services/pursuit_command_service.py:85`
- constructor dependencies at `src/ai_rpg_world/application/world/services/pursuit_command_service.py:38`

`src/ai_rpg_world/application/world/services/pursuit_continuation_service.py` already owns the tick-time continuation state machine.

Key seam:
- `evaluate_tick(...)` at `src/ai_rpg_world/application/world/services/pursuit_continuation_service.py:85`
- visible refresh and replan at `src/ai_rpg_world/application/world/services/pursuit_continuation_service.py:128`
- frozen `last_known` continuation and failure outcomes at `src/ai_rpg_world/application/world/services/pursuit_continuation_service.py:199`

Planner implication: do not spend Phase 6 re-implementing pursuit semantics unless a composition bug exposes a small missing adapter. The real work is assembling these services into one non-test runtime.

### 2. World tick already supports pursuit continuation, but only optionally

`WorldSimulationApplicationService` accepts `movement_service` and `pursuit_continuation_service` as optional dependencies.

Key seam:
- constructor accepts optional `pursuit_continuation_service` at `src/ai_rpg_world/application/world/services/world_simulation_service.py:124`
- player movement prepass calls `_advance_pending_player_movements(...)` at `src/ai_rpg_world/application/world/services/world_simulation_service.py:184`
- pursuit continuation only runs when `self._pursuit_continuation_service is not None` at `src/ai_rpg_world/application/world/services/world_simulation_service.py:329`

Current failure mode:
- if `movement_service` exists but `pursuit_continuation_service` is omitted, the runtime still boots
- active pursuit then silently degrades into “advance only if some plain path already exists”
- no fail-fast or capability assertion exposes the missing wire

Planner implication: Phase 6 must either make the player runtime assemble this dependency unconditionally, or introduce an explicit bootstrap contract that fails fast when a pursuit-enabled runtime omits it.

### 3. LLM tool wiring already supports pursuit start/cancel, but only optionally

`create_llm_agent_wiring(...)` already supports pursuit tools, but only when `pursuit_command_service` is injected.

Key seam:
- optional `pursuit_command_service` parameter at `src/ai_rpg_world/application/llm/wiring/__init__.py:179`
- pursuit tools are enabled only when non-`None` at `src/ai_rpg_world/application/llm/wiring/__init__.py:323`
- tool mapper receives it as `pursuit_service` at `src/ai_rpg_world/application/llm/wiring/__init__.py:352`

Tool execution already exists:
- `ToolCommandMapper` validates `start_pursuit` and `cancel_pursuit` on the injected service
- if absent, pursuit tools are effectively unavailable

Planner implication: wiring only world tick is insufficient. Phase 6 must also inject `PursuitCommandService` into the same live LLM runtime path.

### 4. Observation and LLM resumption are already implemented downstream

Phase 4 already completed the downstream side of `OBSV-02`.

Key seams:
- pursuit events are registered in `_OBSERVED_EVENT_TYPES` at `src/ai_rpg_world/infrastructure/events/observation_event_handler_registry.py:177`
- pursuit recipients are resolved through `PursuitRecipientStrategy` at `src/ai_rpg_world/application/observation/services/observation_recipient_resolver.py:102`
- pursuit failed/cancelled observations set `schedules_turn=True` and `breaks_movement=False` at `src/ai_rpg_world/application/observation/services/observation_formatter.py:1380`
- observation handler appends output and schedules turns when `schedules_turn` is true at `src/ai_rpg_world/application/observation/handlers/observation_event_handler.py:131`
- world tick runs scheduled turns after the unit of work at `src/ai_rpg_world/application/world/services/world_simulation_service.py:292`

Planner implication: Phase 6 must not invent new resumption logic. It only needs to ensure the live player runtime actually emits pursuit events into the already-wired observation path.

### 5. There is still no non-test runtime assembly path under `src/`

The only explicit runtime seam in `src/` is the generic LLM bootstrap:

- `compose_llm_runtime(...)` in `src/ai_rpg_world/application/llm/bootstrap.py:31`

But that function is only a pass-through:

- it forwards `**wiring_kwargs` into `create_llm_agent_wiring(...)`
- it optionally calls a caller-provided `composition_builder`
- it optionally calls a caller-provided `service_builder`
- it does not build pursuit services itself

The repo search results only show pursuit assembly in tests, not in a non-test bootstrap or presentation entrypoint.

Planner implication: Phase 6 likely needs to create or upgrade one concrete runtime composition module in `src/` that assembles:

1. `PursuitCommandService`
2. `PursuitContinuationService`
3. `create_llm_agent_wiring(..., pursuit_command_service=...)`
4. `EventHandlerComposition(..., observation_registry=...)`
5. `WorldSimulationApplicationService(..., movement_service=..., pursuit_continuation_service=..., llm_turn_trigger=..., reflection_runner=...)`

## Architecture Decision The Planner Must Make Early

Pick one owner for live player runtime composition.

The codebase currently has reusable parts but no authoritative “player runtime bootstrap” that guarantees they are assembled together. If the plan spreads assembly across multiple callers, this gap can recur.

Recommended decision:
- create one concrete bootstrap/composer for the player + LLM + observation + world runtime path
- keep `create_llm_agent_wiring(...)` as the library seam
- keep `compose_llm_runtime(...)` as a generic helper only if Phase 6 adds a higher-level wrapper that actually assembles pursuit

Good outcome:
- one function or module returns a pursuit-capable runtime package
- callers cannot accidentally wire LLM pursuit tools without world-tick continuation
- callers cannot accidentally wire world-tick continuation without observation/turn-resume path

Bad outcome:
- multiple places manually construct subsets of the runtime
- Phase 6 “passes” with another test-only composition
- future callers keep treating pursuit as optional by omission

## Recommended Composition Shape

### Composition responsibilities

The non-test player runtime assembler should build, in this order:

1. `world_query_service`
2. `movement_service`
3. `pursuit_command_service`
4. `pursuit_continuation_service`
5. `wiring_result = create_llm_agent_wiring(..., pursuit_command_service=pursuit_command_service, movement_service=movement_service, ...)`
6. `event_handler_composition` with `observation_registry=wiring_result.observation_registry`
7. `world_simulation_service` with:
   - `movement_service=movement_service`
   - `pursuit_continuation_service=pursuit_continuation_service`
   - `llm_turn_trigger=wiring_result.llm_turn_trigger`
   - `reflection_runner=wiring_result.reflection_runner`

### Why this ownership is correct

- `PursuitCommandService` is the upstream seam for LLM tool-driven start/cancel.
- `PursuitContinuationService` is the upstream seam for world-tick continuation.
- observation/turn-resume is already downstream and only needs pursuit events to actually occur on the live path.
- `WorldSimulationApplicationService` is the only runtime seam that can close start -> continuation -> observation -> turn-resume in a single execution path.

## Specific Planning Risks

### 1. Silent capability loss is the real regression risk

Both pursuit seams are optional today. That means the runtime can boot while pursuit is only half-enabled.

Examples:
- `pursuit_command_service` omitted: pursuit tools disappear from LLM runtime
- `pursuit_continuation_service` omitted: start may succeed in some entrypoint, but tick continuation never runs
- observation registry omitted from event composition: pursuit fail/cancel events never resume LLM turns

The plan should include either:
- fail-fast assertions in the new bootstrap, or
- a named runtime profile/capability object that makes “pursuit-enabled runtime” explicit and testable

### 2. `compose_llm_runtime(...)` currently hides the gap rather than closing it

`compose_llm_runtime(...)` sounds like a full runtime builder, but it only forwards dependencies. That naming mismatch is part of why this gap survived.

Planner implication:
- either upgrade it so the pursuit-capable player runtime is composed there
- or create a clearer higher-level bootstrap and leave `compose_llm_runtime(...)` documented as a low-level seam

### 3. The same test shape can pass without proving shipped behavior

The repo already has strong integration tests around the parts. The audit gap exists because those tests do not prove a non-test runtime entrypoint actually assembles the same path.

Planner implication:
- at least one Phase 6 regression must instantiate the non-test bootstrap/composer from `src/`
- do not stop at constructing services directly inside the test body, because that is exactly the coverage pattern that missed this gap

### 4. Do not reopen Phase 3 or Phase 4 scope accidentally

Tempting but out of scope:
- rewriting continuation semantics
- changing observation payload schemas again
- adding a new turn-trigger mechanism
- changing monster pursuit behavior

Phase 6 should only add the narrow adapter work needed to compose already-built seams together.

## Likely Plan Split

### 06-01: Create the live player runtime assembler

Goal:
- establish one non-test composition module that builds pursuit-capable player runtime pieces together

Include:
- instantiate `PursuitCommandService`
- instantiate `PursuitContinuationService`
- pass `pursuit_command_service` into `create_llm_agent_wiring(...)`
- pass `pursuit_continuation_service` into `WorldSimulationApplicationService`
- register `observation_registry` through `EventHandlerComposition`
- add fail-fast or explicit capability checks so pursuit cannot be silently omitted in this runtime path

Primary deliverable:
- one authoritative composition path under `src/`

### 06-02: Connect the full player pursuit execution path

Goal:
- prove that the assembled runtime supports:
  start pursuit -> world tick continuation -> pursuit outcome event -> observation -> LLM turn scheduling

Include:
- LLM-triggered pursuit start through the live tool wiring
- same runtime tick path executing pursuit continuation
- pursuit fail/cancel reaching observation handler and scheduling turn
- end-of-tick `run_scheduled_turns()` still using the existing world simulation seam

Primary risk to cover:
- only wiring start or only wiring continuation

### 06-03: Add regression coverage against recurrence

Goal:
- lock the composition contract so the gap cannot recur through future optional-argument drift

Include:
- tests against the non-test bootstrap/composer, not just direct service construction
- assertions that pursuit tools are enabled in the assembled runtime
- assertions that `WorldSimulationApplicationService` inside the assembled runtime has a non-`None` continuation service
- assertions that observation registry is present in the same runtime
- one end-to-end regression proving failed/cancelled pursuit schedules LLM resumption through that assembled path

## Don’t Hand-Roll

- Do not add a second pursuit-specific event delivery path. Reuse `ObservationEventHandler`.
- Do not add a second LLM turn queue. Reuse `ILlmTurnTrigger` and `run_scheduled_turns()`.
- Do not create a second world-tick pursuit loop outside `WorldSimulationApplicationService`.
- Do not hide pursuit wiring inside tests only.

## Open Questions The Planner Should Resolve Up Front

1. Which module should own the new concrete runtime assembly?

Recommendation:
- prefer a dedicated bootstrap/composition module near `application/llm/bootstrap.py` or a new presentation/runtime module
- avoid burying this inside tests or a narrow infra container that the game runtime does not use

2. Should the pursuit-capable runtime fail fast when a required pursuit dependency is missing?

Recommendation:
- yes, for the new Phase 6 composition path
- keep lower-level library seams generic, but make the new high-level runtime path explicit and strict

3. Should Phase 6 return a richer composition result object?

Recommendation:
- probably yes if it improves testability
- exposing the built `pursuit_command_service`, `pursuit_continuation_service`, `event_handler_composition`, and `world_simulation_service` in one returned object would make recurrence tests much cleaner

4. Do we need to change public APIs or only add a new assembler?

Recommendation:
- prefer adding one assembler over broad API changes
- only widen API surfaces if existing builder signatures make strict assembly impossible

## Validation Architecture

### 1. Composition Contract Validation

Validate the new non-test runtime assembler directly.

Must prove:
- pursuit tools are enabled in the returned LLM wiring
- observation registry is part of the returned event composition
- world simulation holds a non-`None` `pursuit_continuation_service`
- world simulation also uses the same `llm_turn_trigger` returned by wiring

This is the most important validation layer because it closes the exact audit gap.

### 2. Start-To-Continuation Runtime Validation

Instantiate the real Phase 6 bootstrap, not manually assembled mocks, and prove:

- the LLM/tool path can call pursuit start
- the resulting player aggregate enters active pursuit
- a subsequent world tick invokes pursuit continuation through `WorldSimulationApplicationService`

This validates `PURS-03`, `PURS-04`, and `RUNT-01` at the composed-runtime level.

### 3. Observation Resumption Validation

Using the same assembled runtime, prove:

- pursuit failed or cancelled events are observed through the registered observation handler
- the observation output schedules an LLM turn
- `WorldSimulationApplicationService.tick()` runs scheduled turns through the existing trigger

This validates `OBSV-02` on the real player runtime path.

### 4. Recurrence Guard Validation

Add narrow regressions that fail if future refactors omit either optional pursuit seam.

Examples:
- assembled runtime exposes no pursuit tools
- assembled world simulation lacks continuation service
- assembled event composition omits observation registry
- start pursuit succeeds but no continuation is evaluated on tick

These tests should target the high-level assembler, not only the lower-level services.

## Planner Bottom Line

Plan Phase 6 as a bootstrap/composition closure phase with one authoritative player runtime assembly path. The code already has the player pursuit command service, continuation service, observation wiring, and LLM resumption semantics. What is still missing is the one non-test runtime path that assembles all of them together and makes omission impossible or at least obvious.

If the plan does not create and verify that single composition path, the audit gap can recur even if all lower-level pursuit tests keep passing.
