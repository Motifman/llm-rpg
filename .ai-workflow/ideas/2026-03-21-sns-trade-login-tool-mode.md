---
id: feature-sns-trade-login-tool-mode
title: SNS ツール拡充と SNS ログイン／ログアウトによるツールモード切替（Trade 含む）
slug: sns-trade-login-tool-mode
status: idea
created_at: 2026-03-21
updated_at: 2026-03-21
source: flow-idea
branch: null
related_idea_file: null
---

# Goal

- LLM エージェントが **SNS ドメインの能力をツール経由で漏れなく使える**ようにし、application 層の **コマンド／クエリで既にある操作**とツール定義のギャップを埋める。
- **「ログイン」は Web サービスの認証ではない。** ゲーム内で **SNS アプリを開いた／閉じた** に相当する **SNS 専用状態（SNS モード）への遷移**として表現する。SNS アプリを開いていないときは SNS 機能は使えない、というルールをツールで表現する。
- **プレイヤーとゲーム内 SNS ユーザーは常に紐づいている前提**（本フローでアカウント新規作成まで必須にしない）。
- **SNS モード ON** の間は SNS・Trade・タイムライン系ツールが使え、**ログアウト**で通常プレイのツールセットに戻る。ツール一覧では **SNS モードに入る操作を最初に見せる**。

# Success Signals

- `application/social/contracts/commands.py` にあるコマンドのうち、意図的に除外しない限り **対応する LLM ツール（または読み取り経路）が揃っている**ことが一覧で説明できる。
- **SNS モード OFF**: `sns_*`（ログイン用を除く）・`trade_*`・タイムライン取得ツールは **ツール一覧に出ない**（カタログ未登録または同等）。**例外として「SNS モードに入る」ためのツールだけ**が見える（先頭表示）。
- **SNS モード ON**: 上記が利用可能。**ログアウト**で SNS モード OFF に戻り、再び **ログイン用ツール以外の SNS 系は見えない**状態になる（通常の移動・戦闘など通常プレイツールはそのまま）。
- **タイムライン系は複数**用意する（Twitter 的 UX）。少なくとも **フォローしているプレイヤーの投稿だけが並ぶタイムライン**（ホーム／フォロー中）を含める。

# Non-Goals（今回の idea では確定しない／後続で切る）

- 外部 OAuth・パスワード認証など **実アカウント認証**はスコープ外。状態は **SNS モード ON/OFF** のみ。
- **プレイヤーと SNS の初回紐付け／ユーザー作成**をログインツールの必須ステップにすることは想定しない（既に紐づいている前提）。
- ドメインモデルの大規模変更（SNS 集約の再設計）は、必要性が出た場合のみ別 idea に分離。
- Shop・ギルド等を SNS モード必須にするかは **未確定**（現合意は **SNS + Trade + タイムライン系**）。

# Problem

1. **ツールとコマンド／クエリの非対称**  
   - 現状の SNS ツール（`tool_catalog/sns.py`）は投稿・リプライ・いいね・フォロー系・ブロック系まで。  
   - 一方 `commands.py` には **DeletePost / DeleteReply、プロフィール取得・更新、通知既読** などがあり、**対応ツールがない**。
   - **クエリ**（`post_query_service`, `reply_query_service`, `user_query_service`, `notification_query_service`）はアプリ層にあるが、**LLM から直接読む専用ツール**は別途設計が必要（`memory_query` の変数は episodic / facts / laws / recent_events / state / working_memory のみで **SNS フィードを直接参照しない**）。

2. **利用可否が「SNS モード」と結びついていない**  
   - `SnsToolAvailabilityResolver` は `context is not None` のみ（`availability_resolvers.py`）。  
   - Trade も在庫・取引有無ベースで、**SNS アプリ起動状態**とは独立。

3. **ユーザー意図**  
   - **SNS アプリを開いていないのに SNS を触れない**体験をツールで表現したい。冒頭は **SNS モードに入るツール**、モード内で SNS・Trade・タイムラインを使い、**ログアウトで通常プレイに戻す**。

# Constraints

- DDD: ドメインルールは既存サービス／集約に寄せ、ツールは **アプリケーション層のユースケース呼び出し**に留める。
- 既存パターン: `tool_catalog/*`、`tool_constants`、`sns_executor` / `trade_executor`、`register_default_tools` のフラグ、`PlayerCurrentStateDto` への拡張の有無。
- **タイムライン系は複数ツール**（Twitter 的）で設計する — プロンプト肥大化とのバランスは `PLAN` でツール名・説明を圧縮する等で調整。

# Code Context

| 領域 | モジュール |
|------|------------|
| SNS ツール定義 | `application/llm/services/tool_catalog/sns.py` |
| SNS 実行 | `application/llm/services/executors/sns_executor.py` |
| Trade ツール | `application/llm/services/tool_catalog/trade.py` |
| 利用可否 | `application/llm/services/availability_resolvers.py`（`SnsToolAvailabilityResolver` は context のみ） |
| カタログ登録 | `application/llm/services/tool_catalog/__init__.py`（`sns_enabled` / `trade_enabled`） |
| コマンド | `application/social/contracts/commands.py` |
| クエリ | `application/social/services/*_query_service.py` |
| wiring | `application/llm/wiring/__init__.py`（`sns_enabled` は `post_service is not None` 等） |

**調査で判明したギャップ（コマンド → ツール）**

- ツールあり: CreatePost/Reply, LikePost/Reply, Follow/Unfollow, Subscribe/Unsubscribe, Block/Unblock  
- ツールなし（候補）: DeletePost, DeleteReply, UpdateUserProfile, GetUserProfiles（要設計）, MarkNotificationAsRead, MarkAllNotificationsAsRead  

**クエリ**: タイムラインは **複数ツール**（フォロー中 TL 必須、その他は Twitter 的に増やす）。通知・プロフィール等は `PLAN` で列挙。

# Open Questions（残り）

1. **フォロー中 TL 以外**に、最初から必須にしたいタイムライン種別（例: 自分の投稿のみ、通知タブ、ブックマーク等）の **MVP 一覧**。
2. 実装戦略 **A / B / C** の最終選択（ユーザー合意: **ログアウト後は SNS 系はログインツール以外見えない** → **A は不適合寄り**。B または C を推奨）。

# Decision Snapshot

- **Proposal**:  
  - **SNS モード**（`sns_app_open` / `sns_session_active` 等）を `PlayerCurrentStateDto` または同等に持ち、**モードに入る／出るツール**で切り替える。  
  - **SNS モード OFF** のツールカタログ: 通常プレイツール + **`sns_enter`（仮）だけ**を SNS カテゴリとして出す。**SNS モード ON** で `sns_*` / `trade_*` / **複数タイムライン取得ツール** / `sns_logout` を登録。  
  - **Trade** は **SNS モードと同じ理由**（アプリを開いていないと市場機能を触らせない）でモード必須。  
  - **不足コマンド**は `commands.py` / query と照合してツール追加（削除・プロフィール・通知既読など）。

- **Options considered**:  
  - A: フラグ + リゾルバのみ → **一覧にツール名が残りやすく、今回の「見えなくなる」と矛盾しがち**  
  - B: モードに応じてカタログを **登録ツール集合ごと切替**  
  - C: レジストリ差し替え（B の強い版）

- **Selected option**: **B または C**（ユーザー確認済み: ログアウト後は **ログインツール以外の SNS 系が見えない**）。最終は実装コストで B vs C を決める。

- **Why this option now**: 表示上「見えない」が要件のため、**カタログ／登録集合の差**が主戦場。

# Alignment Notes

- **Initial interpretation**: 「ログイン」は認証ではなく **SNS 専用状態への遷移**。
- **User-confirmed intent**（2026-03-21）:  
  - ログイン = **SNS アプリを開いた状態**のメタファ。プレイヤーとゲーム内 SNS は **常に紐づけ済み**。  
  - タイムラインは **複数**、Twitter 想定。**フォローしているプレイヤーだけの TL** を含む。  
  - Trade のモード必須理由は **SNS と同じ**（アプリ未起動では使わせない）。  
  - ログアウト後は **ログインツール以外は見えない**（= SNS モード用ツールは一覧から消え、**SNS に入るためのツールだけ**が通常時に見える）。

- **Cost or complexity concerns**: タイムライン複数によるツール数増加、モード別カタログのテスト。

- **Assumptions**:  
  - 外部認証なし。**SNS モード**はゲーム内フラグ。  
  - 紐づけ済みプレイヤーで動かす（初回 `create_user` は別コンテキストでも可）。

- **Reopen alignment if**:  
  - 「見えない」を **executor 拒否**で済ませる方針に落とす場合（文言と要件の再確認）。  
  - Shop 等も SNS モード必須に広げる場合。

# Promotion Criteria（planning に進む前に）

- [ ] SNS モードの **状態の置き場所**（DTO 拡張 vs 別コンテキスト）が実装方針として確定  
- [ ] **タイムライン種別の MVP 一覧**（フォロー中 TL 以外）が合意されている  
- [ ] ツールカタログ戦略 **B vs C** が選ばれ、**SNS モード OFF 時はログイン用ツールのみが SNS 系として見える**ことがテストで表現できる  

# Promotion

- Next step: `flow-plan` で feature 化し、`PLAN.md` にツール一覧とテスト方針を書く。
