from types import SimpleNamespace

from ai_rpg_world.application.player.services.player_perception_policy import (
    PlayerPerceptionPlane,
    PlayerPerceptionPolicy,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


def _registry() -> PlayerOutcomeRegistry:
    registry = PlayerOutcomeRegistry.new_for_players([PlayerId(1), PlayerId(2)])
    registry.set_outcome(PlayerId(2), PlayerOutcomeEnum.DEAD)
    return registry


class TestPlayerPerceptionPolicy:
    """生者と去った主体の知覚行列を一つの方針として固定する。"""

    def test_disabled_policy_keeps_every_player_on_the_living_plane(self) -> None:
        """機能が無効なら DEAD も従来の層として扱い、知覚を新たに遮らない。"""
        policy = PlayerPerceptionPolicy(outcome_registry=_registry())

        assert policy.plane_of(PlayerId(2)) is PlayerPerceptionPlane.LIVING
        assert policy.can_perceive_player(PlayerId(1), PlayerId(2)) is True

    def test_living_cannot_perceive_departed_but_departed_can_perceive_both(self) -> None:
        """有効時は生者→幽霊だけを遮り、幽霊→生者・幽霊を許す。"""
        policy = PlayerPerceptionPolicy(
            outcome_registry=_registry(), departed_agents_enabled=True
        )

        assert policy.can_perceive_player(PlayerId(1), PlayerId(2)) is False
        assert policy.can_perceive_player(PlayerId(2), PlayerId(1)) is True
        assert policy.can_perceive_player(PlayerId(2), PlayerId(2)) is True

    def test_spot_effect_actor_uses_the_same_perception_matrix(self) -> None:
        """actor_entity_id を持つ公開効果も、生者へ幽霊の実行者を漏らさない。"""
        policy = PlayerPerceptionPolicy(
            outcome_registry=_registry(), departed_agents_enabled=True
        )
        event = SimpleNamespace(actor_entity_id=EntityId.create(2))

        assert policy.can_receive_event(PlayerId(1), event) is False
        assert policy.can_receive_event(PlayerId(2), event) is True

    def test_actorless_world_event_is_outside_the_player_plane_matrix(self) -> None:
        """天候のように actor の無い出来事は、観測者の層にかかわらず遮らない。"""
        policy = PlayerPerceptionPolicy(
            outcome_registry=_registry(), departed_agents_enabled=True
        )

        assert policy.can_receive_event(PlayerId(1), SimpleNamespace()) is True
        assert policy.can_receive_event(PlayerId(2), SimpleNamespace()) is True

    def test_ejected_player_is_not_a_departed_agent_in_the_first_version(self) -> None:
        """湧かせる位置規則の無い EJECTED は、第1版の幽霊層へ入れない。"""
        outcomes = PlayerOutcomeRegistry.new_for_players([PlayerId(1)])
        outcomes.set_outcome(PlayerId(1), PlayerOutcomeEnum.EJECTED)
        policy = PlayerPerceptionPolicy(
            outcome_registry=outcomes, departed_agents_enabled=True
        )

        assert policy.plane_of(PlayerId(1)) is PlayerPerceptionPlane.LIVING
