# プレイヤーのHP・MP・スタミナ値型の試験監査

## 結論

78宣言を読み、3型の値オブジェクトと本番の生成・更新・保存復元経路、関連する集約試験を確認した。大半は独立した数値・境界の契約を守っており、単純または高速という理由で削る対象ではなかった。

この変更では、正常なhash衝突を不具合とする検査を外し、元値の破壊的更新を相反する2操作で打ち消していた検査を修復する。6演算の0量境界を既存試験へ追加し、到達しない負残量を想定した重複1宣言を削除した。製品コードの変更はない。

## 対象と基準

基準の上流コミット: `0b51eb28d4692635a932dcf4063ab9b231768bf0`。Python 3.10.22、pytest 8.4.1。外部通信を遮断し、実LLM・有償APIを使わず直列測定した。CI全体の計測ではない。

| 試験ファイル | 基準の宣言/ケース | 変更後の宣言/ケース | 基準行数 | 変更後行数 |
|---|---:|---:|---:|---:|
| `tests/domain/player/value_object/test_hp.py` | 23/23 | 23/25 | 166 | 167 |
| `tests/domain/player/value_object/test_mp.py` | 21/21 | 21/23 | 152 | 153 |
| `tests/domain/player/value_object/test_stamina.py` | 34/34 | 33/35 | 202 | 201 |
| 合計 | 78/78 | 77/83 | 520 | 521 |

行数は末尾改行の有無に依存しない論理行数。試験差分は32追加/31削除、差引1行増。既存ケースを1件削除し、0量のケースを6件追加した。製品差分0、試験補助コード差分0。新規文書の行数は試験行数に含めない。

基準は78件を2回とも全通過。変更後は83件を2回とも全通過。関連の `tests/domain/player/aggregate/test_player_status_aggregate.py` と `tests/domain/player/test_player_hp_delta.py` は合計78件を基準・候補・意図的変更の復元後の3回とも全通過した。基準の失敗・製品修復はない。

## 責任を残した境界

- 生成・演算・残量判定・割合・Python値型の契約は、対応する3つの値オブジェクト試験が主担当のまま
- 集約のダウン状態、死亡イベントと加害者、実回復量・消費量イベント、不足時の状態保持、複合消費の事前検証は集約試験へ残す。集約試験を値型試験の代替とはしない
- HPの前回基準との差分と表示は `test_player_hp_delta.py` に残す
- 直接コンストラクタは不正値を拒否し、`create()` は現在値を範囲内へ補正する。本番の世界生成・状態復元は直接コンストラクタを、SQLite復元やレベルアップ・復帰は `create()` を使うため、入口を重複として一括削除しない
- `MonsterMp.use()` は残量不足を拒否し、Playerの `Mp.consume()` は0へ補正する。名前や実装が似ていても別の契約なので共有のResource基底や汎用試験へまとめない
- 公開値型の等値/hash契約を保持する。現在の本番コードでHP/MPを直接setやdictのキーにする利用は確認していないが、導入履歴で明示された公開Pythonプロトコルであり、等値とhashの整合は独立して必要

本番の参照点:

- `application/world_runtime/world_runtime.py:5252–5263` と `application/being/world_subsystems/player_vitals_codec.py:63–110`: 直接生成・復元
- `infrastructure/repository/sqlite_player_state_codec.py:67–160` と `sqlite_trade_command_codec.py:443–477`: 補正付き生成
- `domain/player/aggregate/player_status_aggregate.py:742–869,919–1058`: ダメージ、回復、消費、レベルアップ、復帰
- `domain/world_graph/service/spot_interaction_service.py:628–664`: HP割合を使う条件。最大HP=0をVOで0.0とする契約と、条件側で拒否する契約は別

## 実際に修復した検査

1. HP/MPの `test_hash`: 同値の同hashとsetでの重複除去は保持し、「非等値なら必ずhashが異なる」だけを削除。衝突は合法で、値型の比較契約を壊さない。逆にidentity由来のhashでは同値別個体が異なるキーとなり得るため、残す検査が必要
2. Staminaの `test_immutability`: consume(10)とrecover(10)の最後だけを確認すると、元の値を50→40→50と書き換える実装でも通る。消費直後に元の現在値と上限を確認し、回復後の確認も維持した。`dataclass(frozen=True)` や属性代入時の具体的例外は固定していない
3. 6つの正常演算宣言: Hp.heal/damage、Mp.heal/consume、Stamina.consume/recoverを0量と元の正量の2行表にした。元の固定期待値・最大値保持を全て残し、0量を受け入れて値を変えない境界を加えた。集約の0コスト試験は下位演算を呼ばないので、この証明の代替にはならない
4. `test_is_empty_negative_value` の削除: `Stamina.create(-5,100)` は空判定前に0へ補正するので、負残量を判定していなかった。既存の `test_create_stamina_with_negative_value` と `test_is_empty_true` が生成と空判定を個別に守る。直接コンストラクタで負値を拒否する試験も残した

公開操作後に元の値が保たれることと、公開属性への直接代入を拒否することは別の契約。今回は前者の見逃しを直し、後者を実装のfrozen指定だけを根拠に追加していない。

## 全宣言の判定

R=残す、F=契約を保持して検査を修復、C=残す側へ移管して統合、D=削除。第二読解後はR68/F9/C0/D1。位置は全て編集前の固定コミット。各型の演算試験は小さくても独立した入口なので残す。

### hp

| 宣言 | 判定 | 守る契約・具体的退行 |
|---|:---:|---|
| [test_create_hp_success:12](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L12-L16) | R | 正常入力の現在値と上限をそのまま保持する。生成時の初期値取り違えを検出 |
| [test_create_hp_with_value_over_max:18](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L18-L22) | R | 生成時に上限を超えた値を上限へ補正する。上限補正の削除・誤った上限を検出 |
| [test_create_hp_with_negative_value:24](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L24-L28) | R | 生成時の負値を0へ補正し上限を保持する。負値の流出・上限の消失を検出 |
| [test_create_hp_with_zero_max_hp:30](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L30-L34) | R | 上限0なら正の入力も0/0になる。0上限での補正漏れを検出 |
| [test_direct_instantiation_with_valid_values:36](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L36-L40) | R | 直接生成の正常値と上限を保持。実運用の直接入口をfactory専用へ変える退行を検出 |
| [test_direct_instantiation_negative_max_hp:42](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L42-L45) | R | 負の上限を型固有の検証例外として拒否。上限検証の削除・別条件での誤拒否を検出 |
| [test_direct_instantiation_negative_value:47](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L47-L50) | R | 直接生成では負値を補正せず型固有例外にする。factoryと同じ補正処理へ誤統合する退行を検出 |
| [test_direct_instantiation_value_over_max:52](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L52-L55) | R | 直接生成では上限超過を型固有例外にする。補正付き生成との仕様混同を検出 |
| [test_heal_success:57](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L57-L62) | F | healが指定量だけ正しい方向へ変化し上限を保持。加減算方向・未更新・上限取り違えを検出。0量受理の契約も既存宣言へ追加し、負数ガードの<から<=への退行を検出する |
| [test_heal_over_max:64](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L64-L69) | R | healの結果を上限へ補正し上限自体は維持。回復時の補正漏れを検出 |
| [test_heal_negative_amount:71](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L71-L75) | R | healの負数を型固有例外で拒否。負量を許して逆方向へ更新する退行を検出 |
| [test_damage_success:77](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L77-L82) | F | damageが指定量だけ正しい方向へ変化し上限を保持。加減算方向・未更新・上限取り違えを検出。0量受理の契約も既存宣言へ追加し、負数ガードの<から<=への退行を検出する |
| [test_damage_over_current:84](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L84-L89) | R | damageで残量超過しても結果0・元の上限を返す。負残量・不足例外への誤変更を検出 |
| [test_damage_negative_amount:91](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L91-L95) | R | damageの負数を型固有例外で拒否。負量を許して逆方向へ更新する退行を検出 |
| [test_can_consume_success:97](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L97-L102) | R | 残量未満・等量・超過の消費可否をそれぞれ確認。比較の反転と等量のoff-by-oneを検出 |
| [test_can_consume_negative_amount:104](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L104-L108) | R | 負の要求量を検証例外にする。負量を消費可と扱う退行を検出 |
| [test_is_alive:110](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L110-L114) | R | HP1は生存、0と0/0は非生存。>0を>=0へ変える退行を検出 |
| [test_is_full:116](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L116-L120) | R | 上限ちょうどと0/0を満タン、途中値を非満タンと判定。ゼロ上限の扱い・比較誤りを検出 |
| [test_get_percentage:122](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L122-L127) | R | 途中・0・満タン・最大値0の割合を独立の定数で確認。分母・単位誤りとゼロ除算を検出 |
| [test_string_representation:129](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L129-L132) | R | 公開文字列表現が現在値/最大値。順番逆転や片方欠落を検出。ソース文字列照合ではない |
| [test_equality:134](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L134-L144) | R | 同値・現在値違い・上限違い・別型を区別。identity比較や比較項目欠落を検出 |
| [test_hash:146](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L146-L157) | F | 等値の同hashとset重複除外は公開契約で残す。非等値の別hash要求のみ不正: 正常な衝突実装を誤検知する |
| [test_immutability:159](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_hp.py#L159-L166) | R | healが元値を変えず更新後の値を返す。破壊的更新して同じ個体を返す退行を検出 |

### mp

| 宣言 | 判定 | 守る契約・具体的退行 |
|---|:---:|---|
| [test_create_mp_success:10](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L10-L14) | R | 正常入力の現在値と上限をそのまま保持する。生成時の初期値取り違えを検出 |
| [test_create_mp_with_value_over_max:16](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L16-L20) | R | 生成時に上限を超えた値を上限へ補正する。上限補正の削除・誤った上限を検出 |
| [test_create_mp_with_negative_value:22](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L22-L26) | R | 生成時の負値を0へ補正し上限を保持する。負値の流出・上限の消失を検出 |
| [test_direct_instantiation_negative_max_mp:28](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L28-L31) | R | 負の上限を型固有の検証例外として拒否。上限検証の削除・別条件での誤拒否を検出 |
| [test_direct_instantiation_negative_value:33](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L33-L36) | R | 直接生成では負値を補正せず型固有例外にする。factoryと同じ補正処理へ誤統合する退行を検出 |
| [test_direct_instantiation_value_over_max:38](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L38-L41) | R | 直接生成では上限超過を型固有例外にする。補正付き生成との仕様混同を検出 |
| [test_heal_success:43](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L43-L48) | F | healが指定量だけ正しい方向へ変化し上限を保持。加減算方向・未更新・上限取り違えを検出。0量受理の契約も既存宣言へ追加し、負数ガードの<から<=への退行を検出する |
| [test_heal_over_max:50](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L50-L55) | R | healの結果を上限へ補正し上限自体は維持。回復時の補正漏れを検出 |
| [test_heal_negative_amount:57](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L57-L61) | R | healの負数を型固有例外で拒否。負量を許して逆方向へ更新する退行を検出 |
| [test_consume_success:63](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L63-L68) | F | consumeが指定量だけ正しい方向へ変化し上限を保持。加減算方向・未更新・上限取り違えを検出。0量受理の契約も既存宣言へ追加し、負数ガードの<から<=への退行を検出する |
| [test_consume_over_current:70](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L70-L75) | R | consumeで残量超過しても結果0・元の上限を返す。負残量・不足例外への誤変更を検出 |
| [test_consume_negative_amount:77](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L77-L81) | R | consumeの負数を型固有例外で拒否。負量を許して逆方向へ更新する退行を検出 |
| [test_can_consume_success:83](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L83-L88) | R | 残量未満・等量・超過の消費可否をそれぞれ確認。比較の反転と等量のoff-by-oneを検出 |
| [test_can_consume_negative_amount:90](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L90-L94) | R | 負の要求量を検証例外にする。負量を消費可と扱う退行を検出 |
| [test_is_empty:96](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L96-L100) | R | 0/100と0/0は空、1/100は非空。ゼロ境界の比較誤りを検出 |
| [test_is_full:102](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L102-L106) | R | 上限ちょうどと0/0を満タン、途中値を非満タンと判定。ゼロ上限の扱い・比較誤りを検出 |
| [test_get_percentage:108](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L108-L113) | R | 途中・0・満タン・最大値0の割合を独立の定数で確認。分母・単位誤りとゼロ除算を検出 |
| [test_string_representation:115](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L115-L118) | R | 公開文字列表現が現在値/最大値。順番逆転や片方欠落を検出。ソース文字列照合ではない |
| [test_equality:120](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L120-L130) | R | 同値・現在値違い・上限違い・別型を区別。identity比較や比較項目欠落を検出 |
| [test_hash:132](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L132-L143) | F | 等値の同hashとset重複除外は公開契約で残す。非等値の別hash要求のみ不正: 正常な衝突実装を誤検知する |
| [test_immutability:145](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_mp.py#L145-L152) | R | healが元値を変えず更新後の値を返す。破壊的更新して同じ個体を返す退行を検出 |

### stamina

| 宣言 | 判定 | 守る契約・具体的退行 |
|---|:---:|---|
| [test_create_stamina_success:10](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L10-L14) | R | 正常入力の現在値と上限をそのまま保持する。生成時の初期値取り違えを検出 |
| [test_create_stamina_with_value_over_max:16](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L16-L20) | R | 生成時に上限を超えた値を上限へ補正する。上限補正の削除・誤った上限を検出 |
| [test_create_stamina_with_negative_value:22](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L22-L26) | R | 生成時の負値を0へ補正し上限を保持する。負値の流出・上限の消失を検出 |
| [test_direct_instantiation_negative_max_stamina:28](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L28-L31) | R | 負の上限を型固有の検証例外として拒否。上限検証の削除・別条件での誤拒否を検出 |
| [test_direct_instantiation_negative_value:33](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L33-L36) | R | 直接生成では負値を補正せず型固有例外にする。factoryと同じ補正処理へ誤統合する退行を検出 |
| [test_direct_instantiation_value_over_max:38](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L38-L41) | R | 直接生成では上限超過を型固有例外にする。補正付き生成との仕様混同を検出 |
| [test_consume_success:43](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L43-L48) | F | consumeが指定量だけ正しい方向へ変化し上限を保持。加減算方向・未更新・上限取り違えを検出。0量受理の契約も既存宣言へ追加し、負数ガードの<から<=への退行を検出する |
| [test_consume_to_zero:50](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L50-L55) | R | 残量と等しい消費でちょうど0になる。等量消費拒否・0を1へ丸める退行を検出 |
| [test_consume_over_current_value:57](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L57-L62) | R | consumeで残量超過しても結果0・元の上限を返す。負残量・不足例外への誤変更を検出 |
| [test_consume_negative_amount:64](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L64-L68) | R | consumeの負数を型固有例外で拒否。負量を許して逆方向へ更新する退行を検出 |
| [test_recover_success:70](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L70-L75) | F | recoverが指定量だけ正しい方向へ変化し上限を保持。加減算方向・未更新・上限取り違えを検出。0量受理の契約も既存宣言へ追加し、負数ガードの<から<=への退行を検出する |
| [test_recover_over_max:77](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L77-L82) | R | recoverの結果を上限へ補正し上限自体は維持。回復時の補正漏れを検出 |
| [test_recover_negative_amount:84](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L84-L88) | R | recoverの負数を型固有例外で拒否。負量を許して逆方向へ更新する退行を検出 |
| [test_can_consume_true:90](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L90-L93) | R | 足りる要求量をtrueと判定。常にfalseや比較反転を検出 |
| [test_can_consume_false:95](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L95-L98) | R | 残量不足をfalseと判定。常にtrueや比較反転を検出 |
| [test_can_consume_exactly_current_value:100](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L100-L103) | R | 現在値ちょうどを消費可と判定。>=を>へ変える境界退行を検出 |
| [test_can_consume_zero:105](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L105-L108) | R | 残量0でも要求0なら消費可。空なら無条件falseにする退行を検出 |
| [test_can_consume_negative_amount:110](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L110-L114) | R | 負の要求量を検証例外にする。負量を消費可と扱う退行を検出 |
| [test_is_empty_false:116](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L116-L119) | R | 正残量は空ではない。常にtrueを返す退行を検出 |
| [test_is_empty_true:121](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L121-L124) | R | 残量0は空。0を非空と扱う退行を検出 |
| [test_is_empty_negative_value:126](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L126-L129) | D | 負値はcreate時点で0へ補正済みで、負残量を判定していない。test_create_stamina_with_negative_value＋test_is_empty_trueを残せば独立契約なし |
| [test_is_full_false:131](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L131-L134) | R | 上限未満は満タンではない。常にtrue・比較反転を検出 |
| [test_is_full_true:136](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L136-L139) | R | 上限ちょうどは満タン。等量を見落とす比較退行を検出 |
| [test_get_percentage_normal:141](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L141-L144) | R | 半分の残量を0.5として返す。整数除算や百分率100への変更を検出 |
| [test_get_percentage_zero_max:146](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L146-L149) | R | 最大値0でも割合0.0。ゼロ除算を防ぐ独立境界 |
| [test_get_percentage_zero_value:151](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L151-L154) | R | 現在値0の割合0.0。下限を正数へ丸める退行を検出 |
| [test_get_percentage_full:156](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L156-L159) | R | 最大値の割合1.0。百分率100や分母違いを検出 |
| [test_str_representation:161](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L161-L164) | R | 公開文字列表現が現在値/最大値。順番逆転や片方欠落を検出。ソース文字列照合ではない |
| [test_equality_same_values:166](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L166-L170) | R | 別個体でも現在値と上限が同じなら等値。identity比較への退行を検出 |
| [test_equality_different_values:172](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L172-L176) | R | 現在値が異なれば非等値。現在値を比較から落とす退行を検出 |
| [test_equality_different_max:178](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L178-L182) | R | 上限が異なれば非等値。上限を比較から落とす退行を検出 |
| [test_equality_with_non_stamina:184](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L184-L187) | R | 別型の文字列とは非等値。型を無視した文字列表現比較への退行を検出 |
| [test_hash_consistency:189](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L189-L193) | R | 等値の別個体が同hashになる。identity由来hashで等値要素が別キーになる退行を検出 |
| [test_immutability:195](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/player/value_object/test_stamina.py#L195-L202) | F | consume(10)による減算とrecover(10)による加算の破壊的更新が相殺され最後の50だけで通る。各操作直後の元値保持を確認する |

## 履歴の確認

- [a1c01bcd](https://github.com/Motifman/llm-rpg/commit/a1c01bcd009bce48197a51b16d19244d55d2f69f)、2025-10-03: HP/MPのドメイン例外化とeq/hash/str、割合等の追加時に試験を導入。hash不一致要求も初回からあり、別の業務上の衝突禁止を守る証拠はなかった
- [9b6047f](https://github.com/Motifman/llm-rpg/commit/9b6047f121ef0fd6bbc4816cc7bd68ca322f1374)、2025-10-11: Stamina等を導入。相反する操作を最後にだけ検査する不変性試験と、補正後の負値空判定も初回から存在
- [757a2ef](https://github.com/Motifman/llm-rpg/commit/757a2ef85e3c23f516e5e63aa7842a93e1464b5e) のsrc-layout移行と [2bd6b264](https://github.com/Motifman/llm-rpg/commit/2bd6b264aacc321a310af32eb75b34441e64d36f) のimport整列を確認。これを契約変更の理由にはしていない
- [6959eadf](https://github.com/Motifman/llm-rpg/commit/6959eadfc64945a43e4b91201b5f2fba4ae7d40c) のHP表示・前回増減は実観察に由来する別機能なので、関連表示試験は保持

## 意図的な製品変更による保存性の確認

試験をmockで差し替えず、対応する製品ownerを一時変更して検出力を確認した。旧試験との比較が必要な変更では、旧試験と候補を別プロセスで実行。最後に製品の3ファイルを元のバイト列へ完全復元し、最終試験を実行した。

| 一時的な変更 | 旧試験 | 変更後の試験 | 確認したこと |
|---|---|---|---|
| HPのhashを定数0へ | test_hashだけ失敗 | 25件全通過 | 合法な衝突を誤検知しなくなる |
| MPのhashを定数0へ | test_hashだけ失敗 | 23件全通過 | 同上 |
| HPのhashをidentity由来へ | test_hash失敗 | test_hash失敗 | 同値別個体の同hashを保持 |
| MPのhashをidentity由来へ | test_hash失敗 | test_hash失敗 | 同上 |
| Stamina.consume/recoverの元値を破壊的更新 | 34件全通過 | test_immutabilityだけ失敗 | 相反する操作の打ち消しを見逃さない |
| Stamina.createの負値補正を削除 | 対照不要 | 残した負入力生成試験が失敗 | 削除した試験の生成側契約を保持 |
| Stamina.is_emptyの0を非空へ | 対照不要 | 残した空判定試験が失敗 | 削除した試験の判定側契約を保持 |
| Hp.healの負数判定を `<0` から `<=0` へ | 23件全通過 | 0量の行だけ失敗 | 0量受理の見逃しを修復 |
| Hp.damageを同様に変更 | 23件全通過 | 0量の行だけ失敗 | 同上 |
| Mp.healを同様に変更 | 21件全通過 | 0量の行だけ失敗 | 同上 |
| Mp.consumeを同様に変更 | 21件全通過 | 0量の行だけ失敗 | 同上 |
| Stamina.consumeを同様に変更 | 34件全通過 | 0量の行だけ失敗 | 同上 |
| Stamina.recoverを同様に変更 | 34件全通過 | 0量の行だけ失敗 | 同上 |

13種類の一時変更、旧試験との対照を含む24回の実行は全て意図した宣言で結果を確認した。関連試験3回と最終主対象2回を含め29回。別途、初期主対象の基準2回がある。一時変更の復元失敗や未説明の失敗はない。

## 最終検証と効率

| 対象 | 1回目の壁時計 | 2回目の壁時計 | 結果 |
|---|---:|---:|---|
| 基準の主対象 | 0.452315秒 | 0.410775秒 | 78件×2通過 |
| 変更後の主対象 | 0.378158秒 | 0.438407秒 | 83件×2通過 |

主対象の試験本体合計は基準約7ms、変更後約6–8ms。プロセス起動等の影響が大きく、少数回のばらつき範囲で高速化を主張しない。CI全体の速度改善も主張しない。今回の価値は誤検知の除去と、従来見逃していた退行の検出である。

- 対象3ファイルのruff 0.16.8: 成功
- `git diff --check`: 成功
- 製品コードの最終差分: なし
- 関連集約・HP表示78件: 基準、候補、全て復元後の最終で成功
- 独立した保存性レビュー: 指摘なしで採用可能。基準78宣言と候補をAST照合し、68保持・9修復・1削除の整合、29実行のJUnit・失敗箇所、製品のバイト復元を確認。レビュー担当による全試験の再実行は行っていない

再実行例:

```sh
uv run pytest tests/domain/player/value_object/test_hp.py tests/domain/player/value_object/test_mp.py tests/domain/player/value_object/test_stamina.py
uv run pytest tests/domain/player/aggregate/test_player_status_aggregate.py tests/domain/player/test_player_hp_delta.py
uv run ruff check tests/domain/player/value_object/test_hp.py tests/domain/player/value_object/test_mp.py tests/domain/player/value_object/test_stamina.py
git diff --check
```

## 継続する所有ルール

- 演算の期待値はownerの式を呼んで再生成せず、具体的な固定値を置く
- 0量、等量、超過、不正入力は違う境界。集約が下位を呼ばない0コスト試験でVOの0量受理を代替しない
- 元値保持は操作の直後に検査し、後続の逆操作で破壊的更新を打ち消させない
- hashは同値との整合と集合での振る舞いを守り、非等値の衝突まで禁止しない
- 直接生成の拒否とfactoryの補正を区別し、実装上の委譲だけを削除理由にしない
- 状態遷移・イベント・不足拒否は集約側の独立契約として保持する
