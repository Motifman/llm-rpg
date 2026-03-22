---
id: feature-trade-page-tool-gating
title: Trade Page Tool Gating
slug: trade-page-tool-gating
status: in_progress
created_at: 2026-03-22
updated_at: 2026-03-22
branch: feature/trade-page-tool-gating
---

# Current State

- Active phase: Phase 3（Trade Page Session と Snapshot DTO）
- Last completed phase: Phase 2（Trade モード導線と露出分離）
- Next recommended action: `TradePageSessionService` 相当・page kind / ref・DTO 配線
- Handoff summary: `register_default_tools` は `trade_enabled` のみで Trade カタログを登録。`trade_enter` / `trade_exit` と `TradeModeRequiredAvailabilityResolver` で 4 ミューテーションを取引所モードにゲート。`SnsEnterToolAvailabilityResolver` は SNS/取引のいずれも未起動時のみ `sns_enter`。`SnsModeSessionService` に `enter_trade_mode` / `exit_trade_mode` / `is_trade_mode_active`。executor は `TradeToolExecutor` が `sns_mode_session` を共有し、`ActiveGameAppConflictError` を enter 系で捕捉。

# Phase Journal

## Phase 1

- Started: 2026-03-22
- Completed: 2026-03-22
- Commit: （本コミット）
- Tests: `tests/application/social/services/test_active_game_app_session_service.py`、既存 `test_world_query_service` 拡張、`pytest tests/` 全件通過
- Findings:
  - `SnsModeSessionService` はオプションで `ActiveGameAppSessionService` を注入可能。未指定時は内部で新規作成（従来の `SnsModeSessionService()` 単体呼び出しのテスト互換）。
  - `PlayerCurrentStateDto` は後方互換のため `is_sns_mode_active` のみを渡す既存テストを `__post_init__` で `active_game_app` に昇格。
- Plan revision check: 不要。Phase 1 の checkpoint（none→sns→none→trade と拒否）と整合。
- User approval: （plan 変更なし）
- Plan updates: なし
- Goal check: active app の真実の置き場所は `ActiveGameAppSessionService` 1 箇所。SNS/Trade 同時 ON は不可。
- Scope delta: なし
- Handoff summary: 上記 Current State のとおり。
- Next-phase impact: Phase 2 で `trade_enter` が `enter_trade` を呼ぶよう executor を接続すれば、`ActiveGameAppConflictError` が SNS 未退出のまま取引所に入る経路をブロック可能。

## Phase 2

- Started: 2026-03-22
- Completed: 2026-03-22
- Commit: feature ブランチの最新コミット（Phase 2 完了時点）
- Tests: `tests/application/llm/test_tool_definitions.py`、`test_available_tools_provider.py`、`test_sns_mode_wiring_e2e.py`、`pytest tests/application/llm/` 全件通過
- Findings:
  - `PlayerCurrentStateDto` の `active_game_app` をテストで差し替えるときは `dataclasses.replace` を使うと `__post_init__` により `is_trade_mode_active` が整合する（構築後の属性代入だけでは resolver が誤る）。
  - `TradeToolExecutor` は入退場ハンドラを常に登録し、`sns_mode_session` が無い場合は `_execute_trade_enter` が unknown を返す。
- Plan revision check: 不要。Phase 2 の success criteria（3 状態の露出・trade_enabled のみ登録）と整合。
- User approval: （plan 変更なし）
- Plan updates: なし
- Goal check: Trade は `sns_enabled` に依存せず登録され、取引所モード時のみ 4 ミューテーション、SNS モード時は Trade ファミリー非表示。
- Scope delta: なし
- Handoff summary: 上記 Current State のとおり。
- Next-phase impact: Phase 3 で Trade page session を載せれば、`PlayerCurrentStateDto` への snapshot 配線と整合させる。

## Phase 3

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
