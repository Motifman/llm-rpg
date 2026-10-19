# 戦闘計算の試験契約

## 目的と範囲

能力補正の試験は、整数のはずの最大MP・防御・速度だけが小数で返っても通っていた。
空の状態効果の試験も、7項目中3項目だけを見ていたため、残る値の欠落を見逃していた。
この2宣言を、それぞれの計算所有者の公開結果で検査し直す。

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。
次の5ファイル・34宣言を全件読み、保持32・判定修理2・統合0・削除0とした。
元の37入力ケースは残し、必要な入力2例を足した。製品コードは変更しない。

| 試験ファイル | 元の宣言 | 展開ケース 前→後 | 判断 |
| --- | ---: | ---: | --- |
| `tests/domain/combat/service/test_combat_logic_service.py` | 8 | 8→8 | 保持8 |
| `tests/domain/combat/value_object/test_damage.py` | 4 | 4→4 | 保持4 |
| `tests/domain/combat/value_object/test_hit_effect.py` | 9 | 12→12 | 保持9 |
| `tests/domain/combat/value_object/test_status_modifier.py` | 7 | 7→8 | 保持6・修理1 |
| `tests/domain/common/service/test_effective_stats_domain_service.py` | 6 | 6→7 | 保持5・修理1 |

試験は451行から469行。変更は2ファイルで追加43行・削除25行。
内部のfixture2個と `_base_stats` は計32行で、この行数の内数。
製品と試験支援ファイルの追加・削除は0行。本文書と所有規則は試験の行数に含めない。

## 保持先と根拠

### 損傷計算

第一所有者は `CombatLogicService.calculate_damage`。8宣言をそのまま残す。

- `test_calculate_damage_normal`: 攻撃50・防御30から損傷35、回避・会心とも偽
- `test_calculate_damage_evaded`: 回避率1なら損傷0・回避あり
- `test_calculate_damage_critical`: 会心率1なら既定倍率1.5で損傷52・会心あり
- `test_calculate_damage_minimum_damage_guarantee`: 攻撃50・防御200・倍率1でも損傷1
- `test_calculate_damage_applies_power_multiplier`: 威力倍率2なら損傷70
- `test_calculate_damage_with_custom_config`: 指定最小値10と会心倍率2.0を反映
- `test_calculate_damage_evasion_has_priority_over_critical`: 両方の率が1でも回避が優先し、会心旗は偽
- `test_calculate_damage_with_applied_modifiers`: 加算10・乗算1.2の補正済み攻撃72から損傷57

数値は実装から生成した期待値ではなく、独立した固定値である。
計算式の説明が実装と似ているという理由では削除しない。
確率0/1の入力は `random()` の範囲 `[0, 1)` に対して結果が一定になる。
元の乱数の扱い、tick数、試行回数は変更しない。

本番呼出は `HitBoxDamageHandler._handle_impl`。
対象解決、攻撃時能力の優先、HP反映、保存はハンドラの別契約で、#1666の監査範囲を重複計上しない。
集約の試験内で計算と反映を手組みする `application_style` の経路は、実ハンドラの証明とは扱わない。
補正済み能力の損傷試験も、本番接続の証明とは主張しない。

### 損傷値と命中時効果

`Damage` の4宣言は通常10、会心指定20、回避0の公開生成口と負値拒否を守る。
計算サービスの実装が変わっても、これらの値と旗の意味は生成APIの契約として残る。

`HitEffect` の9宣言は次の契約を持つ。

- `test_knockback_factory`: 2マス、持続0、強度2.0、指定確率0.5
- `test_slow_factory`: 速度減少率0.25、持続4、既定確率1.0
- `test_poison_factory`: 毎tick損傷3.0、持続5
- `test_paralysis_factory`: 麻痺の種別、持続3、強度1.0
- `test_silence_factory`: 沈黙の種別、持続2、強度1.0
- `test_negative_duration_raises`: 負の持続を専用例外で拒否
- `test_negative_intensity_raises`: 負の強度を専用例外で拒否
- `test_invalid_chance_raises`: 確率1.2を専用例外で拒否
- `test_continuous_effect_requires_positive_duration`: 継続効果4種が持続0をそれぞれ拒否

SQLiteのHitBox・SkillSpec復元は `HitEffect` を直接構築する。
便利生成メソッドの本番呼出はないが、[効果機能の導入](https://github.com/Motifman/llm-rpg/commit/5d2c857b2d558bf7445b93dc573dc0fcfb327454)から存在する公開APIであり、廃止は別の設計判断になる。
SQLite往復試験の効果が空であることも、この値の試験を消す根拠にはならない。
#1695のHitBox保存・寿命の試験は変更しない。

### 任意の能力補正

`test_status_modifier.py` の実所有者は `BaseStats.apply_modifiers`。
`StatusModifier` は入力値であり、期限付き効果の `compute_effective_stats` とは別の規則を持つ。

保持する6宣言は、加算50+10=60、単独乗算50×1.5=75、加算後の乗算90、
複数倍率100×0.8×0.5=40、会心率0.1+1.0の上限1.0、攻撃50-100の下限0である。

修理する `test_apply_modifiers_keeps_amounts_int_and_rates_in_range` は、
[型改修](https://github.com/Motifman/llm-rpg/commit/c1b34769a7a79185d12e460fdabe34c667609189)後の
[整数型の回帰試験](https://github.com/Motifman/llm-rpg/commit/1a018a369348feb4bccc6fce818030b026f6ab45)を保持する。
元の入力は `(100,50,50,30,10,0.1,0.05)` と、攻撃×1.5・会心率+5・回避率-1。
元の攻撃/最大HPの型、会心率1.0、回避率0.0の検査を残し、量5種類すべての型と公開値を調べる。
`75.0 == 75` は真なので、値の等価比較だけで整数型を保証したとはしない。

追加行は `(101,51,51,31,11,0.1,0.05)` の量5種類へ各1.5倍を適用し、
固定値 `(151,76,76,46,16,0.1,0.05)` を期待する。
期待値側で `int`、`min`、`max` や本体の助け関数を呼ばない。

本番の `apply_modifiers` 呼出はないが、公開機能の導入と回帰の履歴があるため廃止しない。
割合上限だけの試験をこの表へ統合する案は、所有層や試験支援を減らさないため採用しなかった。
型と割合の別契約を読みやすく残し、削減数を目的にしない。

### 期限付き効果の実効値

第一所有者は `compute_effective_stats`。
次の5宣言は変更しない。

- `test_multiple_buffs_multiply`: 攻撃20へ1.5倍と1.2倍で36
- `test_filters_expired_effects`: tick10では期限5を除外し、期限20だけを適用して攻撃30
- `test_buff_and_debuff_stacking`: 強化1.5倍と弱化0.5倍を併用して攻撃15
- `test_defense_and_speed_effects`: 防御30・速度4となり、攻撃10は保持
- `test_max_hp_mp_and_rates_unchanged`: 効果ありでもHP200・MP80・会心率0.25・回避率0.1を保持

修理する空効果の宣言は、元の基本値 `(100,50,20,10,5,0,0)`、空リスト、tick10を残す。
3項目だけの検査を `result == base` へ広げる。
これは公開された不変値の恒等変換を守る比較で、返却実体の同一性や別実体生成は要求しない。
非0率を持つ `(200,80,15,12,7,0.25,0.1)` の空入力も1例追加する。

本番は `HitBoxDamageHandler`、`SkillCommandService._use_player_skill_impl`
（公開入口 `use_player_skill`）、`MonsterSkillExecutionDomainService.execute` が呼ぶ。
集約側の効果追加や公開一覧の試験を、今回の監査数へ追加しない。

## 検証

資格情報を除きネットワークを遮断した隔離環境で、Python 3.10.22 / pytest 8.4.1を使用した。
実LLMや有償APIは呼んでいない。

- 未編集の対象5ファイル: 37件成功
- 未編集の関連範囲: 429件成功
- 変更後の対象: 39件成功。変異復元後も同じ39件を2回成功
- 変異復元後の関連範囲: 430件成功
- 変更した2ファイルのruff 0.16.8と `git diff --check`: 成功

関連範囲はcombatドメイン、BaseStats、player/monster集約、monster/skill実行、
combatハンドラ、skillアプリケーション。
関連試験は対象の一部を含むため、対象と関連の件数を単純に足さない。
一意のケース数は基準435、変更後437。リポジトリ全体の試験はこの作業木では未実行。

### 見逃しを塞いだ8種類の変異

同じ製品変異に、元の対象37件と変更後39件を順に実行した。
次の8種類は旧対象が成功し、新しい所有者試験が意図した箇所で失敗した。

1. 補正後の最大MPだけをfloatにする
2. 補正後の防御だけをfloatにする
3. 補正後の速度だけをfloatにする
4. 共通の量の整数化を `int` から `round` に替える
5. 空効果時だけ最大MPを0にする
6. 空効果時だけ速度を0にする
7. 空効果時だけ会心率を0にする
8. 空効果時だけ回避率を0にする

元の整数化を外す変異と、割合上限を外す変異の2種類は、旧・新どちらも検出した。
前者は整数型の判定、後者は本来通る補正後の値構築が拒否されることで失敗した。
これは改善8種類とは分け、既存回帰の保存対照として扱う。

各切替で対象のPythonキャッシュを消し、書込みを無効化した。
変異前後のソースハッシュを確認し、毎回元のバイト列へ復元した。収集エラーは0。
最終製品ソースは基準と一致する。

## 証明の限界

共通の `round` 変異は151.5→152で識別する。76.5・46.5・16.5はPythonの偶数丸めでも
元期待値と同じなので、各量だけの丸め変更をすべて検出したとは主張しない。
会心損傷の既存52.5→52も、単独では `round` との差を識別しない。

確率分布、期限ちょうど、効果の全種類に対する上下限網羅は今回の追加対象ではない。
最小損傷の既存試験は倍率1での下限を守り、倍率1未満でも最終値を1以上にするという
新しい製品規則は導入しない。
