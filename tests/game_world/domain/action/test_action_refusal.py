from __future__ import annotations

from ai_rpg_world.game_world.domain.action.action_outcome_for_actor import ActionOutcomeForActor, UnsummarizedAction
from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal
from ai_rpg_world.game_world.domain.action.actor_situation import ActorSituation
from ai_rpg_world.game_world.domain.action.built_in_attempts import ItemDropAttempt
from ai_rpg_world.game_world.domain.action.common_rule_refusal import NotCarrying
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import ItemSpecId, PersonId, SpotId
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from tests.game_world.support.world_design_for_tests import compose_world, item_spec, nouns

_ALICE = PersonId("alice")
_LAMP = item_spec("lamp")
_LAMP_1 = ItemInstanceId("lamp_1")
_DESIGN = compose_world(nouns(item_specs=(_LAMP,)))
_REFUSAL = ActionRefusal(
    attempt=ItemDropAttempt(_ALICE, _LAMP_1, Openly()),
    reason=NotCarrying(),
    text=TextWithUnassignedPeople("持っていない。").about({}),
)


def _situation(item_specs: dict[ItemInstanceId, ItemSpecId]) -> ActorSituation:
    return ActorSituation(at_spot=SpotId("hall"), actor_as=PersonBody(_ALICE), item_specs=item_specs)


class TestOutcomeForActorOfRefusal:
    """ActionRefusal.outcome_for_actor が、断りの文と、断った時点で品物を引けるかで決まる要約を、1 つの値として返すことを保証する。"""

    def test_refusal_with_every_item_known_is_summarized_with_its_name(self) -> None:
        """断った時点でランプの種類を引けるとき、結末は断りの文と、ランプの名前を当てた要約を持つ。"""
        situation = _situation({_LAMP_1: _LAMP.item_spec_id})

        outcome = _REFUSAL.outcome_for_actor(_DESIGN, situation)

        assert outcome == ActionOutcomeForActor(
            result=_REFUSAL.text, summary=TextWithUnassignedPeople("dropした lamp").about({})
        )

    def test_refusal_with_an_item_gone_has_no_summary(self) -> None:
        """断った時点でランプがもう世界に無く種類を引けないとき、結末は断りの文と UnsummarizedAction を持つ。"""
        outcome = _REFUSAL.outcome_for_actor(_DESIGN, _situation({}))

        assert outcome == ActionOutcomeForActor(result=_REFUSAL.text, summary=UnsummarizedAction())
