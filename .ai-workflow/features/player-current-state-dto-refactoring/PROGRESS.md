---
id: feature-player-current-state-dto-refactoring
title: Player Current State Dto Refactoring
slug: player-current-state-dto-refactoring
status: in_progress
created_at: 2026-03-23
updated_at: 2026-03-23
branch: codex/player-current-state-dto-refactoring-phase0
---

# Current State

- Active phase: **Phase 1**（Sub DTO 導入と Compat Facade 化）
- Last completed phase: **Phase 0**（属性棚卸しと責務境界の固定）
- Next recommended action: `flow-exec` で Phase 1 の DTO 設計と compat 導入に着手
- Handoff summary: Phase 0 で `PlayerCurrentStateDto` の全属性を `world` / `runtime` / `app_session` に分類し、compat shortcut 候補、heavy payload 方針、formatter / availability / UI の consumer map を `PHASE0_ATTRIBUTE_INVENTORY.md` に固定。`available_trades`、`actionable_objects`、`notable_objects` は raw world facts ではなく tool-facing runtime context として扱う方針に寄せた。

# Phase Journal

## Phase 0

- Started: 2026-03-23
- Completed: 2026-03-23
- Commit: （この phase 完了コミット）
- Tests:
  - コード変更なしのため回帰確認として `pytest tests/application/world/services/test_player_current_state_builder.py -q`
  - `pytest tests/application/llm/test_current_state_formatter.py tests/application/llm/test_ui_context_builder.py tests/application/llm/test_availability_resolvers.py -q`
- Findings:
  - `ToolAvailabilityContext = PlayerCurrentStateDto` の現契約が `src/ai_rpg_world/application/llm/contracts/dtos.py` に明記されており、Phase 1 では resolver 入力型を変えず compat facade を優先するのが妥当。
  - `availability_resolvers.py` と `ui_context_builder.py` は `runtime` 依存が最も強い一方、SNS / Trade mode/page state は `app_session` として独立させやすい。
  - `actionable_objects` / `notable_objects` は `visible_objects` 由来だが、consumer から見ると tool-facing に加工済みの sibling list であり、`runtime` owner に置く方が後続 phase の説明が自然。
- Plan revision check:
  - **不要**。3 分割 (`world` / `runtime` / `app_session`) で主要属性を無理なく分類でき、後続 phase の順序も維持可能。
- User approval:
  - 不要（future phase の並び替えや scope 変更なし）
- Plan updates:
  - `PLAN.md` に Phase 0 deliverables を明記
  - `PHASE0_ATTRIBUTE_INVENTORY.md` を追加
- Goal check:
  - **達成**。属性棚卸し表、consumer map、shortcut policy、heavy payload policy が揃い、Phase 1 の前提が固定された。
- Scope delta:
  - なし（artifact 固定のみ）
- Handoff summary:
  - Phase 1 では `PlayerWorldStateDto` / `PlayerRuntimeContextDto` / `PlayerAppSessionStateDto` の導入時に、Phase 0 の shortcut 候補を優先して property 委譲へ載せる。
- Next-phase impact:
  - Phase 1 では `player_id` / `player_name` を facade root に残すか `world` 側へ完全移譲するかの最終判断だけ追加で必要。
