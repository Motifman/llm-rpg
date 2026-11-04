# 知覚 (Stimulus と Perceived)

世界で起きたことを、誰が、どれだけはっきり知るか。決めた経緯は #1974。

```
ドメインイベント
  ↓ StimulusTranslator が刺激に変える
刺激 (Stimulus)
  ↓ DeliverPerception が知覚しうる人を選び、材料を集めて、刺激に聞く
知覚の結果 (Perceived / NotPerceived / NoticedLater)
  ↓ 観測の出口が時刻の札を付ける
Being の契約の観測 (文は TextWithPeople のまま。人の穴は Being が埋める)
```

知覚の決まりはドメインサービスにしない。規則は知覚する人 (`Perceiver`) と刺激、明るさと音の値に置き、世界を何でも読める窓口 (`WorldFacts`) は渡さない。

## 人と文

```python
@final
@dataclass(frozen=True)
class PersonHandle:                       # 環境の中で 1 人をずっと指す印。名前ではない
    value: int

@final
@dataclass(frozen=True)
class PersonRef:
    handle: PersonHandle
    appearance: str
    visible_name: str | NoVisibleName     # 名札の世界、最初から知っている相手だけ

@final
@dataclass(frozen=True)
class Unidentified: ...                   # 見分けのつかない人。印を持たない

@final
@dataclass(frozen=True)
class TextWithPeople:
    template: str                         # 穴は人だけ ({actor} {target})。物や操作の名前は作るときに埋める
    people: Mapping[str, PersonRef | Unidentified]
```

ゲームが作る文には、ほかの人の名前を文字として入れず、必ず `PersonRef` で渡す。列挙の値やキーもそのまま入れず、宣言の呼び名を使う。

## 刺激

```python
Stimulus = SightStimulus | SoundStimulus | BodilyStimulus | AnnouncementStimulus

Salience = Notable | Background

@final
@dataclass(frozen=True)
class SightTexts:
    clear: TextWithPeople
    dim: TextWithPeople | NotSeenInDim                    # 暗くて人の見分けがつかないとき
    unseen_actor: TextWithPeople | NotSeenWithoutActor    # 行った人が見えないとき (去った人の行為)
    noticed_later: TextWithPeople | NotNoticedLater       # 倒れていた本人が起きてから気づくとき

@final
@dataclass(frozen=True)
class SightStimulus:
    where: SpotId
    witness: SightTexts
    target: SightTexts | NoTarget
    seen_in_dark: bool
    manner: Openly | Stealthily
    involved: tuple[PersonId, ...]
    salience: Salience

    def perceived_by(self, perceiver: Perceiver, lighting: Lighting) -> PerceptionOutcome: ...

@final
@dataclass(frozen=True)
class SoundStimulus:
    origin: SpotId
    loudness: Loudness                    # ささやき / ふつう / 大きい / とても大きい
    clear: TextWithPeople
    muffled: TextWithPeople               # 誰の声か分からない
    noticed_later: TextWithPeople | NotNoticedLater
    whispered_to: PersonId | NotWhispered
    involved: tuple[PersonId, ...]
    salience: Salience

    def perceived_by(self, perceiver: Perceiver, reach: SoundReach, values: HearingValues) -> PerceptionOutcome: ...

@final
@dataclass(frozen=True)
class BodilyStimulus:                     # 行った本人の結果もこれ。暗くても自分のしたことは分かる
    person: PersonId
    text: TextWithPeople
    salience: Salience

    def perceived_by(self, perceiver: Perceiver) -> PerceptionOutcome: ...

@final
@dataclass(frozen=True)
class AnnouncementStimulus:
    audience: PeopleSelection
    text: TextWithPeople
    salience: Salience

    def perceived_by(self, perceiver: Perceiver) -> PerceptionOutcome: ...
```

## 知覚する人

```python
PerceiverState = Awake | Down | Gone | Departed

@final
@dataclass(frozen=True)
class Perceiver:                          # ユースケースが、生死・居場所・世界の決まりから作る
    person: PersonId
    state: PerceiverState
    location: Location
    attentive: bool                       # 耳を澄ましている

    def notices_surroundings(self, involved: bool) -> SurroundingsAwareness: ...

SurroundingsAwareness = Aware | NoticesLater | Unaware
```

| 刺激 | 起きている | 倒れている | 死んだ (`Gone`) | 去った |
|---|---|---|---|---|
| 見える | 明るさで決まる | 自分が関わるものは `NoticedLater`、ほかは `NotPerceived` | 知覚しない | 見える |
| 聞こえる | 音の届き方で決まる | 同上 | 知覚しない | 聞こえる |
| 本人の体 | 感じる | 感じる | 知覚しない | 体が無いので無い |
| 世界の知らせ | 届く | `NoticedLater` | 知覚しない | 届く |

移動中の人はどの場所にもいない。見える刺激には気づかず、区間の両端の場所で起きた「大きい」「とても大きい」音だけを隣の場所の音として聞く。

## 知覚の結果

```python
PerceptionOutcome = Perceived | NotPerceived | NoticedLater

PerceivedQuality = SeesClearly | SeesShapes | HearsClearly | HearsMuffled | HearsFaintly | Felt | Told

@final
@dataclass(frozen=True)
class Perceived:
    perceiver: PersonId
    text: TextWithPeople
    quality: PerceivedQuality
    happened_at: WorldTick
    calls_attention: bool                 # 関わっている、または目立つ刺激をかすか以外で知覚した。真なら手番を起こす

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
    outdoor: bool
    dark_time_of_day: bool                # 昼夜の宣言で、今の時間帯が暗いか
    weather_obscures: bool                # WeatherDeclaration.obscures_sight
    light_source_present: bool            # その場所の誰かが、灯った光源を持っているか

    def lighting(self) -> Lighting: ...
        # 宣言 → 屋外で暗い時間帯か見えにくくする天候なら 1 段暗く (重なっても 1 段)
        # → 光源があれば、暗い・真っ暗を薄暗いへ

Lighting = Bright | Dusky | Dark | PitchDark

SightQuality = SeesClearly | SeesShapes | SeesNothing

class Lighting:
    def sight(self) -> SightQuality: ...
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
class SoundLevel:
    value: int

    def weakened_by(self, loss: SoundLoss) -> "SoundLevel": ...
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
    ends: tuple[SpotId, SpotId]
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

HearingQuality = HearsClearly | HearsMuffled | HearsFaintly | HearsNothing
```

`HearingValues` は `WorldRules` にある ([world_design.md](world_design.md))。ささやきは、宛先にははっきり、同じ場所のほかの人にはかすかに届く。「N 名に届いた」も同じ計算で数え、倒れている人は入れない。

## 倒れている間のこと

```python
@final
@dataclass(frozen=True)
class MissedNotice:
    text: TextWithPeople
    happened_at: WorldTick
```

ためる集約 `MissedNotices` は [world_state.md](world_state.md)。

## 場面

```python
@final
@dataclass(frozen=True)
class SpotContents:                       # その場所にあるもの。ユースケースが集める
    spot: SpotDeclaration
    passages: tuple[PassageInState, ...]
    objects: tuple[ObjectDeclaration, ...]
    ground_items: tuple[ItemInstanceId, ...]
    people: tuple[PersonRef, ...]
    bodies: tuple[PersonRef, ...]
    monsters: tuple[MonsterId, ...]

@final
@dataclass(frozen=True)
class VisibleSurroundings:
    spot: SpotDeclaration
    shows_description: bool               # 真っ暗なら説明を出さず、音と気温だけ
    passages: tuple[PassageInState, ...]  # 真っ暗でも出す (手探りで分かる)
    objects: tuple[ObjectDeclaration, ...]
    ground_items: tuple[ItemInstanceId, ...]
    people: tuple[PersonRef | Unidentified, ...]
    bodies: tuple[PersonRef | Unidentified, ...]
    monsters: tuple[MonsterId, ...]
    distant: tuple[DistantSight, ...]     # 屋外で見えるときだけ。視程は天候の宣言から

    @classmethod
    def seen_with(cls, sight: SightQuality, contents: SpotContents, distant: tuple[DistantSight, ...]) -> "VisibleSurroundings": ...
```

- 持ち物、体の状態、時刻は、見えているものではなく自分が知っていること。場面に入れず、知覚を通さずに集約から読む。複数の集約にまたがるものはドメインサービスにする
- 場面は「何が見えるか」だけを持つ。「何ができるか」は `AvailableActions` ([action.md](action.md)) が持ち、行為の対象の候補は場面に出ているものに限る
- 着いたとき、起き上がったとき、その場所の明るさが上がったとき (灯した、夜が明けた、明かりを持った人が来た) は、場面の人、倒れた体、モンスターを 1 つの観測にして渡す。明るさが上がったかは、出来事の前後の `LightingConditions` を比べて決める
