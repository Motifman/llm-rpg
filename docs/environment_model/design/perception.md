# 知覚 (Stimulus と Perceived)

世界で起きたことを、誰が、どれだけはっきり知るか。決めた経緯は #1974。

```
確定したドメインイベント
  ↓ OccurrencesInCommit がまとまり (1 つの行為、1 回の発火、時の経過のイベント 1 つ) に分ける
  ↓ StimulusTranslator が刺激に変える
刺激 (Stimulus)
  ↓ DeliverPerception が知覚しうる人を選び、材料を集めて、刺激に聞く
知覚の結果 (Perceived / NotPerceived / NoticedLater)。まとまりごとに、届けた記録 (PerceptionDeliveryReport) も作る
  ↓ 観測の出口が時刻の札を付ける
Being の契約の観測 (文は TextWithAssignedPeople のまま。人のプレースホルダーは Being が埋める)
```

確定したイベントは、まとまりに分けて刺激に変える (D2206)。

- 行為と、作者の出来事・反応・二人で合わせる操作の発火は、1 回ずつを 1 まとまりにする。確定したイベントを出た順 (`DomainEvent.sequence`) に読み、行為と発火の記録のイベント (`PersonActedEvent`、`ActionAttemptFailedEvent`、`HappeningFiredEvent`、`ReactionFiredEvent`、`JointActionCompletedEvent`、`JointActionTimedOutEvent`) までを 1 まとまりにする。効果は記録より先に当たるので、その発火の効果から出たイベントは、その発火のまとまりに入る。最後の記録より後に出たイベント (世界の終わりなど) は、最後のまとまりに入る
- 時の経過 (`WorldTickAdvancedEvent` を含む確定) では、イベント 1 つずつを 1 まとまりにする。同じ tick に広場へ着いたハルとゲンは、広場のサヨにどちらも届く
- どちらでもない確定 (ハンドラの確定など) は、確定全体で 1 まとまり。原因は名前の無い原因 (`UnnamedCause`) で、イベントの種類名を並べる

1 つのまとまりから出た刺激は、1 人には最初に知覚したもの 1 つだけを渡す。扉が開くのを見た人に、同じ扉の音を別の観測として重ねないため。数えるのは、同じものを別の感覚で知る刺激 (本人の体・見える・聞こえる) だけで、世界の知らせ (結末、時間帯、作者の `announcement_to`) は数えず、ほかと重なっても届ける。世界の知らせは見聞きしたことの言い換えではなく、別のことを伝えるため (D2203)。聞く順は、行為のイベント (`PersonActedEvent`、`ActionAttemptFailedEvent`) から作った刺激が先で、状態のイベントから作った刺激が後。その中では 本人の体 → 見える → 聞こえる → 世界の知らせ。同じ種類の刺激が 2 つ以上あれば、目立つ刺激 (`Notable`) を目立たない刺激 (`Background`) より先にし、それも同じならイベントの通し番号の順 (出た順) にする。順はイベントの種類と刺激の目立ち方で決め、集約をまたいでイベントが集まる順には頼らない。数える刺激のうち、`always_delivered` の刺激 (倒れたこと) だけは、ほかと重なっても届ける。

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
    appearance: DescriptionText           # CharacterDeclaration.appearance
    visible_name: DisplayName | NoVisibleName   # 名札の世界 (WorldRules.name_tags) か、見る人が最初から知っている相手 (knows_at_start) だけ

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

@final
@dataclass(frozen=True)
class PeopleSeenBy:                       # PeopleAsSeen の実装
    viewer: PersonId
    register: PeopleRegisterReading       # 番号、名前、見た目 (world_state.md の PeopleRegister)
    name_tags: bool                       # WorldRules.name_tags
    knows_at_start: frozenset[PersonId]   # 見る人の CharacterDeclaration.knows_at_start

    def ref_of(self, person: PersonId) -> PersonRef: ...
        # 名前を出すのは、名札の世界か、knows_at_start の相手か、見る人自身
        # 名前を出す相手の名前が名簿に記録されていなければ、見た目だけに落とさず断る (PeopleRegister.name_of)
```

ゲームが作る文には、ほかの人の名前を文字として入れず、必ず `PersonRef` で渡す。列挙の値やキーもそのまま入れず、宣言の呼び名を使う。

- 型の名前の Person は 1 人 (`PersonHandle`、`PersonRef`)、People は文の中の人たちを指す。2 つの文の型はどちらもプレースホルダーを持ち、違いは誰が入るかが決まっているかだけ
- 文は 3 段で決まる。作者が宣言に書く文は `TextWithUnassignedPeople` ([world_design.md](world_design.md)、[condition.md](condition.md) の `failure_text`)。刺激を作るとき、条件を評価するときに、誰のことかが決まって `TextAboutPeople` になる。見る人が決まったところ (知覚を届けるところ、いまできることを組むところ、断られた本人に届けるところ) で、その人から見た呼び方を当てて `TextWithAssignedPeople` にする
- 同じ出来事や理由を、行った人と見ていた人が別の呼び方で見るので、見る人が決まる前に `PersonRef` を当てない。刺激と断られた理由は `TextAboutPeople` で持ち、知覚の結果 (`Perceived`) から先は `TextWithAssignedPeople`。プレースホルダーが埋まらないままの文は Being に渡らない
- プレースホルダーは人だけ。物や操作の名前は、宣言がどの物体・操作のものか分かっているので、作者が文に直接書く。例外は組み込みの行為の知覚の文 (`BuiltInActionPerceptions`、[world_design.md](world_design.md)) で、扱う物や場所が行為ごとに変わるので呼び名のプレースホルダーを書ける。刺激に変える役が先に呼び名で埋める
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
class SightTarget:                        # 行為の相手と、相手が見る文。相手は notice_by_target の確率で気づく。相手が involved に無ければ刺激を作れない
    person: PersonId
    texts: SightTexts

@final
@dataclass(frozen=True)
class SightStimulus:
    where: SpotId
    witness: SightTexts
    target: SightTarget | NoTarget
    seen_in_dark: bool                    # 暗くても見える行為か (光る物、大きな動き)。真なら真っ暗でも dim の文が届く
    manner: Openly | Stealthily
    actor_departed: bool                  # 行った人が去った人。生きている人には unseen_actor の文を届け、去った人には clear の文を届ける
    involved: tuple[PersonId, ...]
    salience: Salience
    always_delivered: bool                # 作者の目撃の文が倒れたことに触れていなくても、見ていた人が知るため
    at: WorldTick

    def perceived_by(self, perceiver: Perceiver, lighting: Lighting, view: PeopleAsSeen, random: RandomSource, stealth: StealthRule) -> PerceptionOutcome: ...
        # Stealthily の刺激だけ、見ていた人ごとに StealthRule の確率 (見え方ごと、耳を澄ましていれば attentive_bonus を足す) を random から引いて気づくかを決める。気づかなければ NotPerceived

@final
@dataclass(frozen=True)
class SoundStimulus:
    origin: SpotId
    loudness: Loudness                    # ささやき / ふつう / 大きい / とても大きい
    clear: TextAboutPeople
    muffled: TextAboutPeople               # 誰の声か分からない。くぐもる・かすかなときに unidentified() で当てる
    noticed_later: TextAboutPeople | NotNoticedLater
    source: Voice | Noise
    involved: tuple[PersonId, ...]
    salience: Salience
    at: WorldTick

    def perceived_by(self, perceiver: Perceiver, reach: SoundReach, values: HearingValues, view: PeopleAsSeen) -> PerceptionOutcome: ...

@final
@dataclass(frozen=True)
class Voice:                              # 話す声。はっきり聞こえたときだけ、clear の文に見る人から見た呼び方を当てる
    whispered_to: PersonId | NotWhispered

@final
@dataclass(frozen=True)
class Noise: ...                          # 物音。はっきり聞こえても clear の文は unidentified() で当てる

@final
@dataclass(frozen=True)
class BodilyStimulus:                     # 行った本人の結果もこれ。暗くても自分のしたことは分かる
    person: PersonId
    text: TextAboutPeople
    salience: Salience
    at: WorldTick

    def perceived_by(self, perceiver: Perceiver, view: PeopleAsSeen) -> PerceptionOutcome: ...

@final
@dataclass(frozen=True)
class AnnouncementStimulus:
    audience: frozenset[PersonId]         # 刺激に変える役が PeopleSelection で選んでおく。知覚の規則には facts を渡さないため
    text: TextAboutPeople
    salience: Salience
    at: WorldTick
    reaches_who_left_the_world: bool = False   # 結末の知らせだけが真。世界から外れた人には、これが真の知らせだけが届く
    kept_while_fainted: bool = True            # 時間帯の知らせだけが偽。倒れている相手には届けず、ためもしない

    def perceived_by(self, perceiver: Perceiver, view: PeopleAsSeen) -> PerceptionOutcome: ...
```

## 知覚する人

```python
Perceiver = LivingPerceiver | DepartedPerceiver | DeadPerceiver | PersonWhoLeftTheWorld

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

@final
@dataclass(frozen=True)
class DeadPerceiver:                      # 死んで、去った人としても動かない人
    person: PersonId

    def notices_surroundings(self, involved: bool) -> SurroundingsAwareness: ...   # いつも Unaware

@final
@dataclass(frozen=True)
class PersonWhoLeftTheWorld:              # 作者の結末が決まって、世界から外れた人。居場所が無い
    person: PersonId
    life: Alive | Down

    def notices_surroundings(self, involved: bool) -> SurroundingsAwareness: ...   # LivingPerceiver と同じく、倒れていれば AwareOnWaking

SurroundingsAwareness = Aware | AwareOnWaking | Unaware
```

死んだ人が去った人として行為をしない世界 (`departed_persons_act` が偽) の死んだ人は `DeadPerceiver` になり、何も知覚しない。どの場所にもおらず、体も感じず、周りに気づかないので、どの刺激も `NotPerceived` になり、見渡しても `NothingInView`。

| 刺激 | `LivingPerceiver` (`Alive`) | `LivingPerceiver` (`Down`) | `DepartedPerceiver` | `DeadPerceiver` | `PersonWhoLeftTheWorld` |
|---|---|---|---|---|---|
| 見える | 明るさで決まる | 自分が関わるものは `NoticedLater`、ほかは `NotPerceived` | 見える | `NotPerceived` | `NotPerceived` |
| 聞こえる | 音の届き方で決まる | 同上 | 聞こえる | `NotPerceived` | `NotPerceived` |
| 本人の体 | 感じる | 感じる (気を失っていても痛みや寒さは体に残る。#1974 の 6.) | 体が無いので無い | `NotPerceived` | `NotPerceived` |
| 世界の知らせ | 届く | `NoticedLater` (知らせの文をそのままためる)。時間帯の知らせは、倒れている人を相手から外すので届かない | 届く | `NotPerceived` | 結末の知らせ (`reaches_who_left_the_world`) だけ届く。倒れていれば `NoticedLater` |

- 去った人は、同じ場所の見える刺激を、明るさとこっそりに関わらず `SeesClearly` で clear の文で見る。音は、その場所に届いていれば `HearsClearly` で聞く。ただし宛先でないささやきは、生きている人と同じくかすか。去った人も行為ができるので、生きている人どうしの秘密が筒抜けにならないようにする
- 倒れている人は、見える刺激なら同じ場所にいること、音なら届くことだけで `NoticedLater` を受ける。明るさとこっそりの確率は見ない。文は、相手なら `target` の、ほかは `witness` の `noticed_later` で、`NotNoticedLater` なら `NotPerceived`
- 去った人の行為を生きている人が見るときは、明るさの規則はふだんどおりで、文は `unseen_actor`。`SeesShapes` なら `unidentified()` で当てる

移動中の人はどの場所にもいない。見える刺激には気づかず、区間の両端の場所で起きた「大きい」「とても大きい」音だけを隣の場所の音として聞く。聞こえ方は、その音の大きさを `loss_per_passage` 1 つぶん弱めて決める。

作者が書く結末と時間帯の知らせは、どちらも世界の知らせ (`AnnouncementStimulus`) にする (D2203)。

| 知らせ | 元のイベント | 相手 (`audience`) | 目立ち方 | 倒れている人 |
|---|---|---|---|---|
| 結末 (`OutcomeDeclaration.announcement`) | `PersonOutcomeDecidedEvent` | 結末が決まった本人だけ。世界から外れていても届ける (居場所を問わない)。文の `{each_person}` も本人。死んだ結末 (`Died`) には出さない | `Notable` | `NoticedLater` でためて、目が覚めたとき、または気を失ったまま世界から外れるときに、たまった知らせと同じ順で届く |
| 時間帯 (`DayPhaseDeclaration.announcement`) | `TimeOfDayChangedEvent` | 宣言の `audience` で選んだ人。`EveryoneAwake` なら起きている全員で、死んで去った人として動く人と移動中の人を含む。どちらでも倒れている人と、結末が決まって世界から外れた人は外す。`PassWorldTime` が時計を進めるときに選んで `TimeOfDayChangedEvent` に載せる | `Background` | 相手に入れないので、届かず、ためもしない |

- 例: 籠が上がってハルとサヨが外へ出たとき、坑道の奥のゲンには「ゲンは坑道に取り残された」だけが届き、ハルの結末は届かない。籠が上がる様子は、作者が出来事の知らせに書いて周りに伝える。結末の知らせは数えないので、同じ発火の籠の音を聞いたゲンにも両方届く
- 時間帯が変わって明るさも変わったときは、明るさの知らせ (`DeliverDarkeningHandler`、`DeliverSurroundingsOnBrighteningHandler`) と作者の時間帯の文の両方が届く。作者の文が明るさに触れるとは限らないため。重なりが気になれば、作者が文を直す
- 時間帯の知らせをためないのは、目が覚めたときに何時間も前の「夜になった」が届くと、いまの時刻と食い違うため。目が覚めたときの場面で分かれば足りる
- 気を失ったまま結末が決まった人は、世界から外れて目覚めない。外れるときに、たまった知らせ (結末の知らせを含む) を、目が覚めたときと同じくためた順で渡す。結末が後で必ず本人に届くようにするため
- 屋外の場所にいる人に限るときは、屋外の場所を並べて選ぶ (`is_at_spot` の `any_of`)。移動中の人はどの場所にもいないので選ばれない
- 本人の体の刺激 (`BodilyStimulus`) にしないのは、倒れていても届いてしまい、結末を目が覚めたときに届ける決まりと食い違うため

## 知覚の結果

```python
PerceptionOutcome = Perceived | NotPerceived | NoticedLater

PerceivedQuality = SeesClearly | SeesShapes | HearsClearly | HearsMuffled | HearsFaintly | Felt | Told | NoticedOnWaking   # SightQuality と HearingQuality の値をそのまま使う。NoticedOnWaking は倒れている間にたまった知らせ (#2154)

@final
@dataclass(frozen=True)
class Perceived:
    perceiver: PersonId
    text: TextWithAssignedPeople
    quality: PerceivedQuality
    happened_at: WorldTick
    calls_attention: bool                 # 関わっている、または目立つ刺激をかすか以外で知覚した。本人の体と世界の知らせは目立つときだけ。世界は手番を起こさない。外側が考え直す目安に使う

@final
@dataclass(frozen=True)
class NotPerceived:
    reason: NotPerceivedReason

@final
@dataclass(frozen=True)
class NoticedLater:
    notice: MissedNotice
```

知覚しなかった刺激は、理由 (`NotPerceivedReason`) を持つ (D2206)。理由は刺激と知覚する人が決める。死んだ人 (`DeadPerceiver`) と世界から外れた人は居場所が無いので、見える・聞こえる刺激では「その場にいない」、他人の体の刺激では「本人の体ではない」になる。「死んでいる」「世界から外れた」になるのは、宛先に入っていた知らせが届かなかったときだけ。

| 理由 | いつ |
|---|---|
| `ELSEWHERE` その場にいない | 見える刺激の場所にいない。居場所の無い人 (死んだ人、世界から外れた人) の見える・聞こえる刺激 |
| `OUT_OF_EARSHOT` 遠い | 音が届かない。ささやきで鳴った場所にいない |
| `TOO_QUIET` 音が小さい | 届いたが、聞こえる大きさに足りない |
| `TOO_DARK` 暗くて見えない | 暗い・真っ暗で、その明るさの文が無い |
| `STEALTH_UNNOTICED` こっそりに気づかなかった | こっそりの確率を引いて気づかなかった |
| `ACTOR_UNSEEN` 行為者が見えない | 去った人の行為で、行為者が見えないときの文が無い |
| `UNCONSCIOUS` 気を失っている | 倒れていて関わっていない。関わっていても、起きてから知る文が無い |
| `NOT_OWN_BODY` 本人の体ではない | 本人の体の刺激で、本人でない。体の無い去った人 |
| `NOT_ADDRESSED` 知らせの宛先でない | 世界の知らせの相手でない |
| `LEFT_THE_WORLD` 世界から外れた | 結末が決まって世界から外れた人が、宛先に入っていた知らせを受けない |
| `DEAD` 死んでいる | 去った人として行為をしない世界の死んだ人が、宛先に入っていた知らせを受けない |
| `ALREADY_PERCEIVED` 同じものをもう知った | 同じまとまりの別の感覚の刺激を、もう知った (1 人に 1 つ) |

## 届けた記録

`DeliverPerception` は 1 まとまりを届けるたびに、記録 (`PerceptionDeliveryReport`) を作って受け口 (`PerceptionReportReceiver`) に渡す (D2206)。`trace.jsonl` への書き出しは、run の入口を作るときに足す。

```python
@final
@dataclass(frozen=True)
class PerceptionDeliveryReport:
    cause: PerceptionCause                # ActionTaken | ActionFailed | HappeningFiring | ReactionFiring | JointActionSettling | TimePassed | Waking | UnnamedCause
    at: WorldTick                         # 届けた時刻
    stimuli: tuple[StimulusDeliveryResult, ...]   # 届けた順

@final
@dataclass(frozen=True)
class StimulusDeliveryResult:
    stimulus: StimulusDescription         # 種類 (Sense)、文 (はっきり知ったときの文の型)、場所、宛先
    perceived_by: tuple[PersonId, ...]    # 届いた
    kept_for: tuple[PersonId, ...]        # 起きてから知る形でためた
    missed_by: Mapping[PersonId, NotPerceivedReason]   # 届く見込みがあって届かなかった人と理由
```

- 届く見込みの無かった人 (`ELSEWHERE`、`NOT_OWN_BODY`、`NOT_ADDRESSED`) は、`missed_by` に残さない。刺激ごとに世界の全員が並ぶと、追いたい人が埋もれるため。どの理由を外すかは記録を作る側 (`PeopleReachedByStimuli`) が決める
- 居場所の無い人 (死んだ人、世界から外れた人) は、見える・聞こえる・他人の体の刺激では届く見込みが無かったので並ばない。外れたハルは扉の音の記録に並ばない
- 例: 広場でハルが扉を壊すと、記録には、見える刺激がハルとサヨに届き、音が広間のゲンに届き、坑道の奥のアキには音が「遠い」で届かず、サヨには音が「同じものをもう知った」で届かなかったことが残る

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

音の届き方は、出来事が確定した後の通路の状態で計算する (扉を開けた音は、開いた扉を通る)。`HearingValues` は `WorldRules` にある ([world_design.md](world_design.md))。聞こえる刺激で人が分かるのは声 (話す) だけ。物音の文の人のプレースホルダーはいつも `Unidentified`。ささやきは、鳴った場所にいる宛先にははっきり、同じ場所のほかの人には、去った人も含めてかすかに届く。かすかなときの文はくぐもったときと同じ (`muffled` を `unidentified()` で当てる)。「N 名に届いた」も同じ計算で数え、倒れている人は入れない。

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
    passages: tuple[ContainedPassage, ...]
    sections: tuple[SpotSectionDeclaration, ...]
    objects: tuple[ContainedObject, ...]
    ground_items: tuple[ItemInstanceId, ...]
    people: tuple[PresentPerson, ...]
    bodies: tuple[PresentPerson, ...]

@final
@dataclass(frozen=True)
class ContainedObject:                    # 現れているかも持つ。隠れた物を場面から外すのは seen_with
    declaration: ObjectDeclaration
    revealed: bool
    look: DescriptionText | NoLook        # ユースケースが集めるときに WorldDesign.looks_of(物).look_now で決める (#2067、#2070)

@final
@dataclass(frozen=True)
class SeenObject:
    declaration: ObjectDeclaration
    look: DescriptionText | NoLook        # 場面には説明に続けてこの文を出す (「北の坑道の水門: 鉄の水門。開いていて、水の流れる音がする」)

@final
@dataclass(frozen=True)
class ContainedPassage:
    passage: PassageInState
    revealed: bool

@final
@dataclass(frozen=True)
class VisibleSurroundings:
    spot: SpotDeclaration
    sight: SightQuality
    shows_description: bool               # 真っ暗なら説明を出さず、音と気温だけ
    passages: tuple[PassageInState, ...]  # 真っ暗でも出す (手探りで分かる)
    sections: tuple[SpotSectionDeclaration, ...]
    objects: tuple[SeenObject, ...]
    ground_items: tuple[ItemInstanceId, ...]
    people: tuple[SeenPerson, ...]
    bodies: tuple[SeenPerson, ...]        # 倒れている人と死んだ人

    @classmethod
    def seen_with(cls, sight: SightQuality, contents: SpotContents) -> "VisibleSurroundings": ...
        # 現れていない物と通路 (hidden_until_revealed) は出さない。暗い・真っ暗では、暗くても見える物体 (seen_in_dark) だけ
        # 地面の品物と人の持ち物は SeesClearly のときだけ出す (暗いときは持ち物を出さない)。区画と通路は真っ暗でも出す (手探りで分かる)

    def perceived_by(self, viewer: PersonId, texts: SurroundingsTexts, at: WorldTick) -> tuple[Perceived, ...]: ...
        # 場面の人と倒れた体を、SurroundingsTexts.scene_as_seen の 1 つの文にした見える知覚。人も倒れた体もいなければ空 (#2154)
```

- 見渡す (`LookAround`) と、見渡す人のいる場所の場面を返す。見渡す本人は場面の人に入れない。去った人 (`DepartedPerson`) は誰の場面にも出さない。倒れた体は、その場所の体 (`PersonBody`) のうち倒れた人と死んだ人。去った人が見渡すと、明るさに関わらず `SeesClearly` で見る。移動中の人、倒れている人、去った人として動かない世界の死んだ人には場面が無い (`NothingInView`) (#2154)
- モンスター (`SeenMonster`) は [monster.md](monster.md)。遠くの場所が見える仕組み (`DistantSight`) は #2040 で決めてから足す
- 持ち物、体の状態、時刻は、見えているものではなく自分が知っていること。場面に入れず、知覚を通さずに集約から読む。複数の集約にまたがるものはドメインサービスにする
- 場面は「何が見えるか」だけを持つ。「何ができるか」は `AvailableActions` ([action.md](action.md)) が持ち、行為の対象の候補は場面に出ているものに限る
- 人が着いたことは、行為ではなく `OccupantEnteredSpotEvent` から、`BuiltInActionPerceptions.arrival` の文で、着いた場所にいた人へ刺激を作る。文には `{origin}` (来た場所の名前) を書ける。着いた本人には届けない (本人には場面が渡る) (#2061)
- 話すことは、声の大きさ (`Whisper` / `OrdinaryVoice` / `Shout`) ごとの宣言 (`BuiltInActionPerceptions.speech`) で刺激を作る。音の大きさも、その宣言の `loudness` を使う (#2061)
- 品物の時間が切れて消えたこと (`ItemRanOutEvent`) は、持っていた本人には本人の体の刺激、地面にあったときはその場所の見える刺激として、`Lasts.ended_text` で作る。暗くなったことは `DeliverDarkeningHandler` が別に届ける (#2068)
- 着いたとき、起き上がったとき、その場所の明るさが上がったとき (灯した、夜が明けた、明かりを持った人が来た) は、場面の人、倒れた体、モンスターを 1 つの観測にして渡す (`DeliverSurroundings`)。明るさが上がったかは、出来事の前後の `LightingConditions` を比べて決める
- 場面の観測は、いる側の文だけを people_here、bodies_here の順につなぐ。人も倒れた体もいなければ (真っ暗も含む) 観測を出さない。品質は見え方 (`SeesClearly` / `SeesShapes`) のまま、目立つ知らせにはしない (#2154)
- 起き上がった人には、「目が覚めた」(`SurroundingsTexts.waking`、本人の体の刺激、目立つ) → たまった知らせ (ためた順、`NoticedOnWaking`、目立たない) → 場面 の順に渡す。たまった知らせも目が覚めた時刻の観測にする。Being の短期記憶は同じ環境の観測を時刻で安定に並べ直すので、倒れている間の時刻で渡すと「目が覚めた」より前に記憶に入るため。いつ起きたかは作者の `noticed_later` の文が表す (#2154)
