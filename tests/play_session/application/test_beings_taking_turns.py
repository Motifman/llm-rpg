from __future__ import annotations

from typing import Any

from ai_rpg_world.being.application.choose_action import (
    ActionChoosingCompletion,
    ActionChoosingReply,
    ToolCallReply,
)
from ai_rpg_world.being.contract import OwnActionResult
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.short_term_memory import Attempt, ObservedOutcome
from ai_rpg_world.being.infrastructure.scripted_action_choosing import ScriptedActionChoosing
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.trigger import WorldConditionsSettling
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    FlagId,
    ItemSpecId,
    ObjectId,
    PersonId,
    SpotId,
    SpotSectionId,
    StateKeyId,
)
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.play_session.application.play_rounds import PlayRoundsCommand, RoundLimitReached, WorldEnded
from ai_rpg_world.play_session.domain.turn_rounds import ChoiceFailed, TurnFinishedEvent
from tests.play_session.mine_village_session import WORLD, MineVillageSession

_GEN = PersonId("gen")


def _reply(tool_name: str, call_id: str, **arguments: object) -> ActionChoosingReply:
    return ActionChoosingReply(tool_call=ToolCallReply(tool_name=tool_name, arguments=arguments, call_id=call_id))


def _listening(count: int) -> list[ActionChoosingReply]:
    return [_reply("listen", f"listen_{i}") for i in range(count)]


def _turn_order(session: MineVillageSession) -> tuple[PersonId, ...]:
    return session.casts.get(WORLD).people()


def _answered_attempts(session: MineVillageSession, person: PersonId) -> list[Attempt]:
    return [
        e
        for e in session.short_term_memories.get(BeingId(person.value)).unsummarized()
        if isinstance(e, Attempt) and e.is_answered()
    ]


class _AnswersByPerson(ActionChoosingCompletion):
    """1 人ずつ頼まれるので、巡りの残りのターンの先頭を、いま頼まれている人とみなして答えを選ぶ。決めていない人は耳を澄ます。"""

    def __init__(self, session: MineVillageSession, answers: dict[PersonId, list[ActionChoosingReply]]) -> None:
        self._session = session
        self._answers = answers
        self.asked: list[PersonId] = []

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        person = self._session.turn_rounds.get(WORLD).due_turns()[0]
        self.asked.append(person)
        planned = self._answers.get(person, [])
        return planned.pop(0) if planned else _reply("listen", f"listen_{len(self.asked)}")


class _FailingFor(_AnswersByPerson):
    """決めた人の呼び出しだけを、LLM の時間切れのように例外で落とす。"""

    def __init__(self, session: MineVillageSession, failing: PersonId) -> None:
        super().__init__(session, {})
        self._failing = failing

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        reply = super().choose_action(messages, tools, reasoning_off=reasoning_off)
        if self.asked[-1] == self._failing:
            raise TimeoutError("no reply in 95 seconds")
        return reply


def _ready_to_start_the_lift(session: WorldSession) -> None:
    facts, world = session.facts(), session.aggregates()
    nouns, now = facts.nouns(), facts.now()
    for flag in nouns.all_flags():
        if flag.flag_id in (FlagId("generator_running"), FlagId("generator_warm")):
            world.flags().raise_flag(flag, WorldConditionsSettling(now))
    [fuel] = [k for k in nouns.object_of(ObjectId("generator")).state_keys if k.key == StateKeyId("fuel")]
    world.object_state(ObjectId("generator")).add_to_count(fuel, Count(2))
    key = world.bring_item_into_world(nouns.item_spec_of(ItemSpecId("lift_key")), now)
    world.inventory(_GEN).receive(key, ItemSpecId("lift_key"))
    world.whereabouts().teleport(PersonBody(_GEN), nouns.spot_of(SpotId("lift_landing")), now)
    world.whereabouts().enter_section(PersonBody(_GEN), nouns.section_of(SpotSectionId("cage")), frozenset())


class TestBeingsTakingTurnsOneByOne:
    """BeingsTakingTurnsOneByOne が、4 人の Being に場面と選択肢を渡して行動を選ばせ、世界で確定させて結果を Being に返すことを保証する。"""

    def test_each_of_the_four_gets_a_scene_and_choices_every_round(self) -> None:
        """スタブの LLM で廃坑の山村 v2 を 2 巡り回すと、4 人に毎巡り 1 回ずつ、場面と行動の候補とツールが渡る (#2230 の完了条件)。"""
        session = MineVillageSession(round_limit=2, delivers_world_events=True).started()
        completion = ScriptedActionChoosing(_listening(8))

        stopped = session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        assert stopped == RoundLimitReached()
        assert len(completion.calls) == 8
        for round_calls in (completion.calls[:4], completion.calls[4:]):
            assert len({call.messages[0]["content"] for call in round_calls}) == 4
        for call in completion.calls:
            assert "【現在地と周囲】" in call.messages[1]["content"]
            assert "【行動の候補】" in call.messages[1]["content"]
            assert "listen" in {tool["function"]["name"] for tool in call.tools}

    def test_result_of_the_chosen_action_answers_the_attempt(self) -> None:
        """1 巡り目に全員が耳を澄ますと、ゲンの短期記憶の試みに、耳を澄ます行為の成功の文と行動の要約「耳を澄ました」が結び付く。"""
        session = MineVillageSession(round_limit=1, delivers_world_events=True).started()

        session.play_rounds(session.beings_taking_turns(ScriptedActionChoosing(_listening(4))))(
            PlayRoundsCommand(WORLD)
        )

        [attempt] = _answered_attempts(session, _GEN)
        assert isinstance(attempt.result, ObservedOutcome)
        assert attempt.result.observation.body == "耳を澄まし、周囲の音や人の気配を確かめた。"
        route = attempt.result.observation.route
        assert isinstance(route, OwnActionResult)
        assert (route.succeeded, route.action_summary) == (True, "耳を澄ました")

    def test_choosing_to_wait_skips_the_next_round(self) -> None:
        """1 巡り目にゲンだけが待つを選ぶと、2 巡り目はゲンを除く 3 人にだけ頼む。"""
        session = MineVillageSession(round_limit=2).started()
        order = _turn_order(session)
        first_round = [
            _reply("wait", "wait_gen") if person == _GEN else _reply("listen", f"listen_{person.value}")
            for person in order
        ]
        completion = ScriptedActionChoosing([*first_round, *_listening(3)])

        session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        assert len(completion.calls) == 7

    def test_turn_without_a_tool_call_is_used_up_and_comes_back_next_round(self) -> None:
        """ゲンの LLM がツールを 1 つも呼ばなかったら、世界には何も送らず、次の巡りでまたゲンに頼む。"""
        session = MineVillageSession(round_limit=2).started()
        order = _turn_order(session)
        first_round = [
            ActionChoosingReply(tool_call=None) if person == _GEN else _reply("listen", f"listen_{person.value}")
            for person in order
        ]
        completion = ScriptedActionChoosing([*first_round, *_listening(4)])

        session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        assert len(completion.calls) == 8
        assert [a.move.call_id for a in _answered_attempts(session, _GEN)] != []
        assert all(a.move.tool_name == "listen" for a in _answered_attempts(session, _GEN))

    def test_destination_not_offered_is_answered_with_the_worlds_guidance(self) -> None:
        """ゲンが行き先の候補に無い「北の坑道」へ行こうとすると、試みには失敗の結果として世界の案内が結び付く。"""
        session = MineVillageSession(round_limit=1).started()
        order = _turn_order(session)
        replies = [
            _reply("travel_to", "go_north", destination="北の坑道")
            if person == _GEN
            else _reply("listen", f"listen_{person.value}")
            for person in order
        ]

        session.play_rounds(session.beings_taking_turns(ScriptedActionChoosing(replies)))(PlayRoundsCommand(WORLD))

        [attempt] = _answered_attempts(session, _GEN)
        assert isinstance(attempt.result, ObservedOutcome)
        assert attempt.result.observation.route.succeeded is False  # type: ignore[union-attr]
        assert "北の坑道" in str(attempt.result.observation.body)

    def test_lift_started_by_gen_ends_the_world_and_stops_the_play(self) -> None:
        """鍵を持ったゲンが暗い乗り場の籠にいて、発電機が暖まっている。ゲンの Being がカンテラを灯し、灯を手に持ってから操作盤で昇降機を動かすと、世界が終わる。同じ巡りの残りの人には頼まず、WorldEnded で止まる (#2232 の完了条件)。"""
        session = MineVillageSession(delivers_world_events=True).started()
        session.scope.run(_ready_to_start_the_lift)
        completion = _AnswersByPerson(
            session,
            {
                _GEN: [
                    _reply("interact", "light", target="カンテラ", how="油を足して灯す"),
                    _reply("hold_item", "hold", item="カンテラの灯"),
                    _reply("interact", "start_lift", target="籠の操作盤", how="鍵を差して昇降機を動かす"),
                ]
            },
        )

        stopped = session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        assert stopped == WorldEnded()
        assert completion.asked[-1] == _GEN
        [lit, held, started] = _answered_attempts(session, _GEN)
        assert isinstance(started.result, ObservedOutcome)
        assert (started.move.call_id, started.result.observation.route.succeeded) == ("start_lift", True)  # type: ignore[union-attr]

    def test_failed_llm_call_is_a_failed_turn_and_the_others_still_take_theirs(self) -> None:
        """ゲンの LLM の呼び出しが例外で落ちると、ゲンのターンは選べなかったターンとして残り、世界にも記憶にも何も入らず、同じ巡りの残りの人には頼む。"""
        session = MineVillageSession(round_limit=1).started()
        completion = _FailingFor(session, _GEN)

        session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        finished = [e for e in session.turn_round_events if isinstance(e, TurnFinishedEvent)]
        [gens] = [e for e in finished if e.person == _GEN]
        assert gens.outcome == ChoiceFailed("TimeoutError: no reply in 95 seconds")
        assert len(finished) == 4
        assert _answered_attempts(session, _GEN) == []
