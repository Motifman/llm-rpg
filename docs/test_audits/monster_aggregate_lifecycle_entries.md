# モンスター集約の生命状態と時刻契約

## 目的と完了範囲

残っていた元48宣言を全件読み直し、うち47宣言をこの変更の保存確認対象とした。判定は対象47についてR40/F1/C6/D0。回避を手書きで調停する元24は、#1732が共通計算の同じ表を変更中で、旧Monsterの回避率0.03・乱数0.0を含まないため、「#1732統合後のモンスター回避移管」としてC案のまま未解決とし、原文を維持する。元48全体ではR40/F1/C7（うち1保留）/D0となる。

同じ出現・復活を重ねて作る時刻/初回座標の試験と、同じ成長能力値を別々に取り出す試験を公開入口へまとめる。自然寿命には非0の出現時刻を加え、経過時間を世界の絶対時刻と取り違える欠落を検出する。短い既定値、取得関数、専用例外、構築状態は独立した契約として残す。

公開基準は#1730の`464ffbc859eb273130b53f8e27820fda27e91e2a`。先行の元60宣言（復活・状態効果等7、行動32、栄養・資源21）は再計上しない。元47は41宣言43行になり、ファイル全体は98宣言116行から92宣言112行へ、試験コードは2100行から2083行へ変わる。試験差分は追加40/削除57行。製品・共通準備・支援コードの変更はない。

## 保持する層

- `MonsterLifecycleState`はHP/MPや生死の純粋な状態更新を所有する。集約は公開入口の拒否、入力受渡し、状態への代入、位置・時刻・通知の生成を所有する
- `MonsterSpawnSlotService`は復活候補の選択と保存を所有する。その試験では集約の判定や座標を模造しており、集約の実装を置き換える証明ではない
- `GrowthStage`は乗率等の値域を所有する。集約が経過時間から現在段階を選び、各能力軸や逃走閾値に適用する契約はここに残す
- 通知の検査は集約内の未配信列までであり、外部の配送や観測への到達を証明したとは言わない
- 例外試験が元から要求していた専用例外と入力を残し、拒否時の全状態/全通知の原子性は新しい契約として追加しない

## 先に移してから除去した6宣言

| 元番号 | 元の入力・確認 | 保持先 |
|---|---|---|
| 6 | create直後の復活座標None | 1 `test_create_success` |
| 75 | create直後の出現時刻None | 1 `test_create_success` |
| 7 | 出現座標(10,20,0)、地点1、時刻0から初回復活座標を得る | 2 `test_spawn_success`の元行 |
| 76 | 出現座標(0,0,0)、地点1、時刻42を保存 | 2の追加行。元2の座標(10,20,0)/時刻0は残す |
| 10 | 出現0→100被害で死亡100→別位置へ復活200。出現時刻0/200 | 8 `test_get_respawn_coordinate_after_respawn_unchanged` |
| 85 | 出現0、現在50の幼体能力値の最大HP80/MP40 | 81の攻撃16/防御12/速度8と同じ取得結果 |

出現通知の座標は各行の固定辞書で比較し、製品の変換関数で期待値を作らない。元宣言を残した段階49行が成功してから6宣言を除去し、候補43行の成功を確認した。空になった`TestSpawnedAtTick`以外の試験クラスや共有準備を整理目的で変更していない。

## 自然寿命の補強

元53の「出現0・寿命50・現在50でTrue/DEAD/NATURAL」をそのまま表の一行に残す。別行は出現37、寿命50に対し現在86（経過49）でFalse/ALIVE、現在87（経過50）でTrue/DEAD/NATURALを確認する。期待する時刻は86/87の固定値であり、検査対象の計算から作らない。

[自然寿命の導入](https://github.com/Motifman/llm-rpg/commit/f74bb8b1e779d06e7871422da71135db6fc484ce)は、出現時刻からの経過で寿命を測ることを明記している。経過計算を現在の絶対時刻だけに変えた対照では元47行すべてが成功し、候補は追加した非0起点のFalse確認で失敗した。元の境界条件を変える対照では、旧0→50行も候補の同じ行も失敗する。

既定の未出現、死亡済み、寿命None、寿命0、寿命100の半分時点を除かない。未出現の試験が出現時刻Noneの判定だけを単独で証明しているとは主張しない。

## 戦闘計算の成功と回避を分けて判断する

元23の成功は、実テンプレートの能力値、実`CombatLogicService`、実集約のHPと被害通知を結ぶ。攻撃50/防御15から42被害となりHP58を検査するため、計算所有者と固定被害入口の試験へ分けず保持する。通常被害を切り上げる変異で、旧新ともこのHP58確認が失敗した。手書きifそのものが本番のハンドラ分岐を証明するという意味ではない。

元24の回避は計算が先に完結し、引数なしの`record_evasion()`へDamageも数値も渡さない。将来の移管案は次の通りだが、この変更では実施せず完了に含めない。

- 攻撃の全能力値100/30/50/5/12/0/0、防御100/50/20/15/10/0.05/0.03、乱数0.0、既定倍率/設定を共通計算所有者の表へ移す
- 座標(1,1,0)・時刻0の無傷HP100を維持し、回避通知1件の座標/HP100を直接回避入口へ移す
- 元25の負傷HP80/座標(2,3,0)の行と全確認を残す
- 共通計算側#1732の固定差分には旧Monsterの全入力が含まれないことを照合済み。#1732統合後に同じ表へ移管する。統合自体は今回の承認に含まれず、手書きifという見た目だけで削除しない

## 全48宣言の台帳

位置は基準#1730のもの。Rは保持（必要な移管先としての拡張を含む）、Fは契約を保持して補強、Cは入力と確認を保持先へ移管する。

| 元番号・宣言 | 判定 | 保護する契約・保持先 | 検出する回帰または判断理由 |
|---|---|---|---|
| 1 [`test_create_success`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L139) | R | 未出現の個体ID/テンプレート/DEAD/位置なしと作成通知1件・属性を保持。ID6の復活座標None、ID75の出現時刻Noneを受け入れる | 値オブジェクトが正しくても、createの状態指定・識別子受渡し・通知追加が壊れる |
| 2 [`test_spawn_success`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L157) | R | 指定地点・座標・時刻でALIVE/満HP100・MP50。出現通知の位置/地点を保持。ID7の初回座標とID76の非0時刻42・座標0を表で受け入れる | spawnの代入、時刻の受渡し、HP/MP初期化、通知座標のいずれかの破損 |
| 3 [`test_spawn_already_spawned_raises_error`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L179) | R | 位置0で出現済み個体へ位置1/tick1の二度目のspawnはMonsterAlreadySpawnedException | 専用例外の削除/取り違え/二重出現を検出。全状態や通知の原子性は元契約に含めず追加しない |
| 4 [`test_spawn_with_pack_id_sets_pack_and_leader`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L187) | R | spawnのgoblin_pack_1とis_pack_leader=Trueを公開値へ保存 | 群れIDやTrueを無視する回帰。群れ省略/復活とは別の引数受渡し |
| 5 [`test_spawn_without_pack_keeps_none`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L194) | R | 群れ引数省略時はpack_id=None/is_pack_leader=False | 既定群れや既定リーダーを誤って設定する回帰。短い既定値契約を保持 |
| 6 [`test_get_respawn_coordinate_before_spawn_returns_none`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L200) | C | create直後get_respawn_coordinate=NoneをID1へ移管 | 同一create準備と未出現状態の公開契約を一箇所へまとめる。getterだから削除するのではない |
| 7 [`test_get_respawn_coordinate_after_spawn_returns_initial_position`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L204) | C | create→spawn((10,20,0),spot1,tick0)後の初回復活座標をID2の元行へ移管 | ID2と完全に同じ公開入力。保持先へ同一assertを入れてから削除 |
| 8 [`test_get_respawn_coordinate_after_respawn_unchanged`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L212) | R | spawn0→100被害で死亡tick100→別位置(5,5,0)へ復活tick200でも初回位置0を保持。ID10の初回tick0と復活tick200を受け入れる | 復活で初回位置まで上書きする回帰を捕捉。復活成功59は先行所有なので変更しない |
| 10 [`test_respawn_sets_spawned_at_tick`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L231) | C | 同じspawn0→死亡100→復活200の時刻0/200をID8へ移管 | ID8と同一入力のライフサイクル軌跡。非0の更新を失わない |
| 20 [`test_apply_damage_success`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L634) | R | ALIVE/HP100への30被害でHP70、被害通知1件・damage30/current_hp70・集約識別を保持 | MonsterLifecycleStateの算術だけでは集約の代入忘れ/通知漏れ/誤値を検出できない |
| 21 [`test_apply_damage_not_spawned_raises_error`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L653) | R | 未出現へのdamage10/tick10はMonsterNotSpawnedException | 未出現は正HP100なのでHPだけの生存判定への置換でも拒否が消え検出できる |
| 22 [`test_apply_damage_already_dead_raises_error`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L657) | R | spawn後damage100/tick10で死亡した個体へのdamage1/tick11はMonsterAlreadyDeadException | 死亡後を未出現と取り違えた例外や再被害受理を検出。正HP死の追加や原子性を必須とはしない |
| 23 [`test_application_style_damage_flow_success`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L667) | R | 実テンプレートBaseStats→実CombatLogicService（乱数0.9）→実集約apply_damageで42被害/HP58/被害通知1件 | 攻撃50/防御15の計算結果の値渡しと集約反映を一緒に保護する。成功の結合を分割しない。手書きif自体が製品の調停を証明するとは言わない |
| 24 [`test_application_style_damage_flow_evaded`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L701) | C・保留 | 実計算の旧全BaseStatsとrandom0/回避率0.03は共通計算所有者へ、spawn座標(1,1,0)/tick0/HP100維持・回避通知1件と同座標/HP100はID25へ移管 | 回避分岐はDamageをrecord_evasionへ渡さず計算が先に完結する。両所有者へ全入力と全確認を移せば失われる値渡し接続はない。手書きifだけを削除理由にしない |
| 25 [`test_record_evasion_success`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L736) | R | spawn(2,3,0)/tick0→damage20/tick1→clear後の回避通知1件、現在HP80・座標・集約識別と属性を原文のまま保持。ID24の無傷HP100/座標1行の受入は将来の移管案で、今回は未実施 | record_evasion独自の通知型/値/座標が壊れる回帰。C24のHP維持確認を移す新しい無傷行はまだ追加していない |
| 26 [`test_record_evasion_not_spawned_raises_error`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L757) | R | 未出現への回避記録はMonsterNotSpawnedException | 未出現の例外型を保護。statusとcoordinateのどちらか単独の分岐証明とは言わない |
| 27 [`test_record_evasion_dead_raises_error`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L761) | R | spawn→damage100で死亡した個体の回避はMonsterAlreadyDeadException | 死後coordinate=Noneだが未出現例外ではなく死亡例外を返す区別を守る |
| 28 [`test_update_map_placement_success`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L773) | R | ALIVEの地点1/位置0から地点2/位置(5,10,0)へ両方更新 | 配置の片方だけが更新される回帰。gatewayのmap更新とは別の集約保存契約 |
| 29 [`test_update_map_placement_not_spawned_raises_error`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L784) | R | 未出現へのupdate_map_placement(spot1,position0)はMonsterAlreadyDeadException | 未出現の既定正HPでも拒否し、HPだけの判定への置換を検出 |
| 30 [`test_update_map_placement_after_death_raises_error`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L789) | R | spawn→damage100死亡後の配置spot2/(1,1,0)をMonsterAlreadyDeadExceptionで拒否 | 死体の再配置受理/例外取り違えを検出。全状態比較は未要求 |
| 31 [`test_death_by_damage_adds_reward_event`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L800) | R | 致死100被害/tick100/attacker999でDEAD・位置消去・死亡時刻100、復活200・報酬・討伐者999・KILLED_BY_MONSTER通知 | 純粋状態のwith_deathは座標/報酬/通知を作らず代替できない。死亡調停の接続が所有契約 |
| 32 [`test_death_by_player_sets_cause_killed_by_player`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L823) | R | killer_player_id1付き致死被害はKILLED_BY_PLAYERとPlayerId1を通知 | プレイヤー討伐をモンスター討伐と誤分類する回帰 |
| 33 [`test_starve_success`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L841) | R | 正HP100でstarve(tick100)するとDEAD/STARVATION・討伐者両方None | HPゼロを要件と誤って追加する回帰、飢餓死因/討伐者の取り違え |
| 34 [`test_starve_when_not_spawned_raises`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L853) | R | 未出現starve(tick10)はMonsterNotSpawnedException | 正HP100の未出現を誤って飢餓死として扱う回帰 |
| 35 [`test_starve_when_already_dead_raises`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L858) | R | damage100/tick10死亡後starve(tick20)はMonsterAlreadyDeadException | 死亡済みを再処理する回帰、未出現例外との取り違え |
| 53 [`test_die_from_old_age_success`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1128) | F | 元のspawn0/寿命50/current50→True/DEAD/NATURALを維持。spawn37/寿命50でtick86の直前False/ALIVEとtick87の丁度True/DEAD/NATURALを同じ表へ追加 | 元は出現時刻0だけなので経過時刻を世界の絶対時刻として読む回帰を見逃す。非0の出現から寿命を測る公開契約を補強 |
| 54 [`test_die_from_old_age_returns_false_when_elapsed_under`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1161) | R | spawn0/寿命100/current50ではFalse/ALIVE | 寿命未満でも死亡する回帰。元の寿命100/半分50入力を残す |
| 55 [`test_die_from_old_age_returns_false_when_not_spawned`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1192) | R | 既定create（DEAD/出現時刻None/寿命None）でtick1000はFalse/DEAD | 未出現入力に対する公的な無操作契約を維持。出現時刻Noneガード単独の証明ではなく、別の正寿命/ALIVE無時刻入力へ勝手に置換しない |
| 56 [`test_die_from_old_age_returns_false_when_already_dead`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1198) | R | 寿命10のspawn0→damage100/tick5死亡後、tick20の自然死要求はFalse/DEAD | statusガードを外すと_dieが無操作でもTrueが返り既存assertが検出できる。原子性の追加不要 |
| 57 [`test_die_from_old_age_returns_false_when_max_age_ticks_none`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1230) | R | 寿命NoneのALIVEへtick100000でもFalse/ALIVE | 寿命未設定を有効値として処理する回帰 |
| 58 [`test_die_from_old_age_returns_false_when_max_age_ticks_zero`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1239) | R | 寿命0のALIVEへtick100000でもFalse/ALIVE | 0を即死と解釈する回帰。Noneと異なる合法設定を保持 |
| 60 [`test_respawn_too_early_raises_error`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1293) | R | spawn0→死亡100からtick150での復活はMonsterRespawnIntervalNotMetException | 待ち時間100を無視する回帰。固定兄弟の成功59に混ぜない |
| 61 [`test_respawn_not_dead_raises_error`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1300) | R | ALIVEのtick200復活はMonsterNotDeadException | should_respawnのFalseにだけ依存して別例外を出す回帰も検出 |
| 62 [`test_should_respawn_conditions`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1306) | R | 死亡tick100から150ではFalse、200丁度でTrue | 待ち時間の比較境界や死亡時刻起点を誤る回帰 |
| 63 [`test_should_respawn_no_auto_respawn`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1312) | R | 自動復活Falseでは死亡100→1000でもFalse | 十分経過していても自動復活の無効指定を守る契約 |
| 75 [`test_spawned_at_tick_before_spawn_is_none`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1512) | C | create直後spawned_at_tick=NoneをID1へ移管 | 未出現時刻は初期状態を作るcreate所有試験にまとめる |
| 76 [`test_spawned_at_tick_after_spawn_equals_current_tick`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1516) | C | spawn((0,0,0),spot1,tick42)でspawned_at_tick42をID2の新しい表行へ移管 | 既存ID2のtick0/(10,20,0)を残し、元76の非0時刻と座標0を失わない |
| 77 [`test_get_current_growth_multiplier_before_spawn_returns_one`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1558) | R | 未出現かつ成長段階ありのcurrent0/200は乗率1 | 未出現なのに幼体/成体を選ぶ回帰。getterでも独立した時刻判定契約 |
| 78 [`test_get_current_growth_multiplier_when_current_tick_before_spawned_at_returns_one`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1565) | R | spawn100より前のcurrent50/99は乗率1 | 負の経過時間で幼体を選ぶ回帰、絶対時刻と経過時刻の取り違えを検出 |
| 79 [`test_get_current_growth_multiplier_juvenile_stage`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1573) | R | spawn0のcurrent0/50/99で幼体乗率0.8 | 幼体区間や開始点を誤る回帰 |
| 80 [`test_get_current_growth_multiplier_adult_stage`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1582) | R | spawn0のcurrent100丁度/200で成体乗率1 | 境界を超過判定にしたり古い段階を使い続ける回帰 |
| 81 [`test_get_base_stats_with_growth_applies_growth_multiplier_juvenile`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1590) | R | spawn0/current50の攻撃16/防御12/速度8を保持。ID85のmaxHP80/maxMP40を同じ取得結果へ追加 | 成長乗率を能力軸の一部へ適用し忘れる回帰。純粋GrowthStageは値保持だけで計算を所有しない |
| 82 [`test_get_base_stats_with_growth_applies_growth_multiplier_adult`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1601) | R | spawn0/current150の攻撃20/防御15/速度10 | 成体でも幼体能力が残る回帰 |
| 83 [`test_get_effective_flee_threshold_and_allow_chase_default_without_flee_bias`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1611) | R | 成長段階に逃走補正未指定ならtick50で閾値0.2/追跡True | None補正と追跡既定値の適用破損 |
| 84 [`test_get_base_stats_with_growth_no_growth_stages_uses_one`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1620) | R | 成長段階なしのspawn0/current1000は攻撃/防御がテンプレート素値 | 段階がない際に不正な乗率をかける回帰。元比較先は入力テンプレートで計算値の自己比較ではない |
| 85 [`test_get_base_stats_with_growth_applies_growth_to_max_hp_mp`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1629) | C | spawn0/current50のmaxHP80/maxMP40を同条件ID81へ移管 | 同じ成長後BaseStatsを得る準備を共有して全能力軸の期待を一箇所にする |
| 86 [`test_spawn_initializes_hp_mp_with_effective_stats_juvenile`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1639) | R | 幼体0.8のspawn0でHP値/上限80、MP値/上限40 | 成長後BaseStatsが正しくてもspawnで素のHP/MPを使う回帰。reconstitute既知差異を正当化する期待は追加しない |
| 88 [`test_get_effective_flee_threshold_with_stage_flee_bias`](https://github.com/Motifman/llm-rpg/blob/464ffbc859eb273130b53f8e27820fda27e91e2a/tests/domain/monster/aggregate/test_monster_aggregate.py#L1661) | R | 逃走補正1.5/追跡Falseの幼体tick50は閾値0.3/False、成体150は0.2/True | 現在段階の行動補正読込、既定への復帰を守る。状態機械の判断とは別の所有者 |

## 履歴と呼出し元

- [集約の初期導入](https://github.com/Motifman/llm-rpg/commit/452aae918104b0b1041e0b280fd8410831eebf6d)と[計算/適用の分離](https://github.com/Motifman/llm-rpg/commit/1cf0e10b10ab80a45380695c6798dde5542c5bf5)が、公開作成・被害・回避・生死の元契約
- [配置更新入口](https://github.com/Motifman/llm-rpg/commit/ce41ebad119b1c33c60dd3d87376cea5d8dd82ee)と[群れID/役割](https://github.com/Motifman/llm-rpg/commit/5123277e703f96fee0905bc26f50a9905fa50790)の追加を保持
- [出現時刻/成長段階](https://github.com/Motifman/llm-rpg/commit/461ca51bb527fca5f63949600b303617a9553dfa)、[成長する最大HP/MPと行動補正](https://github.com/Motifman/llm-rpg/commit/9d282461f9225bb3f190025ee2267bc55f988925)、[出現・復活時の成長HP/MP初期化](https://github.com/Motifman/llm-rpg/commit/8694788913801447ca5e27437356f1adaa266bf7)を区別する
- 作成は`MonsterSpawnSlotService`が呼び、`MonsterSpawnApplicationService`は既存個体のspawnを呼ぶ。復活の初回座標はスロットの選択とSQLite保存の双方で利用される
- 被害は`HitBoxDamageHandler`と`SpotPlayerAttackService`が呼ぶ。回避は前者が呼び、後者は回避入口を呼ばない
- 配置更新は`GatewayHandler`と生存進行サービス、自然死は`MonsterLifecycleSurvivalCoordinator`が呼ぶ

## 変異と意味保持対照

旧47行と候補43行を同じ製品変異で実行した。1組の改善、12組の保持、2組の意味保持、合計15組30実行。失敗は予定した所有試験の確認式または専用例外の要求で起きた。収集/準備エラー・スキップはない。

| 変異/対照 | 旧 | 新 | 主な確認 |
|---|---|---|---|
| 寿命を絶対時刻で測る | 成功47 | 非0起点の追加行が失敗 | 現在86でFalse |
| 未出現の初回座標を位置0にする | 失敗 | 失敗 | 6→1のNone |
| 未出現の出現時刻を0にする | 失敗 | 失敗 | 75→1のNone |
| 出現時に初回位置を保存しない | 失敗 | 失敗 | 7→2の初回座標 |
| 出現時刻を常に0にする | 失敗 | 失敗 | 76→2の時刻42 |
| 復活後も以前の出現時刻を残す | 失敗 | 失敗 | 10→8の時刻200 |
| 成長最大HPだけ素値へ戻す | 失敗 | 失敗 | 85→81の80 |
| 成長最大MPだけ素値へ戻す | 失敗 | 失敗 | 85→81の40 |
| 通常被害を切り上げる | 失敗 | 失敗 | 23のHP58 |
| 二重出現を受け入れる | 失敗 | 失敗 | 3の専用例外 |
| 未出現/死亡への被害を受け入れる | 失敗 | 失敗 | 21/22の専用例外 |
| 致死被害後の死亡処理を飛ばす | 失敗 | 失敗 | 31のDEAD |
| 寿命丁度では死亡しない | 失敗 | 失敗 | 53の元0→50行 |
| 寿命計算の局所変数名だけ変更 | 成功47 | 成功43 | 表記から独立 |
| 初回座標を局所変数経由で返す | 成功47 | 成功43 | 実装形から独立 |

出現時刻や致死処理の変異は、他の試験の前提操作にも波及した。予定した所有試験の直接確認を保存証明に使い、無関係な前提操作の失敗を別の改善として計上していない。全変異後に主・原本・併用の各作業木で製品1601 Pythonファイルの基準ハッシュ一致を確認した。

## 実行結果と兄弟変更

- 未編集の全ファイル116件、関連19件、固定兄弟併用11件がそれぞれ成功
- 元宣言を残した移管段階49件、統合後43件が成功
- 最終は全ファイル112＋関連19の131件、固定兄弟併用11件が成功。重複・失敗・エラー・スキップ0
- 関連19は状態値6、出現アプリ2、復活1、生存進行1、実戦闘ハンドラ1、共通計算8。基準#1730の共通計算を使い、並行中のPlayer候補を混ぜていない
- 対象外50宣言、成功23、保留24、拡張しないR36宣言は原文と構文木が一致。共有準備も不変。元48にあった118確認式の対応を記録
- Python3.10.22/pytest8.4.1、通信禁止・資格情報除去・対象作業木のsrcを確認する安全実行器、毎回新しいキャッシュと証拠名で直列実行
- Ruff0.16.8、`git diff --check`成功。全リポジトリ試験はローカルでは実施していない

兄弟#1715の先端`6309e6aeab1e5f1274f0b347471a2a2cc46776d2`はこの差分へ含めない。基準では元の差分がそのまま適用できた。候補では削除した元10宣言がその差分の周辺行に含まれていて、そのままの適用は失敗した。対象4宣言自体は不変なので、固定兄弟の4宣言を検証済み原文のまま別作業木へ移し、それ以外88宣言の不変と元7契約11行の成功を確認した。これは周辺行の競合を解消した確認であり、無衝突だったとは記載しない。

## 残りと限界

この変更の保存確認対象は47宣言で、回避24は未解決。先行60と合わせて107宣言を扱ったことになるが、保存確認と公開先端のCIは別に完了を確認する。作業木の検査はGitHub全体試験の成功を代替しない。

既知の成長付き`spawn`と`reconstitute`の初期HP/MP差は別所見のままとし、製品修理や新しい仕様期待を追加していない。同じ時刻のENRAGE/FLEEの保留、活動中の記憶/SNSも変更しない。

先行の栄養・資源21の基準XMLを誤って上書きした証拠保全事故は別記録に残した。失われた原XMLを再構成せず、当時の独立確認と残るJSON/生ログ/段階記録、無傷の最終併用XMLで元結果を裏付ける。今回の各実行は専用の証拠名で区別し、誤って未適用状態で走った7行を兄弟併用の11行に数えていない。製品・試験・公開済み成果物の変更はこの事故に伴って生じていない。
