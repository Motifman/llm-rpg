---
id: feature-sns-trade-login-tool-mode
title: SNS ツール拡充と SNS モード切替
slug: sns-trade-login-tool-mode
status: in_progress
created_at: 2026-03-21
updated_at: 2026-03-21
branch: feature/sns-trade-login-tool-mode
---

# Current State

- Active phase: Phase 2（次に着手）
- Last completed phase: Phase 1
- Next recommended action: `flow-exec` で Phase 2（モード別カタログ切替の基盤化）を実装
- Handoff summary:
  - `STATE_AND_TOOL_MATRIX.md` に `is_sns_mode_active`、OFF/ON 表示行列、command parity（Phase 3/4 対象と defer）、MVP timeline 3 種の想定ツール名を固定。`IDEA.md` に要約を追記し `PLAN.md` の Code Context / Phase 1 / Change Log を更新。

# Phase Journal

## Phase 1: 状態契約とツール行列の固定

- Started: 2026-03-21
- Completed: 2026-03-21
- Commit: f269eaf
- Tests: コード変更なしのためスキップ（既存テストへの影響なし）
- Findings:
  - 既存 `sns.py` には `sns_enter` / `sns_logout` / timeline ツールは未存在。行列上の論理名は Phase 2〜4 で `tool_constants` および catalog に追加する前提で固定した。
  - ON 時は `sns_enter` を出さず `sns_logout` のみモード遷移として出す推奨を明文化（一覧のノイズ低減）。
  - `CreateUserCommand` は引き続き feature 外；読み取り defer に `GetUserProfilesCommand` と人気・検索・通知一覧を明示。
- Plan revision check:
  - Phase 2〜5 の順序・成功条件は維持できる。新規必須作業の抜けはなし。
- User approval:
  - 不要（artifact のみ、plan の future phase 変更なし）
- Plan updates:
  - `PLAN.md` に Phase 1 artifact 参照・Change Log・`in_progress`・Code Context を反映
- Goal check:
  - Phase 1 の Checkpoint（`PLAN.md` と `IDEA.md` に一致した契約）を満たす
- Scope delta:
  - なし
- Handoff summary:
  - Phase 2 で `PlayerCurrentStateDto.is_sns_mode_active` の供給（ビルダー）と `register_default_tools` / provider の登録集合切替、Trade を SNS モード側へ、provider 系テストを追加する
- Next-phase impact:
  - 行列どおりに tool 名定数・カテゴリ登録を分岐すればよい。`sns_enter` は通常時のみ登録、`trade_*` は SNS モード時のみ、など。

## Planning

- Started: 2026-03-21
- Completed: 2026-03-21
- Commit:
- Tests: none (planning artifact update only)
- Findings:
  - `SnsToolAvailabilityResolver` は `context is not None` のみで、「一覧から消える」要件は resolver 単独では満たせない
  - `register_default_tools()` は `trade_enabled` / `sns_enabled` のカテゴリ一括登録なので、モード別登録集合切替が主要な設計点
  - `PlayerCurrentStateDto` は provider / resolver / prompt 側で既に共通参照点になっており、状態置き場として最も導入しやすい
  - 既存 query には `get_home_timeline` / `get_user_timeline` / プロフィール / 通知 があり、MVP timeline 3 種は既存 service を再利用できる
- Plan revision check:
  - 初回 plan 作成なので revision なし
- User approval:
  - MVP timeline 3 種、B 案、`PlayerCurrentStateDto` 拡張方針について会話で確認済み
- Plan updates:
  - Phase 1-5 を定義
- Goal check:
  - execution に進めるだけの状態契約、phase 順序、成功条件、reopen 条件を `PLAN.md` に反映済み
- Scope delta:
  - 人気投稿/検索/通知一覧/関係プロフィール一覧は MVP 必須から外し、follow-up 候補として明記
- Handoff summary:
  - 次は Phase 1 で SNS モード状態項目名、tool matrix、command parity の defer 範囲を固定する
- Next-phase impact:
  - Phase 1 の matrix が Phase 2 以降の tool constants / catalog / mapper / tests の増減を決める
