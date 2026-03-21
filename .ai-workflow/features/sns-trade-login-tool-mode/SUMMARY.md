---
id: feature-sns-trade-login-tool-mode
title: Sns Trade Login Tool Mode
slug: sns-trade-login-tool-mode
status: ship-ready
created_at: 2026-03-21
updated_at: 2026-03-22
branch: feature/sns-trade-login-tool-mode
---

# Outcome

SNS をゲーム内アプリとして表現し、`PlayerCurrentStateDto.is_sns_mode_active` とツールカタログ／resolver で通常時は `sns_enter` のみ、SNS モード時は SNS・Trade・MVP timeline read を一覧に出す構成を実装した。レビュー指摘（通知既読の所有者検証、`create_world_query_service` 経由の `is_sns_mode_active` 回帰）は解消済み。

# Delivered

- `PlayerCurrentStateDto.is_sns_mode_active` と `SnsModeSessionService`、モード別ツール登録・resolver（`register_default_tools` / `SnsToolAvailabilityResolver` 等）
- `sns_enter` / `sns_logout` と不足 command ツール、MVP 3 種（`sns_home_timeline` / `sns_list_my_posts` / `sns_list_user_posts`）と `PostQueryService` 接続
- `create_llm_agent_wiring` の `sns_mode_session` / `post_query_service`、`LlmAgentWiringResult.sns_mode_session`
- ブートストラップ文書: `application/llm/wiring/__init__.py`（同一セッション instance・`post_query_service` は LLM wiring のみ）、`world_query_wiring` の `sns_mode_session` 説明
- テスト: `test_available_tools_provider` / `test_tool_definitions` / `test_tool_command_mapper`、および `tests/application/llm/test_sns_mode_wiring_e2e.py`（wiring → `DefaultPromptBuilder.build` の `tools` をモード別に固定）
- レビュー後追補: `MarkNotificationAsReadCommand` に `user_id` を追加し、`NotificationCommandService` で所有者検証。`create_world_query_service(..., sns_mode_session=...)` の実配線を通る `is_sns_mode_active` 回帰テスト（`tests/application/world/services/test_world_query_service.py`）

# Remaining Work

- MVP 外（`STATE_AND_TOOL_MATRIX.md` defer）: 人気投稿・キーワード検索・通知一覧・関係プロフィール一覧・`GetUserProfilesCommand` 経路のツール化は follow-up
- 実ゲームの composition root で `create_world_query_service` と `create_llm_agent_wiring` に同一 `sns_mode_session` と `post_query_service=PostQueryService(...)` が渡っているかの手動確認（コードベースはテストで固定済み）
- **残余リスク（REVIEW 記載）**: `demos/sns/demo_sns_system.py` の手動操作は自動テストの対象外

# Evidence

- **Release gate**: `REVIEW.md` の Release Gate は `Ship ready: yes`、Blocking findings なし（2026-03-22 時点）
- **テスト実行**（2026-03-22、venv、pytest 8.4.1 / Python 3.10.20）:

```text
python -m pytest tests/application/llm/ tests/application/social/services/test_notification_command_service.py tests/application/world/services/test_world_query_service.py -q
```

- **結果**: `1109 passed`（1 warning、所要約 4.3s）

# Merge / 出荷後の git 動線

- **ブランチ**: `feature/sns-trade-login-tool-mode`
- **推奨**: 変更が複数モジュールにまたがるため、CI とレビュー履歴のため **main 向け PR を開いてマージ**するのが無難
- **代替**: 単独開発で PR を挟まない方針なら、`main` を最新化のうえ **ローカルで fast-forward または `--no-ff` マージ**でも可（コミットは Conventional Commits を維持）

マージ後はリモートへ `push`、不要なら feature ブランチ削除。
