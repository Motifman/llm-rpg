---
id: feature-trade-page-tool-gating
title: Trade Page Tool Gating
slug: trade-page-tool-gating
status: review
created_at: 2026-03-22
updated_at: 2026-03-22
branch: codex/trade-page-tool-gating
---

# Review Prompt

Review all files for this feature. Verify DDD boundaries, implementation quality, exception handling, and test thoroughness. Check that there are no placeholder implementations or deferred shortcuts. Compare test strictness with existing strong suites such as `src/domain/trade` and `src/domain/sns`.

# Findings

## Critical

- None

## Major

- ~~`trade_cancel` が `my_trades / selling` で実運用上ほぼ出ません。~~ **解消済み（2026-03-22）**: `TradeCancelTradePageAvailabilityResolver` を修正し、仮想ページが `my_trades` / `selling` のときは `available_trades` に依存しない。未配線（`trade_virtual_page_kind is None`）は従来どおり `available_trades` 必須。`tests/application/llm/test_available_tools_provider.py` の selling ケースは `available_trades=[]` で `trade_cancel` を検証。

## Minor

- ~~未知の `my_trades_tab` / `tab` が selling に丸められる~~ **解消済み（2026-03-22）**: `trade_executor` で `incoming|selling` 以外は `invalid_arg_value_result`（`INVALID_TARGET_LABEL`）。`tests/application/llm/test_tool_command_mapper.py` に失敗系を追加。

# Follow-up

- Additional phases needed: なし
- Files to revisit: なし（上記修正でクローズ）

# Release Gate

- Ship ready: yes
- Blocking findings: なし
