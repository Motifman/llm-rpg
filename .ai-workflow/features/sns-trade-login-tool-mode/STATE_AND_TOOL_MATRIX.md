---
id: feature-sns-trade-login-tool-mode
artifact: state-and-tool-matrix
title: SNS モード状態契約とツール表示行列
slug: sns-trade-login-tool-mode
status: active
created_at: 2026-03-21
updated_at: 2026-03-21
---

# 1. `PlayerCurrentStateDto` への状態項目（Phase 2 で実装）

| フィールド名 | 型 | 意味 |
|-------------|-----|------|
| `is_sns_mode_active` | `bool` | **ゲーム内 SNS アプリを開いている**（SNS モード ON）とみなすか。認証ではなく UI メタファ。`True` のとき SNS モード用ツール集合をカタログに載せる。`False` のときは通常プレイ用集合 + モード遷移用の `sns_enter` のみが SNS 系として見える。 |

- **デフォルト**: `False`（ビルダーが値を埋めない後方互換は `False` 扱い）。
- **ソース**: `player_current_state_builder` が、ランタイム上の SNS モード状態（永続化方針は Phase 2 以降の実装で確定。候補はプレイヤー／セッション付きの既存コンテキスト合成）から供給する。
- **単一の参照点**: `DefaultAvailableToolsProvider` およびツール登録分岐はこのフラグを読む（B 案: 登録集合の切替が主、resolver は補助）。

# 2. ツール名・説明の命名方針

- **プレフィックス**: 既存どおり `sns_` / `trade_`（`tool_constants` の `TOOL_NAME_PREFIX_*`）。
- **モード遷移**: `sns_enter` / `sns_logout`（「ログイン／ログアウト」ではなく、説明文で **SNS アプリを開く／閉じる** と明示する）。
- **読み取り系（timeline MVP）**: 動詞 + 対象が分かる英語スネークケース（例: `sns_home_timeline`, `sns_list_my_posts`, `sns_list_user_posts`）。実装時は `tool_constants` に `TOOL_NAME_*` を追加し、定義・mapper・executor で同一文字列を使う。
- **説明文**: ユーザー向けに「ゲーム内 SNS」「認証ではない」を必要な箇所（enter/logout）のみ短く触れる。既存ツールとトーンを揃える。

# 3. 表示行列（モード × ツール）

凡例: **○** = 一覧に出す / **×** = 一覧に出さない（登録集合に含めない）

## 3.1 通常時（`is_sns_mode_active == False`）

| カテゴリ | ツール名（論理名） | 表示 |
|----------|-------------------|------|
| モード遷移 | `sns_enter` | ○（**SNS 系で唯一 ○。一覧では可能なら先頭付近**） |
| モード遷移 | `sns_logout` | × |
| SNS 投稿・反応・関係 | `sns_create_post` … `sns_unblock`（既存 10 種） | × |
| Trade | `trade_offer`, `trade_accept`, `trade_cancel`, `trade_decline` | × |
| Timeline MVP（Phase 4） | `sns_home_timeline`, `sns_list_my_posts`, `sns_list_user_posts`（予定名） | × |
| その他通常プレイ | world / move / speech / …（既存） | ○（従来どおり） |

## 3.2 SNS モード ON（`is_sns_mode_active == True`）

| カテゴリ | ツール名（論理名） | 表示 |
|----------|-------------------|------|
| モード遷移 | `sns_enter` | ×（再入不要なら登録しない。実装で「入るだけ」なら × で問題なし） |
| モード遷移 | `sns_logout` | ○ |
| SNS | 既存 `sns_*` 10 種 + Phase 3 で追加する command 系 | ○ |
| Trade | 4 種すべて | ○ |
| Timeline MVP | 上記 3 種 | ○ |

※ `sns_enter` を ON 時に出すかは実装時に決める。推奨: **OFF のみ ○**、ON では `sns_logout` のみモード遷移として表示。

# 4. `commands.py` との対応（コマンドパリティ）

`application/social/contracts/commands.py` のコマンドを列挙し、**今回のツール／クエリでカバーする対象**と **意図的に後回しするもの**を固定する。

## 4.1 Phase 3 までにツール（入口）を用意する（パリティ対象）

| コマンド | 備考 |
|----------|------|
| `UpdateUserProfileCommand` | ツール未着手 → Phase 3 |
| `DeletePostCommand` | 同上 |
| `DeleteReplyCommand` | 同上 |
| `MarkNotificationAsReadCommand` | 同上 |
| `MarkAllNotificationsAsReadCommand` | 同上 |
| （モード遷移） | `sns_enter` / `sns_logout` はアプリケーション層のユースケース経由で `is_sns_mode_active` を更新する想定（Phase 3） |

## 4.2 既にツールが存在しパリティ維持

| コマンド | 既存ツール |
|----------|------------|
| `CreatePostCommand` | `sns_create_post` |
| `CreateReplyCommand` | `sns_create_reply` |
| `LikePostCommand` / `LikeReplyCommand` | `sns_like_post` / `sns_like_reply` |
| `FollowUserCommand` … `UnblockUserCommand` | `sns_follow` … `sns_unblock` |

## 4.3 意図的に defer（MVP 外・本 feature の必須に含めない）

| コマンド / クエリ | 理由 |
|-------------------|------|
| `CreateUserCommand` | 初回 SNS ユーザー作成は feature 非スコープ（`PLAN.md` Out of scope） |
| `GetUserProfilesCommand` | プロフィール取得は通知・検索と同様、MVP 読み取りは timeline 3 種に集中 |
| `post_query_service.get_popular_posts` / `search_posts_by_keyword` / トレンド等 | 人気・検索は follow-up |
| `notification_query_service` の一覧系 | 既読コマンドは Phase 3、一覧表示ツールは必須にしない |
| `user_query_service` の関係プロフィール一覧など | 同上 |

## 4.4 Phase 4（MVP 読み取り）でカバーする query 対応

| 目的 | 想定ツール名（実装時に `tool_constants` 化） | 主な query |
|------|---------------------------------------------|------------|
| ホーム TL（フォロー中） | `sns_home_timeline` | `get_home_timeline` |
| 自分の投稿一覧 | `sns_list_my_posts` | `get_user_timeline`（viewer = 自分の `user_id`） |
| 特定ユーザーの投稿一覧 | `sns_list_user_posts` | `get_user_timeline`（対象 `user_id` を引数で指定） |

# 5. 後続 phase への参照

| Phase | この artifact の使い方 |
|-------|------------------------|
| 2 | `is_sns_mode_active` を DTO / builder に載せ、`register_default_tools` と provider で行列どおりに登録集合を切替 |
| 3 | パリティ 4.1 の command ツール + enter/logout |
| 4 | 4.4 の read ツール 3 種 |
| 5 | wiring・回帰テスト |

# 6. `IDEA.md` / `PLAN.md` との整合

- ログイン = **SNS アプリ起動メタファ**、`sns_enter` のみ通常時表示、カタログ戦略 B、MVP timeline 3 種 — 本ファイルの表と一致。
- 変更が必要になった場合は **Plan Revision Gate** に従い、`PLAN.md` と本ファイルを更新する。
