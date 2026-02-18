"""SpawnSlot 値オブジェクトのテスト"""

import pytest
from ai_rpg_world.domain.monster.value_object.spawn_slot import SpawnSlot
from ai_rpg_world.domain.monster.value_object.spawn_condition import SpawnCondition
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterRespawnValidationException
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay


class TestSpawnSlot:
    """SpawnSlot のテスト"""

    @pytest.fixture
    def spot_id(self) -> SpotId:
        return SpotId(1)

    @pytest.fixture
    def coordinate(self) -> Coordinate:
        return Coordinate(5, 5, 0)

    @pytest.fixture
    def template_id(self) -> MonsterTemplateId:
        return MonsterTemplateId.create(1)

    def test_create_success_minimal(self, spot_id: SpotId, coordinate: Coordinate, template_id: MonsterTemplateId):
        """最小限のパラメータで作成できること"""
        slot = SpawnSlot(
            spot_id=spot_id,
            coordinate=coordinate,
            template_id=template_id,
        )
        assert slot.spot_id == spot_id
        assert slot.coordinate == coordinate
        assert slot.template_id == template_id
        assert slot.weight == 1
        assert slot.condition is None
        assert slot.max_concurrent == 1

    def test_create_success_full(
        self, spot_id: SpotId, coordinate: Coordinate, template_id: MonsterTemplateId
    ):
        """全パラメータで作成できること"""
        condition = SpawnCondition(time_band=TimeOfDay.NIGHT)
        slot = SpawnSlot(
            spot_id=spot_id,
            coordinate=coordinate,
            template_id=template_id,
            weight=2,
            condition=condition,
            max_concurrent=3,
        )
        assert slot.weight == 2
        assert slot.condition == condition
        assert slot.max_concurrent == 3

    def test_create_fail_weight_negative(
        self, spot_id: SpotId, coordinate: Coordinate, template_id: MonsterTemplateId
    ):
        """weight が負のときはエラー"""
        with pytest.raises(MonsterRespawnValidationException, match="weight"):
            SpawnSlot(
                spot_id=spot_id,
                coordinate=coordinate,
                template_id=template_id,
                weight=-1,
            )

    def test_create_fail_max_concurrent_zero(
        self, spot_id: SpotId, coordinate: Coordinate, template_id: MonsterTemplateId
    ):
        """max_concurrent が 0 のときはエラー（正の値のみ許可）"""
        with pytest.raises(MonsterRespawnValidationException, match="max_concurrent must be positive"):
            SpawnSlot(
                spot_id=spot_id,
                coordinate=coordinate,
                template_id=template_id,
                max_concurrent=0,
            )

    def test_create_fail_max_concurrent_negative(
        self, spot_id: SpotId, coordinate: Coordinate, template_id: MonsterTemplateId
    ):
        """max_concurrent が負のときはエラー"""
        with pytest.raises(MonsterRespawnValidationException, match="max_concurrent must be positive"):
            SpawnSlot(
                spot_id=spot_id,
                coordinate=coordinate,
                template_id=template_id,
                max_concurrent=-1,
            )

    def test_frozen(self, spot_id: SpotId, coordinate: Coordinate, template_id: MonsterTemplateId):
        """SpawnSlot は不変であること"""
        slot = SpawnSlot(spot_id=spot_id, coordinate=coordinate, template_id=template_id)
        with pytest.raises(AttributeError):
            slot.weight = 10
