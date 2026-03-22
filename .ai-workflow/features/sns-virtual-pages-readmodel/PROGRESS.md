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

- Active phase: **Phase 2**（Page Session と Page DTO 基盤）
- Last completed phase: **Phase 1**（画面契約と遷移モデル固定）
- Next recommended action: `SnsPageSessionService` または `sns_mode_session` 拡張の設計確定と、画面種別 enum / DTO / ref 生成の最小実装＋ unit test
- Handoff summary: `PLAN.md` に **Screen Scope Contracts** を追加済み。5 画面・タブ・ref・ページング・汎用ツール一覧・既存 query 対応表を固定。以降の phase はこの契約を原則変更しない。

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
