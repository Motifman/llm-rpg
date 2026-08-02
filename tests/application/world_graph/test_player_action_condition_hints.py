"""同席者行に出す対人 action に、前提条件のヒントが添うことを保証する。

物体行は既に ``gather(夜のみ)`` の形でヒントを出している。対人 action だけ
裸の名前で並ぶと、「暗い場所でだけ襲える」ことは**失敗して初めて**分かる。
失敗文でも学べるが、行動 1 回とターン 1 つを必ず捨てることになる。

一方で、**executor が「使える操作」を列挙する経路には裸の名前を出す**。
そこにヒント付きの文字列を出すと、LLM が ``strike_down(暗い場所のみ)`` を
そのまま action_name として渡し、「そんな操作は無い」の無限ループになる。
表示用と識別子用は別物として分ける。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.player_interaction_application_service import (
    PlayerInteractionApplicationService,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef


class _StubItemSpecRepository:
    """spec id から名前を引けるだけの最小 stub。"""

    def __init__(self, names: dict) -> None:
        self._names = names

    def find_by_id(self, spec_id):
        name = self._names.get(int(spec_id))
        if name is None:
            return None
        return type("_Spec", (), {"name": name})()


def _service(*definitions: InteractionDef, item_names=None):
    return PlayerInteractionApplicationService(
        spot_graph_repository=None,
        player_inventory_repository=None,
        item_repository=None,
        item_spec_repository=_StubItemSpecRepository(item_names or {}),
        player_status_repository=None,
        world_flag_state=None,
        player_interactions=tuple(definitions),
    )


def _definition(
    action_name: str,
    *conditions: InteractionCondition,
    display_label: str = "",
) -> InteractionDef:
    return InteractionDef(
        action_name=action_name,
        display_label=display_label,
        preconditions=tuple(conditions),
        effects=(),
    )


class TestActionLabelsCarryConditionHints:
    """available_action_labels() が表示用のヒント付き文字列を返す。"""

    def test_lighting_condition_becomes_a_hint(self) -> None:
        """SPOT_LIGHTING_IS は「暗い場所のみ」として添う。"""
        svc = _service(_definition(
            "strike_down",
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
                required_lighting="DARK",
            ),
            display_label="背後から襲う",
        ))
        assert svc.available_action_labels() == (
            "背後から襲う (strike_down・暗い場所のみ)",
        )

    def test_required_item_becomes_a_hint(self) -> None:
        """HAS_ITEM は品目名つきで「ナイフが要る」として添う。

        物体行では remediation と重複するため出さないが、対人 action には
        その重複が無い。何を持てば成立するのかは、失敗するまで prompt の
        どこにも出ていない。
        """
        svc = _service(
            _definition(
                "strike_down",
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                    target_item_spec_id=ItemSpecId.create(7),
                ),
            ),
            item_names={7: "ナイフ"},
        )
        assert svc.available_action_labels() == ("strike_down(ナイフが要る)",)

    def test_multiple_conditions_are_joined_in_declaration_order(self) -> None:
        """複数の条件は宣言順に「・」で連ねる (物体行と同じ書式)。"""
        svc = _service(
            _definition(
                "strike_down",
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
                    required_lighting="DARK",
                ),
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                    target_item_spec_id=ItemSpecId.create(7),
                ),
            ),
            item_names={7: "ナイフ"},
        )
        assert svc.available_action_labels() == (
            "strike_down(暗い場所のみ・ナイフが要る)",
        )

    def test_action_without_hintable_conditions_stays_bare(self) -> None:
        """ヒントに落とせる条件が無ければ、名前だけを返す。"""
        svc = _service(_definition(
            "tend",
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.TARGET_PLAYER_IS_INCAPACITATED,
            ),
        ))
        assert svc.available_action_labels() == ("tend",)

    def test_unresolvable_item_name_degrades_to_no_hint(self) -> None:
        """品目名を引けなければ、その条件のヒントだけを落とす。

        名前が出せないだけで action 候補ごと消すと、宣言した行為が LLM から
        発見できなくなる。ヒントの欠落より候補の消失のほうが重い。
        """
        svc = _service(
            _definition(
                "strike_down",
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.HAS_ITEM,
                    target_item_spec_id=ItemSpecId.create(99),
                ),
            ),
            item_names={},
        )
        assert svc.available_action_labels() == ("strike_down",)


class TestActionNamesStayBare:
    """available_action_names() は識別子なのでヒントを付けない。"""

    def test_names_are_unchanged_by_conditions(self) -> None:
        """条件があっても action_name はそのまま返る。

        executor の「人に対して使える操作: ...」列挙はこちらを使う。ここに
        ヒントを混ぜると、LLM が装飾ごと action_name として渡してしまう。

        行為者の state を渡す。渡さないと空が返る (伏せた操作の名前が
        案内から漏れていたため、行為者ごとに絞るようにした)。
        """
        svc = _service(_definition(
            "strike_down",
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
                required_lighting="DARK",
            ),
        ))
        assert svc.available_action_names({}) == ("strike_down",)
