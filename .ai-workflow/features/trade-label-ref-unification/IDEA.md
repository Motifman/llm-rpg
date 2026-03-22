---
id: feature-trade-label-ref-unification
title: Trade の `trade_label` / `trade_ref` 契約一本化
slug: trade-label-ref-unification
status: planned
created_at: 2026-03-22
updated_at: 2026-03-22
source: flow-plan
branch: codex/trade-label-ref-unification
related_idea_file: .ai-workflow/ideas/2026-03-22-trade-label-ref-unification.md
---

# Goal

- 取引ミューテーションの対象指定を `trade_ref` に一本化し、LLM が迷わず同じ形式で accept / cancel / decline を呼べるようにする。
- `trade_label` 互換経路に起因する二重管理を減らし、resolver・executor・テスト・説明文を単純化する。
- SNS 仮想ページの `r_*` 系と同じ発想で、取引所の page-local ref 契約を一貫したものにする。

# Success Signals

- `trade_accept` / `trade_cancel` / `trade_decline` の推奨入力が `trade_ref` に揃い、ツール定義と失敗文言もそれを前提にしている。
- 仮想ページ利用時に `trade_label` を経由しなくても、`trade_ref` だけで対象解決と操作が成立する。
- `trade_label` 互換パスを残す理由がなくなり、関連テストが `trade_ref` 契約を回帰防止として固定している。

# Non-Goals

- Guild / Shop / World 全体の label/ref 設計を横断的に変えること。
- `inventory_item_label` や `target_player_label` など、取引出品時に使う別種ラベルを改名すること。
- `r_trade_*` 自体の命名規則変更や世代情報の埋め込みをこの段階で行うこと。

# Problem

1. 取引ミューテーションはツール定義上 `trade_label` と `trade_ref` の二重経路を持ち、外部契約が冗長になっている。
2. `guild_shop_trade_resolver` と `trade_executor` の両方に label / ref 分岐が残っており、保守コストと回帰余地が増えている。
3. `available_trades` の `T*` ラベル系 current state と仮想ページの `trade_ref` が並立し、LLM にとって「どれを使うべきか」が曖昧になりうる。

# Constraints

- DDD を守り、`trade_ref` や表示都合の識別子はドメインへ持ち込まず、アプリケーション層で解決する。
- 既存の `TradePageSessionService.issue_trade_ref` / `resolve_trade_ref` と `TradePageQueryService` の snapshot generation パターンを正とする。
- 従来の label-only 環境との後方互換は不要という合意を前提にする。

# Code Context

- Relevant modules
  - `src/ai_rpg_world/application/llm/services/tool_catalog/trade.py`
  - `src/ai_rpg_world/application/llm/services/executors/trade_executor.py`
  - `src/ai_rpg_world/application/llm/services/_argument_resolvers/guild_shop_trade_resolver.py`
  - `src/ai_rpg_world/application/llm/services/availability_resolvers.py`
  - `src/ai_rpg_world/application/llm/services/ui_context_builder.py`
  - `src/ai_rpg_world/application/world/services/player_current_state_builder.py`
- Reusable patterns
  - SNS 仮想ページの `r_post_*` / `r_reply_*` を前提にした `*_ref` 説明文
  - `trade-page-tool-gating` feature で導入済みの `TradePageSessionService` / `TradePageQueryService`
  - `tests/application/llm/test_tool_definitions.py`
  - `tests/application/llm/test_available_tools_provider.py`
  - `tests/application/llm/test_tool_command_mapper.py`
- Unknowns to research
  - `available_trades` と `TradeToolRuntimeTargetDto` の `T*` ラベルを今回どこまで掃除するか
  - prompt/current state への説明文統一をどこまで同 feature に含めるか

# Open Questions

- 仮想ページの行表示に `trade_ref` 以外の短縮ラベルを新設する価値があるか
- `available_trades` を mutation 導線から完全に外すか、情報表示だけ残すか

# Decision Snapshot

- Proposal:
  - `trade_accept` / `trade_cancel` / `trade_decline` は `trade_ref` のみを受け付ける契約へ寄せる。
  - `trade_label` 互換経路は executor / argument resolver / ツール定義から段階的に除去する。
  - `trade_page_refresh` などの説明文も SNS 仮想ページと揃え、`r_trade_*` の page-local 性を明確化する。
- Options considered:
  - A: 現状維持で説明だけ強化する
  - B: 仮想ページ利用時だけ strict にし、label 経路を内部互換として残す
  - C: 後方互換を捨てて `trade_ref` 一本へ即時移行する
- Selected option:
  - C
- Why this option now:
  - `trade-page-tool-gating` の完了で `trade_ref` 基盤は既に整っており、残る複雑さの主因が `trade_label` 互換パスだから。

# Alignment Notes

- Initial interpretation:
  - まず public contract と内部解決経路を `trade_ref` 側へ揃え、その後に文言とテストを固定する follow-up feature が必要。
- User-confirmed intent:
  - LLM にとって識別しやすいことを優先する。
  - 識別子は簡潔で、既存の他ツールと一貫していることを重視する。
  - tool description / refresh 文言の統一も今回の feature に含める。
- Cost or complexity concerns raised during discussion:
  - `available_trades` と `T*` runtime target が current state 側に残っており、契約変更だけでは「見えるが使えない」状態を生みうる。
  - `trade_label` を消すと command mapper / wiring / availability テストの期待値更新が広く必要になる。
- Assumptions:
  - `r_trade_*` は SNS の `r_*` 系と同じく、十分に簡潔かつ一貫した page-local 識別子として扱える。
  - mutation 対象は仮想ページの現在スナップショットからコピーする運用で十分である。
- Reopen alignment if:
  - `available_trades` ベースの非ページ導線を正式仕様として残す必要が出た場合
  - `r_trade_*` が LLM にとって識別しづらい実例が出て、別表示識別子の併記が必要になった場合

# Promotion Criteria

- [x] 後方互換を捨てて `trade_ref` 一本化へ寄せる方針
- [x] 文言統一を同 feature に含める方針
- [x] phase は 2 本に圧縮してよいという方針
