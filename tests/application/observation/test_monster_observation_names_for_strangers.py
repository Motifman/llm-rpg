"""モンスターが人を襲う観測を居合わせた人の記録に入れるとき、名前を知らない被害者が見た目で書かれることを保証する (#1605)。

formatter が組んだ観測を ``PlayerAcquaintances.view_for`` に通し、受け手の記録に入る版を見る。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.spot_graph_formatter import (
    SpotGraphObservationFormatter,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
    InMemoryAcquaintanceRepository,
)
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (
    InMemoryMemoryTurnClock,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAttackedPlayerInSpotEvent,
    MonsterStartedChasingInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId

GRAPH_ID = SpotGraphId.create(1)
SPOT = SpotId(1)
BEAST = MonsterId.create(101)
WITNESS = PlayerId(1)
VICTIM = PlayerId(2)
NAMES = {1: "ハル", 2: "サヨ"}
LOOKS = {1: "測量具を背負った年かさの人", 2: "綿入れを着込んだ若い娘"}


def _formatter() -> SpotGraphObservationFormatter:
    name_resolver = MagicMock(spec=ObservationNameResolver)
    name_resolver.monster_name_by_monster_id.return_value = "坑道の獣"
    name_resolver.player_name.side_effect = lambda pid: NAMES[pid.value]
    spot = MagicMock(interior=None)
    spot.name = "坑道"
    repo = MagicMock()
    repo.find_graph.return_value.get_spot.return_value = spot
    return SpotGraphObservationFormatter(
        ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
            spot_graph_repository=repo,
        )
    )


def _acquaintances() -> PlayerAcquaintances:
    """ハルはサヨに会ったが、まだ名前を知らない。"""
    acquaintances = PlayerAcquaintances(
        store=InMemoryAcquaintanceRepository(),
        being_id_of=lambda pid: BeingId(f"being_p{pid.value}"),
        turn_reader=InMemoryMemoryTurnClock(),
        environment_name="山村",
        names_by_player_id=NAMES,
        appearances_by_player_id=LOOKS,
    )
    acquaintances.record_meeting(WITNESS, "サヨ")
    return acquaintances


def _attacked() -> MonsterAttackedPlayerInSpotEvent:
    return MonsterAttackedPlayerInSpotEvent.create(
        aggregate_id=GRAPH_ID,
        aggregate_type="SpotGraphAggregate",
        attacker_monster_id=BEAST,
        spot_id=SPOT,
        target_player_id=EntityId.create(VICTIM.value),
        damage=3,
        target_incapacitated=False,
        target_visible=True,
    )


def _chasing() -> MonsterStartedChasingInSpotEvent:
    return MonsterStartedChasingInSpotEvent.create(
        aggregate_id=GRAPH_ID,
        aggregate_type="SpotGraphAggregate",
        monster_id=BEAST,
        spot_id=SPOT,
        target_player_id=EntityId.create(VICTIM.value),
    )


def _recorded_by_witness(acquaintances: PlayerAcquaintances, event: object) -> ObservationOutput:
    output = _formatter().format(event, WITNESS)
    assert output is not None
    chosen = acquaintances.view_for(WITNESS, output)
    assert chosen is not None
    return chosen


class TestMonsterAttackSeenByAStranger:
    """モンスターの攻撃の観測で、居合わせた人が被害者を呼ぶ言葉を保証する。"""

    def test_victim_whose_name_is_unknown_is_written_by_appearance(self) -> None:
        """名前を知らない人が襲われると、居合わせた人の記録には見た目で書かれ、名前は本文にも structured にも出ない。"""
        acquaintances = _acquaintances()

        chosen = _recorded_by_witness(acquaintances, _attacked())

        assert chosen.prose == "坑道の獣が綿入れを着込んだ若い娘を攻撃した。"
        assert "サヨ" not in str(chosen.structured)

    def test_victim_whose_name_is_known_is_written_by_name(self) -> None:
        """名前を知っている人が襲われると、居合わせた人の記録には名前のまま書かれる。"""
        acquaintances = _acquaintances()
        acquaintances.learn_name(WITNESS, VICTIM, how="名乗り")

        chosen = _recorded_by_witness(acquaintances, _attacked())

        assert chosen.prose == "坑道の獣がサヨを攻撃した。"


class TestMonsterChaseSeenByAStranger:
    """モンスターが人を狙って追跡を始めた観測で、居合わせた人が標的を呼ぶ言葉を保証する。"""

    def test_target_whose_name_is_unknown_is_written_by_appearance(self) -> None:
        """名前を知らない人が狙われると、居合わせた人の記録には見た目で書かれ、名前は本文にも structured にも出ない。"""
        acquaintances = _acquaintances()

        chosen = _recorded_by_witness(acquaintances, _chasing())

        assert chosen.prose == "坑道の獣が綿入れを着込んだ若い娘を狙って追跡を始めた。"
        assert "サヨ" not in str(chosen.structured)
