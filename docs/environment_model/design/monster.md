# モンスター

モンスターは、世界の中で決まった手順で動く生き物。エージェントの外側が動かす人と違い、時間が進むたびに世界が動かす。動きはスポットグラフの場所・通路・通路の時間・音の届き方の上に乗り、人と同じ決まり (閉じた扉は通れない、暗いと見えにくい) に従う (#1971)。

ここに書くのは第 1 段。群れ (第 2 段) と生態系 (第 3 段) は、末尾の「この先」に置く。

## 種類と湧き (宣言)

```python
@final
@dataclass(frozen=True)
class MonsterSpecDeclaration:               # モンスターの種類。品物の種類と同じく、個体は世界の中で生まれる
    monster_spec_id: MonsterSpecId
    name: DisplayName                       # 坑道の獣
    description: DescriptionText
    max_hp: HitPoints
    attack: MonsterAttack
    senses: MonsterSenses
    temperament: Temperament
    flees_below: HpRatio | NeverFlees       # HP がこの割合より下がったら、気性に関わらず逃げる
    gives_up_after: Ticks                   # 調べに行く・探すを、この時間でやめてねぐらへ帰る
    wander_chance: Probability              # 休んでいるとき、1 tick に縄張りの隣の場所へ歩き出す確率
    drops: tuple[MonsterDrop, ...]          # 死んだ場所の地面に落とす物

@final
@dataclass(frozen=True)
class MonsterAttack:
    damage: Damage
    every: Ticks                            # 何 tick ごとに襲えるか。1 以上

@final
@dataclass(frozen=True)
class MonsterSenses:
    sees_in_dark: bool                      # 明るさを 1 段上げて見る (真っ暗は暗い、暗いは薄暗いとして見る)
    hears_from: SoundLevel                  # この大きさ以上で届いた音を聞き取る

Temperament = Hostile | Territorial | Retaliating | Timid
# Hostile: 見た人を追って襲う (坑道の獣、野犬)
# Territorial: 縄張りの中にいる人だけを襲う。縄張りの外へ出た人は追わない (大型カニ)
# Retaliating: 攻撃した人だけを追って襲う
# Timid: 人を見たら逃げる

@final
@dataclass(frozen=True)
class MonsterDrop:
    item_spec: ItemSpecId
    count: Count
    chance: Probability                     # 書かなければ 1 (必ず落とす)

@final
@dataclass(frozen=True)
class MonsterSpawnDeclaration:              # どこに何匹いるか。ねぐらと縄張りは種類ではなくここに書く (同じ種類でも湧く場所ごとに違う)
    spawn_id: MonsterSpawnId
    spec: MonsterSpecId
    count: Count                            # 1 以上
    home: SpotId                            # ねぐら。休む場所で、あきらめたら帰る場所
    territory: tuple[SpotId, ...]           # 歩き回る範囲。home を含む

# 条件と知覚の文は動詞の側に置く (名詞は互いを ID で指すだけ。#2075 の物の見え方と同じ)

@final
@dataclass(frozen=True)
class MonsterPresenceDeclaration:           # 湧きが世界にいる条件。design.presence_of(spawn) で引き、書かなければ AlwaysPresent
    spawn: MonsterSpawnId
    present_while: Condition | AlwaysPresent

@final
@dataclass(frozen=True)
class MonsterPerceptionsDeclaration:        # 種類ごとの知覚の文の書き換え。design.monster_perceptions_of(spec) で引き、書かなければ世界の既定 (monster_perceptions)
    spec: MonsterSpecId
    perceptions: MonsterPerceptions

@final
@dataclass(frozen=True)
class MonsterPerceptions:                   # モンスターのしたことが周りにどう知覚されるか
    appeared: PerceptionDeclaration         # 現れた ({origin})
    left: PerceptionDeclaration             # 去った ({destination})
    attacked: PerceptionDeclaration         # 襲った ({target} は襲われた人。本人には target の文)
    fled: PerceptionDeclaration
    died: PerceptionDeclaration
```

- YAML では、`present_while` は `monster_spawns.<名前>` の下に、種類ごとの `perceptions` は `monster_kinds.<名前>` の下に書く。読み込みが動詞として取り出す (`looks:` と同じ)
- `present_while` が真になったら、HP が満たされた個体が `count` だけ `home` に湧く。偽になったら、死骸も含めて世界から外れる。書かなければ (`AlwaysPresent`) 世界の始まりからいて、死んだら死骸が残る。時間で湧き直す仕組みは持たない
- `present_while` は、時間が進むとき (`PassWorldTime`) だけ確かめる。行為が確定するたびに確かめると、湧くか消えるかが行為の数に左右されるため (#1978 の D2 と同じ考え)。きっかけは `WorldTimePassing`。真偽が変わったときだけ湧かせ・外す (反応と同じ数え方)。世界の始まりに真なら、`OpenWorld` が湧かせる
- `present_while` の条件は、物の見え方と同じく世界の状態だけで決まるものに限る。きっかけから人を引く主語・`chance`・引数を読めば `DesignFlaw`
- `home` が `territory` に無い、`territory` が空、`territory` の場所が宣言に無い、は `DesignFlaw`
- 落とす物の `chance` は、死んだときに 1 つずつ `facts.random()` から引く
- 落とす物の品物の種類・湧きの種類が宣言に無ければ `DesignFlaw`

## 個体 (集約)

```python
class Monster:                                    # 個体ごと。MonsterId は湧いたときに世界が決める
    @classmethod
    def spawn(cls, monster_id: MonsterId, spawn: MonsterSpawnDeclaration, spec: MonsterSpecDeclaration, number: MonsterNumber, now: WorldTick) -> "Monster": ...
        # MonsterSpawnedEvent。number は同じ種類の中で湧いた順の番号で、ずっと変わらない (野犬 (2))

    def take_damage(self, amount: Damage, by: PersonId, now: WorldTick) -> None: ...
        # MonsterDamagedEvent、0 になれば MonsterDiedEvent(monster, spec, spawn, killed_by, at)
        # 攻撃した人を覚える。Hostile と Retaliating は追う、HP が flees_below を下回れば逃げる
    def sense(self, senses: SensedThisTick, now: WorldTick) -> None: ...
        # 見たもの・聞いたものから、覚えていることと状態を書き換える (MonsterStateChangedEvent)
    def leave_world(self) -> None: ...

    def next_move(self, facts: WorldFacts, here: SpotId) -> MonsterMove: ...   # 問い合わせ。状態と覚えていることから、この tick にすることを返す
    def health(self) -> HpRatio: ...
    def is_dead(self) -> bool: ...
    def state(self) -> MonsterState: ...

MonsterState = Resting | Wandering | Investigating | Chasing | Searching | Returning | Fleeing
# Resting: ねぐらで休む / Wandering: 縄張りを歩く / Investigating(spot, since): 音のした場所へ向かう
# Chasing(prey: PersonId): 獲物を追う / Searching(last_known, since): 見失った場所のまわりを探す
# Returning: ねぐらへ帰る / Fleeing(from_person: PersonId | NoOne): 逃げる

@final
@dataclass(frozen=True)
class LastKnownPlace:                             # 最後に獲物を見た・聞いた場所 (LKP)
    person: PersonId
    spot: SpotId
    at: WorldTick
    left_by: PassageId | NotSeenLeaving           # 出ていくところを見ていれば、その通路

MonsterMove = MoveAlong | AttackPerson | StayPut
# MoveAlong(route: Route) / AttackPerson(person: PersonId) / StayPut()

@final
@dataclass(frozen=True)
class SensedThisTick:
    seen_people: tuple[SeenByMonster, ...]        # 同じ場所にいて、見えた人。立っているか倒れているかも持つ
    heard: tuple[HeardSound, ...]                 # 前の tick のあいだに鳴り、hears_from 以上で届いた音
    left_here: tuple[PersonLeaving, ...]          # 見ているあいだに出ていった人と、その通路
```

## 1 tick の流れ

`PassWorldTime` の最後 (時計 → 移動 → 体 → 品物の時間 → 天候 → モンスター) で、次を順に行う。

1. **湧きを確かめる**: `present_while` の真偽が変わった湧きについて、個体を湧かせるか外す
2. **個体ごとに (湧いた順に) 感じて動く**。移動の途中の個体は、着くまで決め直さない (人の「行っているあいだ」と同じ)
   1. 感じる: 同じ場所の人を、`LightingConditions` と夜目で見る。音は `SoundsThisTick` から、自分の場所に `hears_from` 以上で届いたものを聞く。見ていた人が出ていった通路も見る
   2. 覚える: `Monster.sense` が、最後に獲物を見た場所と状態を書き換える
   3. 決める: `Monster.next_move` が、することを 1 つ返す
   4. 動く: `MoveAlong` は `Whereabouts.start_travel`、`AttackPerson` は `PersonVitals.take_damage(damage, now, StruckByMonster(monster))`、`StayPut` は何もしない
3. `SoundsThisTick` を空にする

状態の移り方:

| いまの状態 | きっかけ | 次の状態 |
|---|---|---|
| 休む・歩く | `hears_from` 以上の音を聞いた | 調べに行く (音のした場所) |
| 休む・歩く・調べに行く・探す・帰る | 人を見た (Hostile。Territorial は縄張りの中の人だけ) | 追う |
| 休む・歩く・調べに行く・探す・帰る | 人を見た (Timid) | 逃げる |
| 追う | 獲物が同じ場所に立っている | 追う (`every` ごとに襲う) |
| 追う | 獲物が出ていくのを見た | 追う (その通路をたどる) |
| 追う | 獲物を見失った (倒れた、通路が閉じた、出ていくのを見ていない) | 探す (最後に見た場所) |
| 調べに行く・探す | `gives_up_after` を過ぎた、道が無い | 帰る |
| 帰る | ねぐらに着いた | 休む |
| どれでも | HP が `flees_below` を下回った | 逃げる |
| 逃げる | 脅かした人が見えなくなった | 帰る |
| 休む | `wander_chance` に当たった | 歩く (縄張りの隣の場所) |

- 道は `WorldDesign.route` で、通れる通路だけをたどって選ぶ。閉じた通路・現れていない通路は通れない。通る条件 (`passage_traversal`) のある通路は、人を読まない条件 (夜だけ通れる、など) なら確かめて通り、人を読む条件 (荷・鍵・体) が付いていれば通れない。作者は通る条件で「人だけが通れる抜け道」を書ける
- 音を聞いたら、音のした場所へ最短の道で向かう。途中で別の音や獲物に出会えば切り替える。閉じた扉で道が無ければ、`gives_up_after` で帰る。音は閉じた扉を弱まりながら越えるが、モンスターは越えられない
- 襲う相手は、追っている獲物が同じ場所に立っていればその人、いなければ見えている立っている人から `facts.random()` で 1 人。倒れている人は襲わない
- 逃げる先は、脅かした人が来た通路を避けた隣の場所。ねぐらへの道があればそちらを選ぶ
- Territorial は、縄張りの外へ出た獲物を追わず、探さずに帰る

## 音の帳簿

```python
class SoundsThisTick:                             # 世界に 1 つ。帳簿なのでイベントは出さない
    def note(self, origin: SpotId, reach: SoundReach, at: WorldTick) -> None: ...
    def heard_at(self, spot: SpotId, from_level: SoundLevel) -> tuple[HeardSound, ...]: ...
    def clear(self) -> None: ...
```

- 音が鳴ったとき、`DeliverPerception` が届く範囲 (`SoundReach`) を 1 回だけ計算し、人にはその場で届け、同じ結果を `SoundsThisTick.note` に書く。音の届き方の計算は 1 か所のまま、受け手が 2 種類になる
- 人は帳簿を読まない。人への知らせは確定したその場で届き、「1 つの確定の範囲から 1 人に届く刺激は 1 つ」の決まりもその場で守る。帳簿を介すと、次に時間が進むまで届かない
- モンスターは 1 tick に 1 回だけ動くので、前の tick のあいだに鳴った音をまとめて聞く。音のたびにすぐ動くと、1 tick に何度も動けてしまう
- モンスターが立てた音 (足音、唸り声) も帳簿に入る。ほかのモンスターが聞く

## 人がモンスターを攻撃する

```python
AttackMonsterAttempt(actor: PersonId, monster: MonsterId)   # 一緒にいること (WithMonster) を確かめる。行っているあいだは持たない
```

- 痛手は `WorldRules.person_attack_damage` (共通の部品の既定 10)。武器・防御・命中・会心は持たない。武器で威力を変える仕組みは、要るシナリオが出たときに足す
- `Monster.take_damage` が、攻撃した人を覚えて状態を変える
- 見た人への文は、組み込みの行為の知覚の表の `attack_monster` の行。`{monster}` (モンスターの呼び名) と `{actor}` を書ける。共通の部品の既定は「{actor}が{monster}に打ちかかった。」
- 死んだら `MonsterDiedEvent`。`DropMonsterLootHandler` が、死んだ場所の地面に落とす物を置く (`bring_item_into_world` → `GroundItems.place`)。死骸は、湧きの `present_while` が偽になるまで残る。地面に落ちた物は、死骸が外れても残る

## 「倒されたら」の条件

```python
MonsterKilledCondition(spawn: MonsterSpawnId)   # その湧きの個体が、一度でも人に倒されていれば真
```

- 倒された記録は湧きの帳簿 (`MonsterSpawnRecords`) が持つ。湧きの真偽の変わり目と、倒された個体と倒した人と時刻を記録する
- 出来事の条件に書ける (「北の獣を倒したら、北の坑道が安全になる」)。倒した人に褒美を渡したいときは、`MonsterDiedEvent` を受けて知らせるのではなく、作者が出来事で書く

## 知覚

- モンスターがしたこと (現れた、去った、襲った、逃げた、死んだ) は、それぞれのドメインイベントから、刺激に変える役が刺激を作る。現れた・去ったは `Whereabouts` の `OccupantEnteredSpotEvent` / `OccupantLeftSpotEvent` (居場所は `MonsterBody`) から作る
- 文は世界の既定の `MonsterPerceptions` (共通の部品の `monster_perceptions`) に置き、種類ごとに `MonsterPerceptionsDeclaration` で書き換えられる。文には `{monster}` (呼び名) と、行ごとの呼び名 (`{origin}`、`{destination}`、`{target}` (襲われた人)) を書ける。刺激に変える役が `{monster}` を先に呼び名で埋める
- 襲われた人には本人の体の刺激が届く (「坑道の獣に襲われた」)。暗くて見えなければ、見える刺激の `dim` の文 (「暗闇から何かに襲われた」)
- モンスターの足音や唸り声は、聞こえる刺激として通路をまたいで届く (「重い足音が近づいてくる」)

## 場面

```python
@final
@dataclass(frozen=True)
class SeenMonster:
    monster: MonsterId
    called: DisplayName                     # 呼び名。同じ種類が 2 匹以上いれば番号を付ける (野犬 (2))
    health: DescriptionText                 # 傷の具合の文
    doing: DescriptionText                  # いましていることの文 (眠っている、こちらを見ている、襲いかかってくる)
    dead: bool
```

- `VisibleSurroundings` と `SpotContents` に `monsters` を足す。明るさの扱いは人と同じで、暗いときは呼び名でなく「何かがいる」、真っ暗では出さない
- 傷の具合は、HP の割合の境 (7 割、3 割) と文 (健康、傷を負っている、瀕死) を共通の部品の `monster_health` に置く (`MonsterHealthTexts`。境が重なる・0 から始まる段が無いと作れない)
- いましていることの文は、状態ごとに共通の部品の `monster_doing` に置く (`MonsterDoingTexts`。状態のどれかが無いと作れない) (休む: 眠っている、歩く: うろついている、調べに行く: 辺りを嗅ぎ回っている、追う: こちらを睨んでいる、探す: 何かを探している、帰る: 去ろうとしている、逃げる: 逃げようとしている)

## この先

- 第 2 段 (群れ): 群れの仲間が獲物を見たことを分け合い、頭について動く
- 第 3 段 (生態系): 空腹、モンスターどうしの捕食、地面の食べ物を食べる、増える。死骸を物のように扱い、解体して素材を取る操作 (皮を剥ぐ、など)
- 襲ったときの状態異常 (島の出血・毒) は、状態効果 (#2014) が決まってから足す
