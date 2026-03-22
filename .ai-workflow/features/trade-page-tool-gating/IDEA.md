id: feature-trade-page-tool-gating
title: Trade 独立モード・取引所 UI と LLM 向けページ表示
slug: trade-page-tool-gating
status: planned
created_at: 2026-03-22
updated_at: 2026-03-22
source: flow-plan
branch: feature/trade-page-tool-gating
related_idea_file: .ai-workflow/ideas/2026-03-22-trade-page-tool-gating.md
---

# Goal

- Trade を SNS から分離し、`trade_enabled` のみで Trade 系ツールが登録されるようにする。
- ゲーム内の取引所アプリとして、LLM が読みやすい一覧・検索・自分の取引ページを提供する。
- 将来のアプリモード追加も見据え、SNS と Trade が同時にアクティブにならない単一スロットのモード表現へ寄せる。

# Success Signals

- `sns_enabled` が false でも、`trade_enabled` が true なら Trade 用ツールがカタログ登録される。
- Trade モード ON のときだけ、取引ミューテーションと取引所 read ツールが一貫して露出する。
- SNS モードと Trade モードが同時に真にならず、別アプリへ入るには明示的 exit が必要であることがテストで保証される。
- 取引所の `market` / `search` / `my_trades` の少なくとも 1 画面以上が、ページスナップショット経由で LLM に読ませられる。

# Non-Goals

- SNS ドメイン自体の機能追加やタイムライン仕様変更。
- 外部認証や永続セッション化。
- 取引所以外のアプリモード一般化を大規模に進めること。
- オークション、推薦、価格履歴分析などの高度機能。

# Problem

1. `register_default_tools` では `trade_enabled and sns_enabled` のときだけ Trade ツールが登録され、プロダクト要件の「Trade は独立アプリ」と矛盾している。
2. Trade ツールはミューテーション中心で、市場一覧・検索・自分の取引を読むためのページ／スナップショット導線が弱い。
3. モード状態は `SnsModeSessionService` に閉じており、SNS/Trade 相互排他を将来まで保てる単一モデルになっていない。

# Constraints

- DDD を崩さず、モード状態や page session はアプリケーション層の責務に留める。
- 既存の `register_default_tools`、availability resolver、executor、wiring、`PlayerCurrentStateDto` の拡張パターンを踏襲する。
- Trade read は既存の query service / read model を優先再利用し、ドメインへ UI ref を持ち込まない。
- UX は「自動切替」ではなく、別アプリへ入る前に明示的 exit を要求する。

# Code Context

- Relevant modules
  - `src/ai_rpg_world/application/llm/services/tool_catalog/__init__.py`
  - `src/ai_rpg_world/application/llm/services/tool_catalog/trade.py`
  - `src/ai_rpg_world/application/llm/services/availability_resolvers.py`
  - `src/ai_rpg_world/application/llm/services/executors/sns_executor.py`
  - `src/ai_rpg_world/application/llm/services/executors/trade_executor.py`
  - `src/ai_rpg_world/application/world/contracts/dtos.py`
  - `src/ai_rpg_world/application/world/services/player_current_state_builder.py`
  - `src/ai_rpg_world/application/trade/services/global_market_query_service.py`
  - `src/ai_rpg_world/application/trade/services/personal_trade_query_service.py`
  - `src/ai_rpg_world/application/trade/services/trade_query_service.py`
- Reusable patterns
  - `SnsModeSessionService` と `SnsPageSessionService`
  - `SnsPageQueryService` の page-local ref と snapshot generation
  - `tests/application/llm/test_available_tools_provider.py`
  - `tests/application/llm/test_sns_mode_wiring_e2e.py`
- Unknowns to research
  - Trade page snapshot を `PlayerCurrentStateDto` に載せるか、別 DTO 経路にするか
  - `my_trades` を売り手／買い手の 1 画面 2 タブにするか
  - 既存 `trade_label` と新しい page-local `trade_ref` の移行方法

# Open Questions

- `my_trades` は `selling` / `incoming` の 2 タブで十分か、詳細ページが初期スコープに必要か。
- Trade page session を SNS と完全分離するか、共通の active app slot から派生する別 session にするか。

# Decision Snapshot

- Proposal:
  - 単一の active app slot をアプリケーション層に導入し、その上で SNS と Trade の ON/OFF 表示を派生させる。
  - Trade は独立モードで起動し、`market` / `search` / `my_trades` のページスナップショットと page-local ref を提供する。
  - 第 1 弾の検索は `item_name + price range + rarity/type` まで含める。
- Options considered:
  - A: Trade を SNS から切り離し、独立モードと取引所ページを導入する
  - B: 登録条件だけ外して、ページや相互排他は後回しにする
  - C: 従来どおり SNS モード配下の Trade のまま維持する
- Selected option:
  - A
- Why this option now:
  - ユーザー要求が「SNS からの切り離し」「LLM 可読な取引所 UI」「アプリ相互排他」まで明確になっており、配線だけの修正では目的を満たさないため。

# Alignment Notes

- Initial interpretation:
  - Trade の登録条件修正と、SNS 仮想ページの対称物として Trade page を導入する計画が必要。
- User-confirmed intent:
  - SNS と Trade は同時に ON にしない。
  - 別アプリに入るには、先に明示的に exit する。
  - 検索は item name だけでなく、price range と rarity/type まで含める。
- Cost or complexity concerns raised during discussion:
  - 既存 `SnsModeSessionService` 前提の resolver / wiring / tests が多く、active app slot への置き換え範囲が広い。
  - SNS virtual pages と同等の Trade page を作るなら session、snapshot、tool gating、prompt 表示まで通しで触る必要がある。
- Assumptions:
  - Trade page は SNS page と同様に非永続セッションで十分である。
  - `GlobalMarketQueryService` と `PersonalTradeQueryService` を組み合わせれば、初期スコープの read は賄える。
- Reopen alignment if:
  - 既存 query だけでは `my_trades` の必要情報が足りず、新規 read model が実質必須だと判明した場合。
  - 明示的 exit UX が実運用上不自然で、自動切替へ戻す必要が出た場合。

# Promotion Criteria

- [x] Trade を SNS から分離する方針
- [x] アプリ相互排他を単一スロットで表現する方針
- [x] `market` / `search` / `my_trades` を初期ページ候補とする方針
- [x] 検索スコープを `item_name + price range + rarity/type` にする方針
