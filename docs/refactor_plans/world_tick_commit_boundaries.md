# world tickの確定境界と段階移行表

## 目的

`SpotGraphSimulationApplicationService` は世界時刻を一つ進め、複数のstageを
決められた順序で呼ぶ調整役である。tick全体を一つのtransactionにはしない。
利用者から一つの成功・失敗に見えるstageまたはcommandが、自分で更新対象と
成功eventを確定する。

## coordinatorの失敗規則

1. 世界時刻はstage開始前に一度だけ進める。後段が失敗しても戻さない。
2. 完了済みの前段commandは確定済みとして残す。同じtickを自動再試行しない。
3. 失敗したcommandは自分の更新と成功eventを開始前へ戻す。
4. stageが例外を返したら、依存する後段stageとpost-tick hookは実行しない。
5. commit後の観測失敗は業務状態を戻さず、配送保留または警告として扱う。
6. 呼出し側はtick失敗を観測できる。次のtickへ進むか停止するかはdriverが決める。
7. 残り時間・終了判定が参照するruntimeのtick値は、失敗経路でも時刻源へ同期する。
8. 前段commandの実験指標は、そのcommandの確定直後に記録し、tick全体の成功を待たない。

時刻を戻さないのは、前段の移動などが既に独立commitされているためである。
時刻だけ戻して再実行すると、同じtickの効果を二重適用する方が危険になる。

## stage別の境界

| 順序 | stage | 望ましい確定単位 | 同じscopeへ入れる状態 | event・callback | 移行 |
|---:|---|---|---|---|---|
| 1 | travel | playerごとの1 tick進行 | player status、graph、退場者位置 | 移動eventはcommit後。到着callbackと累積移動tickはplayer command終了後 | 済 #1242 |
| 2 | scenario event | event定義1件 | progress、flag、interior、graph、item、inventory | messageと成功eventはcommit後 | 済 #1243第3段 |
| 3 | reactive object | binding 1件 | interior、必要ならgraph event queue、確率乱数 | 状態変更eventはcommit後 | 済 #1243第6段 |
| 4 | reactive passage | stage 1回 | graph上の全対象接続、確率乱数 | passage eventはcommit後 | 済 #1243第6段 |
| 5 | synchronized action | group 1件 | prepare registry、flag、graph | messageと成功eventはcommit後 | 済 #1243第7段 |
| 6 | weather | 遷移1回 | weather state、専用乱数状態 | 天候観測はcommit後・最善努力 | 未 |
| 7 | day/night | 遷移1回 | current time-of-day | 変化観測はcommit後・最善努力 | 未 |
| 8 | needs decay | stage 1回 | 全player status | 集約eventはcommit後。evidenceの重複防止状態はstatus確定後に最善努力で更新 | 済 #1243第2段 |
| 9 | status effects | stage 1回 | 全player status | `PlayerDownedEvent`等はcommit後 | 済 #1243初段 |
| 10 | monster spawn | slot 1件 | monster、loadout、graph、slot対応、採番 | spawn/despawn eventはcommit後 | 済 #1243第4段 |
| 11 | monster behavior | monster 1体の行動 | monster、player status、graph、item等の実更新 | 攻撃・移動eventは各command確定後 | 済 #1243第5段 |
| 12 | food spoilage | stage 1回 | 対象item群 | 個別・一括観測は全保存commit後 | 未 |
| 13 | trade offer expiry | offer 1件 | trade、二者inventory予約 | 期限切れ観測はcommit後 | 未 |
| 14 | market order expiry | order 1件 | order、預り品、返却先inventory | 期限切れ観測はcommit後 | 未 |
| 15 | player outcome rule | playerとruleの1組 | outcome、progress、必要なgraph状態 | outcome通知はcommit後 | 未 |
| 16 | death grace | player 1人 | outcome、grace timer、退場状態 | outcome通知はcommit後 | 未 |

## 同期必須処理と確定後処理

- 不変条件検査、具体的な削除対象の確保、同じtransactionに必要なread model更新は
  commit前必須処理にする。失敗したらcommand全体を戻す。
- 観測pipeline、trace、LLM再起床、通知callbackは原則commit後にする。
- 後続stageが同じtickで必要とする状態はrepositoryまたは参加資源へ先にcommitする。
  後続stageは前段の確定状態を読む。
- 後続stageが必要とする「通知handlerの副作用」は、単なる観測に偽装しない。
  必須なら同期処理として明示し、そうでなければ独立commandへ分ける。

## 段階移行順

1. 状態異常: player status保存と`PlayerDownedEvent`の境界を代表実装にする。
2. needs decay: 同じproviderを再利用し、evidence更新の確定時期を分離する。済。
3. scenario event: 更新資源が最も多いため、event 1件ごとに分割する。済。
4. monster spawn / behavior: spawnはslot単位、behaviorはmonster 1体の行動単位へ
   移行済み。後続monsterの失敗で先行commandを戻さず、各commandのeventだけを
   確定後に配送する。
5. reactive / synchronized action: reactive objectはbinding単位、passageはstage単位、
   synchronized actionはgroup単位へ移行済み。各commandが追加したeventだけを確定後に
   配送する。
6. weather / day-night / spoilage / expiry / outcome: 次にweatherとday-nightから、状態と
   callbackを順次分離する。

各段階で、途中保存失敗なら状態と成功観測が残らない試験を置く。全stageの移行が
終わるまで、未移行stageの部分確定リスクはこの表で明示し続ける。
