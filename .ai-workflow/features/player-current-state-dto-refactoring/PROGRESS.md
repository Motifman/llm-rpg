---
id: feature-player-current-state-dto-refactoring
title: Player Current State Dto Refactoring
slug: player-current-state-dto-refactoring
status: in_progress
created_at: 2026-03-23
updated_at: 2026-03-23
branch: codex/player-current-state-dto-refactoring-phase3
---

# Current State

- Active phase: **Phase 4**（実装修正とテスト移行）
- Last completed phase: **Phase 3**（Formatter / Availability / UI の依存整理）
- Next recommended action: `flow-exec` で `current_state_formatter.py` → `ui_context_builder.py` → `availability_resolvers.py` の順に内部参照を置換する
- Handoff summary: Phase 3 で consumer ごとの着地点を [`PHASE3_CONSUMER_DEPENDENCY_PLAN.md`](/Users/minagawa/.codex/worktrees/4a2d/ai_rpg_world/.ai-workflow/features/player-current-state-dto-refactoring/PHASE3_CONSUMER_DEPENDENCY_PLAN.md) に固定した。結論は、public 入力型は維持しつつ、内部だけ `world` / `runtime` / `app` alias へ寄せる方針である。

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

## Phase 2

- Started: 2026-03-23
- Completed: 2026-03-23
- Commit: （この phase 完了コミット）
- Tests:
  - `uv run pytest tests/application/world/test_player_current_state_dto.py tests/application/world/services/test_player_current_state_builder.py tests/application/world/services/test_world_query_service.py -q`
  - `uv run pytest tests/application/llm/test_current_state_formatter.py tests/application/llm/test_ui_context_builder.py tests/application/llm/test_availability_resolvers.py -q`
- Findings:
  - `PlayerCurrentStateDto.from_components` を用意すると、builder 側で facade への field mapping を 1 箇所に寄せられ、Phase 2 の compose 構造が見えやすくなる。
  - `PlayerCurrentStateBuilder` では `runtime` の詳細組み立てをなお `PlayerRuntimeContextBuilder` に委譲できるため、Phase 2 で無理に runtime builder 自体を分割する必要はなかった。
  - app session helper 抽出直後に SNS snapshot query が二重実行されたが、旧ロジック除去で解消した。これは compose 移行時に旧直書きロジックが残りやすい、という注意点になった。
- Plan revision check:
  - **不要**。builder の責務は `world` / `runtime` / `app_session` の compose として十分説明可能になり、後続の consumer 棚卸し順序も維持できる。
- User approval:
  - 不要（future phase の並び替えや scope 変更なし）
- Plan updates:
  - `PLAN.md` の Phase 2 notes に `from_components` ベース compose を追記
- Goal check:
  - **達成**。`PlayerCurrentStateBuilder` の返却処理は、巨大な 1 回の dataclass 初期化から、複数コンテキストを assemble する構造へ整理された。
- Scope delta:
  - なし（builder と DTO assembly の範囲内）
- Handoff summary:
  - Phase 3 では formatter / availability / UI の各 consumer が、どこまで sub DTO 直参照へ寄せるべきかを棚卸しし、compat property を残す対象を決める。
- Next-phase impact:
  - `from_components` ができたので、Phase 4 以降に builder 以外から facade を再構成する必要が出ても共通の assemble 入口を使える。

## Phase 3

- Started: 2026-03-23
- Completed: 2026-03-23
- Commit: （この phase 完了コミット）
- Tests:
  - コード変更なし。artifact 固定のみのため追加テストは未実施
- Findings:
  - `current_state_formatter.py` は world 依存が最も強く、最初の移行対象にしやすい。
  - `ui_context_builder.py` は runtime 依存が最も強いが、関数冒頭で alias を束縛するだけでも依存境界がかなり明確になる。
  - `availability_resolvers.py` は件数が多いため、入力型変更ではなく resolver family ごとの内部 alias 化が最も安全。
- Plan revision check:
  - **不要**。入力型を維持したまま内部参照だけを新境界へ寄せる方針で、既存 future phase の順序と成功条件を維持できる。
- User approval:
  - 不要（future phase の追加・並び替えなし）
- Plan updates:
  - `PHASE3_CONSUMER_DEPENDENCY_PLAN.md` を追加
  - `PLAN.md` の Phase 3 checkpoint / notes を更新
- Goal check:
  - **達成**。formatter / availability / UI の各 consumer について、Phase 4 で何をどの順に変更するかが明文化された。
- Scope delta:
  - なし（dependency plan の固定のみ）
- Handoff summary:
  - Phase 4 は formatter → UI builder → availability resolver の順で内部参照を `world` / `runtime` / `app` alias に寄せる。
- Next-phase impact:
  - Phase 4 では public API や fixture 形を変えず、内部参照差し替えとテスト更新に集中できる。
