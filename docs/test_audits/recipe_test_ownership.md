# レシピ・ドメインテストの所有者整理

## 要点

レシピ関連5ファイルの全85宣言を読み、同じ集約の処理を再試験する5宣言を既存の所有者テストへ集約した。サービスファイルで集約を直接呼んでいた混合種類の合算試験1件は、入力・順序・期待値を変えず集約ファイルへ移した。異なるIDならハッシュも必ず異なるという過剰条件1行も取り除いた。本番コードは変更していない。

材料一覧の返却リストを変更しても元の材料が失われない保証、集約IDによる同一性、サービス本来の候補選択16件、3値型の別契約36件を残した。RecipeIngredientとRecipeResultは似た実装でも別の型と検証境界であり、片方の試験で代用しない。

## 範囲と変更規模

| 項目 | 変更前 | 変更後 |
|---|---:|---:|
| 主対象テストファイル | 5 | 5 |
| テスト宣言・収集ケース | 85 | 80 |
| 主対象5ファイルの行数 | 1325 | 1248 |
| うちファイル内fixture | 12宣言・164行 | 12宣言・164行 |
| 専用支援ファイル | 0 | 0 |
| 本番所有者5ファイル | 337行 | 337行 |

編集した試験は2ファイルで31行追加・108行削除、純減77行。集約ファイルは28宣言のまま（重複1削除・1移入）、サービスファイルは21→16宣言、RecipeId・RecipeIngredient・RecipeResultは14/11/11宣言で未変更。fixture行数は総行数の内数である。

本番や試験支援の公開口を追加・削除する必要はなかった。独立契約を残した結果として本番変更は0行であり、削減数のためにサービスや値型の存続判断へ範囲を広げていない。

## 所有者と保持先

1. 生成結果の重複：旧 `TestRecipeAggregate.test_create_valid_recipe_aggregate` の6検証は同じfixtureを使う `test_properties_access` にすべて含まれる。保持先はID・名称・説明・材料件数・完成品ID/数量に加え、各材料の内容と返却リストの変更隔離も確認する
2. ハッシュ：`test_equality_different_recipe` のID非等値は保持し、hash非等値だけを削除した。同じIDなら名称や説明が異なっても等価で同じhashとなる `test_equality_same_recipe` も保持した
3. サービスファイルの末尾4件：実際にはRecipeDomainServiceを呼ばず `RecipeAggregate.calculate_available_quantities` を直接呼んでいた。単一スタック、異なる種類、同種複数、空入力の各検証は、集約ファイルの同じ入力・期待値の4件を保持先とした
4. 混合種類の合算：`test_calculate_inventory_quantities_mixed_specs` は元の関数本文をそのまま移動した。ItemInstanceId 1/2/3/4、木材5・石3・木材2・石1という順序と、2キー・木材7・石4という期待値を保存した

| サービス側で退かせた試験 | 集約側の保持先 |
|---|---|
| test_calculate_inventory_quantities_single_item | test_calculate_available_quantities_single_item |
| test_calculate_inventory_quantities_multiple_different_items | test_calculate_available_quantities_multiple_different_items |
| test_calculate_inventory_quantities_same_spec_multiple_items | test_calculate_available_quantities_same_spec_multiple_items |
| test_calculate_inventory_quantities_empty_inventory | test_calculate_available_quantities_empty_inventory |

## 実利用と履歴の確認

固定点は上流 `0b51eb28d4692635a932dcf4063ab9b231768bf0`。対象ファイル全文、所有者、呼び出し先、関連する保存・検索の入口、CIと履歴を照合した。

- RecipeAggregateは入力検証、公開材料一覧の変更隔離、合成可否、不足量、所持数合算、ID同一性を所有する
- ItemDomainServiceは材料一覧から消費計画を作る。RecipeInfoQueryServiceは保存層から取得した公開値をDTOへ写す。材料/完成品値の保持を単なる属性コピーとしてすべて消してはいけない
- InMemoryRecipeRepositoryはRecipeIdを辞書キーにし、完成品と材料の索引を持つ。SQLiteの復元処理はRecipeId・RecipeIngredient・RecipeResultを構築し、保存処理はIDの整数変換を使う
- RecipeDomainServiceは定義と再公開以外の本番呼び出しを確認できなかった。これは同名のRecipeInfoQueryServiceの呼び出しと区別した。サービス全体の廃止判断は別課題として保留し、本来の検索・候補選択契約16件を残した
- 5ファイルは [e1255c6](https://github.com/Motifman/llm-rpg/commit/e1255c613bff7c0890fa1614df8b6f0c97a03310) のitem向け244件の包括的試験追加で導入された。その後の履歴は例外整理、装備種別必須化へのfixture追随、src-layout移行、import整列。対象の重複やhash非等値を個別障害の再発防止として追加した履歴は確認できない

[Pythonのハッシュ契約](https://docs.python.org/3.10/reference/datamodel.html#object.__hash__)は等しい値のhash一致を要求するが、異なる値の衝突禁止は要求しない。整数等と等しく扱う型の数値互換ハッシュは別の有用な契約であり、一律に削除しない。RecipeAggregateとRecipeIdは整数との等値を定義していない。

## 検証結果

測定日は2026-10-13。Python 3.10.22・pytest 8.4.1、作業場所のsrcを優先し、外部接続を遮断、認証環境変数を除去して直列実行した。外部LLM・実APIは呼ばない。

| 対象 | 変更前 | 変更後 |
|---|---|---|
| 主対象5ファイル | 85成功×2（0.20/0.14秒） | 80成功×2（0.16/0.15秒） |
| 関連3ファイル | 41成功（0.69秒） | 41成功（0.52秒） |
| 対象2ファイルのruff | 基準検査は未実施 | 成功 |
| git diff --check | 成功 | 成功 |
| 本番ソース差分 | 0 | 0 |

初回候補実行も80成功（0.17秒）。表の変更後主試験は、全変異を復元した後の2回である。関連41件は、ItemDomainServiceの材料消費計画7件とスタック処理9件、RecipeInfoQueryService19件、SQLiteRecipeRepository6件。主対象の所有者試験とは分けて数え、これらの層は編集していない。

表の時間はpytest表示値。起動を含む実時間は主試験変更前0.492/0.514秒、変更後0.439/0.486秒、関連変更前1.013秒・変更後0.897秒。試験自体が短く測定回数も少ない。初期基準実行と最終実行では表示の冗長度も異なるため、速度改善を主張しない。リポジトリ全体の試験やGitHub CIの成功を示すものでもない。

## 変異による保持契約の確認

集約所有者へ以下の6変異を1件ずつ一時適用し、旧・新の2試験ファイルへ計12回、直列で実行した。旧49件・新44件の対象を毎回確認し、各変異後に本番原文と候補テストをバイト一致で復元した。すべて意図したassertの失敗であり、収集失敗やfixture例外ではない。

| 変異 | 旧試験 | 新試験 | 新側で確認できた契約 |
|---|---|---|---|
| 全レシピのhashを定数0にする（合法） | 赤 | 緑 | 不要な衝突禁止だけを外せた |
| hashをインスタンスの参照IDにする（不正） | 赤 | 赤 | 同じ集約IDの等値ハッシュ |
| 同種数量を加算せず後のスタックで上書きする | 赤 | 赤 | 同種複数スタックと混合種類の合算 |
| 再登場した種類に他種類の累積値を混ぜる | 赤 | 赤 | 移したmixed_specsだけが両側で赤 |
| 材料一覧から内部リストを直接返す | 赤 | 赤 | test_properties_accessの変更隔離 |
| 構築検証後に説明を消去する | 赤 | 赤 | 生成結果の保持先test_properties_access |

混合種類への累積混入は、初登場の別種類や同種だけのインベントリでは通る変異にした。旧側ではサービスファイル、移動後は集約ファイルの同じmixed_specs試験が唯一の失敗となり、元の組合せを保持した意味を確認した。

## 再現用の対象

```bash
uv run --frozen pytest   tests/domain/item/aggregate/test_recipe_aggregate.py   tests/domain/item/service/test_recipe_domain_service.py   tests/domain/item/value_object/test_recipe_id.py   tests/domain/item/value_object/test_recipe_ingredient.py   tests/domain/item/value_object/test_recipe_result.py -q
uv run --frozen pytest   tests/domain/item/service/test_item_domain_service.py   tests/application/inventory/services/test_recipe_info_query_service.py   tests/infrastructure/repository/test_sqlite_recipe_repository.py -q
uv run --frozen ruff check   tests/domain/item/aggregate/test_recipe_aggregate.py   tests/domain/item/service/test_recipe_domain_service.py
git diff --check
```

実測は外部接続禁止を加えた隔離環境で行った。通常CIはPython3.10の `uv run --frozen pytest -n auto` へ流れる。

## 保留した点

- `test_find_recipes_by_ingredient_non_existing_ingredient` は「存在しない」と命名されているが、実際は石を使うレシピ1件が見つかる有用な正例。削除せず、入力に即した名称への整理を別課題として残す
- RecipeDomainService自体の非テスト利用は未確認。今回の集約所有者整理と混ぜて型・再公開を廃止しない
- RecipeId、RecipeIngredient、RecipeResultの既存契約は保持し、新しい凍結実装固定や不用意な共通化へ範囲を広げない

## 全85宣言の台帳

Rは保持（移動のみを含む）、Cは指定した既存の保持先へ集約、Fは独立契約を保持して過剰なassertを修理、Dは独立契約不要として削除する判定。集計はR79・C5・F1・D0。C5件の退去で新側80件となる。行番号は固定点の旧ファイル。全85件は変更前2回成功した。


### tests/domain/item/aggregate/test_recipe_aggregate.py（28宣言）

| 旧行 | 判定 | テスト | 契約・保持先 |
|---|---|---|---|
| 79–86 | C | `TestRecipeAggregate.test_create_valid_recipe_aggregate` | 同じfixtureのID・名称・説明・材料件数・結果ID/数量は test_properties_access:436–455 が全て包含。追加移管なし |
| 88–108 | R | `TestRecipeAggregate.test_create_recipe_with_empty_name_raises_error` | 空名称を InvalidRecipeException で拒否し、レシピID付き理由を返す。空名称許可の退行を検出 |
| 110–130 | R | `TestRecipeAggregate.test_create_recipe_with_whitespace_name_raises_error` | 空白のみの名称を拒否。単なる空文字チェックへの退行を検出 |
| 132–152 | R | `TestRecipeAggregate.test_create_recipe_with_empty_description_raises_error` | 空説明を拒否して対象レシピと理由を示す。説明検証の欠落を検出 |
| 154–169 | R | `TestRecipeAggregate.test_create_recipe_with_empty_ingredients_raises_error` | 材料なしの生成を拒否。無材料クラフトの許可を検出 |
| 171–195 | R | `TestRecipeAggregate.test_create_recipe_with_duplicate_ingredients_raises_error` | 同じItemSpecIdを2項目へ分けた材料一覧を拒否。ID単位の重複検出漏れを検出 |
| 197–204 | R | `TestRecipeAggregate.test_can_craft_with_sufficient_ingredients` | 両材料が必要量を超えると合成可。ちょうど一致しか認めない退行を検出 |
| 206–213 | R | `TestRecipeAggregate.test_can_craft_with_exact_ingredients` | 両材料が必要量ちょうどなら合成可。境界の比較演算子誤りを検出 |
| 215–222 | R | `TestRecipeAggregate.test_can_craft_with_insufficient_wood` | 最初の材料だけが1個不足なら不可。材料の一部しか判定しない退行を検出 |
| 224–231 | R | `TestRecipeAggregate.test_can_craft_with_insufficient_stone` | 後の材料だけ0個なら不可。先頭材料だけの判定を検出 |
| 233–240 | R | `TestRecipeAggregate.test_can_craft_with_missing_ingredient_spec` | 辞書に後の材料種別自体がない場合は不可。欠落種別を無視する退行を検出 |
| 242–244 | R | `TestRecipeAggregate.test_can_craft_with_empty_available_items` | 所持辞書が空なら不可。空入力の誤った真や例外を検出 |
| 246–254 | R | `TestRecipeAggregate.test_can_craft_with_extra_ingredients` | 不要な完成品を余分に持っても合成可。所持種類集合の完全一致を強いる退行を検出 |
| 256–264 | R | `TestRecipeAggregate.test_get_missing_ingredients_none_missing` | 全材料が足りていれば不足一覧は空。必要量を不足量として返す退行を検出 |
| 266–277 | R | `TestRecipeAggregate.test_get_missing_ingredients_partial_missing` | 木材1個不足のみを返す。欠ける材料の選択と差分数量の誤りを検出 |
| 279–293 | R | `TestRecipeAggregate.test_get_missing_ingredients_all_missing` | 両種類の所持0から木材2・石1を返す。一件で打ち切る退行を検出 |
| 295–306 | R | `TestRecipeAggregate.test_get_missing_ingredients_missing_spec` | 石が辞書にない場合も不足1を返す。欠落キーの扱いを検出 |
| 308–311 | R | `TestRecipeAggregate.test_calculate_available_quantities_empty_inventory` | 空インベントリの合算は空辞書。空入力時の例外・余計なキーを検出。service:404の保持先 |
| 313–325 | R | `TestRecipeAggregate.test_calculate_available_quantities_single_item` | 単一スタック木材5を同じ種別キーの数量5へ写す。種別/数量取得誤りを検出。service:343の保持先 |
| 327–345 | R | `TestRecipeAggregate.test_calculate_available_quantities_multiple_different_items` | 木材5・石3を別キーへ分ける。全種を一つへまとめる退行を検出。service:358の保持先 |
| 347–369 | R | `TestRecipeAggregate.test_calculate_available_quantities_same_spec_multiple_items` | 木材5+3+2を10へ合算する。後勝ち上書きや先頭だけの採用を検出。service:379の保持先 |
| 371–394 | R | `TestRecipeAggregate.test_equality_same_recipe` | ID同一なら名称/説明が違っても等しくハッシュも同一。全フィールド等値への退行を検出 |
| 396–419 | F | `TestRecipeAggregate.test_equality_different_recipe` | 418行の異なるID非等値を保持。419行のhash非等値だけ除去。衝突なしを要求する独立契約はない |
| 421–425 | R | `TestRecipeAggregate.test_equality_with_non_recipe_aggregate` | 文字列・整数・Noneとは非等値。同型確認を失う退行を検出 |
| 427–434 | R | `TestRecipeAggregate.test_string_representation` | 公開文字列表現に名称・材料ID/数量・完成品ID/数量が含まれる。片側の欠落を検出。外部表示経路未確認なので今回拡張/削除しない |
| 436–455 | R | `TestRecipeAggregate.test_properties_access` | 公開値の保持と、返却材料リストclear後も元の材料が残ること。内部リスト露出を検出。aggregate:79の保持先 |
| 457–485 | R | `TestRecipeAggregate.test_single_ingredient_recipe` | 材料1種類で必要量ちょうど/不足と不足数量を扱う。2種類前提の退行を検出 |
| 487–526 | R | `TestRecipeAggregate.test_large_quantity_recipe` | 木材10・石5の必要量と木材9での不足1を扱う。数量を真偽や小固定数へ潰す退行を検出 |

### tests/domain/item/service/test_recipe_domain_service.py（21宣言）

| 旧行 | 判定 | テスト | 契約・保持先 |
|---|---|---|---|
| 125–134 | R | `TestRecipeDomainService.test_find_recipes_by_result_item_existing_item` | 異なる完成品2レシピから剣のレシピだけを選択。完成品条件の取り違えを検出 |
| 136–143 | R | `TestRecipeDomainService.test_find_recipes_by_result_item_non_existing_item` | 材料としてはある鉄を完成品として検索すると空。材料検索との混同を検出 |
| 145–152 | R | `TestRecipeDomainService.test_find_recipes_by_result_item_empty_recipes` | 候補空の完成品検索は空。空リスト時の例外を検出 |
| 154–163 | R | `TestRecipeDomainService.test_find_recipes_by_ingredient_existing_ingredient` | 両レシピ共通の木材で2件を返す。最初の一致で打切る退行を検出 |
| 165–173 | R | `TestRecipeDomainService.test_find_recipes_by_ingredient_non_existing_ingredient` | 実際は石を使う1件だけを返す正例。名前/説明の不存在という表現は誤り。部分一致選択の契約を保持 |
| 175–182 | R | `TestRecipeDomainService.test_find_recipes_by_ingredient_unused_ingredient` | 完成品つるはしは材料検索では空。完成品検索との混同を検出 |
| 184–191 | R | `TestRecipeDomainService.test_find_recipes_by_ingredient_empty_recipes` | 候補空の材料検索は空。空リスト時の例外を検出 |
| 193–211 | R | `TestRecipeDomainService.test_can_player_craft_recipe_sufficient_inventory` | 実ItemAggregateの所持から合成可能を返す。集約の合算/可否への接続欠落を検出 |
| 213–231 | R | `TestRecipeDomainService.test_can_player_craft_recipe_insufficient_inventory` | 木材不足の実インベントリで不可。サービスが常に真を返す/合算を取り違える退行を検出 |
| 233–237 | R | `TestRecipeDomainService.test_can_player_craft_recipe_empty_inventory` | 実インベントリ空で不可。空集合の接続例外や誤った真を検出 |
| 239–253 | R | `TestRecipeDomainService.test_can_player_craft_recipe_missing_ingredient_type` | 石種別がない実インベントリで不可。存在する材料だけを見る退行を検出 |
| 255–280 | R | `TestRecipeDomainService.test_get_available_recipes_for_player_all_available` | 必要材料が全てあると2候補を返す。最初のレシピだけを返す退行を検出 |
| 282–306 | R | `TestRecipeDomainService.test_get_available_recipes_for_player_partial_available` | 鉄2でつるはしだけ不可、剣だけ残る。レシピごとの可否条件を混同する退行を検出 |
| 308–321 | R | `TestRecipeDomainService.test_get_available_recipes_for_player_none_available` | 木材1のみなら利用可能一覧は空。可否の否定や既定候補返却を検出 |
| 323–335 | R | `TestRecipeDomainService.test_get_available_recipes_for_player_empty_recipes` | 材料を持っていても候補が空なら空。候補を勝手に生成する退行を検出 |
| 337–341 | R | `TestRecipeDomainService.test_get_available_recipes_for_player_empty_inventory` | 候補はあるが所持空なら一覧空。空所持の扱いを検出 |
| 343–356 | C | `TestRecipeDomainService.test_calculate_inventory_quantities_single_item` | RecipeDomainServiceを呼ばず集約静的メソッドを直接呼ぶ。aggregate:313と同じ木材5→5。移管不要 |
| 358–377 | C | `TestRecipeDomainService.test_calculate_inventory_quantities_multiple_different_items` | 集約を直接呼び、aggregate:327と同じ木材5・石3→別キー。移管不要 |
| 379–402 | C | `TestRecipeDomainService.test_calculate_inventory_quantities_same_spec_multiple_items` | 集約を直接呼び、aggregate:347と同じ木材5+3+2→10。移管不要 |
| 404–408 | C | `TestRecipeDomainService.test_calculate_inventory_quantities_empty_inventory` | 集約を直接呼び、aggregate:308と同じ空→空。移管不要 |
| 410–439 | R | `TestRecipeDomainService.test_calculate_inventory_quantities_mixed_specs` | 集約所有者へ本文を変更せず移動。木材5+2→7と石3+1→4を同時に保証。種類間で累積値を共有する退行を検出 |

### tests/domain/item/value_object/test_recipe_id.py（14宣言）

| 旧行 | 判定 | テスト | 契約・保持先 |
|---|---|---|---|
| 10–13 | R | `TestRecipeId.test_create_valid_id` | 正のIDを保持。ID値の欠落を検出 |
| 15–18 | R | `TestRecipeId.test_create_from_string` | 数字文字列123を整数IDへ変換。文字列保持や変換不能を検出 |
| 20–23 | R | `TestRecipeId.test_invalid_id_zero` | IDゼロをドメイン例外で拒否。下限比較の誤りを検出 |
| 25–28 | R | `TestRecipeId.test_invalid_id_negative` | 負IDを拒否。ゼロだけ拒否する退行を検出 |
| 30–33 | R | `TestRecipeId.test_invalid_string` | 非数値abcをドメイン例外へ変換。組込み例外の露出を検出 |
| 35–38 | R | `TestRecipeId.test_invalid_string_empty` | 空の文字列をドメイン例外で拒否。空文字の既定ID化を検出 |
| 40–43 | R | `TestRecipeId.test_str_conversion` | IDの公開文字列42を保持。デバッグ表現への変化を検出 |
| 45–48 | R | `TestRecipeId.test_int_conversion` | IDの整数変換42を保持。保存処理のint(recipe_id)が壊れる退行を検出 |
| 50–58 | R | `TestRecipeId.test_equality` | 同値IDの等値・別ID/文字列の非等値。参照同一性や型混同を検出 |
| 60–69 | R | `TestRecipeId.test_hash` | 等値IDの同一ハッシュと集合重複除去。辞書キーで別インスタンスを探せなくなる退行を検出 |
| 71–75 | R | `TestRecipeId.test_immutable` | 既存IDへの再代入を拒否。辞書キーが生成後に変化する退行を検出 |
| 77–80 | R | `TestRecipeId.test_create_from_large_number` | 999999を受理。IDに不必要な小さい上限を足す退行を検出 |
| 82–85 | R | `TestRecipeId.test_create_from_string_with_spaces` | 前後空白付き123を受理。公開文字列入力の正規化退行を検出 |
| 87–90 | R | `TestRecipeId.test_create_from_string_with_newlines` | 末尾改行付き123を受理。空白をスペースだけに狭める退行を検出 |

### tests/domain/item/value_object/test_recipe_ingredient.py（11宣言）

| 旧行 | 判定 | テスト | 契約・保持先 |
|---|---|---|---|
| 16–23 | R | `TestRecipeIngredient.test_create_valid_recipe_ingredient` | 材料のIDと数量5を保持。構築時のフィールド取り違えを検出 |
| 25–31 | R | `TestRecipeIngredient.test_create_with_minimum_quantity` | 数量1を受理。下限を誤って2以上とする退行を検出 |
| 33–40 | R | `TestRecipeIngredient.test_invalid_quantity_zero` | 数量0をドメイン例外と型別理由で拒否。下限の抜けを検出 |
| 42–49 | R | `TestRecipeIngredient.test_invalid_quantity_negative` | 数量-1を拒否。ゼロだけ拒否する退行を検出 |
| 51–58 | R | `TestRecipeIngredient.test_str_representation` | 公開文字列表現でIDと数量3を結合。集約文字列から数量が落ちる退行を検出 |
| 60–70 | R | `TestRecipeIngredient.test_equality_same_ingredients` | 同じ材料ID・数量の別インスタンスが等しい。参照同一性だけの比較を検出 |
| 72–83 | R | `TestRecipeIngredient.test_equality_different_spec_id` | 数量が同じでもIDが違えば非等値。ID比較欠落を検出 |
| 85–95 | R | `TestRecipeIngredient.test_equality_different_quantity` | IDが同じでも数量が違えば非等値。数量比較欠落を検出 |
| 97–104 | R | `TestRecipeIngredient.test_equality_different_type` | 文字列・整数と非等値。同型確認欠落を検出 |
| 106–121 | R | `TestRecipeIngredient.test_hash_consistency` | 等しい2値のハッシュ一致と集合重複除去。等値/ハッシュ不整合を検出 |
| 123–135 | R | `TestRecipeIngredient.test_immutable` | 数量・種別IDの再代入を拒否。集約が共有する材料/完成品値の外部変更を検出 |

### tests/domain/item/value_object/test_recipe_result.py（11宣言）

| 旧行 | 判定 | テスト | 契約・保持先 |
|---|---|---|---|
| 16–23 | R | `TestRecipeResult.test_create_valid_recipe_result` | 完成品のIDと数量5を保持。構築時のフィールド取り違えを検出 |
| 25–31 | R | `TestRecipeResult.test_create_with_minimum_quantity` | 数量1を受理。下限を誤って2以上とする退行を検出 |
| 33–40 | R | `TestRecipeResult.test_invalid_quantity_zero` | 数量0をドメイン例外と型別理由で拒否。下限の抜けを検出 |
| 42–49 | R | `TestRecipeResult.test_invalid_quantity_negative` | 数量-1を拒否。ゼロだけ拒否する退行を検出 |
| 51–58 | R | `TestRecipeResult.test_str_representation` | 公開文字列表現でIDと数量3を結合。集約文字列から数量が落ちる退行を検出 |
| 60–70 | R | `TestRecipeResult.test_equality_same_results` | 同じ完成品ID・数量の別インスタンスが等しい。参照同一性だけの比較を検出 |
| 72–83 | R | `TestRecipeResult.test_equality_different_spec_id` | 数量が同じでもIDが違えば非等値。ID比較欠落を検出 |
| 85–95 | R | `TestRecipeResult.test_equality_different_quantity` | IDが同じでも数量が違えば非等値。数量比較欠落を検出 |
| 97–104 | R | `TestRecipeResult.test_equality_different_type` | 文字列・整数と非等値。同型確認欠落を検出 |
| 106–121 | R | `TestRecipeResult.test_hash_consistency` | 等しい2値のハッシュ一致と集合重複除去。等値/ハッシュ不整合を検出 |
| 123–135 | R | `TestRecipeResult.test_immutable` | 数量・種別IDの再代入を拒否。集約が共有する材料/完成品値の外部変更を検出 |
