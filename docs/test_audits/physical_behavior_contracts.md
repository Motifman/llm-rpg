# 観測生成・技能選択の試験契約

> 過去の試験監査（2026-10-25追記、Issue #1862）。削除済みのタイルマップ・当たり判定に関する実装や試験の記述を含む。
> 本文の呼出元・保持先・件数は監査当時の記録で、現在の保証ではない。現存する領域もあるため一括して退役とは扱わない。[世界の現在の構成](../game/world_architecture.md)を参照。

## 範囲と結論

5ファイルの元58宣言を読み、R47（保持）/F8（修理）/C1（統合）/D2（削除候補）と判定した。今回は旧生態のF5と旧コンテキストのD2を未完の保留とし、元51宣言（R47/F3/C1）を対象にした。保留7件は本文とスキップ指定を変更していない。

- 基準main: `d209c63707827317f9c6c1409ce873b91a0af713`
- 当初の `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f` でも基準を実行。#1693の統合後に対象・所有者・直接呼出元・依存固定・CIの不変を確認し、新mainで再実行した
- 変更は4試験ファイルと本記録のみ。製品・独立した共通支援・CIの変更はない
- 元58宣言から57宣言へ。Z軸の行を追加したため実行行は58のまま。成功53には保留中のPlanActionContext 2件が含まれる。元51宣言の監査範囲と、成功53/スキップ5という実行件数を混同しない

## 主担当と残す層

`MonsterBehaviorCoordinator.process_actor_behavior` は文脈生成、観測生成、遷移計算、集約への適用、行動決定を順に呼ぶ。

- 実地図から敵対・脅威・選択対象を作る: `test_behavior_service.py`。上位の文脈捕捉試験は `build_observation` を差し替えており、生成結果の検査を代替しない
- 射程と使用可能集合からスロットを選ぶ: `test_skill_selection_policy.py`。First/Bossは候補処理が別なので、似た空入力や射程外試験も各実装の独立契約として残す
- コンテキストの省略既定と不正入力の拒否: `test_behavior_context.py`。生成試験というだけで削除しない
- 観測の公開保持値・属性再代入拒否・値の等価性: `test_behavior_observation.py`。属性参照先のリストを深く不変にする保証や、内部WorldObjectの構造的等値は追加しない
- 観測から遷移意図、遷移意図から状態・追跡・通知への適用はモンスター側に残す。視認と被弾は別の入口として扱う

`Observation.current_tick` と `target_context` は現在、下流で読む箇所が見つからない公開保持契約である。生成時の対象選択には `target_context` を直接渡すが、観測に保存された値の利用とは区別する。First/Boss具体型の本番生成箇所も見つからず、公開exportとresolverの注入型契約を実利用の実績と混同しない。

## 修理した検査

1. 観測のOR条件は、敵対リストだけ、選択対象だけ、誤った脅威分類でも成功した。元のgoblin100/(0,0)、human1/(2,0)、視界5/360度、Growth(0.2,True)、tick0を保ち、敵対=[player]、脅威=[]、選択対象=playerを個別に確認する。growth同一性とtick非Noneを残し、tick0の値まで確認する
2. Z軸差1・射程1の成功だけではZを無視しても成功した。元のactor100/(0,0,0)、target1/(0,0,1)、slot0/range1/mp10→0の行を残し、同じ配置のrange0→Noneを追加した。期待値は固定値で、製品の距離関数から生成しない
3. 観測の等価性試験は3属性を比較するだけだった。元の空集合・対象None・集結(1,1)の2観測と3確認を残して観測自体の等値を検査し、集結(1,2)だけ異なる観測を不等値の対照にした。導入時の「同じ内容の観測は等しいこと（値の比較）」という明示仕様に沿う修理であり、新たな深い等価性は約束しない

## 統合した1宣言

`TestGrowthContext.test_create_success_minimal` の `(effective_flee_threshold=0.0, allow_chase=True)` は、境界試験の `ctx_low` と同じ入力だった。元の閾値0.0確認に加えて `allow_chase is True` を境界試験へ先に移し、旧宣言が残る段階で成功を確認してから重複宣言だけを除いた。1.0/False、0.3/True、0.5/False、4つの拒否入力は保持する。退役ファイルや削除する製品入口はない。

## 未完の保留7宣言

旧生態5件は、[plan_action撤去](https://github.com/Motifman/llm-rpg/commit/2607c4d561e8538bc9383b504b0ec58f3a270d9d)で状態/移動確認をORの観測確認に置換され、将来実装時対応としてスキップされた。[責務移管](https://github.com/Motifman/llm-rpg/commit/867365382e00507fd53dd80a923b89496d40e9f2)で旧戦略とcomponentの行動状態もなくなった。視認時の生態規則を廃止する明示判断は確認できない。

- `test_flee_only_spots_target_goes_flee`: 視認したFLEE_ONLYが逃走する元契約
- `test_patrol_only_ignores_target`: 視認してもPATROLを維持する元契約。現本文は廃止されたstate引数を渡すため、スキップ解除だけでは準備段階で失敗する
- `test_ambush_in_range_chases` / `test_ambush_out_of_range_does_not_chase`: 初期位置から待ち伏せ範囲内外の相手を視認したときの追跡可否
- `test_territorial_beyond_radius_returns_to_initial`: 実地図で初期(2,2)、actor(7,7)、半径3、対象(10,10)からRETURNとMOVEまで進む元契約

現行のFLEE_ONLY/PATROL_ONLY/AMBUSH保持試験と#1719は被弾時であり、上の視認時を代替しない。縄張りの判断・集約適用には現行の部分的な証拠があるが、元の実地図から移動決定までの移管完了とは数えない。静的な経路差を記録しただけで、製品不具合を実行再現したとは主張しない。

`TestPlanActionContext` の2件は、旧戦略に渡す観測と共有イベントリストを検査する。本体宣言と試験以外の参照がなく、製品本体と一体で取り除く候補だが、この変更は製品削除を含まないため保持して保留する。

## 全58宣言の判定

F5/D2の「保留」は未適用で、完了範囲に含めない。RのうちGrowth境界試験だけがCの確認式を受け取り、残るR46と保留7は宣言の構文木が不変である。

### `tests/domain/world/service/test_behavior_service.py`

| 元宣言 | 判定 | 契約・保持先 |
|---|---|---|
| `TestAutonomousBehaviorComponent::test_validation_success` | R | 視界5・移動確率0.5と巡回点/技能の空既定値を受理する公開設定。初期値の取り違えを検出する |
| `TestAutonomousBehaviorComponent::test_validation_errors` | R | 負視界、361度視野角、1.5の移動確率を各ドメイン例外で拒否する。別ガードに隠れない3独立入力 |
| `TestAutonomousBehaviorComponent::test_validation_random_move_chance_boundary` | R | 確率0と1の両端を受理する。厳密不等号への誤変更を検出する |
| `TestBehaviorService::TestBuildObservationAndErrors::test_actor_not_in_map_raises_object_not_found` | R | 未配置99999の観測生成をMAP.OBJECT_NOT_FOUNDで拒否し対象を知らせる。空観測への誤握りつぶしを検出する |
| `TestBehaviorService::TestBuildObservationAndErrors::test_build_observation_returns_observation_with_visible_hostiles` | F | 実地図のgoblin100/(0,0)からhuman1/(2,0)を敵対リストと選択対象へ入れ、growth0.2/Trueとtick0を渡す。ORはリスト欠落/選択欠落/誤脅威分類を見逃す |
| `TestBehaviorService::TestBuildObservationAndErrors::test_build_observation_non_autonomous_returns_empty_like_observation` | R | 普通のActorComponentでは敵対/脅威/対象なしの観測を返す。自律アクター用属性の無条件参照を検出する |

### `tests/domain/world/service/test_ecology_behavior.py`

| 元宣言 | 判定 | 契約・保持先 |
|---|---|---|
| `TestEcologyFleeOnly::test_flee_only_spots_target_goes_flee` | F（保留） | 恒久skipに加え旧plan_actionの状態/移動確認をORの観測確認へ置換済み。撤去履歴2607c4dは将来実装時対応と記す。被弾時の生態試験は視認時の代替にならず、元入力と本文を保持する |
| `TestEcologyPatrolOnly::test_patrol_only_ignores_target` | F（保留） | 恒久skipに加え旧plan_actionの状態/移動確認をORの観測確認へ置換済み。撤去履歴2607c4dは将来実装時対応と記す。被弾時の生態試験は視認時の代替にならず、元入力と本文を保持する |
| `TestEcologyAmbush::test_ambush_in_range_chases` | F（保留） | 恒久skipに加え旧plan_actionの状態/移動確認をORの観測確認へ置換済み。撤去履歴2607c4dは将来実装時対応と記す。被弾時の生態試験は視認時の代替にならず、元入力と本文を保持する |
| `TestEcologyAmbush::test_ambush_out_of_range_does_not_chase` | F（保留） | 恒久skipに加え旧plan_actionの状態/移動確認をORの観測確認へ置換済み。撤去履歴2607c4dは将来実装時対応と記す。被弾時の生態試験は視認時の代替にならず、元入力と本文を保持する |
| `TestEcologyTerritorial::test_territorial_beyond_radius_returns_to_initial` | F（保留） | 恒久skipに加え旧plan_actionの状態/移動確認をORの観測確認へ置換済み。撤去履歴2607c4dは将来実装時対応と記す。被弾時の生態試験は視認時の代替にならず、元入力と本文を保持する |

### `tests/domain/world/service/test_skill_selection_policy.py`

| 元宣言 | 判定 | 契約・保持先 |
|---|---|---|
| `TestFirstInRangeSkillPolicy::test_select_slot_returns_none_when_no_skills` | R | 空技能集合から選択しない。空入力の添字参照/既定技能捏造を検出する |
| `TestFirstInRangeSkillPolicy::test_select_slot_returns_none_when_all_out_of_range` | R | 遠距離(20,20)では射程1/2の技能を選ばない。距離判定の欠落を検出する |
| `TestFirstInRangeSkillPolicy::test_select_slot_returns_first_in_range` | R | 複数技能が射程内のとき入力順先頭slot0を選ぶ。末尾/長射程優先への誤変更を検出する |
| `TestFirstInRangeSkillPolicy::test_select_slot_skips_out_of_range_then_returns_next` | R | 先頭射程0を飛ばして射程5のslot1を選ぶ。最初の候補で打ち切る退行を検出する |
| `TestFirstInRangeSkillPolicy::test_select_slot_exactly_at_range` | R | 距離1/射程1の等値を許す。<への誤変更を検出する。単軸のため距離方式の違いは証明しない |
| `TestFirstInRangeSkillPolicy::test_select_slot_single_skill_in_range` | R | 入力リスト位置0ではなく実slot_index2を返す。列挙添字と技能スロットの混同を検出する |
| `TestFirstInRangeSkillPolicy::test_select_slot_z_axis_in_distance` | F | z差1の距離を射程計算へ含める。元の射程1許可だけではz無視も成功するため、元入力を残して同座標の射程0拒否を足す |
| `TestFirstInRangeSkillPolicy::test_select_slot_with_usable_slot_indices_restricts_to_slot` | R | 使用可能集合{1}を優先して射程内slot0を除外する。使用可能情報の無視を検出する |
| `TestFirstInRangeSkillPolicy::test_select_slot_with_usable_slot_indices_none_in_range_returns_none` | R | 使用可slot1は射程外、射程内slot0は不可という競合でNone。射程/使用可の片方だけの採用を検出する |
| `TestFirstInRangeSkillPolicy::test_select_slot_with_empty_usable_slot_indices_returns_none` | R | 空の使用可集合は制限なしではなく利用不可。空集合の真偽によるNone混同を検出する |
| `TestFirstInRangeSkillPolicy::test_select_slot_with_context_none_ignores_usable` | R | 明示Noneでは使用可制限を適用せずslot0。省略引数の別試験と違う呼出し形を保つ公開API契約 |
| `TestBossSkillPolicy::test_select_slot_returns_none_when_no_skills` | R | 空技能集合から選択しない。空入力の添字参照/既定技能捏造を検出する |
| `TestBossSkillPolicy::test_select_slot_returns_none_when_all_out_of_range` | R | 遠距離(20,20)では射程1/2の技能を選ばない。距離判定の欠落を検出する |
| `TestBossSkillPolicy::test_select_slot_without_context_returns_first_in_range` | R | Bossでも文脈省略時に入力順先頭の射程内slot0を返す。無条件AOE情報要求を検出する |
| `TestBossSkillPolicy::test_select_slot_with_targets_in_range_by_slot_returns_aoe_priority` | R | 使用可0/1のうち対象数1対3でslot1。通常ポリシーの先頭選択への誤委譲を検出する |
| `TestBossSkillPolicy::test_select_slot_with_usable_slot_indices_filters_slots` | R | Boss独自の候補絞込で不可slot0を落としslot1。First側とは実装所有者が独立 |
| `TestBossSkillPolicy::test_select_slot_usable_slot_none_in_range_returns_none` | R | Boss独自の候補生成でも射程内だが不可のslot0を選ばない。候補絞込漏れを検出する |
| `TestBossSkillPolicy::test_select_slot_targets_by_slot_missing_slot_uses_zero` | R | 対象数未登録slot0が例外にならず、登録数2のslot1が勝つ。正確な0以外をすべて弁別する試験とは主張しない |
| `TestBossSkillPolicy::test_select_slot_empty_targets_by_slot_returns_first_in_range` | R | 空対象数辞書では最大値探索せず先頭slot0。空辞書処理の退行を検出する |
| `TestBossSkillPolicy::test_select_slot_usable_and_targets_combined` | R | 対象数最大だが不可のslot1を落とし、可slot0/2の中で3体のslot2を選ぶ。フィルタ前の最大値選択を検出する |

### `tests/domain/world/value_object/test_behavior_context.py`

| 元宣言 | 判定 | 契約・保持先 |
|---|---|---|
| `TestTargetSelectionContext::test_create_empty_defaults` | R | 対象選択のHP/脅威辞書の空既定。データ無しを最近距離へ委ねる公開APIの省略契約 |
| `TestTargetSelectionContext::test_create_with_data` | R | ID1のHP0.5と脅威10を異なる辞書に保持。対象選択ポリシーが二情報を別々に解釈する契約 |
| `TestSkillSelectionContext::test_create_empty_defaults` | R | 技能使用可集合と件数辞書の空既定。空集合を制限なしと取り違える変更を防ぐ公開省略契約 |
| `TestSkillSelectionContext::test_create_with_data` | R | 使用可{0,1}と対象件数0:2/1:1を同時保持。利用可集合と件数の転記漏れを検出する公開入力契約 |
| `TestGrowthContext::test_create_success_minimal` | C | Growth(0.0,True)は境界試験に全く同じ入力あり。allow_chase is Trueを境界試験へ先に移してから重複宣言を除く |
| `TestGrowthContext::test_create_success_boundary_flee_threshold` | R | Growth閾値0と1を両方受理しFalseを保つ。境界の過剰拒否を検出する。最小生成のTrue確認を受け取る |
| `TestGrowthContext::test_create_success_mid_value` | R | Growth(0.3,True)の通常値の受理・保持。整数化/端点だけ許容する誤変更を検出する |
| `TestGrowthContext::test_create_success_allow_chase_false` | R | Growth(0.5,False)でFalseを保持する。中間値でFalseだけを既定Trueへ戻す退行を検出する |
| `TestGrowthContextValidation::test_effective_flee_threshold_negative_raises` | R | -0.1を範囲違反のドメイン例外で拒否。下限欠落を検出する |
| `TestGrowthContextValidation::test_effective_flee_threshold_over_one_raises` | R | 1.01を範囲違反のドメイン例外で拒否。上限欠落を検出する |
| `TestGrowthContextValidation::test_effective_flee_threshold_not_number_raises` | R | 文字列0.5を数値型違反のドメイン例外で拒否。暗黙変換/組込み例外漏れを検出する |
| `TestGrowthContextValidation::test_allow_chase_not_bool_raises` | R | 整数1をbool扱いせず拒否。真偽値への暗黙変換を検出する |
| `TestPlanActionContext::test_create_with_default_event_sink` | D（保留） | 旧PlanActionContextの空list既定と観測同一性だけを検査。全追跡ファイル検索で本番呼出しなし。製品撤去と一体の削除候補だが今回製品変更不可のため本文不変・完了除外 |
| `TestPlanActionContext::test_create_with_custom_event_sink` | D（保留） | 旧PlanActionContextが同じsinkへ追記する契約のみ。本番戦略とplan_actionが撤去済み。製品撤去と一体の削除候補として保留 |

### `tests/domain/world/value_object/test_behavior_observation.py`

| 元宣言 | 判定 | 契約・保持先 |
|---|---|---|
| `TestBehaviorObservationCreation::test_create_with_defaults` | R | 引数省略時の観測の空集合/Noneの公開既定値。製造側は値を明示するため既定値の変化を代替検出できない |
| `TestBehaviorObservationCreation::test_create_with_empty_lists_explicit` | R | 明示空リストと対象Noneで観測生成できる公開入力契約。省略入力と区別して保持する |
| `TestBehaviorObservationCreation::test_create_with_skill_context` | R | 技能文脈{0,1},件数{0:2,1:1}の観測への格納。同一文脈をresolverへ渡す公開キャリア契約。現アプリ試験は観測生成をモックしており代替にならない |
| `TestBehaviorObservationCreation::test_create_with_growth_context` | R | Growth(0.3,True)の同一文脈と値を観測に保持。遷移サービスへ成長条件を渡す契約。値を固定既定へ戻す退行を検出する |
| `TestBehaviorObservationCreation::test_create_with_target_context` | R | ID1のHP0.5/脅威10を含む同一文脈を観測に保持する公開キャリア契約。欠落/別参照差替えを検出する。選択政策へ渡すのは生成時の入力でありObservation.target_contextの下流読取ではない |
| `TestBehaviorObservationCreation::test_create_with_pack_rally_coordinate` | R | 集結位置(8,5)を保持しresolverへ渡す公開値契約。x/y取り違えを検出する |
| `TestBehaviorObservationCreation::test_create_with_current_tick` | R | tick100の同一値を保持する公開キャリア契約。欠落/誤初期化を検出する。Observation.current_tickを下流が実際に読む利用は未確認 |
| `TestBehaviorObservationCreation::test_create_with_selected_target` | R | 対象ID1/(3,4)の同一実体を保持。mockは値の代役であり判定結果を自作していない。対象の誤置換を検出する |
| `TestBehaviorObservationCreation::test_create_with_visible_threats_and_hostiles` | R | 脅威[10]、敵対[10,20]、選択20を同時保持。二つの候補集合を混同する退行を検出する |
| `TestBehaviorObservationImmutability::test_frozen_visible_threats_assign_raises` | R | 観測の脅威属性の再代入を拒む。参照先listの深い不変性までは約束しない |
| `TestBehaviorObservationImmutability::test_frozen_selected_target_assign_raises` | R | 観測の選択対象の再代入を拒む。生成後の対象差替えを防ぐ公開不変性契約 |
| `TestBehaviorObservationImmutability::test_frozen_current_tick_assign_raises` | R | 観測時刻の再代入を拒む。観測の時点を書き換える退行を検出する |
| `TestBehaviorObservationEquality::test_same_values_equality` | F | 導入3d09646の明示仕様「同じ内容の観測は等しいこと（値の比較）」を守る。元の3属性比較だけでは観測自体の等価性を検査しないため、同じ元2観測の==と集結位置だけ違う観測の!=を加える。内部WorldObjectの深い構造的等値は約束しない |

## 履歴・隣接範囲

- [技能選択の導入](https://github.com/Motifman/llm-rpg/commit/5386f882e2834b507552dcbda5c05b5f4a147409): 距離と入力順から技能を選ぶ責務を独立
- [GrowthContext検証の導入](https://github.com/Motifman/llm-rpg/commit/8694788913801447ca5e27437356f1adaa266bf7): 閾値の範囲・数値型とbool検証の理由
- [観測値の分離](https://github.com/Motifman/llm-rpg/commit/3d096463feca28d4b95752c182ae6da424536677): 公開値と等価性の既存意図

#1666の同期戦闘配送、#1713の反応/探索、#1719の被弾、#1721の縄張り、#1726の観測入力/遷移適用、#1728の集約公開入口、#1747の通知を照合した。対象4試験・所有者と直接の変更パス重複はない。これらの未統合PRの追加保証を現mainの保証と混同せず、変更や完了数の再計上もしない。

## 検証

Python 3.10.22、専用作業木のsrc読込確認、外部通信遮断、直列で実行した。有料LLMや実API試験は実行していない。

| 段階 | 成功 | スキップ | 意味 |
|---|---:|---:|---|
| 旧main基準 | 53 | 5 | 元58宣言全収集 |
| 新main基準 | 53 | 5 | 変更後の基準で再検証 |
| 確認式移管段階 | 54 | 5 | Cの旧宣言を残して先に保持先を検証 |
| 最終5ファイル | 53 | 5 | 57宣言、Z軸表を展開して58実行行 |
| 最終・隣接込み | 107 | 5 | 対象選択、観測遷移、文脈builder、実tickの可視対象追跡を含む |

- 改善変異7: 選択対象欠落、敵対リスト欠落、敵対を脅威へ誤分類、tick誤値、Z無視、観測の等値無効化、集結位置を比較から除外。全て旧成功/新失敗
- 保持変異2: Growth閾値0を拒否、閾値0の追跡許可をFalseへ上書き。旧新とも失敗
- 無害対照1: Firstのローカル変数名だけを変更。旧新とも成功
- 有効な旧新版比較は20実行。対照作成時にメソッド名まで変えた初回2実行は意味保存にならないため除外し、ローカル変数だけの対照で再実行した
- 変異後は製品1601ファイルの内容ハッシュが基準と一致。主作業木にも製品差分なし
- 対象ruff、差分空白検査に成功。全リポジトリ試験はローカル未実行
- CIは通常の全収集で対象を含むため登録変更なし。既定でquality/live_apiは除外される

5試験の行数は1005→1019、差分+26/-12。内数の支援関数は107→107行、独立支援ファイルは0変更。製品差分は0行。本記録は文書として別計上する。

今後の監査でも、三者択一で複数の出力契約を代表させず、距離の検査には方式や軸の無視を区別する入力を置く。スキップされた旧入口は名前の似た新入口で代替済みとせず、元の条件と観測可能な結果がどこへ移ったかを確認する。

## 公開前のmain更新と再検証

公開準備後に#1694/#1754がmainへ入り、基準が `00aeddef745aba1ec7743ca3118bbe239a01b3c3` へ進んだ。旧監査のコミットと証拠を残し、更新mainをマージした。履歴の付け替えは行っていない。

- 上流の59変更は補助LLMの記録・再解釈経路・プロンプト順序設定など。対象、所有者、直接呼出元、隣接試験、依存固定、CIの35パスは内容が不変
- 4試験の内容と試験だけの差分は保存承認時と同一。旧51宣言の判断、元入力、保留7件は変えていない
- 更新mainで対象・隣接を再実行し、107成功・5スキップを確認。新しい有料LLM・実API実行はない
- 更新mainでは上流が製品2ファイルを撤去したため、製品は1599ファイル。全て新mainと同一。前節の1601ファイルは旧基準での復元証拠として残す
- 本変更の製品差分0、試験差分+26/-12は変わらない。追加はこの更新記録だけ
