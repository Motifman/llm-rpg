# 部屋と物体の知覚・公開値保持の試験監査

## 結果

- 基準main: `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`（2026-10-14）
- 8ファイル85宣言を全読し、保持71・修理12・統合2・単純削除0。変更後は83宣言
- 夜・天候の試験に重複していた既定引数の2宣言だけを、同じ公開APIを既に検査する照明の主試験へ集約した
- 選択する対象、登録順、境界値、状態を保つ範囲、正負の対照を12宣言で補強した。元の入力と期待値は保持した
- 製品と共通準備は変更していない。試験7ファイルは追加125・削除47行、対象全8ファイルは1124→1202行。文書は別計上
- 未編集の対象101件・関連24件が成功。元の統合対象を残した110件成功後に2宣言を除去し、全復元後は対象108件＋関連24件＝132件成功
- 16種類の故障を旧新32実行で対照。修理対象14種類は旧の焦点試験が通り、新しい焦点試験が意図した判定で失敗した。統合対象2種類は移管前の元試験と保持先、移管後の保持先が同じ故障を検出した

## 責任分担

照明の基本則・通常物体の視認閾値・知覚文は `test_spot_perception_service.py`、夜と天候の合成は `test_spot_perception_night_weather.py` が主担当となる。照明と光源を渡し、屋外・夜・天候の追加引数を省略した既定挙動も基本則の試験で保持する。

物体の公開状態を選ぶ一般規則は `entity/test_spot_object_visible_state.py`、規則の入力拒否は `value_object/test_state_display_rule.py`、閲覧者と読了・状態条件の組合せは `test_spot_object_perception.py` に置く。物体が見えるかと、視覚的な細部を読めるかは別の判断なので、照明の列挙値が同じでも統合しない。

雰囲気の部分更新は `aggregate/test_spot_graph_update_atmosphere.py`、内部構造の集合操作は `test_spot_interior_entity.py`、ノードに渡す値と屋外の既定は `test_spot_node_step2.py` が主担当となる。小さい構築試験や既定値を、外見だけで削除しない。

JSON宣言から効果を適用し、同室・別室へ通知する保証は `tests/demos/test_world_runtime_change_atmosphere_effect.py` に残す。痕跡の実表示は `test_vents_move_the_impostor_unseen.py::TestRecentVentTrace`、燃料圧計の分数表示と解除は `test_station_drill_fuel_freeze_emergency.py::test_pressure_gauge_shows_world_minutes_only_during_the_emergency` に残す。SQLiteの符号化・復号と世界snapshotの復元も別契約であり、この監査へ移管・加算しない。

今回退役するファイルや製品の試験専用入口はない。既存の配置・通路・音・移動の主試験も移さない。

## 統合した2宣言

| 元の宣言（夜・天候） | 残す宣言（照明の基本則） | 同じ入力と判定 |
|---|---|---|
| `TestBackwardCompat.test_kwarg` | `TestEffectiveLighting.test_bright_unchanged` | 追加の引数を省略、BRIGHT・光源なし→BRIGHT |
| `TestBackwardCompat.test_dark_spot_dim` | `TestEffectiveLighting.test_dark_with_light_becomes_dim` | 追加の引数を省略、DARK・光源あり→DIM |

元の準備では音・匂いに空文字、温度にNORMALを与えていたが、照明計算はそれらを参照しない。既定引数を通る同じ照明契約であり、別の危険を検査する層ではなかった。保持先の成功を元試験の削除前に確認し、故障対照でも検出力を確かめた。

## 修理した12宣言

| 宣言 | 補った判定 |
|---|---|
| `test_unspecified_fields_are_preserved` | 現状はtemperature/smell/sound_intensity/hazard_descriptionが既定で、巻戻しを見逃す。各項目に異なる非既定値を置き、更新後の全項目と更新前の値を検査する |
| `test_state_display_exact_match_wins_over_at_least_rule` | 完全一致が先に登録された入力しかない。下限→完全一致/完全一致→下限の両順を同じ主試験で検査する |
| `test_state_display_uses_largest_matching_at_least_threshold` | 下限3→5の昇順だけなので最後の一致を使う退行を見逃す。両登録順と5/6の境界値を同じ主試験へ加える |
| `test_resolved_flag_suppresses_a_recent_deadline_display` | 解決フラグ指定のある規則を常に隠しても成功する。同じ規則でフラグなし/無関係フラグの表示を先に確かめ、解決フラグのみ消す |
| `test_recent_visual_trace_is_hidden_without_light` | requires_light規則を照明に関係なく常に隠しても通る。同じ規則のBRIGHT/DIM正対照を既存表へ追加する |
| `test_replace_object` | 単一要素では全オブジェクトを置換する退行を検出できない。無関係物体と非空の他集合を置き、対象だけの差替え・元値の保持を検査する |
| `test_ground_item_same_instance` | 現状は同じ値を再送し長さしか見ない。同一実体IDで別specの値を再送し、先行値と別IDの品を保持することを検査する |
| `test_returns_find_ground_item_instance` | 単一要素では先頭品を無条件返却しても通る。複数品から先頭以外をID指定で引く |
| `test_find_ground_item_none` | 空集合だけでは不一致IDを無視する退行を検出できない。別IDの品がある集合でも欠落IDはNoneと検査する |
| `test_with_interior_and_atmosphere` | is not Noneだけでは指定値を既定の別インスタンスに替えても通る。内部構造を非空にし、渡した値が等しく保持されることを検査する |
| `test_requires_read_and_state_both_needed` | 状態は常にunlocked=Trueで、状態条件を無視しても通る。同じ読了者についてunlocked=Falseとキー欠落を加え、基本説明のままと検査する |
| `test_dim_unchanged` | 説明は光源有無に無関係だがFalseしか通さない。Trueも既存宣言の表で検査し、明るさをBRIGHTへ上げる退行を検出する |

空の内部構造、他項目が既定の雰囲気、同じ地面アイテムの再追加、単一要素の探索、空集合の欠落探索、count=6で昇順に登録した下限の入力も残した。照明痕跡の試験名だけは、正負の4行に合わせて `test_recent_visual_trace_is_only_shown_with_light` へ改名した。

## 履歴と境界

- 知覚と読了者の公開契約: [1fd28d8](https://github.com/Motifman/llm-rpg/commit/1fd28d8b817e287f074f8c1d8fc5a315813f4caf)
- 屋外の夜・天候の減光: [972ce82](https://github.com/Motifman/llm-rpg/commit/972ce82e07a3a1e927e287f1a3323b5ab613e055)
- 雰囲気更新が未接続だった問題と部分更新の判断: [133ac15](https://github.com/Motifman/llm-rpg/commit/133ac15befd2ef353bed7e0a9cd2a2d4e2414bab)
- 地面集合の重複防止と探索: [11e30f2](https://github.com/Motifman/llm-rpg/commit/11e30f2e393e84737e094cc757860df84f108c5a)
- 生の状態値を作者文言へ変える規則と型の区別: [eb2cde0](https://github.com/Motifman/llm-rpg/commit/eb2cde064532ba3509d6f431cd5eb0eaf93279b9)
- 累積材料の最大下限表示: [0a82a7c](https://github.com/Motifman/llm-rpg/commit/0a82a7c169ccff21cdaf91b99c1eeb0022198bcc)
- 記録手番の非公開判断を書込側へ移した回帰: [1bb9cee](https://github.com/Motifman/llm-rpg/commit/1bb9cee16fed2688311a96b35184fa714fee71ba)
- 通気口の物理的な使用痕跡: [48822f8](https://github.com/Motifman/llm-rpg/commit/48822f83e4df2aa58ebd2eab32e7287185c04882)
- 燃料凍結の残時間と解決旗: [14a1f09](https://github.com/Motifman/llm-rpg/commit/14a1f09077d503f9dd9e774b61786a90629a70d8)

`within_ticks` は世界の物体に残る使用痕跡や警告の期間であり、エピソード記憶の保持期間ではない。現在手番・照明・世界フラグから表示を導く。#1694の再解釈撤去やSNSの投稿配信・画面参照の変更とは、所有者と公開入口を共有しない。

`with_detail_read` の本番からの直接呼出は現在の検索では見つからず、同梱シナリオにもrequires_read宣言は見つからなかった。ただし読了者集合は `SpotGraphCurrentStateBuilder` が説明選択に使い、`SpotInteriorSubsystemCodec.capture/restore` が世界snapshotの動的フィールドとして保存・復元する。導入履歴の公開契約と復元入力が残るため削除しない。今回の部品試験を、実際の読む行為まで接続済みという保証にはしない。

地面アイテムの実体IDによる追加・除去・探索は、#1682の積重ね判断や#1688の備蓄条件の対象選択とは別である。製品所有者を共有する#1735/#1736や音・移動の監査とは、異なるメソッドの試験だけを変更する。

## 故障対照と検証

| 意図的な故障 | 旧焦点 | 新焦点 |
|---|---|---|
| 照明更新で非指定の匂いを消す | 0失敗/1件 | 1失敗/2件 |
| 対象以外の物体も置換する | 0失敗/1件 | 1失敗/2件 |
| 物体置換で側の集合を空にする | 0失敗/1件 | 1失敗/2件 |
| 同一実体IDの品を再送値へ上書きする | 0失敗/1件 | 1失敗/1件 |
| IDを無視して先頭の品を返す | 0失敗/2件 | 2失敗/2件 |
| 指定された内部構造を空へ替える | 0失敗/1件 | 1失敗/2件 |
| 指定された雰囲気をBRIGHTへ替える | 0失敗/1件 | 2失敗/2件 |
| 読了後の状態条件を無視する | 0失敗/1件 | 1失敗/1件 |
| 登録順で先の一致を選ぶ | 0失敗/1件 | 1失敗/2件 |
| 最大下限でなく最後の下限を選ぶ | 0失敗/1件 | 2失敗/4件 |
| 下限ちょうどを除外する | 0失敗/1件 | 2失敗/4件 |
| 解決旗の定義があれば常に隠す | 0失敗/1件 | 1失敗/1件 |
| 視覚痕跡を照明に関係なく隠す | 0失敗/2件 | 2失敗/4件 |
| DIMを光源ありでBRIGHTへ上げる | 0失敗/1件 | 1失敗/1件 |
| 既定BRIGHTをDIMへ替える | 2失敗/2件 | 1失敗/1件 |
| 光源ありのDARKを補光しない | 2失敗/2件 | 1失敗/1件 |

ここで旧焦点が通るとは、対応する元の宣言がその故障を検出しなかったという意味であり、旧リポジトリ全体がその故障で通るという主張ではない。各回は製品実装へ故障を入れ、同じ対象で旧新を対照し、元バイトへ必ず復元した。収集エラーや準備中の例外を検出成功として数えていない。

Python3.10.22 / pytest8.4.1、固定依存、秘密値を継承せず外部接続を遮断する実行器で検証。対象のsrcからimportしたことを毎回確認した。基準・保持先確認・復元後の成功実行に失敗/収集エラー/skipは0。Ruff 0.16.8と `git diff --check` も成功した。

`git ls-files src tests` が列挙する追跡済み3176ファイル（Python3158、その他18のシナリオJSON・説明・シェル）を元と候補で基準と比較し、元は差分0、候補の製品は差分0、変更は予定の試験7ファイルだけと確認した。独立第二読で全85宣言を再確認し、候補の保持71宣言は構文木不変、統合2以外の宣言削除なしを確認した。

通常CIはPython3.10の `uv run --frozen pytest -n auto` で実行し、quality/live_apiは既定から除外される。今回全リポジトリ試験・実LLM・有償APIはローカルで実行していない。公開後の正確な先端のCIは別途確認する。速度改善や製品不具合の修理は主張しない。

## 全85宣言の台帳

Rは保持、Fは同じ契約の修理、Cは保持先への統合。C2以外の保持先は同じ宣言（上記の改名1件を除く）。パラメーター表は宣言として1件と数え、元の全行を残した。

### `tests/domain/world_graph/aggregate/test_spot_graph_update_atmosphere.py`

| 判定 | 宣言 | 検出する退行 |
|---|---|---|
| R | `TestUpdateSpotAtmosphere.test_lighting_is_replaced` | 照明を更新しない、または指定値DARKを別値へ取り違える |
| F | `TestUpdateSpotAtmosphere.test_unspecified_fields_are_preserved` | 照明更新に伴い非指定の音・危険度を初期化する |
| R | `TestUpdateSpotAtmosphere.test_hazard_level_and_description_are_replaced` | 危険度または危険説明の適用を省略する |
| R | `TestUpdateSpotAtmosphere.test_spot_without_atmosphere_gains_one` | 雰囲気Noneのスポットを更新不能にする |
| R | `TestUpdateSpotAtmosphere.test_spot_without_atmosphere_gets_bright_when_lighting_is_unspecified` | 雰囲気Noneから危険度だけを更新すると明るさがBRIGHT以外になる |
| R | `TestUpdateSpotAtmosphere.test_unknown_spot_raises` | 未知スポットへの更新を黙って無視・追加する |
| R | `TestUpdateSpotAtmosphere.test_no_field_specified_leaves_atmosphere_untouched` | 更新指定なしで既存の雰囲気値を初期化する |

### `tests/domain/world_graph/entity/test_spot_object_visible_state.py`

| 判定 | 宣言 | 検出する退行 |
|---|---|---|
| R | `TestVisibleState.test_returns_full_state_by_default` | 非公開指定なしの通常キーを落とす |
| R | `TestVisibleState.test_excludes_hidden_keys` | 非公開キーが公開stateへ混入する |
| R | `TestVisibleState.test_does_not_mutate_original_state` | 表示のための除外が元オブジェクトまたは渡された辞書を破壊する |
| R | `TestVisibleState.test_hides_available_when_true` | 正常なavailable=Trueを生値で表示する |
| R | `TestVisibleState.test_renders_available_false_as_recovery_hint` | available=Falseが生値になり標準の復帰ヒントが消える |
| R | `TestVisibleState.test_uses_author_defined_unavailable_hint` | 作者指定の復帰ヒントを標準値で上書きする |
| R | `TestVisibleState.test_hides_a_recorded_tick_key_listed_in_hidden_state_keys` | 記録キーを非公開集合で伏せなくなる。綴りによる特殊扱いの再導入は次の正対照が検出する |
| R | `TestVisibleState.test_a_tick_looking_name_alone_does_not_hide_anything` | last_harvest_tickという名前だけで値を伏せ、書込側の非公開導出漏れを覆い隠す |
| R | `TestVisibleState.test_rejects_empty_unavailable_hint` | 空白の復帰ヒントを受理し、手掛かりの無い表示になる |
| R | `TestVisibleState.test_state_display_rule_renders_matching_value_as_tag` | 一致する値を作者文言へ変換せず生値で漏らす |
| R | `TestVisibleState.test_state_display_value_mismatch_remains_raw` | 完全一致しない値を誤変換するか隠して宣言漏れを見えなくする |
| F | `TestVisibleState.test_state_display_exact_match_wins_over_at_least_rule` | 完全一致より下限規則を優先する |
| F | `TestVisibleState.test_state_display_uses_largest_matching_at_least_threshold` | 最大でない下限を選ぶ |
| R | `TestVisibleState.test_state_display_without_matching_at_least_rule_remains_raw` | 下限未達の値を近い表示へ丸める、または隠す |
| R | `TestVisibleState.test_state_display_at_least_does_not_treat_bool_as_int` | Trueを整数1として下限規則に当てる |
| R | `TestVisibleState.test_state_display_for_available_overrides_legacy_unavailable_hint` | availableの明示規則より旧復帰ヒントを優先する |
| R | `TestVisibleState.test_hidden_state_key_suppresses_state_display_rule` | 通常の表示規則がhidden指定を迂回し第三者へ漏れる |
| R | `TestVisibleState.test_recent_hidden_tick_renders_only_the_author_text` | 期限ちょうどの痕跡を早期に消す、または内部手番を公開する |
| R | `TestVisibleState.test_recent_tick_disappears_after_the_declared_window` | 期限を過ぎた痕跡または内部手番が残る |
| R | `TestVisibleState.test_recent_tick_can_render_remaining_world_minutes` | 経過手番の差引や世界の分数への換算を誤る |
| F | `TestVisibleState.test_resolved_flag_suppresses_a_recent_deadline_display` | 解決済みの警告を表示し続ける |
| F | `TestVisibleState.test_recent_visual_trace_is_hidden_without_light` | DARK/PITCH_BLACKで視覚的な痕跡を見せる |
| R | `TestVisibleState.test_recent_tick_rule_requires_the_current_tick` | 現在手番の未配線を黙って無視する、または固有例外以外で失敗する |
| R | `TestVisibleState.test_light_gated_rule_requires_effective_lighting` | 照明の未配線を黙って無視する、または別ガードで落ちる。current_tick=8は先行ガードを通す |
| R | `TestVisibleState.test_bool_state_display_rule_does_not_match_zero_or_one` | False/Trueの規則を数値0/1と同一視する |

### `tests/domain/world_graph/test_spot_interior_entity.py`

| 判定 | 宣言 | 検出する退行 |
|---|---|---|
| F | `TestSpotInterior.test_replace_object` | 指定オブジェクトの状態置換が行われない |
| R | `TestSpotInterior.test_replace_unknown_raises` | 存在しない物体の置換を黙って受理する |
| R | `TestSpotInteriorGroundItems.test_with_ground_item_adds_new_item` | 地面アイテムを追加しない、別品を追加する、または元集合を変更する |
| F | `TestSpotInteriorGroundItems.test_ground_item_same_instance` | 同一実体の地面アイテムを二重追加する |
| R | `TestSpotInteriorGroundItems.test_excludes_ground_item_instance` | 指定ID以外を削除する、全削除する、または削除しない |
| F | `TestSpotInteriorGroundItems.test_returns_find_ground_item_instance` | 存在する地面アイテムを取得できない |
| F | `TestSpotInteriorGroundItems.test_find_ground_item_none` | 存在しない品を取得したことにする |

### `tests/domain/world_graph/test_spot_node_step2.py`

| 判定 | 宣言 | 検出する退行 |
|---|---|---|
| F | `TestSpotNodeStep2.test_with_interior_and_atmosphere` | 指定した内部構造・雰囲気が欠落する |
| R | `TestSpotNodeStep2.test_is_outdoor_defaults_false` | is_outdoor未指定の既存シナリオに夜/天候の影響を誤適用する |
| R | `TestSpotNodeStep2.test_is_outdoor_explicit_true` | 屋外指定を無視して天候の適用対象から外す |

### `tests/domain/world_graph/test_spot_object_perception.py`

| 判定 | 宣言 | 検出する退行 |
|---|---|---|
| R | `TestDetailReadBy.test_unread_shows_base_description` | 未読者へ詳細説明を公開する |
| R | `TestDetailReadBy.test_read_shows_detailed_description` | 読了者へ詳細の内容を見せない |
| R | `TestDetailReadBy.test_other_agent_still_sees_base` | 一人の読了を全閲覧者へ共有し秘密内容を漏らす |
| R | `TestDetailReadBy.test_no_viewer_id_shows_base` | 閲覧者未指定を読了者として扱う |
| R | `TestDetailReadBy.test_with_detail_read_is_immutable` | 読了を追加すると元オブジェクトの読了集合も変更する |
| R | `TestDetailReadBy.test_multiple_readers` | 二人目の読了追加で一人目を失う、または未読の三人目にも内容を公開する |
| F | `TestRequiresReadWithStateCondition.test_requires_read_and_state_both_needed` | 未読ガードを無視する、または読了と条件成立時に詳細を見せない |

### `tests/domain/world_graph/test_spot_perception_night_weather.py`

| 判定 | 宣言 | 検出する退行 |
|---|---|---|
| C | `TestBackwardCompat.test_kwarg` | 追加kwargs省略時BRIGHTを維持しない |
| C | `TestBackwardCompat.test_dark_spot_dim` | 追加kwargs省略時DARK/光源ありをDIMへ上げない |
| R | `TestOutdoorNight.test_bright_dim_2` | 屋外夜のBRIGHTがDIMへ減光しない |
| R | `TestOutdoorNight.test_dim_dark` | 屋外夜のDIMがDARKへ減光しない |
| R | `TestOutdoorNight.test_dark_pitch_black` | 屋外夜のDARKがPITCH_BLACKへ減光しない |
| R | `TestIndoorNight.test_bright` | 屋内BRIGHTを夜だから暗くする |
| R | `TestIndoorNight.test_dark` | 屋内DARKを夜だからさらに暗くする |
| R | `TestWeatherObscuresVision.test_bright_dim` | 夜でなくても屋外悪天候がBRIGHTをDIMにしない |
| R | `TestWeatherObscuresVision.test_not_affected` | 屋内を悪天候だから暗くする |
| R | `TestNightAndWeatherCombo.test_night_and_storm_lower_visibility_by_one_stage` | 夜と嵐を重複適用して二段階暗くする |
| R | `TestLightBearerInteraction.test_dim` | 夜の減光を光源の補光より後に適用し、DIMへ戻せない |

### `tests/domain/world_graph/test_spot_perception_service.py`

| 判定 | 宣言 | 検出する退行 |
|---|---|---|
| R | `TestEffectiveLighting.test_bright_unchanged` | 光源あり/なしでBRIGHTを不当に変更する。kwargs既定の主保持先でもある |
| F | `TestEffectiveLighting.test_dim_unchanged` | 光源なしのDIMを変更する |
| R | `TestEffectiveLighting.test_dark_without_light_stays_dark` | 光源なしのDARKを不当に明るくする |
| R | `TestEffectiveLighting.test_dark_with_light_becomes_dim` | 光源ありのDARKをDIMへ上げない。夜天候側の互換再実行の主保持先 |
| R | `TestEffectiveLighting.test_pitch_black_with_light_becomes_dim` | PITCH_BLACKを補光対象から落とす |
| R | `TestEffectiveLighting.test_pitch_black_without_light_stays` | 光源なしのPITCH_BLACKを不当に明るくする |
| R | `TestEffectiveLighting.test_no_atmosphere_defaults_bright` | 雰囲気未設定でBRIGHT既定を失う |
| R | `TestCanSeeObjects.test_bright_can_see` | BRIGHTで物体を見せない |
| R | `TestCanSeeObjects.test_dim_can_see` | DIMで物体を見せない |
| R | `TestCanSeeObjects.test_dark_cannot_see` | DARKで通常の物体を見せる |
| R | `TestCanSeeObjects.test_pitch_black_cannot_see` | PITCH_BLACKで通常の物体を見せる |
| R | `TestLightingPerceptionText.test_bright_no_note` | 明るい部屋へ不要な暗闇の補足を追加する |
| R | `TestLightingPerceptionText.test_dark_with_own_light` | 自分の光源という原因を補足から落とす |
| R | `TestLightingPerceptionText.test_dark_with_companion_light` | 同行者の光源名を補足から落とす |
| R | `TestLightingPerceptionText.test_pitch_black_no_light` | 完全な暗闇の補足を失う |
| R | `TestLightingPerceptionText.test_dark_no_light` | 暗くて見えない補足を失う |

### `tests/domain/world_graph/value_object/test_state_display_rule.py`

| 判定 | 宣言 | 検出する退行 |
|---|---|---|
| R | `TestStateDisplayRule.test_accepts_primitive_value_and_text` | 妥当な規則を拒否する、key/value/textを取り違える。拒否試験の正常入力対照として保持 |
| R | `TestStateDisplayRule.test_rejects_empty_or_non_string_key` | 空/空白/非文字列のkeyを受理する。各行はvalue/textを正常にしてkeyガードへ到達 |
| R | `TestStateDisplayRule.test_rejects_non_primitive_value` | 配列/空辞書/非空辞書を比較値として受理する。key/textは正常 |
| R | `TestStateDisplayRule.test_rejects_empty_or_non_string_text` | 空/空白/非文字列の作者文を受理する。先行key/valueは正常 |
| R | `TestStateDisplayRule.test_rejects_non_integer_at_least` | bool/浮動小数/文字列を整数下限へ暗黙変換して受理する |
| R | `TestStateDisplayRule.test_rejects_non_positive_integer_within_ticks` | 0/負数/bool/浮動小数/文字列を有効な期限にする。value=None、at_leastなしで組合せガードは独立 |
| R | `TestStateDisplayRule.test_rejects_non_boolean_requires_light` | None/0/1/文字列を照明条件のboolとして受理する。within_ticks=5は先行ガードを通す |
| R | `TestStateDisplayRule.test_rejects_completion_flag_without_a_timed_rule` | 時限規則でないunless_flag_setを受理して黙って無視する |
| R | `TestStateDisplayRule.test_rejects_remaining_minutes_without_a_timed_rule` | 期限なしのremaining_minutes差込みを受理して未置換文字列を表示する |
