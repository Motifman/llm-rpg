# 品目授受の数量・宛先・前検証を守る

## 目的と基準

元の6ファイル51宣言を全文確認し、保持27、検査修理19、統合5、単独削除0とした。既定数量の同じ入力、抽選と授受の繰り返しを表へまとめる一方、個数だけでなく指定品目と宛先を照合し、動的な名前・明示対象・不足時の無変更を確かめる。製品の挙動を変える変更ではない。

固定親は [#1763](https://github.com/Motifman/llm-rpg/pull/1763) の `41c56aedfdf43f42988044726d35a02ad7d0e98c`、対応するローカル基準は `1818a71e442ca704e6bc2de97e815b40d65b558f`、treeは `cc6ca7c0afb2935aa910fbeb7869035d47a99b95`。親に含まれる [#1688](https://github.com/Motifman/llm-rpg/pull/1688) の承認済み備蓄対象修正はそのまま残し、この変更の製品差分は0。

親の相互作用94宣言の保持先168件と備蓄対象6件は関連試験として使うが、今回の51宣言へ二重計上しない。別の記憶機能削除やItemの監査枝は取り込まない。

## 最新mainとの関係

2026-10-14 15:32 UTC時点の最新main `e5b2b2a24646309b365772fafce431b42041ad89` は、直前の `0c8f480dde980c18577a7d5033996a40a947c19a` からアプリケーション・デモ・表示層の試験14ファイルだけが変わっていた。今回の6ファイルと関連305件の対象パスには交差がなく、製品・domain試験・uv.lockの変更もない。これは差分の読み取り照合であり、最新mainを統合した全体試験の成功を意味しない。上記の実行結果は固定親に対する検証である。

## 所有境界と導入理由

- `WorldGraphEffectService.apply_effects` が品目の付与・削除列を返す。`handlers/items.py` と `item_transfer.py` が品目名・数量・宛先を解決し、`plan_item_removals` は変更前の削除要求を返す
- `SpotInteractionService` の物体・宣言済み操作は、実体状態や抽選を始める前に行為者の全削除数を確認する。`PlayerInteractionApplicationService` は行為者・対象者を別々に確保し、結果も別の所持品へ反映する
- `SpotInteractionApplicationService` と `spot_inventory_helpers` は未予約の実体だけを数え、全量を確保してから消費する。装備・予約・重複実体・古くなった削除計画は `tests/application/world_graph/test_item_quantity_integration.py` が所有する
- `LootTableAggregate.roll` と実メモリ内リポジトリを使い、指定表の当選品目と数量が付与列へ渡ることを確認する。確率分布そのものはItem側で検査し、ここに複製しない
- `ScenarioLoader` の `parse_required_quantity` は、作者の必要数0・負数・整数へ変換できない文字列を拒否する。数値文字列、小数、真偽値の現行受理範囲を厳格化する変更は含めない

導入履歴も確認した。数量は [fbf3bcba](https://github.com/Motifman/llm-rpg/commit/fbf3bcbae19fba0cb3527ab34f1edc0c45dec3fb) と未配線拒否の [9afb1009](https://github.com/Motifman/llm-rpg/commit/9afb10090080af3314ab0d1ce8314ca6b36d99fd)、投入は [7dec38ad](https://github.com/Motifman/llm-rpg/commit/7dec38add6f8fe70798411f7c021dd719d379408)、不足時の先行状態変更防止は [aa329748](https://github.com/Motifman/llm-rpg/commit/aa329748ecc9eb4c2585f949fa010c032a306122) に由来する。

二者間の品目名は [1db21d9b](https://github.com/Motifman/llm-rpg/commit/1db21d9bb2a1b48a580b0d1be1369870e3e08e1a)、宛先分離は [f9ff9235](https://github.com/Motifman/llm-rpg/commit/f9ff923557232ea1ffcbf51fa7f12de59b734d06)、共通所持判定は [22d422ff](https://github.com/Motifman/llm-rpg/commit/22d422ff0b3927e0953502db412563e71983e1df)。抽選表の欠落時にも警告して他効果を続ける判断は [b9a60e43](https://github.com/Motifman/llm-rpg/commit/b9a60e43ab0a558f8aefbbe56dcc9bf4512b487d)、乱数源の分離は [4ef625a0](https://github.com/Motifman/llm-rpg/commit/4ef625a0a6ab5310afd0e71718532d26e348c5dd) に対応する。

## 第二読で戻した保持判断

`TestTargetHasItem.test_delegates_target_ownership_to_common_evaluator` は、呼出形状だけを見る重複として統合候補にしていた。しかし `docs/design_decisions.md` §75は共通評価器への委譲を設計契約として明記している。正条件だけを直接の集合所属判定へ戻す退行は、実評価を使う試験と否定条件の評価不能試験では見逃せる。

独立した第二読でこの点を指摘され、元宣言の構文木を無変更のまま保持した。共通評価不能を普通の未所持へ潰さない2行も残した。「モックがある」という見た目だけで削らない。

## 統合した層と保持先

全6ファイルを残す。試験専用の製品入口や共有支援ファイルの削除はなく、低価値な繰り返しだけを整理する。

| 統合元 | 保持先 | 保持した入力・検査 |
|---|---|---|
| 抽選の `test_times_two_2` | `TestBasicLootDrop.test_selected_table_grants_exact_items` | 表1、品目100、数量1、times=2の元入力。完全な `(100,100)` は元の品目別個数検査を含む |
| 抽選の `test_min_max_quantity_grant` | 同上 | 表1、品目100、数量3、times省略の元入力。完全な3個の列を確認 |
| `TestHasItemRequiredQuantity.test_default_required_quantity_is_one` | 同クラスの `test_required_quantity_one_with_counts_none_passes_via_frozenset_fallback` | 必要数・countsとも省略、所持7、成立Trueという完全同一入力と断言 |
| 対象REMOVEの単独試験 | `TestTargetPlayerItemBuckets.test_transfers_keep_actor_and_target_buckets_separate` | 対象REMOVE7だけの行を保持。行為者削除列は空 |
| 行為者GIVEの単独試験 | 同上 | 行為者GIVE7だけの行を保持。対象付与列は空 |

元の抽選1回試験と複合授受試験はFとして同じ保持表へ改名した。元の単独2入力・組合せ入力を残し、逆方向の授受も別品目で確かめる。統合元を残した81件が成功し、5組の保存変異が旧宣言と保持先の双方で落ちたことを確認してから元の重複宣言を除いた。統合後は46宣言74件。

## 51宣言の台帳

Rは保持、Fは当該宣言の検査修理、Cは保持先へ統合。Fの件数を「旧試験が見逃した退行数」とは呼ばない。以下の位置は編集前の6ファイルを基準とする。

### test_deposit_item_to_object_effect.py

| 元の宣言と行 | 判定 | 検出契約と扱い |
|---|---|---|
| `TestDistributedDeposit::test_two_players_deposit_two_plus_one_then_light_condition_passes` (85) | R | 2人が2個と1個を預けた状態と点火成立を連続実行し、所持だけではなく蓄積量を使う。保持先: 同宣言 |
| `TestDistributedDeposit::test_holding_three_without_deposit_does_not_satisfy_light_condition` (122) | R | 所持3個だけでは空の台を点火できず、必要量と現在量を返す。保持先: 同宣言 |
| `TestDepositQuantityConsistency::test_requested_three_with_two_owned_removes_and_increments_two` (140) | R | 要求3・所持2の切詰めで消費予約2個と蓄積2個が一致する。保持先: 同宣言 |
| `TestDepositQuantityConsistency::test_all_moves_every_owned_item_and_leaves_no_remainder` (166) | F | allの4個消費と既存1への加算5を保持。別物体を明示した行も加え、操作元への誤加算を防ぐ。保持先: 同宣言。旧暗黙対象行を保持 |
| `TestDepositQuantityConsistency::test_missing_state_key_starts_from_zero` (192) | R | 新しいstateキーは0起点。既存キーを失わない。保持先: 同宣言 |
| `TestDepositQuantityConsistency::test_zero_owned_does_not_touch_object_state` (217) | R | 所持0は消費予約も状態変更もしない。保持先: 同宣言 |
| `TestObjectStateIntAtLeast::test_threshold_missing_and_non_int_semantics` (263) | R | 閾値ちょうど・1不足・キー不在・非整数の4行と説明文。仕様説明の1不足を0扱いとする誤記のみ正す。保持先: 同宣言 |

### test_effect_item_removal_preflight.py

| 元の宣言と行 | 判定 | 検出契約と扱い |
|---|---|---|
| `TestEffectItemRemovalPreflight::test_item_state_is_unchanged_when_removal_is_insufficient` (85) | F | 不足時に実ItemAggregateを変えない。単独REMOVEに加えて分割REMOVE・COMBINEの合算、物体入口、足りる対照を追加。保持先: 同宣言を数量の前検証表へ拡張 |
| `TestEffectItemRemovalPreflight::test_player_state_is_unchanged_when_removal_is_insufficient` (105) | R | 不足を後段に書いてもプレイヤー状態は不変。保持先: 同宣言 |
| `TestEffectItemRemovalPreflight::test_loot_roll_is_not_started_when_removal_is_insufficient` (125) | R | 不足時は抽選Repository問い合わせを開始しない。既存の負対照は本番抽選の入口を閉じるので有効。保持先: 同宣言 |
| `TestEffectItemRemovalPreflight::test_deposit_without_counts_stops_before_player_state_change` (147) | R | DEPOSITのcounts未配線は先行プレイヤー状態変更前に型付き例外と原因文で停止。保持先: 同宣言 |
| `TestEffectItemRemovalPreflight::test_deposit_without_counts_stops_before_loot_roll` (176) | R | DEPOSITのcounts未配線は先行抽選問い合わせ前に停止。保持先: 同宣言 |

### test_give_from_loot_table_effect.py

| 元の宣言と行 | 判定 | 検出契約と扱い |
|---|---|---|
| `TestBasicLootDrop::test_single_entry_table_item_rendered` (72) | F | 単一表の付与をanyではなく全品目列で確認。3元入力を表へまとめ、別の表IDを選ぶ対照を追加。保持先: TestBasicLootDrop::test_selected_table_grants_exact_items |
| `TestBasicLootDrop::test_times_two_2` (85) | C | times=2、数量1の2個付与。元入力をそのまま表の1行へ移す。保持先: TestBasicLootDrop::test_selected_table_grants_exact_items |
| `TestBasicLootDrop::test_min_max_quantity_grant` (101) | C | times省略、数量3の3個付与。元入力をそのまま表の1行へ移す。保持先: TestBasicLootDrop::test_selected_table_grants_exact_items |
| `TestSilentSkip::test_repository_uninjected_silent_skip` (121) | F | Repository未注入時は付与なし。警告と後続メッセージ効果継続まで確かめる。保持先: 同宣言 |
| `TestSilentSkip::test_loot_table_id_unregistered_silent_skip` (130) | F | 未登録ID999では付与なし。警告と後続効果継続も確認。保持先: 同宣言 |
| `TestSilentSkip::test_loot_table_id_invalid_silent_skip` (139) | F | 非整数IDでは付与なし。警告と後続効果継続も確認。保持先: 同宣言 |
| `TestSeededLootDrop::test_same_seed_grants_the_same_items` (163) | R | 同じ種は同じ列、異なる種は異なる列。注入乱数が無視・固定される退行を検出。保持先: 同宣言 |
| `TestSeededLootDrop::test_module_random_does_not_change_the_result` (175) | R | モジュール乱数の変更が注入乱数へ混ざらない。確定的な独立性契約。保持先: 同宣言 |

### test_item_quantity_semantics.py

| 元の宣言と行 | 判定 | 検出契約と扱い |
|---|---|---|
| `TestGiveItemQuantity::test_default_quantity_is_one` (43) | R | GIVEのquantity省略は指定品目1個。保持先: 同宣言 |
| `TestGiveItemQuantity::test_quantity_n_grants_n_instances` (57) | R | GIVEのquantity=3は指定品目3個。保持先: 同宣言 |
| `TestGiveItemQuantity::test_negative_quantity_yields_zero_grants` (71) | R | 負数量は付与0。保持先: 同宣言 |
| `TestGiveItemQuantity::test_zero_quantity_yields_no_grant` (84) | R | 数量0は付与0。負数とは独立境界。保持先: 同宣言 |
| `TestGiveItemQuantity::test_invalid_quantity_string_falls_back_to_one` (97) | F | 不正quantityの既定1は個数だけでなく指定品目7そのものを返す。保持先: 同宣言 |
| `TestRemoveItemQuantity::test_quantity_n_queues_n_removals` (114) | F | REMOVEのquantity=2は個数だけでなく指定品目7を2個返す。保持先: 同宣言 |
| `TestRemoveItemQuantity::test_default_quantity_is_one` (127) | F | REMOVEのquantity省略は指定品目7を1個返す。保持先: 同宣言 |
| `TestHasItemRequiredQuantity::test_default_required_quantity_is_one` (163) | C | required_quantity省略・counts省略・所持7の同一入力を後述互換試験が既に持つ。保持先: TestHasItemRequiredQuantity::test_required_quantity_one_with_counts_none_passes_via_frozenset_fallback |
| `TestHasItemRequiredQuantity::test_required_quantity_n_passes_when_owned_n` (178) | R | 要求2・所持2の等号成立。保持先: 同宣言 |
| `TestHasItemRequiredQuantity::test_required_quantity_n_fails_when_owned_less` (195) | R | 要求3・所持2の不足と作者文面。保持先: 同宣言 |
| `TestHasItemRequiredQuantity::test_required_quantity_two_with_counts_none_raises` (214) | R | 要求2なのにcountsなしは未配線例外。単なる不足へ潰さない。保持先: 同宣言 |
| `TestHasItemRequiredQuantity::test_required_quantity_one_with_counts_none_passes_via_frozenset_fallback` (233) | R | 数量既定1では古いfrozenset入力が使える。統合元と入力・assertが同一。保持先: 同宣言 |
| `TestRequiredQuantityScenarioLoader::test_negative_required_quantity_rejected` (254) | F | ScenarioLoaderはrequired_quantity=0を拒否。名称を正し負数・intへ変換できない文字列も同じ表で確かめる。保持先: TestRequiredQuantityScenarioLoader::test_nonpositive_or_invalid_required_quantity_rejected |
| `TestHasItemsRequiredQuantity::test_each_spec_must_meet_required_quantity` (304) | R | HAS_ITEMSは2品目の要求2を同時に満たすと成立。保持先: 同宣言 |
| `TestHasItemsRequiredQuantity::test_one_spec_below_required_fails` (326) | F | HAS_ITEMSは1種不足で拒否。最後の品目だけを見る退行に備え不足品目の順序を反転した行も追加。保持先: 同宣言 |

### test_target_item_vocabulary.py

| 元の宣言と行 | 判定 | 検出契約と扱い |
|---|---|---|
| `TestTargetHasItem::test_passes_when_target_owns_the_fixed_item` (73) | F | 対象の固定品目が成立する実評価。元の7/行為者空集合と別品目8/行為者7を比較し、所持集合と品目両方の配線を守る。保持先: 同宣言 |
| `TestTargetHasItem::test_delegates_target_ownership_to_common_evaluator` (81) | R | §75/22d422ffが共通核への委譲を独立した設計契約として定める。正条件だけ直書きmembershipへ戻す退行は実評価では捕捉できないため呼出検証も保持。保持先: 同宣言・無変更 |
| `TestTargetHasItem::test_fails_with_a_learnable_message_when_target_lacks_it` (106) | F | 対象が品目7を持たない通常拒否。元行と行為者だけが持つ行、具体的理由を確認。保持先: 同宣言 |
| `TestTargetHasItem::test_rejects_when_target_inventory_was_not_provided` (115) | F | 対象の所持未配線は拒否。否定条件でも未所持と見なして通さない行を追加。保持先: 同宣言 |
| `TestTargetHasItem::test_reads_the_spec_id_from_interaction_parameters` (127) | F | 実行時品目選択。元item_spec_id=7と任意キー・別ID・固定値の囮で名前と値と優先順位を独立に確認。保持先: 同宣言 |
| `TestTargetHasItem::test_fails_when_the_named_parameter_is_absent` (139) | R | 動的条件の参照キー欠落は通常拒否と理由を返す。保持先: 同宣言 |
| `TestTargetHasNoItem::test_passes_when_target_does_not_own_it` (156) | R | TARGET_HAS_NO_ITEMの対象未所持は成立。保持先: 同宣言 |
| `TestTargetHasNoItem::test_evaluation_failure_is_not_inverted_to_satisfied` (165) | R | 共通評価不能2種は否定反転せず例外停止。共通核が返す失敗を入力する独立の境界契約。保持先: 同宣言 |
| `TestTargetHasNoItem::test_fails_when_target_owns_it` (195) | R | TARGET_HAS_NO_ITEMの対象所持は拒否。保持先: 同宣言 |
| `TestRuntimeItemSelectionEffect::test_give_item_reads_spec_id_from_named_parameter` (217) | F | 動的GIVEは指定名の品目。旧行に任意キーと固定値の囮を追加しREMOVEにも同じ品目選択契約を通す。保持先: TestRuntimeItemSelectionEffect::test_transfer_reads_spec_id_from_named_parameter |
| `TestRuntimeItemSelectionEffect::test_fixed_item_spec_id_still_works` (227) | R | 固定品目8とACTOR明示の既存記法。保持先: 同宣言 |
| `TestRuntimeItemSelectionEffect::test_missing_named_parameter_raises_instead_of_granting_nothing` (237) | F | 動的キー欠落は例外なら何でもよいという検査をやめ、GIVE/REMOVEのInteractionEffectValidationExceptionとキー名を確認。保持先: 同宣言 |

### test_target_player_item_effects.py

| 元の宣言と行 | 判定 | 検出契約と扱い |
|---|---|---|
| `TestTargetPlayerItemBuckets::test_remove_item_on_target_goes_to_target_bucket` (85) | C | 対象REMOVE7だけの行為者バケット空を、複合授受の表へ元単独入力のまま移す。保持先: TestTargetPlayerItemBuckets::test_transfers_keep_actor_and_target_buckets_separate |
| `TestTargetPlayerItemBuckets::test_give_item_on_actor_still_goes_to_actor_bucket` (97) | C | 行為者GIVE7だけの対象バケット空を、複合授受の表へ元単独入力のまま移す。保持先: TestTargetPlayerItemBuckets::test_transfers_keep_actor_and_target_buckets_separate |
| `TestTargetPlayerItemBuckets::test_take_pattern_splits_into_two_buckets` (108) | F | 元の対象REMOVE7＋行為者GIVE7、元単独2入力を保持し、逆方向(行為者REMOVE・対象GIVE)も別品目で4列すべて検査。保持先: TestTargetPlayerItemBuckets::test_transfers_keep_actor_and_target_buckets_separate |
| `TestTargetPlayerMissing::test_raises_instead_of_falling_back_to_actor` (131) | F | 対象不在REMOVEの型付き拒否を保持し、GIVEにも同じ拒否を確認。保持先: 同宣言 |

## 検証結果

2026-10-14、Python3.10.22。各実行で対象作業木自身の `src` を読み込んだことを確認し、認証情報・プロキシを除いた環境でネットワークを禁止した。品質確認用・実API試験は通常の選択規則で除外した。

| 対象 | 変更前 | 変更後 |
|---|---:|---:|
| 投入効果 | 10成功 | 11成功 |
| 削除前検証 | 5成功 | 10成功 |
| 抽選表効果 | 8成功 | 9成功 |
| 数量規則 | 15成功 | 17成功 |
| 対象品目の語彙 | 13成功 | 21成功 |
| 二者の品目列 | 4成功 | 6成功 |
| 対象合計 | 55成功 | 74成功 |
| 関連 | 305成功 | 305成功 |

関連は親94の保持先7ファイル、備蓄対象、アプリケーションの数量・削除配線、Itemの状態・集約・実体・抽選集約、投入と対人のシナリオ読込。関連初回のパス誤記による収集0の1試行は成功件数へ含めず、実在する対象へ修正して実行した。

CIはPython3.10の `uv run --frozen pytest -n auto`、Ruff、型検査などで実行される。通常のpytest収集対象なので個別登録の変更は不要。ローカルのリポジトリ全件実行は行っておらず、公開後の正確なheadに対するCI確認とは区別する。

### 意図的な製品変更による検出力の確認

24種の一時変更を旧新で比較し、計48実行した。改善17組は毎回、旧全55件が成功し、候補全74件の狙った断言または例外期待が失敗した。保存5組は統合前の候補81件で元宣言と保持先の双方が同じ変更を検出し、追加の保存2組は最終候補74件でも検出した。

| 一時変更 | 旧→新の失敗数 | 検出箇所 |
|---|---:|---|
| 明示投入先を操作元へ固定 | 0→1 | 明示先の蓄積が1のままで5にならない |
| 複数効果の削除計画を最後の効果だけにする | 0→2 | 分割REMOVEの不足を物体/宣言済み両入口で見逃す |
| COMBINEの入力を削除計画から落とす | 0→2 | 合成材料不足を両入口で見逃す |
| 抽選表をID1へ固定 | 0→1 | 指定表9の品目108・6個を返せない |
| 抽選失敗の警告をdebugへ降格 | 0→3 | 未注入・未登録・不正IDの警告水準 |
| 抽選不成立で後続効果も打ち切る | 0→3 | 後続メッセージが消える |
| 条件の参照キーを固定 / 固定品目を優先 | 各0→1 | 任意キーの対象品目を選べない |
| 授受の参照キーを固定 / 固定品目を優先 | 各0→2 | GIVE/REMOVEの任意キーを選べない |
| 動的品目欠落を一般ValueErrorへ変更 | 0→2 | 指定したドメイン例外を返さない |
| 対象GIVEを行為者へ送る / 対象なしGIVEを許す | 各0→1 | 4列の宛先分離 / 対象不在の例外期待 |
| HAS_ITEMSの最後の品目だけを見る | 0→1 | 最初の品目不足を見逃す |
| 必要数の負数 / 変換不能文字列を許す | 各0→1 | ScenarioLoaderが拒否しない |
| 対象の所持未配線を否定条件の成立へ倒す | 0→1 | TARGET_HAS_NO_ITEMでも拒否する |

保存5組は、抽選回数の固定（旧1/併存3失敗）、当選数量の固定（1/3）、対象削除先の取り違え（2/5）、行為者付与先の取り違え（7/10）、旧frozenset入力の無視（2/2）。元C5の各入力と保持先が失敗した位置も個別に確認した。

追加の保存対照は、削除品目の取り違え（旧2/候補9失敗）と正条件だけの共通評価器バイパス（1/1）。後者は保持した元R宣言が未呼出しの `call_args` を参照した箇所で失敗した。収集・準備失敗ではないが、断言失敗とは区別して記録する。削除品目の取り違えでは、指定品目列の断言だけでなく、正しい所持数がある成功対照の不当拒否も検出する。

全実行で収集・準備エラーは0。各変更を元のバイトへ戻し、旧新両作業木の製品1618ファイルのSHA-256一致を確認してから最終74件・305件を実行した。途中で一時ディスクが満杯になったが実行中の変異48実行は正常完了し、終了後にこの監査だけの再生成可能なキャッシュを整理した。証拠原本は保持し、最終試験は別の空き領域で実行した。

対象Ruffと `git diff --check` も成功。試験は1431行から1462行（198追加・167削除、差引31行）となり、共有支援ファイルと製品の差分は0。速度改善や削減行数を成果とはしない。

## 所有規約と引き継ぎ

- 品目授受の数量は返却列の品目・個数・行為者/対象者を合わせて確認する。個数だけの断言で品目の取り違えを通さない
- 動的名の試験では従来キーだけを使わず任意キーと別値を置く。固定値も併記し、実行時指定の優先を独立に確かめる
- 不足時の前検証は実体を本当に変更する効果と抽選入口を使い、拒否だけでなく無変更・未開始を確認する。所持数が足りる対照も持つ
- 警告付き継続は警告水準・原因と、後続効果の実行を確認する。logger名や全文を固定しない
- 数量の予約とItemのスタック適合性は別所有者。[#1682](https://github.com/Motifman/llm-rpg/pull/1682) / [#1764](https://github.com/Motifman/llm-rpg/pull/1764) の耐久品数量0・仕様ID・満杯・実集約サービス接続と、状態付きスタック拒否は別の保持契約として残す
- 今回の基準失敗は0で、製品修理は0。状態効果24宣言など残る領域は別監査へ引き継ぐ
