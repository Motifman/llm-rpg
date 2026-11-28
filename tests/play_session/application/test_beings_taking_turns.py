from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.being.application.choose_action import (
    ActionChoosingCompletion,
    ActionChoosingReply,
    ToolCallReply,
)
from ai_rpg_world.being.contract import OwnActionResult
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.short_term_memory import Attempt, MemoryOperationOutcome, ObservedOutcome, Perception
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
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.play_session.application.play_rounds import PlayRoundsCommand, RoundLimitReached, WorldEnded
from ai_rpg_world.play_session.domain.turn_rounds import (
    ChoiceFailed,
    ObservationPassedOnEvent,
    RoundOpenedEvent,
    SkippedTurn,
    TurnFinishedEvent,
    TurnSkipReason,
)
from tests.play_session.mine_village_session import WORLD, MineVillageSession

_GEN = PersonId("gen")


def _reply(tool_name: str, call_id: str, **arguments: object) -> ActionChoosingReply:
    return ActionChoosingReply(tool_call=ToolCallReply(tool_name=tool_name, arguments=arguments, call_id=call_id))


def _murmur(call_id: str) -> ActionChoosingReply:
    return _reply("speak", call_id, reach="ふつうの声で話す", content="ふむ")


def _murmuring(count: int) -> list[ActionChoosingReply]:
    return [_murmur(f"murmur_{i}") for i in range(count)]


def _turn_order(session: MineVillageSession) -> tuple[PersonId, ...]:
    return session.casts.get(WORLD).people()


def _answered_attempts(session: MineVillageSession, person: PersonId) -> list[Attempt]:
    return [
        e
        for e in session.short_term_memories.get(BeingId(person.value)).unsummarized()
        if isinstance(e, Attempt) and e.is_answered()
    ]


class _AnswersByPerson(ActionChoosingCompletion):
    """1 人ずつ頼まれるので、巡りの残りのターンの先頭を、いま頼まれている人とみなして答えを選ぶ。決めていない人はふつうの声で一言つぶやく。"""

    def __init__(self, session: MineVillageSession, answers: dict[PersonId, list[ActionChoosingReply]]) -> None:
        self._session = session
        self._answers = answers
        self.asked: list[PersonId] = []
        self.prompts: list[tuple[PersonId, str]] = []

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        person = self._session.turn_rounds.get(WORLD).due_turns()[0]
        self.asked.append(person)
        self.prompts.append((person, messages[-1]["content"]))
        planned = self._answers.get(person, [])
        return planned.pop(0) if planned else _murmur(f"murmur_{len(self.asked)}")


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
    world.inventory(_GEN).receive(key, ItemSpecId("lift_key"), WorldTick(0))
    world.whereabouts().teleport(PersonBody(_GEN), nouns.spot_of(SpotId("lift_landing")), now)
    world.whereabouts().enter_section(PersonBody(_GEN), nouns.section_of(SpotSectionId("cage")), frozenset())


class TestBeingsTakingTurnsOneByOne:
    """BeingsTakingTurnsOneByOne が、4 人の Being に場面と選択肢を渡して行動を選ばせ、世界で確定させて結果を Being に返すことを保証する。"""

    def test_each_of_the_four_gets_a_scene_and_choices_every_round(self) -> None:
        """スタブの LLM で廃坑の山村 v2 を 2 巡り回すと、4 人に毎巡り 1 回ずつ、場面と行動の候補とツールが渡る (#2230 の完了条件)。"""
        session = MineVillageSession(round_limit=2, delivers_world_events=True).started()
        completion = ScriptedActionChoosing(_murmuring(8))

        stopped = session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        assert stopped == RoundLimitReached()
        assert len(completion.calls) == 8
        for round_calls in (completion.calls[:4], completion.calls[4:]):
            assert len({call.messages[0]["content"] for call in round_calls}) == 4
        for call in completion.calls:
            assert "【現在地と周囲】" in call.messages[1]["content"]
            assert "【現在選べる対象引数】" in call.messages[1]["content"]
            assert "speak" in {tool["function"]["name"] for tool in call.tools}

    def test_listening_never_reaches_the_beings(self) -> None:
        """耳を澄ます行為は世界に残っているが、2 巡り回しても 4 人のどのツールの名前・説明にもプロンプトにも listen と「耳を澄ま」が出ない (#2305 まで)。"""
        session = MineVillageSession(round_limit=2, delivers_world_events=True).started()
        completion = ScriptedActionChoosing(_murmuring(8))

        session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        assert len(completion.calls) == 8
        for call in completion.calls:
            shown = repr(call.tools) + "".join(message["content"] for message in call.messages)
            assert "listen" not in shown and "耳を澄ま" not in shown

    def test_result_of_the_chosen_action_answers_the_attempt(self) -> None:
        """1 巡り目に全員がふつうの声で「ふむ」と言うと、ゲンの短期記憶の試みに、話す行為の成功の文と行動の要約が結び付く。"""
        session = MineVillageSession(round_limit=1, delivers_world_events=True).started()

        session.play_rounds(session.beings_taking_turns(ScriptedActionChoosing(_murmuring(4))))(
            PlayRoundsCommand(WORLD)
        )

        [attempt] = _answered_attempts(session, _GEN)
        assert isinstance(attempt.result, ObservedOutcome)
        assert attempt.result.observation.body == "「ふむ」と言った。"
        route = attempt.result.observation.route
        assert isinstance(route, OwnActionResult)
        assert (route.succeeded, route.action_summary) == (True, "あなたは言った: 「ふむ」")

    def test_choosing_to_wait_skips_the_next_round(self) -> None:
        """1 巡り目にゲンだけが待つを選ぶと、2 巡り目はゲンを除く 3 人にだけ頼む。"""
        session = MineVillageSession(round_limit=2).started()
        order = _turn_order(session)
        first_round = [
            _reply("wait", "wait_gen") if person == _GEN else _murmur(f"murmur_{person.value}") for person in order
        ]
        completion = ScriptedActionChoosing([*first_round, *_murmuring(3)])

        session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        assert len(completion.calls) == 7

    def test_turn_without_a_tool_call_is_used_up_and_comes_back_next_round(self) -> None:
        """ゲンの LLM がツールを 1 つも呼ばなかったら、世界には何も送らず、次の巡りでまたゲンに頼む。"""
        session = MineVillageSession(round_limit=2).started()
        order = _turn_order(session)
        first_round = [
            ActionChoosingReply(tool_call=None) if person == _GEN else _murmur(f"murmur_{person.value}")
            for person in order
        ]
        completion = ScriptedActionChoosing([*first_round, *_murmuring(4)])

        session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        assert len(completion.calls) == 8
        assert [a.move.call_id for a in _answered_attempts(session, _GEN)] != []
        assert all(a.move.tool_name == "speak" for a in _answered_attempts(session, _GEN))

    def test_destination_not_offered_is_answered_with_the_worlds_guidance(self) -> None:
        """ゲンが行き先の候補に無い「北の坑道」へ行こうとすると、試みには失敗の結果として世界の案内が結び付く。"""
        session = MineVillageSession(round_limit=1).started()
        order = _turn_order(session)
        replies = [
            _reply("travel_to", "go_north", destination="北の坑道")
            if person == _GEN
            else _murmur(f"murmur_{person.value}")
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


class TestArrivalComesBackAsOwnAction:
    """移動して着いたことが、着いた本人には目撃の文ではなく、自分の行動の行として届くことを保証する。"""

    def test_gen_reads_setting_off_and_arriving_as_his_own_action_lines(self) -> None:
        """ゲンが南の横坑口から暗い南の横坑の奥へ移ると、次のターンの【直近の出来事】に、古い run と同じ出発の行と着いた行が並び、自分を見分けられない「誰かがどこからかやって来た。」は無い。"""
        session = MineVillageSession(delivers_world_events=True, round_limit=3).started()
        answers = _AnswersByPerson(session, {_GEN: [_reply("travel_to", "t1", destination="南の横坑の奥")]})

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        last_prompt = [prompt for person, prompt in answers.prompts if person == _GEN][-1]
        recent = last_prompt[last_prompt.index("【直近の出来事】") : last_prompt.index("【思い出せる出来事】")]
        assert (
            "[行動] 「南の横坑口」から「南の横坑の奥」へ向かって出発した → [結果] 「南の横坑の奥」へ移動中。" in recent
        )
        assert (
            "[行動] 「南の横坑の奥」に着いた → [結果] 「南の横坑の奥」に到着した。ここから次の行動を選べる。" in recent
        )
        assert "  呼び出し: travel_to()" in recent
        assert "やって来た" not in recent


class TestWhoIsAskedWhileOthersAct:
    """行為の最中の人は自分に向けたものがあったときだけ、待っている人は目立つ出来事で、次の巡りに頼まれることを保証する。"""

    _SAYO = PersonId("sayo")

    def _asked_in_round_two(self, gen_does: ActionChoosingReply, sayo_does: ActionChoosingReply) -> bool:
        session = MineVillageSession(delivers_world_events=True, round_limit=2).started()
        answers = _AnswersByPerson(session, {_GEN: [gen_does], self._SAYO: [sayo_does]})

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        asked = answers.asked.count(_GEN)
        assert asked in (1, 2), f"gen must act in round one, asked {asked} times"
        return asked == 2

    def test_gen_searching_is_not_asked_when_sayo_searches_beside_him(self) -> None:
        """探している最中 (3 tick かかる) のゲンは、同じ場所でサヨが探すのを見ても、次の巡りに頼まれない。"""
        assert not self._asked_in_round_two(_reply("explore", "e1"), _reply("explore", "e2"))

    def test_gen_searching_is_asked_when_sayo_whispers_to_him(self) -> None:
        """探している最中のゲンも、サヨにささやかれれば (to=ゲン)、次の巡りに頼まれる。"""
        whisper = _reply("speak", "s1", reach="ささやく", to="ゲン", content="そっちはどう？")

        assert self._asked_in_round_two(_reply("explore", "e1"), whisper)

    def test_gen_waiting_is_woken_when_sayo_searches_beside_him(self) -> None:
        """待つを選んだゲンは、同じ場所でサヨが探すのを見ると (目立つ出来事)、次の巡りに頼まれる。"""
        assert self._asked_in_round_two(_reply("wait", "w1"), _reply("explore", "e2"))

    def test_gen_searching_is_skipped_with_the_reason_in_the_round_opened_event(self) -> None:
        """サヨが探すのを見ただけの探している最中のゲンは、2 巡り目の RoundOpenedEvent に「行為の最中で、自分に向けたものが無い」と飛ばした理由が残る。"""
        session = MineVillageSession(delivers_world_events=True, round_limit=2).started()
        answers = _AnswersByPerson(session, {_GEN: [_reply("explore", "e1")], self._SAYO: [_reply("explore", "e2")]})

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        second = [e for e in session.turn_round_events if isinstance(e, RoundOpenedEvent) and e.round == 2]
        assert [s for s in second[0].skipped if s.person == _GEN] == [
            SkippedTurn(_GEN, TurnSkipReason.IN_THE_MIDDLE_OF_ACTION_AND_NOT_ADDRESSED)
        ]


def _bring_haru_to_the_south_adit_mouth(session: WorldSession) -> None:
    facts, world = session.facts(), session.aggregates()
    world.whereabouts().teleport(
        PersonBody(PersonId("haru")), facts.nouns().spot_of(SpotId("south_adit_mouth")), facts.now()
    )


class TestWordsReachThoseNearby:
    """同じ場所で話した言葉が、見える文に押しのけられず、声をはっきり聞いた人に届くことを保証する。"""

    _SAYO = PersonId("sayo")

    def _perceived_by(self, person: PersonId, session: MineVillageSession) -> list[str]:
        return [
            e.observation.body
            for e in session.short_term_memories.get(BeingId(person.value)).unsummarized()
            if isinstance(e, Perception)
        ]

    def test_gen_hears_what_sayo_says_beside_him(self) -> None:
        """同じ場所でサヨがふつうの声で「灯りを点けよう」と言うと、ゲンには「サヨが「灯りを点けよう」と言った。」が届き、「サヨが何か話している。」は届かない。"""
        session = MineVillageSession(delivers_world_events=True, round_limit=1).started()
        answers = _AnswersByPerson(
            session, {self._SAYO: [_reply("speak", "s1", reach="ふつうの声で話す", content="灯りを点けよう")]}
        )

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        heard = self._perceived_by(_GEN, session)
        assert "サヨが「灯りを点けよう」と言った。" in heard
        assert "サヨが何か話している。" not in heard

    def test_gen_hears_what_sayo_whispers_to_him(self) -> None:
        """サヨがゲンに「秘密だ」とささやくと、ゲンには「サヨが「秘密だ」とささやいた。」が届き、「サヨがあなたに顔を寄せた。」は届かない。"""
        session = MineVillageSession(delivers_world_events=True, round_limit=1).started()
        answers = _AnswersByPerson(
            session, {self._SAYO: [_reply("speak", "w1", reach="ささやく", to="ゲン", content="秘密だ")]}
        )

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        heard = self._perceived_by(_GEN, session)
        assert "サヨが「秘密だ」とささやいた。" in heard
        assert "サヨがあなたに顔を寄せた。" not in heard

    def test_haru_beside_them_sees_only_that_sayo_whispered(self) -> None:
        """同じ場所にいるハルには、サヨがゲンにささやいた言葉は届かず、いまどおり「…が…に何かささやいた。」の見える文が届く。"""
        session = MineVillageSession(delivers_world_events=True, round_limit=1).started()
        session.scope.run(_bring_haru_to_the_south_adit_mouth)
        answers = _AnswersByPerson(
            session, {self._SAYO: [_reply("speak", "w1", reach="ささやく", to="ゲン", content="秘密だ")]}
        )

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        heard = self._perceived_by(PersonId("haru"), session)
        assert any(body.endswith("に何かささやいた。") for body in heard)
        assert not any("秘密だ" in body for body in heard)


class TestChoicesWhileInTheMiddleOfAnAction:
    """行為の最中に呼ばれた人の【現在選べる対象引数】に、いまは選べない引数の無い行動が理由つきで出ることを保証する。"""

    _BUSY = "いまできない（手が離せない。今していることが済むまで待つしかない）"

    def test_gen_called_while_searching_sees_explore_and_wait_unavailable(self) -> None:
        """探している最中 (3 tick かかる) のゲンがサヨにささやかれて呼ばれると、ゲンの候補表に「- explore: いまできない（…）」と「- wait: いまできない（…）」が出る。"""
        session = MineVillageSession(delivers_world_events=True, round_limit=2).started()
        answers = _AnswersByPerson(
            session,
            {
                _GEN: [_reply("explore", "e1")],
                PersonId("sayo"): [_reply("speak", "s1", reach="ささやく", to="ゲン", content="そっちはどう？")],
            },
        )

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        gen = [prompt for person, prompt in answers.prompts if person == _GEN]
        assert len(gen) == 2
        table = gen[1][gen[1].index("【現在選べる対象引数】") :]
        assert f"- explore: {self._BUSY}" in table
        assert f"- wait: {self._BUSY}" in table

    def test_gen_before_searching_sees_no_unavailable_line_for_explore_or_wait(self) -> None:
        """何もしていない 1 巡り目のゲンの候補表には、探すと待つの「いまできない」の行が出ない。"""
        session = MineVillageSession(delivers_world_events=True, round_limit=1).started()
        answers = _AnswersByPerson(session, {})

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        [gen] = [prompt for person, prompt in answers.prompts if person == _GEN]
        table = gen[gen.index("【現在選べる対象引数】") :]
        assert "- explore:" not in table and "- wait:" not in table


class TestBelongingsComingAndGoing:
    """持ち物が増えたり減ったりしたことが、本人にだけ品物の名前つきで届くことを保証する。"""

    def test_lighting_the_lamp_tells_gen_the_oil_went_and_the_flame_came(self) -> None:
        """ゲンがカンテラに油を足して灯すと、古い run と同じく「カンテラの油を捨てました。」「カンテラの灯を入手しました。」が、効果の順でゲンの【直近の出来事】に並び、サヨには届かない。"""
        session = MineVillageSession(delivers_world_events=True, round_limit=4).started()
        answers = _AnswersByPerson(session, {_GEN: [_reply("interact", "l1", target="カンテラ", how="油を足して灯す")]})

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        gen = [prompt for person, prompt in answers.prompts if person == _GEN][-1]
        sayo = [prompt for person, prompt in answers.prompts if person == PersonId("sayo")][-1]
        recent = gen[gen.index("【直近の出来事】") : gen.index("【思い出せる出来事】")]
        assert recent.index("カンテラの油を捨てました。") < recent.index("カンテラの灯を入手しました。")
        assert "を入手しました。" not in sayo and "を捨てました。" not in sayo

    def test_handing_the_oil_to_sayo_tells_each_side_at_the_time_it_happened(self) -> None:
        """2 巡り目 (0:30) にゲンがサヨへカンテラの油を渡すと、ゲンには「[Day 1 深夜 0:30] カンテラの油を捨てました。」、サヨには「[Day 1 深夜 0:30] カンテラの油を入手しました。」が届く。"""
        session = MineVillageSession(delivers_world_events=True, round_limit=4).started()
        answers = _AnswersByPerson(
            session,
            {_GEN: [_murmur("l0"), _reply("give_item", "g1", to="サヨ", item="カンテラの油")]},
        )

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        gen = [prompt for person, prompt in answers.prompts if person == _GEN][-1]
        sayo = [prompt for person, prompt in answers.prompts if person == PersonId("sayo")][-1]
        assert "- [Day 1 深夜 0:30] カンテラの油を捨てました。" in gen
        assert "- [Day 1 深夜 0:30] カンテラの油を入手しました。" in sayo
        assert "入手しました" not in gen and "捨てました" not in sayo


class TestBodyChangeSinceTheLastScene:
    """身体の状態の「、前回 ±N」が、その人に前に渡した場面の値からの増減になることを保証する。"""

    def test_hunger_grown_between_two_scenes_is_written_as_the_change(self) -> None:
        """1 巡り目のゲンの場面には「前回」が無く、時間が進んで空腹が増えた 2 巡り目の場面の空腹の行は、古い run と同じく値のかっこの外に「、前回 +N」が付く (例: 「空腹: 問題なし（1/100）、前回 +1」)。"""
        session = MineVillageSession(round_limit=2).started()
        answers = _AnswersByPerson(session, {})

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        first, second = [prompt for person, prompt in answers.prompts if person == _GEN][:2]
        hunger_line = next(line for line in second.splitlines() if line.startswith("  空腹: "))
        assert "前回" not in first
        assert re.fullmatch(r"  空腹: \S+（\d+/\d+）、前回 \+\d+", hunger_line)


class TestMemoOfferedToBeings:
    """新しい世界が Being にメモの引数を出し、書いたメモが次のターンの【メモ】に出ることを保証する。"""

    def test_first_prompt_explains_the_memo_and_every_action_takes_it(self) -> None:
        """1 ターン目から、システムプロンプトに古い run と同じ【メモの書き方】が出て、思い出す道具と目次を直す道具を除く行動のツールはどれも memo の引数を持つ。"""
        session = MineVillageSession(round_limit=1, delivers_world_events=True).started()
        completion = ScriptedActionChoosing(_murmuring(4))

        session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        first = completion.calls[0]
        assert (
            "【メモの書き方】\n- 行動の tool の `memo` に、あとで使いたいことを書ける。" in first.messages[0]["content"]
        )
        actions = [
            tool for tool in first.tools if tool["function"]["name"] not in {"episode_recall", "episode_revise_index"}
        ]
        assert actions and all("memo" in tool["function"]["parameters"]["properties"] for tool in actions)

    def test_memo_written_with_an_action_appears_in_the_next_turn(self) -> None:
        """ゲンが一言つぶやくついでにやることを書くと、次のターンの【メモ】のやることにその文が出る。"""
        session = MineVillageSession(round_limit=2, delivers_world_events=True).started()
        todo = {"do": "add", "kind": "todo", "text": "倉庫でカンテラの油を探す"}
        answers = _AnswersByPerson(
            session, {_GEN: [_reply("speak", "l1", reach="ふつうの声で話す", content="ふむ", memo=[todo])]}
        )

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        first, second = [prompt for person, prompt in answers.prompts if person == _GEN]
        assert "倉庫でカンテラの油を探す" not in first
        memo = second[second.index("【メモ】") : second.index("【現在地と周囲】")]
        assert "やること:" in memo and "倉庫でカンテラの油を探す" in memo


class TestEpisodesWrittenWhileTakingTurns:
    """遊びの進行がターンごとに Being のターンを終え、範囲が埋まると裏で書いたエピソードが次の場面に出て、終わりに残りも書かれることを保証する。"""

    def test_first_prompt_offers_recalling_and_explains_the_index(self) -> None:
        """1 ターン目から、思い出す道具 episode_recall が出て、【渡される文面の読み方】に古い run と同じ目次の読み方の行が出る。"""
        session = MineVillageSession(round_limit=1, delivers_world_events=True).started()
        completion = ScriptedActionChoosing(_murmuring(4))

        session.play_rounds(session.beings_taking_turns(completion))(PlayRoundsCommand(WORLD))

        first = completion.calls[0]
        assert "episode_recall" in {tool["function"]["name"] for tool in first.tools}
        assert (
            "- 【思い出せる出来事】は、自分が昔の出来事を書き残した記憶の目次である。"
            "本文は `episode_recall` で呼び名を指定して思い出したときだけ読める。目次の一行だけから細部を補わない。"
        ) in first.messages[0]["content"]

    def test_episode_written_when_the_range_fills_appears_in_a_later_index(self) -> None:
        """ゲンが 20 回行動して短期記憶の範囲が埋まると、裏で書いたゲンのエピソードが、書き終わったあとの場面の【思い出せる出来事】に出る。

        裏のスレッドの速さに頼らないよう、20 巡りのあとで書き終わるのを待ってから、ゲンにもう 1 ターン頼む。
        """
        session = MineVillageSession(round_limit=20, delivers_world_events=True).started()
        answers = _AnswersByPerson(session, {})
        next_turn = ScriptedActionChoosing(_murmuring(1))
        try:
            session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))
            assert session.memory_writing.finish(BeingId(_GEN.value)) is True
            list(session.beings_taking_turns(next_turn).take_turns([_GEN]))
        finally:
            session.memory_writing.shutdown()

        gens = [prompt for person, prompt in answers.prompts if person == _GEN]
        later = next_turn.calls[0].messages[1]["content"]
        assert len(gens) == 20 and all("ゲンの記憶" not in prompt for prompt in gens)
        assert "ゲンの記憶" in later[later.index("【思い出せる出来事】") : later.index("【メモ】")]
        assert session.memory_writing.failures() == {}

    def test_ending_the_session_writes_what_was_not_yet_written(self) -> None:
        """2 巡りで終えると、4 人それぞれの、まだまとめていない出来事が 1 件ずつエピソードになる。"""
        session = MineVillageSession(round_limit=2, delivers_world_events=True).started()
        session.play_rounds(session.beings_taking_turns(ScriptedActionChoosing(_murmuring(8))))(
            PlayRoundsCommand(WORLD)
        )

        session.ended()

        for person in _turn_order(session):
            [episode] = session.episodes.list_by_being(BeingId(person.value))
            assert episode.environment_name == "廃坑の山村" and "ふむ" in episode.body


class TestRevisingTheIndexWhileTakingTurns:
    """新しい世界で、Being が目次を直すツールを選ぶと、世界に行為を渡さずに目次が直ることを保証する (#2261 の完了条件)。"""

    def test_gen_revises_the_index_of_an_episode_and_the_world_sees_no_action(self) -> None:
        """ゲンが目次の「金庫の番号を聞いた」を「井戸でサヨと話した」に直すと、目次が直り、ゲンの行為は世界に渡らない。"""
        session = MineVillageSession(round_limit=1, delivers_world_events=True).started()
        gen = BeingId(_GEN.value)
        episode = Episode.write(
            being_id=gen,
            episode_id="3f2a7b00-0000-4000-8000-00000000abcd",
            environment_name="廃坑の山村",
            written_turn=0,
            index=EpisodeIndex(summary="金庫の番号を聞いた", recall_when="金庫の話が出たとき"),
            body="サヨと井戸で話した。",
        )
        session.episodes.add(episode)
        revise = _reply(
            "episode_revise_index",
            "r1",
            handle=episode.handle,
            about="井戸でサヨと話した",
            recall_when="井戸の話が出たとき",
            inner_thought="目次が違っていた",
        )
        answers = _AnswersByPerson(session, {_GEN: [revise]})

        session.play_rounds(session.beings_taking_turns(answers))(PlayRoundsCommand(WORLD))

        revised = session.episodes.find_by_handle(gen, episode.handle)
        assert revised is not None and revised.index.summary == "井戸でサヨと話した"
        [attempt] = _answered_attempts(session, _GEN)
        assert attempt.move.tool_name == "episode_revise_index"
        assert isinstance(attempt.result, MemoryOperationOutcome) and attempt.result.succeeded


_PEOPLE_BY_NAME = {"ハル": PersonId("haru"), "ミオ": PersonId("mio"), "ゲン": _GEN, "サヨ": PersonId("sayo")}
_MIO, _SAYO = PersonId("mio"), PersonId("sayo")


def _finished_turns(session: MineVillageSession) -> list[TurnFinishedEvent]:
    return [e for e in session.turn_round_events if isinstance(e, TurnFinishedEvent)]


def _has_finished(session: MineVillageSession, person: PersonId, *, times: int = 1) -> Callable[[], bool]:
    return lambda: sum(1 for e in _finished_turns(session) if e.person == person) >= times


@dataclass(frozen=True)
class _Planned:
    reply: ActionChoosingReply | Exception
    returns_after: Callable[[], bool] | None = None


class _ThinkingAtOnce(ActionChoosingCompletion):
    """人柄の名前で誰の呼び出しかを見分け、決めた条件が揃うまで返事を返さない。並べて呼ばれないと条件が揃わず、時間切れで落ちる。"""

    def __init__(
        self,
        answers: dict[PersonId, list[_Planned]],
        *,
        late: Callable[[PersonId], _Planned | None] = lambda person: None,
    ) -> None:
        self._answers = answers
        self._late = late
        self._lock = threading.Lock()
        self.asked: list[PersonId] = []
        self.timed_out: list[PersonId] = []

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        found = re.search(r"あなたは(.+?)、", messages[0]["content"])
        assert found is not None
        person = _PEOPLE_BY_NAME[found.group(1)]
        with self._lock:
            self.asked.append(person)
            planned = self._answers.get(person, [])
            plan = self._late(person) or (
                planned.pop(0) if planned else _Planned(_murmur(f"murmur_{person.value}_{len(self.asked)}"))
            )
        if plan.returns_after is not None:
            deadline = time.monotonic() + 5.0
            while not plan.returns_after():
                if time.monotonic() > deadline:
                    self.timed_out.append(person)
                    raise AssertionError(f"{person.value} was not asked at the same time as the others")
                time.sleep(0.005)
        if isinstance(plan.reply, Exception):
            raise plan.reply
        return plan.reply


class TestBeingsTakingTurnsAtOnce:
    """BeingsTakingTurnsAtOnce が、ターンのある全員に同時に考えさせ、返事が返った順に世界で確定させることを保証する。"""

    def test_quicker_reply_is_carried_out_first_and_keeps_its_order(self) -> None:
        """ゲンの返事がミオの行為の確定まで返らないとき、ミオの行為が先に確定し、TurnFinishedEvent の順もミオがゲンより前になる。"""
        session = MineVillageSession(round_limit=1).started()
        completion = _ThinkingAtOnce({_GEN: [_Planned(_murmur("gen"), returns_after=_has_finished(session, _MIO))]})

        session.play_rounds(session.beings_taking_turns_at_once(completion))(PlayRoundsCommand(WORLD))
        assert completion.timed_out == []

        order = {e.person: e.order for e in _finished_turns(session)}
        assert order[_MIO] < order[_GEN]
        assert len(order) == 4

    def test_what_gen_perceived_while_choosing_comes_after_his_own_result(self) -> None:
        """隣のサヨの言葉がゲンの考えているあいだに確定すると、ゲンの短期記憶には自分の試みと結果のあとに、サヨの言葉が並ぶ。"""
        session = MineVillageSession(round_limit=1, delivers_world_events=True).started()
        speak = _reply("speak", "sayo_speaks", reach="ふつうの声で話す", content="灯りを点けよう")
        completion = _ThinkingAtOnce(
            {
                _SAYO: [_Planned(speak)],
                _GEN: [_Planned(_murmur("gen"), returns_after=_has_finished(session, _SAYO))],
            }
        )

        session.play_rounds(session.beings_taking_turns_at_once(completion))(PlayRoundsCommand(WORLD))
        assert completion.timed_out == []

        gens = session.short_term_memories.get(BeingId("gen")).unsummarized()
        kinds = [
            "own" if isinstance(e, Attempt) else e.observation.body
            for e in gens
            if isinstance(e, Attempt) or (isinstance(e, Perception) and "灯りを点けよう" in e.observation.body)
        ]
        assert kinds == ["own", "サヨが「灯りを点けよう」と言った。"]
        [attempt] = _answered_attempts(session, _GEN)
        assert attempt.move.call_id == "gen"

    def test_gen_who_chose_to_wait_is_woken_by_what_happened_while_he_was_choosing(self) -> None:
        """ゲンが考えているあいだに隣でサヨが探し始めると (目立つ出来事)、ゲンが待つを選んでも、次の巡りにまた頼まれる。"""
        session = MineVillageSession(round_limit=2, delivers_world_events=True).started()
        completion = _ThinkingAtOnce(
            {
                _SAYO: [_Planned(_reply("explore", "sayo_explores"))],
                _GEN: [_Planned(_reply("wait", "gen_waits"), returns_after=_has_finished(session, _SAYO))],
            }
        )

        session.play_rounds(session.beings_taking_turns_at_once(completion))(PlayRoundsCommand(WORLD))
        assert completion.timed_out == []

        assert completion.asked.count(_GEN) == 2

    def test_failed_call_is_a_failed_turn_and_the_others_still_take_theirs(self) -> None:
        """ゲンの呼び出しが例外で落ちても、ほかの 3 人の行為は確定し、ゲンのターンは選べなかったターンとして残る。"""
        session = MineVillageSession(round_limit=1).started()
        completion = _ThinkingAtOnce({_GEN: [_Planned(TimeoutError("no reply in 95 seconds"))]})

        session.play_rounds(session.beings_taking_turns_at_once(completion))(PlayRoundsCommand(WORLD))
        assert completion.timed_out == []

        outcomes = {e.person: e.outcome for e in _finished_turns(session)}
        assert outcomes.pop(_GEN) == ChoiceFailed("TimeoutError: no reply in 95 seconds")
        assert len(outcomes) == 3 and _answered_attempts(session, _GEN) == []

    def test_what_gen_perceives_from_his_own_action_reaches_him_before_his_turn_ends(self) -> None:
        """ゲンがカンテラを灯すと、自分の行為で届いた「カンテラの灯を入手しました。」は預からず、ゲンのターンを終えるより前に渡る。"""
        session = MineVillageSession(round_limit=1, delivers_world_events=True).started()
        session.scope.run(_ready_to_start_the_lift)
        completion = _ThinkingAtOnce(
            {_GEN: [_Planned(_reply("interact", "light", target="カンテラ", how="油を足して灯す"))]}
        )

        session.play_rounds(session.beings_taking_turns_at_once(completion))(PlayRoundsCommand(WORLD))
        assert completion.timed_out == []

        gens = [
            "finished" if isinstance(e, TurnFinishedEvent) else e.observation.body.template
            for e in session.turn_round_events
            if getattr(e, "person", None) == _GEN and isinstance(e, (TurnFinishedEvent, ObservationPassedOnEvent))
        ]
        assert gens.index("カンテラの灯を入手しました。") < gens.index("finished")

    def _world_ending_while_mio_thinks(self) -> tuple[MineVillageSession, object]:
        session = MineVillageSession(delivers_world_events=True).started()
        session.scope.run(_ready_to_start_the_lift)
        noted = {"do": "add", "kind": "todo", "text": "籠の様子を見る"}

        def mio_waits_in_the_round_gen_starts_the_lift(person: PersonId) -> _Planned | None:
            opened = [e for e in session.turn_round_events if isinstance(e, RoundOpenedEvent)][-1]
            if person != _MIO or _GEN not in opened.due or not _has_finished(session, _GEN, times=2)():
                return None
            return _Planned(
                _reply("speak", "mio_late", reach="ふつうの声で話す", content="待って", memo=[noted]),
                returns_after=_has_finished(session, _GEN, times=3),
            )

        completion = _ThinkingAtOnce(
            {
                _GEN: [
                    _Planned(_reply("interact", "light", target="カンテラ", how="油を足して灯す")),
                    _Planned(_reply("hold_item", "hold", item="カンテラの灯")),
                    _Planned(_reply("interact", "start_lift", target="籠の操作盤", how="鍵を差して昇降機を動かす")),
                ]
            },
            late=mio_waits_in_the_round_gen_starts_the_lift,
        )
        stopped = session.play_rounds(session.beings_taking_turns_at_once(completion))(PlayRoundsCommand(WORLD))
        assert completion.timed_out == []
        return session, stopped

    def test_choice_returned_after_the_world_ended_is_discarded_with_its_exchange(self) -> None:
        """ゲンが昇降機を動かして世界が終わったあとに返ったミオの選択は、世界に送られず、LLM とのやりとりごと WorldEnded に残る。"""
        _, stopped = self._world_ending_while_mio_thinks()

        assert isinstance(stopped, WorldEnded)
        [mios] = [d for d in stopped.discarded if d.person == _MIO]
        assert mios.exchange is not None and mios.failure is None
        call = mios.exchange.replies[-1].tool_call
        assert call is not None and call.call_id == "mio_late"

    def test_discarded_choice_leaves_nothing_in_memory_or_memo(self) -> None:
        """世界が終わって捨てたミオの選択は、ミオの短期記憶にも、添えたメモにも残らない。"""
        session, _ = self._world_ending_while_mio_thinks()

        mios = session.short_term_memories.get(BeingId("mio")).unsummarized()
        assert "mio_late" not in [e.move.call_id for e in mios if isinstance(e, Attempt)]
        assert session.memo_books.get(BeingId("mio")).memos == ()
