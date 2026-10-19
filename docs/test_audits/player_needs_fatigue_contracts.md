# プレイヤーの欲求・疲労の契約監査

## なぜ

「疲労が未登録」の試験が実際には既定の登録済み状態を使い、初回差分の試験は空辞書でも成功していた。ダウン中のHP保持も、損傷条件を満たさない入力だけでは確かめられなかった。差分の繰返し参照は返り値の比較だけで、欲求の上限を変更しても成功した。

疲労の5段階は同じ集約の組立てを繰り返していたため、元の入力と検査を同じ境界の表へ集約した。小さな試験や既定値の試験という理由で削除せず、公開契約として独立しているものは残した。

## 範囲と基準

- 基準: main `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`
- 対象: 以下の5ファイル、元54宣言。分類は保持45、修復4、統合5、削除0
- 最終: 50宣言・60ケース。パラメータの各行は実行件数には含め、宣言数には含めない
- 製品・専用支援ファイルの変更は0。廃止ファイルも0。関連アプリケーション試験は参照・実行しただけで編集しない
- 主所有者: `PlayerStatusAggregate`、`AgentNeed`、`AgentNeeds`、`FatigueExertionPolicy`、`NeedsDecayTick`

| 試験ファイル | 行数 前→後 | 宣言 前→後 | 最終ケース |
| --- | ---: | ---: | ---: |
| `tests/domain/player/aggregate/test_player_status_fatigue.py` | 98→103 | 8→4 | 13 |
| `tests/domain/player/aggregate/test_player_status_needs_decay_tick.py` | 230→223 | 10→10 | 11 |
| `tests/domain/player/test_agent_needs.py` | 150→150 | 18→18 | 18 |
| `tests/domain/player/test_player_needs_delta.py` | 144→152 | 9→9 | 9 |
| `tests/domain/player/value_object/test_fatigue_exertion.py` | 72→72 | 9→9 | 9 |

対象試験の合計は 694→700 行。専用支援ファイルは前後とも0。製品は差分0行。

## どの境界で何を守るか

1. 疲労段階は `test_fatigue_tiers_and_threshold_predicates` が所有する。元の29/30/60/85/100をすべて残し、0/59/84/99を加えた。段階名と3つの公開判定を、製品定数から生成しない期待値で検査する
2. 既定の疲労0と未登録は異なる入力である。元の既定入力も残し、`AgentNeeds.empty()` を実際に渡した行で未登録0/okを確かめる
3. tick規則は集約の公開入口が所有する。ダウン中は元の空腹50/疲労0に加え、空腹100/疲労95も使う。欲求・HP・`changed` を調べ、保存や配送の順序はアプリケーションの確定境界に任せる
4. 差分は初回の両キー0、符号、基準値上書き、繰返し参照、表示への伝達を区別する。参照の不変検査は欲求の値と上限に限定し、後続の+1から差分6が出ることも確認する。他の集約状態を一括比較しない
5. `FatigueExertionPolicy()` の構築時既定と共有インスタンスの公開メソッドは異なる入口として残す。共有インスタンスだけを補正する変更では前者の退行を拾えない
6. `AgentNeeds.default()`、空集合、未登録追加、不変値の契約も維持する。`increase_all` と `has_critical` は現製品から直接呼ばれていないが、この監査だけで公開APIやその独立試験を削除しない

`test_needs_decay_command_scope.py` は全員の保存巻戻し・確定後観測・確定後の解放失敗を守り、集約試験と役割が異なる。`test_needs_decay_tick_command_scope_wiring.py` の本番構成・ライフサイクル巻戻し2件は読取照合のみで、以下の実行件数には含めない。`test_spot_graph_wait_fatigue_recovery.py` の2件は政策定数の再検査で、待機実行の配線を証明するものではない。今回は範囲外として据え置いた。

## 差分表示の現経路と履歴

`SpotGraphCurrentStateBuilder` が `compute_need_deltas()` と `describe_all_with_deltas()` を呼ぶ。記録は `_WorldLlmTurnTrigger._account_result` から `_snapshot_needs_after_turn` へ進むターン終了時である。古いコメントの「プロンプト構築直前」と混同せず、隣接する再解釈処理も対象にしない。

- [欲求導入 34ea257](https://github.com/Motifman/llm-rpg/commit/34ea257aa31e4892cda5faaecef5535faf52c79d): 既定セットと未登録追加は当時のレビューで明示された契約
- [疲労導入 4c24a62](https://github.com/Motifman/llm-rpg/commit/4c24a622e262dad0b57faacc4a4c49f64c9641ee): 限界でも回復手段を塞がない設計
- [差分導入 44da4fc](https://github.com/Motifman/llm-rpg/commit/44da4fcd750a3355d5f2bfb5a6daec96f16b4b2a): 回復傾向を身体表示へ伝える目的
- [政策移管 7e8b80d](https://github.com/Motifman/llm-rpg/commit/7e8b80d2d964e91165d647c071d2e821258c4cf2) と [tick移管 f1163b5](https://github.com/Motifman/llm-rpg/commit/f1163b59c55ad3e9096f4fbf91ef0ec7d9745c73): 個体の規則をドメインへ移した経緯

## 元54宣言の対応

Rは保持、Fは契約を残して入力・検査を修復、Cは同じ所有境界の表へ統合。各R/Fは同じ場所に残る。Cの5宣言は `TestFatigueLevelTiers.test_fatigue_tiers_and_threshold_predicates` に吸収した。最初のFだけは、実入力に合わせて `test_default_or_unregistered_fatigue_value_zero` へ改名した。

### `tests/domain/player/aggregate/test_player_status_fatigue.py`

| 元の宣言 | 判断 | 保持する契約・検出する退行 |
| --- | :---: | --- |
| `TestFatigueApplyRecover.test_fatigue_unregistered_fatigue_value_zero` | F | 既定の疲労0/okを維持し、未登録も同じになる。現入力は既定の登録済みFATIGUEで未登録分岐を通らない。既定行を残してAgentNeeds.empty()行を追加する |
| `TestFatigueApplyRecover.test_apply_fatigue_value_increases` | R | apply_fatigue(40)で疲労0→40。疲労増加を呼ばない、別欲求へ適用する誤りを検出する |
| `TestFatigueApplyRecover.test_recover_fatigue_value_decreases` | R | recover_fatigue(30)で疲労70→40。回復を呼ばない、加算してしまう誤りを検出する |
| `TestFatigueLevelTiers.test_zero_29_ok` | C | 疲労29はok。test_fatigue_tiers_and_threshold_predicatesの29行が既存assertを吸収する |
| `TestFatigueLevelTiers.test_30_59_tired` | C | 疲労30はtired。同表の30行が吸収し、59も加えて境界直前を検査する |
| `TestFatigueLevelTiers.test_60_84_fatigued` | C | 疲労60はfatiguedかつis_fatigued=True。同表の60行が吸収し、84と各判定False側も検査する |
| `TestFatigueLevelTiers.test_85_99_severe` | C | 疲労85はsevereかつis_severely_fatigued=True。同表の85行が吸収し、99と各判定False側も検査する |
| `TestFatigueLevelTiers.test_100_exhausted` | C | 疲労100はexhaustedかつis_exhausted=True。同表の100行が既存の表示・判定assertを吸収する |

### `tests/domain/player/aggregate/test_player_status_needs_decay_tick.py`

| 元の宣言 | 判断 | 保持する契約・検出する退行 |
| --- | :---: | --- |
| `TestNeedsDecayTickSkipped.test_downed_player_unchanged` | F | ダウン中は欲求とHPを更新せずchanged=False。空腹50/疲労0ではHP減少条件を満たさない。既存行を残し空腹100/疲労95行を追加して拒否前のダメージ漏出を検出する |
| `TestNeedsDecayTickSkipped.test_empty_needs_unchanged` | R | 欲求空ならHP維持かつchanged=False。空を既定セットへ誤置換して増加する変更を検出する |
| `TestNeedsDecayTickHungerIncrease.test_hunger_increases_below_max_no_damage` | R | 空腹0→1ではchanged=TrueでHP100維持。増加を落とす、限界前にダメージを与える変更を検出する |
| `TestNeedsDecayTickHungerIncrease.test_starvation_damage_when_reaching_max_this_tick` | R | 空腹99→100に達する同じtickでHP98。増加前の空腹で判定してダメージを次tickへ遅らせる変更を検出する |
| `TestNeedsDecayTickHungerIncrease.test_starvation_damage_disabled_when_zero` | R | 空腹100でもdamage=0ならchanged=False/HP100。無効設定を無視する、飽和でchangedを立てる変更を検出する |
| `TestNeedsDecayTickFatigueCritical.test_fatigue_critical_damage_at_threshold` | R | 疲労95ちょうどでHP97かつchanged=True。>=を>へ変えて境界を落とす変更を検出する |
| `TestNeedsDecayTickFatigueCritical.test_fatigue_below_threshold_no_damage` | R | 疲労94ではHP100かつchanged=False。疲労閾値を1早める変更を検出する |
| `TestNeedsDecayTickFatigueCritical.test_custom_fatigue_threshold` | R | 指定閾値90で疲労90ならHP99。設定閾値を無視して95固定にする変更を検出する |
| `TestNeedsDecayTickCombined.test_starvation_and_fatigue_critical_both_apply` | R | 空腹100/疲労95は同tickで合計5ダメージ。elif化して片側だけ処理する変更を検出する |
| `TestNeedsDecayTickCombined.test_zero_rate_need_does_not_increase` | R | 空腹の正レートだけ増加し疲労0レートは維持。0レートを無視しない変更を検出する。負レートの証明とは数えない |

### `tests/domain/player/test_agent_needs.py`

| 元の宣言 | 判断 | 保持する契約・検出する退行 |
| --- | :---: | --- |
| `TestAgentNeed.test_create_clamps_value` | R | createは150→100、-10→0へ丸める。生成時の上限/下限丸めを外す変更を検出する |
| `TestAgentNeed.test_increase` | R | 空腹30に20を加え50を返す。increaseの演算符号/量の変更を検出する |
| `TestAgentNeed.test_increase_clamps_at_max` | R | 90+20は上限100になる。increaseの上限違反を検出する |
| `TestAgentNeed.test_satisfy` | R | 空腹80を30満たして50になる。satisfyの演算符号/量の変更を検出する |
| `TestAgentNeed.test_satisfy_clamps_at_zero` | R | 10-50は下限0になる。satisfyの下限違反を検出する |
| `TestAgentNeed.test_is_critical` | R | is_criticalは80でTrue、79でFalse。危険判定の境界ずれを検出する |
| `TestAgentNeed.test_is_satisfied` | R | is_satisfiedは20でTrue、21でFalse。充足判定の境界ずれを検出する |
| `TestAgentNeed.test_describe_levels` | R | 空腹10/60/90を問題なし/高い/危険と表示。自然言語段階の対応取り違えを検出する |
| `TestAgentNeed.test_frozen` | R | 生成後の欲求値を代入で破壊できない。frozenを外して可変にする変更を検出する。公開不変値契約として保持 |
| `TestAgentNeed.test_invalid_max_value` | R | max_value=0をValueErrorで拒否。無効な上限を受理する変更を検出する。例外型は元の契約を維持し製品修正しない |
| `TestAgentNeed.test_fatigue_describe` | R | 疲労の説明には疲労ラベルが入る。空腹へのラベル混同を検出する |
| `TestAgentNeeds.test_default_creates_hunger_and_fatigue` | R | 既定セットは空腹と疲労の2件で値0。既定追加/欠落/非ゼロ値を検出する。初期設定は独立契約で保持 |
| `TestAgentNeeds.test_with_updated` | R | with_updatedは空腹30へ更新し元の0を保つ。元コレクション破壊と更新未適用を検出する |
| `TestAgentNeeds.test_increase_all` | R | increase_allは空腹5/疲労3を別々に適用。レート取り違え/片側欠落を検出する。現製品からの呼出なしだが公開コレクション契約として保持し製品削除しない |
| `TestAgentNeeds.test_describe_all` | R | describe_allは空腹と疲労の2表示を返す。欠落/重複した表示を検出する |
| `TestAgentNeeds.test_empty` | R | emptyは長さ0、HUNGER取得None。空セット生成の誤りを検出する |
| `TestAgentNeeds.test_with_updated_inserts_unregistered_type` | R | 未登録空腹50はemptyへ1件追加される。追加分岐を消す変更を検出する。歴史のレビュー指摘を直接保持 |
| `TestAgentNeeds.test_has_critical` | R | has_criticalは既定False、空腹85でTrue。危険欲求集計の誤りを検出する。現製品からの呼出なしだが公開APIとして保持 |

### `tests/domain/player/test_player_needs_delta.py`

| 元の宣言 | 判断 | 保持する契約・検出する退行 |
| --- | :---: | --- |
| `TestComputeNeedDeltas.test_initial_call_returns_zero_for_all_needs` | F | 初回は空腹20/疲労30の両キーでdelta0。get(...,0)では空辞書でも成功する。{HUNGER:0,FATIGUE:0}の独立期待値へ変更 |
| `TestComputeNeedDeltas.test_snapshot_then_change_then_delta` | R | snapshot後に疲労+5/空腹+3を別キーで返す。差分を計算しない/種別を混同する変更を検出する |
| `TestComputeNeedDeltas.test_negative_delta_means_recovery` | R | 疲労80から10回復した差分は-10。改善の符号反転を検出する |
| `TestComputeNeedDeltas.test_snapshot_overwrites_previous_baseline` | R | snapshotを50→60へ上書き後65の差分は5。最初の基準値を保持する変更を検出する |
| `TestComputeNeedDeltas.test_compute_does_not_modify_state` | F | 繰り返し差分参照は同じ結果で欲求と基準値を保持。現比較は同じ誤値や欲求の上限変更を見逃す。既知delta、欲求ごとの現在値・上限を独立確認し、続く+1でdelta6を確認する。他の集約状態は比較しない |
| `TestDescribeAllWithDeltas.test_no_delta_falls_back_to_describe_all` | R | 空差分の表示は通常表示と互換。空delta時の不要な接尾辞等を検出する。通常表示は別テストの独立期待値で保護される互換契約として残す |
| `TestDescribeAllWithDeltas.test_positive_delta_shows_plus_sign` | R | 疲労増加5は前回+5と表示。正差分のプラス符号欠落を検出する |
| `TestDescribeAllWithDeltas.test_negative_delta_shows_minus_sign` | R | 疲労回復10は前回-10と表示。負差分の符号/値取り違えを検出する |
| `TestDescribeAllWithDeltas.test_zero_delta_no_suffix` | R | 差分0なら前回の接尾辞を出さない。変化なしの不要表示を検出する |

### `tests/domain/player/value_object/test_fatigue_exertion.py`

| 元の宣言 | 判断 | 保持する契約・検出する退行 |
| --- | :---: | --- |
| `TestFatigueExertionCost.test_travel_leg_cost_is_one` | R | 既定の移動コストは1。移動の種別対応または定数の退行を検出する |
| `TestFatigueExertionCost.test_attack_cost_is_five` | R | 既定の攻撃コストは5。攻撃の種別対応または定数の退行を検出する |
| `TestFatigueExertionCost.test_interact_cost_is_two` | R | 既定の操作コストは2。操作の種別対応または定数の退行を検出する |
| `TestFatigueExertionCost.test_wait_cost_is_zero` | R | 待機コストは0。待機にも疲労を加算する変更を検出する |
| `TestFatigueExertionRecovery.test_wait_recovery_is_twenty` | R | 既定の待機回復は20。待機回復の対応または強度退行を検出する |
| `TestFatigueExertionRecovery.test_non_wait_recovery_is_zero` | R | 移動/攻撃/操作の回復は0。待機以外も回復させる変更を検出する |
| `TestFatigueExertionExhaustedBlock.test_heavy_exertions_blocked_when_exhausted` | R | 移動/攻撃/操作は限界時に停止対象。重い行動の停止対象を外す変更を検出する |
| `TestFatigueExertionExhaustedBlock.test_wait_not_blocked_when_exhausted` | R | 待機は限界時にも停止対象にならない。回復手段まで塞ぐ変更を検出する |
| `TestFatigueExertionRecoveryWaitRegression.test_recovery_wait_above_ten` | R | 新規FatigueExertionPolicyの回復既定値は10超。共有定数とは別の構築入口。共有インスタンスだけ20固定なら他の既定API試験では構築時の退行を検出できず保持 |

## 意図的な誤実装で検出力を確認

各行で同じ製品変更に対して元5ファイル全54件と候補5ファイル全60件を別々に実行した。元の試験では全行が成功し、新しい試験は対応する契約で失敗した。試験ごとに新しいキャッシュを使い、各変更後に製品を元のバイト列へ戻した。

| 一時的に入れた誤り | 元の試験 | 候補の試験 |
| --- | ---: | ---: |
| 未登録の疲労を1と返す | 54成功 | 1失敗 / 59成功 |
| 初回だけ両キーを欠落させる | 54成功 | 1失敗 / 59成功 |
| 差分参照時に欲求の上限を増やす | 54成功 | 1失敗 / 59成功 |
| ダウン中も損傷を適用してからchanged=Falseを返す | 54成功 | 1失敗 / 59成功 |
| 疲労開始を60から59へ早める | 54成功 | 1失敗 / 59成功 |
| 重度開始を85から84へ早める | 54成功 | 1失敗 / 59成功 |
| 限界開始を100から99へ早める | 54成功 | 1失敗 / 59成功 |
| 疲労判定を常時真にする | 54成功 | 4失敗 / 56成功 |
| 重度判定を常時真にする | 54成功 | 6失敗 / 54成功 |
| 限界判定を常時真にする | 54成功 | 8失敗 / 52成功 |

ダウン中HPの証明は保持レビューで補強した。最初の誤りは `changed=True` の検査で先に失敗したため、HP保持だけの証明には数えない。`changed=False` と欲求値を保ったまま損傷を漏出させる誤りに置き換え、HPの期待値100に対して98となる検査で失敗することを確認し、復元後の99件も再度成功した。

この確認は現製品の不具合報告ではない。実製品の未編集基準は全93件成功した。`AgentNeed` が無効値で組込みの `ValueError` を投げる点は基準時点の既存契約として残しており、例外設計の変更やIssue作成は行っていない。

## 試験

Python 3.10.22で、秘密情報を除いた環境・ネットワーク遮断・検査対象固有のソース・新しいキャッシュを使用した。通常のCIはPython 3.10、固定依存関係、`pytest -n auto` により対象を収集する。試験ファイルの移動はなく、収集設定の変更は不要。

- 未編集基準: 所有54 + 関連39 = 一意93件成功
- 候補: 所有60件成功
- 最終関連確認: 所有60 + 関連39 = 一意99件成功
- 意図的な誤実装: 上表の旧/新比較。通常成功件数へ加算しない
- Ruff 0.16.8の静的検査・整形確認と差分空白検査: 成功

関連39件は `test_spot_graph_needs_decay.py` 7件、`test_needs_decay_fatigue_critical.py` 4件、`test_needs_decay_starvation.py` 4件、`test_needs_decay_fatigue_passive_off.py` 3件、`test_needs_decay_command_scope.py` 4件、`test_speech_executor_fatigue_blur.py` 8件、`test_spot_graph_wait_fatigue_recovery.py` 2件、`test_own_fatigue_hint_rendered.py` 7件。複数回実行しても一意件数は39件である。

## マージ後の引継ぎ

[PR #1727](https://github.com/Motifman/llm-rpg/pull/1727)、[PR #1729](https://github.com/Motifman/llm-rpg/pull/1729) の別テスト差分は取り込まない。

未完成の合成戦闘試験は別の範囲であり、今回の完了数には含めない。公開PRの作成・CI確認・マージ状態はこの文書のローカル試験結果とは分けて報告する。
