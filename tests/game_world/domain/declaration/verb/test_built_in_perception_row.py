from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.verb.built_in_perception_row import BuiltInPerceptionRow
from ai_rpg_world.game_world.domain.design_flaw import DesignLocation
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind

_WITH_TARGET = (ActionKind.HAND_OVER, ActionKind.TEND)
_WITHOUT_TARGET = (
    ActionKind.TRAVEL,
    ActionKind.LISTEN,
    ActionKind.WAIT,
    ActionKind.PICK_UP,
    ActionKind.DROP,
    ActionKind.SEARCH,
    ActionKind.USE_ITEM,
    ActionKind.HOLD,
    ActionKind.PUT_AWAY,
    ActionKind.CAST_BALLOT,
)
_LOCATION = DesignLocation("built_in_action_perceptions", "row", "announcement")


class TestBuiltInPerceptionRowTarget:
    """BuiltInPerceptionRow が、組み込みの行為ごとに相手がいるかを 1 か所で決めることを保証する。"""

    @pytest.mark.parametrize("kind", _WITH_TARGET)
    def test_hand_over_and_tend_have_target(self, kind: ActionKind) -> None:
        """渡す・介抱するの行は相手がいる。"""
        assert BuiltInPerceptionRow.of_kind(kind).has_target

    def test_whisper_has_target(self) -> None:
        """ささやくの行は相手がいる。"""
        assert BuiltInPerceptionRow.whisper().has_target

    @pytest.mark.parametrize("kind", _WITHOUT_TARGET)
    def test_other_kinds_have_no_target(self, kind: ActionKind) -> None:
        """渡す・介抱するのほかの組み込みの行為の行は相手がいない。"""
        assert not BuiltInPerceptionRow.of_kind(kind).has_target

    @pytest.mark.parametrize(
        "row", [BuiltInPerceptionRow.speak(), BuiltInPerceptionRow.shout(), BuiltInPerceptionRow.arrival()]
    )
    def test_speak_shout_and_arrival_have_no_target(self, row: BuiltInPerceptionRow) -> None:
        """ふつうに話す・叫ぶ・着いたの行は相手がいない。"""
        assert not row.has_target

    def test_every_kind_in_the_table_is_decided(self) -> None:
        """組み込みの行為の表に書ける ActionKind は、どれも相手がいるかが決まっている。種類を足したら、ここに足す。"""
        assert sorted(kind.name for kind in _WITH_TARGET + _WITHOUT_TARGET) == sorted(
            kind.name for kind in BuiltInPerceptionRow.kinds()
        )


class TestBuiltInPerceptionRowDownedTarget:
    """BuiltInPerceptionRow が、相手が倒れている行を介抱だけと決めることを保証する。"""

    def test_tend_target_is_down(self) -> None:
        """介抱の行は、相手が倒れている。"""
        assert BuiltInPerceptionRow.of_kind(ActionKind.TEND).target_is_down

    @pytest.mark.parametrize(
        "row",
        [BuiltInPerceptionRow.of_kind(ActionKind.HAND_OVER), BuiltInPerceptionRow.whisper()],
        ids=["hand_over", "whisper"],
    )
    def test_other_rows_with_target_have_standing_target(self, row: BuiltInPerceptionRow) -> None:
        """渡す・ささやくの行は、相手がいても倒れていない。"""
        assert not row.target_is_down


class TestBuiltInPerceptionRowNames:
    """BuiltInPerceptionRow が、文に書ける呼び名に {target} を入れるかを、相手がいるかから決めることを保証する。"""

    def test_row_with_target_can_name_target(self) -> None:
        """ささやくの行は {actor}・{target}・{speech} を書ける。"""
        assert BuiltInPerceptionRow.whisper().nameable == frozenset({"actor", "target", "speech"})

    def test_row_without_target_cannot_name_target(self) -> None:
        """ふつうに話すの行は {actor}・{speech} だけを書ける。"""
        assert BuiltInPerceptionRow.speak().nameable == frozenset({"actor", "speech"})


class TestBuiltInPerceptionRowPlacement:
    """BuiltInPerceptionRow が、知らせの条件に相手を読めるかを、相手がいるかから決めることを保証する。"""

    def test_row_with_target_allows_reading_target(self) -> None:
        """渡すの行の照らし合わせの場所は、相手 (TARGET) を読める。"""
        placement = BuiltInPerceptionRow.of_kind(ActionKind.HAND_OVER).placement(_LOCATION)

        assert SubjectKind.TARGET in placement.subjects

    def test_row_without_target_refuses_reading_target(self) -> None:
        """拾うの行の照らし合わせの場所は、相手 (TARGET) を読めず、行う人 (ACTOR) は読める。"""
        placement = BuiltInPerceptionRow.of_kind(ActionKind.PICK_UP).placement(_LOCATION)

        assert (SubjectKind.TARGET in placement.subjects, SubjectKind.ACTOR in placement.subjects) == (False, True)
