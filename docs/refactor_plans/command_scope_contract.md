# CommandScope・Unit of Work・イベント確定契約

## 位置づけ

この文書は #1094 / #1095 の再構築で守る規範である。
既存の `docs/what_is_uow.md` は検討過程を含む解説資料であり、実装判断が競合した場合は
この文書と `docs/design_decisions.md` を優先する。

対象は、1 回のアプリケーションコマンドで複数集約・複数リポジトリを変更し、
ドメインイベントを処理して結果を外部へ伝える経路である。問い合わせ専用処理、
シナリオ読込、migration、実験結果ファイルの生成は原則として対象外とする。

## 解決する問題

現行コードでは、次の責務が重なっている。

- `UnitOfWork` が transaction、イベント収集、同期処理位置、commit 済みイベントを持つ
- `TransactionalScope` が commit 後配送を追加で担う
- `InMemoryUnitOfWork` は遅延操作と全体 snapshot、`SqliteUnitOfWork` は即時 SQL を使う
- SQLite リポジトリは生成方法によって独自 commit の有無が変わる
- インメモリリポジトリは UoW 未注入時に即時反映し、注入時だけ操作を遅延する
- `EventPublisher` が transaction 内の登録と commit 後配送の両方を表す

この差により、同じアプリケーションサービスでも構成によって原子性が変わる。
また、永続化成功前の通知、rollback 後のイベント配送、リポジトリ単位の部分 commit、
イベントの二重回収を型だけでは防げない。

## 用語と責務

### Application Command

利用者から見て成功または失敗が一つに決まる操作である。
例は「道具を使う」「取引を承認する」「1 tick の世界処理を確定する」である。

原則として、1 Application Command に 1 `CommandScope` を対応させる。

### UnitOfWork

永続化 transaction の基盤機能である。責務は次に限定する。

- transaction の開始
- scope に参加する repository へ同じ transaction 資源を提供する
- 永続状態の commit
- 永続状態の rollback
- transaction が有効かどうかの管理

`UnitOfWork` は次を行わない。

- イベントハンドラの検索や呼出し
- 外部通知
- commit 後イベントの配送
- 用途固有の業務処理
- repository の生成方法に応じた意味の切替

SQLite では 1 connection / 1 transaction、インメモリでは同等の作業コピーまたは
変更集合を使う。実装方式は違っても、公開される原子性は同じでなければならない。

### CommandScope

アプリケーション層で 1 command の完了を統括する境界である。

- `UnitOfWork` を開始・終了する
- scope 専用 repository を提供する
- command 内で発生したドメインイベントを操作単位で集める
- transaction 内の同期イベントを収束するまで処理する
- commit 前に outbox 候補を同じ transaction へ登録する
- commit 成功後だけ配送側へ引き渡す
- 例外時の rollback と例外の保存を統括する

`CommandScope` は業務判断を持たない。どの集約をどう変更するかは application service と
domain が決める。

### DomainEventCollector

1 command の間だけ存在するイベント集合である。

- aggregate が生成したイベントを一度だけ受け取る
- 同期処理待ち、処理済み、commit 後配送候補を区別する
- rollback 時は未確定イベントをすべて破棄する
- repository に保存する集約へ未配送イベントを焼き付けない

aggregate 内のイベント queue は移行中の発生源として残せるが、repository を跨いで
持ち越す永続状態にはしない。イベントを `get_events()` と `clear_events()` の別操作で扱う
経路は、最終的に原子的な `pull_events()` 相当へ寄せる。

### SyncDomainEventDispatcher

同じ transaction 内で必要なハンドラだけを呼ぶ。

- ハンドラは現在の `CommandScope` に明示的に参加する
- ハンドラは repository を通して別 aggregate を変更できる
- ハンドラが新しいイベントを生成した場合は同じ collector へ戻す
- queue が空になるまで処理する
- 例外は command 全体を失敗させる
- ハンドラ自身は commit / rollback しない
- 外部 API、WebSocket、メール、別DBなどrollback不能な副作用を実行しない

無限連鎖を静かに継続しないよう、処理件数上限または循環検出を設け、超過時は
command を失敗させる。

### AfterCommitHandoff

commit 成功後の配送開始を表す。これは transaction の一部ではない。

- 観測、通知、別bounded contextへの連携は原則としてここから始める
- 配送失敗を理由に commit 済みの状態を rollback したことにしない
- 再試行が必要な配送は outbox を正本にする
- 配送は少なくとも一回になり得るため、受信側は event id で冪等にする

プロセス内の即時呼出しは移行中の互換手段に限る。最終形では、永続状態と outbox recordを
同じ transaction で commitし、workerが配送する。

## 正常系の確定順序

1. `CommandScope` を開始する
2. `UnitOfWork` が transaction を開始する
3. scope 専用 repository から集約を取得する
4. domain 操作を実行し、保存予定を登録する
5. aggregate のイベントを collector へ移す
6. 同期イベントを宣言順に処理する
7. ハンドラが生成した保存予定とイベントを再び取り込む
8. 同期イベントがなくなるまで 5〜7 を繰り返す
9. commit 後配送が必要なイベントを outbox 候補へ変換する
10. 永続状態と outbox record を一度の commit で確定する
11. commit 済み outbox の配送開始を通知する
12. scope を閉じる

永続化を先に確定してから同期ハンドラを呼ぶこと、同期ハンドラの途中で repository が
独自 commit すること、commit 前に外部通知することは禁止する。

## 異常系の契約

### domain操作または同期ハンドラが失敗した場合

1. 最初の例外を保持する
2. transaction が有効なら rollback を一度だけ試みる
3. collector と未確定 outbox 候補を破棄する
4. commit 後配送を開始しない
5. 元の例外を再送出する

### commit が失敗した場合

- transaction がまだ有効なら rollback を一度だけ試みる
- commit 成功として扱わない
- outbox 配送を開始しない
- commit 例外を主原因として保存する

### rollback も失敗した場合

- 最初の command / commit 例外を隠さない
- rollback 例外も属性・例外連鎖・traceで取得可能にする
- Python 3.10 でも両方を保持できる専用application例外へ包む
- 不明な状態として接続や作業コピーを再利用しない

### commit 後配送が失敗した場合

- command の永続化結果は成功済みであり、rollback しない
- outboxを未配送のまま残して再試行可能にする
- 呼出し元へ「業務失敗」ではなく「配送保留」として観測可能にする
- outbox導入前の互換経路でも、commit済み状態を失敗前へ戻したふりをしない

## repository契約

### scope参加repository

- `CommandScope` が所有する同一 transaction 資源から生成する
- `save` / `delete` の中で commit / rollback しない
- transaction 外で write を呼ぶと明示的に拒否する
- 同じ scope 内では read-your-writes を保証する
- 保存用複製から未回収イベントを除外する
- transaction の生connectionをapplication serviceへ公開しない

### 単独書込み

fixture作成、migration、管理用スクリプトなど、1 repositoryだけを明示的に確定する用途は
別の auto-commit adapter または専用commandを使う。scope参加版と同じclassをconstructor引数で
切り替えない。

### 生成境界

`for_shared_unit_of_work(connection)` のようなrepositoryごとの任意呼出しは、scope専用の
`RepositoryProvider`へ集約する。command serviceは、正しく参加したrepositoryだけを
`CommandContext`から取得する。

## 入れ子scope

暗黙の入れ子transactionは作らない。

- transaction 内同期ハンドラは現在の `CommandContext` を受け取って同じscopeへ参加する
- application serviceから別commandを直接呼ぶ場合も、同じcontextへ参加する内部APIを使う
- contextを渡さずに新しいscopeを開こうとした場合は開始前に拒否する
- commit 後ハンドラは元transaction完了後なので、新しい独立scopeを開ける
- 将来 savepoint が必要になっても、通常の入れ子commandとは別の明示APIにする

## イベントの分類

| 種類 | 実行時期 | 失敗時の扱い | 例 |
|---|---|---|---|
| Domain event | transaction内 | command全体をrollback | 別集約の必須更新 |
| Integration event | commit後 | outboxから再試行 | 別bounded contextへの通知 |
| Observation | commit後 | 観測欠損として記録・再試行方針に従う | エージェント・観戦者向け通知 |
| Trace | 各境界 | ゲーム状態を変更しない | begin / commit / rollback / delivery |

同じ `BaseDomainEvent` に同期・非同期ハンドラを混在登録する現行方式は段階移行の対象とする。
イベント型または配送 envelope に、transaction内処理かcommit後配送かを明示する。

## 状態機械

`CommandScope` は次の一方向遷移だけを許す。

```text
NEW -> ACTIVE -> COMMITTING -> COMMITTED -> CLOSED
          |           |
          +-> ROLLING_BACK <-+
                    |
                    v
               ROLLED_BACK -> CLOSED
```

- `begin`、`commit`、`rollback` は各一回だけ
- `COMMITTED` 後のrollbackは禁止
- `ROLLED_BACK` 後のcommitは禁止
- `CLOSED` 後のrepository利用は禁止
- commit後配送の成否はtransaction状態を戻さない

## 共通契約試験

同じ試験群をインメモリ実装とSQLite実装へ適用する。

1. 二つのrepository更新が同時にcommitされる
2. 二つ目の更新失敗で一つ目もrollbackされる
3. scope内で保存した値を再取得できる
4. scope外writeが拒否される
5. repositoryが独自commitしない
6. 同期ハンドラが生成した追加更新も同じcommitへ含まれる
7. 同期ハンドラ失敗で全更新と全イベントが破棄される
8. commit失敗でcommit後配送が0回になる
9. rollback失敗時に元例外とrollback例外の両方が残る
10. commit成功前にはcommit後配送が0回である
11. commit後配送失敗でも永続状態はcommit済みである
12. 同じevent idの再配送を受信側が重複適用しない
13. 暗黙の入れ子scopeが開始前に拒否される
14. 同期イベント連鎖がqueue空まで一度ずつ処理される
15. 上限を超えるイベント連鎖がrollbackされる
16. outbox recordとdomain状態が同時にcommit / rollbackされる

## 現行APIからの移行

| 現行 | 移行先 | 方針 |
|---|---|---|
| `UnitOfWork.begin/commit/rollback` | transaction port | 永続化責務だけ残す |
| `UnitOfWork.add_events*` | `DomainEventCollector` | transaction APIから分離 |
| 同期処理済み件数 | collector / dispatcher | UoWから分離 |
| commit済みイベント一時保持 | outbox / handoff | UoWから分離 |
| `TransactionalScope` | `CommandScope` | application command完了を統括 |
| `SyncEventDispatcher` | `SyncDomainEventDispatcher` | current contextを明示注入 |
| `InMemoryEventPublisherWithUow` | handler registry + handoff | 登録・同期処理・外部配送を分割 |
| repositoryの `for_shared_unit_of_work` | scoped `RepositoryProvider` | 参加漏れを生成時に防ぐ |
| repositoryの内部commit | auto-commit adapter | command経路から排除 |
| `get_events` + `clear_events` | 原子的なevent drain | 二重回収を防ぐ |

移行中は既存APIをadapterで維持するが、新規application commandは旧UoWとEventPublisherを
直接組み合わせない。

## 段階移行

1. 現行の差をcharacterization testで固定する
2. transaction port、collector、dispatcher、handoffの最小Protocolを追加する
3. インメモリとSQLiteへ共通契約試験を通す
4. scoped `RepositoryProvider`を追加する
5. 一つの縦断ユースケースを`CommandScope`へ移す
6. transaction内イベント連鎖を移す
7. outboxを追加しcommit後直送を置換する
8. bounded context単位でcommandを移す
9. 旧生成経路とrepository内部commitを削除する

最初の縦断移行は、複数inventory・world state・イベントが同時に変わるinteraction系から
選ぶ。ただし契約基盤のPRと用途移行PRは分ける。

## 完了条件

- application commandがscope外のwrite repositoryを受け取れない
- in-memory / SQLiteで共通原子性試験が全て成功する
- transaction内ハンドラがcommit / rollbackできない
- commit前の外部配送が構造的に不可能である
- rollbackしたイベントが観測・外部配送へ流れない
- repository生成方法による原子性の差がない
- outboxがdomain状態と同じtransactionで保存される
- 旧UoWイベントAPIとrepository内部commitが本番command経路からなくなる
