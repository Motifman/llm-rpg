---
id: feature-sns-virtual-pages-readmodel
title: Sns Virtual Pages Readmodel
slug: sns-virtual-pages-readmodel
status: shipped
created_at: 2026-03-22
updated_at: 2026-03-23
branch: feature/sns-virtual-pages-readmodel
---

# Outcome

SNS モード中のゲーム内 SNS を、LLM 向けの **仮想画面（home / post_detail / search / profile / notifications）** と **page-local ref**、**現在画面に応じたツール出し分け**として再構成した。既存の細かい read ツールは catalog から除去し、汎用ナビ＋`SnsPageQueryService` 経由のスナップショットに集約した。Phase 6 で **永続 read projection は不採用**を確定し、未読数は既存 `NotificationQueryService`、ref 無効化は page session のスナップショット世代で説明できる状態にした。

# Delivered

- **画面契約と DTO**: `SnsVirtualPageKind`、スナップショット DTO、Screen Scope Contracts（`PLAN.md`）に沿った表示・ページング・生 ID 非露出。
- **Page session**: `SnsPageSessionService`（タブ・offset・検索・profile 対象・ref マップ・世代バンプ）。
- **Page query**: `SnsPageQueryService.get_current_page_snapshot` が各画面を既存 query サービスで組み立て、ref を発行。
- **ツール統合**: `sns_view_current_page` / `sns_open_page` / `sns_open_ref` / `sns_page_next` / `sns_page_refresh` / `sns_switch_tab` と、画面依存の書き込み gating（executor・catalog・wiring・provider）。
- **旧 read 削除**: `sns_home_timeline` / `sns_list_my_posts` / `sns_list_user_posts` を catalog・executor から除去。
- **Phase 6**: projection 不採用の根拠を `PLAN.md` に記載し、`test_phase6_projection_decision.py` で未読経路を固定。
- **テスト**: page session、page query、executor 仮想ページ、available tools provider、Phase 6 判定を含む関連スイート。

# Remaining Work

- **本 feature の必須タスク**: なし（`PLAN.md` の全 phase 完了、`PROGRESS.md` と整合）。
- **運用・任意のフォロー**: アプリが `sns_page_query_service` / `sns_page_session` を配線しない場合、SNS ON でも仮想ページツールが一覧に出ない（設計どおり）。本番配線での観測や、負荷増大時の projection 再検討は `PLAN.md` の Reopen alignment に従う。

# Evidence

- **テスト（実施日: 2026-03-23）**:
  ```bash
  source venv/bin/activate
  python -m pytest tests/application/social/sns_virtual_pages/ \
    tests/application/llm/services/executors/test_sns_executor_virtual_pages.py \
    tests/application/llm/test_available_tools_provider.py -q
  ```
  **結果**: `42 passed`（1 warning、当該スイート範囲）。
- **レビュー**: `.ai-workflow/features/sns-virtual-pages-readmodel/REVIEW.md` に **`Ship ready: yes`**、Blocking findings なし。
- **マージ方針**:
  - **推奨**: `feature/sns-virtual-pages-readmodel` から **PR を開き**、`main` へマージ（差分レビュー・CI 確認用）。
  - **直接マージ**: 単独作業で CI をローカルで確認済みなら、`main` にチェックアウトして `merge --no-ff` でも可（プロジェクトの `feature-development-workflow.mdc` に従う）。

# 未解決・隠していない事項

- **軽量 projection**: 意図的に未導入。将来、一覧・未読コストや整合性が問題になった場合のみ再検討（`PLAN.md` Phase 6 記載どおり）。
