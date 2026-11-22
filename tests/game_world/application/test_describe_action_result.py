from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.being.contract import AgentMove, JsonValue, Observation, OwnActionResult, TextWithPeople
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.describe_action_result import (
    DescribeActionResult,
    DescribeActionResultCommand,
)
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.pass_world_time import PassWorldTime, PassWorldTimeCommand
from ai_rpg_world.game_world.application.settle_world_conditions import SettleWorldConditions
from ai_rpg_world.game_world.application.take_chosen_action import TakeChosenAction, TakeChosenActionCommand
from ai_rpg_world.game_world.application.tell_current_time import TellCurrentTime, TellCurrentTimeCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId, SpotId, WorldId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import load_scenario
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore

_MINE_VILLAGE = Path(__file__).parents[3] / "data" / "scenarios" / "mine_village_v2.yaml"
_WORLD = WorldId("world")
_GEN = PersonId("gen")
_OFFICE = SpotId("company_office")
_OPEN_SAFE = "番号を合わせて金庫を開ける"


@pytest.fixture(scope="module")
def mine_village() -> WorldDesign:
    return load_scenario(_MINE_VILLAGE).design


class _GenInTheOffice:
    """廃坑の山村 v2 を開き、ゲンが自分の名前で入って、金庫のある鉱山会社の事務所へ移る。"""

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
        self.scope = CommandScope(store, CommittedEventsDistributor())
        self.scope.run(lambda session: self._move_to_office(session, design))
        assert isinstance(design.day_night, DayNightDeclaration)
        self._take = TakeChosenAction(self.scope, design, SettleWorldConditions(self.scope, design))
        self.describe = DescribeActionResult(self.scope, design, design.day_night)
        self.tell_time = TellCurrentTime(self.scope, design.day_night)
        self._pass_time = PassWorldTime(self.scope)

    def _move_to_office(self, session: WorldSession, design: WorldDesign) -> None:
        session.people_register().name(_GEN, DisplayName("ゲン"))
        session.aggregates().whereabouts().teleport(PersonBody(_GEN), design.nouns.spot_of(_OFFICE), WorldTick(0))

    def result_of(self, tool_name: str, **arguments: JsonValue) -> Observation:
        move = AgentMove(call_id="call_1", tool_name=tool_name, arguments=arguments)
        reply = self._take(TakeChosenActionCommand(_GEN, move))
        return self.describe(DescribeActionResultCommand(reply=reply, call_id="call_1"))

    def pass_ticks(self, count: int) -> None:
        for _ in range(count):
            self._pass_time(PassWorldTimeCommand())


def _template(body: str | TextWithPeople) -> str:
    return body.template if isinstance(body, TextWithPeople) else body


def _succeeded_and_summary(result: Observation) -> tuple[bool, str | None]:
    route = result.route
    assert isinstance(route, OwnActionResult) and route.call_id == "call_1"
    summary = route.action_summary
    return route.succeeded, summary if summary is None or isinstance(summary, str) else summary.template


class TestDescribeActionResult:
    """DescribeActionResult が、世界の返事を、本人の行動の結果 (OwnActionResult) の観測にすることを保証する。"""

    def test_done_interaction_becomes_a_successful_result_with_the_authors_text(
        self, mine_village: WorldDesign
    ) -> None:
        """ゲンが金庫を「1907」で開けると、結果は成功で、本文は作者が操作に書いた成功の文 (起動鍵だ…) になる。"""
        gen = _GenInTheOffice(mine_village)

        result = gen.result_of("interact", target="金庫", how=_OPEN_SAFE, code="1907")

        assert _succeeded_and_summary(result) == (True, f"「金庫」で{_OPEN_SAFE}")
        assert "昇降機の起動鍵だ" in _template(result.body)

    def test_lighting_the_lamp_carried_gives_the_authors_text_for_the_lamp(self, mine_village: WorldDesign) -> None:
        """ゲンが持っているカンテラを灯すと、本文は、持ち物のカンテラの操作に作者が書いた成功の文になる。"""
        gen = _GenInTheOffice(mine_village)

        result = gen.result_of("interact", target="カンテラ", how="油を足して灯す")

        assert _succeeded_and_summary(result) == (True, "「カンテラ」で油を足して灯す")
        assert _template(result.body).startswith("カンテラに油を足して火を入れた。")

    def test_done_built_in_action_becomes_a_successful_result_with_the_text_of_the_kind(
        self, mine_village: WorldDesign
    ) -> None:
        """組み込みの行為 (耳を澄ます) では、要約と本文は、共通の部品に行為ごとに書いた「耳を澄ました」と成功の文になる。"""
        gen = _GenInTheOffice(mine_village)

        result = gen.result_of("listen")

        assert _succeeded_and_summary(result) == (True, "耳を澄ました")
        assert _template(result.body) == "耳を澄まし、周囲の音や人の気配を確かめた。"

    def test_names_of_things_are_filled_into_the_summary_and_the_text(self, mine_village: WorldDesign) -> None:
        """ゲンが井戸へ移動を始めると、要約と本文の行き先に「井戸」が入る。"""
        gen = _GenInTheOffice(mine_village)

        result = gen.result_of("travel_to", destination="井戸")

        assert _succeeded_and_summary(result) == (True, "井戸へ移動した")
        assert _template(result.body) == "「井戸」へ移動中。到着までは他の行動はできない。"

    def test_spoken_words_are_filled_into_the_summary_and_the_text(self, mine_village: WorldDesign) -> None:
        """ゲンがふつうの声で「誰かいるか」と話すと、要約は「あなたは言った: 「誰かいるか」」、本文は「「誰かいるか」と言った。」になる。"""
        gen = _GenInTheOffice(mine_village)

        result = gen.result_of("speak", reach="ふつうの声で話す", content="誰かいるか")

        assert _succeeded_and_summary(result) == (True, "あなたは言った: 「誰かいるか」")
        assert _template(result.body) == "「誰かいるか」と言った。"

    def test_shouting_uses_the_text_for_shouting(self, mine_village: WorldDesign) -> None:
        """ゲンが「助けて」と叫ぶと、要約は「あなたは叫んだ: 「助けて」」、本文は「「助けて」と叫んだ。」になり、話すときの文と分かれる。"""
        gen = _GenInTheOffice(mine_village)

        result = gen.result_of("speak", reach="叫ぶ", content="助けて")

        assert _succeeded_and_summary(result) == (True, "あなたは叫んだ: 「助けて」")
        assert _template(result.body) == "「助けて」と叫んだ。"

    def test_refused_action_becomes_a_failed_result_with_the_reason(self, mine_village: WorldDesign) -> None:
        """ゲンが金庫を「0000」で開けようとすると、結果は失敗で、本文は作者の書いた断りの理由 (扉はびくともしない) になる。"""
        gen = _GenInTheOffice(mine_village)

        result = gen.result_of("interact", target="金庫", how=_OPEN_SAFE, code="0000")

        assert _succeeded_and_summary(result) == (False, f"「金庫」で{_OPEN_SAFE}")
        assert "扉はびくともしない" in _template(result.body)

    def test_guidance_becomes_a_failed_result_with_the_guidance_text(self, mine_village: WorldDesign) -> None:
        """ゲンが無いツール名を選ぶと、結果は失敗で、要約は無く (行為にならなかったため)、本文は世界の案内の文になる。"""
        gen = _GenInTheOffice(mine_village)

        result = gen.result_of("fly")

        assert _succeeded_and_summary(result) == (False, None)
        assert isinstance(result.body, str)
        assert "fly" in result.body

    def test_result_is_about_the_actor_at_the_current_time(self, mine_village: WorldDesign) -> None:
        """1 日 48 tick で 0 時に始まる山村で 3 tick 経ってからゲンが待つと、結果は本人に向けた本人についての観測で、時刻は「1 日目 01:30」になる。"""
        gen = _GenInTheOffice(mine_village)
        gen.pass_ticks(3)

        result = gen.result_of("wait")

        assert (result.subject_is_self, result.addressed_to_self) == (True, True)
        assert result.time.display == "1 日目 01:30"


class TestTellCurrentTime:
    """TellCurrentTime が、世界のいまの時刻を、観測と同じ何日目と時:分で答えることを保証する。"""

    def test_tells_the_day_and_clock_time(self, mine_village: WorldDesign) -> None:
        """1 日 48 tick で 0 時に始まる山村では、開いたばかりで「1 日目 00:00」、3 tick 経つと「1 日目 01:30」と答える。"""
        gen = _GenInTheOffice(mine_village)
        at_opening = gen.tell_time(TellCurrentTimeCommand())

        gen.pass_ticks(3)

        assert at_opening.display == "1 日目 00:00"
        assert gen.tell_time(TellCurrentTimeCommand()).display == "1 日目 01:30"
