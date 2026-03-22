---
id: feature-sns-virtual-pages-readmodel
title: Sns Virtual Pages Readmodel
slug: sns-virtual-pages-readmodel
status: in_progress
created_at: 2026-03-22
updated_at: 2026-03-22
branch: codex/sns-virtual-pages-readmodel
---

# Current State

- Active phase: **Phase 3**（Page Query Service 実装）
- Last completed phase: **Phase 2**（Page Session と Page DTO 基盤）
- Next recommended action: 既存 `PostQueryService` / `ReplyQueryService` 等を束ねる `SnsPageQueryService`（仮称）と画面スナップショット DTO の組み立て、各画面＋ref のテスト
- Handoff summary: `SnsPageSessionService`・画面 enum・`SnsPageSessionState`・ref 発行/解決・`PlayerCurrentStateDto` の `sns_virtual_page_kind` / `sns_home_tab` / `sns_page_snapshot_generation`・`create_world_query_service` / `create_llm_agent_wiring` / `SnsToolExecutor` への同一インスタンス配線を追加済み。

# Phase Journal

## Phase 1

- Started: 2026-03-22
- Completed: 2026-03-22
- Commit: （この更新とともにコミット）
- Tests: コード変更なしのため対象テストなし。回帰として `pytest tests/application/llm/test_available_tools_provider.py -q` を実行予定
- Findings:
  - 既存 `PostQueryService` / `ReplyQueryService` / `NotificationQueryService` / `UserQueryService` のメソッドで Phase 3 の画面スナップショットは十分束ね可能（IDEA の調査と一致）。
  - `post_detail` のページングは `get_reply_thread` 一発取得が中心。深いスレッド分割が必要なら Phase 3 で `get_replies_by_post_id` との分担をコード見て確定する余地あり（契約上は「既存 max_depth に従う」で十分）。
- Plan revision check: **不要**。future phase の順序・成果物は維持可能。Screen Scope Contracts は PLAN の Phase 2〜4 の記述と矛盾なし。
- User approval: **不要**（契約を画面一覧から外していない。`search` のキーワード/ハッシュタグ両モードを契約に明記したのみ）
- Plan updates: **Screen Scope Contracts** セクション追加、Phase 1 checkpoint 文言更新、Change Log 1 行
- Goal check: **達成** — 画面一覧・allowed actions・ref 意味・ページング方針が PLAN 上で曖昧なく記述された
- Scope delta: なし（Phase 1 の予定 scope 内）
- Handoff summary: Phase 2 では page session に `page_kind`, `home_tab`, `limit`/`offset`, 検索クエリ, profile 対象 ref, ref マップとスナップショット世代を載せる設計を具体化する
- Next-phase impact: DTO 名（`SnsVirtualPageKind` 等）は Screen Scope Contracts の用語に合わせる

## Phase 2

- Started: 2026-03-22
- Completed: 2026-03-22
- Commit: （phase 完了コミット）
- Tests: `pytest tests/application/social/sns_virtual_pages/`、`pytest tests/` 全件通過
- Findings:
  - page session は `SnsModeSessionService` とは別インスタンスで保持し、`sns_enter` / `sns_logout` で `on_enter_sns` / `on_exit_sns` を呼ぶと、モード ON/OFF とページ状態が整合する。
  - `get_state` は未初期化時に home 既定を自動作成するため、page session を配線していても enter 前に `get_player_current_state` が呼ばれると DTO に home が載りうる。Phase 4 で enter 必須にするかは運用で決められる（現状は `is_sns_mode_active` が False なら DTO の仮想ページフィールドは空のまま）。
  - ref プレフィックスは `r_post_NN` / `r_user_NN` / `r_reply_NN` / `r_notif_NN`（不透明文字列の契約を満たす）。
- Plan revision check: **不要**。Phase 3 の「page query が ref を含む DTO を組み立てる」前提は維持可能。
- User approval: **不要**（PLAN の Phase 2 scope から外れていない）
- Plan updates: **なし**
- Goal check: **達成** — メモリ上の page session・DTO 拡張・enter/logout 連動・単体テストで検証
- Scope delta: なし
- Handoff summary: Phase 3 で `SnsPageSessionService` を注入した query 層サービスが、各画面のスナップショット用 DTO と ref 発行を担う
- Next-phase impact: スナップショット DTO は `application/social/` 配下の新モジュールに置くと page session と並びやすい
