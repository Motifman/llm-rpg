---
id: feature-trade-label-ref-unification
title: Trade Label Ref Unification
slug: trade-label-ref-unification
status: completed
created_at: 2026-03-22
updated_at: 2026-03-22
branch: codex/trade-label-ref-unification
---

# Current State

- Active phase: （なし・PLAN の Phase は完了）
- Last completed phase: Phase 2
- Next recommended action: REVIEW / ship（`flow-review` または main へのマージ判断）
- Handoff summary: 取引ミューテーションの引数解決は `trade_ref` のみ。executor は `trade_page_session.resolve_trade_ref` 経由のみで `trade_id` 直指定を廃止。`TradeToolRuntimeTargetDto` は非仮想ページ時の UI 要約（T*）にのみ残存。

# Phase Journal

## Phase 1

- Started: 2026-03-22
- Completed: 2026-03-22
- Commit: 09a4e71
- Tests: `pytest tests/application/llm/test_tool_definitions.py tests/application/llm/test_available_tools_provider.py tests/application/llm/test_ui_context_builder.py tests/application/llm/test_tool_command_mapper.py`
- Findings:
  - `dataclasses.replace` では `PlayerCurrentStateDto.__post_init__` が再実行されないため、テストでは `is_trade_mode_active` を明示する必要がある。
  - 仮想ページ incoming で `available_trades` が空でも受諾を出す挙動に変えたため、provider に空リストケースのテストを追加した。
- Plan revision check: 不要。Phase 2 で予定どおり resolver の `trade_label` 分岐を除去すればよい。
- User approval: 不要（future phase 変更なし）
- Plan updates: なし
- Goal check: 達成（definition / availability / UI で mutation は `trade_ref` 前提と読める）
- Scope delta: なし
- Handoff summary: `tool_catalog/trade.py` でミューテーション 3 種を `trade_ref` 必須に統一。`availability_resolvers` の Accept/Decline は仮想ページ incoming 時は `available_trades` を見ない。`ui_context_builder` は仮想取引所配線時に T* と `TradeToolRuntimeTargetDto` を載せない。`guild_shop_trade_resolver` は欠落時メッセージを `trade_ref` 案内に変更しつつ `trade_label` 引数は内部互換として維持。executor の invalid 文言を `trade_ref` のみに。
- Next-phase impact: Phase 2 で `_resolve_trade_label` の `trade_label` 分岐削除、メソッド名整理、mapper テストの `trade_label` 言及除去が中心。

## Phase 2

- Started: 2026-03-22
- Completed: 2026-03-22
- Commit: e9cf84e
- Tests: `pytest tests/application/llm/`
- Findings:
  - `ToolCommandMapper` は引数 resolver を通さないため、mapper 単体テストの欠落系は executor の `invalid_arg_result("trade_ref")` に依存する（メッセージに `trade_ref` を含む）。
  - `DefaultToolArgumentResolver` 経由のテストでは `trade_ref` の正規化（strip）を明示的に検証した。
- Plan revision check: 不要（2 phase で PLAN どおり完了）
- User approval: 不要
- Plan updates: なし
- Goal check: 達成（mutation 解決に `trade_label` コードパスなし、テストの `trade_label` 許容 assertion を除去）
- Scope delta: なし
- Handoff summary: `GuildShopTradeArgumentResolver._resolve_trade_ref_mutation` に整理し `trade_label` / `TradeToolRuntimeTargetDto` 依存を削除。`TradeToolExecutor._resolve_trade_id` から `trade_id` 直読みを削除。`test_tool_argument_resolver` に trade accept の成功・失敗を追加し、`_make_shop_guild_trade_context` から未使用の T1 trade target を削除。`test_tool_command_mapper` の欠落系は `trade_ref` のみ assert。
- Next-phase impact: なし（本 feature の PLAN は Phase 2 まで）
