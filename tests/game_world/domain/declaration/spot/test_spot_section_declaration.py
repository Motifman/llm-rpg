from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.spot import NoCapacity, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.exception.spot_declaration_exception import DuplicateReachableObjectException
from ai_rpg_world.game_world.domain.value_object import DisplayName, ObjectId, SpotId, SpotSectionId


class TestSpotSectionDeclarationReachableObjects:
    """SpotSectionDeclaration が、中から届く物に同じ物を 2 回書いた宣言を作らないことを保証する。"""

    def test_same_object_listed_twice_raises(self) -> None:
        """reachable_objects に同じ ObjectId を 2 回書くと DuplicateReachableObjectException を投げる。"""
        with pytest.raises(DuplicateReachableObjectException):
            SpotSectionDeclaration(
                section_id=SpotSectionId("lift_cage"),
                spot_id=SpotId("lift_landing"),
                name=DisplayName("籠の中"),
                capacity=NoCapacity(),
                reachable_objects=(ObjectId("lift_lever"), ObjectId("lift_lever")),
            )

    def test_distinct_objects_are_kept_in_the_written_order(self) -> None:
        """reachable_objects に別々の物を書くと、断らずに書いた順のまま持つ。"""
        section = SpotSectionDeclaration(
            section_id=SpotSectionId("lift_cage"),
            spot_id=SpotId("lift_landing"),
            name=DisplayName("籠の中"),
            capacity=NoCapacity(),
            reachable_objects=(ObjectId("lift_lever"), ObjectId("lift_bell")),
        )

        assert section.reachable_objects == (ObjectId("lift_lever"), ObjectId("lift_bell"))
