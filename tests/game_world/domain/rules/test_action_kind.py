from __future__ import annotations

from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind


class TestActionKind:
    """ActionKind が action.md に並ぶ、どの世界にもある行為の種類だけを持つことを保証する。"""

    def test_members_match_the_kinds_listed_in_the_design(self) -> None:
        """種類は action.md の一覧と同じ 19 個で、手に持つ (HOLD) と荷にしまう (PUT_AWAY) を含む。"""
        expected = {
            "TRAVEL",
            "SPEAK",
            "LISTEN",
            "WAIT",
            "TEND",
            "HAND_OVER",
            "PICK_UP",
            "DROP",
            "SEARCH",
            "USE_ITEM",
            "ENTER_SECTION",
            "LEAVE_SECTION",
            "HOLD",
            "PUT_AWAY",
            "CAST_BALLOT",
            "INTERACT_WITH_OBJECT",
            "INTERACT_WITH_CARRIED_ITEM",
            "INTERACT_WITH_PERSON",
            "ATTACK_MONSTER",
        }

        assert {kind.name for kind in ActionKind} == expected

    def test_each_value_is_its_own_name(self) -> None:
        """どの種類も、値が名前と同じ文字列なので、名前の綴りから種類を引ける。"""
        assert all(ActionKind(kind.name) is kind for kind in ActionKind)
