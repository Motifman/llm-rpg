"""人が倒された観測を記録に入れるとき、名前を知らない倒した人が見た目で書かれることを保証する (#1609)。

formatter が組んだ観測を ``PlayerAcquaintances.view_for`` に通し、受け手の記録に入る版を見る。
"""

from __future__ import annotations

from unittest.mock import MagicMock

# observation.contracts.interfaces と prompt_builder_config の循環 import を避ける。
from ai_rpg_world.application.llm.services import prompt_builder as _prompt_builder  # noqa: F401
from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.player_formatter import (
    PlayerObservationFormatter,
)
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
    InMemoryAcquaintanceRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

SPOT = SpotId(1)
WITNESS = PlayerId(1)
VICTIM = PlayerId(2)
KILLER = PlayerId(3)
NAMES = {1: "ハル", 2: "サヨ", 3: "ゲン"}
LOOKS = {
    1: "測量具を背負った年かさの人",
    2: "綿入れを着込んだ若い娘",
    3: "髭の濃い大柄な人",
}


def _formatter(
    lighting: LightingEnum = LightingEnum.BRIGHT, victim_learns_killer: bool = True
) -> PlayerObservationFormatter:
    """3 人とも同じ場所にいる。"""
    name_resolver = MagicMock(spec=ObservationNameResolver)
    name_resolver.player_name.side_effect = lambda pid: NAMES[pid.value]
    graph = MagicMock()
    graph.get_entity_spot.return_value = SPOT
    repo = MagicMock()
    repo.find_graph.return_value = graph
    lighting_resolver = MagicMock()
    lighting_resolver.resolve.return_value = lighting
    return PlayerObservationFormatter(
        ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
            spot_graph_repository=repo,
            effective_lighting_resolver=lighting_resolver,
            death_semantics=MagicMock(
                announce_globally=True, victim_learns_killer=victim_learns_killer
            ),
        )
    )


def _acquaintances() -> PlayerAcquaintances:
    """ハルとサヨはゲンに会ったが、まだ名前を知らない。"""
    acquaintances = PlayerAcquaintances(
        store=InMemoryAcquaintanceRepository(),
        being_id_of=lambda pid: BeingId(f"being_p{pid.value}"),
        turn_reader=InMemoryExpectationRepository(),
        environment_name="山村",
        names_by_player_id=NAMES,
        appearances_by_player_id=LOOKS,
    )
    acquaintances.record_meeting(WITNESS, "サヨ")
    acquaintances.record_meeting(WITNESS, "ゲン")
    acquaintances.record_meeting(VICTIM, "ゲン")
    return acquaintances


def _downed() -> PlayerDownedEvent:
    return PlayerDownedEvent.create(
        aggregate_id=VICTIM,
        aggregate_type="PlayerStatusAggregate",
        killer_player_id=KILLER,
    )


def _recorded_by(
    acquaintances: PlayerAcquaintances,
    recipient: PlayerId,
    formatter: PlayerObservationFormatter | None = None,
) -> ObservationOutput:
    output = (formatter or _formatter()).format(_downed(), recipient)
    assert output is not None
    chosen = acquaintances.view_for(recipient, output)
    assert chosen is not None
    return chosen


class TestKillerSeenByABystander:
    """居合わせた人の記録で、倒した人を呼ぶ言葉を保証する。"""

    def test_killer_whose_name_is_unknown_is_written_by_appearance(self) -> None:
        """名前を知らない人が人を倒すのを見ると、記録には見た目で書かれ、名前は本文にも structured にも出ない。"""
        acquaintances = _acquaintances()

        chosen = _recorded_by(acquaintances, WITNESS)

        assert chosen.prose == "髭の濃い大柄な人が綿入れを着込んだ若い娘を倒した。"
        assert "ゲン" not in str(chosen.structured)

    def test_killer_whose_name_is_known_is_written_by_name(self) -> None:
        """名前を知っている人が人を倒すのを見ると、記録には名前のまま書かれる。"""
        acquaintances = _acquaintances()
        acquaintances.learn_name(WITNESS, KILLER, how="名乗り")

        chosen = _recorded_by(acquaintances, WITNESS)

        assert chosen.prose == "ゲンが綿入れを着込んだ若い娘を倒した。"

    def test_killer_hidden_by_darkness_is_not_named_in_structured(self) -> None:
        """暗くて倒した人を見分けられないとき、structured に倒した人の名前を足さない。"""
        output = _formatter(lighting=LightingEnum.DARK).format(_downed(), WITNESS)

        assert output is not None
        assert "ゲン" not in str(output.structured)


class TestKillerSeenByTheVictim:
    """倒された本人の記録で、倒した人を呼ぶ言葉を保証する。"""

    def test_killer_whose_name_is_unknown_is_written_by_appearance(self) -> None:
        """名前を知らない人に倒されると、本人の記録には見た目で書かれ、名前は本文にも structured にも出ない。"""
        acquaintances = _acquaintances()

        chosen = _recorded_by(acquaintances, VICTIM)

        assert chosen.prose == "髭の濃い大柄な人があなたを倒した。"
        assert "ゲン" not in str(chosen.structured)

    def test_killer_withheld_from_the_victim_is_not_named_in_structured(self) -> None:
        """シナリオが本人に倒した人を知らせないとき、structured に倒した人の名前を足さない。"""
        output = _formatter(victim_learns_killer=False).format(_downed(), VICTIM)

        assert output is not None
        assert "ゲン" not in str(output.structured)
