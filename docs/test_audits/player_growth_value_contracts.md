# 成長値の保持・曲線・構築拒否を検査する

## 対象と判断

BaseStats、ExpTable、Growth、StatGrowthFactorの各19宣言、元76宣言を全件読んだ。
保持R55・検査補強F4・統合C17・削除D0とする。構築拒否の元20入力は同じ所有者の3表へ移す。
結果は59宣言・78実行であり、宣言の削減を入力や契約の削除と混同しない。
製品コード、共有fixture、他の試験、CI設定は変更しない。

| 所有者 | R | F | C | D |
| --- | ---: | ---: | ---: | ---: |
| BaseStats | 10 | 1 | 8 | 0 |
| ExpTable | 15 | 1 | 3 | 0 |
| Growth | 18 | 1 | 0 | 0 |
| StatGrowthFactor | 12 | 1 | 6 | 0 |

初案から8件をRへ戻した。Growthのlevel0拒否・上位レベルの経験値不足・非初期状態への0加算・
L4到達、ExpTableのL3曲線・負経験値、StatGrowthFactorのL5減衰・負レベル拒否は、
短い独立した境界として残す。構築子、公開逆算、等価性、ハッシュ、集合の重複除去、
代入禁止、量の0許容、割合の上限も、単純に見えることを理由に削除しない。

## 4件の補強

### BaseStats.grow: 戻り値だけ正しくても元の値を壊さない

元の入力 `(100,50,10,5,8,.05,.03)` と係数 `.1/.01`、元HP100、戻りHP110、
別インスタンスの3assertを保持した。元の全7項目と戻り値の全7項目を追加観測する。
期待値は製品から生成せず、量は `(110,55,11,5,8)`、割合は `.06/.04`。
既存と同じ近似精度で比較し、元のmax_mpだけを変更する故障も検出する。

### Growth.gain_exp: 指定した曲線と元の値を保持する

元の既定曲線100/1.5/0、L2/100へ182加算してL3/282となる入力と元3assertを残した。
追加行は曲線200/1/.5、L2/330へ170加算してL3/500。元のlevel・経験値・曲線3項目と、
新しいGrowthの曲線3項目・別インスタンスを観測する。期待曲線は同じオブジェクトへの参照ではなく、
独立した数値tupleである。曲線オブジェクト自体の同一性は要求しない。

L3/500は誤った既定曲線でも構築可能なので、対象行は経験値不足の別ガードに阻まれず、
曲線保持のassertへ到達する。元のtotal_expだけを変更する故障も直接検出する。

### StatGrowthFactor.for_level: 指定係数と非初期レベルの減衰を全項目へ反映する

元のlevel1/base2→HP係数2と元assertを行として残す。元行は全7係数を確認し、
level4/base2→量係数1・割合係数.1の行を加える。HPだけに指定係数を使う故障と、
指定係数を与えた場合だけレベル減衰を省く故障を分けて検出する。

### ExpTable.get_level_from_exp: 到達可能な最大レベルを返す

元の10000と元2assertを保持し、独立した期待レベル22と次レベルの未到達を確認する。
9623 ≤ 10000 < 10318。従来の下界・単調増加だけでは、21などの過小な戻り値も通る。
非試験の直接利用者は今回のsrc/docs検索では未検出だが、導入時からの公開APIとして残す。

## 同じ所有者の構築拒否を3表へ移す

- BaseStatsの9行: 量5項目の負値と、割合2項目の下限外・上限外
- ExpTableの4行: base_expとexponentそれぞれの負値・0
- StatGrowthFactorの7行: 各係数の負値

各行の全引数値と型、固有例外クラス、元のmatch文字列を保持した。
表は正常な引数辞書の1項目だけを不正値へ替える。行idは元試験名とする。
移管先20行を先に成功確認してから、重複する17宣言を取り除いた。
異なる値型をまとめる汎用helperや、製品を反射して作る項目表は導入しない。

## 各層の主担当と実際の利用者

数値成長はBaseStatsとStatGrowthFactor、累積曲線・逆算はExpTable、
経験値加算・曲線保持・元状態保持はGrowthが主担当である。
PlayerStatusAggregate.gain_expはこれらを呼び、HP/MP上限とPlayerLevelUpEventへ接続する。
集約の「増えた」だけの確認は、正確な値の試験の代替にならない。

起動処理・シナリオ読込・SQLite復元・成長スナップショットも値型の実利用者である。
導入コミット `9b6047f121ef0fd6bbc4816cc7bd68ca322f1374` で4所有者と試験が同時に追加され、
今回の基準まで試験クラスの構文木は同じだった。似たSkillDeckExpTableは既定値・
offset検証・所有者が異なるため統合しない。内部実装を固定する製品用の補助APIも作らない。

## 元76宣言の保持先

Rはその位置で保持、Fは同名で補強、Cは下記の表へ元の入力と拒否確認を移す。
3表の主宣言も名前だけ一般化したRとして数える。

### test_base_stats.py

| 元の試験 | 判断 | 契約・保持先 |
| --- | --- | --- |
| `test_create_valid_base_stats` | R | 7 項目の非一様な正値をそのまま保持する公開構築契約 |
| `test_create_with_zero_values` | R | 量・確率とも 0 を許容する下限 |
| `test_create_with_negative_max_hp_raises_error` | R | `test_rejects_invalid_base_stats_fields` の同名行へ移管。max_hp=-1 を BaseStatsValidationException で拒否する |
| `test_create_with_negative_max_mp_raises_error` | C | `test_rejects_invalid_base_stats_fields` の同名行へ移管。max_mp=-10 を BaseStatsValidationException で拒否する |
| `test_create_with_negative_attack_raises_error` | C | `test_rejects_invalid_base_stats_fields` の同名行へ移管。attack=-5 を BaseStatsValidationException で拒否する |
| `test_create_with_negative_defense_raises_error` | C | `test_rejects_invalid_base_stats_fields` の同名行へ移管。defense=-2 を BaseStatsValidationException で拒否する |
| `test_create_with_negative_speed_raises_error` | C | `test_rejects_invalid_base_stats_fields` の同名行へ移管。speed=-3 を BaseStatsValidationException で拒否する |
| `test_create_with_negative_critical_rate_raises_error` | C | `test_rejects_invalid_base_stats_fields` の同名行へ移管。critical_rate=-0.1 を BaseStatsValidationException で拒否する |
| `test_create_with_critical_rate_over_one_raises_error` | C | `test_rejects_invalid_base_stats_fields` の同名行へ移管。critical_rate=1.5 を BaseStatsValidationException で拒否する |
| `test_create_with_negative_evasion_rate_raises_error` | C | `test_rejects_invalid_base_stats_fields` の同名行へ移管。evasion_rate=-0.05 を BaseStatsValidationException で拒否する |
| `test_create_with_evasion_rate_over_one_raises_error` | C | `test_rejects_invalid_base_stats_fields` の同名行へ移管。evasion_rate=1.2 を BaseStatsValidationException で拒否する |
| `test_grow_with_valid_growth_factor` | R | 各量は対応する係数の 1+係数 倍で切捨て、確率は加算される |
| `test_grow_with_critical_rate_capped_at_one` | R | critical_rate の加算が 1 を超えたときだけ上限 1 に収まる |
| `test_grow_with_evasion_rate_capped_at_one` | R | evasion_rate の上限制御は critical_rate から独立 |
| `test_grow_with_zero_growth_factor` | R | 0 係数による成長は全値を保持する |
| `test_grow_returns_new_instance` | F | 成長後の新しい値と、変更されない元の値を同時に返す非破壊更新 |
| `test_equality` | R | 同じ値の BaseStats は等しく、HP 違い・異種値は等しくない |
| `test_hash` | R | 等しい値は同じハッシュで集合内では重複排除される |
| `test_immutability` | R | 既存値の max_hp への直接代入が拒否され、元値が残る |

### test_exp_table.py

| 元の試験 | 判断 | 契約・保持先 |
| --- | --- | --- |
| `test_create_valid_exp_table` | R | base_exp,exponent,level_offset の指定値を保持する |
| `test_create_with_level_offset` | R | 非既定の曲線係数とオフセットを保持する |
| `test_create_with_negative_base_exp_raises_error` | R | `test_rejects_nonpositive_curve_parameters` の同名行へ移管。base_exp の非正値 -1.0 は ExpTableValidationException |
| `test_create_with_zero_base_exp_raises_error` | C | `test_rejects_nonpositive_curve_parameters` の同名行へ移管。base_exp の非正値 0.0 は ExpTableValidationException |
| `test_create_with_negative_exponent_raises_error` | C | `test_rejects_nonpositive_curve_parameters` の同名行へ移管。exponent の非正値 -1.0 は ExpTableValidationException |
| `test_create_with_zero_exponent_raises_error` | C | `test_rejects_nonpositive_curve_parameters` の同名行へ移管。exponent の非正値 0.0 は ExpTableValidationException |
| `test_get_required_exp_for_level_one` | R | 初期レベル1の累積必要経験値は0 |
| `test_get_required_exp_for_level_two` | R | 累積必要経験値は基準曲線で L2=100 |
| `test_get_required_exp_for_level_three` | R | 非整数になる指数曲線の L3 累積必要経験値を切捨てて282とする |
| `test_get_required_exp_with_level_offset` | R | 非ゼロの level_offset が必要経験値曲線の底へ反映される |
| `test_get_level_from_exp_zero` | R | 累積経験値0から初期レベル1を返す公開逆算契約 |
| `test_get_level_from_exp_negative` | R | 負の累積経験値は逆算ではレベル1へ丸める |
| `test_get_level_from_exp_level_two` | R | L2 のしきい値ちょうどでレベル2へ逆算する |
| `test_get_level_from_exp_between_levels` | R | L2 と L3 の間では最大到達レベル2を返す |
| `test_get_level_from_exp_exact_level_three` | R | L3 のしきい値ちょうどまで複数回探索できる |
| `test_get_level_from_exp_high_value` | F | 大きい累積経験値でも到達可能な最大レベルを返す |
| `test_equality` | R | 同じ曲線は等しく base_exp 違いと異種値は異なる |
| `test_hash` | R | 同じ曲線は同一ハッシュで集合中1件になる |
| `test_immutability` | R | base_exp の直接代入を拒否し元値を保持 |

### test_growth.py

| 元の試験 | 判断 | 契約・保持先 |
| --- | --- | --- |
| `test_create_valid_growth` | R | 初期レベル・経験値・指定曲線を保持する |
| `test_create_level_two_with_sufficient_exp` | R | レベル2の必要累積経験値ちょうどを受け入れる |
| `test_create_with_negative_level_raises_error` | R | level=-1を拒否する |
| `test_create_with_zero_level_raises_error` | R | レベル0も拒否する |
| `test_create_with_negative_total_exp_raises_error` | R | 負の total_exp を固有のドメイン例外で拒否する |
| `test_create_with_insufficient_exp_for_level_raises_error` | R | 指定レベルの累積しきい値未満なら構築できない |
| `test_create_with_insufficient_exp_for_higher_level_raises_error` | R | 高いレベルでも必要経験値1不足を拒否する |
| `test_gain_exp_zero_returns_same_growth_no_level_up` | R | 経験値0の獲得でも等価な新インスタンスを返し昇格しない |
| `test_gain_exp_small_amount_no_level_up` | R | しきい値未満の加算でも経験値は保存し昇格しない |
| `test_gain_exp_exact_amount_for_level_up` | R | しきい値と一致した加算で昇格し全経験値を保持する |
| `test_gain_exp_more_than_needed_for_level_up` | R | 余剰経験値を失わず1段階昇格できる |
| `test_gain_exp_multiple_level_up` | R | 1回の加算で複数レベルを進められる |
| `test_gain_exp_from_mid_level` | F | 非初期状態への加算は元を保ち、指定曲線を保持した新しい状態を返す |
| `test_gain_exp_negative_amount_raises_error` | R | 負の獲得経験値を GrowthValidationException で拒否する |
| `test_gain_exp_zero_from_higher_level` | R | 非初期レベルでの0獲得は現在の経験値とレベルを維持する |
| `test_gain_exp_to_reach_level_four` | R | L3からのちょうど237加算で累積519のL4へ進む |
| `test_equality` | R | 同じ level,total_exp,exp_table は等しく、別状態・異種値は異なる |
| `test_hash` | R | 等しい Growth が同じハッシュを持ち集合で重複排除される |
| `test_immutability` | R | level の直接変更を拒否し元値を保持する |

### test_stat_growth_factor.py

| 元の試験 | 判断 | 契約・保持先 |
| --- | --- | --- |
| `test_create_valid_stat_growth_factor` | R | 7 個の異なる係数をそのまま保持する |
| `test_create_with_negative_hp_factor_raises_error` | R | `test_rejects_negative_growth_factor_fields` の同名行へ移管。hp_factor の負値 -1.0 を固有例外で拒否する |
| `test_create_with_negative_mp_factor_raises_error` | C | `test_rejects_negative_growth_factor_fields` の同名行へ移管。mp_factor の負値 -0.5 を固有例外で拒否する |
| `test_create_with_negative_attack_factor_raises_error` | C | `test_rejects_negative_growth_factor_fields` の同名行へ移管。attack_factor の負値 -0.2 を固有例外で拒否する |
| `test_create_with_negative_defense_factor_raises_error` | C | `test_rejects_negative_growth_factor_fields` の同名行へ移管。defense_factor の負値 -0.1 を固有例外で拒否する |
| `test_create_with_negative_speed_factor_raises_error` | C | `test_rejects_negative_growth_factor_fields` の同名行へ移管。speed_factor の負値 -0.3 を固有例外で拒否する |
| `test_create_with_negative_critical_rate_factor_raises_error` | C | `test_rejects_negative_growth_factor_fields` の同名行へ移管。critical_rate_factor の負値 -0.1 を固有例外で拒否する |
| `test_create_with_negative_evasion_rate_factor_raises_error` | C | `test_rejects_negative_growth_factor_fields` の同名行へ移管。evasion_rate_factor の負値 -0.05 を固有例外で拒否する |
| `test_create_with_zero_hp_factor_allows_zero` | R | 0 の係数は合法で成長停止を表現できる |
| `test_for_level_one` | R | 既定係数でL1の量成長は1、確率成長は.1 |
| `test_for_level_two` | R | L2のHP係数は約 .7071067812 でL1より小さい |
| `test_for_level_five` | R | L5でも逆平方根曲線が続きL2より小さい |
| `test_for_level_with_custom_base_growth_rate` | F | 非既定の base_growth_rate は指定レベルの減衰と全係数へ反映される |
| `test_for_level_zero_raises_error` | R | for_level はlevel=0をドメイン例外で拒否する |
| `test_for_level_negative_raises_error` | R | 負のレベルも計算前にドメイン例外で拒否 |
| `test_growth_rate_decreases_with_level` | R | L1からL10まで連続してHP成長率が下がる |
| `test_equality` | R | 同じ7係数は等しくHP係数違い・異種値は異なる |
| `test_hash` | R | 等しい係数は同じハッシュで集合中1個になる |
| `test_immutability` | R | hp_factor への直接代入を拒否して元係数を保持する |

## 旧版・候補の検出力

各誤変更は対象76件＋関連14件の旧90件、候補78件＋同関連14件の92件で直列実行した。

| 改善の対照 | 旧90件 | 候補92件 |
| --- | --- | --- |
| BaseStatsの正しい結果を作った後、元max_mpだけを変更 | 全成功 | 元の全値比較1件が失敗 |
| Growthの結果を作った後、元total_expだけを変更 | 全成功 | 元の値比較2行が失敗 |
| 正しく構築したGrowthの戻り曲線だけを既定値へ置換 | 全成功 | 非既定曲線の保持比較1行が失敗 |
| 指定base2をMP係数だけへ反映しない | 全成功 | 全係数比較2行が失敗 |
| 指定係数の場合だけレベル減衰を省く | 全成功 | level4の期待係数1行が失敗 |
| 逆算の戻りレベルを21に切り詰める | 全成功 | 最大レベル22の比較1件が失敗 |

別に、Growthの構築引数の段階で既定曲線を渡す対照も実行した。
この場合は旧対象76件が全成功でも、既存の関連集約が「L2/60に必要経験値100」の別ガードで失敗する。
候補はそれに加え、非既定曲線行の曲線比較で失敗する。この既存検出力を、新しい検査の独自性とは数えない。
構築後差替えの対照はそのガードと交絡せず、曲線保持assert自体の検出差を示す。

移管した20拒否行については、対応するガードだけを20種類、個別に破った。
量5・割合の上下4・曲線の負と0の4・係数7である。旧版では該当する元1試験、
候補では対応する表の1行が、それぞれDID NOT RAISEで失敗し、他の全件は成功した。

さらに製品を正常に戻し、3表を一時的に正常値のままにする対照を実行した。
全20行がDID NOT RAISEで失敗し、別の不正条件で通過する拒否試験ではないことを確認した。
合計は改善6種＋保持20種の旧新52実行、別の曲線対照2実行、合法入力対照1実行。
全55実行で準備・後始末の失敗は0。意図的な誤変更であり、製品の不具合報告ではない。

## 保存と最終検証

- 元F4の全assertを保持。元の入力行に加えたのはGrowthとStatGrowthFactorの各1行だけ
- 名前を一般化した主表3件を除くR52件の構文木は不変。うち2件は累積経験値の誤ったコメントだけを訂正
- 元20拒否入力の値・型・例外・文言を静的照合し、行ごとの変異と合法入力対照も確認
- 製品1601 Pythonファイルの全ハッシュが実験前後で一致。候補4ファイルも固定版へ復元
- 未編集76＋関連14の90件成功。復元後は78＋14＝一意92件成功し、重複するnodeidなし
- 関連14は集約経験値3、StatusModifier7、JSON往復3、成長スナップショット1
- スナップショットは `TestPlayerGrowthCodec::test_capture_restore_round_trip_2` の1件だけ。関連14、BeingSnapshot34、memory/SNSの監査完了を計上しない
- Python3.10.22・pytest8.4.1。対象作業木のsrc読込、資格情報除去、通信遮断を確認した安全な実行環境を使用
- Ruff0.16.8と `git diff --check` が成功。試験4ファイルは956行から845行へ111行減、製品差分0
- 全リポジトリ試験は手元で未実行。公開後の正確な先端CIは別途確認する

対象と関連の通常の再実行範囲:

```bash
uv run --frozen pytest \
  tests/domain/player/value_object/test_base_stats.py \
  tests/domain/player/value_object/test_exp_table.py \
  tests/domain/player/value_object/test_growth.py \
  tests/domain/player/value_object/test_stat_growth_factor.py \
  tests/domain/player/aggregate/test_player_status_aggregate.py::TestPlayerStatusAggregate::test_gain_exp_level_up \
  tests/domain/player/aggregate/test_player_status_aggregate.py::TestPlayerStatusAggregate::test_gain_exp_no_level_up \
  tests/domain/player/aggregate/test_player_status_aggregate.py::TestPlayerStatusAggregate::test_gain_exp_when_downed \
  tests/domain/combat/value_object/test_status_modifier.py \
  tests/infrastructure/repository/test_player_status_json_codec.py \
  tests/application/being/test_world_subsystems_phase9_2b.py::TestPlayerGrowthCodec::test_capture_restore_round_trip_2 -q
```

基準はmain `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f` と同じ内容。
最新57件の公開中PRを照合し、対象4試験・4所有者・この文書への直接競合はなかった。
#1706の補正試験は旧契約の関連証明として使い、変更しない。
#1722は同じ集約試験ファイルの状態効果部分だけを変更し、選択した経験値3件は不変だった。

## 今後の所有ルール

- 数式・不変値・曲線の保持は各値型で直接確認し、集約の増減確認へ置き換えない
- 表の拒否行は対象以外を正常に保ち、元の例外型・文言も残す
- 原値を参照で保存するだけの自己比較を避け、非既定値と独立した期待値で検査する
- 公開API、意味のある境界、数学的な不変条件は短いことを理由に削除しない
- 似た値型を同じ準備関数でまとめる前に、所有者と境界の違いを確認する
