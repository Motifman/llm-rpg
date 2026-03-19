unit of workの役割ってなんですか？

Unit of Work の役割は、**「一連の変更をひとまとまりの仕事として扱うこと」**です。

もう少し正確にいうと、

オブジェクトの変更を追跡する

どの順番でDBに反映するかを管理する

まとめて commit / rollback する

永続化の詳細をドメインロジックから隠す

ためのパターンです。

直感的なイメージ

たとえば「プレイヤーがショップでアイテムを買う」という処理を考えます。

このとき同時に、

プレイヤーの所持金を減らす

アイテムをインベントリに追加する

購入履歴を保存する

在庫を減らす

という複数の変更が起きます。

これらをバラバラに保存すると、

所持金だけ減った

でもアイテムが追加されなかった

在庫だけ減った

みたいな壊れた状態が起こりえます。

なので、

この購入処理に関する変更は全部まとめて1回の仕事として扱う
成功なら全部保存、失敗なら全部なかったことにする

という必要があります。
これを担当するのが Unit of Work です。

Repository との違い

Repository は主に

集約やエンティティを取得する

保存対象を表現する

役割です。

一方 Unit of Work は

複数 Repository にまたがる変更を束ねる

トランザクション境界を作る

commit / rollback を管理する

役割です。

つまり、

Repository = 出し入れの窓口

Unit of Work = 作業全体の管理者

と見るとわかりやすいです。

典型的な流れ

たとえば擬似コードで書くとこうです。

with uow:
    player = uow.players.get(player_id)
    shop = uow.shops.get(shop_id)
    
    player.buy(item, shop)

    uow.commit()

ここで uow は、

players repository

shops repository

DB session / transaction

をまとめて持っています。

この with uow: の中で行われた変更を追跡し、最後に commit() でまとめて保存します。途中で例外が出たら rollback します。

なぜ必要か
1. トランザクションの一貫性

複数の更新を原子的に扱えます。
全部成功か、全部失敗か、を保証しやすいです。

2. ドメイン層をDB詳細から分離

ドメインサービスやアプリケーションサービスが、毎回 SQL や session 管理を書かなくて済みます。

3. 変更の追跡を一元化

どのエンティティが新規作成・更新・削除されたかをまとめて扱えます。

4. イベント発行との相性がよい

DDD では commit 後にドメインイベントを発行したいことがあります。
Unit of Work はその境界としてちょうどよいです。

数学っぽく抽象化すると

永続化前の状態を 
𝑆
S、処理による変更を 
𝑇
T とすると、本来やりたいのは

𝑆
↦
𝑇
(
𝑆
)
S↦T(S)

という変換を、途中の半端な状態を外に見せずに一括で適用することです。

もし更新が複数あって

𝑇
=
𝑇
𝑛
∘
𝑇
𝑛
−
1
∘
⋯
∘
𝑇
1
T=T
n
	​

∘T
n−1
	​

∘⋯∘T
1
	​


なら、Unit of Work はこの合成変換を

全体として確定する

失敗したら元の 
𝑆
S に戻す

ための境界を作っています。

つまり「複数の局所操作を1つの整合的な操作として扱う仕組み」です。

ORM との関係

SQLAlchemy などの ORM には実質的に Unit of Work 的な仕組みがあります。

たとえば session は

オブジェクトの変更を追跡し

flush 時に SQL を発行し

commit / rollback を管理する

ので、内部的にはかなり Unit of Work 的です。

ただしアプリケーション設計では、ORM の session をそのまま露出させずに、

AbstractUnitOfWork

SqlAlchemyUnitOfWork

のような形で明示的に包むことが多いです。

これは設計上、

テストしやすくする

インフラ依存を隔離する

transaction boundary を明示する

ためです。

DDD で特に重要な点

DDD では「1つのユースケースの整合性」を保ちたいので、Unit of Work は

アプリケーションサービスの1回の実行

1つのコマンド処理

1つの集約更新の境界

に対応することが多いです。

たとえば

注文を作成する

スキルを発動する

モンスターをスポーンさせる

のようなユースケースごとに 1 UoW を張るイメージです。

ありがちな誤解
「Repository があれば十分では？」

不十分なことが多いです。
Repository は個別の保存窓口でしかなく、複数変更をまたぐ整合性までは面倒を見ません。

「DB トランザクションと同じ？」

かなり近いですが、完全に同一ではありません。
Unit of Work はアプリケーション側の抽象で、その内部で DB transaction を使うことが多い、という関係です。

「毎回必要？」

小さい CRUD アプリなら明示しなくても済むことがあります。
ただし、複数の更新・イベント・集約が絡むと急に価値が出ます。

一言でまとめると

Unit of Work は、

ユースケース中に起きた複数の変更を追跡し、それらを一括で永続化して整合性を守るための仕組み

です。

あなたが今考えているようなゲームやイベント駆動の文脈だと特に重要で、
「この処理のどこまでを同じトランザクションに入れるか」を表現する中心になります。

必要なら次に、
Python + SQLAlchemy での Unit of Work の最小実装例 をかなり実践的に書けます。

次に知りたいのが、ドメインイベントをaggregateのメソッド（use_skillとか）を使うたびにaggregateクラスの中にイベントが溜まります。このイベントに対して同一トランザクションで処理したい同期的なイベントハンドラや非同期的なイベントハンドラが反応します。ではこのイベントハンドラを反応させる方法を教えてください。uowがこの役割を担うわけではないですか？
思考時間: 2 ～ 3 秒

はい、その理解でかなり近いです。
**「aggregate に溜まったドメインイベントを、いつ・どう dispatch するか」**の責務は、実務上かなり多くの場合 UoW が境界を握る 形にします。

ただし、厳密には分けて考えると整理しやすいです。

Aggregate: イベントを「発生させて保持する」

Event Dispatcher / Message Bus: イベントに対応するハンドラを呼ぶ

Unit of Work: どのタイミングで dispatch するかを管理する

Transaction: DB 的に同一コミットに含めるかを決める

つまり、

UoW 自体がハンドラの本体ではないが、
**「集めたイベントを適切な dispatcher に流す起点」**になる

と考えるのがよいです。

1. まず何が起きているのか

たとえば aggregate のメソッド

player.use_skill(skill_id, target_id)

を呼ぶと、内部で状態変化が起きて、その結果として

SkillUsed

ManaConsumed

CooldownStarted

のようなイベントが player.events に積まれるとします。

イメージはこうです。

class Player:
    def __init__(self, ...):
        self.events = []

    def use_skill(self, skill_id, target_id):
        # 状態変更
        self.mp -= 10

        # イベント発生
        self.events.append(
            SkillUsed(player_id=self.id, skill_id=skill_id, target_id=target_id)
        )

重要なのは、aggregate は「イベントを発火したい」と宣言するだけで、
誰がそれを処理するかは知らないようにすることです。

これで aggregate は純粋になります。

2. どこでイベントハンドラを呼ぶのか

ここが核心です。

結論からいうと、典型的には次の2案です。

案A: UoW の commit 前に同期イベントを処理する

これは

同じトランザクションで副作用も保存したい

失敗したら全部 rollback したい

ときに使います。

流れは

aggregate のメソッドを呼ぶ

aggregate にイベントが溜まる

UoW がそのイベントを集める

同期ハンドラを呼ぶ

そこで追加の集約更新も起こる

最後にまとめて commit

です。

形式的には

𝑆
→
aggregate method
𝑆
′
S
aggregate method
	​

S
′

でイベント集合 
𝐸
E が発生し、さらに同期ハンドラによる変換を 
𝐻
H とすると、

𝑆
′
→
𝐻
(
𝐸
)
𝑆
′
′
S
′
H(E)
	​

S
′′

として、最終状態 
𝑆
′
′
S
′′
 を一回の transaction で commit します。

このとき、どこかで例外が起きれば 
𝑆
S に rollback できます。

案B: commit 後に非同期イベントを publish する

これは

メール送信

通知

別サービス連携

重い集計

後続ジョブ

など、同一トランザクションに入れたくない処理に使います。

流れは

aggregate のメソッドを呼ぶ

イベントが溜まる

同期ハンドラが必要なら commit 前に実行

DB commit 成功

その後で非同期イベントを publish

です。

これは重要で、非同期ハンドラを commit 前に実行すると危険です。
なぜなら、非同期キューに送信できたのに DB が rollback する、という不整合が起こるからです。

3. したがって UoW はどういう役割を担うか

はい、UoW はまさにこの役割を担うのに適しています。
ただし、UoW が全部やるというより、UoW が orchestration を担うと考えるのが綺麗です。

たとえば責務分担はこうです。

Aggregate

状態を変える

ドメインイベントを events に積む

Repository

aggregate を取得する

追跡対象に乗せる

Unit of Work

変更対象 aggregate を追跡する

そこからイベントを収集する

commit 前の同期 dispatch を実行する

DB commit する

commit 後の非同期 publish を実行する

Message Bus / Event Bus

イベント型ごとのハンドラを引く

ハンドラを順番に呼ぶ

4. 一番よくある設計

かなりよくあるのは次の形です。

with uow:
    player = uow.players.get(player_id)
    player.use_skill(skill_id, target_id)

    uow.commit()

そして uow.commit() の中で

tracked aggregates からイベント収集

同期ハンドラ処理

session.commit()

非同期 publish

を行います。

5. 擬似コードで全体像を書く

かなり本質的な形を書くとこうです。

class AbstractUnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.rollback()

    def commit(self):
        self._dispatch_sync_events()
        self._commit()
        self._publish_async_events()

    def rollback(self):
        self._rollback()

ただしこれだけだと、同期ハンドラの中でさらに新しいイベントが発生する場合に足りません。
なので実際は イベントをキューとして回す のが定番です。

6. 同期ハンドラでさらにイベントが出る問題

これが大事です。

たとえば

SkillUsed が発生

それを同期ハンドラが受ける

ハンドラの中で target aggregate を更新

その更新が DamageApplied を発生

さらに別の同期ハンドラが動く

という連鎖が起こりえます。

したがって、単に最初の aggregate の events を一回だけ読むのではなく、

未処理イベントがなくなるまで回す

必要があります。

数学的には、イベント処理を閉包的に回していると思えばよいです。

最初のイベント集合を 
𝐸
0
E
0
	​

 とし、ハンドラ適用で新たなイベントが生じる操作を 
Φ
Φ とすると、

𝐸
𝑘
+
1
=
Φ
(
𝐸
𝑘
)
E
k+1
	​

=Φ(E
k
	​

)

を繰り返し、最終的に新しいイベントが出なくなる不動点まで回すイメージです。

もちろん実装では無限ループ防止も考えます。

7. 実装パターン：UoW がイベントキューを drain する

たとえばこんな形です。

class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory, sync_bus, async_bus):
        self.session_factory = session_factory
        self.sync_bus = sync_bus
        self.async_bus = async_bus

    def __enter__(self):
        self.session = self.session_factory()
        self.players = PlayerRepository(self.session)
        self.monsters = MonsterRepository(self.session)
        self.seen = set()
        self._async_events_to_publish = []
        return self

    def collect_new_events(self):
        while self.seen:
            aggregate = self.seen.pop()
            while aggregate.events:
                yield aggregate.events.pop(0)

    def commit(self):
        self._dispatch_sync_events()
        self.session.commit()
        self._publish_async_events()

    def _dispatch_sync_events(self):
        queue = list(self.collect_new_events())

        while queue:
            event = queue.pop(0)

            # 同期ハンドラ実行
            new_async_events = self.sync_bus.handle(event, uow=self)
            if new_async_events:
                self._async_events_to_publish.extend(new_async_events)

            # 同期ハンドラが新たな aggregate 更新を生み、
            # そこから events が増える可能性があるので再収集
            queue.extend(list(self.collect_new_events()))

    def _publish_async_events(self):
        for event in self._async_events_to_publish:
            self.async_bus.publish(event)

    def rollback(self):
        self.session.rollback()

ここで self.seen は repository が読み込んだ aggregate を登録するための集合です。

8. Repository 側で tracked aggregate を UoW に教える

UoW がイベントを回収するには、どの aggregate が今回の作業単位に関わったかを知る必要があります。
そのため repository が取得時に UoW に登録します。

class PlayerRepository:
    def __init__(self, session, seen):
        self.session = session
        self.seen = seen

    def get(self, player_id):
        player = self.session.get(Player, player_id)
        if player is not None:
            self.seen.add(player)
        return player

    def add(self, player):
        self.session.add(player)
        self.seen.add(player)

これで UoW は今回触った aggregate からイベントを回収できます。

9. 同期ハンドラと非同期ハンドラをどう分けるか

ここはルールを明確にするのが重要です。

同期ハンドラに向くもの

同一整合性境界で必須な更新

commit 失敗なら一緒に消えてほしい処理

同じ DB transaction で処理すべき副作用

例:

SkillUsed を受けて target HP を減らす

クールダウン状態を付与する

リソース消費を記録する

同一集約群内の必須整合性更新

非同期ハンドラに向くもの

遅延可能

失敗時リトライ可能

外部システム連携

重い処理

例:

ログ集計

通知送信

analytics

別サービスへのメッセージ送信

AI エージェントへの後処理依頼

10. 一番危ない罠
罠1: commit 前に非同期 publish する

これは危険です。

順番が

queue に publish 成功

DB commit 失敗

となると、外部から見ると「起きていないイベント」が飛んでしまいます。

これを避けるためには、普通は

commit 後に publish

さらに厳密には outbox pattern を使う

です。

11. outbox pattern との関係

非同期イベントを安全に扱うには、しばしば outbox を使います。

流れは

同一 transaction の中で

ドメイン状態更新

outbox テーブルに「後で publish すべきイベント」を保存

commit

別プロセスやジョブが outbox を読んで publish

publish 成功したら outbox を完了扱いにする

こうすると

domain update
∧
outbox insert
domain update∧outbox insert

が同一 transaction に入るので、
「DB は成功したがイベントだけ失った」あるいはその逆をかなり防げます。

つまり、

同期ハンドラ: UoW 内で直接実行

非同期ハンドラ: UoW 内では outbox へ記録、実際の実行は外部 worker

という構成が最も堅いです。

12. では「UoW が反応させる」のか？

厳密に言うとこうです。

イベントに反応する主体はハンドラ

ハンドラを起動する窓口は message bus

その起動タイミングを決めるのが UoW

なので、
「UoW が反応させる」は設計上かなり自然な表現です。

ただし UoW の中にハンドラの分岐ロジックを全部埋め込むより、

uow.commit()
    -> sync_message_bus.handle(event)
    -> session.commit()
    -> async_message_bus.publish(event)

のように分けた方が見通しがいいです。

13. 実践的な最小構成

おすすめは次の構成です。

Aggregate
class AggregateRoot:
    def __init__(self):
        self.events = []
Message Bus
class MessageBus:
    def __init__(self, handlers):
        self.handlers = handlers  # {EventType: [handler, ...]}

    def handle(self, event, **kwargs):
        for handler in self.handlers.get(type(event), []):
            handler(event, **kwargs)
UoW
class UnitOfWork:
    def commit(self):
        self._dispatch_sync_events_until_empty()
        self._commit()
        self._publish_async_events()

この責務分担ならかなり扱いやすいです。

14. ゲームの use_skill だとどうなるか

たとえば player.use_skill() に対してはこんな切り分けになります。

aggregate 内

MP 減少

skill 使用可否チェック

SkillUsed イベント発行

同期ハンドラ

target へのダメージ適用

状態異常付与

クールダウン開始

コンボ状態更新

非同期ハンドラ

戦闘ログ永続化

websocket 通知

analytics 送信

replay 記録

別 shard / 別 service 連携

このとき、
「戦闘結果として必ず整合していなければいけないもの」は同期、
「遅れてもよいもの」は非同期
と分けるのが基本です。

15. 設計上の重要な注意

同期ハンドラを無制限に増やすと、実質的に「イベント経由で何でも同一 transaction に突っ込む」ことになり、見通しが悪くなります。

なので経験的には、

必須整合性だけ同期

それ以外は outbox 経由で非同期

に寄せた方が保守しやすいです。

特にゲームでは同期ハンドラが深く連鎖すると、
「use_skill しただけなのに、どこで何が起きたかわからない」
という問題が起きやすいです。

16. まとめると

あなたの問いに対する答えを一文でいうと、

aggregate に溜まったドメインイベントは、UoW が commit 境界で収集し、message bus を通して同期ハンドラを transaction 内で実行し、非同期ハンドラ向けイベントは commit 後または outbox 経由で publish する
のが典型設計です。

かなり実践的には次の順番がおすすめです。

aggregate method
→
events append
→
UoW collects
→
sync handlers
→
DB commit
→
async publish/outbox
aggregate method→events append→UoW collects→sync handlers→DB commit→async publish/outbox

必要なら次に、
Python で Aggregate + UoW + SyncBus + AsyncBus + Outbox を含んだ小さい実装例を、use_skill シナリオで具体的に書きます。

message_busはevent_publisherですか？
集約, uow, event_publisher, repository, 同期ハンドラ、非同期ハンドラ（後これは実装上どう区別する？）, 同期ハンドラが呼んだ集約がまたイベントを発行することの考慮、非同期イベントハンドラの考慮、後のoutboxパターンへの拡張を含めたそれぞれの登場人物の役割と大まかなコード、全体の組み上げについて教えてください。


はい、近いですが **完全に同じとは限りません**。
実装上は次のように分けると混乱しにくいです。

* **message bus**: 「イベントやコマンドを受け取り、対応するハンドラを呼ぶ仕組み」全般
* **event publisher**: 「イベントを外へ publish する仕組み」。特に非同期配送や外部ブローカー送信を強く含意しやすい

なので、

* **同期イベントをその場でハンドラに渡す部分**も含めて言うなら `message_bus`
* **Kafka / Redis / SQS / WebSocket などへ飛ばす部分**を特に言いたいなら `event_publisher`

として分けるのが自然です。

実務では次のように分けると綺麗です。

* `SyncMessageBus`: 同期ハンドラを呼ぶ
* `EventPublisher`: 非同期用イベントを outbox や外部メッセージ基盤へ送る
* あるいは両方まとめて広義に `message_bus` と呼ぶ

以下、登場人物の役割、最小コード、全体フローを一つの設計として整理します。

---

# 1. 全体像

あなたがほしい構成を先に図式化するとこうです。

[
\text{Application Service}
\to
\text{UoW}
\to
\text{Repository}
\to
\text{Aggregate}
]

Aggregate がイベントを溜める：

[
\text{Aggregate method}
\to
\text{state change}
\to
\text{domain events append}
]

その後 UoW がイベントを回収し、

1. **同期ハンドラ**を transaction 内で走らせる
2. そこから新しい aggregate 更新と新しいイベント発生があればさらに処理する
3. 最後に DB commit
4. **非同期イベント**は commit 後に publish、または outbox に保存

という流れです。

---

# 2. 登場人物ごとの役割

## 2.1 Aggregate

役割は

* ドメイン状態を持つ
* 不変条件を守る
* メソッド実行時にドメインイベントを `events` に積む

です。

Aggregate は、

* 誰がイベントを処理するか
* DB にどう保存するか
* 非同期配送するか

を知りません。

つまり Aggregate は

> 「こういう事実が起きた」

というイベントを宣言するだけです。

---

## 2.2 Repository

役割は

* Aggregate を取得する
* 永続化対象として session に乗せる
* UoW がイベント回収できるよう「今回触った aggregate」を追跡対象に入れる

です。

Repository はイベントを dispatch しません。

---

## 2.3 Unit of Work

役割は

* transaction の境界を持つ
* 今回触った aggregate を把握する
* aggregate に溜まったイベントを回収する
* 同期ハンドラを回す
* commit / rollback する
* 非同期イベントを outbox または publisher に渡す

です。

一番重要なのは、UoW は

> **イベントハンドラの中身を書く場所ではなく、いつ何を dispatch するかの境界を管理する場所**

だということです。

---

## 2.4 Sync Message Bus

役割は

* イベント型に応じて同期ハンドラを探す
* その場で呼ぶ

です。

これは in-process な dispatcher です。
関数呼び出しに近いです。

---

## 2.5 Async Event Publisher

役割は

* 非同期で処理したいイベントを配送可能な形にする
* outbox に書く、またはブローカーに publish する

です。

ここは「今すぐハンドラ実行」ではなく、

* 後で処理されるよう enqueue する
* 外部システムへ通知する

側です。

---

## 2.6 同期ハンドラ

役割は

* 同一 transaction 内でやるべき必須処理を行う
* 必要なら別 aggregate を取得して更新する
* その結果、新しいイベントが出てもよい

例:

* `SkillUsed` を受けて target にダメージ適用
* クールダウン開始
* resource 消費の整合的更新

---

## 2.7 非同期ハンドラ

役割は

* commit 後に遅延実行してよい処理を行う
* 外部通知や重い処理を担当する

例:

* 通知
* メール
* analytics
* 戦闘ログの二次処理
* 別サービス連携

---

# 3. 同期ハンドラと非同期ハンドラは実装上どう区別するか

ここはかなり重要です。
一番わかりやすいのは **登録先を分ける** 方法です。

たとえばイベント型ごとに

```python
SYNC_EVENT_HANDLERS = {
    SkillUsed: [apply_damage, start_cooldown],
}

ASYNC_EVENT_HANDLERS = {
    SkillUsed: [notify_clients, send_analytics],
}
```

のように分けます。

実装上の区別は色々ありますが、代表的には次の3方式です。

---

## 方式A: ハンドラレジストリを分ける

最も単純です。

```python
sync_handlers[type(event)]
async_handlers[type(event)]
```

で別々に扱います。

これはおすすめです。

---

## 方式B: イベント型を分ける

たとえば

* `DomainEvent`
* `IntegrationEvent`

を分ける方法です。

例:

* `SkillUsed` は domain event
* `SkillUsedPublished` や `BattleLogRequested` は integration event

ただし最初から厳密に分けすぎると少し重いです。

---

## 方式C: ハンドラに属性を持たせる

たとえば

```python
@sync_handler(SkillUsed)
def apply_damage(...): ...

@async_handler(SkillUsed)
def notify_clients(...): ...
```

のように decorator や metadata で区別します。

これもよいですが、内部的には結局レジストリ分離に近いです。

---

# 4. 基本方針

まずは次のルールにすると整理しやすいです。

* **同期ハンドラ**: 同一 transaction に含めたい処理
* **非同期ハンドラ**: commit 後にやればよい処理

さらに重要なのは、

* 同期ハンドラは **UoW と Repository を使って aggregate を更新してよい**
* 非同期ハンドラは **別 transaction / 別 worker で動く前提**で考える

という違いです。

---

# 5. 最小コード構成

以下は大まかな骨組みです。

---

## 5.1 イベント基底

```python
from dataclasses import dataclass


class Event:
    pass


@dataclass
class SkillUsed(Event):
    player_id: str
    target_id: str
    skill_id: str


@dataclass
class DamageApplied(Event):
    target_id: str
    amount: int


@dataclass
class ClientNotificationRequested(Event):
    topic: str
    payload: dict
```

---

## 5.2 Aggregate 基底

```python
class AggregateRoot:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def _raise_event(self, event: Event) -> None:
        self.events.append(event)
```

---

## 5.3 具体的な Aggregate

```python
class Player(AggregateRoot):
    def __init__(self, player_id: str, mp: int) -> None:
        super().__init__()
        self.id = player_id
        self.mp = mp
        self.cooldowns: set[str] = set()

    def use_skill(self, skill_id: str, target_id: str, mana_cost: int) -> None:
        if skill_id in self.cooldowns:
            raise ValueError("skill is on cooldown")
        if self.mp < mana_cost:
            raise ValueError("not enough mp")

        self.mp -= mana_cost

        self._raise_event(
            SkillUsed(
                player_id=self.id,
                target_id=target_id,
                skill_id=skill_id,
            )
        )

    def start_cooldown(self, skill_id: str) -> None:
        self.cooldowns.add(skill_id)
```

```python
class Monster(AggregateRoot):
    def __init__(self, monster_id: str, hp: int) -> None:
        super().__init__()
        self.id = monster_id
        self.hp = hp

    def apply_damage(self, amount: int) -> None:
        self.hp -= amount
        self._raise_event(DamageApplied(target_id=self.id, amount=amount))
```

---

## 5.4 Repository

Repository は aggregate を取得し、UoW の追跡対象に追加します。

```python
class PlayerRepository:
    def __init__(self, session, seen: set) -> None:
        self.session = session
        self.seen = seen

    def get(self, player_id: str) -> Player | None:
        player = self.session.get(Player, player_id)
        if player is not None:
            self.seen.add(player)
        return player

    def add(self, player: Player) -> None:
        self.session.add(player)
        self.seen.add(player)
```

```python
class MonsterRepository:
    def __init__(self, session, seen: set) -> None:
        self.session = session
        self.seen = seen

    def get(self, monster_id: str) -> Monster | None:
        monster = self.session.get(Monster, monster_id)
        if monster is not None:
            self.seen.add(monster)
        return monster

    def add(self, monster: Monster) -> None:
        self.session.add(monster)
        self.seen.add(monster)
```

---

## 5.5 SyncMessageBus

```python
class SyncMessageBus:
    def __init__(self, handlers: dict[type, list]) -> None:
        self.handlers = handlers

    def handle(self, event: Event, uow) -> None:
        for handler in self.handlers.get(type(event), []):
            handler(event, uow=uow)
```

この bus は「その場で」呼ぶだけです。

---

## 5.6 AsyncEventPublisher

最初はダミーでも十分です。

```python
class AsyncEventPublisher:
    def publish(self, event: Event) -> None:
        print(f"publish async event: {event}")
```

後でここを

* Redis Stream
* RabbitMQ
* Kafka
* SQS
* WebSocket queue

などに差し替えられます。

---

# 6. UoW の核心

ここが一番大事です。

UoW は

1. seen aggregates からイベントを集める
2. 同期ハンドラを回す
3. 同期ハンドラが新しい aggregate を触って新イベントを出したらまた集める
4. 同期処理が終わったら commit
5. 非同期イベントを outbox または publisher に渡す

を行います。

---

## 6.1 なぜ「また集める」が必要か

たとえば

* `player.use_skill()` が `SkillUsed` を発行
* 同期ハンドラ `apply_damage_handler` が `monster.apply_damage()` を呼ぶ
* `monster.apply_damage()` が `DamageApplied` を発行

という連鎖がありえます。

だから最初の `SkillUsed` だけ処理して終わりでは不十分です。

未処理イベントがなくなるまで queue を drain する必要があります。

---

## 6.2 UoW コード

```python
class UnitOfWork:
    def __init__(self, session_factory, sync_bus: SyncMessageBus, async_publisher: AsyncEventPublisher) -> None:
        self.session_factory = session_factory
        self.sync_bus = sync_bus
        self.async_publisher = async_publisher

    def __enter__(self):
        self.session = self.session_factory()
        self.seen: set = set()
        self.players = PlayerRepository(self.session, self.seen)
        self.monsters = MonsterRepository(self.session, self.seen)
        self._pending_async_events: list[Event] = []
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.rollback()
        else:
            self.rollback()  # commit 済みなら実害なしの設計でもよい
        self.session.close()

    def collect_new_events(self) -> list[Event]:
        events: list[Event] = []
        for aggregate in list(self.seen):
            while aggregate.events:
                events.append(aggregate.events.pop(0))
        return events

    def commit(self) -> None:
        self._dispatch_sync_events_until_empty()
        self.session.commit()
        self._publish_async_events()

    def rollback(self) -> None:
        self.session.rollback()

    def stage_async_event(self, event: Event) -> None:
        self._pending_async_events.append(event)

    def _dispatch_sync_events_until_empty(self) -> None:
        queue = self.collect_new_events()

        while queue:
            event = queue.pop(0)
            self.sync_bus.handle(event, uow=self)

            newly_raised = self.collect_new_events()
            queue.extend(newly_raised)

    def _publish_async_events(self) -> None:
        for event in self._pending_async_events:
            self.async_publisher.publish(event)
```

---

# 7. 同期ハンドラの例

たとえば `SkillUsed` に対して、

* モンスターへダメージ適用
* プレイヤーにクールダウン付与
* クライアント通知用イベントを async 側へ積む

をやるとします。

```python
def apply_damage_handler(event: SkillUsed, uow: UnitOfWork) -> None:
    monster = uow.monsters.get(event.target_id)
    if monster is None:
        raise ValueError("target monster not found")
    monster.apply_damage(amount=10)
```

```python
def start_cooldown_handler(event: SkillUsed, uow: UnitOfWork) -> None:
    player = uow.players.get(event.player_id)
    if player is None:
        raise ValueError("player not found")
    player.start_cooldown(event.skill_id)
```

```python
def stage_notification_handler(event: SkillUsed, uow: UnitOfWork) -> None:
    uow.stage_async_event(
        ClientNotificationRequested(
            topic="battle.skill_used",
            payload={
                "player_id": event.player_id,
                "target_id": event.target_id,
                "skill_id": event.skill_id,
            },
        )
    )
```

ここで `stage_notification_handler` は「同期ハンドラとして動いている」けれど、
実際の通知自体は transaction 内で送らず、**非同期イベントとして退避**しています。

この形はかなり実践的です。

---

# 8. 非同期ハンドラはどこで動くか

いまの最小構成では、`AsyncEventPublisher.publish()` は単にイベントを送るだけです。
その先で worker が非同期ハンドラを実行します。

たとえば別プロセスでは

```python
class AsyncMessageBus:
    def __init__(self, handlers: dict[type, list]) -> None:
        self.handlers = handlers

    def handle(self, event: Event) -> None:
        for handler in self.handlers.get(type(event), []):
            handler(event)
```

```python
def notify_clients_handler(event: ClientNotificationRequested) -> None:
    print("notify websocket clients", event.topic, event.payload)
```

つまり非同期側では

* publisher がイベントをキューへ入れる
* worker が取り出す
* async handler を実行する

という構成です。

---

# 9. 組み上げ例

```python
sync_handlers = {
    SkillUsed: [
        apply_damage_handler,
        start_cooldown_handler,
        stage_notification_handler,
    ],
}

sync_bus = SyncMessageBus(sync_handlers)
async_publisher = AsyncEventPublisher()

uow = UnitOfWork(
    session_factory=session_factory,
    sync_bus=sync_bus,
    async_publisher=async_publisher,
)
```

アプリケーションサービスはこうなります。

```python
def use_skill(player_id: str, target_id: str, skill_id: str, mana_cost: int, uow: UnitOfWork) -> None:
    with uow:
        player = uow.players.get(player_id)
        if player is None:
            raise ValueError("player not found")

        player.use_skill(skill_id=skill_id, target_id=target_id, mana_cost=mana_cost)
        uow.commit()
```

---

# 10. ここまでの実行フロー

この `use_skill()` を実行すると、

1. `player.use_skill()` が state change
2. `SkillUsed` が `player.events` に入る
3. `uow.commit()` が `SkillUsed` を回収
4. `apply_damage_handler` が monster を更新
5. `monster.apply_damage()` が `DamageApplied` を発行
6. `start_cooldown_handler` が player を更新
7. `stage_notification_handler` が `ClientNotificationRequested` を `_pending_async_events` に積む
8. UoW が `DamageApplied` など新イベントもまた回収
9. 全同期処理が終わったら `session.commit()`
10. commit 成功後、`ClientNotificationRequested` を publish

となります。

---

# 11. ここで見えてくる重要な原則

## 11.1 同期ハンドラの中で外部送信しない

たとえば同期ハンドラの中で WebSocket 通知や Kafka publish を直接やると、

* 通知は成功
* でも DB commit が失敗

という不整合が起きえます。

なので同期ハンドラでは

* 非同期イベントを stage する
* outbox に積む

までに留めるのが基本です。

---

## 11.2 非同期イベントは commit 後に送る

これは transaction の整合性のためです。

---

## 11.3 同期ハンドラが aggregate を更新して新イベントを出すのは OK

ただし UoW が queue drain できる設計にしておく必要があります。

---

# 12. outbox への拡張

ここからが将来拡張です。

最初は `AsyncEventPublisher.publish()` を commit 後に直接呼んでもよいですが、
堅牢性を上げるには outbox パターンへ進みます。

---

## 12.1 outbox の考え方

同一 transaction の中で

* ドメイン状態の更新
* outbox テーブルへのイベント保存

を一緒に commit します。

つまり、

[
\text{domain update} + \text{outbox insert}
]

を原子的に行います。

これで

* DB だけ更新されてイベント喪失
* イベント送信だけされて DB rollback

の問題を避けやすくなります。

---

## 12.2 outbox 用レコード

```python
from dataclasses import dataclass
import json
import uuid


@dataclass
class OutboxMessage:
    id: str
    event_type: str
    payload: str
    processed: bool = False

    @classmethod
    def from_event(cls, event: Event) -> "OutboxMessage":
        return cls(
            id=str(uuid.uuid4()),
            event_type=type(event).__name__,
            payload=json.dumps(event.__dict__),
            processed=False,
        )
```

---

## 12.3 UoW の変更

`_publish_async_events()` を直接呼ぶ代わりに、commit 前に outbox へ保存します。

```python
class UnitOfWork:
    # 途中は同じ

    def commit(self) -> None:
        self._dispatch_sync_events_until_empty()
        self._store_outbox_messages()
        self.session.commit()

    def _store_outbox_messages(self) -> None:
        for event in self._pending_async_events:
            msg = OutboxMessage.from_event(event)
            self.session.add(msg)
```

この形だと commit 後の publish は別 worker の責務になります。

---

## 12.4 outbox worker

```python
def publish_outbox_messages(session, publisher: AsyncEventPublisher) -> None:
    messages = session.query(OutboxMessage).filter_by(processed=False).all()

    for msg in messages:
        event = deserialize_event(msg.event_type, msg.payload)
        publisher.publish(event)
        msg.processed = True

    session.commit()
```

これにより、非同期配送は再試行可能になります。

---

# 13. message_bus と event_publisher の整理をもう一度

ここまでの構成を言葉で固定すると、

## message bus

「イベントを受けて対応する handler を呼ぶ仕組み」

* in-process の同期 dispatch に使う
* worker 内で非同期 handler を呼ぶときにも使える

## event publisher

「イベントをどこかへ送る仕組み」

* Kafka へ publish
* Redis Stream へ enqueue
* outbox から配送
* WebSocket 配信依頼を送る

なので、

* **bus は dispatch**
* **publisher は transport / delivery**

と考えると整理しやすいです。

---

# 14. 実践でおすすめの責務分離

かなりおすすめなのは次です。

### Aggregate

イベントを発生させる

### Repository

取得・追加・追跡

### UoW

transaction 境界、イベント回収、同期 dispatch、非同期イベント staging

### SyncMessageBus

同期 handler を呼ぶ

### AsyncEventPublisher

非同期イベントを outbox または broker へ渡す

### Async Worker

非同期イベントを受けて handler 実行

この分け方だと、最初は小さく始めて、あとから outbox に育てやすいです。

---

# 15. 最小から段階的に育てる順番

おすすめ順はこうです。

### 段階1

* aggregate が `events` を持つ
* UoW が同期イベントを drain する
* 非同期はまだ考えない

### 段階2

* `uow.stage_async_event()` を導入
* commit 後に直接 publisher する

### 段階3

* publisher 直送をやめて outbox 保存にする
* worker が outbox を読む

### 段階4

* 必要なら integration event と domain event を分ける

この順番だと無理がありません。

---

# 16. 注意点

## 無限イベント連鎖

A の handler が B を起こし、B の handler がまた A を起こす、というループに注意です。
設計で閉路を避けるか、ガードを入れます。

## 同期ハンドラ肥大化

同期ハンドラが増えすぎると「use_skill 一発で何が起こるかわからない」状態になります。
必須整合性だけを同期に寄せるのが基本です。

## 非同期処理の冪等性

outbox や再試行を使うと、同じイベントが複数回処理される可能性があります。
非同期 handler は冪等に寄せるのが安全です。

---

# 17. 一文でまとめると

あなたの構成は次の理解で組み上げると綺麗です。

> Aggregate がイベントを溜め、Repository が触った aggregate を UoW に見せ、UoW が未処理イベントを回収して SyncMessageBus で同期ハンドラを transaction 内で走らせ、非同期向けのイベントは staging して commit 後に publisher へ渡し、将来的にはその publish を outbox に置き換える。

---

# 18. かなり短い骨格だけ最後に再掲

```python
player.use_skill(...)
# -> player.events に SkillUsed

uow.commit()
# -> collect events
# -> sync_bus.handle(SkillUsed)
# -> handler が monster.apply_damage()
# -> monster.events に DamageApplied
# -> collect again
# -> queue empty まで続ける
# -> async events を outbox or publisher へ
# -> db commit
```