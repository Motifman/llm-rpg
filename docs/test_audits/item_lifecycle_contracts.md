# アイテム実体の数量・状態と通知を保持する

## 対象と結論

先行の[スタック判定監査 #1682](https://github.com/Motifman/llm-rpg/pull/1682)に続き、集約・実体・個別状態・腐敗の4試験ファイルで未監査だった元76宣言を全文確認した。判定は保持56、検査修理16、同じ集約内の保持先への統合4、単独削除0。先行で扱った元8宣言は今回の計上に含めない。

数量操作の拒否後に値が壊れても通る検査、状態の入力辞書を共有しても通る検査、先行キーだけ更新してから不正な状態値を拒否しても通る検査を修理した。使用失敗・耐久不変修理の通知抑制、最終消費の残数量、合成時の実際の生成数量、ID同一性にも独立した対照を足した。製品の振る舞いは変えていない。

編集は3試験ファイルで追加109行・削除81行（差引+28行）。腐敗の8宣言は保持した。製品・共有支援の追加削除は0行。監査文書は別計上。

## 固定基準と計上

基準は#1682の固定head `25075240c79bb81ff8765ed6a8d196582418f699`。先行監査後の4ファイルは80宣言85ケースで、このうち4宣言9ケースが先行の元8宣言を守る保持先だった。今回の変更後は76宣言87ケース。宣言統合4件で準備の重複を減らし、状態拒否の対照2行を追加した。実行件数の削減や速度改善を成果にしない。

先行の保持先4宣言は装飾子と本文をバイト単位で維持した。集約から実体へのスタック判定接続を守るサービス試験も変更せず、実集約の採用ID105/107・合計45を再実行した。

## 条件判定と入口・通知の所有者

- `ItemInstance`は直接構築、数量変更、使用結果、状態の検証と変更隔離を所有する。SQLite復元はこの直接構築を通る
- `ItemAggregate`は公開生成入口、実体への接続と使用・破損・修理・合成・腐敗イベントを所有する。イベントの内容、順序、発行抑制は実体の計算試験で代用しない
- 個別状態の片側/両側によるスタック拒否と、状態解除後の再許可は状態試験に保持する。使う側/使われる側の効果適用やSQLite保存は別の接続契約として関連実行する
- 腐敗判定はItem集約、走査・保存・確定後配送はFoodSpoilageStageとCommandScopeが所有する。境界値・既腐敗の通知抑制を所有者側に残す
- `create_by_crafting`、`repair_durability`、`get_item_info`および実体自身の比較・ハッシュ・表現について、具体的な非テスト利用は未確認。公開APIの試験として保持し、実ゲームの経路で検証済みとは称さない。ItemInstanceIdを辞書キーにする利用とも区別する

## 4宣言の統合と元入力

| 退去した宣言 | 保持先 | 保存した入力・確認 |
|---|---|---|
| test_properties_access | test_create_item_with_durability | ID24、元の仕様・耐久100/100・数量1、公開値と非破損の全5確認 |
| test_is_broken_with_none_durability | test_create_basic_item_aggregate | ID25、数量1、耐久なし、非破損。元のID1・数量5も維持 |
| test_is_broken_with_full_durability | test_create_item_with_durability | ID26、耐久100/100、数量1、非破損。元のID2と移管ID24も維持 |
| test_is_broken_with_zero_durability | test_create_item_with_broken_durability | ID27、耐久0/100、数量1、破損。元のID4も維持 |

4件とも同じ集約の生成入口を使い、独立した例外やイベントの確認は持っていなかった。保持先へ元入力を表として移し、旧宣言も残した91ケースが成功してから旧4宣言を退かせた。パラメータの名前で失敗入力を区別するが、同じテスト内で先のassertが失敗すれば後続assertを実行しないという診断上の制限はある。

## 履歴で確認した契約

- [2025-10-05の包括的item試験導入](https://github.com/Motifman/llm-rpg/commit/e1255c613bff7c0890fa1614df8b6f0c97a03310)：生成、数量、耐久、等価性、公開情報の元試験。統合4件はこの同層の重複に由来する
- [最後の1個の消費修理](https://github.com/Motifman/llm-rpg/commit/be014066df0c9a485040784bf3f9777779a521eb)：数量1→0と数量0の使用失敗を明示。実体の退行防止と集約の通知を両方残す
- [個別状態の導入](https://github.com/Motifman/llm-rpg/commit/a1125a10dfd08d988f7e2cd606ebbb3777fa036e)：入力の防御的コピー、状態付きのスタック禁止、取得情報への状態露出
- [状態検証の導入レビュー](https://github.com/Motifman/llm-rpg/commit/32e83cc453a2fc4c5c70815a1b617b6c2d4f48ce)：構築・置換・マージの全入口で非プリミティブを拒否し、失敗時には元状態を維持すると明記。逐次適用を防ぐ対照はこの契約を検査する
- [腐敗ルールの所有者移管](https://github.com/Motifman/llm-rpg/commit/efc1a252bb99b051c0ed2ff6d9fd37b4e4efcf58)と[確定後イベントへの整理](https://github.com/Motifman/llm-rpg/commit/f0066bdde41255cff3a8ea9847051eeacd0f6f77)：腐敗条件の判定と保存・通知を混同せず保持する

## 検証結果

2026-10-14、Python3.10.22、固定依存、通信遮断、認証情報を除いた環境で直列に実行。各記録で自分の作業ツリーの製品ソースを読み込んだことを確認した。実LLMや有料APIは使用していない。

| 範囲 | 結果 |
|---|---|
| 未編集基準の今回対象 | 76成功 |
| 先行#1682の保持先 | 9成功、今回の監査加点なし |
| 元宣言を残した移管段階 | 91成功 |
| 最終の主4ファイル | 87成功×2、失敗/スキップなし |
| 計画・購入・使用・SQLiteの関連 | 基準83成功、最終83成功 |
| 状態効果・腐敗・耐久等の追加関連 | 最終66成功、失敗/スキップなし |
| 製品の復元 | 22変異の各組の後、1621ファイル全てが基準hashと一致 |

16改善変異は旧4ファイル85ケースが成功し、候補87ケースは狙った追加assertで失敗した。保持5変異は旧新各7ケースを実行し、双方で変異を検出。合法な定数ハッシュは旧新とも成功し、異なるIDのハッシュ非衝突を要求していないことを確認した。各変異は同じ変更を旧新へ適用し、型の事故・収集エラー・fixture例外を成果に含めていない。

| 変異 | 旧失敗数 | 新失敗数 | 判定 |
|---|---:|---:|---|
| 合成実体の数量だけ1へ固定 | 0 | 1 | 検査修理 |
| 失敗使用にも通知 | 0 | 2 | 検査修理 |
| 最終消費の残数だけ1と誤記 | 0 | 1 | 検査修理 |
| 耐久不変でも修理通知 | 0 | 1 | 検査修理 |
| 負加算を適用してから拒否 | 0 | 2 | 検査修理 |
| 超過数量を保存してから拒否 | 0 | 1 | 検査修理 |
| 不足減算を適用してから拒否 | 0 | 2 | 検査修理 |
| 不正数量を代入してから拒否 | 0 | 1 | 検査修理 |
| 加算0拒否前に数量を0へ初期化 | 0 | 1 | 検査修理 |
| 減算0拒否前に数量を0へ初期化 | 0 | 1 | 検査修理 |
| 等価性に可変数量を混入 | 0 | 2 | 検査修理 |
| ハッシュに可変数量を混入 | 0 | 1 | 検査修理 |
| 構築状態を入力辞書と共有 | 0 | 1 | 検査修理 |
| 置換状態を入力辞書と共有 | 0 | 1 | 検査修理 |
| 検証前に元状態を消去 | 0 | 1 | 検査修理 |
| キーごとの検証と適用を交互に行う | 0 | 1 | 検査修理 |
| 破損判定を偽へ固定 | 2 | 2 | 契約保持 |
| 破損判定を真へ固定 | 5 | 5 | 契約保持 |
| 生成IDを999へ置換 | 3 | 5 | 契約保持 |
| 生成耐久を失う | 4 | 5 | 契約保持 |
| 生成数量を1へ置換 | 1 | 1 | 契約保持 |
| 合法な定数ハッシュ | 0 | 0 | 合法変更を許容 |

## 全76宣言の台帳

Rは保持、Fは契約を残した検査修理、Cは指定した保持先への統合。Rの受入先3件も元入力行と確認式の意味を保ちながら表にしている。先行の元8宣言は表の外。

| ファイル・宣言 | 判定 | 保持する契約／保持先 |
|---|---|---|
| aggregate/test_item_aggregate.py::test_create_basic_item_aggregate | R | 通常生成でID・仕様・数量5・耐久なし・非破損・イベントなしを保持 |
| aggregate/test_item_aggregate.py::test_create_item_with_durability | R | ID2・数量1・耐久100/100を集約から取得でき非破損 |
| aggregate/test_item_aggregate.py::test_create_item_with_partial_durability | R | 部分耐久50/100の生成値を保持し非破損 |
| aggregate/test_item_aggregate.py::test_create_item_with_broken_durability | R | 耐久0/100を保持し破損と判定 |
| aggregate/test_item_aggregate.py::test_create_with_invalid_durability_spec_mismatch | R | 耐久仕様なしへの耐久指定を集約入口固有の理由で拒否 |
| aggregate/test_item_aggregate.py::test_create_with_quantity_exceeding_max_stack_size | R | 集約生成で100/上限64を数量付き理由で拒否 |
| aggregate/test_item_aggregate.py::test_create_by_crafting_emits_event | F | 生成数量3の合成生成でID・仕様・数量3を含むイベント1件と耐久なし |
| aggregate/test_item_aggregate.py::test_create_by_crafting_with_durability_max | R | 合成時に仕様由来の最大耐久100を構築 |
| aggregate/test_item_aggregate.py::test_create_from_instance | R | 既存のID7・数量10の実体を集約へ再構成 |
| aggregate/test_item_aggregate.py::test_use_item_without_durability | R | 数量5の使用で使用イベント1件に残数4と耐久なしを記録 |
| aggregate/test_item_aggregate.py::test_use_item_with_durability_not_broken | R | 耐久50の使用では耐久減少を持つ使用イベントのみ |
| aggregate/test_item_aggregate.py::test_use_item_breaks_on_use | F | 耐久1の使用で使用→破損の順に2イベントと対象IDを記録 |
| aggregate/test_item_aggregate.py::test_add_quantity | R | 集約経由で数量5に3を加えて8になる |
| aggregate/test_item_aggregate.py::test_remove_quantity | R | 集約経由で数量10から4を減じ6になる |
| aggregate/test_item_aggregate.py::test_set_quantity | R | 集約経由で数量5を15に置換する |
| aggregate/test_item_aggregate.py::test_repair_durability_emits_event | R | 耐久50を10修理すると60を含む修理イベント1件 |
| aggregate/test_item_aggregate.py::test_repair_durability_without_durability_no_effect | R | 耐久なしへの修理でイベントを作らない |
| aggregate/test_item_aggregate.py::test_repair_durability_over_max_clamps_to_max | F | 耐久95を10修理すると上限100にとどまる |
| aggregate/test_item_aggregate.py::test_quantity_operations_with_invalid_values | F | 数量5への加算-1・減算10・設定-1を各ドメイン例外で拒否 |
| aggregate/test_item_aggregate.py::test_properties_access | C | ID24・耐久100/100・数量1の公開値と非破損。保持先: test_create_item_with_durability |
| aggregate/test_item_aggregate.py::test_is_broken_with_none_durability | C | ID25・数量1・耐久なしで非破損。保持先: test_create_basic_item_aggregate |
| aggregate/test_item_aggregate.py::test_is_broken_with_full_durability | C | ID26・耐久100/100で非破損。保持先: test_create_item_with_durability |
| aggregate/test_item_aggregate.py::test_is_broken_with_zero_durability | C | ID27・耐久0/100で破損。保持先: test_create_item_with_broken_durability |
| aggregate/test_item_aggregate.py::test_events_persist_after_getting | R | 数量1の使用後に2回get_eventsしても1件残る |
| aggregate/test_item_aggregate.py::test_multiple_uses_accumulate_events | F | 数量2の2回使用で使用イベント2件が蓄積する |
| aggregate/test_item_aggregate.py::test_get_item_info_no_durability | R | 耐久なし材料の公開情報11項目を独立した期待辞書へ写す |
| aggregate/test_item_aggregate.py::test_get_item_info_with_durability_full | R | 耐久100の装備の公開情報を全項目へ写す |
| aggregate/test_item_aggregate.py::test_get_item_info_with_durability_broken | R | 耐久0をNoneにせず破損trueとともに公開情報へ写す |
| entity/test_item_instance.py::test_create_basic_item_instance | R | 直接構築した実体のID・名称・種別・上限・数量既定・説明を保持 |
| entity/test_item_instance.py::test_create_with_durability | R | 直接構築した実体の耐久最大100・現在50を保持 |
| entity/test_item_instance.py::test_use_basic_item | R | 最後の1個を使うと成功し数量0になる |
| entity/test_item_instance.py::test_use_item_with_durability | R | 耐久50の使用が成功し49になる |
| entity/test_item_instance.py::test_use_item_quantity_zero_returns_false | R | 数量0は使用失敗し0を保持 |
| entity/test_item_instance.py::test_use_broken_item | R | 破損した耐久0の品は使用失敗し耐久0を保持 |
| entity/test_item_instance.py::test_add_quantity_success | R | 数量1に5を加えて6になる |
| entity/test_item_instance.py::test_invalid_quantity_negative | R | 直接構築の数量-1を拒否 |
| entity/test_item_instance.py::test_invalid_durability_without_spec_max | R | 上限1だが耐久仕様なしの実体へ耐久を渡すと拒否 |
| entity/test_item_instance.py::test_invalid_durability_max_mismatch | R | 仕様最大100と耐久最大200の不一致を拒否 |
| entity/test_item_instance.py::test_add_quantity_zero | F | 数量1への加算0を拒否 |
| entity/test_item_instance.py::test_add_quantity_negative | F | 数量1への加算-1を拒否 |
| entity/test_item_instance.py::test_add_quantity_over_max | F | 数量1に64を足す上限64超過を拒否 |
| entity/test_item_instance.py::test_remove_quantity_success | R | 数量1→加算5→減算3で3になる |
| entity/test_item_instance.py::test_remove_quantity_zero | F | 数量1への減算0を拒否 |
| entity/test_item_instance.py::test_remove_quantity_insufficient | F | 数量1から2の減算を拒否 |
| entity/test_item_instance.py::test_equality | F | 同じ実体IDは等しく、異なるIDは等しくない |
| entity/test_item_instance.py::test_hash | F | 同じ実体IDのハッシュ一致と集合重複排除 |
| entity/test_item_instance.py::test_repr | R | 公開表現へ型名・ID・名称・数量を含める |
| entity/test_item_instance.py::test_invalid_quantity_over_max_stack_size | R | 直接構築の数量15/上限10を値付き理由で拒否 |
| entity/test_item_instance.py::test_durability_item_must_have_max_stack_size_one | R | 上限1・仕様最大100と一致する耐久品を直接生成できる |
| test_item_instance_state.py::test_default_state_is_empty_dict | R | 状態省略時は空辞書 |
| test_item_instance_state.py::test_state_initial_value_can_be_set | F | 構築時のlitとcharges_remainingを保持 |
| test_item_instance_state.py::test_state_property_returns_defensive_copy | R | 取得状態の値変更・キー追加が実体へ影響しない |
| test_item_instance_state.py::test_replace_state_swaps_entire_dict | F | a/bの既存状態をcだけに置換する |
| test_item_instance_state.py::test_merge_state_overwrites_keys_and_adds_new | R | litを上書きしchargesを残しextraを追加する |
| test_item_instance_state.py::test_create_with_initial_state | R | 集約createでlit=Falseを実体へ渡す |
| test_item_instance_state.py::test_aggregate_replace_state | R | 集約入口でaを消してbだけへ置換する |
| test_item_instance_state.py::test_aggregate_merge_state | R | 集約入口でaを残しbを追加する |
| test_item_instance_state.py::test_get_item_info_includes_state | R | 公開情報にlit/chargesを含める |
| test_item_instance_state.py::test_two_empty_state_instances_can_stack | R | 空状態同士はスタック可能 |
| test_item_instance_state.py::test_one_side_with_state_disallows_stacking | R | 片側だけ状態ありでも両方向で拒否 |
| test_item_instance_state.py::test_both_with_state_disallows_stacking_even_when_equal | R | 同じ非空状態同士でもスタック拒否 |
| test_item_instance_state.py::test_non_primitive_value_in_constructor_rejected | R | 構築でdatetime値を専用例外と理由で拒否 |
| test_item_instance_state.py::test_non_primitive_value_in_replace_state_rejected | F | 置換でobject値を専用例外で拒否 |
| test_item_instance_state.py::test_non_primitive_value_in_merge_state_rejected | F | マージでlist値を拒否し元のlit状態を維持 |
| test_item_instance_state.py::test_non_str_key_rejected | R | 状態の整数キーを型別理由で拒否 |
| test_item_instance_state.py::test_all_primitive_types_accepted | R | str/int/float/bool/Noneの全5種を保持 |
| test_item_instance_state.py::test_replace_state_with_empty_dict_makes_stackable_again | R | 状態ありで拒否し空へ置換後に再許可する |
| test_item_instance_state.py::test_durable_instance_can_have_state | R | 耐久80とenchantment状態が共存する |
| aggregate/test_item_spoilage.py::test_no_spoils_after_ticks_leaves_state_unchanged | R | 腐敗設定なしではUNCHANGED・空状態 |
| aggregate/test_item_spoilage.py::test_first_call_records_acquired_at_without_spoiling | R | 初回tick3を記録しACQUIRED_AT_RECORDED・未腐敗 |
| aggregate/test_item_spoilage.py::test_existing_acquired_at_tick_is_not_overwritten | R | 取得tick10を次tick11で保持し未腐敗 |
| aggregate/test_item_spoilage.py::test_before_threshold_does_not_spoil | R | 取得0・閾値8のtick7は未腐敗 |
| aggregate/test_item_spoilage.py::test_exact_threshold_marks_newly_spoiled | R | tick8で腐敗し個体・仕様・名称・tick付きイベント1件 |
| aggregate/test_item_spoilage.py::test_beyond_threshold_marks_newly_spoiled | R | tick20でも腐敗する |
| aggregate/test_item_spoilage.py::test_already_spoiled_is_unchanged | R | 腐敗済みをtick100で再通知せず保持する |
| aggregate/test_item_spoilage.py::test_non_int_acquired_at_returns_invalid_without_state_change | R | 取得時刻badをINVALID_ACQUIRED_ATとして状態不変 |

## 再実行と残る境界

主対象は `tests/domain/item/aggregate/test_item_aggregate.py`、`tests/domain/item/entity/test_item_instance.py`、`tests/domain/item/test_item_instance_state.py`、`tests/domain/item/aggregate/test_item_spoilage.py`。通常の `uv run --frozen pytest` にこの4パスを渡して再実行できる。CIは通常収集へ自動的に含み、Python3.10の `uv run --frozen pytest -n auto` を通る。CI設定・依存固定は変更していない。

- 全リポジトリの成功は局所結果から推定しない。公開後の正確なheadのCI確認が別途必要
- 親#1682は未マージの固定依存。最新mainでの実行をこの結果で代用しない。所有者・利用元・依存・CIなど61ファイルが00ae基準と同一である静的比較は別途行った
- 状態付きの品をplan_mergeがまとめる疑義、計画APIの廃止、SQLite trade codecの状態保存対象は今回の製品修理に含めない
- 属性の再代入拒否から内部リストの深い不変性を推論しない。既存イベント/状態/数量の独立契約を短さだけで削除しない
