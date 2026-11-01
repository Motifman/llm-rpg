# 行為の洗い出し (担当 A): interact / use_item / tend_to_player / give_item / pickup_item / drop_item / explore / set_sub_location

- 読んだ版: origin/main `f231eb62a` (#1961)。土台は `docs/environment_model/inventory/c_interactions_effects.md` (版 `21a33e4c9`)。その後に担当範囲のファイルへ入った変更は #1946 (介抱の同席判定) と #1958 (gold 不足の失敗観測) の 2 件で、本書の行番号は `f231eb62a` のもの
- パスは `src/ai_rpg_world/` からの相対。略記: `EXEC` = `application/llm/services/executors/spot_graph_tool_executor.py`、`CAT` = `application/llm/services/tool_catalog/spot_graph.py`、`RES` = `application/llm/services/_argument_resolvers/spot_graph_resolver.py`、`DISP` = `application/llm/services/world_llm_turn/tool_dispatch.py`、`SIAS` = `application/world_graph/spot_interaction_application_service.py`、`PIAS` = `application/world_graph/player_interaction_application_service.py`、`XFER` = `application/world_graph/spot_graph_item_transfer_service.py`、`RT` = `application/world_runtime/world_runtime.py`
- 【事実】はコードで確かめたこと、【推測】は読んだ範囲からの見立て (実行・試験はしていない)

---

## 0. 全行為に共通する外側の流れ 【事実】

| 段 | 内容 | 根拠 |
|---|---|---|
| 手番を回すか | 倒れている (`can_act()` が False)・結果確定 (EJECTED 等)・移動中の人には LLM 手番そのものを回さない。去った主体 (DEAD + departed 有効) には回す | `application/llm/services/world_llm_turn/turn_trigger.py:143-146, 379-397`、`application/player/services/player_life_query.py:72-99` |
| ツールを出すか | `ToolExposure.split_for_phase`。シナリオの `disabled_tools`、会議フェーズ、去った主体 (`DEPARTED_TOOLS = speak/travel_to/interact/listen/wait`) で絞る。`tend_to_player` は会議中も出す共通ブロック | `application/llm/tool_exposure.py:96-109, 255-285`、`RT:1570-1641` |
| 出していないツール | 実行時に `get_tool_definitions(player_id)` を引き直し、無ければ `TOOL_BECAME_UNAVAILABLE` / `TOOL_NOT_OFFERED_NOW` | `DISP:1074-1121, 1178-1194` |
| 1 手番 1 行為 | Phase B が tool_call を 1 件取り出して実行 | `application/llm/services/world_llm_turn/phase_b.py:192-240` |
| 名前の解決 | resolver が、その手番のプロンプトに出した対象の表 (`runtime_context.targets`) からラベルを内部 ID に置き換える。表に無ければ失敗 DTO。対象の表は同じ場所・見えているものだけ (暗所で見えない物体・不可視物体は表に入らない `application/world_graph/spot_graph_current_state_builder.py:1148-1150`) | `RES:575-633`、`DISP:382-417, 782-918` |
| say_inline | ハンドラの後で SAY として出す。行動が失敗しても出す (D1601)。出していないツールなら出さない | `application/llm/services/world_llm_turn/say_inline_delivery.py:26-62`、`EXEC:731-787`、`DISP:445-451, 1194` |
| 時間 | ツール実行の中で即時に確定する。どの行為も world tick を進めない (tick は別ループ)。移動中に重い行為を選ぶと移動を中断し、行為が失敗したら移動を戻す (ただし移動中は手番が回らないので、通常は通らない) | `DISP:991-1059`、`phase_b.py:240-279` |

`inner_thought` は全ツールが持つ (必須)。`say_inline` を持つのは `interact` `use_item` `tend_to_player` `give_item` `pickup_item` `drop_item` `explore`。`set_sub_location` だけ持たない (`CAT:89-104`)。

---

## 1. interact — 物・手元の道具・人に、宣言された操作をする

1 つのツールが、resolver の解決結果で 4 経路に分かれる (`EXEC:899-927`)。

```
target_label → resolver (RES:1552-1654)
  spot_graph_player → target_player_id → 対人 (§1-C)
  inventory_item    → item_spec_id     → 手元の道具 (§1-B)
  spot_graph_object → object_id
       action_name が synchronized_action_groups に在る → 準備 (§1-D)
       それ以外 → 物体 (§1-A)
```

共通:
- 引数: `target_label` (必須)、`action_name` (必須)、`parameters` (任意の dict)、`say_inline`、`inner_thought` (`CAT:123-178`)。`parameters` は resolver を素通りして (`RES:532-543`) 前提条件 (`PUZZLE_INPUT_MATCH`) と効果 (`WRITE_PLAYER_TEXT` の本文、品目を実行時引数で決める `GIVE_ITEM` など) に渡る
- action_name は表示の写し崩れを救済し、設定があれば LLM 判断で読み替える (`RES:1578-1594`)
- 疲労 100 なら 4 経路すべての前で `EXHAUSTED` (`EXEC:900-902, 524-544`)。LLM 層
- 成功後、物体・道具・対人の 3 経路は疲労 +2 を確定境界の外で別保存 (`EXEC:956, 1049, 1128`)。去った主体には足さない (`EXEC:552-559`)。準備経路は足さない
- 同じ引数の繰り返しはループ検知の対象 (閾値 4) (`application/llm/services/loop_guard_detectors.py:23`)
- cooldown がある (宣言した操作だけ)

### 1-A. 物体への操作

| 項目 | 内容 |
|---|---|
| 主体 | 既定は生者だけ。操作ごとに `allowed_actor_planes` で去った主体 (DEPARTED) を許せる (`domain/world_graph/value_object/interaction_def.py:97, 108-110`)。去った主体の居場所は `DepartedPositionStore` から引く (`SIAS:290-300`)。倒れている人は手番が無い |
| 対象 | 行為者の現在地の物体。`target_label` (表示名、同名は `#N`) を `object_id` に解決。実行時は `interior.get_object(object_id)` で引き、`visible` は見直さない (見えない物体は resolver の表に入らないので届かない) |
| 前提 (シナリオ) | `InteractionDef.preconditions` を宣言順に AND で評価、最初の不成立で `InteractionNotAllowedException` (`domain/world_graph/service/spot_interaction_service.py:760-781, 171-268`)。種類は 31 個 (`domain/world_graph/enum/interaction_condition_type.py`)。パズル入力欠けは `InteractionParameterMissingException` (`spot_interaction_service.py:79-91`)。D 層 |
| 前提 (コード) | ①cooldown 残り (`SIAS:1248, 471-493`) ②存在層 (`SIAS:1249-1250, 366-375`) ③操作名が無い → `InteractionNotFoundException` (D) ④効果が消す品目を全量持っているか (D `spot_interaction_service.py:783-790`、A `SIAS:1303` 予約品除外) ⑤納める gold を凍結分を除いて払えるか (`SIAS:1307-1323, 1678-1706`)。①②⑤は A 層 |
| 世界の変化 | `InteractionEffect` を使う。`WorldGraphEffectService.apply_effects` (D) の結果を A が当てる: 世界フラグ、interior (物体 state / 公開 / 小部屋の発見)、gold、通路、転移、雰囲気、品目の付与・削除、道具 instance の state、本人の自由 state、接続の作成・削除、本人へのダメージ・状態異常・欲求 (`SIAS:1325-1600`)。CALL_MEETING は会議 command に任せる (`SIAS:1650-1676`)。保存先は `SpotInterior` / `SpotGraphAggregate` / `PlayerInventoryAggregate` / `ItemAggregate` / `PlayerStatusAggregate` / `MutableWorldFlagState` / cooldown store |
| 確定境界 | 1 つの `CommandScope`。CALL_MEETING を宣言した操作だけ scope の外 (`SIAS:1031-1113`) |
| 本人に返る (成功) | 効果 `SHOW_MESSAGE` 等の文 (シナリオ作者の文) + 在室数表示 (コードの文) を `; ` で連結。空なら「完了」(コード) (`EXEC:957`、`SIAS:1640-1648`)。trace に `object_state_changes` |
| 本人に返る (失敗) | 前提不成立: 「行動が拒否された: {理由}」+ 区分ごとの remediation (`EXEC:1601-1647`)。理由は条件の `failure_message` (作者) か、コードの既定文 (`spot_interaction_service.py:323-338` など)。状態が先に進んだときは「いまできるのは …」を足す。操作名違い: 「このオブジェクトには '{x}' という操作がありません。利用可能な操作: …」(コード) (`EXEC:971-1014`)。cooldown: 「まだそれはできない。あと…」(コード) |
| 周り (成功) | `SpotObjectInteractedEvent` を A が組み立て、`witness_policy` が SAME_SPOT のときだけ同席者 (行為者除く) へ。文は作者の `witness_observation_message` → 表示ラベル → 従来文 (`SIAS:1600-1620`、`application/observation/services/recipient_strategies/spot_graph_recipient_strategy.py:211-220, 447`)。`PUBLIC_OBSERVABLE` 効果は `SpotPublicEffectObservedEvent` 系で同席者へ。転移・通路などはグラフのイベントで届く |
| 周り (失敗) | 前提不成立のときだけ、rollback 後に `SpotObjectInteractionFailedEvent` を同席者へ (役割などの秘匿条件・引数欠けは出さない、同じ失敗は 24 tick 抑止) (`SIAS:1099-1112, 1276-1303, 2055-2175`)。gold 不足も「納めるだけの持ち合わせがなかった。」で出す (#1958、`SIAS:1307-1323`)。**cooldown と存在層の拒否は try の外なので出さない** (`SIAS:1248-1250`) |
| 時間 | 即時。cooldown の起点は成功時だけ記録 (`SIAS:1638`) |

### 1-B. 手元の道具への操作

| 項目 | 内容 |
|---|---|
| 主体 | 1-A と同じ (`allowed_actor_planes`)。去った主体には interact が出るが、道具を持てるかは確かめていない |
| 対象 | 自分の所持品。`target_label` → `item_spec_id` (resolver の DTO は item_spec_id を `item_instance_id` 欄に入れる慣習 `RES:1621-1636`)。実行時に所持品から同じ品目の instance を 1 つ引き直す。**取引で予約中の品も除外しない** (`SIAS:597-617`) |
| 前提 (シナリオ) | 道具の登録簿の `InteractionDef.preconditions` (`SIAS:619-627`、`spot_interaction_service.py:832-866`)。物体は渡さない (`acting_object=None`) |
| 前提 (コード) | ①操作名が無い → NotFound (`SIAS:643-645`) ②持っていない →「その道具を持っていない。」(`SIAS:610-617`) ③存在層 ④cooldown (道具キー) (`SIAS:724-731`) ⑤効果の明示対象物が世界に無い / 複数部屋にまたがる → `ApplicationException` (`SIAS:761-797`) ⑥削除全量・gold (`SIAS:824-825`) |
| 世界の変化 | 1-A と同じ効果系。効果は明示対象物の部屋の interior に当たり、前提は行為者の現在地で評価 (`SIAS:761-801, 834-955`)。未知の状態異常・欲求の種類名は `ValueError` で全体 rollback (物体経路は警告スキップ) (`SIAS:938-952` 対 `SIAS:1520-1576`) |
| 本人に返る | 成功: 効果の文 or「完了」。失敗: 「行動が拒否された: {理由}」+ 固定の remediation (区分なし) / 操作名違い「この所持アイテムには … という操作がありません」(`EXEC:1061-1082`) |
| 周り | 操作そのものの目撃イベントは出さない (居場所が漏れるため、と docstring) (`SIAS:712-718`)。世界に出る効果 (グラフのイベント・公開効果) だけ届く (`SIAS:957-965`)。失敗観測も出さない |
| 時間 | 即時、cooldown あり |

### 1-C. 人への操作 (`player_interactions`)

| 項目 | 内容 |
|---|---|
| 主体 | `allowed_actor_planes` (`PIAS:835-837`)。行為者の居場所は `graph.get_entity_spot` で引く (`PIAS:847`)。【推測】去った主体を許した操作では、`DepartedPositionStore` を見ないので居場所が身体側になる |
| 対象 | 同じ場所に居るプレイヤー。`target_label` → `target_player_id`。倒れている相手は身体の位置 (`fallen_body_registry`) で同席を判定 (`PIAS:848-868`) |
| 前提 (シナリオ) | `can_interact` で preconditions を評価 (相手の HP・state・所持品を見る条件を含む) (`PIAS:924-946`)。`TARGET_PLAYER_IS_INCAPACITATED` を宣言していれば倒れた相手を、していなければ立っている相手を要求 (`PIAS:182-198`) |
| 前提 (コード) | ①存在層 ②自分自身は不可 (`ApplicationException`) ③同じ場所 (`ApplicationException`「相手が同じ場所にいません。」) ④`validate_actionable_target` (退場確定・倒れ/立ち) (`PIAS:870-886`、`domain/player/service/actionable_target.py:64-109`) ⑤cooldown ⑥削除全量 (対象・行為者) ⑦受け取り側の空き (`PIAS:948-993`)。①④⑤は `InteractionNotAllowedException`、②③は `ApplicationException`。A 層 |
| 引数の特例 | `parameters.item` を相手の所持品の品目へ読み替える (LLM 判断の救済あり) (`PIAS:915-922, 1164-1250`) |
| 世界の変化 | `InteractionEffect` を使う。当てるのは flags・品目の付与 / 削除 (行為者・対象)・行為者の自由 state・ダメージ (行為者・対象)。状態異常・欲求・転移・接続などは捨てる (土台 doc §2-1 の表) (`PIAS:971-1077`) |
| 本人に返る | 成功: 効果の文 (+品名を読み替えたときの「「x」は「y」と解釈した。」)。失敗: 前提不成立は「行動が拒否された: …」、②③は `ApplicationException` が `exception_result` に落ち、日本語の文のまま **error_code=SYSTEM_ERROR** で返る (`EXEC:1145-1159`、`application/llm/services/tool_executor_helpers.py:132-182`) |
| 周り | `PlayerInteractedWithPlayerEvent`。SAME_SPOT なら同席者 (対象本人を含む)、ACTOR_ONLY でも `notify_target` なら対象本人だけ (`spot_graph_recipient_strategy.py:222-244`)。倒れたら `PlayerDownedEvent` (既知の全員へ)。失敗観測は出さない |
| 時間 | 即時、cooldown あり |

### 1-D. 二人で合わせる操作の準備 (同期行動)

| 項目 | 内容 |
|---|---|
| 主体 | 1-A と同じ判定 (`SIAS:1789-1790`) |
| 対象 | `action_name` だけで現在地の物体を引き直す。resolver が解決した `object_id` は使わない。同名の物体が複数あれば拒否 (`SIAS:1756-1799`) |
| 前提 (シナリオ) | 対象操作の preconditions を効果なしで評価 (`SIAS:1791-1798`) |
| 前提 (コード) | シナリオに `synchronized_action_groups` が無い / 名前が無い / time_provider 未配線 / cooldown / 同じグループの別役を既に受け持っている (`EXEC:1455-1528`) |
| 世界の変化 | 効果は起こさない。世界フラグ `prepared:` を立て、`SynchronizedActionRegistry` に tick つきで登録 (`EXEC:1530-1534, 1674-1718`)。実際の効果は tick 側の `SynchronizedActionResolverStageService` |
| 本人に返る | 「「{表示名}」を受け持った。まだ動いていない。…」(コード) (`EXEC:1538-1544`) |
| 周り | グループが `on_prepare_observation_message` を宣言していれば `SpotPlayerPreparedActionEvent` を同席者へ (作者の文) (`EXEC:1697-1718`) |

---

## 2. use_item — 所持している消耗品を自分に使う

| 項目 | 内容 |
|---|---|
| 主体 | 生者 (去った主体には出さない `tool_exposure.py:109`)。疲労上限の拒否は無い |
| 対象 | 自分の所持品。`item_label` → `item_spec_id` + `is_spoiled` (`RES:1065-1114`)。実行時に (品目, 腐敗) で空でない枠を引き直し、取引で予約中の品は除く (`EXEC:453-483`) |
| 引数 | `item_label`、`say_inline`、`inner_thought` (`CAT:255-288`)。効果へ渡る実行時の値は無い |
| 前提 (シナリオ) | 無い (アイテム定義の `item_type` と `consume_effect` だけ) |
| 前提 (コード) | 持っている (予約中なら「取引に出しているので使えません」) / ItemType が CONSUMABLE (`EXEC:1236-1270`)。すべて LLM 層の実行者の中 |
| 世界の変化 | `InteractionEffect` を使わない。`ItemAggregate.use()` で数量 −1、0 なら所持品から外して instance を削除 (`EXEC:1277-1313`)。腐敗品: 実行者が直接 `apply_damage` + 空腹の一部回復 (`spoiled_consumption_outcome`) (`EXEC:1316-1355`)。新鮮品: `ConsumableUsedEvent` → `ConsumableEffectHandler` が `ItemEffect` (Heal / DamageHp / RecoverMp / Gold / Exp / Revive / SatisfyNeed / Composite) を `PlayerStatusAggregate` に当てる (`EXEC:1356-1367`、`application/world/handlers/consumable_effect_handler.py:67-135`)。`fatigue_recovery` があれば疲労回復 (`EXEC:1370-1372`)。全部 1 つの CommandScope (`EXEC:1161-1198`) |
| 本人に返る | 新鮮:「{名前}を使用した。」+「（効果が適用された）」(コード)。腐敗:「{名前}を食べてしまった。腐っていた——…（{n} ダメージ…）」(コード)。HP 回復量などは結果文に入らず、`PlayerHpHealedEvent` 等の本人向け観測で届く (`consumable_effect_handler.py:82-90`)。失敗: `ITEM_NOT_FOUND` / `ITEM_NOT_CONSUMABLE` / 予約中 (コード) |
| 周り | 新鮮品で `consume_effect` があるときだけ `ConsumableUsedEvent` →「{X}が{品}を使用した。」を同じ場所の他者へ (`application/observation/services/recipient_strategies/item_use_recipient_strategy.py:44-63`、`formatters/item_use_formatter.py:22-58`)。**腐敗品と効果なしの品は誰にも見えない** (イベントを出さない)。倒れたら `PlayerDownedEvent` |
| 時間 | 即時。cooldown なし |

---

## 3. tend_to_player — 同じ場所で倒れている人を起こす

| 項目 | 内容 |
|---|---|
| 主体 | 生者 (去った主体には出さない)。自分が倒れていれば拒否 (手番が無いので実質通らない)。疲労上限の拒否は無い |
| 対象 | 人。`target_player_label` → `target_player_id` (`RES:1413-…`)。行の表示は「同席かつ行動不能・未退場の相手」にだけ出す (`application/world_graph/spot_graph_current_state_builder.py:565-571`) |
| 引数 | `target_player_label`、`say_inline`、`inner_thought` (`CAT:497-523`)。効果へ渡る値は無い (回復率はコードの定数 0.6 `EXEC:2904`) |
| 前提 (シナリオ) | 無い。蘇生の無い世界は `disabled_tools` で消す (`tool_exposure.py:96-104`) |
| 前提 (コード) | 自分自身不可 / 同席 (相手が倒れていれば身体の位置、#1946) / 自分が倒れていない / 相手が退場確定でない / 相手が倒れている (`EXEC:3027-3076, 3114-3129`、`actionable_target.py:64-109`)。判定は D のドメインサービス `validate_actionable_target`、同席の材料集めは LLM 層の実行者 |
| 世界の変化 | `InteractionEffect` を使わない。`PlayerStatusAggregate.revive(0.6, caregiver)` で HP = 最大×0.6、`is_down=False`、`PlayerRevivedEvent` (`domain/player/aggregate/player_status_aggregate.py:722-760`)。同じ CommandScope の commit 前ハンドラが身体の記録と死亡猶予を取り消す (`EXEC:3093-3104`、`RT:5551, 6104`) |
| 本人に返る | 成功:「{名} を介抱して意識を取り戻させた。（HP a/b）」(コード)。失敗: 拒否理由ごとの固定文 (`EXEC:271-281`) と既存 error_code (`INVALID_TARGET_KIND` / `EXHAUSTED` / `INTERACTION_PRECONDITION_FAILED`) |
| 周り | `PlayerRevivedEvent` を本人と既知の全員へ。同席者は「{X}が復帰しました。」、離れた人は「遠くで誰かが動けるようになった気配がした。」(`application/observation/services/recipient_strategies/default_recipient_strategy.py:115-138`、`formatters/player_formatter.py:247-288`)。**誰が介抱したかは観測文に出ない** (caregiver はイベントに載るが、この formatter は使っていない)。失敗は誰にも見えない |
| 時間 | 即時。cooldown なし |

---

## 4. give_item — 同じ場所の人に、持ち物を直接渡す (複数件まとめて)

| 項目 | 内容 |
|---|---|
| 主体 | 生者 (去った主体には出さない。同席者行の案内も去った視点では出さない `spot_graph_current_state_builder.py:1505`)。疲労上限の拒否は無い |
| 対象 | 品 × 人の組 (1〜8 件)。`gives[].item_label` → `item_spec_id`+`is_spoiled`、`gives[].target_player_label` → `target_player_id` (`RES:1116-1267`)。件ごとに解決失敗を残して先へ進む |
| 引数 | `gives[{item_label, target_player_label, quantity?}]` (quantity は 1 以上、省略 1)、`say_inline`、`inner_thought` (`CAT:359-421`) |
| 前提 (シナリオ) | 無い |
| 前提 (コード) | 件ごと、1 個ごとに: 手元にある (予約中を除く、`EXEC:2593-2608`) → 自分自身でない → 相手の inventory がある → 相手が退場確定でない → 相手が倒れていない → 枠が空でない → **同じ場所** → 相手に空きがある (`XFER:535-599`)。判定は A 層。`validate_actionable_target` は使わない |
| 世界の変化 | `InteractionEffect` を使わない。送り手の枠から instance を外し、受け手の空き枠へ入れる (`XFER:600-609`)。**1 個ごとに別の CommandScope** (`EXEC:2611-2629` → `XFER:503-533`)。途中で止まっても、それまでに渡した分は確定 |
| 本人に返る | 「give_item 結果:」+ 件ごとの OK / NG 行 (コード)。1 件でも渡れば success、全部駄目なら「give_item: 全て失敗」と最初の失敗の error_code (`EXEC:2672-2701`)。足りない数は「x/y 個」で返す。trace に頼んだ数と動いた数 |
| 周り | 1 個ごとに `PlayerGaveItemEvent` →「{X}が{品}を{Y}に渡した。」を同じ場所の送り手以外 (受け手を含む) へ。受け手の手番を起こす (`spot_graph_recipient_strategy.py:425-427`、`formatters/_spot_graph_object_handler.py:318-345`)。失敗は誰にも見えない |
| 時間 | 即時。cooldown なし |

---

## 5. pickup_item — 今いる場所の地面の物を拾う

| 項目 | 内容 |
|---|---|
| 主体 | 生者 (去った主体には出さない)。疲労上限の拒否は無い |
| 対象 | 現在地の地面の品 (`SpotInterior.ground_items`)。`ground_item_label` → `item_instance_id` (`RES:1320-1356`)。持ち主の区別は無い (誰が置いた物でも、初期配置でも拾える) |
| 引数 | `ground_item_label`、`stealth` (bool、既定 false)、`say_inline`、`inner_thought` (`CAT:425-461`)。`stealth` は観測の範囲 (`WitnessPolicy`) にだけ効く |
| 前提 (シナリオ) | 無い |
| 前提 (コード) | 地面にまだある (`GroundItemGoneError`) / 自分の inventory に空きがある (`PickupSelfInventoryFullError`) (`XFER:414-449`)。A 層 |
| 世界の変化 | `InteractionEffect` を使わない。inventory に入れ、interior の地面から外す (`XFER:451-460`)。1 つの CommandScope |
| 本人に返る | 「{品}を拾い上げた。」(コード)。失敗は例外の日本語文と error_code をそのまま (先取りの可能性・drop の助言を含む、コード) (`EXEC:1838-1850`) |
| 周り | `stealth=false` なら `PlayerPickedUpItemEvent` →「{X}が{品}を拾い上げた。」を同席者へ (手番を起こす)。`stealth=true` なら誰にも届かない (`spot_graph_recipient_strategy.py:211-220, 449`、`_spot_graph_object_handler.py:668-695`) |
| 時間 | 即時 |

## 6. drop_item — 持ち物を今いる場所の地面に置く

| 項目 | 内容 |
|---|---|
| 主体 | 生者 (去った主体には出さない)。疲労上限の拒否は無い |
| 対象 | 自分の所持品 1 個。`item_label` → `item_spec_id`+`is_spoiled`、枠は実行時に引き直す (予約中は除く) (`RES:1269-1318`、`EXEC:1763-1773`) |
| 引数 | `item_label`、`stealth`、`say_inline`、`inner_thought` (`CAT:315-354`) |
| 前提 (シナリオ) | 無い |
| 前提 (コード) | 持っている (予約中なら「取引に出しているので置けません」) / 枠が空でない (`XFER:329-334`)。地面の容量制限は無い |
| 世界の変化 | `InteractionEffect` を使わない。inventory から外し、interior の地面に `GroundItem` を足す (`XFER:347-357`)。1 つの CommandScope |
| 本人に返る | 「{品}を地面に置いた。」(コード) |
| 周り | pickup と同じ形 (`PlayerDroppedItemEvent`、stealth で消える) (`_spot_graph_object_handler.py:642-666`) |
| 時間 | 即時 |

---

## 7. explore — 今いる場所を探す

| 項目 | 内容 |
|---|---|
| 主体 | 生者 (去った主体には出さない)。疲労上限の拒否も疲労の加算も無い (`EXEC:203-208` の対応表に無い) |
| 対象 | なし (現在地) |
| 引数 | `say_inline`、`inner_thought` だけ (`CAT:107-121`) |
| 前提 (シナリオ) | 行為そのものには無い。発見物ごとの `discovery_condition` (ALWAYS / SEARCH_COUNT / HAS_ITEM / FLAG_SET) (`domain/world_graph/service/spot_exploration_service.py:79-109`) |
| 前提 (コード) | 現在地の interior と inventory がある (`application/world_graph/spot_exploration_application_service.py:136-152`)。それ以外で断られることは無い |
| 世界の変化 | `InteractionEffect` を使わない。その人・その場所の探索回数 +1 (`ISpotExplorationProgressStore`、rollback 参加者)、条件を満たした発見物を発見済みに、品を inventory へ付与 (溢れは足元へ) (`spot_exploration_application_service.py:154-178`、`infrastructure/unit_of_work/interaction_rollback_participants.py:196-207`)。1 つの CommandScope |
| 本人に返る | 発見あり:「発見: {作者の description} / …」。発見なし:「新しい発見はなかった。」+ 尽きていれば「…もう無い。」+ 見えている物体の名前一覧 (コード) (`EXEC:836-866`) |
| 周り | 毎回 `SpotExploredEvent` →「{X}が周囲を探索している。」を同席者へ (手番を起こす)。何を見つけたかは伝えない (`spot_exploration_application_service.py:180-189`、`formatters/_spot_graph_movement_handler.py:202-219`) |
| 時間 | 即時。SEARCH_COUNT は回数で解禁するので、時間ではなく試行回数を数える |

---

## 8. set_sub_location — 同じ場所の中の小部屋を移る

| 項目 | 内容 |
|---|---|
| **配線** | **実験 runtime では LLM に出さず、ハンドラも登録しない**。`ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS` で定義から除き (`application/llm/services/world_llm_turn/escape_tools.py:28-40`、`phase_a.py:142`)、`wire_missing_spot_graph_tools` の対象表に無い (`DISP:256-351`)。実行者の実装 (`EXEC:789-813`) は残っている |
| 主体 | (実装上) 移動中でない人 |
| 対象 | 小部屋。`sub_location_label` → `sub_location_id`。表示は隠れていない小部屋だけ (`application/llm/services/spot_graph_ui_context_builder.py:851-874`)。ラベル未指定は「小部屋から出る」(None) (`RES:319-341, 1541-1550`) |
| 引数 | `sub_location_label` (任意)、`inner_thought`。say_inline なし |
| 前提 (コード) | 移動中は不可 (`domain/player/value_object/player_spot_navigation_state.py:79-83`、D)。その小部屋が現在地のものか・発見済みかは実行時に確かめない (resolver の表だけ) |
| 世界の変化 | `PlayerStatusAggregate.spot_navigation_state.current_sub_location_id` を書き換える (`application/world_graph/spot_graph_movement_application_service.py:143-176`)。この値を読むのはプロンプトの「（現在ここ）」表示と snapshot だけで、前提条件・観測・音には効かない (`grep current_sub_location_id` の結果) |
| 本人に返る | 「サブロケーションを更新しました。」(コード) |
| 周り | 何も出さない |
| 時間 | 即時 |

---

## 9. 担当の行為をまたいで見えたこと

【事実】
- **同じ「相手が有効か」を 3 通りに書いている。** tend と対人 interact は `validate_actionable_target` (D) を使い、give は転送サービスに独自の判定を持つ (`XFER:550-582`)。give は「死亡 → 倒れ → 枠 → 同じ場所」の順なので、別の場所に居る相手の死亡・倒れが本人に伝わる。`validate_actionable_target` の docstring が避けている漏れ (`actionable_target.py:74-86`) が give にだけ残っている
- **同席の判定材料が行為ごとに違う。** give は両者ともグラフの presence、tend と対人 interact は倒れた相手なら身体の位置、物体 interact は去った主体なら `DepartedPositionStore`、対人 interact は行為者側で `DepartedPositionStore` を見ない
- **失敗が周りに見えるのは物体 interact だけ。** 道具 interact・対人 interact・give・pickup・drop・use_item・tend の失敗は同席者に届かない。物体 interact でも cooldown と存在層の拒否は届かない
- **成功の見え方もばらつく。** 物体 interact・対人 interact・pickup・drop は `witness_policy` (作者の宣言、または `stealth` 引数) で隠せる。give・explore・use_item は隠せない。use_item は腐敗品と効果なしの品だけ誰にも見えない (隠すつもりではなく、イベントを出さない経路だから)
- **「世界を変える仕組み」が 3 つ。** interact は `InteractionEffect` (シナリオの効果)、use_item は `ItemEffect` (アイテム定義の効果、ハンドラが当てる) + 腐敗の直書き、tend / give / pickup / drop / explore / set_sub_location は効果なしで application が集約を直接変える。回復を例にとると、use_item の Heal、interact の SATISFY_NEED、tend の revive が別の経路
- **規則の置き場所が層をまたぐ。** use_item の「CONSUMABLE だけ」「腐敗でダメージ」と tend の同席判定・回復率 0.6 は LLM 層の実行者 (`EXEC`) にある。疲労上限で止めるのも LLM 層で、interact だけが対象 (use_item・give・explore などは疲労 100 でも通る)
- **確定境界の粒度が違う。** interact・use_item・tend・pickup・drop・explore は 1 行為 1 scope。give は 1 個 1 scope で部分成功する。interact の疲労加算は scope の外で別保存
- **取引の予約の扱いが違う。** use_item・give・drop は予約中の品を除くが、道具 interact は除かない (`SIAS:610-617`)。効果の REMOVE_ITEM 側は未予約品で検算する (`SIAS:1735-1754`)
- **人を対象にする入口が 3 つ。** 対人 interact (`target_label`)、give_item (`target_player_label`)、tend_to_player (`target_player_label`)。同じ「同席の人」の表 (`spot_graph_player`) を引くが、引数名が違う
- **失敗の error_code の付き方が揃っていない。** 対人 interact の「自分自身」「同じ場所にいない」は `ApplicationException` から `SYSTEM_ERROR` になる。give の同じ失敗は専用の code (`GIVE_ITEM_TARGET_IS_SELF` / `..._NOT_IN_SAME_SPOT`)、tend は `INVALID_TARGET_KIND` / `INTERACTION_PRECONDITION_FAILED`
- **本人に返る文の作り手。** interact は作者の文 (効果の SHOW_MESSAGE、条件の failure_message) が中心で、作者が書かなければ「完了」やコードの既定文。他の行為はすべてコードの文。去った主体への拒否文「…自分の担当と共通の点検を続けられる。」はコードに固定された、特定の世界向けの文 (`application/world_graph/interaction_actor_plane.py:22-26`)
- **ツールの説明と実装のずれ。** interact の引数 `target_label` のコメントは「現時点で解決できるのは引き続き物体だけ」と書くが、resolver は人と所持道具も解決する (`CAT:126-131` 対 `RES:1567`)。tend の docstring は回復率 0.4 と書くが、定数は 0.6 (`EXEC:2978` 対 `EXEC:2904`)。tend の説明は「第三者にも介抱している様子が SAY として届く」と書くが、届くのは say_inline を書いたときだけ (`CAT:509-511`)
- **set_sub_location は実験 runtime に無い。** 状態としての小部屋も、表示以外で読まれていない

【推測】
- give の 1 個ごとの scope と 1 個ごとの観測イベントのため、3 個渡すと同席者に同じ文が 3 回届く (イベント発行は 1 個ごと `XFER:503-533`、まとめる処理は見当たらない)
- 対人 interact で去った主体を `allowed_actor_planes` に入れた操作は、行為者の居場所をグラフから引くため、幽霊の位置と食い違う (去った主体を許す対人操作が実在するかは見ていない)
- tend の観測で介抱した人の名前が出ないのは、formatter の `caregiver_player_id` 未使用による。post hoc の handler が別にあると docstring にあるが (`player_status_aggregate.py:731-734`)、その観測は確かめていない
