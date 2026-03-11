# Phase 01 Verification

## Verdict

- status: passed
- phase: `01-pursuit-domain-vocabulary`
- goal: `追跡を静的移動と分離した明示的なドメイン概念として定義する`
- verified_on: `2026-03-11`

## Scope Checked

- Plan files:
  - `01-01-PLAN.md`
  - `01-02-PLAN.md`
  - `01-03-PLAN.md`
- Summary files:
  - `01-01-SUMMARY.md`
  - `01-02-SUMMARY.md`
  - `01-03-SUMMARY.md`
- Supporting docs:
  - `.planning/ROADMAP.md`
  - `.planning/REQUIREMENTS.md`
  - `01-CONTEXT.md`
  - `01-RESEARCH.md`
- Code and tests under `src/` and `tests/`

## Requirement ID Cross-Reference

`REQUIREMENTS.md` maps Phase 1 to `OUTC-01`, `OUTC-02`, `RUNT-02`. `ROADMAP.md` declares the same phase requirement set. All requirement IDs found in Phase 01 PLAN frontmatter are accounted for in `REQUIREMENTS.md`.

| Requirement ID | In PLAN frontmatter | In REQUIREMENTS.md Phase mapping | Evidence | Result |
|---|---|---|---|---|
| `OUTC-01` | `01-01-PLAN.md` | Yes | `PursuitFailureReason` defines structured failure outcomes and excludes `cancelled` | Passed |
| `OUTC-02` | `01-02-PLAN.md`, `01-03-PLAN.md` | Yes | explicit pursuit lifecycle events exist and player aggregate emits them | Passed |
| `RUNT-02` | `01-01-PLAN.md`, `01-03-PLAN.md` | Yes | pursuit state exists independently from static movement destination/path state | Passed |

No extra requirement IDs were found in Phase 01 plans, and none of the required IDs are missing from the implementation trace.

## Must-Have Audit

### Plan 01-01

| Must-have | Evidence | Result |
|---|---|---|
| Dedicated pursuit domain types instead of static destination/path reuse | `src/ai_rpg_world/domain/pursuit/value_object/pursuit_state.py`, `pursuit_last_known_state.py`, `pursuit_target_snapshot.py` define separate pursuit vocabulary under `domain/pursuit` | Passed |
| Machine-readable failure reasons for Phase 1 outcomes | `src/ai_rpg_world/domain/pursuit/enum/pursuit_failure_reason.py` defines `target_missing`, `path_unreachable`, `vision_lost_at_last_known` | Passed |
| Explicit last-known target state | `PursuitLastKnownState` is a dedicated value object and `PursuitState` requires snapshot or last-known state | Passed |
| Regression coverage for separation from static movement | `tests/domain/pursuit/value_object/test_pursuit_state.py` asserts pursuit state does not expose static movement fields | Passed |

### Plan 01-02

| Must-have | Evidence | Result |
|---|---|---|
| Explicit started/updated/failed/cancelled events | `src/ai_rpg_world/domain/pursuit/event/pursuit_events.py` defines all four lifecycle events | Passed |
| Failed events carry structured reason plus actor/target/last-known context | `PursuitFailedEvent` includes `actor_id`, `target_id`, `failure_reason`, `last_known`, optional `target_snapshot` | Passed |
| Cancelled remains separate from failure | `PursuitCancelledEvent` is a distinct event and `PursuitFailureReason` contains no `cancelled` member | Passed |
| Event payload regression coverage | `tests/domain/pursuit/event/test_pursuit_events.py` covers payload shape and failed/cancelled distinction | Passed |

### Plan 01-03

| Must-have | Evidence | Result |
|---|---|---|
| Player pursuit state stored independently from static destination/path state | `PlayerStatusAggregate` has dedicated `_pursuit_state`; `clear_path()` only clears movement fields | Passed |
| Player aggregate can start/update/fail/cancel pursuit and emit lifecycle events | `start_pursuit`, `update_pursuit`, `fail_pursuit`, `cancel_pursuit` emit `Pursuit*Event` through `add_event(...)` | Passed |
| Monster-side integration strategy is explicit without implementing Phase 5 behavior | `docs/pursuit/phase1_integration_strategy.md` names `BehaviorStateEnum`, `TargetSpottedEvent`, `TargetLostEvent` and defers behavior mapping to Phase 5 | Passed |
| Static movement clearing/advancing does not implicitly erase pursuit state | aggregate and movement-service regressions keep pursuit state after movement-path completion/clearing | Passed |

## Goal Achievement Against Roadmap Success Criteria

| Roadmap success criterion | Evidence | Result |
|---|---|---|
| 1. 追跡状態が通常の移動先/path 情報とは独立して保持される | `PlayerStatusAggregate` stores `_pursuit_state` separately; `tests/domain/player/aggregate/test_player_status_aggregate.py` and `tests/application/world/services/test_movement_service.py` verify path clearing does not clear pursuit | Passed |
| 2. 追跡終了理由が構造化された enum/値として表現される | `PursuitFailureReason` enum implements required structured reasons | Passed |
| 3. 追跡開始・更新・失敗・中断を表すドメインイベントが存在する | `PursuitStartedEvent`, `PursuitUpdatedEvent`, `PursuitFailedEvent`, `PursuitCancelledEvent` exist and are exercised by tests | Passed |

## Implementation Evidence

- `src/ai_rpg_world/domain/pursuit/value_object/pursuit_state.py`
  - neutral pursuit state with `actor_id`, `target_id`, `target_snapshot`, `last_known`, `failure_reason`
- `src/ai_rpg_world/domain/pursuit/value_object/pursuit_last_known_state.py`
  - explicit last-known target state for continuation semantics
- `src/ai_rpg_world/domain/pursuit/enum/pursuit_failure_reason.py`
  - structured outcome vocabulary required by `OUTC-01`
- `src/ai_rpg_world/domain/pursuit/event/pursuit_events.py`
  - explicit lifecycle event contract required by `OUTC-02`
- `src/ai_rpg_world/domain/player/aggregate/player_status_aggregate.py`
  - aggregate-owned pursuit state and lifecycle methods separate from movement fields
- `docs/pursuit/phase1_integration_strategy.md`
  - documented monster alignment touchpoints without premature runtime implementation

## Test Evidence

Executed:

```bash
.venv/bin/python -m pytest \
  tests/domain/pursuit/value_object \
  tests/domain/pursuit/enum \
  tests/domain/pursuit/event \
  tests/domain/player/aggregate/test_player_status_aggregate.py \
  tests/domain/monster/aggregate/test_monster_aggregate.py \
  tests/application/world/services/test_movement_service.py -q
```

Result:

- `319 passed in 2.45s`

## Findings

- No gaps found against the declared Phase 01 must_haves.
- No missing requirement IDs in PLAN frontmatter cross-reference.
- No evidence that pursuit was collapsed into static movement state in Phase 01.

## Conclusion

Phase 01 goal achievement is verified. The codebase now contains a neutral pursuit vocabulary, structured pursuit outcome reasons, explicit lifecycle events, aggregate-owned player pursuit state separated from static movement, and a documented monster alignment path for later phases.
