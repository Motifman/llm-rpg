---
id: feature-trade-label-ref-unification
title: Trade Label Ref Unification
slug: trade-label-ref-unification
status: in_progress
created_at: 2026-03-22
updated_at: 2026-03-22
branch: codex/trade-label-ref-unification
---

# Current State

- Active phase: Phase 2
- Last completed phase: Phase 1
- Next recommended action: Phase 2（内部 resolver / executor の `trade_label` 互換除去と回帰テスト一本化）
- Handoff summary: 公開スキーマは `trade_ref` のみ・仮想ページ時は UI から T* と trade runtime target を外し、incoming の availability を `available_trades` 非依存に変更。resolver はプログラム引数向けに `trade_label` 分岐を残している（Phase 2 で削除予定）。

# Phase Journal

## Phase 1

- Started: 2026-03-22
- Completed: 2026-03-22
- Commit: （このコミット）
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

- Started:
- Completed:
- Commit:
- Tests:
- Findings:
- Plan revision check:
- User approval:
- Plan updates:
- Goal check:
- Scope delta:
- Handoff summary:
- Next-phase impact:
