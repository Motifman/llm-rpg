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

- Active phase: Phase 3（次に着手）
- Last completed phase: Phase 2
- Next recommended action: `flow-exec` で Phase 3（SNS モード遷移ツールと不足 command tool）
- Handoff summary:
  - `PlayerCurrentStateDto.is_sns_mode_active` とビルダー既定 `False`、`sns_enter` 定義、`SnsEnterToolAvailabilityResolver` / `SnsModeRequiredAvailabilityResolver`、既存 SNS 操作系は `SnsToolAvailabilityResolver` を SNS モード ON のみに変更。Trade は `trade_enabled and sns_enabled` でのみ登録し resolver で SNS モード必須に。`test_available_tools_provider` / `test_tool_definitions` で OFF/ON の tool 名を固定。

# Phase Journal

## Phase 2: モード別カタログ切替の基盤化

- Started: 2026-03-21
- Completed: 2026-03-21
- Tests: `pytest tests/application/llm/test_available_tools_provider.py tests/application/llm/test_tool_definitions.py`、および `tests/application/llm/` 全件
- Findings:
  - 登録集合は「Trade は sns と同時登録」に寄せ、モード別の「見えない」は resolver + `is_sns_mode_active` で達成。`sns_enter` の executor / mapper は Phase 3（現状はツール一覧のみ、実行は UNKNOWN_TOOL）。
  - ビルダーは永続ソース未確定のため `is_sns_mode_active=False` 固定。Phase 3 の enter/logout ユースケース接続時に供給元を確定する。
- Plan revision check:
  - Phase 3〜5 の順序・成功条件は維持。`sns_enter` の実行経路は Phase 3 スコープとして既に PLAN にあり追加 phase は不要。
- User approval:
  - 不要（PLAN の future phase 文言変更なし）
- Plan updates:
  - `PLAN.md` Change Log のみ（完了記録）
- Goal check:
  - SNS モード OFF/ON で tool 名がテストで固定され、通常時は SNS 系は `sns_enter` のみ（他 sns_* / trade_* は非表示）を満たす
- Scope delta:
  - なし
- Handoff summary:
  - Phase 3 で `sns_enter`/`sns_logout` の application ユースケース、executor・mapper、モード状態の更新先（永続またはセッション）を接続
- Next-phase impact:
  - `sns_logout` 定数・resolver（ON のみ）と既存 command ツール追加が Phase 3 の主作業

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
