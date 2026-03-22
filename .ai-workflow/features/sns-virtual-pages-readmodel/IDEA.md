---
id: feature-sns-virtual-pages-readmodel
title: LLM向け仮想SNS画面・画面遷移・ページスコープツール
slug: sns-virtual-pages-readmodel
status: idea
created_at: 2026-03-22
updated_at: 2026-03-22
source: flow-idea
branch: null
related_idea_file: .ai-workflow/ideas/2026-03-22-sns-virtual-pages-readmodel.md
---

# Goal

- **ゲーム内 SNS を Twitter 風の「仮想画面」群として LLM に提供する。** query の断片ではなく、`home` / `post_detail` / `search` / `profile` / `notifications` の画面と、その間の遷移を持つ UI として扱う。
- **LLM に見せるツールは「現在画面で使えるもの」に絞る。** 画面に応じてツール集合を切り替え、LLM が「画面を見る → その画面で押せる操作だけ選ぶ」という形で扱えるようにする。
- **生の内部 ID を LLM に見せない。** 画面スナップショットには page-local な参照子（ref）を含め、投稿・ユーザー・通知の遷移はその ref を使って行う。
- **既存の query service を内部再利用しつつ、画面用の読み取りモデルを再構成する。** 画面 DTO と page session が主であり、永続化された ReadModel / projection は必要性が明確な場合のみ導入する。

# Success Signals

- SNS モード ON 時、LLM は **現在画面のスナップショット**と **その画面で利用可能なツールのみ**を受け取り、画面遷移を伴う操作ができる。
- `home`（`following` / `popular` タブ）、`post_detail`、`search`、`profile`、`notifications` の各画面について、**表示項目・遷移先・許可操作**が契約として定義されている。
- 投稿詳細やプロフィール遷移などが **生 ID を露出せず ref ベース**で実現されている。
- **既存の個別 read ツール**（`sns_home_timeline` など）に頼らなくても、仮想画面ツール群だけで主要な SNS 読み取り導線が成立する。
- 既存の **SNS モード切替・Trade 連動**を壊さず、LLM にとってのツール一覧が整理される。

# Non-Goals（この idea の段階で必須にしない／別 idea に逃がしうるもの）

- **本格的なレコメンドエンジン**の導入。`home` の第 2 タブは当面 `popular` とし、内部実装は popular / trending ベースでよい。
- **タイムライン全文を、ユーザーごとに常時マテリアライズ**して保持すること。
- **全文 projection を前提とした巨大な永続 ReadModel** の新設。
- **外部 OAuth・実認証**、プレイヤーと SNS の初回紐付け必須化。
- **Shop / Guild 等のモード必須化**の拡大。
- 既存 `PostQueryService` / `UserQueryService` / `NotificationQueryService` / `ReplyQueryService` を **無条件削除**すること。

# Problem

1. **読み取りツールを query 単位で足し続けると、LLM から見た SNS が「画面」ではなくバラバラの API 群になる。**
2. **「今どの画面にいるか」と「その画面で何が押せるか」が結びついていない。** そのため、LLM が人間的な UI メタファで操作しにくい。
3. **生 ID 非露出ポリシー**を保ちつつ、画面内の投稿・ユーザー・通知を指定して遷移する仕組みが必要である。
4. **通知やタイムラインは既存 query / event 経路がある。** 新しい画面モデルを作るとしても、既存の正を無視して全面再構築すると重複と整合コストが大きい。

# Constraints

- **DDD**: 画面用ツールはアプリケーション層のユースケース呼び出しに留める。page session や ref 解決もアプリケーション層で扱い、ドメインを UI 状態で汚さない。
- **既存パターン**: `available_tools_provider` による利用可能ツール出し分け、`sns_mode_session` によるモード状態、`tool_catalog` / executor / wiring の登録パターンを踏襲する。
- **読み取り実装**: 投稿・通知・プロフィール・リプライは **既存 query service の Pull 合成**を基本とする。
- **ReadModel / projection**: 導入する場合も **未読数、バッジ、page invalidation 用メタ**など軽量なものに限定し、本文の二重保存は避ける。
- **参照指定**: 画面内で見えている項目の選択は **page-local ref** で行い、生の `post_id` / `user_id` / `notification_id` を LLM に見せない。

# Code Context

| 領域 | モジュール・備考 |
|------|------------------|
| SNS モードの既存状態 | `application/social/services/sns_mode_session_service.py`、`PlayerCurrentStateDto.is_sns_mode_active` |
| 既存 SNS read | `application/social/services/post_query_service.py`、`reply_query_service.py`、`user_query_service.py`、`notification_query_service.py` |
| SNS 通知生成 | `application/social/services/notification_event_handler_service.py` |
| SNS イベント登録 | `infrastructure/events/sns_event_handler_registry.py` |
| ツール出し分け | `application/llm/services/available_tools_provider.py`、availability resolver 群 |
| 既存 SNS ツール | `application/llm/services/tool_catalog/sns.py`、`services/executors/sns_executor.py` |
| ReadModel 先行例 | `domain/trade/read_model/trade_read_model.py`、`application/trade/handlers/trade_event_handler.py` |

**調査メモ**:
- `ReplyQueryService` には **ポスト詳細 + 返信ツリー** を返す `get_reply_thread` が既にある。
- `PostQueryService` には **ホームTL / ユーザー投稿 / 検索 / popular / trending hashtag** の材料がある。
- `UserQueryService` は **自分・他人プロフィール** および follow / follower 系のプロフィール列挙が可能。
- したがって、仮想画面は **既存 query service の束ね直し**でかなり構築できる。

# Open Questions（plan 前に解くとよいもの）

1. **page session の置き場**: `sns_mode_session` 拡張か、SNS 専用の `SnsPageSessionService` を別で持つか。
2. **画面ツールの粒度**: `sns_view_current_page` / `sns_open_page` / `sns_open_ref` / `sns_page_next` / `sns_switch_tab` / `sns_page_refresh` / 画面依存アクション、までを最終形とするか。
3. **ref の寿命と invalidation**: 画面更新や次ページ取得で過去 ref をどう扱うか。
4. **popular タブの内部実装**: `get_popular_posts` と trending 情報をどう組み合わせるか。
5. **軽量 projection の要否**: 通知未読数や page invalidation に projection を入れる必要があるか。
6. **既存 read ツール**をどの phase で catalog から外し、どの phase で削除するか。

# Decision Snapshot

- **Proposal**:
  - **仮想 SNS 画面**（`home` / `post_detail` / `search` / `profile` / `notifications`）を定義する。
  - LLM は **現在画面のスナップショット**と **その画面で使えるツール**だけを受け取る。
  - 画面内の投稿・ユーザー・通知の指定は **page-local ref** で行い、生 ID は見せない。
  - 画面表示は **既存 query service の Pull 合成**を基本とし、必要なら軽量 projection を追加する。
  - 既存の個別 read ツールは最終的に **catalog から外して削除**する。

- **Options considered**:
  - **A**: query ごとに read ツールを増やし続ける。
  - **B**: 仮想画面 + page session + 画面依存ツール出し分け（本 idea）。
  - **C**: 画面本文まで全面 projection する。

- **Selected option**: **B**。A は UI メタファが壊れ、C はコストが重い。

- **Why this option now**: ユーザー要望の中心が **「LLM フレンドリーな SNS UI」** であり、画面・遷移・ツール出し分けを最初から final shape として決めた方が設計がぶれにくいため。

# Alignment Notes

- **Initial interpretation**: 当初は ReadModel 中心の集約 read tool を想定していた。
- **User-confirmed intent**（会話より）:
  - Twitter 風に、**複数の固有画面**と **その間の遷移**を持つ UI として作りたい。
  - `profile` は **自分にも他人にも使うプロフィール画面**として扱う。
  - `home` の第 2 タブは **recommended ではなく popular** とする。
  - ReadModel は **必要なら入れる、不要なら入れない**。
  - ツールは **少数の汎用ツールを current page に応じて出し分ける**方式を採る。
  - 既存 read ツールは **最終的に削除**する。

- **Cost or complexity concerns**:
  - 画面 session、ref の寿命、現在画面に応じた tool gating、既存 read tool との置換順序。

- **Assumptions**:
  - `sns-trade-login-tool-mode` で **SNS モードと provider / wiring の足場**は既に利用可能。
  - LLM 向けには **画面スナップショット JSON + 現在画面に応じた少数ツール**が最も扱いやすい。
  - popular タブは現時点では **popular / trending ベース**で十分である。

- **Reopen alignment if**:
  - 画面単位ではなく query 単位ツールへ戻したい、という要件に変わったとき。
  - 生 ID 非露出ポリシーを緩める判断が出たとき。
  - popular ではなく本格 recommendation が必要になったとき。
  - page session を SNS モード状態とは別概念で持つ必要が強くなったとき。

# Promotion Criteria（`flow-plan` に進む前に）

- [x] 画面一覧（`home` / `post_detail` / `search` / `profile` / `notifications`）が決まっている
- [x] `home` のタブが `following` / `popular` と決まっている
- [x] `profile` は自分・他人を統合した画面と決まっている
- [x] ツール戦略が **current page に応じた少数の汎用ツール出し分け**と決まっている
- [x] ReadModel / projection は **必要性が立った場合のみ追加**と決まっている
- [x] 既存 read ツールを最終的に削除する方針が決まっている

# Promotion

- Next step: `PLAN.md` に画面定義、page session、ref 契約、page-scoped tools、既存 read tool 置換、テスト方針を書き、`flow-exec` 可能な粒度の phase に落とす。
