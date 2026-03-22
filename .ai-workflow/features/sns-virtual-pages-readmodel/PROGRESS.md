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

- Active phase: **Phase 5**（既存 Read ツール置換と削除）
- Last completed phase: **Phase 4**（Tool Catalog / Executor / Provider 統合）
- Next recommended action: `sns_home_timeline` 等の旧 read ツールを catalog から外し、仮想画面ツールへの移行を完了する
- Handoff summary: 汎用ツール 7 種（`sns_view_current_page` 等）を `register_default_tools(..., sns_virtual_pages_enabled=...)` / `SnsToolExecutor` / `create_llm_agent_wiring(sns_page_query_service=..., reply_query_service=..., notification_query_service=...)` で配線。画面別 resolver で書き込み系を gating。`PlayerCurrentStateDto.sns_profile_is_self` を追加。

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

## Phase 3

- Started: 2026-03-22
- Completed: 2026-03-22
- Commit: （phase 完了コミット）
- Tests: `pytest tests/application/social/sns_virtual_pages/test_sns_page_query_service.py`、`pytest tests/` 全件通過
- Findings:
  - `SnsPageQueryService.get_current_page_snapshot` は先頭で `bump_snapshot_generation` を呼び、スナップショット取得のたびに ref マップを捨て世代を進める（古い ref の再利用を防ぐ）。
  - `post_detail` で `post_detail_root_post_id` が未設定のときは `SnsVirtualPageSnapshotDto.error` にメッセージを載せ、本文は返さない（遷移は Phase 4 のツールで事前設定する想定）。
  - `home` / `popular` は `limit+1` 件取得で `has_more` を付与。`popular` では追加で `get_trending_hashtags`（最大 10 件）を載せる。
  - `profile` は `profile_target_user_id` が未設定のとき閲覧者自身（`show_my_profile`）として扱う。
  - `search` は `search_mode` が `HASHTAG` のとき `search_posts_by_hashtag`、それ以外（`KEYWORD` または未設定）は `search_posts_by_keyword`。クエリ空なら結果は空。
  - `notifications` は一覧に `get_unread_count` を併記（数値のみ）。
- Plan revision check: **不要**。Phase 4 の汎用ツール一覧・provider 統合の前提は維持できる。
- User approval: **不要**（PLAN の Phase 3 scope から外れていない）
- Plan updates: **なし**
- Goal check: **達成** — 各画面が既存 query で組み立てられ、スナップショット DTO に page-local ref が載る
- Scope delta: なし
- Handoff summary: Phase 4 で `SnsPageQueryService` と `SnsPageSessionService` を executor / wiring に渡し、`sns_view_current_page` がスナップショット JSON を返すようにする
- Next-phase impact: ツール実行時に viewer = プレイヤーの SNS user id をどう渡すかは既存 SNS ツールと揃える

## Phase 4

- Started: 2026-03-22
- Completed: 2026-03-22
- Commit: （phase 完了コミット）
- Tests: `pytest tests/application/llm/services/executors/test_sns_executor_virtual_pages.py`、`pytest tests/application/llm/ -q`、`pytest tests/application/social/sns_virtual_pages/ -q`
- Findings:
  - `sns_virtual_pages_enabled` は `sns_enabled` と併用時のみ仮想ナビツールを登録（SNS 無効単体では追加しない）。
  - 画面別 gating は `sns_virtual_page_kind is None` のとき従来どおり許可（page session 未配線の互換）。
  - `sns_open_ref` の通知は `NotificationQueryService.get_user_notifications` を走査して ID 一致を探す（一覧外は失敗メッセージ）。
- Plan revision check: **不要**。Phase 5 の旧 read 削除・Phase 6 projection 判定は PLAN のまま進められる。
- User approval: **不要**（PLAN Phase 4 scope から逸脱なし）
- Plan updates: **なし**
- Goal check: **達成** — 汎用ツール・executor・wiring・provider（登録）・画面別 gating・回帰テスト
- Scope delta: なし
- Handoff summary: アプリ組み立てで `sns_page_query_service` と同一の `sns_page_session` を world query と wiring に渡すこと。`reply_query_service` / `notification_query_service` は open_ref 精度用に任意で注入。
- Next-phase impact: Phase 5 で旧 read ツールを catalog から外すと provider / テストの期待ツール名が変わる
