from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.being.contract import AgentMove, FrozenJsonObject, JsonValue
from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.action.action_reply import ActionDone, ActionRefused
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.settle_world_conditions import SettleWorldConditions
from ai_rpg_world.game_world.application.take_chosen_action import (
    TakeChosenAction,
    TakeChosenActionCommand,
    TurnGuidance,
)
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.built_in_attempts import ItemDropAttempt, SpeechAttempt
from ai_rpg_world.game_world.domain.action.speech import OrdinaryVoice, SpeechContent, Whisper
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import (
    Count,
    DisplayName,
    ItemSpecId,
    PersonId,
    SpotId,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.domain.world_records.latest_actions import ActionAttemptFailedEvent, PersonActedEvent
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore

_MINE_VILLAGE = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"
_WORLD = WorldId("world")
_GEN, _SAYO = PersonId("gen"), PersonId("sayo")
_OFFICE = SpotId("company_office")
_OPEN_SAFE = "番号を合わせて金庫を開ける"


def _person(handle: int) -> FrozenJsonObject:
    return FrozenJsonObject({"person": handle})


@pytest.fixture(scope="module")
def mine_village() -> WorldDesign:
    return load_scenario(_MINE_VILLAGE).design


class _Office:
    """廃坑の山村 v2 を開き、ゲンとサヨが自分の名前で入って、鉱山会社の事務所へ移る。"""

    def __init__(self, design: WorldDesign) -> None:
        store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="mine_village_v2",
            scenario_hash="mine_village_v2",
            design=design,
            random=SeedableRandomSource(0),
        )
        OpenWorld(store)(OpenWorldCommand(world_id=_WORLD, design=design))
        self.events: list[DomainEvent] = []
        distributor = CommittedEventsDistributor()
        distributor.register_receiver(self)
        self.scope = CommandScope(store, distributor)
        self.design = design
        self.scope.run(self._move_to_office)
        self._take = TakeChosenAction(self.scope, design, SettleWorldConditions(self.scope, design))

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.events.extend(events)

    def _move_to_office(self, session: WorldSession) -> None:
        office = self.design.nouns.spot_of(_OFFICE)
        for person, name in ((_GEN, "ゲン"), (_SAYO, "サヨ")):
            session.people_register().name(person, DisplayName(name))
            session.aggregates().whereabouts().teleport(PersonBody(person), office, WorldTick(0))

    def gen_chooses(self, tool_name: str, **arguments: JsonValue) -> ActionDone | ActionRefused | TurnGuidance:
        move = AgentMove(call_id="call", tool_name=tool_name, arguments=arguments)
        return self._take(TakeChosenActionCommand(_GEN, move))

    def let_gen_finish_acting(self) -> None:
        self.scope.run(lambda session: session.aggregates().vitals(_GEN).start_action(WorldTick(0)))

    def handle_of_sayo(self) -> int:
        return self.scope.run(lambda session: session.facts().people_register().handle_of(_SAYO).value)

    def items_of_gen(self, spec: str) -> tuple[ItemInstanceId, ...]:
        return self.scope.run(
            lambda session: tuple(
                item
                for item in session.facts().inventory(_GEN).items()
                if session.facts().item(item).spec_id == ItemSpecId(spec)
            )
        )

    def count_of_gen(self, spec: str) -> Count:
        return self.scope.run(lambda session: session.facts().inventory(_GEN).count_of(ItemSpecId(spec)))

    def acted(self) -> list[object]:
        return [event.attempt for event in self.events if isinstance(event, PersonActedEvent)]

    def failed(self) -> list[ActionAttemptFailedEvent]:
        return [event for event in self.events if isinstance(event, ActionAttemptFailedEvent)]


class TestTakeChosenAction:
    """TakeChosenAction が、ゲンの選んだ行動を名前から行為の試みに戻して確定させ、戻せないものには案内を返すことを保証する。"""

    def test_opening_the_safe_with_the_right_code_takes_effect(self, mine_village: WorldDesign) -> None:
        """「金庫 / 番号を合わせて金庫を開ける / 1907」を選ぶと、物への操作として確定し、金庫が開いて起動鍵が手に入る。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("interact", target="金庫", how=_OPEN_SAFE, code="1907")

        assert reply == ActionDone()
        assert office.count_of_gen("lift_key") == Count(1)

    def test_a_wrong_code_is_refused_and_the_reason_reaches_gen(self, mine_village: WorldDesign) -> None:
        """番号を間違えると断られ、作者の書いた理由の文が、返事と、本人に観測として届く失敗の出来事の両方に載る。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("interact", target="金庫", how=_OPEN_SAFE, code="0000")

        assert isinstance(reply, ActionRefused)
        [failed] = office.failed()
        assert failed.refusal == reply.refusal
        assert "扉はびくともしない" in str(reply.refusal.text)
        assert office.count_of_gen("lift_key") == Count(0)

    def test_an_unknown_tool_name_is_not_taken_and_guidance_is_returned(self, mine_village: WorldDesign) -> None:
        """行動の選択肢に無いツール名は確定せず、世界に何も起きないまま、その名前を挙げた案内が返る。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("fly_to", destination="井戸")

        assert reply == TurnGuidance(_GEN, "「fly_to」という行動は無い。", WorldTick(0))
        assert office.acted() == [] and office.failed() == []

    def test_a_destination_not_in_the_scene_is_not_taken_and_guidance_is_returned(
        self, mine_village: WorldDesign
    ) -> None:
        """場面に無い行き先は確定せず、選んだ名前を挙げて選べないことを伝える案内が返る。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("travel_to", destination="北の坑道")

        assert reply == TurnGuidance(_GEN, "「行く」の「行き先」に「北の坑道」は選べない。", WorldTick(0))
        assert office.acted() == []

    def test_a_person_not_in_the_scene_is_guided_without_showing_the_handle(self, mine_village: WorldDesign) -> None:
        """場面にいない人の印を選ぶと確定せず、案内の文には印の番号を出さない。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("speak", reach="ささやく", to=_person(999), content="聞こえるか")

        assert reply == TurnGuidance(_GEN, "「話す」の「相手」に選んだものは、いま選べない。", WorldTick(0))

    def test_whispering_to_sayo_by_her_handle_takes_effect(self, mine_village: WorldDesign) -> None:
        """サヨを人の印で選んでささやくと、書いた中身のささやきとして確定する。"""
        office = _Office(mine_village)

        reply = office.gen_chooses(
            "speak", reach="ささやく", to=_person(office.handle_of_sayo()), content="番号を知っているか"
        )

        assert reply == ActionDone()
        assert office.acted() == [SpeechAttempt(_GEN, Whisper(_SAYO), SpeechContent("番号を知っているか"))]

    def test_a_blank_code_is_guided_instead_of_taken(self, mine_village: WorldDesign) -> None:
        """番号を空白だけで書くと確定せず、書く文字が無いことを伝える案内が返る。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("interact", target="金庫", how=_OPEN_SAFE, code="  ")

        assert reply == TurnGuidance(_GEN, "「code」に書く文字が無い。", WorldTick(0))

    def test_an_item_with_the_same_name_as_others_is_taken_from_the_first_listed(
        self, mine_village: WorldDesign
    ) -> None:
        """3 つあるカンテラの油を置くと、世界が並べた順で先の 1 つが置かれる。"""
        office = _Office(mine_village)
        first = office.items_of_gen("lamp_oil")[0]

        reply = office.gen_chooses("drop_item", item="カンテラの油")

        assert reply == ActionDone()
        assert [attempt.item for attempt in office.acted() if isinstance(attempt, ItemDropAttempt)] == [first]

    def test_inline_speech_is_spoken_in_an_ordinary_voice_after_the_main_action(
        self, mine_village: WorldDesign
    ) -> None:
        """待つ行動に一言を添えると、待つことが確定したあとに、その一言がふつうの声の話す試みとして確定する。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("wait", say_inline="少し休もう")

        assert reply == ActionDone()
        assert [type(attempt).__name__ for attempt in office.acted()] == ["WaitAttempt", "SpeechAttempt"]
        assert office.acted()[1] == SpeechAttempt(_GEN, OrdinaryVoice(), SpeechContent("少し休もう"))

    def test_inline_speech_is_still_spoken_when_the_main_action_is_refused(self, mine_village: WorldDesign) -> None:
        """主の行為が断られても、添えた一言は話す試みとして確定し、返事は主の行為の断りになる。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("interact", target="金庫", how=_OPEN_SAFE, code="0000", say_inline="違ったか")

        assert isinstance(reply, ActionRefused)
        assert office.acted() == [SpeechAttempt(_GEN, OrdinaryVoice(), SpeechContent("違ったか"))]

    def test_inline_speech_on_speaking_is_guided(self, mine_village: WorldDesign) -> None:
        """話す行動には一言を添えられず、確定しないまま案内が返る。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("speak", reach="ふつうの声で話す", content="おい", say_inline="おい")

        assert reply == TurnGuidance(_GEN, "「話す」には一言を添えられない。", WorldTick(0))
        assert office.acted() == []

    def test_listening_takes_effect(self, mine_village: WorldDesign) -> None:
        """耳を澄ますを選ぶと、引数なしで確定する。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("listen")

        assert reply == ActionDone()
        assert [type(attempt).__name__ for attempt in office.acted()] == ["ListeningAttempt"]

    def test_inline_speech_is_not_spoken_when_the_main_action_is_guided(self, mine_village: WorldDesign) -> None:
        """主の行為が案内になったときは、添えた一言も話す試みにならず、世界に何も起きない。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("travel_to", destination="北の坑道", say_inline="行ってくる")

        assert isinstance(reply, TurnGuidance)
        assert office.acted() == [] and office.failed() == []

    def test_blank_inline_speech_is_treated_as_not_added(self, mine_village: WorldDesign) -> None:
        """空白だけの一言は添えなかったことになり、待つことだけが確定する。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("wait", say_inline="   ")

        assert reply == ActionDone()
        assert [type(attempt).__name__ for attempt in office.acted()] == ["WaitAttempt"]

    def test_inline_speech_that_is_not_text_is_guided(self, mine_village: WorldDesign) -> None:
        """文字でない一言は確定せず、文字で書くよう伝える案内が返る。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("wait", say_inline=3)

        assert reply == TurnGuidance(_GEN, "添える一言は文字で書く。", WorldTick(0))

    def test_an_argument_the_choice_does_not_read_is_guided(self, mine_village: WorldDesign) -> None:
        """待つ行動に選択肢に無い引数 (reason) を添えると、黙って捨てずに確定させず、その名前を挙げた案内が返る。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("wait", reason="疲れた")

        assert reply == TurnGuidance(_GEN, "「待つ」では「reason」を選べない。", WorldTick(0))
        assert office.acted() == []

    def test_a_choice_with_nothing_to_pick_is_guided(self, mine_village: WorldDesign) -> None:
        """事務所の床に何も落ちていないとき、拾うを選ぶと、選べるものが無いことを伝える案内が返る。"""
        office = _Office(mine_village)

        reply = office.gen_chooses("pickup_item", item="ランプ")

        assert reply == TurnGuidance(_GEN, "いまは「拾う」で選べるものが無い。", WorldTick(0))

    def test_opening_the_safe_again_is_refused_because_it_is_already_open(self, mine_village: WorldDesign) -> None:
        """開いた金庫を番号でもう一度開けようとすると、いまはできない試みとして確定に回り、扉がもう開いている理由で断られる。"""
        office = _Office(mine_village)
        office.gen_chooses("interact", target="金庫", how=_OPEN_SAFE, code="1907")
        office.let_gen_finish_acting()

        reply = office.gen_chooses("interact", target="金庫", how=_OPEN_SAFE, code="1907")

        assert isinstance(reply, ActionRefused)
        assert "金庫の扉はもう開いている" in str(reply.refusal.text)
