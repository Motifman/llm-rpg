# アイテム統合・材料消費計画の試験監査

## 結論

操作の件数だけでは見逃す対象ID・数量と、実際には通っていなかった分散材料・複数仕様・複数追加スタックを、公開計画入口で検査する。値を構築して読み戻す重複はこの保持先へ集約し、値型にしかない数量制約・属性再代入拒否・耐久値・総消費量は残した。

- 対象は元39宣言。保持22、検査改善7、統合10、単独削除0
- 39宣言39ケースから29宣言36ケースへ。宣言数と表の実行行数は分けて数える
- 2試験ファイルは1020行から854行へ（追加133行、削除299行、差引166行減）。共通入力は165行で変更なし、これらの内数
- 製品コード・専用支援ファイルの変更なし。所有規約を7行追加
- 先行#1682の元8宣言と#1764の元76宣言は加算しない。今回ファイル内の既存保持先（合計45、採用ID105/107）も本文一致を維持

## 固定した依存と実利用

[親PR #1764](https://github.com/Motifman/llm-rpg/pull/1764) のhead `e07b3a5b65941c49b7d52441db5d314c195bbfe5`、tree `66289c270fe15a4456b2ea28f35325e99af8bd76` を基準とする。親は [#1682](https://github.com/Motifman/llm-rpg/pull/1682) のスタック判定保持先を含む。

`ItemStackingDomainService` の外側の直接実行呼出元は確認できなかったが、公開された計画APIを未接続だけで廃止しない。`MergePlan` と操作3型には `application/inventory/services/item_service.py` の `ItemStackingApplicationService.execute_merge_plan` という実利用先があり、更新ID/新数量、削除ID、生成仕様/耐久/数量を集約と保存層へ渡す。計画を生成する責任と、受け取って保存する責任は別である。

[#1676](https://github.com/Motifman/llm-rpg/pull/1676) の固定head `c8b9ced4b5488c57bd6082fcfe6cc3babc591aa5` も読んだ。木材5・石3・木材2・石1を木材7/石4へ集計する検査は、実体ごとの消費・更新・削除対象を決める本件を代替しない。そちらの差分は取り込んでいない。

## 保持先と改善した入力

主な保持先は `tests/domain/item/service/test_item_domain_service.py`。実際の `ItemAggregate` と `RecipeAggregate` を渡し、計算された公開操作値を読む。私有補助関数を直接検査しない。

- 部分消費: 木材5/石3から消費2/1、残量3/2、更新ID1→3・ID2→2、元数量不変
- 分散材料: 元の木材3/2/10・石5を残し、木材1/2/10を追加。要求2が2実体を跨ぎ、ID1削除・ID2部分更新・余剰ID3非採用を検査
- 全消費: 木材2/石1で削除ID1/2だけでなく消費記録2/0・1/0も検査
- 上限超過: 元30/40/25=95を残し、64/32/32/31=159を追加。生成64/31と削除ID112/113/114を確認
- 複数仕様: 元の通常20/30＋耐久1を残し、通常仕様A50/30（上限64）とB20/20（上限32）を追加。同名でも仕様IDを混ぜず、生成16/8へ分ける
- `ItemSpec.__eq__` はIDのみを見るため、生成仕様のID・最大スタック・耐久最大を直接照合する。全属性保持という主張はしない
- 独立した操作の返却順序は固定せず、対象IDと数量を照合する

`tests/domain/item/value_object/test_merge_plan.py` は数量0/負数、属性の再代入拒否、生成操作の耐久値と省略時のNone、総消費13と0を所有する。耐久付き生成操作はサービスが耐久品を除外するため直接入口を残し、実体構築でも合法な最大スタック1・耐久最大100へ入力を直した。属性の再代入拒否は、リスト内容まで変更不能という意味ではない。

## 全39宣言の判定

`S` は上のサービス試験、`V` は計画値型試験。下記の識別子は監査前の宣言名。Rは保持、Fは契約を残して検査改善、Cは指定保持先へ統合。

| ID | ファイル | 判定 | 元宣言 | 検出する契約・移管先 |
|---|---|---|---|---|
| I39-01 | S | F | `TestItemStackingDomainServiceCrafting::test_plan_crafting_consumption_success_single_item_each` | 木材5・石3からID1で2消費/3残、ID2で1消費/2残。更新2件・削除0件。 |
| I39-02 | S | F | `TestItemStackingDomainServiceCrafting::test_plan_crafting_consumption_success_multiple_items_same_spec` | 木材3/2/10、石5から先頭木材ID1と石ID4だけを消費する。 |
| I39-03 | S | F | `TestItemStackingDomainServiceCrafting::test_plan_crafting_consumption_complete_consumption` | 要求と一致する木材2・石1を全消費し、削除ID1/2・更新なし。 |
| I39-04 | S | R | `TestItemStackingDomainServiceCrafting::test_plan_crafting_consumption_insufficient_ingredients_missing_spec` | 木材10だけでは石が欠落しており、Recipe1/欠落理由を伴うInsufficientIngredientsException。 |
| I39-05 | S | R | `TestItemStackingDomainServiceCrafting::test_plan_crafting_consumption_insufficient_quantity` | 木材1・石10では木材の要求2に足らず、数量不足理由で拒否。 |
| I39-06 | S | R | `TestItemStackingDomainServiceCrafting::test_plan_crafting_consumption_empty_available_items` | 利用可能実体が空ならInsufficientIngredientsException。 |
| I39-07 | S | R | `TestItemStackingDomainServiceCrafting::test_plan_crafting_consumption_minimal_ingredients_recipe` | 1材料/1実体/数量1なら消費1・更新0・削除ID1・総消費1。 |
| I39-08 | S | R | `TestItemStackingDomainServiceStacking::test_calculate_max_stack_quantity_single_item` | 候補なしは基準数量10・採用リスト空。 |
| I39-09 | S | R | `TestItemStackingDomainServiceStacking::test_calculate_max_stack_quantity_with_stackable_items` | 基準20に30/40を採用し、上限64を超えても総数量90とID102/103。 |
| I39-10 | S | R | `TestItemStackingDomainServiceStacking::test_calculate_max_stack_quantity_with_non_stackable_items` | 実集約の適合判定から基準10+候補20+15=45、非互換ID106を除外しID105/107。 |
| I39-11 | S | R | `TestItemStackingDomainServiceStacking::test_plan_merge_empty_items` | plan_merge([])は3操作リストすべて空。 |
| I39-12 | S | R | `TestItemStackingDomainServiceStacking::test_plan_merge_single_item` | 単一ID108/数量10には更新・作成・削除なし。 |
| I39-13 | S | R | `TestItemStackingDomainServiceStacking::test_plan_merge_same_spec_items_within_stack_limit` | ID109/20+ID110/30を更新(109,50)、削除110、作成なしへ計画。 |
| I39-14 | S | F | `TestItemStackingDomainServiceStacking::test_plan_merge_same_spec_items_exceed_stack_limit` | ID111/30+112/40+113/25=95を更新111/64、作成同仕様31、削除112/113。 |
| I39-15 | S | F | `TestItemStackingDomainServiceStacking::test_plan_merge_multiple_specs` | 同仕様20/30は更新114/50・削除115、別仕様の耐久ID116は対象外。 |
| I39-16 | S | R | `TestItemStackingDomainServiceStacking::test_plan_merge_non_stackable_items_unchanged` | 同仕様の耐久ID117/118は全操作なし。 |
| I39-17 | V | C | `TestUpdateOperation::test_create_update_operation` | 保持先: `TestItemStackingDomainServiceCrafting::test_plan_crafting_consumption_success_single_item_each + TestItemStackingDomainServiceStacking::test_plan_merge_same_spec_items_within_stack_limit`。計算された更新ID/数量をサービスの部分消費/上限内統合で読む方が強い。宣言を削る前に実値検査の成功を確認した。 |
| I39-18 | V | R | `TestUpdateOperation::test_update_operation_immutable` | UpdateOperationの数量・対象IDへの再代入を拒否。 |
| I39-19 | V | R | `TestUpdateOperation::test_invalid_new_quantity_zero` | UpdateOperationの0は数量例外と元の値付き理由。 |
| I39-20 | V | C | `TestUpdateOperation::test_invalid_new_quantity_negative` | 保持先: `TestUpdateOperation::test_update_operation_rejects_non_positive_quantity`。同じ公開入口の入力違い。元値-1と全文理由検査を0と負数の表へ統合した。 |
| I39-21 | V | C | `TestCreateOperation::test_create_operation_without_durability` | 保持先: `TestCreateOperation::test_create_operation_retains_spec_quantity_and_durability`。耐久ありの生成保持先をNone/100の表にし、元数量5/1と両方の属性値を維持。サービスでは作れない耐久付き値型入口は残す。 |
| I39-22 | V | F | `TestCreateOperation::test_create_operation_with_durability` | CreateOperationが指定仕様・数量1・耐久100/100を保持。 |
| I39-23 | V | R | `TestCreateOperation::test_create_operation_immutable` | CreateOperationの数量と耐久値への再代入を拒否。 |
| I39-24 | V | R | `TestCreateOperation::test_invalid_quantity_zero` | CreateOperationの0を数量例外と元値付き理由で拒否。 |
| I39-25 | V | C | `TestCreateOperation::test_invalid_quantity_negative` | 保持先: `TestCreateOperation::test_create_operation_rejects_non_positive_quantity`。同じ公開入口の負数入力を0と負数の表へ統合した。 |
| I39-26 | V | C | `TestDeleteOperation::test_create_delete_operation` | 保持先: `TestItemStackingDomainServiceCrafting::test_plan_crafting_consumption_complete_consumption + TestItemStackingDomainServiceStacking::test_plan_merge_same_spec_items_within_stack_limit`。削除操作のIDは部分/全消費・上限内統合で計算された値を検査する。 |
| I39-27 | V | R | `TestDeleteOperation::test_delete_operation_immutable` | DeleteOperationの対象ID再代入を拒否。 |
| I39-28 | V | C | `TestMergePlan::test_create_merge_plan_with_operations` | 保持先: `TestItemStackingDomainServiceStacking::test_plan_merge_same_spec_items_exceed_stack_limit`。3操作を実際に計算する上限超過サービスで返された各属性の値と数量/IDを読む方が強い。 |
| I39-29 | V | C | `TestMergePlan::test_create_empty_merge_plan` | 保持先: `TestItemStackingDomainServiceStacking::test_plan_merge_empty_items`。plan_merge([])の空結果を同じ3リストで照合している。 |
| I39-30 | V | R | `TestMergePlan::test_merge_plan_immutable` | MergePlanの操作リスト属性3つの再代入を拒否。 |
| I39-31 | V | C | `TestMergePlan::test_merge_plan_with_multiple_operations` | 保持先: `TestItemStackingDomainServiceStacking::test_plan_merge_multiple_specs + test_plan_merge_same_spec_items_exceed_stack_limit`。渡したリストの長さのコピー検査。2仕様の実統合で複数更新/生成/削除の各属性の値を検査し、同仕様159行でも複数生成を通す。159行は4実体から削除3件を検査し、delete_operations[:2]への切詰めも捕捉する。 |
| I39-32 | V | C | `TestConsumedItem::test_create_consumed_item` | 保持先: `TestItemStackingDomainServiceCrafting::test_plan_crafting_consumption_success_single_item_each + test_plan_crafting_consumption_complete_consumption`。実材料から計算したID/消費量/残量を部分/全消費で検査する。負数制約と変更拒否は値型に残す。 |
| I39-33 | V | R | `TestConsumedItem::test_consumed_item_immutable` | ConsumedItemの消費量・残量を再代入できない。 |
| I39-34 | V | R | `TestConsumedItem::test_invalid_consumed_quantity_zero` | ConsumedItemの消費0は数量例外/正値要求で拒否。 |
| I39-35 | V | C | `TestConsumedItem::test_invalid_consumed_quantity_negative` | 保持先: `TestConsumedItem::test_consumed_item_rejects_non_positive_consumption`。同じ入口の負数入力を0と負数の表へ統合した。 |
| I39-36 | V | R | `TestConsumedItem::test_invalid_remaining_quantity_negative` | 消費5が正でも残量-1は非負制約で拒否。 |
| I39-37 | V | F | `TestCraftingConsumptionPlan::test_create_crafting_consumption_plan` | CraftingConsumptionPlanの消費2件/更新1件/削除1件と消費5+8=13。 |
| I39-38 | V | R | `TestCraftingConsumptionPlan::test_crafting_consumption_plan_immutable` | CraftingConsumptionPlanの消費/更新リスト属性再代入を拒否。 |
| I39-39 | V | R | `TestCraftingConsumptionPlan::test_empty_consumed_items` | 消費記録が空なら更新/削除リストの有無にかかわらず総消費0。 |

## 独立した保存確認

編集前の独立読解で、元の削除3件を最大2件の保持先へ弱める案を見つけ、159の追加行を4実体へ直した。削除を先頭2件へ切る変異は、旧側の複数操作試験と新側の159行の双方で失敗した。耐久省略時のNone、計画値の実利用先、仕様IDだけでは上限を保証できない点も修正した。

削除予定の10宣言を元の本文のまま残し、移管先と並存する46ケースの成功を確認してから退かせた。旧試験用・候補用の独立した作業場所へ同じ製品変異を入れ、全33種類をそれぞれ旧新で実行した。各変異後に製品を元のバイト列へ戻した。

- 改善9種類: 旧成功・新失敗
- 保存23種類: 旧失敗・新失敗
- 合法な対照1種類: 旧新とも成功。独立した計画リストの順だけを反転しても契約を満たす

| 種類 | 意図的な変更 | 旧 / 新 |
|---|---|---|
| 改善 | 部分消費更新に消費前数量を返す | 成功 / 失敗 |
| 改善 | 同仕様を最初の実体だけで打ち切る | 成功 / 失敗 |
| 改善 | 全消費記録の消費量を常に1へ壊す | 成功 / 失敗 |
| 改善 | 追加スタック生成を1回で止める | 成功 / 失敗 |
| 改善 | 別仕様の実体を単一グループに混ぜる | 成功 / 失敗 |
| 改善 | 計画作成中に元実体の数量も書き換える | 成功 / 失敗 |
| 改善 | 統合計画作成中に基準実体を更新する | 成功 / 失敗 |
| 改善 | 消費計画が更新対象IDを誤転記する | 成功 / 失敗 |
| 改善 | 生成操作が仕様の耐久最大を失う | 成功 / 失敗 |
| 保存 | 更新数量の保持を壊す | 失敗 / 失敗 |
| 保存 | 削除対象IDの保持を壊す | 失敗 / 失敗 |
| 保存 | 消費記録の残量を壊す | 失敗 / 失敗 |
| 保存 | 統合計画から更新リストを落とす | 失敗 / 失敗 |
| 保存 | 統合計画から作成リストを落とす | 失敗 / 失敗 |
| 保存 | 統合計画の削除リストを先頭2件へ切る | 失敗 / 失敗 |
| 保存 | 統合計画の更新リストを先頭1件へ切る | 失敗 / 失敗 |
| 保存 | 統合計画の作成リストを先頭1件へ切る | 失敗 / 失敗 |
| 保存 | 空の計画に更新操作を混入する | 失敗 / 失敗 |
| 保存 | UpdateOperationの正値制約を緩める: 0を許す | 失敗 / 失敗 |
| 保存 | UpdateOperationの正値制約を緩める: 負数を許す | 失敗 / 失敗 |
| 保存 | CreateOperationの正値制約を緩める: 0を許す | 失敗 / 失敗 |
| 保存 | CreateOperationの正値制約を緩める: 負数を許す | 失敗 / 失敗 |
| 保存 | ConsumedItemの正値制約を緩める: 0を許す | 失敗 / 失敗 |
| 保存 | ConsumedItemの正値制約を緩める: 負数を許す | 失敗 / 失敗 |
| 保存 | 生成操作の指定耐久値を失う | 失敗 / 失敗 |
| 保存 | 生成操作の省略耐久Noneを変える | 失敗 / 失敗 |
| 保存 | UpdateOperationの属性再代入を許す | 失敗 / 失敗 |
| 保存 | CreateOperationの属性再代入を許す | 失敗 / 失敗 |
| 保存 | DeleteOperationの属性再代入を許す | 失敗 / 失敗 |
| 保存 | MergePlanの属性再代入を許す | 失敗 / 失敗 |
| 保存 | ConsumedItemの属性再代入を許す | 失敗 / 失敗 |
| 保存 | CraftingConsumptionPlanの属性再代入を許す | 失敗 / 失敗 |
| 対照 | 独立操作のリスト順だけを反転しても対象ID・数量の契約は同じ | 成功 / 成功 |

## 実行した検証

| 実行 | 成功ケース | 失敗・skip |
|---|---:|---:|
| 基準2ファイル | 39 | 0 |
| 移管先と旧宣言の並存 | 46 | 0 |
| 統合後2ファイル | 36 | 0 |
| 最終2ファイル | 36 | 0 |
| 最終Itemドメイン全体 | 332 | 0 |

- Python 3.10.22で実行。各作業場所のsrcを読み込むことを検査し、通信を遮断。実LLMの呼出しなし
- 製品Python1621ファイルのハッシュ一致、先行保持先の本文一致を確認
- 対象2ファイルのruff 0.16.8とgit diff --checkが成功
- 通常CIの入口はPython3.10の `uv run --frozen pytest -n auto`。この監査内ではリポジトリ全件実行や最新main上の実行とは主張しない

通常環境での対象確認: `uv run --frozen pytest tests/domain/item/service/test_item_domain_service.py tests/domain/item/value_object/test_merge_plan.py`。関連確認: `uv run --frozen pytest tests/domain/item`。

## 履歴と別件

元試験は [e1255c6](https://github.com/Motifman/llm-rpg/commit/e1255c613bff7c0890fa1614df8b6f0c97a03310) の包括244件追加で導入された。後続は例外整理、装備種別必須化への入力追随、配置変更、import整列。今回の弱い入力を特定障害の回帰検査として追加した履歴ではなかった。製品計画サービスは [ab66552](https://github.com/Motifman/llm-rpg/commit/ab66552acea4ed5ea91f8f9ff110344f2833bdbe)、計画値型は [68dfc0f](https://github.com/Motifman/llm-rpg/commit/68dfc0f1703cfab7e55ad6ed625b488c2c34363c) で公開機能として追加されている。

状態付き実体を `can_stack_with` と候補数量計算が除外する一方、`plan_merge` が統合対象へ入れる不整合を別の最小実行で再現した。空状態対照1件は成功し、片側または両側に状態を持つ3件は対象外という既存不変条件と食い違った。入力自体は変更されず、現行ゲームの呼出経路でデータ消失が起きた証拠ではない。この監査は製品修正も、その現在挙動を正しい仕様とする試験も追加しない。修正・仕様判断は別件とする。


開始後のmain差分 `0c8f480` → `e5b2b2a24646309b365772fafce431b42041ad89` も確認した。変更はapplication/demos/presentation配下の試験14ファイルで、今回のItemドメイン332ケース・製品・依存固定ファイルとは交差しない。上記実行は固定親の上で行い、最新mainを統合しての実行はしていない。
