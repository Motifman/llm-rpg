---
id: feature-player-current-state-dto-refactoring
title: Player Current State Dto Refactoring
slug: player-current-state-dto-refactoring
status: in_progress
created_at: 2026-03-23
updated_at: 2026-03-23
branch: codex/player-current-state-dto-refactoring-phase1
---

# Current State

- Active phase: **Phase 2**（Builder の責務分割）
- Last completed phase: **Phase 1**（Sub DTO 導入と Compat Facade 化）
- Next recommended action: `flow-exec` で Phase 2 の builder 分割に着手
- Handoff summary: Phase 1 で `PlayerWorldStateDto` / `PlayerRuntimeContextDto` / `PlayerAppSessionStateDto` を導入し、`PlayerCurrentStateDto` から `world_state` / `runtime_context` / `app_session_state` の計算プロパティで返す形にした。既存の top-level フィールドと public 契約は維持しつつ、app session 正規化ロジックは `_normalize_app_session_state` に集約した。

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

## Phase 1

- Started: 2026-03-23
- Completed: 2026-03-23
- Commit: （この phase 完了コミット）
- Tests:
  - `uv run pytest tests/application/world/test_player_current_state_dto.py tests/application/world/services/test_player_current_state_builder.py -q`
  - `uv run pytest tests/application/llm/test_current_state_formatter.py tests/application/llm/test_ui_context_builder.py tests/application/llm/test_availability_resolvers.py -q`
- Findings:
  - `PlayerCurrentStateDto(...)` を直接組み立てた後に top-level 属性を差し替える既存テストがあるため、Phase 1 の sub DTO を保存値として持つと同期コストが高い。計算プロパティとして返す構成だと互換を保ちやすい。
  - app session の整合ロジックは `__post_init__` の中だけでなく、`app_session_state` 計算時にも再利用できるよう `_normalize_app_session_state` に抽出するのが自然だった。
  - `actionable_objects` / `notable_objects` / `available_trades` を runtime context 側へ寄せても、既存 formatter / availability / UI のテストは壊れなかった。
- Plan revision check:
  - **不要**。Phase 1 の goal は「内側に sub DTO を導入しつつ public 契約を保つこと」であり、計算プロパティ方式でも後続 phase の builder 分割・利用側整理へ進める。
- User approval:
  - 不要（future phase の順序・scope に変更なし）
- Plan updates:
  - `PLAN.md` の Phase 1 notes に「計算プロパティ方式が安全」という観測を追記
- Goal check:
  - **達成**。`PlayerCurrentStateDto` の既存初期化形を維持したまま、`world_state` / `runtime_context` / `app_session_state` の境界がコード上に導入された。
- Scope delta:
  - なし（DTO と DTO テストの範囲内）
- Handoff summary:
  - Phase 2 では `PlayerCurrentStateBuilder` が返す 1 個の巨大 DTO 組み立てを、少なくとも `world` / `app_session` の塊に分けて compose する実装へ整理していく。
- Next-phase impact:
  - builder 分割では、Phase 1 の計算プロパティに対応する形で private build helper を切り出すと、既存 return shape を保ったまま進めやすい。
