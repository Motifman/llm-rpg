---
id: feature-sns-virtual-pages-readmodel
title: LLM向け仮想SNSページとReadModel（ツール集約）
slug: sns-virtual-pages-readmodel
status: idea
created_at: 2026-03-22
updated_at: 2026-03-22
source: flow-idea
branch: null
related_idea_file: .ai-workflow/ideas/2026-03-21-sns-trade-login-tool-mode.md
---

# Goal

- **細かい SNS 読み取りツールを増やし続けない。** 代わりに、ゲーム内 SNS を **仮想的な「ページ」（画面）単位**で定義し、LLM が **少数のツール**で十分にプレイできるようにする。
- **ReadModel**（表示・参照に特化したモデル）を設計し、**ページ単位で一括取得**できる読み取り経路を用意する。更新は **ドメインイベントを購読する Handler** で ReadModel を整合させる、という形を第一候補とする（リポジトリ内の **Trade の `TradeReadModel` + `TradeEventHandler`** と同系の置き方）。
- **一般的に妥当な線**に寄せる: タイムライン本文は **無理に全文を投影し続けない**（後述）。通知は **既にイベント経路で生成されている**ため、二重化を避ける設計を優先する。

# Success Signals

- SNS モード ON 時、**定義した「ページ」に対応するデータ**が LLM エージェントに **提供され、利用可能であること**がテストまたは契約で示せる（ユーザー合意の成功イメージ）。
- **ツール数**が、個別 query ツールを列挙する方式に比べて **実質的に抑制**されている（例: ページ取得が 1 本＋必要ならナビ／アクションのみ）。
- ReadModel の **更新責務**（どのイベントで何を更新するか）が文書化され、**ドメインの正**との関係が説明できる。
- 既存の **SNS モード切替・Trade 連動**（`sns-trade-login-tool-mode` で完了した範囲）を **壊さない**。

# Non-Goals（この idea の段階で必須にしない／別 idea に逃がしうるもの）

- **タイムライン全文を、ユーザーごとに常時マテリアライズ**して保持すること（コスト・一貫性の理由で、まずは採用判断を保留）。
- **外部 OAuth・実認証**、プレイヤーと SNS の初回紐付け必須化（従来どおりスコープ外になりうる）。
- **Shop / Guild 等のモード必須化**の拡大。
- 既存 `PostQueryService` / `UserQueryService` を **無条件削除**すること（内部実装として再利用する道を残す）。

# Problem

1. **読み取りツールを細かく足すと、一覧とプロンプトが重くなる**（多数の query に 1:1 でツールが付く）。
2. SNS ドメインには **`domain/sns` 配下に ReadModel 名義の型はまだない**一方、**Trade には `TradeReadModel` とイベント Handler による更新**の先行実装がある。LLM 向けの「画面」には **同じパターンを移植できる余地**がある。
3. **タイムライン**は業界的にも **「全部を ReadModel に載せる」ことが標準ではない**。無計画に投影するとストレージ・無効化・整合が重い。
4. **通知**は既に `NotificationEventHandlerService` が `SnsPostCreatedEvent` 等を購読し `SnsNotificationRepository` に保存し、`NotificationQueryService` で読む。**ReadModel を二重に増やすと重複と整合コスト**が出やすい。

# Constraints

- **DDD**: ツールはアプリケーション層のユースケース呼び出しに留める。ReadModel の置き場所は **domain の read_model パッケージ vs 専用 query モデル**など、既存 Trade と揃えるか plan で固定する。
- **既存パターン**: `domain/trade/read_model/trade_read_model.py`、`application/trade/handlers/trade_event_handler.py`、`infrastructure/events/sns_event_handler_registry.py`（SNS は `NotificationEventHandlerService` が既に登録済み）。
- **タイムライン**: **読み取り時組み立て（Pull）＋ページング／カーソル**を基本とし、ReadModel には **メタデータ・カーソル・件数**など、サイズと更新頻度が見合う部分に寄せるのが無難（ベストプラクティス寄りの方針）。
- **通知**: 既存の **通知エンティティ＋クエリ**を正とし、ReadModel は **未読数バッジ用の集計キャッシュ**など、明確な追加価値がある場合に限定する、を原則とする。

# Code Context

| 領域 | モジュール・備考 |
|------|------------------|
| ReadModel 先行例 | `domain/trade/read_model/trade_read_model.py`（CQRS 的コメントあり） |
| イベントで ReadModel 更新 | `application/trade/handlers/trade_event_handler.py` |
| SNS 通知の生成（イベント） | `application/social/services/notification_event_handler_service.py` |
| SNS イベント登録 | `infrastructure/events/sns_event_handler_registry.py`（`SnsPostCreatedEvent` 等 → 通知ハンドラ） |
| タイムライン（Pull） | `application/social/services/post_query_service.py`（`get_home_timeline` 等） |
| 通知の読み取り | `application/social/services/notification_query_service.py` |
| SNS ドメインイベント | `domain/sns/event/post_event.py`, `sns_user_event.py` |
| LLM ツール | `application/llm/services/tool_catalog/`、`available_tools_provider`（本 idea では **新しい集約ツール**を想定） |

**調査メモ**: `domain/sns` および `application/social` に **ReadModel という名前の型は未導入**（2026-03-22 時点 grep）。通知は **Handler + Repository + Query** の流れが既にある。

# Open Questions（plan 前に解くとよいもの）

1. **「ページ」のスキーマ**: ホーム／通知／プロフィール／検索 等、**何画面分を第1弾の契約**に含めるか。
2. **ReadModel の永続化**: Trade のように **専用リポジトリ**に保存するか、**セッション／キャッシュのみ**か、**クエリの合成結果を DTO として返すだけ**（ReadModel 名義はアプリ層）か。
3. **タイムライン**: ページ取得 API の **1 リクエストに含める件数・カーソル**、および **内部で `PostQueryService` を呼ぶ**方針でよいか。
4. **通知 ReadModel の要否**: **未読数だけ**投影するか、**一覧は常に `NotificationQueryService`** に任せるか。
5. **既存の細かい read ツール**（`sns_home_timeline` 等）を **非推奨にするタイミング**と **互換期間**。

# Decision Snapshot

- **Proposal**:  
  - **仮想 SNS ページ**（画面単位の DTO スキーマ）を定義する。  
  - **ReadModel**（またはそれに相当する読み取り専用モデル）を導入し、**ページ取得は原則一括**（ツールも `sns_get_page` 型に集約しうる）。  
  - **更新**は **ドメインイベント + Handler** で行う。SNS には既に `NotificationEventHandlerService` があるため、**新規 Handler は ReadModel 用**とし、**通知本文の二重生成は避ける**（通知ページは既存 query を内部利用する等）。  
  - **タイムライン**は **Pull + ページング**を中核とし、ReadModel に載せるのは **カーソル・メタ・軽い集計**に限定するのが既定。

- **Options considered**:  
  - **A**: 細かい query ごとに LLM ツールを追加し続ける（現状の延長）。  
  - **B**: ページ DTO + 単一／少数の取得ツール + Handler 更新（本 idea）。  
  - **C**: タイムラインも含め **全面マテリアライズ**（大規模・高コスト）。

- **Selected option**: **B**（第一候補）。A はツール爆発、C はまず採らない。

- **Why this option now**: ユーザー要望として **「一般的に良い方法」**と **ツール削減**があり、リポジトリ内に **Trade ReadModel + 通知イベント Handler** の足場がある。

# Alignment Notes

- **Initial interpretation**: SNS に ReadModel が無いので **新設**する。タイムラインは **全文投影よりクエリ組み立て**を主とする。通知は **既存パイプラインを尊重**する。
- **User-confirmed intent**（会話より）:  
  - 作業は **大きめ**なので **別 feature** でよい → 本 idea がその入口。  
  - **同じ sns-trade feature の延長ではなく**、新 feature として **idea から**進める意向。  
  - 成功イメージ: **SNS モード ON で定義ツールが提供・利用可能**で十分ならよい。  
  - phase 分割は **実装が楽なら**でよい。

- **Cost or complexity concerns**:  
  - ページスキーマの設計負荷、ReadModel と既存 Query の **責務の線引き**、イベント不足時の **再構築（rebuild）** 要否。

- **Assumptions**:  
  - `sns-trade-login-tool-mode` で **モードとカタログ**は既に利用可能。  
  - SNS ドメインイベントは今後も ReadModel 更新の **トリガ**として使える。  
  - LLM 向けは **JSON 的に扱いやすいページ DTO** が価値が高い。

- **Reopen alignment if**:  
  - タイムラインを **全文 ReadModel 必須**という要件に変わったとき。  
  - 通知を **別 ReadModel テーブルに複製**することが必須になったとき。  
  - ReadModel を **ドメイン外（インフラのみ）**に閉じ込める方針に変わったとき。

# Promotion Criteria（`flow-plan` に進む前に）

- [ ] **ページ一覧**と **各ページのスキーマ草案**（必須フィールド）が合意されている  
- [ ] **ReadModel の永続方針**（Trade 型 vs 合成 DTO のみ）が決まっている  
- [ ] **タイムライン**を投影に載せる範囲（メタのみ / 先頭 N 件まで、等）が決まっている  
- [ ] **通知**を既存 query のまま組み込むか、集計だけ ReadModel かが決まっている  
- [ ] **既存 read ツール**との移行・非推奨ポリシーが一言でよいので決まっている  

# Promotion

- Next step: `flow-plan` で `forgeflow init-feature --slug sns-virtual-pages-readmodel`（または命名調整）し、`PLAN.md` に Handler 契約・ページ定義・ツール本数・テスト方針を書く。
