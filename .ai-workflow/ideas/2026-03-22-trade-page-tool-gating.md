---
id: feature-trade-page-tool-gating
title: Trade 独立モード・取引所UI（検索・一覧・自分の取引）と LLM 向け表示
slug: trade-page-tool-gating
status: idea
created_at: 2026-03-22
updated_at: 2026-03-22
source: flow-idea
branch: null
related_idea_file: .ai-workflow/ideas/2026-03-21-sns-trade-login-tool-mode.md
---

# Goal

- **Trade を SNS から切り離し**、**Trade モード起動時**にだけ取引系ツール（＋取引所の read）が使えるようにする（SNS の「アプリを開く」と同型のメタファ）。
- **MMO RPG の取引所**として、**出品一覧の閲覧・検索（欲しいアイテム）・自分の取引の閲覧**ができ、**LLM エージェントが読みやすいスナップショット／ページ**で表示できるようにする。
- **ゲーム内「アプリ」モードの相互排他**: **SNS モード中は Trade モードになれない**、**Trade モード中は SNS モードになれない**。将来 **別モードが増えても同様に、常に高々 1 つだけアクティブ**とする。

# Success Signals

- **`trade_enabled` だけで** Trade 用ツールがカタログに載り、**`sns_enabled` に依存しない**（実装後の観測）。
- **Trade モード ON** のときだけ、出品・受諾・キャンセル等のミューテーションと、**取引所の read ツール**が整合して露出する。
- **排他ルール**が一貫している: SNS モードと Trade モードが **同時に真にならない**こと（テストまたはセッション不変条件で保証）。将来モード追加時も **同じ枠組み**で表現できる。
- **検索・出品リスト・自分の取引**の少なくとも一方が、**ページまたはスナップショット経由**で LLM に渡せることが、テストまたは契約で示せる。

# Non-Goals（この idea の段階で必須にしない／別 plan に分けうるもの）

- **SNS ドメインの変更**（タイムライン等）。Trade は **別セッション／別 page kind** で独立させる。
- **実装の詳細コミット**（本ファイルは方向性の確定まで。具体 PLAN は `flow-plan` 側）。

# Problem

1. 現状コードでは **Trade ツールは `sns_enabled` と同時にしかレジストリへ登録されない**ため、SNS を無効にすると Trade も消える。意図は歴史的に **「ゲーム内 SNS アプリの中の取引」**として束ねたことにあるが、**プロダクト上は別物にしたい**という要件と矛盾する。
2. Trade ツールは **4 本のミューテーション中心**で、**取引所の一覧・検索・自分の取引向けの read ツール／仮想ページ**が未整備。`available_trades` サマリだけでは **市場全体の探索**や **MMO 取引所の画面感**が足りない。

# Constraints

- **現状の登録条件**（変更対象）: `register_default_tools` で `if trade_enabled and sns_enabled:` のときだけ `get_trade_specs()`。これを **`trade_enabled` のみ**（または `trade_enabled and not 依存 sns`）に変える必要がある。
- **現状のモードゲート**（変更対象）: `trade.py` の全ツールが `SnsModeRequiredAvailabilityResolver`。**`is_trade_mode_active`（仮称）**のような **Trade 専用フラグ**に差し替え、`sns_enter` とは独立させる。
- **Read / ページ**: SNS の `sns_virtual_page_kind` / `SnsPageQueryService` と **対称ではなく独立**。`PlayerCurrentStateDto` に **trade 用の page kind・スナップショット**を載せるか、別 DTO 経路で載せるかは plan で固定する。
- **モードの相互排他（必須）**: **SNS モード ON ⇔ Trade モード ON は両立しない**。将来のモードも含め、**いずれか 1 つの「アクティブアプリ」だけ**を表現するのが望ましい。実装案としては **`is_sns_mode_active` / `is_trade_mode_active` を独立した bool のまま足し続ける**のではなく、**単一の判別子**（例: `active_game_app: Literal["none","sns","trade",...]` または enum）に **段階的に寄せる**と、不変条件がコードで保ちやすい。
- **ドメイン**: 既存の `PersonalTradeQueryService` / `TradeReadModel` / 取引リポジトリとの接続を調査し、**検索・市場一覧**がクエリで足りるか、ReadModel 拡張が要るかを切り分ける。

# Code Context（現状の根拠）

| 項目 | 内容 |
|------|------|
| 登録が SNS 必須な理由 | `application/llm/services/tool_catalog/__init__.py` のコメント・条件: **Trade は SNS カタログとセットで登録**という実装方針がコードに書かれている（プロダクト要件ではなく **配線上の結合**）。 |
| Trade 4 本 | `trade_offer` / `trade_accept` / `trade_cancel` / `trade_decline` — `SnsModeRequiredAvailabilityResolver` 内包。 |
| プレイヤー状態 | `is_sns_mode_active`, `sns_virtual_page_kind`, `available_trades` 等。**Trade 専用モード用フィールドは未導入**。 |

# Open Questions（plan 前に詰めるとよいもの）

1. **Trade モードの入り口**: `trade_enter` / `trade_exit` を SNS の `sns_enter` / `sns_logout` と同型にするか、**1 ツールで toggle** か。
2. **「市場」データの範囲**: ワールド全体の出品一覧か、**ロケーション／ギルド制限**があるか（ドメインルール）。
3. **検索の単位**: アイテム名・カテゴリ・プレイヤー名・価格帯のどれを第 1 弾にするか。
4. **`sns-trade-login-tool-mode` 完了範囲**との関係: 既存の「SNS 内取引」挙動を **互換維持するか、移行で置き換えるか**。
5. **排他の実装位置**: `sns_enter` / `trade_enter` で **他モードを自動終了**するか、**明示ログアウト必須**か（UX）。

# Decision Snapshot

- **Proposal**:
  - **SNS と Trade をプロダクト上は完全分離**。実装としては **（1）`register_default_tools` で `trade_enabled` のみで Trade カタログ登録（2）Trade ツールのゲートを `SnsModeRequired` から `TradeModeRequired`（仮）へ（3）取引所 read 用に仮想ページまたはスナップショット＋ナビツールを追加（4）検索・一覧・マイ取引を画面／クエリで供給**を第一案とする。
  - **モード排他**: **SNS アクティブ時は Trade に入れない／Trade アクティブ時は SNS に入れない**。将来モードも **同じ排他グループ**に乗せる。**単一のアクティブ種別**で表現する設計を plan で推奨。
  - **LLM 向け表示**は SNS の `view_current_page` 型と同じ思想で、**JSON スナップショット＋ page-local ref** を Trade 側にも持たせ、**MMO 取引所の1画面**として読める形を目指す。

- **Options considered**:
  - **A**: Trade 完全独立モード + 仮想取引所ページ + 検索・一覧・マイ取引 read（**ユーザー意向に合致**）。
  - **B**: 現状のまま SNS 内取引のみ（却下方向）。

- **Selected option**: **A（ユーザー確認済み）** — Trade は SNS と別物。**Trade モード起動時**に利用可能にし、**検索・出品リスト・欲しいアイテムの探索・自分の取引・取引所ページの LLM 可読表示**を目標とする。

- **Why this option now**: プロダクト上の意図が明確になったため、**Non-Goal にしていた「SNS からの切り離し」は Goal に昇格**し、実装は **register / resolver / session / read model** の順で plan に落とせる。

# Alignment Notes

- **Initial interpretation**: SNS のページ遷移パターンを Trade に当てはめられるか、＋ Trade ツールの整理。
- **User-confirmed intent**:
  - **SNS なし単体で Trade を登録したい**理由は、**SNS と完全に別物**にしたいから。現状の **`trade_enabled && sns_enabled` は「実装上 SNS とセットで載せた」だけ**であり、**必須のビジネスルールではない**。
  - **Trade モードを起動したとき**に取引ツールを使いたい。
  - **検索・出品リストの閲覧**、**欲しいアイテムの出品を探す**、**自分の取引の閲覧**。
  - **MMO RPG の取引所ページ**を、**LLM エージェントにとって見やすく**表示したい。
  - **SNS モードと Trade モードは同時に ON にしない（相互排他）**。将来、**ほかのモードが増えても同様に、常にどれか 1 つだけ**。

- **Cost or complexity concerns**:
  - **モードフラグ**を SNS と独立させると、`PlayerCurrentStateDto` ビルダー・セッションサービス・wiring が **SNS と並列に増える**（パターンは既存 `SnsModeSessionService` を参照可能）。
  - **市場一覧・検索**はドメイン／クエリ層の能力に依存。**既存クエリだけでは足りない**場合は ReadModel や新規クエリ API が必要。

- **Assumptions**:
  - **仮定1**: `trade_enter` 系は **ゲーム内「取引所アプリを開く」メタファ**でよい（実認証ではない）。SNS の `sns_enter` と対称。
  - **仮定2**: ミューテーション 4 本は **Trade モード ON** かつ **画面種別（あれば）** でさらに絞る余地は plan で決める。
  - **仮定3（確定）**: **SNS と Trade は同時アクティブにしない**。将来モードも **単一スロット**のモデルで揃える。

- **Reopen alignment if**:
  - **検索・一覧のデータ規模**（全件スキャン禁止など）でインフラ制約が出たとき。
  - **「アプリを切り替えたら前の仮想ページ状態を復元する」**など、排他に加えて **セッション永続**の要件が重くなったとき。

# Promotion Criteria

- **Trade モード**のセッション責務（どのサービスが真実を持つか）が決まっている。
- **アクティブモードの単一性**（enum / 単一フィールド）と、**enter 時の他モード解除**の仕様が決まっている。
- **画面／ページ一覧**（例: マーケット一覧、検索結果、出品詳細、マイ取引）の第 1 弾スコープが決まっている。
- **Read の供給元**（既存クエリ拡張 vs TradeReadModel 拡張）が決まっている。
