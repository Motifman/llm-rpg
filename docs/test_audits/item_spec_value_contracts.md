# アイテム仕様値の拒否条件と同値性の監査

## なぜ

アイテム仕様の空の名前・空白の名前・空の説明・最大耐久0・最大耐久-1の試験は、いずれも装備種別を指定していませんでした。耐久の2件は、さらに最大スタック数も無効でした。対象の検証を外しても別条件が同じ例外を投げ、壊れた検証を見逃していました。

同じIDで属性が異なる仕様の等値確認は、隣の集合試験と完全に同じ2入力を使っていました。この1件だけを既存の集合試験へ集約します。

## 範囲と判断

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。`tests/domain/item/value_object/` の6ファイル、元の71宣言を読み、65宣言を保持（R）、5宣言の判定を修理（F）、1宣言を既存試験へ統合（C）しました。

- 試験の宣言数: 71 → 70
- パラメータを展開した実行件数: 71 → 75
- 対象6試験の行数: 728 → 746（変更は1ファイル、追加47行・削除29行）
- 製品・共通試験支援の差分: 0行。監査文書は試験行数に含めない
- ファイルの廃止: なし。削除数や速度改善を目的にしない

近隣の `ItemAggregate` / `ItemInstance` / `StackingPlan` は今回の監査数へ含めません。PR #1682が持つ集約・実体のスタック判定も変更しません。基準の関連確認で呼んだ試験を本監査の完了宣言数へ重複計上していません。

## 修理と保持先

### 別の無効条件で通っていた5件

各宣言で元の入力をそのまま表の1行として保持しました。もう1行は装備種別を `WEAPON` にし、耐久値の2件では最大スタック数を1にしました。これにより、対象の値だけが無効な場合にも拒否を検査します。空文字・空白文字・耐久0・耐久-1の元の値は変えていません。

同じ試験本体を表の両行で使い、追加行のための重複した準備や製品側の注入点を作っていません。既存の基本装備と耐久100・スタック1の正常構築も保持しました。

`test_invalid_max_stack_size_with_durability` も装備種別が未指定ですが、既存の理由文の断言が別理由の例外による成功を防ぎます。そのため修理対象へ数えていません。

### 同一IDの等値確認

削除元は `TestItemSpec.test_equality_same_spec`、保持先は同じファイルの `TestItemSpec.test_hash` です。

削除元と保持先で、完全に同じ2入力を使用しています。2仕様はID1を共有し、名前・種類・希少度・説明・最大スタック数・装備種別が異なります。保持先は等しいhashだけでなく、2つの別個体を集合へ入れた結果が1件になることを検査し、IDによる同値比較を実際に通します。追加の入力移管は不要です。

異なるID999を拒む `test_equality_different_spec` は残します。IDの異なる値に異なるhashを要求する断言は元からなく、合法的なhash衝突を禁止していません。

## 所有者と実際の利用箇所

- `Durability`: 使用量・修理量・上下限・破損判定・代入拒否を値の試験が担当。`ItemInstance.use/repair_durability` と `ItemAggregate` の通知・状態更新は別の接続契約
- `ItemInstanceId`: 所持品の辞書・予約集合と、チェスト等の入力変換で利用。文字列/整数変換、正値制約、同値集合の試験を残す
- `ItemSpecId`: `InMemoryItemSpecRepository` の辞書キー、SQLiteの検索引数、シナリオや所持品の集合で利用。IDの境界・変換・同値性の主担当を残す
- `ItemSpec`: `world_runtime` がシナリオから構築し、SQLiteの復元器も構築する。`ItemInstance.can_stack_with` が仕様の同値性を使い、装備サービスと設置サービスが種類・設置情報を使う。入力検証を値側の主担当に残す
- `MaxStackSize`: `ItemSpec` と `ItemInstance` の数量・耐久制約で利用。下限1と0/負の拒否、代入拒否を残す

`can_create_durability` と `get_equipment_type` に現行製品の直接呼出箇所はありませんが、公開APIを試験整理のついでに廃止しません。不変性は共有された仕様や値が後から変わることを防ぐ契約です。Python 3.10のdataclassesが生成する代入拒否も直接確認しました。

保存・復元の試験を値側の代わりにはしません。保存経路で属性を落とす危険と、値の入力制約を壊す危険は異なります。[#1392](https://github.com/Motifman/llm-rpg/pull/1392)では2実装の返却型を揃え、[#1398](https://github.com/Motifman/llm-rpg/pull/1398)では光源・腐敗・疲労回復の保存欠落を直しています。

## 検出力の比較

各行は同じ製品変異を旧試験と候補へ適用した結果です。変異は一時的なものです。

| 変異 | 旧試験 | 候補 |
|---|---|---|
| 名前の検証を無効化 | 対象71件が全成功 | 空と空白の追加2行が例外未送出で失敗 |
| 説明の検証を無効化 | 対象71件が全成功 | 空の説明の追加1行が例外未送出で失敗 |
| 耐久の正値検証を無効化 | 対象71件が全成功 | 0と-1の追加2行が例外未送出で失敗 |
| 名前の空白除去をやめる | 対象71件が全成功 | 空白の追加1行が例外未送出で失敗 |
| 耐久比較を `<= 0` から `< 0` へ変える | 対象71件が全成功 | 0の追加1行が例外未送出で失敗 |
| 等値比較に名前一致を追加 | 旧削除元・旧保持先を個別実行し双方失敗 | 削除後の保持先が集合2件となって失敗 |

前5種類は旧/新の10実行、同値比較は旧削除元・旧保持先・新保持先の3実行です。旧/新ごとに空の別キャッシュ領域を割り当て、バイトコードの書込みを無効化しました。読み込む作業木とソースhashを確認し、各実行後も一致を検査しています。誤った収集や準備失敗を検出成功に数えていません。

## 実行済みの検証

Python 3.10.22 / pytest 8.4.1、固定依存を使い、認証情報を除いてネットワーク接続を禁止した実行器で確認しました。実LLM・有償APIは呼んでいません。

- 未編集の対象71件、関連100件が成功
- 変更後の対象75件が成功
- 上記の13変異実行で、すべて予定した失敗または成功を確認
- 製品を元のバイト列へ戻した後、対象75件を2回、関連100件を実行し全成功
- 対象と関連の完全nodeidの交差は0。一意の実行対象は171 → 175件
- 保持65宣言の本文が元と一致。変更外の5試験ファイルも不変。5製品所有者のhash一致
- 変更試験のruff 0.16.8と `git diff --check` が成功

関連100件の範囲は次の7ファイルです。

- `tests/domain/item/aggregate/test_item_aggregate.py`
- `tests/domain/item/entity/test_item_instance.py`
- `tests/infrastructure/repository/test_item_spec_repository_contract.py`
- `tests/infrastructure/repository/test_in_memory_item_spec_repository.py`
- `tests/infrastructure/repository/test_sqlite_item_spec_repository.py`
- `tests/infrastructure/repository/test_sqlite_item_spec_state_codec.py`
- `tests/application/world/services/test_place_object_service.py`

全リポジトリの試験や性能改善は主張しません。公開先の正確なコミットでCIを確認する必要があります。自動マージは行いません。

## 全71宣言の判断

以下は基準時点の宣言です。R=保持、F=契約を保持して判定を修理、C=同じ所有者の強い試験へ統合。Fの元入力も保持しています。

### `tests/domain/item/value_object/test_durability.py`

| 宣言 | 判断 | 契約と検出対象 |
|---|---|---|
| `TestDurability::test_create_valid_durability` | R | 100/50を受理し、現在値・最大値と未破損を返す。入力を満タンへ丸める／部分耐久を破損扱いにする |
| `TestDurability::test_create_full_durability` | R | 上限ちょうど100/100を受理し未破損である。現在値>=最大値を誤って拒否する |
| `TestDurability::test_create_broken_durability` | R | 100/0を受理し破損として扱う。0を無効として拒否する／破損判定を反転する |
| `TestDurability::test_invalid_max_value_zero` | R | 最大0を専用例外で拒否する。最大0を受理する比較境界の誤り |
| `TestDurability::test_invalid_max_value_negative` | R | 最大-1を専用例外で拒否する。負の最大値を絶対値化して受理する。現在0>最大-1とも重なるが負最大で他の範囲条件を同時充足する入力は存在しないため、特定ガード行の検出と混同しない |
| `TestDurability::test_invalid_current_negative` | R | 現在-1を専用例外で拒否する。負の現在値を受理または0へ丸める |
| `TestDurability::test_invalid_current_greater_than_max` | R | 現在150/最大100を専用例外で拒否する。最大超過を受理または上限へ丸める |
| `TestDurability::test_use_success` | R | 50から10使用すると40になり成功・未破損を返す。任意使用量を無視する／成功値や減算を誤る |
| `TestDurability::test_use_to_zero` | R | 5を5使用すると0で成功し破損となる。ちょうど0に到達する使用を失敗扱いにする |
| `TestDurability::test_use_beyond_zero` | R | 3を10使用しても0へ切り詰め成功する。超過使用を拒否する／負数を返す |
| `TestDurability::test_use_already_broken` | R | 既に0なら使用失敗で0・破損を保つ。既破損の使用成功を返す |
| `TestDurability::test_use_default_amount` | R | 省略時の使用量は1で10から9になる。既定の使用量を0や2に変える |
| `TestDurability::test_repair` | R | 50を20修理すると70になる。修理量を無視する／加算を誤る |
| `TestDurability::test_repair_over_max` | R | 90を20修理すると上限100になる。上限超過のまま返す／修理を拒否する |
| `TestDurability::test_repair_default_amount` | R | 省略時の修理量は1で50から51になる。修理既定値を0や2に変える |
| `TestDurability::test_immutable` | R | 現在値への外部直接代入を拒否する。frozenを外して共有された耐久値を書換可能にする |

### `tests/domain/item/value_object/test_item_instance_id.py`

| 宣言 | 判断 | 契約と検出対象 |
|---|---|---|
| `TestItemInstanceId::test_create_valid_id` | R | 下限1の識別子を受理し値を保持する。下限1を不正扱いする／値を0基準へずらす |
| `TestItemInstanceId::test_create_from_string` | R | 文字列123から整数123を作れる。文字列を変換せず保存する／文字列入力を拒否する |
| `TestItemInstanceId::test_invalid_id_zero` | R | 識別子0を専用例外で拒否する。正値条件を>=0へ緩める |
| `TestItemInstanceId::test_invalid_id_negative` | R | 識別子-1を専用例外で拒否する。負数を有効IDとして受理する |
| `TestItemInstanceId::test_invalid_string` | R | abcを専用例外で拒否する。変換失敗を組込みValueErrorのまま流す／無効IDへ補完する |
| `TestItemInstanceId::test_str_conversion` | R | 42の表示文字列は42である。repr形式や接頭辞を外部表示へ漏らす |
| `TestItemInstanceId::test_int_conversion` | R | 42から整数42へ変換できる。SQLiteへ渡す整数変換を失う／値をずらす |
| `TestItemInstanceId::test_equality` | R | 同値1は等しく2と文字列1は異なる。識別子の値比較・型境界を壊す |
| `TestItemInstanceId::test_hash` | R | 同値IDのhashが一致し集合で重複除去できる。同値なのに異hashとなり辞書検索・集合判定が破綻する。異値hashの衝突禁止は要求しない |

### `tests/domain/item/value_object/test_item_spec.py`

| 宣言 | 判断 | 契約と検出対象 |
|---|---|---|
| `TestItemSpec::test_create_basic_item_spec` | R | 基本装備仕様の入力値、耐久未指定、装備判定と装備種別取得を保持する。既定の耐久を勝手に付ける／装備種別を失う。can_create_durabilityとget_equipment_typeは現在の製品直接呼出元なしだが公開APIの独立契約 |
| `TestItemSpec::test_create_with_usage_hint` | R | 作者のusage_hintを仕様に保持する。用途文を既定Noneへ落とす |
| `TestItemSpec::test_create_with_category` | R | QUESTのまま作者分類LOREを保持する。categoryをItemTypeへ混同して変換または消す |
| `TestItemSpec::test_usage_hint_rejects_whitespace_only` | R | 空白だけのusage_hintを専用例外で拒否する。空の用途表示を受理する |
| `TestItemSpec::test_create_with_durability_max_valid_stack_size` | R | 耐久100・最大スタック1の装備仕様を受理する。全耐久品を拒否する／耐久値を失う |
| `TestItemSpec::test_invalid_name_empty` | F | 空の名前を拒否する。旧試験はequipment_type=Noneも無効なので名前検証を除いても同型例外で通る |
| `TestItemSpec::test_invalid_name_whitespace` | F | 空白だけの名前を拒否する。旧試験はequipment_type=Noneも無効なので空白検証を除いても同型例外で通る |
| `TestItemSpec::test_invalid_description_empty` | F | 空の説明を拒否する。旧試験はequipment_type=Noneも無効なので説明検証を除いても同型例外で通る |
| `TestItemSpec::test_invalid_durability_max_zero` | F | 最大耐久0を拒否する。旧試験はstack=10かつequipment_type=Noneも無効なので耐久の正値検証を除いても同型例外で通る |
| `TestItemSpec::test_invalid_durability_max_negative` | F | 最大耐久-1を拒否する。旧試験はstack=10かつequipment_type=Noneも無効なので耐久の正値検証を除いても同型例外で通る |
| `TestItemSpec::test_invalid_max_stack_size_with_durability` | R | 耐久100と最大スタック10の組合せを拒否しその理由を示す。耐久とスタックの整合検証を除く。装備種別も未指定だが理由文の断言が別ガードによる偽陽性を防ぐ |
| `TestItemSpec::test_invalid_equipment_without_equipment_type` | R | 装備品で装備種別未指定を拒否しその理由を示す。装備種別必須を外す |
| `TestItemSpec::test_invalid_non_equipment_with_equipment_type` | R | 非装備品で装備種別指定を拒否する。消費品を装備枠に通す |
| `TestItemSpec::test_create_consumable_item` | R | 効果未指定の消費品を受理し装備扱いしない。全消費品に効果を必須にする／装備判定の逆転 |
| `TestItemSpec::test_create_consumable_item_with_consume_effect` | R | 消費品がHealEffect(50)を保持する。許された効果を消す／数量を取り違える |
| `TestItemSpec::test_invalid_consume_effect_for_non_consumable_raises` | R | 非消費品へのconsume_effect設定を拒否する。MATERIALの効果を受理して誤使用可能にする |
| `TestItemSpec::test_create_equipment_items_different_types` | R | HELMETとARMORも装備品として受理する。WEAPON以外を非装備扱いする／装備種別を一律固定する |
| `TestItemSpec::test_equality_same_spec` | C | 同一IDなら名前・種別・希少度・説明・最大数が異なっても同値。比較を全属性や名前へ変えてしまう。test_hashは完全に同じ2仕様を作り、等hashと集合要素数1によって同じ等値契約を包含する |
| `TestItemSpec::test_equality_different_spec` | R | 同じ他属性でもIDが999なら異なる仕様である。IDを無視して全仕様同値／名前だけで同値とする |
| `TestItemSpec::test_hash` | R | 同じIDの異属性仕様は等hashで集合内の1件にまとまる。hashを属性依存にする／等値を属性依存にする。異値hash不等性は要求しておらず合法衝突を許容 |
| `TestItemSpec::test_immutable` | R | 仕様名の外部直接書換えを拒否する。frozenを外し共有仕様の表示や索引を後から壊せるようにする |
| `TestItemSpecPlaceable::test_placeable_with_valid_object_type` | R | 設置可能CHESTを受理し設置判定と種類を返す。設置可能を常にFalseにする／設置種別を落とす |
| `TestItemSpecPlaceable::test_placeable_doer_sign_switch` | R | DOOR/SIGN/SWITCH/GATEを設置種類として受理する。有効種類の一部を誤って削る。既存4入力のループを維持 |
| `TestItemSpecPlaceable::test_non_placeable_default` | R | 設置情報を省略すると設置不可で種類None。既定で設置可能になる／種類を誤補完する |
| `TestItemSpecPlaceable::test_placeable_without_object_type_raises` | R | 設置可能なのに種類Noneなら拒否し理由を示す。種類必須条件を除く／Noneを有効扱いする |
| `TestItemSpecPlaceable::test_placeable_with_empty_object_type_raises` | R | 設置可能なのに種類空文字なら拒否する。空文字を設置種類として受理する。必須と許可集合の二重拒否は同じ入力の契約を壊さない限り削除理由にしない |
| `TestItemSpecPlaceable::test_placeable_with_invalid_object_type_raises` | R | 未許可INVALID_TYPEを拒否し理由を示す。任意文字列を有効なワールド種類とみなす |
| `TestItemSpecPlaceable::test_non_placeable_with_object_type_raises` | R | 設置不可でCHEST種類を指定した矛盾を拒否する。非設置品に設置先情報を残して通す |

### `tests/domain/item/value_object/test_item_spec_id.py`

| 宣言 | 判断 | 契約と検出対象 |
|---|---|---|
| `TestItemSpecId::test_create_valid_id` | R | 下限1の識別子を受理し値を保持する。下限1を不正扱いする／値を0基準へずらす |
| `TestItemSpecId::test_create_from_string` | R | 文字列123から整数123を作れる。文字列を変換せず保存する／文字列入力を拒否する |
| `TestItemSpecId::test_invalid_id_zero` | R | 識別子0を専用例外で拒否する。正値条件を>=0へ緩める |
| `TestItemSpecId::test_invalid_id_negative` | R | 識別子-1を専用例外で拒否する。負数を有効IDとして受理する |
| `TestItemSpecId::test_invalid_string` | R | abcを専用例外で拒否する。変換失敗を組込みValueErrorのまま流す／無効IDへ補完する |
| `TestItemSpecId::test_str_conversion` | R | 42の表示文字列は42である。repr形式や接頭辞を外部表示へ漏らす |
| `TestItemSpecId::test_int_conversion` | R | 42から整数42へ変換できる。SQLiteへ渡す整数変換を失う／値をずらす |
| `TestItemSpecId::test_equality` | R | 同値1は等しく2と文字列1は異なる。識別子の値比較・型境界を壊す |
| `TestItemSpecId::test_hash` | R | 同値IDのhashが一致し集合で重複除去できる。同値なのに異hashとなり辞書検索・集合判定が破綻する。異値hashの衝突禁止は要求しない |

### `tests/domain/item/value_object/test_item_spec_spoilage.py`

| 宣言 | 判断 | 契約と検出対象 |
|---|---|---|
| `TestItemSpecSpoilsAfterTicks::test_none_spoilage_is_accepted_as_unspoilable_item` | R | QUESTでも腐敗Noneを受理し腐らない仕様を表す。Noneを0や必須数値へ変える |
| `TestItemSpecSpoilsAfterTicks::test_documented_behavior` | R | QUESTでも腐敗8を受理し保持する。腐敗をCONSUMABLE専用にする／期間を取り落とす |
| `TestItemSpecSpoilsAfterTicks::test_rejects_zero` | R | 腐敗0を専用例外で拒否する。<=を<へ変えて即時腐敗を受理する |
| `TestItemSpecSpoilsAfterTicks::test_rejects_negative_value` | R | 腐敗-1を専用例外で拒否する。負の腐敗期間を受理する |

### `tests/domain/item/value_object/test_max_stack_size.py`

| 宣言 | 判断 | 契約と検出対象 |
|---|---|---|
| `TestMaxStackSize::test_create_valid_stack_size` | R | 最大64をそのまま受理する。最大数を1や固定値へ丸める |
| `TestMaxStackSize::test_create_stack_size_one` | R | 下限1を受理する。1を不正扱いして非スタック品の構築を壊す |
| `TestMaxStackSize::test_invalid_stack_size_zero` | R | 最大0を専用例外で拒否する。0枠の仕様を受理する |
| `TestMaxStackSize::test_invalid_stack_size_negative` | R | 最大-1を専用例外で拒否する。負の枠数を受理する |
| `TestMaxStackSize::test_immutable` | R | 最大数の外部代入を拒否する。共有仕様のスタック上限を書換可能にする |

## 履歴と保持の根拠

- [値と仕様の導入](https://github.com/Motifman/llm-rpg/commit/68dfc0f1703cfab7e55ad6ed625b488c2c34363c): 不変性と構築時の検証を持つ公開値として導入
- [ID値の導入](https://github.com/Motifman/llm-rpg/commit/9abf54acb434e627e7d915de5e273bcfc6251871): 正値・変換・同値性を持つ識別子。ItemSpecIdの例外型はこの時点からItemInstanceIdValidationExceptionで、名称だけで変更しない
- [装備種別必須への既存試験追従](https://github.com/Motifman/llm-rpg/commit/814cc10a8cac1ef7ee01d20f26b4e2ed95a33baf): 周辺試験の装備種別を追加。今回の負例は別条件でも落ちるため追従漏れが表面化しなかった
- [腐敗期間の導入](https://github.com/Motifman/llm-rpg/commit/708303aea77b31c12ce2e176fa752438e5edd9f6): Noneは腐らない仕様、正の期間はQUESTにも許可する判断。現行4宣言を保持
- [用途文の導入](https://github.com/Motifman/llm-rpg/commit/1077e733b79a20032664f82411e7371d5d45c529): 作者の用途文を保持して表示へ渡す契約
- [作者分類の導入](https://github.com/Motifman/llm-rpg/commit/a42a2d53bca74a41588e19be481027f5aa0eecd9): categoryをItemTypeと別軸に保ち、誤った用途表示を防ぐ契約

最大耐久が負のDurabilityは、現在値との範囲条件とも衝突しますが、その値域で他条件をすべて満たす入力は存在しません。特定の検証行を通ることと公開契約を混同しないため、今回のF5とは分けて保持しました。同様に設置種類の空文字は許可集合にも含まれませんが、空文字の拒否という公開契約を保持しています。
