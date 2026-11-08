# 知覚 (Stimulus と Perceived)

世界で起きたことを、誰が、どれだけはっきり知るか。決めた経緯は #1974。

```
ドメインイベント
  ↓ StimulusTranslator が刺激に変える
刺激 (Stimulus)
  ↓ DeliverPerception が知覚しうる人を選び、材料を集めて、刺激に聞く
知覚の結果 (Perceived / NotPerceived / NoticedLater)
  ↓ 観測の出口が時刻の札を付ける
Being の契約の観測 (文は TextWithAssignedPeople のまま。人のプレースホルダーは Being が埋める)
```

1 つの確定の範囲 (1 つの行為、1 つの出来事の発火、1 回の時の経過) から出た刺激は、1 人には最初に知覚したもの 1 つだけを渡す。扉が開くのを見た人に、同じ扉の音を別の観測として重ねないため。聞く順は、行為のイベント (`PersonActedEvent`、`ActionAttemptFailedEvent`) から作った刺激が先で、状態のイベントから作った刺激が後。その中では 本人の体 → 見える → 聞こえる → 世界の知らせ。`always_delivered` の刺激 (倒れたこと) だけは、ほかと重なっても届ける。

知覚の決まりはドメインサービスにしない。規則は知覚する人 (`Perceiver`) と刺激、明るさと音の値に置き、世界を何でも読める窓口 (`WorldFacts`) は渡さない。

## 人と文

```python
@final
@dataclass(frozen=True)
class PersonHandle:                       # 環境の中で 1 人をずっと指す印。名前ではない
    value: int                            # 0 以上

@final
@dataclass(frozen=True)
class PersonRef:
    handle: PersonHandle
    appearance: str                       # 空や空白だけは断る
    visible_name: str | NoVisibleName     # 名札の世界、最初から知っている相手だけ。空や空白だけは断る

@final
@dataclass(frozen=True)
class Unidentified: ...                   # 見分けのつかない人。印を持たない

@final
@dataclass(frozen=True)
class TextWithAssignedPeople:
    template: str                         # プレースホルダーは人だけ ({actor} {target})
    people: Mapping[str, PersonRef | Unidentified]   # 文のプレースホルダーと鍵が過不足なく揃う。揃わなければ断る

@final
@dataclass(frozen=True)
class TextWithUnassignedPeople:       # 作者が宣言に書く、人がまだ決まっていない文
    template: str

    def placeholders(self) -> frozenset[str]: ...
    def about(self, people: Mapping[str, PersonId]) -> TextAboutPeople: ...
    def assign(self, people: Mapping[str, PersonRef | Unidentified]) -> TextWithAssignedPeople: ...

@final
@dataclass(frozen=True)
class TextAboutPeople:                    # プレースホルダーに、誰のことかだけを当てた文。誰が見るかはまだ決まっていない
    template: TextWithUnassignedPeople
    people: Mapping[str, PersonId]        # 文のプレースホルダーと鍵が過不足なく揃う。揃わなければ断る

    def seen_by(self, view: PeopleAsSeen) -> TextWithAssignedPeople: ...   # 見る人から見た呼び方を当てる
    def unidentified(self) -> TextWithAssignedPeople: ...                  # 誰も見分けられない (暗がり、誰の声か分からない)

class PeopleAsSeen(Protocol):             # 1 人の見る人から見た、ほかの人の呼び方。知覚を届けるところ、いまできることを組むところが作る
    def ref_of(self, person: PersonId) -> PersonRef: ...
```

ゲームが作る文には、ほかの人の名前を文字として入れず、必ず `PersonRef` で渡す。列挙の値やキーもそのまま入れず、宣言の呼び名を使う。

- 型の名前の Person は 1 人 (`PersonHandle`、`PersonRef`)、People は文の中の人たちを指す。2 つの文の型はどちらもプレースホルダーを持ち、違いは誰が入るかが決まっているかだけ
- 文は 3 段で決まる。作者が宣言に書く文は `TextWithUnassignedPeople` ([world_design.md](world_design.md)、[condition.md](condition.md) の `failure_text`)。刺激を作るとき、条件を評価するときに、誰のことかが決まって `TextAboutPeople` になる。見る人が決まったところ (知覚を届けるところ、いまできることを組むところ、断られた本人に届けるところ) で、その人から見た呼び方を当てて `TextWithAssignedPeople` にする
- 同じ出来事や理由を、行った人と見ていた人が別の呼び方で見るので、見る人が決まる前に `PersonRef` を当てない。刺激と断られた理由は `TextAboutPeople` で持ち、知覚の結果 (`Perceived`) から先は `TextWithAssignedPeople`。プレースホルダーが埋まらないままの文は Being に渡らない
- プレースホルダーは人だけ。物や操作の名前は、宣言がどの物体・操作のものか分かっているので、作者が文に直接書く
- プレースホルダーの書き方は `{名前}` だけ。名前は識別子に限り、位置のプレースホルダー (`{}` `{0}`)、変換 (`{actor!r}`)、書式指定 (`{actor:>3}`)、属性や添字 (`{actor.name}`) と閉じていない括弧は、作るときに断る。`{{` `}}` は文字の括弧

## 刺激

```python
Stimulus = SightStimulus | SoundStimulus | BodilyStimulus | AnnouncementStimulus

Salience = Notable | Background

@final
@dataclass(frozen=True)
class SightTexts:
    clear: TextAboutPeople
    dim: TextAboutPeople | NotSeenInDim                    # 暗くて人の見分けがつかないとき
    unseen_actor: TextAboutPeople | NotSeenWithoutActor    # 行った人が見えないとき (去った人の行為)
    noticed_later: TextAboutPeople | NotNoticedLater       # 倒れていた本人が起きてから気づくとき

@final
@dataclass(frozen=True)
class SightStimulus:
    where: SpotId
    witness: SightTexts
    target: SightTexts | NoTarget
    seen_in_dark: bool                    # 暗くても見える行為か (光る物、大きな動き)。真なら真っ暗でも dim の文が届く
    manner: Openly | Stealthily
    involved: tuple[PersonId, ...]
    salience: Salience
    always_delivered: bool                # 作者の目撃の文が倒れたことに触れていなくても、見ていた人が知るため

    def perceived_by(self, perceiver: Perceiver, lighting: Lighting, view: PeopleAsSeen) -> PerceptionOutcome: ...

@final
@dataclass(frozen=True)
class SoundStimulus:
    origin: SpotId
    loudness: Loudness                    # ささやき / ふつう / 大きい / とても大きい
    clear: TextAboutPeople
    muffled: TextAboutPeople               # 誰の声か分からない。届けるときは unidentified() で当てる
    noticed_later: TextAboutPeople | NotNoticedLater
    whispered_to: PersonId | NotWhispered
    involved: tuple[PersonId, ...]
    salience: Salience

    def perceived_by(self, perceiver: Perceiver, reach: SoundReach, values: HearingValues, view: PeopleAsSeen) -> PerceptionOutcome: ...

@final
@dataclass(frozen=True)
class BodilyStimulus:                     # 行った本人の結果もこれ。暗くても自分のしたことは分かる
    person: PersonId
    text: TextAboutPeople
    salience: Salience

    def perceived_by(self, perceiver: Perceiver, view: PeopleAsSeen) -> PerceptionOutcome: ...

@final
@dataclass(frozen=True)
class AnnouncementStimulus:
    audience: PeopleSelection
    text: TextAboutPeople
    salience: Salience

    def perceived_by(self, perceiver: Perceiver, view: PeopleAsSeen) -> PerceptionOutcome: ...
```

## 知覚する人

```python
Perceiver = LivingPerceiver | DepartedPerceiver

@final
@dataclass(frozen=True)
class LivingPerceiver:
    person: PersonId
    life: Alive | Down
    location: Location
    attentive: bool                       # 耳を澄ましている

    def notices_surroundings(self, involved: bool) -> SurroundingsAwareness: ...

@final
@dataclass(frozen=True)
class DepartedPerceiver:                  # 死んで、去った人として動く人 (DepartedPerson)
    person: PersonId
    location: Location

    def notices_surroundings(self, involved: bool) -> SurroundingsAwareness: ...

SurroundingsAwareness = Aware | AwareOnWaking | Unaware
```

死んだ人が去った人として行為をしない世界 (`departed_persons_act` が偽) の人には、`DeliverPerception` が知覚する人を作らない。何も知覚しない。

| 刺激 | `LivingPerceiver` (`Alive`) | `LivingPerceiver` (`Down`) | `DepartedPerceiver` |
|---|---|---|---|
| 見える | 明るさで決まる | 自分が関わるものは `NoticedLater`、ほかは `NotPerceived` | 見える |
| 聞こえる | 音の届き方で決まる | 同上 | 聞こえる |
| 本人の体 | 感じる | 感じる (気を失っていても痛みや寒さは体に残る。#1974 の 6.) | 体が無いので無い |
| 世界の知らせ | 届く | `NoticedLater` (知らせの文をそのままためる) | 届く |

移動中の人はどの場所にもいない。見える刺激には気づかず、区間の両端の場所で起きた「大きい」「とても大きい」音だけを隣の場所の音として聞く。

## 知覚の結果

```python
PerceptionOutcome = Perceived | NotPerceived | NoticedLater

PerceivedQuality = SeesClearly | SeesShapes | HearsClearly | HearsMuffled | HearsFaintly | Felt | Told   # SightQuality と HearingQuality の値をそのまま使う

@final
@dataclass(frozen=True)
class Perceived:
    perceiver: PersonId
    text: TextWithAssignedPeople
    quality: PerceivedQuality
    happened_at: WorldTick
    calls_attention: bool                 # 関わっている、または目立つ刺激をかすか以外で知覚した。世界は手番を起こさない。外側が考え直す目安に使う

@final
@dataclass(frozen=True)
class NoticedLater:
    notice: MissedNotice
```

## 明るさ

```python
@final
@dataclass(frozen=True)
class LightingConditions:                 # 1 つの場所の明るさを決める材料。ユースケースが集める
    declared: Lighting                    # 場所の宣言 (雰囲気が変わっていれば、変わった値)
    outdoor: bool                         # SpotAtmosphere.outdoor
    dark_time_of_day: bool                # DayPhaseDeclaration.dark
    weather_obscures: bool                # WeatherDeclaration.obscures_sight
    light_source_present: bool            # その場所の誰かが、灯った光源を手に持っているか (荷の中では照らさない)

    def lighting(self) -> Lighting: ...
        # 宣言 → 屋外の場所なら、夜などの暗い時間帯 (DayPhaseDeclaration.dark) か、霧や嵐など見通しの悪い天候 (WeatherDeclaration.obscures_sight) のときに 1 段暗く。両方が重なっても 1 段だけ。屋内は変わらない
        # → 光源があれば、暗い・真っ暗を薄暗いへ

class Lighting(Enum):
    BRIGHT = "BRIGHT"
    DUSKY = "DUSKY"
    DARK = "DARK"
    PITCH_DARK = "PITCH_DARK"

    def sight(self) -> SightQuality: ...

SightQuality = SeesClearly | SeesShapes | SeesNothing
```

| 明るさ | 見え方 | 物体 | 人 |
|---|---|---|---|
| 明るい、薄暗い | `SeesClearly` | 見える | 見分けられる |
| 暗い | `SeesShapes` | 暗くても見える物体だけ | 「誰か」(`Unidentified`) |
| 真っ暗 | `SeesNothing` | 暗くても見える物体だけ | いるのも分からない |

## 音

```python
@final
@dataclass(frozen=True)
class SoundLevel:                         # 0 以上
    value: int

    def weakened_by(self, loss: SoundLoss) -> "SoundLevel": ...   # 0 で止まる
    def is_below(self, other: "SoundLevel") -> bool: ...

@final
@dataclass(frozen=True)
class SoundLoss:                          # 0 以上
    value: int

    def plus(self, other: "SoundLoss") -> "SoundLoss": ...

@final
@dataclass(frozen=True)
class PassageInState:
    passage: PassageDeclaration
    state: PassageStateName

@final
@dataclass(frozen=True)
class SoundLink:
    ends: tuple[SpotId, SpotId]           # 向きを持たない。どちらの端で鳴った音も反対の端へ届く
    loss: SoundLoss                       # 通路ごとの減衰 + 通路の状態の減衰

@final
@dataclass(frozen=True)
class SoundNetwork:
    links: tuple[SoundLink, ...]

    @classmethod
    def through(cls, passages: Iterable[PassageInState], per_passage: SoundLoss) -> "SoundNetwork": ...
    def spread(self, origin: SpotId, start: SoundLevel, stop_below: SoundLevel) -> SoundReach: ...
        # 減衰の合計が最も小さい道で届く。聞こえる下限を下回ったら広げない

@final
@dataclass(frozen=True)
class SoundReach:
    levels: Mapping[SpotId, SoundLevel]

    def level_at(self, spot: SpotId) -> SoundLevel | NotReached: ...

@final
@dataclass(frozen=True)
class NotReached: ...

class Loudness(Enum):
    WHISPER = "WHISPER"
    NORMAL = "NORMAL"
    LOUD = "LOUD"
    VERY_LOUD = "VERY_LOUD"

HearingQuality = HearsClearly | HearsMuffled | HearsFaintly | HearsNothing
```

音の届き方は、出来事が確定した後の通路の状態で計算する (扉を開けた音は、開いた扉を通る)。`HearingValues` は `WorldRules` にある ([world_design.md](world_design.md))。聞こえる刺激で人が分かるのは声 (話す) だけ。物音の文の人のプレースホルダーはいつも `Unidentified`。ささやきは、宛先にははっきり、同じ場所のほかの人にはかすかに届く。「N 名に届いた」も同じ計算で数え、倒れている人は入れない。

## 倒れている間のこと

```python
@final
@dataclass(frozen=True)
class MissedNotice:
    text: TextWithAssignedPeople
    happened_at: WorldTick
```

ためる集約 `MissedNotices` は [world_state.md](world_state.md)。

## 場面

```python
@final
@dataclass(frozen=True)
class SeenPerson:
    person: PersonRef | Unidentified
    section: SpotSectionId | OpenArea     # 籠の中にいる、など
    visible_items: tuple[ItemInstanceId, ...]   # 起きている人は手に持っている物だけ。倒れた人と死んだ人は持ち物すべて

@final
@dataclass(frozen=True)
class PresentPerson:                      # その場所にいる人。見えるかはまだ決まっていない
    person: PersonRef
    section: SpotSectionId | OpenArea
    held_items: tuple[ItemInstanceId, ...]
    all_items: tuple[ItemInstanceId, ...]

@final
@dataclass(frozen=True)
class SpotContents:                       # その場所にあるもの。ユースケースが集める
    spot: SpotDeclaration
    passages: tuple[PassageInState, ...]
    sections: tuple[SpotSectionDeclaration, ...]
    objects: tuple[ObjectDeclaration, ...]
    ground_items: tuple[ItemInstanceId, ...]
    people: tuple[PresentPerson, ...]
    bodies: tuple[PresentPerson, ...]
    monsters: tuple[MonsterId, ...]

@final
@dataclass(frozen=True)
class VisibleSurroundings:
    spot: SpotDeclaration
    shows_description: bool               # 真っ暗なら説明を出さず、音と気温だけ
    passages: tuple[PassageInState, ...]  # 真っ暗でも出す (手探りで分かる)
    sections: tuple[SpotSectionDeclaration, ...]
    objects: tuple[ObjectDeclaration, ...]
    ground_items: tuple[ItemInstanceId, ...]
    people: tuple[SeenPerson, ...]
    bodies: tuple[SeenPerson, ...]        # 倒れている人と死んだ人
    monsters: tuple[MonsterId, ...]
    distant: tuple[DistantSight, ...]     # 屋外で見えるときだけ。視程は天候の宣言から

    @classmethod
    def seen_with(cls, sight: SightQuality, contents: SpotContents, distant: tuple[DistantSight, ...]) -> "VisibleSurroundings": ...
```

- 持ち物、体の状態、時刻は、見えているものではなく自分が知っていること。場面に入れず、知覚を通さずに集約から読む。複数の集約にまたがるものはドメインサービスにする
- 場面は「何が見えるか」だけを持つ。「何ができるか」は `AvailableActions` ([action.md](action.md)) が持ち、行為の対象の候補は場面に出ているものに限る
- 着いたとき、起き上がったとき、その場所の明るさが上がったとき (灯した、夜が明けた、明かりを持った人が来た) は、場面の人、倒れた体、モンスターを 1 つの観測にして渡す (`DeliverSurroundings`)。明るさが上がったかは、出来事の前後の `LightingConditions` を比べて決める
