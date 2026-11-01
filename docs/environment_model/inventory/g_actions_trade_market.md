# 行為の洗い出し C: 商人との売買・人どうしの取引・掲示板の市場

- 読んだ版: origin/main `f231eb62a` (detached)
- パスは特記がなければ `src/ai_rpg_world/` からの相対。行番号はこの版のもの
- 【事実】はコードを読んで確かめたこと。【推測】は読んだ範囲からの見立てで、実行や試験では確かめていない
- 土台: `docs/environment_model/inventory/c_interactions_effects.md` (行動 1 件の流れ、効果の仕組み) と `d_world_state.md` (`pending_trade_offer` / `market_board` の保存)
- 略記
  - EXE = `application/llm/services/executors/spot_graph_tool_executor.py`
  - DEF = `application/llm/services/tool_catalog/spot_graph.py`
  - RES = `application/llm/services/_argument_resolvers/spot_graph_resolver.py`
  - DSP = `application/llm/services/world_llm_turn/tool_dispatch.py`
  - EXP = `application/llm/tool_exposure.py`
  - MER = `application/world_graph/spot_graph_merchant_trade_service.py`
  - PTS = `application/trade/services/player_trade_service.py`
  - MKT = `application/trade/services/market_service.py`
  - RCP = `application/observation/services/recipient_strategies/spot_graph_recipient_strategy.py`
  - FMT = `application/observation/services/formatters/_spot_graph_object_handler.py`
  - UI = `application/llm/services/spot_graph_ui_context_builder.py`
  - RT = `application/world_runtime/world_runtime.py`

---

## 0. 共通の土台

### 0-1. 露出 (どの世界に在るか)

【事実】3 つの系統は独立に宣言され、`ToolExposure.is_exposed` で出し分ける (EXP:46, 52, 62-72, 207-221)。

| 系統 | ツール | 宣言 (シナリオ) | 根拠 |
|---|---|---|---|
| 商人 | `buy_item` `sell_item` | `merchants: [...]` が 1 件以上 | EXP:201, `infrastructure/scenario/parse_economy.py:128-205` |
| 人どうしの取引 | `trade_offer` `trade_accept` `trade_decline` | `player_trade: {enabled, offer_expires_in_ticks}` (block があれば既定 on) | EXP:202, `infrastructure/scenario/parse_world.py:294-320` |
| 市場 | `market_*` 7 本 | `market: {board_spot, reach, order_expires_in_ticks, initial_orders}` | EXP:203, `parse_economy.py:621-` |

- `disabled_tools` で個別に落とせる (EXP:211)
- 去った主体 (departed) には出さない。`DEPARTED_TOOLS` は speak / travel_to / interact / listen / wait だけ (EXP:97, 270-272)。`execute_tool` は「今回のプロンプトで出していないツールは実行しない」を守る (DSP:1178-1194)
- 会議中は出ない (フェーズ固有ブロック、`_MEETING_ONLY_TOOLS` 以外は会議中に落ちる。EXP:300-305)
- 【事実】`tool_catalog/trade.py` にも `trade_offer` / `trade_accept` という同名の旧取引所ツールがある (`tool_constants.py:19, 91-92`)。登録は `register_default_tools(trade_enabled=True)` のときだけで (`tool_catalog/__init__.py:73-74`)、`trade_enabled=` を渡す呼び出しはリポジトリに無い。いまは衝突しない

### 0-2. 実行の経路

【事実】LLM の tool_call → `execute_tool` (DSP:1148) → 包み (`say_inline` の配信、gold 変化の計測) → ハンドラ → (resolver 対象なら) `SpotGraphArgumentResolver.resolve_args` → EXE の `_xxx` → application サービス。

- resolver を挟むのは `resolver_targets` に入ったツールだけ (DSP:324-375, 432-451)。**`buy_item` `sell_item` `trade_*` は入っている。`market_*` は入っていない** (§9 で詳述)
- 全ツールを `wrap_with_gold_change` で包み、その場の全員の gold の差を trace に残す (DSP:731-755)
- `say_inline` を持つツールは `wrap_with_say_inline` で包む。行動の成否によらず発言を出す (DSP:422-427, 453-454。仕組みは c_interactions_effects §1-A の 7)
- 担当 12 本はすべて `say_inline` と `inner_thought` を持つ (DEF:591-990)

### 0-3. 確定境界 (CommandScope)

【事実】3 つのサービスとも、外から呼ばれると `CommandScope` を開き、scope の repository に差し替えた複製で処理する (MER:251-259, 385-409 / PTS:234-245, 332-352 / MKT:1117-1177)。rollback に参加するもの:

| サービス | repository の transaction | 追加の rollback 参加者 | 根拠 |
|---|---|---|---|
| 商人 | あり | 提案 store (使わないが参加) | RT:6219-6234 |
| 人どうしの取引 | あり | 提案 store | RT:6202-6217, `infrastructure/unit_of_work/interaction_rollback_participants.py:366-386` |
| 市場 | あり | 板 store + 提案 store | RT:6235-6252, 同 :390-397 |

観測イベントは scope の `collect_all` に集め、確定後に配る (MER:61-68, PTS:48-55, MKT:72-79)。市場の trace (`MARKET_ACTIVITY`) は確定後に flush (MKT:82-97, 1117-1132)。

### 0-4. 状態の持ち主

| 状態 | 持ち主 | 保存 |
|---|---|---|
| gold | `PlayerStatusAggregate` (`pay_gold` / `earn_gold`) | repository |
| 所持品 | `PlayerInventoryAggregate` + `ItemAggregate` (付与は `grant_item_specs_to_inventory`、除去は `remove_items_of_specs_from_inventory`) | repository |
| 取引に出した品の凍結 | `PlayerInventoryAggregate` の予約 (`reserve_item`) | repository |
| 取引に出した gold の凍結 | 持たない。提案 store から導出 (`TradeFreezeService.available_gold`) | (提案 store) |
| 返事待ちの提案 | `InMemoryPendingTradeOfferStore` (application) が `PendingTradeOffer` (domain、frozen) を保持 | world snapshot `pending_trade_offer` |
| 板の注文・直近の約定 | `InMemoryMarketBoardStore` (application) が `MarketBoard` (domain、frozen) を保持 | world snapshot `market_board` |
| 商人 | `ScenarioMerchantDefinition` (シナリオの宣言、状態なし。在庫・所持金は無限) | なし |

根拠: `trade_freeze_service.py:1-25, 74-143`、`in_memory_pending_trade_offer_store.py`、`domain/trade/aggregate/pending_trade_offer.py`、`domain/trade/aggregate/market_board.py`、MER:194-200、`infrastructure/scenario/models.py:290-302`。

【事実】どの行為も `WorldGraphEffectService.apply_effects` (シナリオの効果の仕組み) を通らない。application サービスが集約のメソッドを直接呼んで世界を変える。

---

## 1. `buy_item` — 同じ場所の商人から品を買う

- **主体**: プレイヤー。去った主体には出ない (露出)。【事実】サービスは主体の生死・倒れを確かめない。居場所はグラフから引き、グラフに居なければ「同席していない」扱い (MER:436-442)。【未確認】倒れた人に手番が回るかはこの調査の範囲外
- **対象**: 商人と品。品名 (`item_label`) で引き、商人は省略可。resolver が、プロンプトに積んだ「その場の商人」の中から `sells` に品名が合うものを探す (RES:940-1035)。同じ品を複数の商人が売っていれば `merchant_label` (商人の名前) で絞る。商人は ID (`merchant_id`) に、品は `item_spec_id` に置き換わる
- **引数**: `item_label` (必須)、`quantity` (必須、1-99)、`merchant_label` (任意)。`say_inline` あり、`inner_thought` あり (DEF:591-625)
- **前提条件**
  - シナリオの宣言: `merchants` に商人がいること、その商人の `sells` にその品があること、価格 (`price`)
  - コードの決まり
    | 断る条件 | error_code | 層 | 根拠 |
    |---|---|---|---|
    | 品名が空 | `INVALID_TARGET_LABEL` | LLM 層 (resolver) | RES:958-963 |
    | 個数が整数でない / 1-99 の外 | `INVALID_ARGUMENT` | LLM 層 | RES:1040-1058 |
    | その場に商人が 0 人 | `MERCHANT_NOT_AT_SPOT` | LLM 層 | RES:985-989 |
    | `merchant_label` に合う商人がその場に居ない | `MERCHANT_NOT_AT_SPOT` | LLM 層 | RES:990-998 |
    | その品を売る商人がその場に居ない | `BUY_ITEM_NOT_SOLD_HERE` | LLM 層 | RES:1000-1009 |
    | 売る商人が複数で、指定が無い | `MERCHANT_AMBIGUOUS` | LLM 層 | RES:1010-1018 |
    | 商人が現在地に居ない (実行時に再確認) | `MERCHANT_NOT_AT_SPOT` | application | MER:423-434 |
    | 商人がその品を売っていない | `BUY_ITEM_NOT_SOLD_HERE` | application | MER:261-268 |
    | 使える gold < 単価 × 個数 (取引の提案に出して凍結中の gold を除く) | `BUY_ITEM_NOT_ENOUGH_GOLD` | application | MER:270-282, 444-449 |
    | 空きスロット < 個数 | `BUY_ITEM_INVENTORY_FULL` | application | MER:286-288, 466-470 |
    | (gold の不足を最後に守る) | `InsufficientGoldException` | domain (`pay_gold`) | c_interactions_effects §2 参照 |
- **世界の変化**: 行為者の gold が `単価 × 個数` 減る (`PlayerStatusAggregate.pay_gold`)。品が `個数` 個、新しい `ItemAggregate` として作られ所持品に入る。溢れは起きない前提で、起きたら `OverflowShouldNotHappenError` (MER:290-299, `application/world_graph/overflow_sinks.py:39-48`)。商人の側は何も変わらない (gold は世界から消える)
- **本人に返るもの**
  - 成功: `「{商人}から{品}を{n}つ買った ({合計}G)。所持金は {残}G。」`。trace_payload に `gold_delta` (負)、`gold_after`、`gold_change_source=merchant_buy`、商人名、品、個数、単価 (EXE:2096-2117)
  - 失敗: 例外の文 (不足額・扱う品の一覧・入る数を含む) と error_code、remediation (EXE:2087-2094、MER:86-175)
- **周りに見えるもの**
  - 成功: `PlayerTradedWithMerchantEvent` (MER:519-538) を同じ場所の他の人へ (行為者を除く。RCP:168-175, 429)。文は「{行為者}が{商人}から{品}を{n}つ買った。」。手番は起こさない (FMT:601-635)
  - 失敗: この行為からの観測は無い。【推測】一般の失敗観測 (`ActionFailedObservationEmitter`、本人向け) は通る
- **時間**: 1 回の呼び出しで完結。期限なし。tick の段は使わない
- **根拠**: EXE:2025-2117、MER:242-309、RES:940-1035

## 2. `sell_item` — 同じ場所の商人へ持ち物を売る

- **主体**: `buy_item` と同じ
- **対象**: 商人と品。resolver は商人の `buys` から品名で引く (RES:1000-1003)。品名は「所持アイテム」の表示名を書くよう説明しているが、resolver が突き合わせるのは**商人の買い取り表の品名** (RES:1001-1003)
- **引数**: `item_label`、`quantity` (1-99)、`merchant_label` (任意)。`say_inline` / `inner_thought` あり (DEF:628-659)
- **前提条件**
  - シナリオの宣言: 商人の `buys` にその品と価格
  - コードの決まり
    | 断る条件 | error_code | 層 | 根拠 |
    |---|---|---|---|
    | 品名・個数・商人の解決 (buy と同じ表) | 同上 (`SELL_ITEM_NOT_BOUGHT_HERE` など) | LLM 層 | RES:958-1018 |
    | 商人が現在地に居ない | `MERCHANT_NOT_AT_SPOT` | application | MER:329 |
    | 商人がその品を買い取らない | `SELL_ITEM_NOT_BOUGHT_HERE` | application | MER:330-337 |
    | 使える所持数 < 個数 (予約中 = 取引に出している品は数えない。文に凍結数を添える) | `SELL_ITEM_NOT_OWNED` | application | MER:339-352 |
    | 除去で全量を確保できない | `SELL_ITEM_NOT_OWNED` | application | MER:354-367 |
- **世界の変化**: 行為者の所持品から `個数` 個を除く (`remove_items_of_specs_from_inventory`)。gold が `単価 × 個数` 増える (`earn_gold`)。品は世界から消える (MER:354-373)
- **本人に返るもの**: 成功は `「{商人}に{品}を{n}つ売った ({合計}G)。所持金は {残}G。」`、`gold_change_source=merchant_sell` (EXE:2096-2117)。失敗は buy と同じ形
- **周りに見えるもの**: `PlayerTradedWithMerchantEvent` (direction=`merchant_sell`) を同じ場所の他の人へ。「{行為者}が{商人}に{品}を{n}つ売った。」 (FMT:617-618)
- **時間**: 1 回で完結
- **根拠**: EXE:2029-2117、MER:311-383

## 3. `trade_offer` — 同じ場所の相手へ交換を持ちかける

- **主体**: プレイヤー (持ちかける側、offerer)
- **対象**: 同じ場所の人。`target_player_label` (表示名、同名なら `#N`) を resolver が `target_player_id` に解決する。候補は今回のプロンプトに積んだ同席者 (`spot_graph_player`) (RES:771-782, 344-361)
- **引数** (DEF:708-736)
  - `target_player_label` (必須)
  - `gives` (必須): `{items: [{item_label, quantity}], gold}`。品は自分の所持品の表示名から `item_spec_id` に解決 (RES:820-853)。【事実】表示の `item_instance_id` 欄に実際は item_spec_id が入っている慣習をそのまま使う (UI:1300-1310)
  - `asks` (必須): 同じ形。品名は**解決せず名前のまま**通し、application が世界の品の宣言 (`item_specs.find_by_name`) で引く (RES:855-863, PTS:556-565)
  - `say_inline` / `inner_thought` あり
- **前提条件**
  - シナリオの宣言: `player_trade` block。提案の期限 `offer_expires_in_ticks` (無ければ既定 10)
  - コードの決まり
    | 断る条件 | error_code | 層 | 根拠 |
    |---|---|---|---|
    | 相手名が空 / 人として解決できない | `INVALID_TARGET_LABEL` / `INVALID_TARGET_KIND` | LLM 層 | RES:771-782 |
    | `gives` / `asks` の形が不正 (オブジェクトでない、items が配列でない、quantity が 1-99 の外、gold < 0) | `INVALID_ARGUMENT` / `INVALID_TARGET_LABEL` | LLM 層 | RES:865-907 |
    | 差し出す品が所持品として解決できない | `INVALID_TARGET_KIND` | LLM 層 | RES:826-846 |
    | 差し出すものが空 / 求めるものが空 | `INVALID_ARGUMENT` | LLM 層 | RES:786-795 |
    | gold が両側にある | `INVALID_ARGUMENT` | LLM 層 | RES:796-800 |
    | 相手と同じ場所に居ない (グラフで比べる。どちらかがグラフに居なければ同じ扱い) | `TRADE_PARTNER_NOT_HERE` | application | PTS:246, 430-438 |
    | 同じ相手へ同じ向きの提案が既に生きている | `TRADE_DUPLICATE_OFFER` | application (store) | PTS:247-248, store:67-69 |
    | 求める品の名前が世界に無い | `TRADE_UNKNOWN_ITEM` | application | PTS:556-565 |
    | 差し出す gold > 使える gold (他の提案に出して凍結中の額を除く) | `TRADE_GOLD_NOT_ENOUGH` | application | PTS:442-448 |
    | 差し出す品の数 > 使える所持数 (予約中を除く) | `TRADE_ITEM_NOT_OWNED` | application | PTS:449-461 |
    | 自分自身へ / 片側が空 / 両側に gold / 期限 ≦ 0 | `TRADE.OFFER_VALIDATION` (ドメイン例外。EXE は `PlayerTradeException` 以外を `exception_result` へ流す) | domain | `domain/trade/aggregate/pending_trade_offer.py:69-89` |
    | 片側に同じ品を 2 度書く / quantity ≦ 0 / gold < 0 | `TRADE.OFFER_VALIDATION` | domain (`TradeSide`) | `domain/trade/value_object/trade_side.py:25-47` |
- **世界の変化**
  - 提案 store に `PendingTradeOffer` (state=PENDING、`expires_at_tick = 現在 tick + 期限`) を足す (PTS:262-271)
  - 差し出す品を、offerer の所持品で予約する (`reserve_item`)。予約できる実体が足りなければ黙って途中でやめる契約で、事前の確認に頼る (`trade_freeze_service.py:95-116`)
  - 差し出す gold は動かない。以後、`available_gold` が提案 store の合計を引いて返すので、商人・市場・取引・`interact` の納金から使えなくなる (`trade_freeze_service.py:74-87`、c_interactions_effects §1-B 11-10)
- **本人に返るもの**: 成功は `「{相手}に取引を持ちかけた ({差し出す} ⇄ {求める})。差し出したものは返事があるまで使えない。」`。trace_payload に `trade_event=offered`、提案 ID、相手、両側の中身、`trade_expires_at_tick` (EXE:1900-1918)。失敗は例外の文と error_code (EXE:304-312 の `_trade_failure`)
- **周りに見えるもの**: `PlayerTradeOfferEvent(kind=offered)` を、行為者の居場所に居る全員へ (RCP:246-254, 432)。行為者本人には文を作らない。相手と第三者に「{行為者}が{相手}に取引を持ちかけた ({gives} ⇄ {asks})。」。**相手の手番だけを起こす** (FMT:353-421)。相手のプロンプトには「自分宛ての取引の申し出」節が出て、残り手番を示す (UI:1212-1231、RT:4945-4960)。【事実】offerer 側に「自分が出している提案」を出す節は無い (`list_from_offerer` を使う表示が無い)
- **時間**: 1 回で完結。期限つき (既定 10 tick、シナリオで上書き)。期限切れは tick の段 `TradeOfferExpiryStage` が片付ける (§6)
- **根拠**: EXE:1854-1918、PTS:222-274、RES:747-907

## 4. `trade_accept` — 自分宛ての提案を受け、その場で交換する

- **主体**: 提案の宛先 (target)
- **対象**: 自分宛ての提案。`offerer_player_label` (申し出た人の名前) で選ぶ。自分宛てが 1 件なら省略できる (RES:908-938, PTS:364-379)。提案 ID は引数に出ない
- **引数**: `offerer_player_label` (任意)。`say_inline` / `inner_thought` あり (DEF:739-759)
- **前提条件**
  | 断る条件 | error_code | 層 | 根拠 |
  |---|---|---|---|
  | 名前が文字列でない / 人として解決できない | `INVALID_TARGET_LABEL` / `INVALID_TARGET_KIND` | LLM 層 | RES:921-932 |
  | 自分宛ての提案が無い / 指定した人からの提案が無い | `TRADE_NO_OFFER_FOR_YOU` | application | PTS:369-376 |
  | 自分宛てが複数あって指定が無い | `TRADE_OFFER_AMBIGUOUS` | application | PTS:377-378 |
  | offerer と target が同じ場所に居ない | `TRADE_PARTNER_NOT_HERE` | application | PTS:290 |
  | 求められた gold / 品が足りない (自分が他の提案に出して凍結中のぶんを除く) | `TRADE_ASK_NOT_MET` (提案は残る) | application | PTS:291, 463-478 |
  | 自分の空き + 渡す品の数 < 受け取る品の数 | `TRADE_SELF_INVENTORY_FULL` (提案は残る) | application | PTS:480-508 |
  | offerer の空き + 渡す品の数 < 受け取る品の数 | `TRADE_PARTNER_INVENTORY_FULL` (提案は残る) | application | 同上 |
  | 既に返事のついた提案 | `TRADE.OFFER_STATE` | domain | `pending_trade_offer.py:124-129` |

  【事実】承諾の時点で期限を確かめない。store に残っている間は、期限の tick を過ぎていても受けられる (`_offer_for` は `list_for_target` をそのまま使う。PTS:364-379)。【推測】期限切れの段は tick に 1 回なので、同じ tick の中で段より先に手番が来れば、期限を過ぎた提案を受けられる
- **世界の変化** (PTS:294-306)
  1. offerer の予約を解く (`release_offer`)
  2. 両側の品を先に抜く (offerer の gives、target の asks)
  3. gold を動かす (gives.gold: offerer → target、asks.gold: target → offerer。`pay_gold` / `earn_gold`)
  4. 両側へ品を渡す (新しい `ItemAggregate` を作る。溢れは `refuse_overflow` で落ちる。RT:4712)
  5. 提案を ACCEPTED にして store から消す (`put` が PENDING 以外を持たない。store:39-48)
- **本人に返るもの**: 成功は `「{offerer}との取引が成立した ({asks} を渡し、{gives} を受け取った)。」`。`gold_affected_player_ids` に offerer を申告し、trace_payload に `trade_event=accepted`、`gold_change_source=trade_settle`、`gold_delta` (target から見た増減) (EXE:1904-1945)。失敗は例外の文
- **周りに見えるもの**: `PlayerTradeOfferEvent(kind=accepted)` を、行為者 (target) の居場所の全員へ。行為者を除き「{target}と{offerer}の取引が成立した ({gives} ⇄ {asks})。」。offerer にも同じ三人称の文が届く。手番は起こさない (FMT:378-381, 414-418)
- **時間**: 1 回で完結
- **根拠**: EXE:1904-1945、PTS:278-313

## 5. `trade_decline` — 自分宛ての提案を断る

- **主体**: 提案の宛先
- **対象・引数**: `trade_accept` と同じ (DEF:762-781、RES:908-938)
- **前提条件**
  | 断る条件 | error_code | 層 | 根拠 |
  |---|---|---|---|
  | 名前の解決 | (accept と同じ) | LLM 層 | RES:921-932 |
  | 自分宛ての提案が無い / 曖昧 | `TRADE_NO_OFFER_FOR_YOU` / `TRADE_OFFER_AMBIGUOUS` | application | PTS:364-379 |
  | 既に返事のついた提案 | `TRADE.OFFER_STATE` | domain | `pending_trade_offer.py:124-129` |

  【事実】**同じ場所に居ることを求めない** (accept は求める。PTS:315-330 と 290 の違い)
- **世界の変化**: offerer の予約を解き、提案を DECLINED にして store から消す (PTS:326-329)。gold の凍結は提案が消えるので自然に解ける
- **本人に返るもの**: `「持ちかけられた取引を断った。相手の品はまた使えるようになる。」`、`trade_event=declined` (EXE:1947-1974)
- **周りに見えるもの**: `PlayerTradeOfferEvent(kind=declined)` を、**行為者 (target) の居場所**の全員へ配り、formatter が当事者以外を落とす (FMT:370-371)。offerer には「{target}は持ちかけられた取引を断った。」。【推測】decline は同席を求めないので、offerer が別の場所に居ると、配信先 (target の居場所の全員) に入らず、断られたことが届かない
- **時間**: 1 回で完結
- **根拠**: EXE:1947-1974、PTS:315-330

## 6. (行為ではない) 提案の期限切れ

【事実】tick の段 `TradeOfferExpiryStage.run` が、期限を過ぎた提案を 1 件ずつ別の scope で、予約解除 → EXPIRED にして store から消す → `TradeOfferExpiredEvent` (`trade_offer_expiry_stage.py:67-117`)。ハンドラ `_observe_expired_trade_offer` が `PlayerTradeOfferEvent(kind=expired, entity_id=target)` を作り、**offerer の居場所**を出来事の場所にして配る (RT:4668-4697)。配信先はその場所の全員で、formatter が当事者以外を落とす。

【推測】target が offerer と別の場所に居ると、target には「流れた」が届かない。formatter と段の docstring は「target にも届ける」と書いている (`trade_offer_expiry_stage.py:16-23`、FMT:385-397) が、配信先の決め方 (RCP:246-254) がそれを保証していない。

---

## 7. 市場の掲示板 (`market_*`) の共通事項

- **板**: 1 世界に 1 枚。置き場所 `board_spot`、届く範囲 `reach` (`at_spot` 既定 / `global`)、注文の期限 `order_expires_in_ticks` (既定 40)、商人の初期注文 `initial_orders` をシナリオが宣言 (`domain/trade/value_object/market_reach.py`、MKT:64-65、RT:4715-4760)
- **預ける**: 出品した品は所持品から抜かれ、買い注文の gold は残高から引かれて板へ移る (凍結ではない) (MKT:1-10)
- **商人の注文**: 商人が売り手なら品は世界の外から来て gold は世界から消える。商人が買い手なら品は世界から消える (MKT:12-16, 1413-1441)
- **同席の確認**: `_require_at_board` が書き込む操作で見る。`reach=global` なら見ない。板の場所が None なら見ない (MKT:1502-1524)。`market_view` だけは executor が自分で見る (EXE:2190-2207)
- **対象の選び方**: 注文 ID は引数に出ない。品名と向きで自分の注文を指す。「同じ品目・同じ向きの自分の注文は 1 件まで」で一意になる (MKT:1526-1556)。品名は世界の品の宣言 (`item_specs.find_by_name`) で引く (MKT:1603-1607)
- **状態の持ち主**: `MarketBoard` (domain、frozen、更新は新しい板を返す) を `InMemoryMarketBoardStore` が保持。注文は `MarketOrder` (domain、frozen) (`domain/trade/aggregate/market_board.py:114-314`、`market_order.py:44-140`)
- **観測**: `MarketBoardActivityEvent` (MKT:1217-1271)。配信は「当事者だけ」 (RCP:180-209)。行為者本人には観測を出さず、`notify_entity_id` (相手) がいて行為者と違えばその人へ、期限切れなら持ち主へ。**居合わせた第三者には出品・値の付け直し・取り下げ・約定のどれも届かない**。FMT には第三者向けの文 (「{行為者}が掲示板に…出した」など) があるが、配信先に第三者が入らないので使われない (FMT:487-586)。【推測】第三者向けの文は、配信方針を変える前の名残
- **trace**: `MARKET_ACTIVITY` (kind=listed / settled / repriced / cancelled / expired / board_snapshot) (MKT:1179-1215)
- **プロンプト**: 板の在り処と自分の注文だけを常駐で出す。他人の値は `market_view` で 1 手番払って読む (UI:1177-1209)

## 8. `market_view` — 板を読む

- **主体**: プレイヤー
- **対象**: 板 (引数で指さない)
- **引数**: なし。`say_inline` / `inner_thought` あり (DEF:797-813)
- **前提条件**
  | 断る条件 | error_code | 層 | 根拠 |
  |---|---|---|---|
  | 市場サービスが未配線 | `NOT_WIRED` | LLM 層 | EXE:2121-2129 |
  | 板と同じ場所に居ない (`reach=global` なら不問。板の場所が無い / グラフ repository が無いときも断る) | `MARKET_BOARD_NOT_HERE` | LLM 層 (executor) | EXE:2172-2173, 2190-2207 |
- **世界の変化**: なし
- **本人に返るもの**: 板の本文 (`market_board_text`。品ごとの買える値・売れる値・件数・直近の約定、自分の注文と状態) と、trace_payload `market_event=viewed`、行数、自分の注文数 (EXE:2145-2188)
- **周りに見えるもの**: なし (EXE:2154-2160 の docstring がその判断を書いている)
- **時間**: 1 手番を使う (ツール説明 DEF:800-803 で明示)。期限なし
- **根拠**: EXE:2145-2207、`application/llm/services/market_board_text.py`

## 9. `market_list_item` — 品を板へ預けて売り注文を出す

- **主体**: プレイヤー
- **対象**: 自分の所持品の品目 (品名)
- **引数**: `item_label`、`quantity` (説明は「1 以上」、schema に minimum なし)、`unit_price` (同)。`say_inline` / `inner_thought` あり (DEF:816-841)
- **前提条件**
  | 断る条件 | error_code | 層 | 根拠 |
  |---|---|---|---|
  | 板と同じ場所に居ない | `MARKET_BOARD_NOT_HERE` | application | MKT:486, 1502-1524 |
  | 品名が世界に無い | `MARKET_UNKNOWN_ITEM` | application | MKT:487, 1603-1607 |
  | 同じ品の売り注文が既にある | `MARKET_DUPLICATE_ORDER` | application | MKT:488, 1526-1556 |
  | 同じ品の売り注文が引き取り待ちで残っている | `MARKET_ORDER_AWAITING_COLLECTION` | application | 同上 |
  | 使える所持数 < 個数 (取引で予約中の品は数えない) | `MARKET_ITEM_NOT_OWNED` | application | MKT:489, 1558-1570 |
  | 個数・単価・期限が 1 以上の整数でない | `TRADE.MARKET_ORDER_VALIDATION` | domain | `market_order.py:36-41, 60-94` |
  | 引数が欠ける / 整数に直せない | `exception_result` (TypeError / ValueError) | LLM 層 | EXE:2243-2251、`_resolver_helpers.py:74-84` |
- **世界の変化**: 行為者の所持品から `個数` 個を除く。板に SELL 注文 (`expires_at_tick = 現在 tick + 期限`) を足す (MKT:490-499)
- **本人に返るもの**: `「掲示板に{品}を{n}つ、1つ{単価}Gで出した。売れるまで手元からは無くなる。」`、trace_payload `market_event=listed`、注文 ID、期限 (EXE:2209-2253)
- **周りに見えるもの**: `MarketBoardActivityEvent(kind=listed)` を出すが、notify が無いので誰にも届かない (§7)
- **時間**: 1 回で完結。注文は期限つき (§14)
- **根拠**: EXE:2209-2253、MKT:465-517

## 10. `market_buy` — 板の安い出品から順に買う

- **主体**: プレイヤー
- **対象**: 品目 (品名)。どの注文を買うかは指定しない。価格の安い順 → 注文 ID の古い順 (MKT:731-748)
- **引数**: `item_label`、`quantity`。`say_inline` / `inner_thought` あり (DEF:844-865)
- **前提条件**
  | 断る条件 | error_code | 層 | 根拠 |
  |---|---|---|---|
  | 板と同じ場所に居ない | `MARKET_BOARD_NOT_HERE` | application | MKT:717 |
  | 品名が世界に無い | `MARKET_UNKNOWN_ITEM` | application | MKT:718 |
  | その品の売り注文が板に無い (引き取り待ちを除く) | `MARKET_NOTHING_TO_BUY` | application | MKT:722-728 |
  | 出ているのが自分の出品だけ | `MARKET_ONLY_YOUR_OWN` | application | MKT:745-750 |
  | 買える分の合計額 > 使える gold (取引の凍結を除く)。1 つも買わない | `MARKET_GOLD_NOT_ENOUGH` | application | MKT:762-767, 1572-1575, 1589-1594 |
  | 空き < 買える分の個数 | `MARKET_INVENTORY_FULL` | application | MKT:768, 1577-1580 |
  | (約定ごとに同じ確認をもう一度) | 同上 | application | MKT:641-646, 1355-1368 |
  | 自分の注文を受ける / 残数を超える / 引き取り待ち | `TRADE.MARKET_BOARD_STATE` / `TRADE.MARKET_ORDER_STATE` | domain | `market_board.py:257-287`、`market_order.py:113-125` |
- **世界の変化** (約定 1 件ごと。MKT:620-684, 1370-1392)
  - 板: 注文の残数を減らす (尽きたら外す)。品目ごとの直近の約定を差し替える
  - 買い手 (行為者): 品を受け取る (新しい `ItemAggregate`)、gold を払う
  - 売り手: プレイヤーなら gold が増える。商人なら gold は世界から消える
  - **板の在庫が足りなければ、あるだけ買う** (部分成立。MKT:752-760)
- **本人に返るもの**: `「掲示板から{品}を買った ({単価}G で {n} つ、…、計 {合計}G)。」`。部分なら「{求めた} つ求めたが、出ていたのは {買えた} つだった。」を足す。`gold_affected_player_ids` に相手のプレイヤー、trace_payload `market_event=bought`、約定の内訳 (EXE:2255-2313)
- **周りに見えるもの**: 約定ごとに `MarketBoardActivityEvent(kind=bought, side=sell, notify=売り手)`。売り手がプレイヤーで行為者と違えば、売り手へ届く。売り手が板に居なければ「掲示板に出していた{品}が{n}つ、1つ{単価}Gで売れた ({行為者}が買った)。」、板に居れば三人称の文 (FMT:530-554)。手番は起こさない
- **時間**: 1 回で完結
- **根拠**: EXE:2255-2313、MKT:620-782

## 11. `market_bid` — gold を板へ預けて買い注文を出す

- **主体**: プレイヤー
- **対象**: 品目 (品名、世界に在る品なら所持していなくてよい)
- **引数**: `item_label`、`quantity`、`unit_price`。`say_inline` / `inner_thought` あり (DEF:926-955)
- **前提条件**
  | 断る条件 | error_code | 層 | 根拠 |
  |---|---|---|---|
  | 板と同じ場所に居ない | `MARKET_BOARD_NOT_HERE` | application | MKT:540 |
  | 品名が世界に無い | `MARKET_UNKNOWN_ITEM` | application | MKT:541 |
  | 同じ品の買い注文が既にある / 引き取り待ち | `MARKET_DUPLICATE_ORDER` / `MARKET_ORDER_AWAITING_COLLECTION` | application | MKT:542 |
  | 個数 × 単価 > 使える gold (取引の凍結を除く) | `MARKET_GOLD_NOT_ENOUGH` | application | MKT:546 |
  | 個数・単価が 1 以上でない | `TRADE.MARKET_ORDER_VALIDATION` | domain | `market_order.py:60-94` |
- **世界の変化**: 行為者の gold を `個数 × 単価` 減らす (`pay_gold`)。板に BUY 注文を足す (MKT:547-556)
- **本人に返るもの**: `「掲示板に{品}を{n}つ、1つ{単価}Gで買うと出した (計 {合計}G を預けた)。」`、`market_event=bid_listed` (EXE:2315-2359)
- **周りに見えるもの**: `kind=listed, side=buy`。誰にも届かない (§7)
- **時間**: 1 回で完結。期限つき
- **根拠**: EXE:2315-2359、MKT:519-574

## 12. `market_sell` — 板の高い買い注文から順に売る

- **主体**: プレイヤー
- **対象**: 品目 (品名)。価格の高い順 → 古い順 (MKT:843-848)
- **引数**: `item_label`、`quantity`。`say_inline` / `inner_thought` あり (DEF:958-980)
- **前提条件**
  | 断る条件 | error_code | 層 | 根拠 |
  |---|---|---|---|
  | 板と同じ場所に居ない | `MARKET_BOARD_NOT_HERE` | application | MKT:834 |
  | 品名が世界に無い | `MARKET_UNKNOWN_ITEM` | application | MKT:835 |
  | その品の買い注文が無い | `MARKET_NOTHING_TO_SELL` | application | MKT:838-842 |
  | 自分の買い注文だけ | `MARKET_ONLY_YOUR_OWN_BID` | application | MKT:849-850 |
  | 使える所持数が 0 | `MARKET_ITEM_NOT_OWNED` | application | MKT:852-859 |
  | (約定ごとに所持数を確認) | `MARKET_ITEM_NOT_OWNED` | application | MKT:1366-1368 |
- **世界の変化** (約定ごと。MKT:1384-1391): 行為者の所持品から抜く。買い手がプレイヤーなら品を渡す (持ちきれなければ**板の足元の地面へ置き**、`MarketDeliveryLeftAtBoardEvent` を買い手へ。RT:4718-4727、FMT:423-456)。買い手が商人なら品は世界から消える。行為者は板に預けてあった gold を受け取る。**求めた数・持っている数・板が求める数の小さい方だけ売る** (部分成立。MKT:861-868)
- **本人に返るもの**: `「掲示板の買い注文へ{品}を売った (… 計 {合計}G)。」`、部分なら差を足す。`market_event=sold` (EXE:2361-2414)
- **周りに見えるもの**: `kind=bought, side=buy` を出す。【事実】`take_order` は向きによらず `notify=trade.seller` を渡す (MKT:656-665)。買い注文を受けたときの売り手は行為者本人なので、`notify == entity_id` となり、配信先が空になる (RCP:205-209)。**買い注文の持ち主には「売られた」が届かない**。FMT には持ち主向けの文「掲示板の買い注文に{品}が{n}つ…売られた」(FMT:537-544) があるが、届く経路が無い。【推測】品が足元に置かれた場合だけ `MarketDeliveryLeftAtBoardEvent` で知る。試験で確かめた記録は見つけていない (`tests` に該当の文で grep して 0 件)
- **時間**: 1 回で完結
- **根拠**: EXE:2361-2414、MKT:804-884, 620-684

## 13. `market_reprice` / `market_cancel` — 自分の注文の値を変える / 取り下げる

### `market_reprice`
- **対象**: 自分の注文。品名 + 向き (`side`) で指す
- **引数**: `item_label`、`side` (schema の enum は `["sell"]` だけ)、`new_unit_price`。`say_inline` / `inner_thought` あり (DEF:868-895)
- **前提条件**
  | 断る条件 | error_code | 層 | 根拠 |
  |---|---|---|---|
  | 板と同じ場所に居ない | `MARKET_BOARD_NOT_HERE` | application | MKT:907 |
  | 品名が世界に無い | `MARKET_UNKNOWN_ITEM` | application | MKT:908 |
  | その品・向きの自分の注文が無い (引き取り待ちは数えない) | `MARKET_NO_SUCH_ORDER` | application | MKT:909, 1475-1500 |
  | 買い注文で値を上げ、差額 > 使える gold | `MARKET_GOLD_NOT_ENOUGH` | application | MKT:910-918 |
  | 新しい単価が 1 以上でない / 引き取り待ち | `TRADE.MARKET_ORDER_VALIDATION` / `TRADE.MARKET_ORDER_STATE` | domain | `market_order.py:127-136` |
  | `side` が sell / buy 以外 | `exception_result` (ValueError) | LLM 層 | EXE:2449-2459 |
- **世界の変化**: 板の注文の単価だけを変える。期限・個数・時間優先の順位は変えない。買い注文なら差額を預け足す / 返す (MKT:910-921)
- **本人に返るもの**: `「{品}の値を 1 つ {旧}G から {新}G へ下げた/上げた。残り {n} つ、期限は変わらない。」`、`market_event=repriced` (EXE:2416-2467)。【事実】EXE は旧値を読むのに `find_my_order_price` を scope の外で先に呼ぶ (EXE:2435)
- **周りに見えるもの**: `kind=repriced`。誰にも届かない (§7)

### `market_cancel`
- **対象・引数**: `item_label`、`side` (enum `["sell"]`)。`say_inline` / `inner_thought` あり (DEF:898-923)
- **前提条件**
  | 断る条件 | error_code | 層 | 根拠 |
  |---|---|---|---|
  | 板と同じ場所に居ない | `MARKET_BOARD_NOT_HERE` | application | MKT:1019 |
  | 品名が世界に無い | `MARKET_UNKNOWN_ITEM` | application | MKT:1020 |
  | その品・向きの自分の注文が無い (**引き取り待ちは数えない**) | `MARKET_NO_SUCH_ORDER` | application | MKT:1021, 1475-1500 |
  | 売り注文で、空き < 残数 (取り下げごと断る) | `MARKET_INVENTORY_FULL` | application | MKT:988-995 |
  | 他人の注文 | `TRADE.MARKET_BOARD_STATE` | domain | `market_board.py:240-245` |
- **世界の変化**: 板から注文を外す。売り注文なら品を所持品へ戻し、買い注文なら預けた gold を返す (MKT:951-997, 1394-1411)
- **本人に返るもの**: `「{品}の出品を取り下げ、{n}つを引き取った。」`、`market_event=cancelled` (EXE:2469-2509)。【事実】買い注文でも同じ文 (gold が戻ったことを言わない)
- **周りに見えるもの**: `kind=cancelled`。誰にも届かない
- **時間**: どちらも 1 回で完結。【事実】`current_tick` を受け取らない (EXE:2435-2445, 2488-2491)

## 14. (行為ではない) 注文の期限切れ

【事実】tick の段 `MarketOrderExpiryStage` が、期限を過ぎた注文を 1 件ずつ別の scope で処理する。預かり物を返せれば板から外し (`expired_returned`)、売り注文で空きが足りなければ板に「引き取り待ち」として残す (`expired_awaiting`) (MKT:1024-1098)。持ち主へ観測を届ける (RCP:200-204、FMT:571-580)。引き取り待ちの観測文は「空きを作ってから取り下げれば引き取れる。」と言う (FMT:576-579)。

---

## 15. 担当の行為をまたいで見えたこと

### 同じことを違う形でやっている

- 【事実】**同席の確認が 3 通り**。商人は resolver (プロンプトの対象表) と application (グラフ) の 2 段 (RES:985-998、MER:423-434)。取引は application だけで、両者の居場所をグラフで比べる (PTS:430-438)。市場は application の `_require_at_board` だが、`market_view` だけ executor の `_is_at_the_board` (EXE:2190-2207) で、板の場所や repository が無いときの扱いが逆 (application は通す、executor は断る)
- 【事実】**空きスロットの数え方が 2 通り**。商人は `iter_slots` で空のスロットを数える (MER:466-470)。取引と市場は `get_inventory_summary()["empty_inventory_slots"]` (PTS:510-514、MKT:1582-1587)
- 【事実】**品名から品を引く方法が 3 通り**。商人は resolver が商人の価格表の品名と突き合わせる (RES:999-1003)。取引の差し出す側は所持品の表示から、求める側は `item_specs.find_by_name` (RES:820-863、PTS:556-565)。市場はすべて `find_by_name` (MKT:1603-1607)
- 【事実】**ID の採番と寿命**。提案は store が `next_offer_id` で払い出し、返事がつくと store から消える (store:32-48)。注文も store が払い出す (MKT:1340)。どちらも domain の集約は frozen で「新しい値を返す」形。CLAUDE.md の「ID を持つ集約を frozen で作らない」とは逆の形
- 【事実】**「二重を弾く」決まりが domain に無い**。同じ相手への二重提案 (store:67-69 を PTS:247 が使う)、同じ品目・同じ向きの注文は 1 件まで (MKT:1526-1556) は application が守る。`MarketBoard` は ID の重複しか見ない (`market_board.py:234-238`)

### 行為によって扱いが食い違う

- 【事実】**部分成立の扱い**。商人は全量か 0 (MER:3-9)。取引は全量か 0。市場は板の在庫・所持数が足りなければ部分成立し、gold 不足だけは 0 (MKT:686-705, 804-822)。ツールの説明はそれぞれ正しく書いている
- 【事実】**同席の要否**。`trade_accept` は同席を求め、`trade_decline` は求めない (PTS:290 と 315-330)
- 【事実】**市場の引数は resolver を通らない**。`market_*` は `resolver_targets` に入っていない (DSP:324-375) ので、RES の `_resolve_market` (RES:689-745。品名の空白除去、整数化、1 以上の確認、side の確認) は実行経路で呼ばれない。executor は `str(args.get("item_label"))` と `required_int_arg` (`int()` するだけ) で読む (EXE:2241-2246 など)。【推測】品名が空・None なら `MARKET_UNKNOWN_ITEM` (「None という品はありません」)、`quantity` が 0 以下のとき、出品と買い注文は domain の検証で断られるが、`market_buy` / `market_sell` は計画が空のまま約定 0 件で**成功**として返る (MKT:752-782, 861-884 で個数の下限を見ていない)。schema にも `minimum` が無い (DEF:832, 860, 944, 972)。商人の `quantity` は schema で 1-99 (DEF:607-611)
- 【事実】**買い注文の値の付け直し・取り下げがツールの schema で塞がれている**。`market_reprice` / `market_cancel` の `side` は enum `["sell"]` (DEF:884, 915)。service は `buy` を扱える (MKT:910-918, 1394-1404) し、`market_bid` の説明は「値を変えたいときは market_reprice を使う」と案内する (DEF:934)。【推測】provider が enum を守らせれば、出した買い注文は期限まで動かせない
- 【事実】**引き取り待ちの注文を引き取る経路が無い**。`market_cancel` → `cancel_by` → `_my_order` が引き取り待ちを除外する (MKT:1475-1500) ので `MARKET_NO_SUCH_ORDER` になる。一方、期限切れの観測は「空きを作ってから取り下げれば引き取れる」(FMT:576-579)、同じ品の出し直しは「先にそれを引き取ってから」(MKT:142-148) と案内する。`cancel_order` (注文 ID で指す) はツールから呼ばれない。【推測】引き取り待ちになった品は、引き取り待ちを解く処理が見当たらないので、run の終わりまで板に残り、同じ品目の同じ向きの注文も出せなくなる
- 【事実】**観測の配り方が系統ごとに違う**。商人は同じ場所の第三者へ (RCP:429)。取引は出来事の場所の全員へ (RCP:432)。市場は当事者だけ (RCP:433)。市場の第三者向けの文 (FMT:497-524, 556-568) は届く経路が無い
- 【事実】**買い注文が埋まったことが持ち主に届かない** (§12)。売り注文が埋まったことは届く (§10)
- 【推測】**断られた・流れたことが当事者に届かないことがある**。decline (§5) と期限切れ (§6) は「出来事の場所に居る全員」から当事者を選ぶので、当事者が別の場所に居ると漏れる
- 【事実】**所持金の行がプロンプトに出るのは商人を宣言した世界だけ** (`economy_declared = bool(merchants)`。`application/world_graph/spot_graph_current_state_builder.py:1520-1522`、UI:1234-1245)。商人の居ない `offering_race_v1` / `v2` は gold と取引・市場を使う世界だが、所持金の行が出ない。【推測】本人は取引の結果文 (例: buy_item の「所持金は {残}G」) からしか残高を知れない。市場と取引の結果文は残高を言わない
- 【事実】**取引に出している提案は、offerer のプロンプトに出ない**。出るのは自分宛ての申し出だけ (UI:1212-1231)。凍結した品・gold は、使おうとして断られたときの文で知る (MER:136, 174、EXE:325-337)

### シナリオの効果の仕組みを使わずに世界を変えている

- 【事実】12 本すべてが `WorldGraphEffectService.apply_effects` を通らない。gold と所持品の増減は application サービスが集約を直接呼ぶ (MER:290-299, 354-373、PTS:516-547、MKT:1370-1475)
- 【事実】`interact` の `DEPOSIT_GOLD_TO_OBJECT` / `GIVE_ITEM` 効果と同じ「gold を払う / 品を付与する」を、別の helper の組み合わせで再実装している。凍結中の gold を除く確認は 4 か所 (`interact`、商人、取引、市場) がそれぞれ `TradeFreezeService` を呼ぶ (c_interactions_effects §1-B 11-10、MER:444-449、PTS:442-448、MKT:1589-1594)
- 【事実】観測イベント (`PlayerTradedWithMerchantEvent` / `PlayerTradeOfferEvent` / `MarketBoardActivityEvent`) は `domain/world_graph/event/spot_graph_event.py:362-440` にあり、`aggregate_type="SpotGraphAggregate"` で application が組み立てる。状態を変えた集約 (提案・板・所持金) が出すドメインイベントではない
- 【事実】商人は宣言だけで状態を持たない。在庫と gold は無限 (MER:17-19, 194-200)

### 時間

- 【事実】12 本すべて 1 回の呼び出しで完結する同期処理。待ち時間 (cooldown) は無い
- 【事実】期限を持つのは提案 (既定 10、`player_trade.offer_expires_in_ticks`) と注文 (既定 40、`market.order_expires_in_ticks`、商人の初期注文は注文ごとに上書き可)。どちらも tick の段で片付ける (b_world_tick の段 13 / 14)
- 【事実】期限の起点は executor の `_current_tick_value` (時刻の提供者 → runtime の順に読み、読めなければ警告して 0) (EXE:1976-2016)

---

## 16. 19 本のシナリオのうち、これらの行為を出しているもの

`data/scenarios/*.json` を読んで、宣言と `disabled_tools` から決めた (露出の規則は §0-1)。

| シナリオ | 商人 | 取引 (期限) | 市場 (板の場所, 期限, 初期注文) | 落としているツール | 出るツール |
|---|---|---|---|---|---|
| `market_town_v1` | 1 | なし | なし | なし | `buy_item` `sell_item` |
| `market_town_v2_trade` | 1 | あり (24) | なし | なし | `buy_item` `sell_item` `trade_*` |
| `market_town_v3_board` | 1 | あり (24) | `market_square`, 24, 3 件 | `buy_item` `trade_offer` `trade_accept` `trade_decline` | `sell_item` `market_*` 7 本 |
| `offering_race_v1` | 0 | あり (6) | `festival_square`, 24, 0 件 | なし | `trade_*` `market_*` 7 本 |
| `offering_race_v2` | 0 | あり (6) | `festival_square`, 24, 0 件 | なし | `trade_*` `market_*` 7 本 |
| 残り 14 本 | 0 | なし | なし | — | 出ない |

- どのシナリオも `market.reach` を書いていないので、すべて `at_spot` (板の前に居ないと使えない)
- 【事実】`offering_race_v1` / `v2` は商人が居ないので、所持金の行がプロンプトに出ない (§15)
