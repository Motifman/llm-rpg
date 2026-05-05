"""Passage 値オブジェクトの単体テスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.enum.passage_kind import (
    BarrierStateEnum,
    DoorStateEnum,
    PassageKindEnum,
    WallStateEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PassageValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.passage import Passage


class TestPassageFactories:
    """Passage の各ファクトリのデフォルト値生成挙動。"""

    def test_open_default_is_traversable_and_full_sound(self) -> None:
        """OPEN は通行可・音透過率1.0。"""
        passage = Passage.open()
        assert passage.kind is PassageKindEnum.OPEN
        assert passage.traversable is True
        assert passage.sound_permeability == pytest.approx(1.0)

    def test_open_can_override_sound_permeability(self) -> None:
        """OPEN でも sound_permeability の上書きは許容される。"""
        passage = Passage.open(sound_permeability=0.7)
        assert passage.sound_permeability == pytest.approx(0.7)

    @pytest.mark.parametrize(
        "state,expected_traversable,expected_sound",
        [
            (WallStateEnum.INTACT, False, 0.1),
            (WallStateEnum.CRACKED, False, 0.4),
            (WallStateEnum.BROKEN, True, 1.0),
        ],
    )
    def test_wall_state_default_table(
        self, state: WallStateEnum, expected_traversable: bool, expected_sound: float
    ) -> None:
        """WALL の各状態で通行可否・音透過率のデフォルトが正しく適用される。"""
        passage = Passage.wall(state)
        assert passage.traversable is expected_traversable
        assert passage.sound_permeability == pytest.approx(expected_sound)
        assert passage.state == state.value

    def test_wall_overrides_apply(self) -> None:
        """WALL のデフォルト値を override 可能。"""
        passage = Passage.wall(
            WallStateEnum.INTACT, traversable=True, sound_permeability=0.95
        )
        assert passage.traversable is True
        assert passage.sound_permeability == pytest.approx(0.95)

    def test_door_locked_is_not_traversable(self) -> None:
        """DOOR LOCKED は通行不可。"""
        passage = Passage.door(DoorStateEnum.LOCKED)
        assert passage.traversable is False

    def test_barrier_active_is_not_traversable(self) -> None:
        """BARRIER ACTIVE は通行不可。"""
        passage = Passage.barrier(BarrierStateEnum.ACTIVE)
        assert passage.traversable is False

    def test_barrier_inactive_is_traversable(self) -> None:
        """BARRIER INACTIVE は通行可。"""
        passage = Passage.barrier(BarrierStateEnum.INACTIVE)
        assert passage.traversable is True


class TestPassageValidation:
    """Passage のバリデーション挙動。"""

    def test_invalid_state_for_kind_rejected(self) -> None:
        """kind と整合しない state を渡すと ValidationException を投げる。"""
        with pytest.raises(PassageValidationException, match="Invalid state"):
            Passage(
                kind=PassageKindEnum.WALL,
                state="LOCKED",  # WALL の状態ではない
                traversable=False,
                sound_permeability=0.1,
            )

    @pytest.mark.parametrize("perm", [-0.01, 1.01, 2.0])
    def test_sound_permeability_out_of_range_rejected(self, perm: float) -> None:
        """sound_permeability が [0.0, 1.0] の範囲外なら ValidationException を投げる。"""
        with pytest.raises(PassageValidationException, match="sound_permeability"):
            Passage(
                kind=PassageKindEnum.OPEN,
                state="OPEN",
                traversable=True,
                sound_permeability=perm,
            )


class TestPassageWithState:
    """Passage.with_state による状態遷移挙動。"""

    def test_wall_intact_to_broken_uses_default_table(self) -> None:
        """INTACT 壁を BROKEN に遷移させると通行可・音透過率1.0になる。"""
        intact = Passage.wall(WallStateEnum.INTACT)
        broken = intact.with_state(WallStateEnum.BROKEN.value)
        assert broken.kind is PassageKindEnum.WALL
        assert broken.state == WallStateEnum.BROKEN.value
        assert broken.traversable is True
        assert broken.sound_permeability == pytest.approx(1.0)

    def test_with_state_rejects_state_of_other_kind(self) -> None:
        """別の kind に属する state を with_state に渡すと拒否される。"""
        wall = Passage.wall()
        with pytest.raises(PassageValidationException):
            wall.with_state("LOCKED")  # LOCKED は DOOR の状態

    def test_with_state_overrides_apply(self) -> None:
        """with_state の override 引数で個別値を上書き可能。"""
        intact = Passage.wall(WallStateEnum.INTACT)
        cracked = intact.with_state(
            WallStateEnum.CRACKED.value, sound_permeability=0.55
        )
        assert cracked.sound_permeability == pytest.approx(0.55)
        # traversable は default のまま
        assert cracked.traversable is False
