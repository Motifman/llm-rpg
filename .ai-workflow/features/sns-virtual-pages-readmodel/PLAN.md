---
id: feature-sns-virtual-pages-readmodel
title: Sns Virtual Pages Readmodel
slug: sns-virtual-pages-readmodel
status: completed
created_at: 2026-03-22
updated_at: 2026-03-23
branch: codex/sns-virtual-pages-readmodel
---

# Objective

SNS モード中のゲーム内 SNS を、LLM から見て扱いやすい仮想画面 UI として再構成する。`home` / `post_detail` / `search` / `profile` / `notifications` の画面、page-local ref による遷移、現在画面に応じた少数の汎用ツール出し分けを導入し、既存の個別 read ツールを最終的に置き換える。

# Success Criteria

- SNS モード ON 時、LLM は常に **現在画面スナップショット**を受け取り、画面に応じたツールのみを利用できる。
- `home`、`post_detail`、`search`、`profile`、`notifications` を相互遷移でき、主要導線が **生 ID 非露出**で成立する。
- `home` は `following` / `popular` タブを持ち、`post_detail` では投稿詳細・返信ツリー・いいね・返信が可能である。
- `profile` は自分・他人を統合し、プロフィール情報、投稿一覧、関係性情報からの遷移を持つ。
- `notifications` は投稿詳細またはプロフィールへの遷移が可能で、既読操作と両立する。
- 既存の個別 read ツールは catalog から外され、新しい画面ツール群に置き換わる。
- テストでは provider / tool catalog / executor / wiring / page query service の各層で、画面ごとの利用可能ツールと ref ベース遷移を確認する。

# Alignment Loop

- Initial phase proposal:
  - まず画面契約と ref 契約を固定し、その後 page session、page query service、tool integration、既存 read ツール置換の順に進める。
- User-confirmed success definition:
  - Twitter 風の複数画面と画面遷移を持つ LLM フレンドリーな SNS ツールを用意する。
  - `profile` は自分にも他人にも使う。
  - `home` の第 2 タブは `popular` とし、内部実装は popular / trending ベースでよい。
  - ReadModel / projection は必要なら入れ、不要なら無理に入れない。
  - ツールは少数の汎用ツールを current page に応じて出し分ける。
- User-confirmed phase ordering:
  - MVP と本番を分けず、最終形を先に固定したうえで、実装順序として phase を切る。
- Cost or scope tradeoffs discussed:
  - 画面本文を全面 projection するのは採らない。
  - search は画面の一種だが、他画面より入力依存であることを契約に明記する。
  - 既存 read ツールは最終的に削除するが、置換の安全性を見ながら段階的に外す。

# Scope Contract

- In scope:
  - 画面定義: `home` / `post_detail` / `search` / `profile` / `notifications`
  - `home` タブ: `following` / `popular`
  - page-local ref と、それを解決する page session
  - current page に応じた tool catalog / available tools の出し分け
  - 既存 query service を束ねる page query service / page DTO
  - 既存 read ツールの非表示化、置換、最終削除
  - 必要になった場合のみ軽量 projection の導入検討
- Out of scope:
  - 本格 recommendation engine
  - タイムライン本文の全面 materialize
  - 通知本文の二重保存
  - SNS モード以外の UI 状態管理一般化
  - 外部認証や初回アカウント紐付け
- User-confirmed constraints:
  - 生 ID は LLM に見せない
  - `profile` は self / other を統合する
  - `popular` は現状の query で実現可能な範囲に寄せる
  - 画面で使えるツールだけを見せる
- Reopen alignment if:
  - 生 ID 非露出ポリシーの維持が著しく実装を複雑化し、別案が必要になった場合
  - `popular` 実装のために推薦ロジックが実質必須と分かった場合
  - page session を `sns_mode_session` から切り離す必要が強くなった場合
  - 既存 query service の返却だけでは画面契約を満たせず、より大きな projection が必要になった場合

# Screen Scope Contracts（Phase 1 確定・以降の phase では原則変更しない）

以下は LLM 向け仮想 SNS 画面の **final shape** である。スナップショット JSON に載せる表示項目・遷移・操作の前提とし、page session / page query service / ツールはこれに従う。

## 共通

- **画面種別（`SnsVirtualPageKind` 想定）**: `home` | `post_detail` | `search` | `profile` | `notifications`
- **生 ID 非露出**: LLM に渡す本文・ツール引数では `post_id` / `user_id` / `reply_id` / `notification_id` を **出さない**。画面内の行選択は **page-local ref**（下記）のみ。
- **ページング（全画面共通方針）**: `limit` 省略時は **20**、最大 **100**。先頭スキップは **`offset`**（既存 `PostQueryService` / `NotificationQueryService` 等と整合）。page session が **現在画面・タブ・検索語・対象ユーザー・`limit`/`offset`** を保持する。
- **スナップショットに含めるメタ**: 画面種別、（該当時）アクティブタブ、ページング摘要（例: `offset`, `limit`, `has_more`）、未読バッジは **数値のみ**可（内部 ID は出さない）。

## Page-local ref 契約

- **目的**: スナップショット上の 1 行（投稿・ユーザー・リプライ・通知）を、ツール引数で指すための **セッション内ローカルな識別子**。
- **形式**: 実装は **不透明な文字列**（例: `r_post_01`, `r_user_3`）。LLM は構造を推測しない。
- **スコープ**: **現在の page session と現在の「スナップショット世代」** にのみ有効。`sns_page_refresh` や画面遷移後は、同一文字列が別実体を指しうるため **古い ref の再利用は非保証**（実装側は可能なら世代番号で無効化する）。
- **解決**: ref → 内部 ID の対応は **アプリケーション層（executor / page query の直前）** でのみ行い、ドメインに UI ref を持ち込まない。

## `home`

- **タブ**: `following`（フォロー TL） / `popular`（人気投稿。内部は `get_popular_posts`＋必要なら `get_trending_hashtags` 等のメタ。**レコメンドエンジンは使わない**）。
- **表示項目**:
  - タブ名、投稿リスト（各行: 著者表示名・本文要約・作成時刻・いいね数・返信数・既読系フラグに相当するものは PostDto 由来）。
  - 各行に **post 用 ref**（詳細へ）。
  - 著者名から **profile へ遷移する user ref**（権限上閲覧可能な場合のみ）。
- **許可操作（概念）**: タブ切替、タイムラインの再読込、次ページ、新規投稿（ compose ）、行から投稿詳細・プロフィールへ遷移。
- **内部クエリの主**: `following` → `PostQueryService.get_home_timeline` / `popular` → `get_popular_posts`（`timeframe_hours` は既定で既存デフォルトに合わせる）。

## `post_detail`

- **対象**: 1 つのルート投稿と、その返信ツリー。
- **表示項目**: `ReplyQueryService.get_reply_thread` に相当（ルート `PostDto` ＋ フラット `ReplyDto` 一覧と depth）。ルート・各返信に **post / reply 用 ref**、著者に **user ref**。
- **許可操作**: ルート・返信へのいいね、返信作成、自分の投稿・返信の削除、著者プロフィールへ遷移、（ルートから）ホーム等へ戻る。
- **注意**: 返信ツリーの深さは既存 `max_depth` に従う。ページングはスレッド全体の取得方針は Phase 3 で既存実装に合わせて確定する（必要なら `get_replies_by_post_id` との役割分担を明記する）。

## `search`

- **性質**: **入力依存**が他画面より強い。page session に **検索モード**（キーワード / ハッシュタグ）と **クエリ文字列** を保持する。
- **表示項目**: 検索結果の `PostDto` リスト（各行 post ref・著者 user ref）、任意でサジェスト用に trending hashtag の一部（あくまで補助）。
- **許可操作**: 検索実行（クエリ更新）、結果の再読込・次ページ、結果から `post_detail` / `profile` へ遷移。
- **内部クエリの主**: `search_posts_by_keyword` / `search_posts_by_hashtag`（既存シグネチャのまま束ねる）。

## `profile`

- **統合**: **自分・他人同一画面**。閲覧対象は page session の「対象ユーザー ref の解決結果」（自分画面はセルフ参照）。
- **表示項目**: `UserProfileDto` 相当（フォロー状態・数、表示名、bio 等）。**`user_id` は LLM 向け JSON では出さず**、プロフィール用 ref または `self` フラグで表す。
  - サブ: **そのユーザーの投稿一覧**（`get_user_timeline`、ページング）。
- **許可操作**: フォロー / アンフォロー / ブロック / サブスク等（関係性）、自分のみプロフィール更新、投稿一覧の post へ遷移、（他人から）ホーム等へ戻る。

## `notifications`

- **表示項目**: 通知リスト（`NotificationQueryService.get_user_notifications`）。各行に **notification ref**。本文・種別・時刻・既読フラグ。関連投稿・返信・actor がある場合は **post / reply / user への遷移用 ref**（解決可能な場合のみ）。
- **許可操作**: 1 件既読・全件既読、通知行から `post_detail` または `profile` へ遷移（関連 ID がないタイプは遷移不可と明示）。
- **既読と一覧**: 既読更新後はスナップショットを再取得すれば整合。未読数は数値表示に留め、内部 ID は出さない。

## 遷移（ツールと画面の対応・Phase 4 で実装する汎用ツール）

| ツール名（予定） | 役割 |
|------------------|------|
| `sns_view_current_page` | 現在画面のスナップショットを返す |
| `sns_open_page` | 論理画面へ遷移（`home` / `search` / `notifications` 等）。引数は page kind と、画面ごとの初期パラメータ（検索語など） |
| `sns_open_ref` | 現在スナップショットに含まれる ref の解決先へ遷移 |
| `sns_page_next` | 現在画面の次ページ（offset 進行） |
| `sns_page_refresh` | 同一条件の再取得（ref 世代更新あり得る） |
| `sns_switch_tab` | `home` の `following` / `popular` の切替 |

画面依存の **書き込み**（いいね・返信・フォロー・既読等）は **その画面にいるときだけ** catalog に出す（既存ツール名は Phase 4〜5 で ref 引数へ移行するか、ラッパーで吸収）。

## 既存 query サービス対応表（実装の正）

| 画面 / 機能 | 主な既存メソッド |
|-------------|------------------|
| `home` following | `PostQueryService.get_home_timeline` |
| `home` popular | `PostQueryService.get_popular_posts`（＋任意 `get_trending_hashtags`） |
| `post_detail` | `ReplyQueryService.get_reply_thread` |
| `search` | `search_posts_by_keyword` / `search_posts_by_hashtag` |
| `profile` | `UserQueryService.get_user_profiles`（コマンド経由）、`PostQueryService.get_user_timeline` |
| `notifications` | `NotificationQueryService.get_user_notifications`、既読系は既存 mark コマンド |

# Code Context

- Existing modules to extend
  - `src/ai_rpg_world/application/llm/services/tool_catalog/sns.py`
  - `src/ai_rpg_world/application/llm/services/executors/sns_executor.py`
  - `src/ai_rpg_world/application/llm/services/available_tools_provider.py`
  - `src/ai_rpg_world/application/llm/wiring/`
  - `src/ai_rpg_world/application/world/contracts/dtos.py`
  - `src/ai_rpg_world/application/social/services/sns_mode_session_service.py` または新規 page session
- Existing exceptions, events, inheritance, and test patterns to follow
  - 既存の SNS query service の例外ハンドリング方針
  - `NotificationEventHandlerService` / `TradeEventHandler` の非同期 handler パターン
  - `tests/application/llm/test_available_tools_provider.py`
  - `tests/application/llm/test_sns_mode_wiring_e2e.py`
  - `tests/application/social/services/test_notification_event_handler_service.py`
- Integration points and known risks
  - current page に応じた tool gating を provider / resolver / executor のどこまでで表現するか
  - ref 解決の寿命管理
  - `ReplyQueryService.get_reply_thread` と投稿詳細画面の契約整合
  - 既存 read ツール削除までの互換期間の扱い

# Risks And Unknowns

- page session をどこに持つかで責務がぶれやすい。
- ref の寿命と invalidation を雑に設計すると、古い ref を踏む不整合が出やすい。
- `popular` タブの内容が user expectation と乖離する可能性がある。
- 既存ツール削除を早めすぎると、回帰の切り分けが難しくなる。

# Phases

## Phase 1: 画面契約と遷移モデル固定

- Goal:
  - 仮想画面 UI の final shape を契約として固定する。
- Scope:
  - 5 画面の定義
  - `home` タブの定義
  - 各画面の表示項目、許可操作、遷移先の整理
  - ツール候補の確定
  - page-local ref の契約整理
- Dependencies:
  - 既存 query service の能力把握
- Parallelizable:
  - 低い
- Success definition:
  - 画面一覧、画面ごとの allowed actions、ref の意味、ページング方針が plan 上で曖昧なく書けている。
- Checkpoint:
  - `PLAN.md` に各画面の scope contract が書かれている（**Screen Scope Contracts** セクションで充足）。
- Reopen alignment if:
  - `search` を別 feature に分離した方が自然だと判明した場合
- Notes:
  - 実装前にここを固定し、以後の phase では契約を基本変更しない。

## Phase 2: Page Session と Page DTO 基盤

- Goal:
  - current page、tab、cursor、ref map を保持する page session と、画面スナップショット DTO を導入する。
- Scope:
  - `SnsPageSessionService` 相当の追加、または既存 session 拡張
  - 画面種別 enum / DTO
  - page-local ref 生成・解決契約
  - current page を prompt / tool decision に渡す基盤
- Dependencies:
  - Phase 1
- Parallelizable:
  - 中程度
- Success definition:
  - 画面遷移と ref 解決の最小単位がメモリ上で成立し、DTO と session の責務が明確である。
- Checkpoint:
  - self-contained な unit test で page session が検証されている。
- Reopen alignment if:
  - `PlayerCurrentStateDto` の責務に載せるには重すぎると判明した場合
- Notes:
  - ここでは projection はまだ必須にしない。

## Phase 3: Page Query Service 実装

- Goal:
  - 既存 query service を束ねて各画面のスナップショットを返す読み取りサービスを作る。
- Scope:
  - `home` (`following` / `popular`)
  - `post_detail`
  - `search`
  - `profile`
  - `notifications`
  - page-local ref を含む画面 DTO の組み立て
- Dependencies:
  - Phase 2
- Parallelizable:
  - 中程度
- Success definition:
  - 各画面が既存 query service の再利用で構築され、LLM が必要な遷移参照を受け取れる。
- Checkpoint:
  - page query service のテストで各画面の内容と ref 発行が確認できる。
- Reopen alignment if:
  - 既存 query だけでは必要な一覧やメタが取れず、新規 query 契約が多数必要になった場合
- Notes:
  - `popular` は recommendation ではなく popular / trending ベースで実装する。

## Phase 4: Tool Catalog / Executor / Provider 統合

- Goal:
  - 画面依存ツール出し分けを LLM stack に組み込む。
- Scope:
  - `sns_view_current_page`
  - `sns_open_page`
  - `sns_open_ref`
  - `sns_page_next`
  - `sns_page_refresh`
  - `sns_switch_tab`
  - 画面依存アクション（いいね、返信、既読など）の gating
  - provider / resolver / wiring / executor 更新
- Dependencies:
  - Phase 3
- Parallelizable:
  - 中程度
- Success definition:
  - 現在画面によって利用可能ツールが変わり、画面操作が end-to-end で成立する。
- Checkpoint:
  - wiring / available tools / executor の回帰テストが通る。
- Reopen alignment if:
  - 汎用ツール群では表現しきれず、画面専用ツールを増やす必要が出た場合
- Notes:
  - ここで LLM フレンドリーさを最優先する。

## Phase 5: 既存 Read ツール置換と削除

- Goal:
  - 個別 read ツールを新しい画面ツール群へ置き換え、catalog から外し、最終的に削除する。
- Scope:
  - `sns_home_timeline`
  - `sns_list_my_posts`
  - `sns_list_user_posts`
  - 必要に応じて関連する定義・executor・tests の整理
- Dependencies:
  - Phase 4
- Parallelizable:
  - 中程度
- Success definition:
  - 新しい導線だけで必要な読取ユースケースが通り、旧 read ツールが LLM に見えず、不要コードも削除できる。
- Checkpoint:
  - provider テストと prompt/wiring テストが新ツール群ベースで成立している。
- Reopen alignment if:
  - 移行直後の運用・検証のために一時的非表示期間が必要になった場合
- Notes:
  - 削除は最後に行う。

## Phase 6: 軽量 Projection の要否判定と必要最小限導入

- Goal:
  - 未読数や page invalidation に projection が必要かを判定し、必要な場合のみ導入する。
- Scope:
  - projection 不要なら明示的に不採用を確定
  - 必要なら未読数や軽量メタに限定
  - handler 登録とテスト追加
- Dependencies:
  - Phase 3 以降
- Parallelizable:
  - 低い
- Success definition:
  - projection を入れる理由、入れない理由のどちらかが明確に説明できる。
- Checkpoint:
  - `PLAN.md` / 実装 / テストの三者で整合が取れている。
- Reopen alignment if:
  - projection が実質本文キャッシュへ膨らみ始めた場合
- Notes:
  - この phase は conditional であり、不要なら「採用しない」を成果とする。

### Phase 6 実施結果（確定）

**軽量 read projection は採用しない。**

- **未読数**: `notifications` の `unread_count` は `NotificationQueryService.get_unread_count` がリポジトリを直接集計する。通知本文の二重保存や投影テーブルは不要（Screen Scope Contracts の「未読は数値のみ」に合致）。
- **page / ref invalidation**: スナップショット取得のたびに `SnsPageSessionService.bump_snapshot_generation` と ref マップ破棄で世代を進める。永続 projection ではなくセッション内メモリで完結。
- **回帰テスト**: `tests/application/social/sns_virtual_pages/test_phase6_projection_decision.py` で、未読が query 経由のライブ集計であることを明示的に固定。

**再検討の目安**（Reopen alignment と整合）: 一覧・未読の取得コストや整合性がボトルネックになった場合、または本文相当のキャッシュが必要になった場合。

# Review Standard

- No placeholder or temporary implementation
- DDD boundaries stay explicit
- Exceptions are handled deliberately
- Tests cover happy path and meaningful failure cases
- Existing strict test style is preserved
- Raw internal IDs are not exposed to the LLM-facing screen contract

# Execution Deltas

- Change trigger:
  - 実装中に画面契約、tool granularity、projection 必要性に大きな変更が出たとき
- Scope delta:
  - `search` の分離、`popular` 契約の変更、projection 導入、既存ツール削除タイミングの調整
- User re-confirmation needed:
  - 画面一覧の変更
  - 生 ID 非露出ポリシーの変更
  - 汎用ツール方針から画面専用多数ツールへの転換

# Plan Revision Gate

- Revise future phases when:
  - current page と tool gating の表現方法が実装上変わるとき
  - projection の必要性が新たに生まれたとき
- Keep future phases unchanged when:
  - 実装詳細の差し替えだけで、画面契約と final shape が変わらないとき
- Ask user before editing future phases or adding a new phase:
  - 画面一覧や主要ツール一覧を変えるとき
  - 旧 read ツールを残す判断へ戻すとき
- Plan-change commit needed when:
  - phase の順序や成果物が実質的に変わるとき

# Change Log

- 2026-03-22: Initial plan created
- 2026-03-22: Reframed from readmodel-centric query aggregation to virtual screens, page transitions, and page-scoped tool design
- 2026-03-22: Phase 1 — Added **Screen Scope Contracts** (per-screen display, actions, transitions, paging, ref rules, query mapping table, planned generic tools)
- 2026-03-23: Phase 6 — **Projection 不採用**を確定（未読は既存 query、ref 世代は page session）。`test_phase6_projection_decision.py` 追加
