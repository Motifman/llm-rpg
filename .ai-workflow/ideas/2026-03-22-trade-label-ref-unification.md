---
id: feature-trade-label-ref-unification
title: 取引ツールの trade_label / trade_ref 二重経路の整理
slug: trade-label-ref-unification
status: idea
created_at: 2026-03-22
updated_at: 2026-03-22
source: flow-idea
branch: null
related_idea_file: .ai-workflow/features/trade-page-tool-gating/PROGRESS.md
---

# Goal

- **取引ミューテーション（受諾・辞退・キャンセル等）の対象指定を、長期的に一本化し、保守コストと分岐バグの余地を減らす。**
- 具体的には、**`trade_ref`（ページローカルな `r_trade_*`）を正とする経路に寄せ、表示用 `trade_label`（例: T1）だけに依存する互換パスを「縮退」（弱める／廃止候補として畳む）**できる状態を目指す。
- ユーザー価値: LLM ツールの契約が単純になり、プロンプト・テスト・実装の**二重管理**が減る。

# Success Signals

- **観測可能な成功**: `trade_accept` / `trade_cancel` / `trade_decline` まわりで、**推奨される入力が明確**（例: 仮想ページ有効時は `trade_ref` 必須、等）であり、テストがその契約を固定している。
- **技術的成功**: `guild_shop_trade_resolver` の `_resolve_trade_label` と `trade_executor` の ref/label 分岐が、**方針に沿って削減または明確に層別化**されている。
- **後方互換**: ~~従来環境~~ **不要**（ユーザー合意: より良いシステムへ即移行。旧ラベル専用環境はサポートしない）。

# Non-Goals（初回で必須にしない可能性があるもの）

- ~~即日の `trade_label` 完全削除~~ → **即時移行で `trade_ref` 一本化を優先**（合意済み方向）。
- **プロンプト文言の全面書き換え**だけを目的とした変更（必要なら follow-up）。
- Trade 以外の **label/ref 二重化**（Guild/Shop 等）の横展開（スコープ外になりうる）。

# Problem

1. **二重経路**: ツール定義上、同じ操作に対して **`trade_label` と `trade_ref` のどちらか一方**を受け付ける経路が並立している（`tool_catalog/trade.py` の記述どおり）。
2. **レビュー指摘の「問題」**: この並立により、**resolver・executor・テスト**に **label 解決と ref 解決の両方**が残り、将来 **`trade_ref` 一本**に寄せる設計意図（仮想ページ＋スナップショット）と**ずれる**。
3. **「縮退」の意味**: **trade_label 専用の互換パスを縮小して単純化する**こと。いまは意図的に残しているが、**未完了タスク**として PROGRESS に記載されている（`trade-page-tool-gating` Phase 6 scope delta）。

# `trade_ref` / `r_trade_*` の意味（実装）

- **形式**: `r_trade_{連番}`。連番はセッション状態の `ref_seq` をインクリメントし、**2 桁ゼロ埋め以上**で整形（`r_trade_01`, `r_trade_02` … 100 回を超えれば `r_trade_100` のように幅が伸びる）。
- **表すもの**: **グローバルな取引 ID ではない**。プレイヤーごとの **取引所仮想ページ session 内**で、そのスナップショット組み立て時に発行される **ページローカルなハンドル**。
- **正への対応**: `TradePageSessionService` が `ref_to_trade_id` に **`r_trade_*` → ドメインの `trade_id`（整数）** を保持し、`resolve_trade_ref` で解決する。
- **無効化**: `bump_snapshot_generation` が走ると ref マップが **全クリア**される。同じ画面を再取得するまで **古い `r_trade_*` は使えない**（スナップショットとツール引数の整合を取るための設計）。
- **`r_` の意図**: 「reference」の略で、**永続キーではなく現在の画面用の参照子**であることを示す命名。

# 設計思想：既存ツールカタログとの調和（採用方針）

本リポジトリの LLM ツールは、**同じ「ラベル」という語でも用途が違う**ため、次の **2 層**に分けて考える。取引の整理は **仮想ページ層に SNS と並べて揃える**ことが「既存との最も強い調和」になる。

## 層 1 — 視界・状況スナップショット型の `*_label`

- **対象**: 移動・世界インタラクション・会話・追跡・戦闘・ギルド・クエストなど。
- **意味**: プロンプトに載る「いま見えている一覧」の **短い記号**（例: P1, M1, I1, Q1, G1, K1）。
- **性質**: **ページ session の `r_*` とは別系統**。ワールド状態ビルダが付与する **表示用ラベル**。

## 層 2 — 仮想ページ（アプリ内画面）の page-local `*_ref`

- **対象**: **SNS 仮想ページ**、**取引所仮想ページ**（`sns_view_current_page` / `trade_view_current_page` 等で得る JSON）。
- **意味**: スナップショット JSON に含まれる **不透明トークン**（`r_post_*`, `r_user_*`, `r_reply_*`, `r_notif_*`, **`r_trade_*`**）。
- **性質**: **現在の画面・現在の世代**に紐づく。画面更新や `*_page_refresh` で **世代が変わると無効**になりうる（SNS の `sns_page_refresh` 説明と同趣旨）。
- **ミューテーション**: 対象行を指す引数は **`*_ref` のみ**が基本（SNS の `post_ref`, `reply_ref`, `trade_accept` の `trade_ref` 等）。**ここに `*_label` を並列させない**のが、SNS 側の並びと一致する。

## 層 3 — ドメイン安定 ID のオプション（ラベルと二択）

- **対象**: ショップの `listing_label` / **`listing_id`**、取引出品の `target_player_label` / **`target_player_id`**。
- **意味**: プロンプト上のラベルではなく、**永続的または一覧に依存しないキー**で指したいときの逃がし。
- **性質**: 仮想ページの `r_*` とは別。**「店の一覧の L1」ではなく在庫 ID で買う**ような用途。

## 取引への適用（この idea の結論に直結）

- **一覧上の行を操作する**受諾・辞退・キャンセル等: **`trade_ref` のみ**（SNS の行指向ツールと同じ思想）。`trade_label` は廃止してよい。
- **出品などワールド資源を指す** `inventory_item_label` / `target_player_label`: **層 1（および層 3 の id）のまま** — ショップ・世界ツールと揃え、仮想ページの `r_trade_*` と混同しない。

## 用語の使い分け（ドキュメント・ツール説明で統一したい）

- **page-local ref** / **スナップショットに含まれる ref**: SNS・取引の仮想ページ系で共通語彙にする。
- **ラベル**: 原則 **層 1** を指す語として使い、仮想ページ行の `r_*` とは対比して書く。

---

# 既存パターンに対する改善案（任意・優先度は別途）

互換性より **一貫した説明文・発見しやすさ**の改善として検討できるもの。

1. **ツール `description` のテンプレ統一**  
   SNS の `sns_open_ref` は `r_post_*`, `r_user_*` を列挙している。取引側も `trade_ref` を **`r_trade_*` と明示**し、同じ「括弧内プレフィックス列挙」スタイルに揃えると、カタログ横断で読みやすい。

2. **`trade_page_refresh` と SNS の `sns_page_refresh` の文言**  
   どちらも「ref の世代が変わることがある」旨を **同じ文面パターン**にすると、エージェント向けの期待動作が揃う。

3. **開発者向けの短い一覧（任意）**  
   `AGENTS.md` や `docs/` に **層 1 / 2 / 3 の表**を 1 枚置くと、新規ツール追加時の迷いが減る（本 idea のスコープ外でもよい）。

4. **SNS の汎用 `ref` vs 取引の `trade_ref`**  
   SNS はナビ用に `ref` 単独、`trade_accept` は意味のある引数名 `trade_ref`。**用途が違うので無理に引数名を統一しない**方がよい。調和は **「文字列の中身は `r_*` ファミリー」**で取る。

5. **ショップの将来**  
   もしショップにも「仮想ショップページ」が入るなら、層 2 と同様に `listing_ref` / `r_listing_*` のような **ページローカル ref** を検討する余地はあるが、**現状の listing_label + listing_id モデルと共存**させる設計が自然（本 idea では実施しない）。

# Constraints

- **後方互換**: **不要**（ユーザー合意）。仮想ページ＋`trade_ref` 前提に寄せる。
- **DDD**: ドメインに LLM 用ラベルを押し込めない。識別子の解決はアプリケーション層（executor / resolver）の責務として既存パターンに合わせる。
- **既存パターン**: `TradePageSessionService.issue_trade_ref` / `resolve_trade_ref`、`TradePageQueryService` がスナップショットに `trade_ref` を載せる流れ。

# Code Context

| 箇所 | 内容 |
|------|------|
| `application/llm/services/tool_catalog/trade.py` | `TRADE_ACCEPT_PARAMETERS` 等で `trade_label` / `trade_ref` 併記 |
| `application/llm/services/executors/trade_executor.py` | `trade_ref` 優先、`trade_label` フォールバック、エラー文言「trade_label または trade_ref」 |
| `application/llm/services/_argument_resolvers/guild_shop_trade_resolver.py` | `_resolve_trade_label` で ref または label |
| `application/trade/trade_virtual_pages/trade_page_query_service.py` | スナップショット行に `trade_ref` を付与 |
| `application/trade/trade_virtual_pages/trade_page_session_service.py` | ref の発行・解決 |

# Open Questions（まだ議論したい）

1. **LLM への説明の仕方**: ツール `description` とシステムプロンプトで、「**直近のスナップショットに載っている `trade_ref` をそのままコピーする**」「**画面更新後は再取得が必要**」をどこまで書くか。
2. **表示の二層化**: スナップショット JSON に **人間向け短いラベル（例: T1）を残し、ミューテーションは `trade_ref` のみ**にするか（LLM は ref をコピー、人間デバッグは T1 を見る）。完全に T1 を消すか。
3. **命名の変更要否**: `r_trade_*` を維持するか、**世代を含む**など誤用しにくい文字列にするか（実装・移行コストとトレードオフ）。

# Decision Snapshot

- **Proposal**:  
  - **目的**: `trade_label` 互換パスを段階的に縮退し、**`trade_ref` を正とする**運用・契約に寄せる。  
  - **手段候補**: 機能フラグまたは「仮想ページ有効時」の strict 化 → テスト固定 → 従来環境の縮小または配線完了後に label 引数の削除。

- **Options considered**:  
  - **A**: 現状維持（ドキュメントのみ）。コストは低いが二重経路は残る。  
  - **B**: 仮想ページ ON 時は `trade_ref` のみ受け付け、OFF 時のみ label（環境別契約）。  
  - **C**: 全クライアントに `trade_ref` を常に供給できるようインフラを揃えたうえで label を deprecate。

- **Selected option**: **C に近い即時移行**（従来環境非サポート・`trade_ref` 一本化）。細部は Open Questions で継続議論。

- **Why this option now**: `trade-page-tool-gating` 完了時点で **縮退は未実施**と明示されており、レビューで **技術的負債／設計のねじれ**として残ったため、別 idea として解消方針を立てる。

# Alignment Notes

- **Initial interpretation**:  
  - 「縮退」は **互換用の label 経路を畳んで単純化する**こと。  
  - 未実施理由は **仮想ページ未配線環境ではスナップショットに `trade_ref` がなく `trade_label` だけで動かす必要がある**ため。

- **User-confirmed intent**（更新）:  
  - **移行は即行いたい**。  
  - **従来環境のサポートは不要**。より良いシステムがあれば移行する。  
  - **`r_trade_*` の意味・LLM 向け分かりやすさと既存整合**は議論継続。

- **Cost or complexity concerns**:  
  - 配線のない環境での回帰、プロンプト・デモの更新コスト、テストフィクスチャの分岐整理。

- **Assumptions**:  
  - `trade_ref` は **ページ世代と無効化**の文脈で既に設計されている。  
  - label は **表示用の安定した短い別名**としてプロンプトに載りやすいが、**ページ遷移で意味がずれる**リスクがある（ref の方が厳密）。

- **Reopen alignment if**:  
  - **「従来環境」を長期サポートし続ける**方針に変わったとき（縮退の優先度が下がる）。  
  - **label だけの運用を正式仕様のまま残す**ことが決まったとき。  
  - 取引の識別子を **数値 ID を LLM に直接渡す**など、別の第三経路が追加されたとき。

# Promotion Criteria（`flow-plan` に進む前に）

- [ ] サポート対象環境（仮想ページ ON/OFF）と **移行スケジュール**の合意  
- [ ] 選んだオプション（B/C 等）に対する **具体的な API・ツール引数の変更案**  
- [ ] 回帰テストの **追加・削除範囲**の目安  
- [ ] プロンプト／ドキュメントの **更新責任**の有無

# Promotion

- Next step: 上記 Open Questions の回答後、`flow-plan` で feature 化するか、小さければ既存 feature の follow-up phase として PLAN に載せる。
