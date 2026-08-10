# 負債マップ: 前提条件・対象解決・死亡/ダウン状態判定

作成: 2026-07-25 (v4coop_reasonfirst_002 分析の後続)。行動の前提条件(precondition)を
「評価・提示・実行」する仕組みの保守性調査(read-only)の記録。**将来のリファクタ、特に
別エージェントが進める interact ツール統合(attack を interact に畳む / プレイヤー名の横に
可能アクションを出す)の設計土台**として残す。

## 要約

負債は **中〜高**。「行動の前提条件解決が保守しづらい」という直感は事実に裏付けられる。ただし
「全くリファクタしていない」わけではなく、直近に θ1〜θ5(runtime_manager と executor の 2 経路
統合)は入っている。手が付いていないのは **precondition 判定の重複 / executor 肥大 / 死亡・
ダウン判定の分散** の軸。

## (A) 前提条件の評価が 4〜5 系統に独立実装されている

enum 名が同じ(`HAS_ITEM` / `OBJECT_STATE` / `WEATHER_IS` / `FLAG_SET`)なので「同じロジック」
と錯覚するが、実装は別々で 1 箇所直しても他が追従しない:

1. `domain/world_graph/service/spot_interaction_service.py:119-320` `_evaluate_condition` —
   **実行時の唯一の権威実装**(15 種類超)。ここは健全・重複なし。
2. `application/world_graph/spot_graph_current_state_builder.py:54-177` — プロンプト提示側が
   OBJECT_STATE / TIME_OF_DAY / WEATHER の **4 種だけ独自再実装**。**`OBJECT_STOCK_AT_LEAST`
   (= #343 で対策した"枯渇"条件の主力)がヒント生成から漏れている** → 備蓄切れの操作が理由
   ヒント無しで表示され続ける(#343 の再発条件が残る)。
3. `application/llm/services/executors/interact_helpers.py:60-84` `list_object_interactions`
   — remediation が precondition 無視で全列挙(#802 で表示集合の不整合自体は解消済みだが判定
   ロジックは別のまま)。
4. `domain/world_graph/service/spot_exploration_service.py:56-75` `_meets_condition` —
   discovery 用に **別 enum(`DiscoveryConditionTypeEnum`)・別評価器**。
5. `application/world_graph/scenario_condition_evaluator.py` — **第 3 の条件体系**
   (`ScenarioEventCondition`)で同名種別を再々実装(HAS_ITEM は全プレイヤー走査など意味も別)。

## (B) 対象解決・死亡/ダウン判定がバラバラ

- `application/llm/services/_argument_resolvers/spot_graph_resolver.py` (952行) の各 resolve は
  ラベル→id 解決のみで **is_dead/is_down を一切見ない**(grep 0 件)。
- 有効性チェックが行動ごとに **3 パターン混在**:
  - `attack`: `spot_attack_orchestrator.py:308` → ドメインサービス `try_attack` に委譲(**good**)。
  - `tend_to_player`: `spot_graph_tool_executor.py:1436-1474` に **executor 内ベタ書き**。
  - `give_item`(`spot_graph_item_transfer_service.py`)/ `whisper`(`speech_executor.py`)は
    **is_dead/is_down チェック無し**。
- **共通の「行動可能性」抽象が無い**。`is_dead`/`is_down` を最低 4 箇所で個別に読み出し
  (executor tend / attack ドメイン層 / ui_context_builder 表示 / current_state_builder DTO)。
- **確定バグ**: `application/llm/services/spot_graph_ui_context_builder.py:640` の
  `give_item_suffix` が is_dead/is_down 分岐の**外**で無条件付与 → 死体に「give_item で渡せる
  相手」表示。かつ give_item に死亡者ガードもテストも無く、**死体にアイテムを渡せてしまう**
  (静かな失敗リスク)。

## (C) executor 肥大

`application/llm/services/executors/spot_graph_tool_executor.py` は **1515 行**(目安 800 の約 2 倍)、
`_give_item` 140 行 / `_use_item` 164 行 / `_tend_to_player` 129 行(目安 50 超)。13 ツールが 1 クラス
同居し、新ツール追加時に「ドメイン委譲すべきか executor 内で書くか」の基準が無い。

## リファクタ計画(ROI 順)

| # | 内容 | コスト | 状態 |
|---|---|---|---|
| 1 | give_item/whisper に死亡/ダウンガード + affordance を is_dead/is_down 分岐の内側へ | 低 | **対応中(案A)** |
| 3 | `OBJECT_STOCK_AT_LEAST` の枯渇ヒントを builder に追加(#343 再発穴埋め) | 中 | **対応中** |
| 2 | `validate_actionable_target(actor, target, require_same_spot)` 共通純粋関数へ括り出し(Strategy 化はしない) | 中 | **保留** — interact 統合と一体設計(別エージェント) |
| 4 | executor を 3〜4 ファイルに分割(travel/explore・item・combat・sensory) | 高 | **保留** — 1/2 後、YAGNI |
| 5 | 4 系統の条件エンジン統合 | — | **非推奨**(文脈が違い過剰設計。各体系トップに「別系統」docstring 注記で十分) |

## interact ツール統合との関係(担当: nagi。設計 doc = #816 interpersonal_interaction_design.md)

nagi が「interact 1本 + target_label 1つ(object も player も)/ 行末に可能アクション + 条件ヒント」
の統一 affordance モデルを実装中。**2026-07-25 の nagi との合意で以下が確定:**

- **【訂正】attack は interact に畳まない**(明示的な非目標)。attack は spot_attack_orchestrator の
  別経路(視認・反撃・pack反応)のまま。「殴る」はエンジン組み込みでなくシナリオ定義の対人行為
  という設計。モンスター行に attack を出すのは**表示規約だけ揃える**(ツールは attack のまま)。
- **対象有効性は 2 層**: (1) 名前→対象の解決 `resolve_target`(種別のみ、状態を見ない。#821 で統一)、
  (2) 状態の有効性 = 前提条件 + 失敗語彙(`TARGET_PLAYER_STATE_IS` を新設しシナリオが「生きた相手だけ」
  を宣言 + エンジン普遍則 `TARGET_IS_SELF` / `NOT_IN_SAME_SPOT` / `TARGET_IS_DOWN` / `TARGET_IS_DEAD`)。
- 対人 action の定義はシナリオ直下 `player_interactions` に1回、場所は前提条件(`SPOT_LIGHTING_IS` /
  `AT_SPOT_IS`)で書く。

### 役割分担(2026-07-25 合意)
- #2 `validate_actionable_target`(上記2層) → **nagi**。#819 の inline ガードは nagi PR 2〜3 で (2) に
  吸収(テストで同保証を固定してから inline 削除)。それまで #819 は残す。
- #4 executor 分割 → **claude**。nagi が `_interact` を触る PR 2 マージ後に着手(または item/sensory 系
  から先に)。
- モンスター attack 誘導 → **claude**(表示規約を nagi のモデルに合わせる)。
- take/loot(倒れた仲間の資材回収) → モデルには乗る(`REMOVE_ITEM(target)` + `GIVE_ITEM(actor)`)が
  nagi の順序では PR 6 と遅く、かつ `TARGET_HAS_ITEM`(所持確認)が未実装で空ポケット REMOVE_ITEM が
  ApplicationException を投げる欠落あり。実 run のボトルネックなので**暫定の専用経路を inline で作る
  案**(後で吸収前提 + 所持確認を入れる)を検討中(ユーザ判断待ち)。
- 条件体系4系統は nagi が `TARGET_PLAYER_STATE_IS` / `SPOT_LIGHTING_IS` / `AT_SPOT_IS` を足すため追従漏れ
  が起きやすい。**各体系トップに「別系統」docstring 注記**を双方で入れる方針。

### nagi の触る範囲(claude が避けるべき箇所)
- **避ける**: `spot_graph_resolver.py` / `ui_context_builder` のプレイヤー行 / interaction の前提条件評価。
- **触ってOK**: executor の item/sensory 系 / discovery・scenario_event の条件エンジン / attack 経路 /
  OBJECT_STOCK ヒント。

## resolver の意図的な非対称(#821 事後レビュー, 2026-07-25)

`_argument_resolvers/spot_graph_resolver.py`(952行)を「重複に見えて実は意図的な非対称」観点で
点検した結果。**将来の resolve_target 統一 / tend 移行で"共通化すると壊れる"箇所**として記録。
結論: これらは未整理ではなく意図的。共通ヘルパへ載せ替えると専用の失敗文面が汎用に落ちる。

- **A. pickup_item の kind/expected_types 食い違い**(:783-798): `InventoryToolRuntimeTargetDto` は
  inventory_item と ground_item の**両方**を表す共有クラスで型では区別不能 → `kind` 文字列で後段検証。
  この「kind 文字列で後段検証」構造自体は drop/give/use にも共通だが、**pickup だけ kind='ground_item'
  が DTO クラス名(Inventory…)と逆方向**の唯一のケース。専用文面「今いる場所に落ちているものでは
  ありません」は `test_pickup_inventory_item_message_uses_natural_place_wording` が固定。
- **B. resolve_object_target だけ `expected_types=()` で型チェック無効化**(:298-304): 代わりに
  `world_object_id` のフィールド存在で防御。object DTO は基底 `ToolRuntimeTargetDto` として登録される
  ため isinstance で絞るクラスが無い、という事情(nagi が abbd5bae でコメント追記済み)。
- **C. give_item/whisper の相手解決は `resolve_player_target`(例外を投げず None 返し)、tend は共通
  helper(例外)**: give の partial-success 設計(1件失敗でも他は通す、
  `test_give_item_unknown_recipient_lists_valid_player_names_in_partial_failure` が固定)を守る分岐。
  統一時に最も壊しやすい。
- **D. destination/sub_location は独自 error_code 体系**(`INVALID_DESTINATION_*`, コメント :150-152)。
- **_resolve_tend_to_player**(:816, 845-861): pickup と**同型の意図的非対称**。失敗文面が「同spot制約」
  と「down制約」の両方を先回りヒントする(`test_tend_to_player_error_hint.py` 固定)。汎用文面に戻すと
  E-36(#639/#640)で直した「別spotなのか未downなのか区別できない」silent confusion が再発。移行保留は妥当。

**層分離の確認**: resolver に `is_dead`/`is_down` は皆無(grep 0)。#819 のガードは executor /
transfer_service のみ。「resolve_target は種別だけ・状態は前提条件層」という分離は現時点で守られている。
**統一時の最大の注意**: tend の2段階の失敗理由(resolver='相手が存在しない'=INVALID_TARGET_LABEL 候補一覧つき /
executor='いるが down でない'=TARGET_IS_NOT_DOWN 相当)を、統一後の前提条件層でも区別可能に保つこと。

## 追加の dead code(nagi 発見, 2026-07-25)

`execute_interaction` が `acting_item_instance_id` / `target_item_instance_id` を受け取るが、**本番の
呼び出し元(application/llm 配下)が誰も渡していない**(出現 0 件)。結果、item instance 層の 6 種
(`ITEM_INSTANCE_STATE` / `CHANGE_*` / `RECORD_*_TICK`)が**エージェントの行動から到達不能**。
= 前提条件・効果の一部が「定義はあるが使えない」死蔵状態。将来 item instance を使う行動を足すときの
配線ポイントとして記録。

## 参考: 主要 file:line
- executor: `spot_graph_tool_executor.py`(1515行, `_give_item` 1041-1179, `_tend_to_player` 1386-1516)
- 権威評価器: `spot_interaction_service.py:119-320`
- 提示側再実装: `spot_graph_current_state_builder.py:54-177`
- remediation: `interact_helpers.py:60-84`
- discovery 条件: `spot_exploration_service.py:56-75`
- scenario 条件: `scenario_condition_evaluator.py`
- affordance 無条件付与バグ: `spot_graph_ui_context_builder.py:640`
- resolver(状態未参照): `_argument_resolvers/spot_graph_resolver.py`
- give_item(ガード無し): `spot_graph_item_transfer_service.py`
- attack(ドメイン委譲の好例): `spot_attack_orchestrator.py:308`
