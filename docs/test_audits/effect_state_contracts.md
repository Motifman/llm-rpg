# 状態効果の公開値と拒否時保持の監査

## 範囲と結論

基準はmain `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。世界旗6、物体状態19、プレイヤー状態13の計38宣言を、製品所有者・呼出元・導入履歴・既存の保持先まで読んだ。独立第二読の最終判定は保持26・修理11・統合1・削除0。元の信用はこの3群で分け、関連試験や表の行を監査宣言へ足していない。

試験は38→37宣言、実行ケースは38→40、対象6ファイルは795→843行。変更したのは4試験ファイルで、追加75・削除27行。製品・共有補助の変更と廃止ファイルは0。削除数や速度改善を目的にしていない。

## 見逃しを直した境界

- WorldFlagRegistry: 追加・削除の前の値と、結合の両入力を操作後に確認する。返却集合の値だけではsetとfrozensetが等価なので、公開型の不変性も確認する。新しい実体であることは強制しない
- 物体状態: キー不足や時刻不足で、警告だけ残して既存状態を消す誤りを検査する。元の空入力・available=Trueを保ち、追加行では別の値も保持する
- プレイヤー状態: caplogを開くだけだった4つの警告契約を実際に検査する。元の空状態を保ち、時刻・キー不足には既存値ありの行も加える
- 時刻単独の変更通知: RECORD_PLAYER_STATE_TICKだけでもacting_player_state_changed=Trueになることを確認する。CHANGE_PLAYER_STATEの要約がある複合適用では、要約だけを見て変更判定する誤りを見抜けなかった
- 前提条件: PLAYER_STATE_ISの全一致・末尾不一致を残し、先頭だけ不一致の行を足す。共有評価器の全件比較とは別に、この入口が要求キーを省かず転送することを守る

## 主担当と統合

`test_non_number_zero`の「非整数を0へ戻して1にする」確認だけを、同じ入力の`test_emits_warning_for_log`へ移した。保持先は警告と結果の両方を一度の実効果適用で見る。元の宣言を残した41件を先に通してから統合元を削除した。

元の小さい構築、既定delta、負delta、キー欠落、status未提供、required_state未提供は残した。ReactiveObjectStateBindingの7宣言も、対称・非対称の宣言許可、両側空と重複キーの拒否、公開する管理キーと選択値の契約として維持した。

空の旗登録簿へ追加で完全一致を要求する初見案は取りやめた。既存の`test_world_flag_transition_trace.py::TestMutableWorldFlagStateTransitions::test_one_replacement_emits_one_transition_for_each_changed_flag`が正確な2通知を比較し、余分な初期旗を既に検出する。

時刻効果の操作元Noneで明示IDを使う試験は残した。これは別物体への優先順位の証明ではない。別対象優先と記録キーの秘匿は`test_recorded_ticks_hide_themselves.py::TestEachLayerHoldsOnItsOwn::test_the_effect_hides_a_key_it_writes_into_another_object`が実効果で保護している。

## 履歴と互換性

- [旗の解除と再発動](https://github.com/Motifman/llm-rpg/commit/9f307154dec44274020ad2224a7bd49c9955c0b8): 指定旗だけの解除と不在時の冪等性を明示した設計判断92を保持
- [汎用整数加算](https://github.com/Motifman/llm-rpg/commit/54de1565c3f0d2e884f6409a3a6568460822bdaa)と[再初期化の警告](https://github.com/Motifman/llm-rpg/commit/f7dbf5cf341d81bc6b33f049662c2e3e2490acfb): 数値結果と診断を同じ主担当へまとめ、どちらも残す
- [記録時刻の導入](https://github.com/Motifman/llm-rpg/commit/d0efcca2e7d25c068daefb5038c276fbd390ecf1)と[公開操作入口への接続](https://github.com/Motifman/llm-rpg/commit/55b9d707b3fe6e2d3767582e7559a00978aa80b1): 警告と入口からの手番伝達は別の責務
- [非対称の宣言許可](https://github.com/Motifman/llm-rpg/commit/ba957acc4ff7009a2cf448e70f43d92100be1016): 監査用managed_state_keysの継続を明記。実適用のstage試験だけへ寄せて公開診断APIを失わせない
- [プレイヤー状態の宣言入口](https://github.com/Motifman/llm-rpg/commit/88bc656ace531d5cb9dca24bace8acffa37507f1): 状態値の更新と、アプリ側の保存判断に使う変更旗を守る
- [処理分割の互換方針](https://github.com/Motifman/llm-rpg/pull/1169): 公開入口と看板定数の再export維持を明記している。内部callerの少なさだけで削除しない。既定可視性と全効果登録の構造検査も別の主担当に残す

WorldFlagRegistry.mergeの現在の非試験呼出元は確認できないが、導入時からの公開値オブジェクトAPIとして保持した。MutableWorldFlagStateは元の登録簿自体を保持しないため、この入力不変性を代わりに証明する試験ではない。

## 全38宣言の台帳

|元の宣言|判定|実際に守る契約・判断|
|---|---|---|
|`test_clear_flag_effect.py::test_clear_flag_removes_only_the_named_world_flag`|R|指定旗だけを解除し、無関係な旗を残す|
|`test_clear_flag_effect.py::test_clear_flag_is_idempotent_when_the_named_flag_is_absent`|R|存在しない指定旗の解除は冪等|
|`test_world_flag_registry.py::TestWorldFlagRegistry::test_empty`|R|emptyが空の不変旗集合を返す|
|`test_world_flag_registry.py::TestWorldFlagRegistry::test_add_remove`|F|追加・削除が元の登録簿を変えず新しい集合を返す|
|`test_world_flag_registry.py::TestWorldFlagRegistry::test_merge`|F|mergeが両集合の和を返し両入力を保持する|
|`test_world_flag_registry.py::TestWorldFlagRegistry::test_as_frozen_set`|F|as_frozen_setは全旗を不変集合として公開する|
|`test_increment_object_state_effect.py::TestIncrementBasic::test_default_delta_increments_state_by_one`|R|delta省略は既存5へ1を加え6にする|
|`test_increment_object_state_effect.py::TestIncrementBasic::test_delta`|R|明示delta3を既存5へ加え8にする|
|`test_increment_object_state_effect.py::TestIncrementBasic::test_negative_delta`|R|負deltaを許しstock10から2減らす|
|`test_increment_object_state_effect.py::TestIncrementBasic::test_state_key_zero_count`|R|キー不在を0として既定1を加える|
|`test_increment_object_state_effect.py::TestIncrementBasic::test_non_number_zero`|C|非整数の既存値を0へ戻して加算する。保持先: test_emits_warning_for_log|
|`test_increment_object_state_effect.py::TestIncrementSilentFallbackWarning::test_emits_warning_for_state_key_missing_log`|F|state_key欠落時に警告し状態を変えない|
|`test_increment_object_state_effect.py::TestIncrementSilentFallbackWarning::test_emits_warning_for_log`|R|非整数再初期化を警告して加算結果も返す|
|`test_record_object_state_tick_effect.py::TestRecordObjectStateTickEffect::test_writes_current_tick_into_state_key_on_acting_object`|R|操作元へ42を書き、既存availableを保持する|
|`test_record_object_state_tick_effect.py::TestRecordObjectStateTickEffect::test_resolves_explicit_object_id_param`|R|操作元Noneでも明示object_idの物体へ5を書ける|
|`test_record_object_state_tick_effect.py::TestRecordObjectStateTickEffect::test_no_op_when_current_tick_missing`|F|current_tick未提供は警告して全状態を保持する|
|`test_record_object_state_tick_effect.py::TestRecordObjectStateTickEffect::test_propagates_through_spot_interaction_service`|R|SpotInteractionServiceの公開実行入口からcurrent_tick99が届く|
|`test_record_object_state_tick_effect.py::TestRecordObjectStateTickEffect::test_no_op_when_state_key_missing`|R|state_key未提供は警告して全状態を保持する|
|`value_object/test_reactive_object_state_binding.py::TestReactiveObjectStateBindingValidation::test_minimal_binding_constructs`|R|対称な最小構築と管理キーの重複排除を許す|
|`value_object/test_reactive_object_state_binding.py::TestReactiveObjectStateBindingValidation::test_both_updates_empty_rejected`|R|両側とも空の宣言を専用例外で拒否する|
|`value_object/test_reactive_object_state_binding.py::TestReactiveObjectStateBindingValidation::test_asymmetric_keys_allowed_for_one_way_lifecycle`|R|片側空の一方向更新を許す|
|`value_object/test_reactive_object_state_binding.py::TestReactiveObjectStateBindingValidation::test_asymmetric_with_both_sides_disjoint`|R|両側の異なるキーを許し管理キーの和集合を公開する|
|`value_object/test_reactive_object_state_binding.py::TestReactiveObjectStateBindingValidation::test_duplicate_key_within_on_true_rejected`|R|true側の重複キーを拒否する|
|`value_object/test_reactive_object_state_binding.py::TestReactiveObjectStateBindingValidation::test_duplicate_key_within_on_false_rejected`|R|false側の重複キーを拒否する|
|`value_object/test_reactive_object_state_binding.py::TestReactiveObjectStateBindingValidation::test_updates_for_returns_correct_dict`|R|同じキーのtrue/false値を正しく選ぶ|
|`test_player_state_effects.py::TestChangePlayerStateEffect::test_merges_state_updates_into_acting_player`|R|部分更新で既存状態と複数新キーを保持し変更旗を返す|
|`test_player_state_effects.py::TestChangePlayerStateEffect::test_no_op_and_warn_when_status_is_none`|R|status未提供の変更は警告し変更旗False|
|`test_player_state_effects.py::TestChangePlayerStateEffect::test_no_op_when_state_updates_not_dict`|F|state_updates非dictは警告して状態と変更旗を保持する|
|`test_player_state_effects.py::TestRecordPlayerStateTickEffect::test_writes_current_tick_into_player_state`|F|時刻単独効果も既存状態を保ち42を書いて変更を通知する|
|`test_player_state_effects.py::TestRecordPlayerStateTickEffect::test_no_op_when_status_missing`|F|status未提供の時刻記録は警告し変更旗False|
|`test_player_state_effects.py::TestRecordPlayerStateTickEffect::test_no_op_when_current_tick_missing`|F|current_tick未提供の時刻記録は警告し状態を保持する|
|`test_player_state_effects.py::TestRecordPlayerStateTickEffect::test_no_op_when_state_key_missing`|F|state_key未提供の時刻記録は警告し状態を保持する|
|`test_player_state_effects.py::TestPlayerStateIsPrecondition::test_passes_when_state_matches`|R|PLAYER_STATE_ISの要求部分が一致すれば余分なstateは無視する|
|`test_player_state_effects.py::TestPlayerStateIsPrecondition::test_fails_when_state_differs`|R|不一致は拒否し作者指定の失敗文を返す|
|`test_player_state_effects.py::TestPlayerStateIsPrecondition::test_fails_when_status_is_none`|R|status未提供の前提条件は不成立|
|`test_player_state_effects.py::TestPlayerStateIsPrecondition::test_required_state_with_multiple_keys_all_match`|F|複数要求キーすべてを共通述語へ渡し一致判定する|
|`test_player_state_effects.py::TestPlayerStateIsPrecondition::test_missing_required_state_rejected`|R|required_state欠落は拒否する|
|`test_player_state_effects.py::TestCombinedActingPlayerEffects::test_change_and_record_in_one_apply`|R|変更と時刻記録を一回で合成し両状態と変更旗を返す|

## 故障対照と復元

同じ基準製品へ一箇所ずつ故障を入れ、元38件と候補40件を比較した。17種類34実行を直列で行い、15種類は元38件が全成功し、候補では狙ったassertが失敗した。残る2種類は統合した非整数の値・警告の保存確認で、元と候補の保持先を区別して確認した。全リポジトリが故障を見逃すという主張ではない。

|故障|元38件|候補40件|
|---|---|---|
|追加が元の空登録簿を壊す|0失敗|1失敗|
|削除が追加済み元登録簿を壊す|0失敗|1失敗|
|結合が左入力を変える|0失敗|1失敗|
|結合が右入力を変える|0失敗|1失敗|
|公開戻り型を可変集合にする|0失敗|1失敗|
|キー不足の警告後に既存stateを消す|0失敗|1失敗|
|手番不足で既存availableを消す|0失敗|1失敗|
|非整数初期化値を5にして元値assertと移管先の検出を比べる|1失敗|1失敗|
|数値復帰は保ち警告だけ落とす|1失敗|1失敗|
|不正updatesの診断を落とす|0失敗|1失敗|
|時刻効果のstatus未提供診断を落とす|0失敗|1失敗|
|時刻未提供診断を落とす|0失敗|2失敗|
|記録キー未提供診断を落とす|0失敗|2失敗|
|時刻不足の無作用が全state初期化になる|0失敗|1失敗|
|記録キー不足の無作用が全state初期化になる|0失敗|1失敗|
|時刻単独はsummaryがないので変更旗がFalseになる|0失敗|1失敗|
|adapterが末尾の要求だけ共通述語へ渡す|0失敗|1失敗|

故障後は毎回、変更製品を元のバイト列へ戻した。旧作業木のsrc/tests全3176ファイル、候補の製品1601ファイル、および変更4試験以外のsrc/tests3172ファイルを基準SHA-256と照合した。保持26宣言のうち統合値を受け入れた1宣言を除く25宣言は構文木不変。

## 試験と限界

- Python3.10.22 / pytest8.4.1。資格情報を除去し外部接続を遮断した固定対象の実行
- 未編集基準: 対象38件、関連42件成功（全55群の基準112件のうち、この単位が所有する範囲）
- 保持先先行41件、統合後40件成功
- 全復元後の最終: 所有40＋関連42＝82件成功、失敗・収集エラー・skipなし
- 変更4試験のRuff0.16.8、git diff --check成功

関連42件はプレイヤー状態の公開操作、宣言的な物体更新、旗の差分通知、別物体への時刻記録、可視性区分と効果登録の境界である。保存の完了や実配送を、効果結果の生成だけで証明したとは扱わない。

全リポジトリ試験・実LLM・有料API・性能比較は未実施。公開後の正確な先端に対するCI結果はローカルの82件に含めない。製品不具合の修正・Issue作成・マージも含めない。

## 競合と所有規則

#1684の備蓄再生・端数繰越と、#1688のOBJECT_STOCK_AT_LEASTの明示対象参照は別の担当である。汎用整数加算の負値や記録手番の対象選択をそこへ混ぜない。#1741の共通述語の計算は変更せず、PLAYER_STATE_ISの入力転送だけを検査する。

契約ごとに一つの主担当を置く: 値オブジェクトの不変性はその公開API、警告と実更新は効果適用、前提入力の取出しは操作サービス、保存・確定・配送はアプリ側。既定値や構築が小さいことだけでは削除しない。
