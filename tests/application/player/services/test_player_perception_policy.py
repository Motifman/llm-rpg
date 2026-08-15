from dataclasses import fields
from types import SimpleNamespace
from typing import ForwardRef, get_args

import pytest

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
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


_ACTOR_ENTITY_ID_FIELDS = frozenset(
    {
        "actor_entity_id",
        "attacker_entity_id",
        "entity_id",
        "original_actor_entity_id",
    }
)
_NON_ACTOR_ENTITY_ID_FIELDS = frozenset(
    {
        # 取引の相手側と、取引を持ちかけた側。どちらも「その出来事の実行者」
        # ではなく、二人の間の状態に付いた役割の目印で、常に entity_id か
        # partner_entity_id のどちらかと同じ人を指す。実行者は kind によら
        # ず entity_id に入る (持ちかけなら持ちかけた人、成立なら承諾した
        # 人、期限切れなら返事をしなかった人) ので、知覚の遮断は entity_id
        # で効く。ここを actor 側に入れると、同じ出来事で 2 人ぶんの層を
        # 見ることになり、どちらで遮ったのか読めなくなる。
        "offerer_entity_id",
        "partner_entity_id",
        # 板の約定の相手 (売り手) と、その場に居なくても届ける相手。どちらも
        # 「その出来事の実行者」ではない — 板を動かしたのは entity_id (出した
        # 人 / 買った人) で、知覚の遮断はそこで効く。ここを actor 側に入れると、
        # 1 つの出来事で 2 人ぶんの層を見ることになり、どちらで遮ったのかが
        # 読めなくなる。
        "counterparty_entity_id",
        "notify_entity_id",
        "recipient_entity_id",
        "target_entity_id",
        "target_player_id",
    }
)


def _contains_entity_id(annotation: object) -> bool:
    if annotation is EntityId or EntityId in get_args(annotation):
        return True
    if isinstance(annotation, ForwardRef):
        return _contains_entity_id(annotation.__forward_arg__)
    return isinstance(annotation, str) and "EntityId" in annotation


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

    @pytest.mark.parametrize("field_name", sorted(_ACTOR_ENTITY_ID_FIELDS))
    def test_every_known_actor_field_uses_the_perception_matrix(
        self, field_name: str
    ) -> None:
        """既知の actor 欄は表記が異なっても、すべて同じ知覚行列を通る。"""
        policy = PlayerPerceptionPolicy(
            outcome_registry=_registry(), departed_agents_enabled=True
        )
        event = SimpleNamespace(**{field_name: EntityId.create(2)})

        assert policy.can_receive_event(PlayerId(1), event) is False

    def test_observed_entity_id_fields_require_an_explicit_actor_classification(
        self,
    ) -> None:
        """観測対象 event の EntityId 欄は actor か対象側かを必ず分類する。

        未知の欄を None として全員へ配る静かな失敗を防ぐため、新しい EntityId 欄を
        足した人には知覚境界での意味を決めさせる。
        """
        actual_field_names: set[str] = set()
        for event_type in ObservedEventRegistry().get_all_event_types():
            actual_field_names.update(
                field.name
                for field in fields(event_type)
                if _contains_entity_id(field.type)
            )

        assert actual_field_names == (
            _ACTOR_ENTITY_ID_FIELDS | _NON_ACTOR_ENTITY_ID_FIELDS
        )

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
