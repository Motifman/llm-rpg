# Phase 2 Research: Player Pursuit Commands

**Phase:** 02-player-pursuit-commands  
**Researched:** 2026-03-11  
**Focus:** planner guidance for explicit pursuit start/cancel commands, validation, and state/event reflection only

## What The Planner Needs To Know

Phase 2 should be planned as an application-entry phase, not a pursuit-loop phase. The domain already has the pursuit vocabulary and lifecycle events. What is missing is the player-facing command/service layer that:

- validates a pursuit target from current visible world state
- transitions from static movement to pursuit cleanly
- exposes explicit cancel semantics separate from `cancel_movement`
- reflects the result through existing LLM tool plumbing and application DTO/error patterns

The planner should avoid pulling Phase 3/4 concerns into this phase. Do not add tick-based continuation, last-known refresh automation outside start/refresh, observation registry wiring, or LLM re-trigger behavior here.

## Current Code Reality

### 1. Pursuit lifecycle already exists in the aggregate

`PlayerStatusAggregate` already owns pursuit state separately from static movement state and emits the domain events Phase 2 needs to reflect:

- `start_pursuit(...)` stores `PursuitState` and emits `PursuitStartedEvent` at [src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L255)
- `update_pursuit(...)` emits only on meaningful change at [src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L285)
- `cancel_pursuit(...)` emits `PursuitCancelledEvent` and clears only pursuit state at [src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L349)

Important constraint: `start_pursuit` rejects switching targets while another pursuit is active; callers must cancel the old one first at [player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L262). That directly matches the Phase 2 context decision that “switch target” is a service responsibility, not an aggregate responsibility.

Existing regression coverage already enforces separation from static movement:

- pursuit start does not populate static destination/path at [tests/domain/player/aggregate/test_player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/domain/player/aggregate/test_player_status_aggregate.py#L688)
- failing pursuit does not clear static path at [tests/domain/player/aggregate/test_player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/domain/player/aggregate/test_player_status_aggregate.py#L731)
- clearing static path does not cancel pursuit at [tests/domain/player/aggregate/test_player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/domain/player/aggregate/test_player_status_aggregate.py#L750)
- explicit cancel emits a cancellation event at [tests/domain/player/aggregate/test_player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/domain/player/aggregate/test_player_status_aggregate.py#L769)

### 2. The application-service pattern is already established by movement

`MovementApplicationService` is the clearest template for Phase 2 command services:

- public entrypoint delegates into `_..._impl` inside `UnitOfWork` at [src/ai_rpg_world/application/world/services/movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/movement_service.py#L179)
- domain/application exceptions are normalized through `_execute_with_error_handling` at [movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/movement_service.py#L91)
- command DTOs are small frozen dataclasses with local validation in [src/ai_rpg_world/application/world/contracts/commands.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/contracts/commands.py#L18)
- app exceptions use typed `error_code`s for LLM-facing failure behavior in [src/ai_rpg_world/application/world/exceptions/command/movement_command_exception.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/exceptions/command/movement_command_exception.py#L9)

Planner implication: Phase 2 should likely add a dedicated pursuit command service and its own command DTOs/exceptions, rather than hiding pursuit start/cancel inside `MovementApplicationService`.

### 3. Static movement cancel semantics are intentionally narrower than pursuit cancel semantics

`cancel_movement` only clears static path/destination state:

- implementation at [src/ai_rpg_world/application/world/services/movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/movement_service.py#L361)
- underlying aggregate method is `clear_path()` at [src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py#L246)

Current regressions make that separation explicit:

- `tick_movement` can clear static path while leaving pursuit intact at [tests/application/world/services/test_movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/world/services/test_movement_service.py#L506)
- `cancel_movement` clears path and returns a success/failure DTO, but does not touch pursuit state at [tests/application/world/services/test_movement_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/world/services/test_movement_service.py#L762)

Planner implication: do not overload existing `cancel_movement` for pursuit stop. Phase 2 needs a separate pursuit cancel entrypoint that may call movement-path clearing as a side effect.

### 4. Visibility resolution already exists and should be reused instead of hand-rolling

The current player-visible world surface is already modeled:

- `WorldQueryService.get_visible_context(...)` delegates to `PlayerCurrentStateBuilder.build_visible_context(...)` at [src/ai_rpg_world/application/world/services/world_query_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/world_query_service.py#L260)
- LOS filtering happens in `VisibleObjectReadModelBuilder.build_visible_objects(...)` using `physical_map.is_visible(...)` at [src/ai_rpg_world/application/world/services/visible_object_read_model_builder.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/visible_object_read_model_builder.py#L63)
- regression for LOS filtering exists at [tests/application/world/services/test_player_current_state_builder.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/world/services/test_player_current_state_builder.py#L140)

This matters because the phase context requires “currently visible targets only.” The safest Phase 2 plan is to resolve pursuit targets against the same visible-object read model already used for LLM context instead of duplicating map/object scanning rules.

### 5. The LLM tool stack already supports ID-safe resolution patterns

Current move tooling already demonstrates the intended LLM integration pattern:

- tool definitions expose only labels, not raw IDs, at [src/ai_rpg_world/application/llm/services/tool_definitions.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/llm/services/tool_definitions.py#L85)
- UI context builder turns visible/actionable objects into runtime targets, including object-destination labels `D1`, `D2`, at [src/ai_rpg_world/application/llm/services/ui_context_builder.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/llm/services/ui_context_builder.py#L342)
- runtime target DTOs already carry `world_object_id`, `spot_id`, and kind metadata at [src/ai_rpg_world/application/llm/contracts/dtos.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/llm/contracts/dtos.py#L120)
- argument resolution converts a destination label into canonical IDs at [src/ai_rpg_world/application/llm/services/tool_argument_resolver.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/llm/services/tool_argument_resolver.py#L148)
- mapper execution follows a simple `args -> app service -> LlmCommandResultDto` flow at [src/ai_rpg_world/application/llm/services/tool_command_mapper.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/llm/services/tool_command_mapper.py#L293)
- wiring injects services into `ToolCommandMapper` centrally at [src/ai_rpg_world/application/llm/wiring/__init__.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/llm/wiring/__init__.py#L331)

Planner implication: Phase 2 can add pursuit tools using the same architecture. The user-requested ID-based primary key (`world_object_id`) should be the service contract, while the LLM-facing layer can still use runtime labels if desired.

## Planning Constraints And Decisions To Preserve

From `02-CONTEXT.md`, the planner should treat these as fixed:

- start target input is `world_object_id`
- valid targets are players and monsters only
- target must be currently visible
- starting pursuit while a static destination/path exists should clear that path and switch to pursuit
- starting pursuit while busy should fail immediately, not queue
- re-starting same target should refresh instead of error
- starting a new target while already pursuing should cancel the old pursuit first
- pursuit cancel takes no target argument
- cancel when not pursuing is a success no-op
- pursuit cancel must also stop the movement currently in progress for that pursuit

The service plan should encode those as tests first-class, not as implementation notes.

## Recommended Service Shape

The cleanest Phase 2 architecture is:

1. Add a dedicated application service in the world/application layer, adjacent to movement.
2. Add separate start/cancel command DTOs.
3. Reuse repositories plus either `WorldQueryService` or `PlayerCurrentStateBuilder`/`VisibleObjectReadModelBuilder` to resolve visible targets.
4. Keep pursuit state mutations inside `PlayerStatusAggregate`; the new service orchestrates validation, switching, path clearing, save, and result DTOs.
5. Keep explicit movement-cancel behavior as a service-level composition concern, not an aggregate concern.

Minimum dependency set looks similar to movement service:

- `PlayerStatusRepository`
- `PlayerProfileRepository` or equivalent for DTO messaging if needed
- `PhysicalMapRepository`
- `SpotRepository` only if result DTOs/messages need spot context
- `GameTimeProvider`
- `UnitOfWork`
- optional helper dependency for visible target lookup

## Recommended Plan Slices

### Slice 02-01: Pursuit start command and validation

Goal: add the explicit start use case and keep it fully deterministic.

Include:

- command dataclass like `StartPursuitCommand(player_id, target_world_object_id)`
- application service method for start
- visible-target resolution from current player state / visible objects
- validation for nonexistent target, invisible target, invalid target kind, same actor, missing map/player placement
- busy-state rejection using the same actor busy truth used by current-state building at [src/ai_rpg_world/application/world/services/player_current_state_builder.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/src/ai_rpg_world/application/world/services/player_current_state_builder.py#L242)
- service logic for:
  - same-target refresh via `update_pursuit(...)` or restart-with-current-snapshot semantics
  - different-target switch via `cancel_pursuit(...)` before `start_pursuit(...)`
  - static path clearing via `clear_path()` before/around pursuit start
- result DTO carrying success/no-op/failure message
- unit tests for command validation and application behavior

Non-goals for this slice:

- no tick continuation
- no automatic last-known updates after start
- no observation registry changes

### Slice 02-02: Explicit pursuit cancel and tool wiring

Goal: add the stop use case and expose both commands to the LLM stack.

Include:

- command dataclass like `CancelPursuitCommand(player_id)`
- application service method for cancel
- no-op success when no active pursuit exists
- active-pursuit cancel via aggregate `cancel_pursuit(...)`
- movement/path clearing alongside pursuit cancel
- tool definition(s), argument resolver support if the tool is label-based, and `ToolCommandMapper` execution path
- wiring updates in LLM wiring factory
- LLM integration tests mirroring existing move-tool coverage

Keep LLM surface narrow:

- start tool should accept exactly one target identifier shape
- cancel tool should accept no target argument

## Validation Rules The Planner Should Make Explicit

The plan should force these validation cases to be named and tested:

- player exists
- player is placed on a map with current coordinate
- actor object exists on the physical map
- actor is not busy
- target `world_object_id` exists on the same current spot
- target is visible under current LOS rules
- target kind is player or monster only
- actor cannot pursue self
- same-target start is treated as refresh/idempotent success
- different-target start while active pursuit cancels old pursuit then starts new pursuit
- cancel with no active pursuit is success no-op

## Likely Test Surfaces

### Domain tests to reuse, not expand much

The aggregate already covers the core domain lifecycle well enough for Phase 2:

- [tests/domain/player/aggregate/test_player_status_aggregate.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/domain/player/aggregate/test_player_status_aggregate.py#L688)

Phase 2 should only add domain tests if service-driven usage exposes a missing aggregate invariant. Otherwise keep the new coverage at application/LLM level.

### Application service tests that should be added

Primary new coverage should mirror `MovementApplicationService` style:

- start success for visible player target
- start success for visible monster target
- start fails for invisible target
- start fails for target not found
- start fails for invalid target type
- start fails while actor busy
- start clears static path/destination
- start same target refreshes without duplicate-error behavior
- start different target cancels previous pursuit and starts new one
- cancel success with active pursuit clears pursuit and path
- cancel no-op success with no active pursuit

Best placement is likely under:

- `tests/application/world/services/`

### Query/read-model regression tests to lean on

Existing visibility/current-state tests are relevant and should be reused as assumptions:

- LOS filtering at [tests/application/world/services/test_player_current_state_builder.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/world/services/test_player_current_state_builder.py#L140)
- busy/path state reflection at [tests/application/world/services/test_player_current_state_builder.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/world/services/test_player_current_state_builder.py#L166)
- `WorldQueryService` busy/path integration at [tests/application/world/services/test_world_query_service.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/world/services/test_world_query_service.py#L850)

These make it unnecessary to invent a second “is actor busy” or “what is visible” rule for pursuit.

### LLM/tool tests that should be added

Follow the same three-layer testing pattern already used for movement:

- resolver tests like [tests/application/llm/test_tool_argument_resolver.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/llm/test_tool_argument_resolver.py#L137)
- mapper tests like [tests/application/llm/test_tool_command_mapper.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/llm/test_tool_command_mapper.py#L72)
- wiring/E2E tests like [tests/application/llm/test_llm_wiring_integration.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/llm/test_llm_wiring_integration.py#L726)

If the tool uses visible-target labels, also add UI-context coverage near:

- [tests/application/llm/test_ui_context_builder.py](/Users/minagawa/Research/llm_trpg_project/ai_rpg_world/tests/application/llm/test_ui_context_builder.py#L324)

## Validation Architecture

Recommended validation layering:

1. Command DTO validation
2. Application-service lookup/visibility/busy validation
3. Aggregate lifecycle mutation
4. Repository save and event persistence through `UnitOfWork`
5. LLM tool adapter tests verifying the command can be reached from tool execution

Specific boundary guidance:

- DTOs validate only scalar shape and positivity.
- Visibility and target-kind checks belong in the application service because they depend on repositories/read models.
- Event emission remains aggregate-owned.
- Tool layer should not re-implement validation rules; it should pass canonical args and surface `error_code`s.

## Risks And Planner Watchouts

- The aggregate cannot switch pursuit targets by itself; the service must handle cancel-then-start sequencing.
- `clear_path()` intentionally does not cancel pursuit, so pursuit cancel must compose both operations explicitly.
- Reusing `actionable_objects` for pursuit targeting may be too narrow, because visibility and interactability are different concepts. Prefer resolving from `visible_objects`, then filtering to player/monster kinds.
- Existing move tools are label-driven, while phase context prefers `world_object_id`. The planner should decide whether:
  - the application API is ID-based and LLM tool remains label-based via runtime resolution, or
  - the tool itself exposes raw `world_object_id`

The first option fits existing LLM architecture better while still preserving an ID-based service contract.

## Prescriptive Recommendation

Plan Phase 2 as exactly two implementation slices:

1. `02-01` builds a dedicated pursuit command service for start/validation/state switching, with service-level tests.
2. `02-02` adds explicit cancel plus LLM tool exposure and integration tests.

That split matches the roadmap, contains scope creep, and aligns with the existing movement/LLM architecture without prematurely implementing continuation or observation delivery.
