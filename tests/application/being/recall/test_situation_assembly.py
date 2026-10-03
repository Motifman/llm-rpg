"""assemble_situation が、観測の契約とエージェントの持ち物だけから状況の 6 つの欄を組み立てる挙動を保証する。"""

from __future__ import annotations

from ai_rpg_world.application.being.recall.situation import SituationField
from ai_rpg_world.application.being.recall.situation_assembly import (
    AgentHoldings,
    assemble_situation,
)
from ai_rpg_world.being.contract import (
    UNKNOWN,
    EnvironmentNotice,
    Observation,
    ObservedTime,
    OwnActionResult,
    OwnBodyState,
    SeenOrHeard,
    ToldOrWritten,
)

NO_HOLDINGS = AgentHoldings()


def _obs(
    body: str,
    *,
    route=None,  # type: ignore[no-untyped-def]
    place="干潟",  # type: ignore[no-untyped-def]
    subject_name=UNKNOWN,  # type: ignore[no-untyped-def]
    subject_is_self: bool = False,
    source=UNKNOWN,  # type: ignore[no-untyped-def]
) -> Observation:
    return Observation(
        body=body,
        route=route if route is not None else SeenOrHeard(),
        time=ObservedTime(display="朝"),
        subject_is_self=subject_is_self,
        subject_name=subject_name,
        source=source,
        place=place,
        addressed_to_self=UNKNOWN,
    )


class TestPlace:
    """場所の欄が、観測の場所の欄だけから決まることを保証する。"""

    def test_place_is_the_newest_known_place(self) -> None:
        """場所は、場所が分かっている観測のうち最も新しいものの場所になる。"""
        observations = [
            _obs("霧が出た", place=UNKNOWN),
            _obs("波が寄せた", place="干潟"),
            _obs("鳥が鳴いた", place="森"),
        ]

        situation = assemble_situation(observations, NO_HOLDINGS)

        assert situation.place == ("干潟",)

    def test_place_is_empty_when_no_observation_knows_it(self) -> None:
        """どの観測も場所を知らなければ、場所の欄は空になる。"""
        situation = assemble_situation([_obs("霧が出た", place=UNKNOWN)], NO_HOLDINGS)

        assert situation.place == ()


class TestCounterpart:
    """相手の欄が、自分以外の主体の名前と、言った・書いた人の名前から決まることを保証する。"""

    def test_counterparts_are_other_subjects_and_speakers_newest_first_without_duplicates(self) -> None:
        """相手は、自分以外の主体の名前と、言われた・書かれていた観測の情報源を、新しい順に重複なく並べる。"""
        observations = [
            _obs("トムが手を振った", subject_name="トム"),
            _obs("「北へ行こう」", route=ToldOrWritten(), subject_name="ミナ", source="ミナ"),
            _obs("トムが走った", subject_name="トム"),
        ]

        situation = assemble_situation(observations, NO_HOLDINGS)

        assert situation.counterpart == ("トム", "ミナ")

    def test_self_and_seen_sources_are_not_counterparts(self) -> None:
        """自分が主体の観測と、見た・聞いた観測の情報源 (自分) は相手に入らない。"""
        observations = [
            _obs("アリスは石を拾った", subject_name="アリス", subject_is_self=True, source="アリス"),
        ]

        situation = assemble_situation(observations, NO_HOLDINGS)

        assert situation.counterpart == ()


    def test_own_writing_is_not_a_counterpart(self) -> None:
        """本人が書いた・言った観測の情報源 (本人) は相手に入らない。"""
        observations = [
            _obs(
                "アリスは掲示板に書いた",
                route=ToldOrWritten(),
                subject_name="アリス",
                subject_is_self=True,
                source="アリス",
            ),
        ]

        situation = assemble_situation(observations, NO_HOLDINGS)

        assert situation.counterpart == ()


class TestOwnStateAndHappening:
    """自分の体の状態と、いま起きたことの欄が、観測の経路で分かれることを保証する。"""

    def test_own_body_state_goes_to_own_state_not_happening(self) -> None:
        """経路が自分の体の状態の観測は自分の状態の欄に入り、いま起きたことには入らない。"""
        observations = [
            _obs("お腹が空いてきた", route=OwnBodyState()),
            _obs("潮が満ちてきた"),
        ]

        situation = assemble_situation(observations, NO_HOLDINGS)

        assert situation.own_state == ("お腹が空いてきた",)
        assert situation.happening == ("潮が満ちてきた",)

    def test_happening_takes_the_newest_three_including_own_action_results(self) -> None:
        """いま起きたことは、自分の行動の結果を含めて新しい順に 3 件までを取る。"""
        observations = [
            _obs("流木を拾えた", route=OwnActionResult(call_id="c1", succeeded=True)),
            _obs("雨が降り出した", route=EnvironmentNotice()),
            _obs("トムが来た", subject_name="トム"),
            _obs("鳥が鳴いた"),
        ]

        situation = assemble_situation(observations, NO_HOLDINGS)

        assert situation.happening == ("流木を拾えた", "雨が降り出した", "トムが来た")


class TestHoldings:
    """やろうとしていることと未解決のことの欄が、エージェントの持ち物から決まることを保証する。"""

    def test_goal_and_inner_thought_go_to_intent(self) -> None:
        """目的と直前の内心は、やろうとしていることの欄に、目的を先にして入る。"""
        holdings = AgentHoldings(goal="島から出る", inner_thought="まず火を起こしたい")

        situation = assemble_situation([], holdings)

        assert situation.intent == ("島から出る", "まず火を起こしたい")

    def test_open_expectations_go_to_unresolved_only(self) -> None:
        """清算待ちの予期は未解決の欄にだけ入り、やろうとしていることには入らない。"""
        holdings = AgentHoldings(open_expectations=("トムが麦束を焼いてくれる",))

        situation = assemble_situation([], holdings)

        assert situation.unresolved == ("トムが麦束を焼いてくれる",)
        assert situation.intent == ()

    def test_unresolved_takes_the_newest_three_expectations(self) -> None:
        """清算待ちの予期は古い順に渡され、新しいものから 3 件だけを未解決の欄に入れる。"""
        holdings = AgentHoldings(open_expectations=("一", "二", "三", "四"))

        situation = assemble_situation([], holdings)

        assert situation.unresolved == ("四", "三", "二")

    def test_blank_holdings_are_left_out(self) -> None:
        """空白だけの目的・内心・予期は欄に入れない。"""
        holdings = AgentHoldings(goal=" ", inner_thought="", open_expectations=("  ",))

        situation = assemble_situation([], holdings)

        for field in (SituationField.INTENT, SituationField.UNRESOLVED):
            assert situation.texts(field) == ()
