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

- Active phase: Phase 2（Trade モード導線と露出分離）
- Last completed phase: Phase 1（Active App Slot 契約の固定）
- Next recommended action: `register_default_tools` / resolver / `trade_enter`・`trade_exit` と SNS 配線の更新
- Handoff summary: 単一 `ActiveGameAppSessionService` が `SnsModeSessionService` 配下に統合済み。`PlayerCurrentStateDto` に `active_game_app` / `is_trade_mode_active` を追加し、`is_sns_mode_active` は `__post_init__` で整合。Trade 入場 API は `enter_trade` / `exit_trade` がセッション層に存在（Phase 2 で executor から接続予定）。

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
