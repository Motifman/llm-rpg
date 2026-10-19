# モンスターの反応・探索を公開状態で検査する

## なぜ

死亡時の探索開始試験は、死んでからCHASEを要求していたためIDLEのままだった。死亡ガードを消しても非CHASEガードで止まり、死亡拒否が壊れたことを検出できなかった。非正の探索期間や非CHASE時の減算も、元のtimerが0のため別のガードに隠れていた。追跡情報の取得では、返してはいけない情報を準備していない否定があった。

この変更は、その条件を独立に満たす入力と拒否前後の公開状態で検査する。同じ集約操作を繰り返していた5宣言を既存主試験へまとめる。製品仕様は変えない。

## 範囲と計数

- 基準main: `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`
- 対象は `test_monster_aggregate_chase_search.py` と `test_monster_aggregate_reaction_state.py` の元29宣言
- 読取判定: R14 / F10 / C5 / D0。Rは保持、Fは契約を保って検査を修理、Cは主試験へ統合
- 元29宣言から24宣言へ統合。入力表を展開した実行件数は29件から37件
- 行動関係の別52宣言（判断・状態機械）と別37宣言（値オブジェクト）はこの変更の完了数に含めない
- Coreの継承による重複収集、攻撃待ち時間・環境被害の監査、再構成時の成長HP/MP差は対象外
- 製品コードの変更・削除、試験専用の製品入口追加は0

## 変えた検査

- 生存CHASEを公開操作で作り、致死ダメージを与えたDEAD_CHASEで探索開始を拒む。元のDEAD_IDLEも残す
- 死亡拒否の比較開始は死亡直後・拒否要求直前。死亡自体が消す追跡情報を、拒否の副作用と混同しない
- timer3に0/-1の探索期間を渡して値が消えないことを確認。元のtimer0行も残す
- 永続化層が使う `MonsterBehaviorState.from_parts` で非CHASEかつ正timerを準備し、減算しないことを確認
- 公開CHASE→FLEEで内部に残る観測spotを用意し、追跡用の取得ではNoneとなることを確認
- IDLEで被弾相手を記録しても追跡相手はNone。第三者からの被弾では新しいref/tickを正確に更新し、追跡相手・開始tick・spotは維持
- 0/-1の逃走期間では既存状態を維持。死亡時の変更拒否では比較対象の状態と未配信イベントを維持
- 私有ライフサイクル値の差し替えをやめ、既存の公開死亡操作を使用。探索timerも既存の公開プロパティで読む

## 統合した宣言と保持先

対象ファイルはともに `tests/domain/monster/aggregate/` 配下。ファイル丸ごとの削除はない。

- `TestIsSearchingLostTarget.test_idle_false` → `TestStartChaseSearch.test_chase_state_op`
- `TestIsSearchingLostTarget.test_chase_search_timer_two_true` → `TestTickChaseSearchTimer.test_returns_timer_two_true` の減算前。開始timer3の正の対照も残す
- `TestResetSearchTimerOnRediscovery.test_op` → `test_timer_zero_chase` の二度目のリセット
- `TestChaseLastObservedProperty.test_returns_chase_state_value` → 再発見主試験と `TestChaseState.test_enter_chase_state_chase_attacker_ref`
- `TestChaseLastObservedProperty.test_chase_clear_none` → `TestClearBehaviorState.test_chase_idle`

保持先に元の検査を先に移してから元宣言を除いた。handlerの実グラフ移動・再発見・保存接続、SQLiteの保存と復元後の挙動は独立契約として残す。アプリ側の第三者被弾試験にも同じ集約APIの完全一致検査があるため、この契約を新規追加とは扱わない。

## 検査が主張しないこと

- `test_timer_zero_false` はFalseという戻り値を守る。減算後のtimer値そのものは確認していない
- `test_flee_idle` はIDLEへの状態解除を守る。生の逃走期限値の消去を証明しない。SQLiteのCHASE解除試験も期限が元からNoneなので、その代わりの証明とは扱わない
- 非CHASEかつ正timerの入力は復元入口で扱える値を使う。新たな生成経路や製品上の状態遷移は追加しない

## 責務と履歴

`record_attacked_by_in_spot` の直接呼出元は `SpotAttackOrchestrator`。反応・群れhandlerは記録された情報を読み、公開FLEE/CHASE APIを使う。探索APIの呼出元は `MonsterReactionHandler`。

- [反応の初導入](https://github.com/Motifman/llm-rpg/commit/92f1c589f2b79b89475e334b68139b434e47fe1f)
- [追跡相手を最後の被弾者から分離した修理](https://github.com/Motifman/llm-rpg/commit/c6e1eae17d42faf96c3b56797981577082fe8948)
- [探索APIと再発見時の保存を整えた修理](https://github.com/Motifman/llm-rpg/commit/0d355a7fa71e51d0f4e7c2a5ff98969a675e2b7b)
- [追跡開始時刻による上限の導入](https://github.com/Motifman/llm-rpg/commit/913dfab40a8432db919a2d37f671a323566004f5)

## 元29宣言の判定

| ファイル | 元宣言 | 判定 | 意図 |
|---|---|---|---|
| chase_search | `TestStartChaseSearch::test_chase_timer` | R | CHASEで探索開始し指定timer3と探索中判定を公開入口で守る。開始処理欠落・timer値違いを検出 |
| chase_search | `TestStartChaseSearch::test_chase_state_op` | R | IDLEで開始してもtimerを作らない。CHASEガード除去を検出する。私有読取は既存公開behavior_search_timerへ置換候補 |
| chase_search | `TestStartChaseSearch::test_dead_state_op` | F | DEADにしてからenter_chaseを呼ぶためIDLEのまま。死亡ガードを消してもCHASEガードで止まり偽陰性。生存CHASE→致死damageのDEAD_CHASEと従来DEAD_IDLEを両方保持し拒否前後を比較 |
| chase_search | `TestStartChaseSearch::test_search_ticks_zero_less_op` | F | 0/-1でtimerが0のまましか見ず、既存timerを0へ消す誤動作を見逃す。開始済timer3を各行に用い指定拒否後も3を保持 |
| chase_search | `TestIsSearchingLostTarget::test_idle_false` | C | IDLEの探索中Falseは開始拒否試験104で同じ値を検査済み。独立する副作用・境界はない |
| chase_search | `TestIsSearchingLostTarget::test_chase_search_timer_zero_false` | R | CHASEでもtimer0では探索中でない。状態だけでTrueにする退行を捕捉 |
| chase_search | `TestIsSearchingLostTarget::test_chase_search_timer_two_true` | C | CHASEかつtimer正でTrueは96の開始結果と同じ契約。timer2固有の境界は154で残る |
| chase_search | `TestTickChaseSearchTimer::test_returns_timer_two_true` | R | timer2から1へ減りTrue。未減算/2減算/早期Falseを検出。生存検索継続の主試験 |
| chase_search | `TestTickChaseSearchTimer::test_returns_timer_one_false` | R | timer1から0へ減りFalse。満了の1tick遅延を捕捉 |
| chase_search | `TestTickChaseSearchTimer::test_timer_zero_false` | R | CHASEかつtimer0でFalseを返す。常時Trueを捕捉する戻り値契約。減算後timer自体は未検査 |
| chase_search | `TestTickChaseSearchTimer::test_chase_false` | F | IDLEとtimer0を同時に使いCHASEガード消失を検出できない。実際の復元入口が受け取るMonsterBehaviorState.from_partsで非CHASE・非ゼロtimerを用いFalseかつtimer不変を検査 |
| chase_search | `TestResetSearchTimerOnRediscovery::test_timer_zero_chase` | R | 再発見でtimer0、CHASE継続、追跡相手と最終spotの保持。timerのみの更新が他状態を消す退行を捕捉 |
| chase_search | `TestResetSearchTimerOnRediscovery::test_op` | C | timer0再リセットは189へ二度目の呼出しとして統合し公開状態の同値を比較。単なる内部再割当禁止は要求しない |
| chase_search | `TestChaseLastObservedProperty::test_returns_chase_state_value` | C | 追跡spotを返す確認は189が再発見後も同じspotで検査。通常開始のspot確認はreaction145へも明示してから統合 |
| chase_search | `TestChaseLastObservedProperty::test_idle_none` | F | IDLEで入力spot自体もNoneのため状態ガード除去を見逃す。公開CHASE→FLEEはspotを内部保持するので、その非CHASE状態でgetterがNoneとなる対照を元IDLE行と併せて検査 |
| chase_search | `TestChaseLastObservedProperty::test_chase_clear_none` | C | CHASE解除後spot=Noneをreaction197へ移し、同じ解除操作の相手/状態/spotを一つの主試験で検査 |
| reaction_state | `TestLastAttackerRef::test_attacker_ref_unspecified_none` | R | 攻撃者省略でも被弾tick5を更新しrefNoneを維持。tick記録欠落を捕捉 |
| reaction_state | `TestLastAttackerRef::test_preserves_player_ref` | R | player攻撃者の型つき参照を保持。playerをmonsterと混同/破棄する退行を捕捉 |
| reaction_state | `TestLastAttackerRef::test_preserves_monster_ref` | R | monster攻撃者の型つき参照を保持。playerのみ記録する退行を捕捉 |
| reaction_state | `TestLastAttackerRef::test_dead_state_op_3` | F | 死亡記録拒否は現在ref/tick=Noneのみ。公開致死操作で正当な死亡状態を作り、既存ref/tickがある場合も上書きされずイベントも不変を検査 |
| reaction_state | `TestFleeState::test_enter_flee_state_flee_true` | R | FLEE開始tick10、期限13でTrue、14でFalse。期限を>=ではなく>で切る1tick境界と開始時刻を守る |
| reaction_state | `TestFleeState::test_duration_ticks_zero_less` | F | 説明は0以下だが0一行しかなく不等号境界が未検査。0/-1各行と既存CHASEの不変性を確認し、全体を別状態へ初期化する誤動作も捕捉 |
| reaction_state | `TestFleeState::test_dead_state_op_2` | F | 死亡後FLEEでないだけでは別状態への誤変更を見逃す。公開死亡後の状態/残存timer/被弾情報/イベントの同値で拒否を検証 |
| reaction_state | `TestChaseState::test_enter_chase_state_chase_attacker_ref` | R | CHASE開始後の追跡判定とattacker_ref。開始時刻/spotは同時更新の公的状態として統合候補、SQLite復元とchase_limitsも別の保存/期限契約を保持 |
| reaction_state | `TestChaseState::test_chase_attacker_ref_none` | F | 現在はIDLEで被弾情報もNoneなのでlast_attacker_refを誤って返しても通る。被弾refを記録したIDLEを使い、追跡対象はNoneで被弾者と区別されることを検査 |
| reaction_state | `TestChaseState::test_chase_attacker_ref_last_attacker_ref` | F | 第三者被弾で追跡対象は維持されるがlast_attacker_ref!=originalだけではNone等を許す。第三者refとの完全一致、tick20、開始tick10/spot不変を比較 |
| reaction_state | `TestChaseState::test_dead_state_op` | F | 死亡後is_chasing=Falseのみ。既存FLEE等をIDLEへ壊す誤動作を見逃す。公開死亡と新しい追跡相手による拒否を用い比較対象の行動・追跡・被弾状態と未配信イベントが不変を比較 |
| reaction_state | `TestClearBehaviorState::test_flee_idle` | R | FLEE解除でIDLEかつis_fleeing=Falseという状態解除の独立契約。生の期限値が消えることはこの試験でもSQLiteのCHASE解除試験でも未証明 |
| reaction_state | `TestClearBehaviorState::test_chase_idle` | R | CHASE解除でIDLEかつ相手None。探索側224のspotNone、開始tickNoneとtimer0を引き継ぐ主試験 |

## 試験

- 未編集の第一範囲29件成功。行動全体118件の未編集結果とは分けて計上する
- 変更後の第一範囲は37件成功。パラメータ展開前は24宣言
- 復元後、第一範囲37件と関連59件を同じ実行で検査し、**96件成功**。nodeid重複0
- Python3.10.22 / pytest8.4.1。資格情報を除去しネットワークを遮断した環境で、当該作業ツリーのsrcを明示して実行
- 変異は独立作業ツリーで1件ずつ実施。旧新それぞれ別のPythonキャッシュを使う
- 製品1601個の.pyファイルを変異前後のSHA256で比較し、全件一致。元・候補の製品差分0
- ruff0.16.8、git diff --check成功。全試験と公開コミットのCIはこのローカル検証に含まない
- 試験2ファイルは437→483行（+46）。製品0行、監査文書は別計上。削除量を増やすために拒否や境界の確認を削らない

関連59件は次の6ファイル。対象2ファイルは通常のpytest対象で、CIではPython3.10とlocked依存の全体試験に含まれる。試験選択設定の変更は不要。

- tests/application/monster/test_monster_reaction_handler_search_phase.py
- tests/application/monster/test_monster_reaction_handler.py
- tests/application/monster/test_monster_reaction_handler_chase_limits.py
- tests/application/monster/test_spot_monster_behavior_tick_react_to_attack.py
- tests/infrastructure/repository/test_sqlite_monster_aggregate_repository.py
- tests/infrastructure/repository/test_sqlite_monster_state_codec_compat.py

## 検出力と保存の対照

以下は本変更の元2ファイル29件と候補2ファイル37件を比べた結果。13件の変異は元の29件を通り候補で失敗した。リポジトリ全体がこれらを見逃していた、という意味ではない。特に第三者refの完全一致は関連アプリ試験に既存の検査がある。

C5の保存確認5件は元試験でも失敗するので、新しい検出力には数えない。すべて失敗したassertの位置を確認し、構築エラーや無関係なガードによる失敗ではないことを照合した。

| 変異 | 元29件 | 候補37件 | 失敗した契約 |
|---|---|---|---|
| 01_start_dead_guard | 29成功 | 36成功/1失敗 | 死亡CHASEで探索timerを書き換えない |
| 02_start_nonpositive_guard | 29成功 | 35成功/2失敗 | 既存timerを0/-1で消去しない |
| 03_tick_chase_guard | 29成功 | 36成功/1失敗 | 非CHASEの正timerを減らさない |
| 04_spot_getter_guard | 29成功 | 36成功/1失敗 | 非CHASEの残存spotを追跡用に公開しない |
| 05_idle_attacker_confusion | 29成功 | 36成功/1失敗 | IDLE被弾者を追跡相手と混同しない |
| 06_negative_flee_duration | 29成功 | 35成功/2失敗 | 負の逃走期間は拒否する |
| 07_dead_record_events | 29成功 | 35成功/2失敗 | 死亡後被弾記録拒否でイベントを消さない |
| 08_dead_flee_events | 29成功 | 35成功/2失敗 | 死亡後FLEE拒否でイベントを消さない |
| 09_dead_chase_events | 29成功 | 35成功/2失敗 | 死亡後CHASE拒否でイベントを消さない |
| 10_third_party_ref_none | 29成功 | 36成功/1失敗 | 第三者の被弾者を正確に更新する |
| 11_dead_record_clears_history | 29成功 | 36成功/1失敗 | 死亡後に以前の被弾情報を消さない |
| 12_dead_flee_clears_state | 29成功 | 36成功/1失敗 | 死亡後FLEE拒否で残存CHASE状態を消さない |
| 13_dead_chase_clears_state | 29成功 | 36成功/1失敗 | 死亡後CHASE拒否で残存FLEE状態を消さない |
| 14_keeper_idle_predicate | 27成功/2失敗 | 36成功/1失敗 | C132:IDLEの探索判定False |
| 15_keeper_positive_predicate | 26成功/3失敗 | 34成功/3失敗 | C143:正の探索timer判定True |
| 16_keeper_zero_reset | 28成功/1失敗 | 36成功/1失敗 | C201:timer0の再リセットは不変 |
| 17_keeper_chase_spot | 27成功/2失敗 | 34成功/3失敗 | C213:CHASEの最終観測spotを保持 |
| 18_keeper_cleared_spot | 27成功/2失敗 | 34成功/3失敗 | C224:IDLE解除後の観測spotはNone |

## 別件として残した観測候補

2Dの状態機械で同tickにENRAGEと脅威FLEEが適用されると、最終状態はFLEEだが観測文はENRAGEになる場合を、公開集約とformatterで再現した。配信全体や期待仕様の最終判断は未確認。この2試験の修理とは責務が違うため、製品修理・期待値の固定・Issue作成は含めない。
