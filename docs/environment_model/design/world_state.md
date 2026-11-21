# 世界の状態 (集約)

集約は自分の ID を持つ。人ごと・物体ごと・品物ごと・場所ごとの集約は、その `PersonId`、`ObjectId`、`ItemInstanceId`、`SpotId` を持つ。世界に 1 つの集約 (`Whereabouts`、`WorldClock` など) は、その世界の `WorldId` を持つ。一時的な遊びの世界が並ぶことがあり、snapshot でもどの世界の状態かを区別するため。

```python
Occupant = PersonBody | DepartedPerson | MonsterBody
# PersonBody(person): 生きている人と、倒れた人・死んだ人の体 / DepartedPerson(person): 死んで去った人 (体は無い)
# MonsterBody(monster)。1 人の人は、死んで去ると PersonBody と DepartedPerson の 2 つの居場所を持つ

@final
@dataclass(frozen=True)
class AtSpot:
    spot: SpotId
    section: SpotSectionId | OpenArea      # OpenArea は区画の外

@final
@dataclass(frozen=True)
class TravelInProgress:
    route: Route
    passage_index: int
    ticks_left_on_passage: Ticks
    departed_from: SpotId

Location = AtSpot | TravelInProgress


class Whereabouts:                                # 世界に 1 つ
    def place(self, occupant: Occupant, spot: SpotDeclaration) -> None: ...
    def remove(self, occupant: Occupant) -> None: ...
    def place_departed(self, person: PersonId, departed_persons_act: bool) -> None: ...
        # 去った人の動く世界でだけ、死んだ人の体のある場所の区画の外に DepartedPerson を置く。体が移動の途中なら、今の区間の出発点 (departed_from) に置く (#2151)
    def start_travel(self, occupant: Occupant, route: Route) -> None: ...
    def advance_travels(self, closed_passages: frozenset[PassageId], now: WorldTick) -> None: ...
        # 1 tick ぶん進める。今の区間の通路が閉じていれば、その区間の出発点 (departed_from) に戻って止まる (TravelBlockedEvent)
        # 次の区間に差しかかったときも同じ tick の中で確かめる。travel_ticks が 0 の区間は時間を使わない
    def cancel_travel(self, occupant: Occupant, now: WorldTick) -> None: ...      # departed_from に戻る
    def teleport(self, occupant: Occupant, spot: SpotDeclaration, now: WorldTick) -> None: ...
    def enter_section(self, occupant: Occupant, section: SpotSectionDeclaration, not_counted: frozenset[PersonId]) -> None: ...
        # その場所にいるときだけ。満員ならドメイン例外。定員に数えるのは Alive の人と去った人
        # 倒れた人と死んだ人の体は数えない。Whereabouts は生死を知らないので、その人たちをユースケースが PersonVitals から集めて not_counted に渡す
        # 別の区画にいれば、そこから出て入る
    def leave_section(self, occupant: Occupant) -> None: ...
        # 移動を始める・テレポートすると、区画からも出る

    def location_of(self, occupant: Occupant) -> Location: ...
    def occupants_at(self, spot: SpotDeclaration) -> tuple[Occupant, ...]: ...
    def are_together(self, actor: Occupant, target: Occupant) -> bool: ...
    def is_at(self, occupant: Occupant, spot: SpotDeclaration) -> bool: ...
    def is_in_section(self, occupant: Occupant, section: SpotSectionDeclaration) -> bool: ...
    def can_reach(self, occupant: Occupant, obj: ObjectDeclaration, sections: tuple[SpotSectionDeclaration, ...]) -> bool: ...
        # 区画の reachable_objects に入っている物は、その区画の中からだけ届く


@final
@dataclass(frozen=True)
class Alive: ...

@final
@dataclass(frozen=True)
class Down:
    fell_at: WorldTick
    cause: FallCause

@final
@dataclass(frozen=True)
class Dead:
    died_at: WorldTick

LifeState = Alive | Down | Dead

FallCause = StruckByPerson | StruckByMonster | Starvation | WorldHappening
# StruckByPerson(person: PersonId) / StruckByMonster(monster: MonsterId) / Starvation: 飢えの痛手 / WorldHappening: 出来事 (どの出来事かは、出来事の宣言ができたら持たせる)

@final
@dataclass(frozen=True)
class StatusEffect:
    kind: StatusEffectType                  # 空でない種類の名前。毎 tick 何をするかはまだ決めていない
    expires_at: WorldTick                   # この tick に達したら外れる


class PersonVitals:                                 # 人ごと。体力 (HP) を持ち、0 になると Down
    @classmethod
    def start(cls, person: PersonId, hp: HitPoints) -> "PersonVitals": ...
        # Alive、空腹と疲れは 0 で始まる。HP 0 では始められない。最大 HP をどの宣言に書くかはまだ決めていない
    # 状態を変える操作は Alive の人だけ受ける (Down・Dead ならドメイン例外)。revive だけは Down の人だけ受ける
    def take_damage(self, amount: Damage, now: WorldTick, cause: FallCause) -> None: ...   # FallCause: 殴られた、飢え、出来事 など
    def heal(self, amount: HealAmount) -> None: ...
    def revive(self, hp_rate: Rate, now: WorldTick) -> None: ...   # HP は最大 × hp_rate を切り捨て、1 は戻す
    def pass_time(self, now: WorldTick, death: DeathRule, hunger: HungerRule) -> None: ...
        # 倒れてから death.grace が過ぎたら Dead (Down.fell_at から数える。別のタイマーは持たない)
        # 起きているあいだだけ空腹を進め、限界のあいだは飢えの痛手 (PersonDamagedEvent)。段階が変わったら HungerLevelChangedEvent
        # 世界から外れた人には呼ばない (PassWorldTime が PersonOutcomes.people_in_world の人にだけ呼ぶ)。外れた人の体は止まり、死なない (D2211)
    def add_status_effect(self, effect: StatusEffect) -> None: ...
    def remove_expired_status_effects(self, now: WorldTick) -> None: ...
    def satisfy_hunger(self, amount: HungerAmount, rule: HungerRule) -> None: ...   # 段階が変わったら HungerLevelChangedEvent
    def exert(self, rule: FatigueRule) -> None: ...      # 段階が変わったら FatigueLevelChangedEvent
    def rest(self, amount: FatigueAmount, rule: FatigueRule) -> None: ...   # 段階が変わったら FatigueLevelChangedEvent
    def start_action(self, until: WorldTick) -> None: ...   # 行っているあいだは、話す以外の行為を断る (Busy)。PersonBecameBusyEvent
    def start_acting(self, exertion: Exertion, until: WorldTick, rule: FatigueRule) -> None: ...   # 疲れさせ、start_action。行っている最中に始めた行為 (話すこと) は、いまの行為の終わりを早めない
    def is_busy(self, now: WorldTick) -> bool: ...
    def hp(self) -> HitPoints: ...
    def hunger(self) -> HungerAmount: ...
    def fatigue(self) -> FatigueAmount: ...

    def can_act(self) -> bool: ...
    def is_dead(self) -> bool: ...
    def life_state(self) -> LifeState: ...
    def occupant_in_world(self, departed_persons_act: bool) -> Occupant: ...
        # 去った人が動く世界で体が死んでいれば DepartedPerson、それ以外は PersonBody。人の居場所を問う条件と効果はこれで見分ける
    def fatigue_reached_limit(self, rule: FatigueRule) -> bool: ...


class PeopleRegister:                             # 世界に 1 つ。人の番号・名前・見た目の名簿
    @classmethod
    def from_characters(cls, world: WorldId, characters: Sequence[CharacterDeclaration]) -> "PeopleRegister": ...
        # 世界の始まりに、登場人物の宣言の順で番号 (PersonHandle) を 0 から振る。番号は人ごとに変わらず、snapshot に残る
    def name(self, person: PersonId, name: DisplayName) -> None: ...
        # Being が世界に入るときに渡す名前 (BeingAttachment の表示の名前) を記録する。世界は名前を宣言から持たない (D1928-3)
        # 名前を記録したら PersonNamedEvent。同じ名前をもう一度記録するのは、状態が変わらないので何もしない
        # 記録済みの人を違う名前で記録し直すのは断る (ドメイン例外)。改名は今のモデルに無い出来事で、要るなら改名の操作として別に設計する (#2045)

    def handle_of(self, person: PersonId) -> PersonHandle: ...
    def name_of(self, person: PersonId) -> DisplayName: ...
        # 名前を記録していない人は断る (ドメイン例外)。登場人物はみな Being が動かすので、名前が無いのは配線の誤り (#2045)
    def appearance_of(self, person: PersonId) -> DescriptionText: ...


class PersonOutcomes:                             # 世界に 1 つ
    def decide(self, person: PersonId, outcome: Outcome) -> None: ...
        # 一度決まった結末は変えない (二度目はドメイン例外)。結末が決まった人はもう行為をしない (ActorCannotAct)。
        # Died 以外の人は、体と持ち物ごと世界から外れる (Whereabouts.remove)。Died の人は departed_persons_act なら去った人として動く

Outcome = Died | DeclaredOutcome            # DeclaredOutcome(outcome: OutcomeDeclaration)。死だけは組み込み

    def outcome_of(self, person: PersonId) -> Outcome | Undecided: ...
    def all_decided(self) -> bool: ...
    def undecided_people(self) -> tuple[PersonId, ...]: ...
    def has_left_the_world(self, person: PersonId) -> bool: ...
        # 作者の結末 (DeclaredOutcome) が決まった人は世界から外れている。Died の人は外れない
    def people_in_world(self) -> tuple[PersonId, ...]: ...
        # 外れていない人を、世界の始まりに渡した順で。外れた人は体も荷の品物も時間が止まる (D2211)


class GroupMembership:                            # 世界に 1 つ
    def join(self, person: PersonId, group: GroupDeclaration) -> None: ...
    def leave(self, person: PersonId, group: GroupDeclaration) -> None: ...
        # 分け方ごとに 1 つの集団にだけ入る。別の集団へ移るときは leave してから join。所属が変わらない分け方 (changes が偽) への出入りはドメイン例外

    def is_member(self, person: PersonId, group: GroupDeclaration) -> bool: ...
    def members_of(self, group: GroupDeclaration) -> frozenset[PersonId]: ...
    def group_of(self, person: PersonId, grouping: GroupingDeclaration) -> GroupId | NotInAnyGroup: ...


class WorldClock:                                 # 世界に 1 つ。time_of_day は昼夜を宣言した世界だけ
    def advance(self, day_night: DayNightDeclaration | NoDayNight, facts: WorldFacts) -> None: ...   # 時間帯が変わったら、facts で知らせの相手を選んで TimeOfDayChangedEvent に載せる (D2203)

    def now(self) -> WorldTick: ...
    def time_of_day(self, day_night: DayNightDeclaration) -> TimeOfDay: ...


StateValue = FlagValue | CountValue | ChoiceValue | StockValue | WrittenText | NothingWritten

class ObjectState:                                # 物体ごと
    @classmethod
    def from_declaration(cls, declaration: ObjectDeclaration, now: WorldTick) -> "ObjectState": ...
        # 在庫は refills_every ごとに 1 つ戻り、capacity で止まる。from_declaration・set・take_from_stock の now から数え、満杯でなければ端数を持ち越す
        # 戻った分は読むときに数えるので、イベントは出さない。次の take_from_stock の before に戻った量が出る

    def set(self, key: ObjectStateKeyDeclaration, value: StateValue, now: WorldTick) -> None: ...   # 在庫の鍵は、値が変わるとき now から数え直す
    def add_to_count(self, key: ObjectStateKeyDeclaration, amount: Count) -> None: ...
    def subtract_from_count(self, key: ObjectStateKeyDeclaration, amount: Count) -> None: ...   # 0 を下回るならドメイン例外
    def take_from_stock(self, key: ObjectStateKeyDeclaration, amount: Count, now: WorldTick) -> None: ...
    def write_text(self, key: ObjectStateKeyDeclaration, body: TextBody, author: PersonId, now: WorldTick) -> None: ...
    def reveal(self) -> None: ...

    def value_of(self, key: ObjectStateKeyDeclaration, now: WorldTick) -> StateValue: ...
    def is_revealed(self) -> bool: ...


class GroundItems:                                # 場所ごと
    def place(self, item: ItemInstanceId) -> None: ...
    def take(self, item: ItemInstanceId) -> None: ...

    def items(self) -> tuple[ItemInstanceId, ...]: ...
    def contains(self, item: ItemInstanceId) -> bool: ...


class SpotSearchProgress:                         # 場所ごと
    def record_search(self, searcher: PersonId) -> None: ...
    def mark_found(self, discoverable: DiscoverableDeclaration, finder: PersonId) -> None: ...

    def search_count(self, person: PersonId) -> Count: ...
    def is_found(self, discoverable: DiscoverableDeclaration, person: PersonId) -> bool: ...


class WorldFlags:                                 # 世界に 1 つ
    def raise_flag(self, flag: FlagDeclaration, trigger: Trigger) -> None: ...
    def lower_flag(self, flag: FlagDeclaration, trigger: Trigger) -> None: ...

    def is_raised(self, flag: FlagDeclaration) -> bool: ...


class PersonInventory:                            # 人ごと。持てる数の上限 (Capacity) を受けて作る
    def receive(self, item: ItemInstanceId, spec: ItemSpecId) -> None: ...   # 荷に入る。品物の種類も覚える
    def give_up(self, item: ItemInstanceId) -> None: ...         # 手の物でも荷の物でも
    def give_up_held(self, item: ItemInstanceId) -> None: ...    # 手の物だけ。荷の物ならドメイン例外 (手から奪う効果が、荷の物を奪わないため)
    def give_up_packed(self, item: ItemInstanceId) -> None: ...  # 荷の物だけ。手の物ならドメイン例外
    def hold(self, item: ItemInstanceId, hands_needed: HandsNeeded) -> None: ...
        # 荷から手に持つ。手は 2 本。足りなければ、今手に持っている物を先に持った順に荷にしまう
    def put_away(self, item: ItemInstanceId) -> None: ...
    def earn(self, amount: Gold) -> None: ...
    def pay(self, amount: Gold) -> None: ...
    def reserve(self, reservation: ReservationId, items: frozenset[ItemInstanceId], gold: Gold) -> None: ...
    def release_reservation(self, reservation: ReservationId) -> None: ...

    def items(self) -> tuple[ItemInstanceId, ...]: ...
    def held_items(self) -> tuple[ItemInstanceId, ...]: ...      # 起きている人を見る人に見えるのは、これだけ
    def packed_items(self) -> tuple[ItemInstanceId, ...]: ...
    def is_full(self) -> bool: ...                               # 手の物も数える
    def available_gold(self) -> Gold: ...
    def is_reserved(self, item: ItemInstanceId) -> bool: ...   # 取引に出した品は、ほかで使えない
    def count_of(self, spec: ItemSpecId) -> Count: ...
    def items_to_give_up(self, spec: ItemSpecId, count: Count) -> tuple[ItemInstanceId, ...]: ...
        # 荷から先に、足りなければ手からも選ぶ。持っている数が足りなければドメイン例外 (TakeItemEffect が 1 つも取らずに断るため)
    def random_packed_item(self, random: RandomSource) -> ItemInstanceId: ...
        # 荷の物から 1 つ選ぶ。荷が空ならドメイン例外。手の物は選ばない (見えているので ItemByArgument で指す)


class Item:                                       # 品物ごと。ItemInstanceId は空でない文字列
    @classmethod
    def come_into_world(cls, item_id: ItemInstanceId, spec: ItemSpecDeclaration, now: WorldTick) -> "Item": ...

    def set(self, key: ItemStateKeyDeclaration, value: StateValue) -> None: ...
    def leave_world(self) -> None: ...
    def run_out(self, now: WorldTick, where: CarriedBy | LyingAt) -> None: ...
        # 宣言の Lasts の時間が過ぎていなければ断る。過ぎていれば ItemRanOutEvent(item, spec_id, where, at) を出して世界から出る
        # どこにあったかは Item が知らないので、手放させたユースケースが渡す (CarriedBy(person) / LyingAt(spot))

    def has_run_out(self, now: WorldTick) -> bool: ...     # 世界にいて、宣言の Lasts の時間が過ぎたか。PassWorldTime が手放させる品物を選ぶのに使う
    def value_of(self, key: ItemStateKeyDeclaration) -> StateValue: ...
    def age(self, now: WorldTick) -> Ticks: ...
    def gives_light(self) -> bool: ...


class PassageStates:                              # 世界に 1 つ
    def change_state(self, passage: PassageDeclaration, new_state: PassageStateName) -> None: ...
    def reveal(self, passage: PassageDeclaration) -> None: ...     # 道が現れる (扉を開けるのは change_state)
    def remove(self, passage: PassageDeclaration) -> None: ...     # 道が無くなる

    def is_traversable(self, passage: PassageDeclaration) -> bool: ...
    def closed_passages(self) -> frozenset[PassageId]: ...         # 通れない状態の道、現れる前の道 (PassageDeclaration.hidden_until_revealed)、無くなった道
    def passages_from(self, spot: SpotDeclaration, declared: tuple[PassageDeclaration, ...]) -> tuple[PassageId, ...]: ...
        # その場所から出られる今ある道。閉じた扉も入れる。片道は ends の前の端からだけ
    def in_state(self, passage: PassageDeclaration) -> PassageInState: ...


class SpotAtmospheres:                            # 世界に 1 つ。場所ごとに今の SpotAtmosphere を持つ (初めは宣言の値)
    def change(self, spot: SpotDeclaration, atmosphere: SpotAtmosphere) -> None: ...

    def atmosphere_of(self, spot: SpotDeclaration) -> SpotAtmosphere: ...


class Weather:                                    # 世界に 1 つ (天候を宣言した世界だけ)
    def change(self, new_state: WeatherState) -> None: ...
    def pass_time(self, now: WorldTick, declaration: WeatherDeclaration, random: RandomSource) -> None: ...
        # declaration.weather_after が選んだ天候へ change する。同じ天候なら何も出さない

    def current(self) -> WeatherState: ...


class ScenarioProgress(AggregateRoot[HappeningFiredEvent | ReactionFiredEvent | JointActionCompletedEvent | JointActionTimedOutEvent]):   # 世界に 1 つ
    def note_happening_fired(self, happening: HappeningDeclaration, now: WorldTick, audience: frozenset[PersonId], refusal: RefusalCode | NoRefusal) -> None: ...
        # HappeningFiredEvent を出す。断られた発火 (refusal が RefusalCode) は相手を空にして載せる
    def note_reaction_fired(self, reaction: ReactionDeclaration, truth: bool, now: WorldTick, refusal: RefusalCode | NoRefusal) -> None: ...
        # 新しい真偽を記録し、ReactionFiredEvent を出す
    def note_reaction_truth(self, reaction: ReactionDeclaration, truth: bool) -> None: ...
        # 発火しなかった反応の真偽を記録する。イベントは出さない

    def may_fire(self, happening: HappeningDeclaration, now: WorldTick) -> bool: ...
        # once の出来事は一度起きたら偽。once でなくても、同じ tick にすでに起きていたら偽
    def reaction_changed(self, reaction: ReactionDeclaration, truth: bool) -> bool: ...
        # 一度も note_reaction_truth していない反応は偽。世界の始まりには何も変わっていないので、最初に見た真偽は記録するだけで変わり目にしない
        # 例: 最初から閉じている扉の「閉じたら知らせる」反応は、tick 0 では知らせず、一度開いてまた閉じたときに初めて知らせる
    def last_fired_at(self, happening: HappeningId) -> WorldTick | NeverFired: ...

    # 二人で合わせる操作の帳簿 (D2173)。操作ごとに JointActionProgress (最初の一押しの tick と、部分ごとに最後に行った人) を持つ
    def note_joint_action_part_done(self, attempt: ActionAttempt, joints: Iterable[JointActionDeclaration], now: WorldTick) -> None: ...
        # どの宣言のどの部分に当たるかは帳簿が attempt.operates(物体, 操作) で決める。同じ部分は後の人で上書きし、窓の起点は動かさない
        # 揃いか時間切れが落ち着いていない操作に書くと JointActionUnsettledException。イベントは出さない
    def joint_action_settlement(self, joint: JointActionDeclaration, now: WorldTick) -> JointActionSettlement: ...
        # 全部の部分が埋まり、distinct_people なら覚えている人が全員違えば COMPLETED。最初の一押し + window を過ぎたら TIMED_OUT。ほかは UNDECIDED
        # 当てる効果は JointActionSettlement.effect_in(joint) が選ぶ (on_complete / on_timeout)
    def note_joint_action_settled(self, joint: JointActionDeclaration, now: WorldTick, audience: frozenset[PersonId], refusal: RefusalCode | NoRefusal) -> None: ...
        # JointActionCompletedEvent か JointActionTimedOutEvent を出し、帳簿を空に戻す。断られたら相手を空にして載せる
        # 空に戻すので、1 回の落ち着かせで同じ操作は揃いか時間切れのどちらか 1 回まで。UNDECIDED のときは JointActionNotSettlingException


class Monster: ...                                # 個体ごと。操作と振る舞いは monster.md

class SoundsThisTick: ...                         # 世界に 1 つの帳簿。monster.md

class MonsterSpawnRecords: ...                    # 世界に 1 つの帳簿。湧きの真偽の変わり目と、倒された記録。monster.md


class WorldStage:                                 # 世界に 1 つ (WorldStage を宣言した世界だけ)
    def enter(self, stage: WorldStageDeclaration, now: WorldTick) -> None: ...

    def current(self) -> WorldStageId: ...
    def entered_at(self) -> WorldTick: ...
    def declaration_in(self, nouns: DeclaredNouns) -> WorldStageDeclaration: ...
        # 今の段階の宣言。段階の無い世界の NoWorldStages も declaration_in で自分自身を返し、allows / allows_interaction でどの行為も許すと答える
        # 共通の前提は attempt.is_allowed_in(facts.world_stage().declaration_in(facts.nouns())) と、段階の有無を見分けずに尋ねる


class GroupDecision:                              # 集団の決定の宣言ごとに 1 つ
    def start(self, voters: frozenset[PersonId], choices: frozenset[PersonId]) -> None: ...
    def cast(self, voter: PersonId, choice: VoteFor | Abstain) -> None: ...
        # voters にいない人の票、二度目の票、choices にいない人への票はドメイン例外
        # 全員が投じたら、ここで集計する
    def withdraw_voter(self, voter: PersonId) -> None: ...   # 残りが全員投じ済みなら、ここで集計する。死んだ人は withdraw_choice を先に呼ぶ
    def withdraw_choice(self, choice: PersonId) -> None: ...  # その人に入っていた票は投じた人に戻り、投じ直せる
    def withdraw_person(self, person: PersonId, life_state: LifeState) -> None: ...
        # 倒れた人・死んだ人を外す。Dead は withdraw_choice のあと withdraw_voter、Down は withdraw_voter だけ、Alive は何もしない
        # 倒れた同じ確定で死ぬこともあるので、外し方はイベントの種類ではなく確定したいまの体の状態で決める (#2151)
    def close(self) -> None: ...                              # それまでの票で集計する
        # 集計: 最多が 1 人で、棄権より多ければ GroupDecisionReachedEvent(chosen)。それ以外は GroupDecisionUnresolvedEvent
        # どちらも票の内訳を持つ。reveals_ballots なら、変換役が投票する人の全員への世界の知らせにする

    def is_open(self) -> bool: ...
    def ballot_choices_for(self, voter: PersonId, people: tuple[PersonId, ...]) -> tuple[VoteFor | Abstain, ...]: ...
        # 開いていて voter が投票する人なら、people の順に選ばれうる人への票、abstain_allowed なら最後に棄権。それ以外は空
    def ballot_refusal(self, voter: PersonId, choice: VoteFor | Abstain) -> WorldRefusal | None: ...
        # cast が断るときに投げる例外。cast と一覧 (action.md) が同じ判断を使う


class MissedNotices:                              # 人ごと。倒れている間にためる帳簿で、イベントを出さない (AggregateRoot を継承しない)
    def keep(self, notice: MissedNotice) -> None: ...
    def clear(self) -> None: ...

    def notices(self) -> tuple[MissedNotice, ...]: ...



class WorldEnding:                                # 世界に 1 つ
    def end(self, now: WorldTick) -> None: ...      # SettleWorldConditions の終わりの判定が呼ぶ。WorldEndedEvent
        # 終わった世界への end はドメイン例外 (状態が変わらない操作は断らない、の例外)。終わった世界はもう進まず、終わりの判定は 1 tick に 1 回しか呼ばれないので、二度目の end は呼ぶ側の誤りを示す

    def has_ended(self) -> bool: ...


class LatestActions:                              # 世界に 1 つ
    def note(self, attempt: ActionAttempt, situation: ActorSituation, now: WorldTick) -> None: ...   # PersonActedEvent(attempt, at_spot, actor_as, item_specs, at)
    def note_failed_attempt(self, refusal: ActionRefusal, situation: ActorSituation, now: WorldTick) -> None: ...   # ActionAttemptFailedEvent(refusal, at_spot, actor_as, item_specs, at) を出すだけで、last_done_at は変えない

@final
@dataclass(frozen=True)
class ActorSituation:                     # 世界を変える前の、行う人の状況。変換役が刺激を作るのに使う (#2146)
    at_spot: SpotId | NotAtSpot           # 移動では出発した場所。移動中なら NotAtSpot
    actor_as: Occupant                    # PersonBody か DepartedPerson
    item_specs: Mapping[ItemInstanceId, ItemSpecId]   # 試みが扱う品物ごとの種類。使い切る品物も、世界に残っているうちに読む

    def last_done_at(self, who: PersonId | Anyone, action: ActionKind | InteractionId) -> WorldTick | NeverDone: ...
        # note は attempt.done_as() の鍵ごとに、行った人と Anyone の両方へ時刻を記録する
```

## ドメインイベント

```python
OccupantPlacedEvent, OccupantRemovedEvent, TravelStartedEvent, OccupantLeftSpotEvent,
OccupantEnteredSpotEvent, TravelBlockedEvent, TravelCancelledEvent, OccupantTeleportedEvent,
OccupantEnteredSectionEvent, OccupantLeftSectionEvent

PersonDamagedEvent, PersonFellEvent, PersonRevivedEvent, PersonDiedEvent, PersonHealedEvent,
StatusEffectAddedEvent, StatusEffectExpiredEvent, HungerLevelChangedEvent, FatigueLevelChangedEvent, PersonBecameBusyEvent

PersonOutcomeDecidedEvent
PersonJoinedGroupEvent, PersonLeftGroupEvent
WorldTickAdvancedEvent, TimeOfDayChangedEvent
ObjectStateChangedEvent, ObjectRevealedEvent, TextWrittenEvent
ItemStateChangedEvent, ItemCameIntoWorldEvent, ItemLeftWorldEvent, ItemRanOutEvent
ItemReceivedEvent, ItemGivenUpEvent, ItemHeldEvent, ItemPutAwayEvent, GoldEarnedEvent, GoldPaidEvent, ItemsReservedEvent, ReservationReleasedEvent
GroundItemPlacedEvent, GroundItemTakenEvent
SpotSearchedEvent, DiscoverableFoundEvent
WorldFlagRaisedEvent, WorldFlagLoweredEvent
PassageStateChangedEvent, PassageRevealedEvent, PassageRemovedEvent
SpotAtmosphereChangedEvent
WorldStageChangedEvent
WorldEndedEvent
WeatherChangedEvent
MonsterSpawnedEvent, MonsterDamagedEvent, MonsterDiedEvent, MonsterStateChangedEvent, MonsterLeftWorldEvent
GroupDecisionStartedEvent, BallotCastEvent, VoterWithdrawnEvent, ChoiceWithdrawnEvent,
GroupDecisionReachedEvent, GroupDecisionUnresolvedEvent
PersonActedEvent, ActionAttemptFailedEvent
```

- `TimeOfDayChangedEvent` は、時間帯の知らせの相手 (`audience`) を載せる。刺激に変える役は世界を読まないので、変わった時点で選んでおく (D2203)
- 前後の値で反応するハンドラのために、状態の変化のイベントは変わる前と後の値を持つ (`ItemStateChangedEvent`、`WeatherChangedEvent`、`TimeOfDayChangedEvent`、`SpotAtmosphereChangedEvent`)
- `ItemHeldEvent` / `ItemPutAwayEvent` / `ItemGivenUpEvent` は持ち主と品物を持つ。`PersonInventory` は持ち主の場所を知らないので、場所は受けるハンドラが `Whereabouts` で引く。`ItemGivenUpEvent` は、手に持っていたかも持つ (手放したあとでは引けないため)
- 状態が変わらない操作 (同じ値への `set`、現れている物の `reveal`、手にある物の `hold` など) は、断らず、イベントも出さない。断ると `CommandScope` ごと巻き戻り、同じ効果を当て直す出来事や反応が全体を止めるため
- 行為の記録 (`LatestActions` の `note` / `note_failed_attempt`) は、状態が変わらなくてもイベントを出す。行為が起きたこと、断られたことそのものを知らせるため (知覚は `PersonActedEvent` / `ActionAttemptFailedEvent` から刺激を作る)
- 世界を表す集約は、状態を変えたら必ずイベントを出す。帳簿の集約 (`ScenarioProgress`、`MissedNotices`) は見張りの外に置く。`ScenarioProgress` は発火と二人で合わせる操作の揃い・時間切れの記録だけイベントを出し (知らせと trace の出口、#2145、D2173)、発火しなかった反応の真偽と、部分を行ったことの記録では出さない。漏れはアーキテクチャのテストで見張る
- 空腹と疲れは、段階 (`HungerRule.levels` / `FatigueRule.levels`) が変わったときだけイベントにする
- 場所に着いたこと (`OccupantEnteredSpotEvent`) は、来た場所 (`origin`) と着いた時刻 (`at`) を持つ。来た場所は最後に歩き切った区間の出発点。区間を歩き切る前に通路が閉じて引き返したときや移動をやめたときは、歩いていた区間の向こうの端になる。teleport では `Teleported`。arrival の文の `{origin}` を、確定したあとの世界から読まずに埋めるため (#2152)
- 移動 (`Whereabouts.advance_travels`) は、着いたとき (`OccupantEnteredSpotEvent`) と止められたとき (`TravelBlockedEvent`) だけイベントにする。道の途中で残りの tick が減ること、途中の場所を通り過ぎることはイベントにしない。tick ごとに出すと、何も起きていない知らせがハンドラと観測に流れるため。見張りのテスト (`tests/architecture/test_world_aggregates_emit_events.py`) もこの例外を持つ
