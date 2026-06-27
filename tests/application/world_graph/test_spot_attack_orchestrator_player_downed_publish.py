"""
``SpotAttackOrchestrator.execute_monster_attack`` で、致命攻撃時に積まれた
``PlayerDownedEvent`` が **publish されない** silent failure (PR-K) を回帰
固定する。

無人島シナリオ Y 実走で発覚: モンスターが player を倒した tick で
``PlayerStatusAggregate.apply_damage`` 内部で ``PlayerDownedEvent`` が
aggregate.add_event されるが、orchestrator はその events を回収 + publish
しないまま save するだけ。結果として:

- ``_format_player_downed`` 経由の observation broadcast が起きない
  (= 本人にも同 spot の他 player にも「戦闘不能」が届かない)
- ``PlayerDownedOutcomeHandler`` が呼ばれない (= outcome=DEAD 遷移なし)

正しい pattern は ``status_effects_tick_stage_service.py:94-101`` を参照。
``status.get_events()`` で回収 + ``status.clear_events()`` +
``event_publisher.publish_all(...)``。
"""

from dataclasses import dataclass, field
from typing import Any, List
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)


def _node() -> SpotNode:
    return SpotNode(
        spot_id=SPOT_A,
        name="干潟",
        description="",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
        atmosphere=SpotAtmosphere(
            lighting=LightingEnum.BRIGHT,
            sound_ambient=None,
            temperature=TemperatureEnum.NORMAL,
            smell=None,
        ),
    )


def _make_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(_node())
    return g


def _make_monster(attack: int = 5):
    monster = MagicMock()
    monster.monster_id = MonsterId.create(101)
    monster.template.faction = MonsterFactionEnum.ENEMY
    monster.template.has_dark_vision = False
    monster.template.base_stats.attack = attack
    monster.status = MonsterStatusEnum.ALIVE
    monster.can_attack_now.return_value = True
    return monster


def _make_player(
    *,
    is_down_before: bool = False,
    is_down_after: bool = False,
    events_when_down: List[Any] = None,
):
    """既存テストの _make_player を拡張: aggregate に積まれる events を
    spy できるよう ``get_events()`` / ``clear_events()`` を実装する。"""
    player = MagicMock()
    player.player_id = PlayerId(3)
    state = {"down": is_down_before, "events": []}
    type(player).is_down = property(lambda self: state["down"])

    def _apply(damage: int) -> None:
        # 既存 PlayerStatusAggregate.apply_damage が「HP 0 で is_down=True に
        # 変化させて PlayerDownedEvent を add_event する」挙動を模した。
        state["down"] = is_down_after
        if is_down_after and events_when_down:
            state["events"].extend(events_when_down)

    player.apply_damage.side_effect = _apply
    player.get_events.side_effect = lambda: list(state["events"])
    player.clear_events.side_effect = lambda: state["events"].clear()
    return player


@dataclass
class _SpyPublisher:
    events_published: List[Any] = field(default_factory=list)

    def publish_all(self, events) -> None:
        self.events_published.extend(events)


def _make_orchestrator(publisher=None):
    spot_repo = MagicMock()
    monster_repo = MagicMock()
    player_repo = MagicMock()
    return SpotAttackOrchestrator(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
        event_publisher=publisher,
    )


class TestEventPublisherInjection:
    """event_publisher は keyword-only で注入できる。未注入時は no-op。"""

    def test_no_publisher_does_not_crash(self):
        """event_publisher を渡さなくても orchestrator は構築できる
        (= 後方互換: 既存 caller がそのまま動く)。"""
        orchestrator = _make_orchestrator(publisher=None)
        assert orchestrator is not None


class TestExecuteMonsterAttackPublishesPlayerEvents:
    """致命攻撃で aggregate に積まれた PlayerDownedEvent が publish される。"""

    def test_fatal_monster_attack_publishes_player_events(self):
        """is_down_after=True (= 致命攻撃) なら player の get_events に積まれた
        PlayerDownedEvent 等を publisher.publish_all が受け取る。"""
        from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent

        downed_event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(3),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=None,
        )
        player = _make_player(
            is_down_after=True, events_when_down=[downed_event]
        )
        monster = _make_monster(attack=999)
        graph = _make_graph()
        graph.place_monster(MonsterId.create(101), SPOT_A)

        publisher = _SpyPublisher()
        orch = _make_orchestrator(publisher=publisher)
        outcome = orch.execute_monster_attack(
            attacker_monster=monster,
            target_player=player,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is True
        # publish_all に PlayerDownedEvent が含まれている
        assert any(
            isinstance(e, PlayerDownedEvent) for e in publisher.events_published
        ), (
            "PR-K: 致命攻撃時に PlayerDownedEvent が publish されていない。"
            "aggregate.get_events() を回収して publish_all に流す必要がある。"
        )
        # clear_events も呼ばれる (= 重複 publish 防止)
        player.clear_events.assert_called()

    def test_non_fatal_attack_does_not_publish_when_no_events(self):
        """致命でなく events が空のとき、publish_all は events=[] で呼ばれて
        も問題ないが、PlayerDownedEvent は流れない。"""
        from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent

        player = _make_player(is_down_after=False, events_when_down=[])
        monster = _make_monster(attack=10)
        graph = _make_graph()
        graph.place_monster(MonsterId.create(101), SPOT_A)

        publisher = _SpyPublisher()
        orch = _make_orchestrator(publisher=publisher)
        orch.execute_monster_attack(
            attacker_monster=monster,
            target_player=player,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )
        assert not any(
            isinstance(e, PlayerDownedEvent) for e in publisher.events_published
        )

    def test_no_publisher_falls_back_silently(self):
        """publisher 未注入時、致命攻撃でも crash せず executed=True を返す。
        後方互換 (= 既存 caller がそのまま動く)。"""
        from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent

        downed_event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(3),
            aggregate_type="PlayerStatusAggregate",
            killer_player_id=None,
        )
        player = _make_player(
            is_down_after=True, events_when_down=[downed_event]
        )
        monster = _make_monster(attack=999)
        graph = _make_graph()
        graph.place_monster(MonsterId.create(101), SPOT_A)

        orch = _make_orchestrator(publisher=None)
        outcome = orch.execute_monster_attack(
            attacker_monster=monster,
            target_player=player,
            graph=graph,
            spot_id=SPOT_A,
            current_tick=WorldTick(10),
        )
        assert outcome.executed is True
