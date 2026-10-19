# 地図の天候と天候遷移の試験契約

## なぜ整理するか

環境ごとの天候保持を調べる3宣言は、後から追加された実地図の通知試験と同じ公開入口・同じ初期状態を準備していた。非公開属性を読むことだけを削除理由にはせず、元の入力と状態断言を通知試験へ先に移し、状態と通知の両方を守る。

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。6ファイル35元宣言を全件確認し、R32（保持）/C3（統合）とした。F（修復）/D（単純削除）は0。元の入力契約を捨てず、5ファイル32宣言・33実行例へ整理する。

## 所有者と残す層

- `PhysicalMapAggregate.set_weather`: 公開現在天候、実変更通知、屋内/地下の正規化と無通知、同値の抑制、連続通知順を所有する。受信側が手で作るイベントの試験は発生源の代わりにならない
- `WeatherZone`: ゾーンの公開構築/値取得、自然遷移/明示的な強制遷移、ゾーン通知、所属集合の防御を所有する。地図への同期とは別の契約
- `WeatherEffectService`: 移動・視界・スタミナの係数、半強度の計算、整数化、サービス自身の屋内免除を所有する。地図は先に晴れへ正規化するため、地図試験だけではサービスの環境分岐を検査できない
- `WeatherSimulationService`: 実抽選の重み反映、全列挙値の非空な正整数規則、具体的な許可/拒否を所有する。表から期待値を作らず、全件性・数値政策・生成と適用の相互運用を区別する
- 移動実行、可視タイル、環境消耗保存、SQLite保存、観測配送、グラフ天候の確定境界と乱数巻戻しは関連層として残す。今回の35宣言へ追加計上しない

`WeatherZone.create`、`force=True`、所属変更の公開操作には現在の通常呼出しを確認できなかった。型や取得値の消費側とは区別し、導入時からの公開操作を今回の重複試験だけの継ぎ目とは断定しない。`random_source`はグラフ天候の本番経路が利用する。製品・共有試験支援・共有指示ファイルは変更しない。

## 3契約の移管

| 元の宣言 | 元入力・断言 | 保持先 |
| --- | --- | --- |
| `test_outdoor_map_accepts_any_weather` | SpotId1/屋外へSTORM1.0。状態全体が要求値と同じ | `test_storm_to_blizzard_emits_event`の最初のSTORM設定直後。イベント消去や次のBLIZZARD設定より前に公開状態を検査 |
| `test_indoor_map_forces_clear_weather` | SpotId2/屋内へSTORM1.0。CLEAR型、強度1.0 | `test_indoor_set_storm_emits_no_event`へ強度1.0を追加。型と通知0件も残す |
| `test_underground_map_forces_clear_weather` | SpotId3/地下へBLIZZARD0.8。CLEAR型 | `test_underground_set_blizzard_emits_no_event`に0.8行を追加し既存1.0行も残す。両行でCLEAR型と通知0件 |

地下の元試験は晴れ強度を検査していない。その契約を勝手に追加条件へ広げない。既存の12通知宣言を全て保持し、状態保持・通知抑制・通知順の違いを残す。退役ファイルは `tests/domain/world/aggregate/test_physical_map_environment_weather.py` のみ。

## 元35宣言の判断

各試験名は基準時点の識別子。保持理由と検出できる失敗を併記する。

### tests/domain/world/aggregate/test_physical_map_environment_weather.py

| 判断 | 宣言 | 契約・検出できる誤り |
| --- | --- | --- |
| C | `test_outdoor_map_accepts_any_weather` | 屋外でSTORM強度1.0をそのまま保持する。屋外への設定を無視する、または強度を変えるを検出 |
| C | `test_indoor_map_forces_clear_weather` | 屋内へSTORM1.0を渡してもCLEAR強度1.0を保持する。屋内で嵐を受け入れる、または晴れ強度を0などに変えるを検出 |
| C | `test_underground_map_forces_clear_weather` | 地下へBLIZZARD強度0.8を渡してもCLEARを保持する。地下だけ悪天候を受け入れる、または0.8の入力時だけ正規化をしないを検出 |

### tests/domain/world/aggregate/test_physical_map_spot_weather_changed_event.py

| 判断 | 宣言 | 契約・検出できる誤り |
| --- | --- | --- |
| R | `test_clear_to_rain_emits_event` | 初期晴れ1.0から雨0.8への通知1件、対象ID、前後の型と強度。通知の欠落/重複、前後の取り違え、強度の欠落、違うスポット通知を検出 |
| R | `test_rain_to_clear_emits_event` | 雨から晴れに回復したときも通知1件と前後型が出る。晴れへの復帰を無通知にする誤りを検出 |
| R | `test_intensity_change_emits_event` | 同じRAINでも0.5から1.0へ変わると通知する。同一性比較をweather_typeだけにして強度差を無視するを検出 |
| R | `test_storm_to_blizzard_emits_event` | 既存STORMからBLIZZARDへの前後型と通知1件。雨関連以外の型変更を除外する、古い状態を取り違えるを検出 |
| R | `test_event_has_required_attributes` | FOG変更でPhysicalMapという発行元、集約ID、event_id、occurred_atを持つ通知を出す。発行元ラベルを誤る、集約IDを間違える、識別子/時刻なしのイベントを組み立てるを検出 |
| R | `test_same_weather_set_again_emits_no_event` | 別インスタンスでも同じCLOUDY0.7の再設定は通知しない。値比較を参照比較に変え、毎tick同じ天候を通知するを検出 |
| R | `test_initial_clear_to_clear_emits_no_event` | 構築直後のCLEAR1.0へCLEAR1.0を設定しても通知しない。初期状態を別の天候にする、または初回同期だけ無条件に通知するを検出 |
| R | `test_indoor_set_storm_emits_no_event` | 屋内STORM1.0の同期でCLEARへ正規化し通知しない。屋内の嵐を保持する、または正規化した架空の変化を通知するを検出 |
| R | `test_underground_set_blizzard_emits_no_event` | 地下BLIZZARD1.0の同期でCLEARへ正規化し通知しない。INDOORだけを除外してUNDERGROUNDを屋外扱いにするを検出 |
| R | `test_two_consecutive_changes_emit_two_events` | CLEAR→RAIN→STORMを変更順に2件蓄積し中間状態をつなぐ。イベントを上書きする、逆順にする、2件目の旧状態を初期値にするを検出 |
| R | `test_spot_id_matches_aggregate` | SNOW0.5への変更イベントが対象地図のspot_idを持つ。雪通知が別スポットを指す、または雪を通知対象から落とすを検出 |
| R | `test_new_weather_state_matches_current_weather` | HEAVY_RAIN0.6で通知の新状態と公開現在状態が要求値に等しい。通知だけ変更して地図状態を書き忘れる、または状態だけ正規化して通知と乖離するを検出 |

### tests/domain/world/aggregate/test_weather_transition.py

| 判断 | 宣言 | 契約・検出できる誤り |
| --- | --- | --- |
| R | `test_transition_constraints` | CLEAR→CLOUDY→RAINは受理しRAIN→CLEARは専用例外で拒否する。集約側が自然遷移制約を呼ばない、または許可遷移を拒否するを検出 |
| R | `test_force_change_weather` | force=TrueでRAIN→CLEARの不許可遷移を明示的に上書きする。forceを無視して専用例外を出すを検出 |
| R | `test_simulation_service_output` | 連続10回、生成された次状態を現実のWeatherZoneへ適用できる。抽選が許可集合外の状態を返して集約更新が失敗するを検出 |

### tests/domain/world/aggregate/test_weather_zone.py

| 判断 | 宣言 | 契約・検出できる誤り |
| --- | --- | --- |
| R | `test_create_weather_zone_success` | createで渡したID/名前/所属集合/初期状態が公開APIで読める。構築経路で別のIDや既定状態を格納する、所属を落とすを検出 |
| R | `test_validation_empty_id` | WeatherZoneIdの0と負数を専用例外で拒否する。正ID制約を外す、下限比較を誤るを検出 |
| R | `test_validation_empty_name` | 空文字と空白のみのWeatherZoneNameを専用例外で拒否する。strip検査または空値検査を消すを検出 |
| R | `test_validation_invalid_intensity` | -0.1と1.1の天候強度を専用例外で拒否する。上下限いずれかを緩める、検査を消すを検出 |
| R | `test_change_weather_emits_event` | 晴れから曇り0.5へ状態を変えWeatherChangedEvent1件に前後型と強度を持つ。集約が状態だけ変えて通知を忘れる、強度を固定するを検出 |
| R | `test_change_weather_no_change` | 同じCLEAR値への更新はWeatherChangedEventを出さない。集約が同値同期でも通知を積むを検出 |
| R | `test_spot_management` | 所属判定、追加、削除、存在しない所属削除の専用例外。集合の追加/削除を取り違える、欠落削除を黙って許すを検出 |
| R | `test_spot_ids_immutability` | 返却集合および構築入力集合の変更が内部所属を汚染しない。getterまたはconstructorのsetコピーを外すを検出 |

### tests/domain/world/service/test_weather_effect_service.py

| 判断 | 宣言 | 契約・検出できる誤り |
| --- | --- | --- |
| R | `test_calculate_movement_cost_multiplier_outdoor` | 晴れ1、雨1.2、半強度雨1.1の屋外移動倍率。係数を変える、強度補間を掛算だけにするを検出 |
| R | `test_calculate_movement_cost_multiplier_indoor` | 屋内STORMでも移動倍率1。サービスの環境分岐を削るを検出 |
| R | `test_calculate_vision_reduction` | FOGの強度1/0.5で視界減衰8/4。減衰係数を変える、強度を無視するを検出 |
| R | `test_get_max_vision_distance` | BLIZZARD強度1/0.5で最大距離3/6、屋内は無限。強度による除算を掛算にする、屋内も有限距離にするを検出 |
| R | `test_calculate_stamina_multiplier` | 晴れ1、吹雪1.8、半強度吹雪1.4、屋内1の消費倍率。係数や強度補間を変更する、屋内免除を消すを検出 |
| R | `test_calculate_environmental_stamina_drain` | 晴れ0、吹雪3、半強度吹雪1、屋内0のtick消耗。整数化を切上げへ変える、強度を無視する、屋内免除を消すを検出 |

### tests/domain/world/service/test_weather_simulation_weighted.py

| 判断 | 宣言 | 契約・検出できる誤り |
| --- | --- | --- |
| R | `test_weighted_simulation_distribution` | CLEARから実抽選1000回が70/25/5相当の幅に収まり他型を生じない。重みを渡し忘れて均等抽選にする、候補にSTORMを混ぜるを検出 |
| R | `test_all_weather_types_have_rules` | 全WeatherTypeEnumに非空の正整数重み表が存在する。列挙値追加時の規則未登録、空表、0/負重みを検出 |
| R | `test_is_transition_allowed` | CLEAR→CLOUDY、BLIZZARD→SNOWを許可しCLEAR→STORM、BLIZZARD→CLEARを拒否。遷移集合を広げすぎる/狭める、引数方向を取り違えるを検出 |

## 確認結果

- 変更前: 所有35件、関連42件が全て成功。基準失敗0
- 先行移管: 旧環境ファイルと拡張した通知試験の16件が成功。その後に旧ファイルを削除
- 3変異の旧新対照: 屋外STORM状態の書込み漏れ、屋内CLEAR強度0.5、地下BLIZZARD0.8だけ正規化をしない誤りを検査。旧の元断言と新の移管断言が同じ理由で失敗した
- 屋外変異は旧2件/新1件、屋内変異は旧1件/新1件、地下変異は旧1件/新1件が失敗。地下の既存1.0行は変異中も成功
- 製品1601ファイルを基準とバイト単位で照合し完全復元を確認。その後、所有33件と関連42件が全て成功
- 対象のruffと `git diff --check` が成功。試験は576行から527行（+6/-55、純49行減）。製品/共有試験支援の差分は0
- 全リポジトリ試験、実LLM、実ネットワークの試験は実行していない。通常CIのPython3.10/pytest選択に含まれ、特別な登録変更はない

再実行は `uv run pytest` に次の5ファイルを渡す。

- `tests/domain/world/aggregate/test_physical_map_spot_weather_changed_event.py`
- `tests/domain/world/aggregate/test_weather_transition.py`
- `tests/domain/world/aggregate/test_weather_zone.py`
- `tests/domain/world/service/test_weather_effect_service.py`
- `tests/domain/world/service/test_weather_simulation_weighted.py`

関連確認は実地図の天候効果4例、移動の天候3例、可視タイル1例、世界シミュレーション6例、SQLite天候ゾーン6例、屋内観測7例、天候/昼夜確定境界11例、環境効果4例の計42例。関連ファイルは変更しない。

## 今後の所有ルール

- 同じ入口・同じ入力の状態試験と通知試験を増やす前に、この保持先へ足せるか確認する。状態と通知を同じことだとみなして片側を省かない
- 初期値、公開取得値、強度、列挙値全件性、通知識別情報は、小さい試験や構造の検査という理由で捨てない
- 生成サービスと許可判定が同じ表を使う相互運用試験は、規則内容の独立証明ではない。具体的な許可/拒否と実抽選の分布試験も残す
- 現在の分布試験と10ステップの相互運用試験には未固定乱数の限界がある。今回の統合による安定性改善や新規不具合検出の向上は主張しない

## 導入の根拠

- [天候・資源採取の導入](https://github.com/Motifman/llm-rpg/commit/d1e5660c3a55878f5f8ebc98227f32236afeacbd): 環境別保持、ゾーン、効果、自然遷移の試験が追加された
- [世界シミュレーションへの天候効果](https://github.com/Motifman/llm-rpg/commit/2e59704ba43df07f93e2db383c9ae17c13eb5d80): 正整数ゾーンIDとスタミナ倍率/消耗を追加
- [地図の天候変更通知](https://github.com/Motifman/llm-rpg/commit/6e55f27bdfa0de6641ea2b5110a6859b56640cb4): 屋外の実変更だけ通知する入口と12宣言を追加
- [天候と昼夜の確定境界](https://github.com/Motifman/llm-rpg/commit/a80c9d4e52a3a27a346c4fed13632f385bf5868e): グラフ天候の専用乱数と巻戻しを導入。設計判断182は直接呼出しのモジュール乱数を維持する
- `docs/domain_events_observation_spec.md` と `docs/agent_design_principles.md`: 天候通知の受信者と観測が行動を起こす責務を確認した

範囲外の旧物理地図天候表示には、列挙値の生値を文面に含める既存試験と表示方針の仕様表現差がある。実運用での到達は未検証であり、今回の製品変更・試験削除・Issue作成には含めない。

## main更新後の確認

公開前に `d209c63707827317f9c6c1409ce873b91a0af713` を取り込んだ。旧基準からの28ファイル変更は天候の所有者・試験・関連試験・依存固定を変更していない。旧基準の調査・変異証拠を保持し、監査候補へ更新を統合した。

所有者、元の担当試験、関連試験、直接の通常呼出し、CI設定、依存固定など34ファイルの内容が旧新基準で同じことを確認した。監査の試験差分も統合前後で同一。製品1601ファイルは新しいmainと一致する。

更新後の作業場所でも所有33件・関連42件が全て成功した。変更した試験のruffと差分の空白検査も成功している。これは天候の限定範囲の再検証であり、更新main全体の試験結果を意味しない。

## 直前のmain再更新後の確認

続いて `00aeddef745aba1ec7743ca3118bbe239a01b3c3` を取り込んだ。d209からの59ファイル変更にも、天候の所有者・元試験・関連試験・依存固定の変更はなかった。共通fixtureを加えた55ファイルを旧新基準で照合し、全件同一を確認した。追跡対象のconftest.pyは両基準に存在しないことも確認した。監査の試験差分も変更していない。

新基準の製品1599ファイルは監査候補と全件一致する。1601からの2ファイル減は上流の製品削除によるもので、この監査の削除成果には含めない。

00aeを統合した状態で所有33件・関連42件が全て成功し、対象ruffと差分の空白検査も成功した。以後の変更はこの記録だけで、試験・製品の内容は検証時と同じ。以前の基準・変異・保存審査の証拠は上書きせず保持する。全体試験・実LLM・実ネットワーク試験は未実施のままである。
