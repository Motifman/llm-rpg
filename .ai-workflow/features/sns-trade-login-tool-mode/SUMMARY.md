---
id: feature-sns-trade-login-tool-mode
title: Sns Trade Login Tool Mode
slug: sns-trade-login-tool-mode
status: completed
created_at: 2026-03-21
updated_at: 2026-03-21
branch: feature/sns-trade-login-tool-mode
---

# Outcome

SNS をゲーム内アプリとして表現し、`PlayerCurrentStateDto.is_sns_mode_active` とツールカタログ／resolver で通常時は `sns_enter` のみ、SNS モード時は SNS・Trade・MVP timeline read を一覧に出す構成を実装した。

# Delivered

- `PlayerCurrentStateDto.is_sns_mode_active` と `SnsModeSessionService`、モード別ツール登録・resolver（`register_default_tools` / `SnsToolAvailabilityResolver` 等）
- `sns_enter` / `sns_logout` と不足 command ツール、MVP 3 種（`sns_home_timeline` / `sns_list_my_posts` / `sns_list_user_posts`）と `PostQueryService` 接続
- `create_llm_agent_wiring` の `sns_mode_session` / `post_query_service`、`LlmAgentWiringResult.sns_mode_session`
- ブートストラップ文書: `application/llm/wiring/__init__.py`（同一セッション instance・`post_query_service` は LLM wiring のみ）、`world_query_wiring` の `sns_mode_session` 説明
- テスト: `test_available_tools_provider` / `test_tool_definitions` / `test_tool_command_mapper`、および `tests/application/llm/test_sns_mode_wiring_e2e.py`（wiring → `DefaultPromptBuilder.build` の `tools` をモード別に固定）

# Remaining Work

- MVP 外（`STATE_AND_TOOL_MATRIX.md` defer）: 人気投稿・キーワード検索・通知一覧・関係プロフィール一覧・`GetUserProfilesCommand` 経路のツール化は follow-up
- 実ゲームの composition root で `create_world_query_service` と `create_llm_agent_wiring` に同一 `sns_mode_session` と `post_query_service=PostQueryService(...)` が渡っているかの手動確認（コードベースはテストで固定済み）

# Evidence

- 最終テスト: `python -m pytest tests/application/llm/`
- 追加回帰: `python -m pytest tests/application/llm/test_sns_mode_wiring_e2e.py`
- レビュー・マージ: 未（ブランチ `feature/sns-trade-login-tool-mode` 上）
