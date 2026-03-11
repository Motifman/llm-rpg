# Phase 02 Verification

## Verdict

- status: passed
- phase: `02-player-pursuit-commands`
- goal: `プレイヤーが追跡開始/中断を明示的に行えるようにする`
- verified_on: `2026-03-11`

## Scope Checked

- Plan files:
  - `02-01-PLAN.md`
  - `02-02-PLAN.md`
- Summary files:
  - `02-01-SUMMARY.md`
  - `02-02-SUMMARY.md`
- Supporting docs:
  - `.planning/ROADMAP.md`
  - `.planning/REQUIREMENTS.md`
  - `02-CONTEXT.md`
  - `02-RESEARCH.md`
  - `02-VALIDATION.md`
- Code and tests under `src/` and `tests/`

## Requirement ID Cross-Reference

Phase 2 maps to `PURS-01` and `PURS-05` in both `ROADMAP.md` and `REQUIREMENTS.md`. Both IDs are present in the Phase 2 plan frontmatter and reflected in implementation.

| Requirement ID | In PLAN frontmatter | Evidence | Result |
|---|---|---|---|
| `PURS-01` | `02-01-PLAN.md`, `02-02-PLAN.md` | `PursuitCommandService.start_pursuit(...)`, pursuit tool definitions/resolver/mapper/wiring | Passed |
| `PURS-05` | `02-02-PLAN.md` | `PursuitCommandService.cancel_pursuit(...)`, no-op cancel semantics, pursuit cancel tool | Passed |

## Must-Have Audit

### Plan 02-01

| Must-have | Evidence | Result |
|---|---|---|
| Explicit application entrypoint for player pursuit start | `src/ai_rpg_world/application/world/services/pursuit_command_service.py` | Passed |
| Visible player/monster targets only; missing/invisible/invalid/self/busy rejected | `PursuitTargetNotFoundException`, `PursuitTargetNotVisibleException`, `PursuitInvalidTargetKindException`, `PursuitSelfTargetException`, `PursuitActorBusyException`, and service tests | Passed |
| Start clears static destination/path without introducing continuation logic | `player_status.clear_path()` inside start flow; no tick/observation changes in service | Passed |
| Same-target refresh and different-target switch are service-owned semantics | `update_pursuit(...)` and `cancel_pursuit()+start_pursuit(...)` branches plus tests | Passed |

### Plan 02-02

| Must-have | Evidence | Result |
|---|---|---|
| Explicit pursuit cancel distinct from movement cancel | `CancelPursuitCommand` and `PursuitCommandService.cancel_pursuit(...)` | Passed |
| Active cancel clears pursuit and path; no active pursuit returns success no-op | service implementation and `test_cancel_pursuit_*` coverage | Passed |
| LLM/tool layer exposes only narrow Phase 2 pursuit controls | `TOOL_NAME_PURSUIT_START`, `TOOL_NAME_PURSUIT_CANCEL`, tool definitions and wiring | Passed |
| Mapper/resolver delegate to application services instead of re-implementing core validation | resolver only resolves labels; mapper calls `PursuitCommandService`; service owns visibility/kind checks | Passed |

## Goal Achievement Against Roadmap Success Criteria

| Roadmap success criterion | Evidence | Result |
|---|---|---|
| 1. LLM 制御プレイヤーがプレイヤーまたはモンスターを追跡対象に指定できる | start service accepts visible player/monster targets; tool layer resolves `P1`/`M1` labels to `world_object_id` | Passed |
| 2. 明示コマンドまたは明示状態変更で追跡を止められる | `CancelPursuitCommand`, service cancel flow, and pursuit cancel tool path exist | Passed |
| 3. 追跡開始/中断がドメイン状態とイベントに正しく反映される | service delegates to aggregate `start_pursuit`, `update_pursuit`, `cancel_pursuit`; aggregate tests and service tests confirm state/event behavior | Passed |

## Implementation Evidence

- `src/ai_rpg_world/application/world/services/pursuit_command_service.py`
  - start/cancel orchestration and visibility-aware validation
- `src/ai_rpg_world/application/world/exceptions/command/pursuit_command_exception.py`
  - stable pursuit command error codes
- `src/ai_rpg_world/application/world/contracts/commands.py`
  - typed start/cancel pursuit command DTOs
- `src/ai_rpg_world/application/llm/services/tool_definitions.py`
  - pursuit start/cancel tool schemas
- `src/ai_rpg_world/application/llm/services/tool_argument_resolver.py`
  - pursuit target label to canonical ID resolution
- `src/ai_rpg_world/application/llm/services/tool_command_mapper.py`
  - LLM execution handoff to `PursuitCommandService`
- `src/ai_rpg_world/application/llm/wiring/__init__.py`
  - optional pursuit service wiring into the LLM runtime

## Test Evidence

Executed:

```bash
.venv/bin/python -m pytest \
  tests/application/world/contracts/test_commands.py \
  tests/application/world/services/test_pursuit_command_service.py \
  tests/application/llm/test_tool_definitions.py \
  tests/application/llm/test_tool_argument_resolver.py \
  tests/application/llm/test_tool_command_mapper.py \
  tests/application/llm/test_llm_wiring_integration.py \
  tests/domain/player/aggregate/test_player_status_aggregate.py -q
```

Result:

- `238 passed, 1 warning in 3.34s`

## Findings

- No gap was found against the declared Phase 2 must-haves.
- Phase 2 stayed within scope: no continuation-loop logic and no observation/LLM re-trigger delivery work was introduced.

## Conclusion

Phase 02 goal achievement is verified. The codebase now exposes explicit player pursuit start/cancel commands, validates visible pursuit targets, cleanly separates pursuit cancel from movement cancel, and provides the minimum LLM tool reachability needed for Phase 2.
