---
id: feature-trade-page-tool-gating
title: Trade Page Tool Gating
slug: trade-page-tool-gating
status: shipped
created_at: 2026-03-22
updated_at: 2026-03-22
branch: feature/trade-page-tool-gating
---

# Outcome

Trade を SNS 配線から切り離し、`ActiveGameAppSessionService` による SNS / Trade の相互排他と、取引所の `market` / `search` / `my_trades` を前提としたページスナップショット＋`trade_ref` 契約のもとで LLM ツールを gated 露出する、という PLAN の成功条件を満たした。レビューで挙がった Major（`trade_cancel` の selling 文脈、`trade_executor` の未知タブ）も解消済みで、出荷ゲートは満たしている。

# Delivered

- **モードとカタログ**: `trade_enabled` のみで Trade ツール登録（`sns_enabled` 非依存）。単一 active app slot で SNS と Trade が同時アクティブにならず、別アプリへは明示 exit 前提。
- **Trade ページ**: `TradePageSessionService` / `TradePageQueryService`、スナップショット DTO と `trade_ref`、既存 `GlobalMarketQueryService` / `PersonalTradeQueryService` / `TradeQueryService` の再利用。
- **ツール層**: provider / availability resolver / `TradeToolExecutor` / wiring / prompt への統合。ページ種別に応じたミューテーション露出と、`trade_virtual_page_kind` 未配線時の従来互換。
- **後追い修正（レビュー対応）**: `TradeCancelTradePageAvailabilityResolver` で `my_trades` / `selling` 仮想ページ時は `available_trades` に依存しない。`trade_executor` で `incoming|selling` 以外のタブは `invalid_arg_value_result`。
- **テスト**: `test_available_tools_provider` / `test_tool_command_mapper` / `test_tool_definitions` / `test_sns_mode_wiring_e2e` ほか、phase 記録どおり各層で回帰を固定。

# Remaining Work

- **PLAN スコープ外の任意フォロー**: Phase 6 で言及のとおり、`trade_label` 互換の縮退は未実施（従来環境向けに残す方針）。追加 phase は [REVIEW.md](REVIEW.md) 上「なし」。

# Evidence

- **テスト（本セッション実行）**:
  ```bash
  cd /path/to/ai_rpg_world && source venv/bin/activate && \
  python -m pytest tests/application/llm/test_available_tools_provider.py \
    tests/application/llm/test_tool_command_mapper.py \
    tests/application/llm/test_tool_definitions.py \
    tests/application/llm/test_sns_mode_wiring_e2e.py -q
  ```
  **結果**: `190 passed`（1 warning、pytest 実行上の既知の表示差分の可能性あり）。
- **レビュー**: [REVIEW.md](REVIEW.md) — `Ship ready: yes`、Blocking findings なし（Major/Minor は解消済みとして記録）。
- **広い回帰**: [PROGRESS.md](PROGRESS.md) Phase 6 時点で `pytest tests/` 全件通過（6007 passed）と記録あり。マージ前にローカルで `pytest tests/` の再実行を推奨。

# Merge / PR

- **推奨**: 機能ブランチ `feature/trade-page-tool-gating` を `main` へ **PR 経由でマージ**（差分レビュー・CI 可視化のため）。チーム運用で main 直マージのみの場合は、上記テストをパスしたコミット上で `main` にマージすればよい。
- **注意**: ワークツリー上のブランチ名は `feature/trade-page-tool-gating`。古いメタデータで `codex/trade-page-tool-gating` と書かれた箇所があれば、リモート/ローカルの実ブランチ名に合わせること。
