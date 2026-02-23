"""
BehaviorStateTransitionService のテスト

正常ケース・境界ケース・返却イベントの検証を網羅する。
"""

import pytest

from ai_rpg_world.domain.monster.service.behavior_state_transition_service import (
    BehaviorStateTransitionService,
    SpotTargetParams,
    StateTransitionResult,
)
from ai_rpg_world.domain.monster.value_object.behavior_state_snapshot import BehaviorStateSnapshot
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
from ai_rpg_world.domain.world.value_object.behavior_context import GrowthContext
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent


def _obj(oid: int, x: int, y: int) -> WorldObject:
    """テスト用の WorldObject（object_id と coordinate のみ使用）"""
    return WorldObject(
        object_id=WorldObjectId(oid),
        coordinate=Coordinate(x, y),
        object_type=ObjectTypeEnum.NPC,
        is_blocking=False,
        component=ActorComponent(race="human"),
    )


def _observation(
    visible_threats=None,
    selected_target=None,
    growth_context=None,
):
    return BehaviorObservation(
        visible_threats=visible_threats or [],
        visible_hostiles=[],
        selected_target=selected_target,
        growth_context=growth_context,
    )


class TestSpotTargetParams:
    """SpotTargetParams の生成と不変性"""

    def test_create_with_required(self):
        """必須フィールドで作成できること"""
        oid = WorldObjectId(1)
        coord = Coordinate(5, 5)
        params = SpotTargetParams(target_id=oid, coordinate=coord)
        assert params.target_id == oid
        assert params.coordinate == coord
        assert params.effective_flee_threshold is None
        assert params.allow_chase is None

    def test_create_with_optional(self):
        """オプション付きで作成できること"""
        params = SpotTargetParams(
            target_id=WorldObjectId(2),
            coordinate=Coordinate(3, 4),
            effective_flee_threshold=0.3,
            allow_chase=True,
        )
        assert params.effective_flee_threshold == 0.3
        assert params.allow_chase is True

    def test_spot_target_params_is_frozen(self):
        """SpotTargetParams は frozen であること"""
        params = SpotTargetParams(
            target_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0),
        )
        with pytest.raises(AttributeError):
            params.target_id = WorldObjectId(2)  # type: ignore[misc]


class TestStateTransitionResult:
    """StateTransitionResult の生成とフィールド"""

    def test_create_defaults(self):
        """デフォルトで空の結果で作成できること"""
        result = StateTransitionResult()
        assert result.apply_enrage is False
        assert result.flee_from_threat_id is None
        assert result.flee_from_threat_coordinate is None
        assert result.spot_target_params is None
        assert result.do_lose_target is False
        assert result.lost_target_id is None
        assert result.last_known_coordinate is None


class TestBehaviorStateTransitionServiceNormal:
    """BehaviorStateTransitionService 正常ケース"""

    @pytest.fixture
    def service(self) -> BehaviorStateTransitionService:
        return BehaviorStateTransitionService()

    @pytest.fixture
    def actor_id(self) -> WorldObjectId:
        return WorldObjectId(100)

    @pytest.fixture
    def actor_coordinate(self) -> Coordinate:
        return Coordinate(5, 5)

    def test_compute_transition_no_change_returns_empty_result(
        self, service, actor_id, actor_coordinate
    ):
        """脅威・ターゲット・フェーズなし・ターゲット持っていないとき何も遷移しないこと"""
        snapshot = BehaviorStateSnapshot(state=BehaviorStateEnum.IDLE)
        obs = _observation()
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.apply_enrage is False
        assert result.flee_from_threat_id is None
        assert result.spot_target_params is None
        assert result.do_lose_target is False

    def test_compute_transition_enrage_only_when_phase_below_threshold(
        self, service, actor_id, actor_coordinate
    ):
        """phase_thresholds ありで HP が閾値以下のとき ENRAGE のみ適用されること"""
        snapshot = BehaviorStateSnapshot(
            state=BehaviorStateEnum.IDLE,
            hp_percentage=0.3,
            phase_thresholds=(0.5, 0.25),
        )
        obs = _observation()
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.apply_enrage is True
        assert result.flee_from_threat_id is None
        assert result.spot_target_params is None
        assert result.do_lose_target is False

    def test_compute_transition_enrage_not_applied_when_already_enrage(
        self, service, actor_id, actor_coordinate
    ):
        """既に ENRAGE のときは apply_enrage が立たないこと"""
        snapshot = BehaviorStateSnapshot(
            state=BehaviorStateEnum.ENRAGE,
            hp_percentage=0.2,
            phase_thresholds=(0.5,),
        )
        obs = _observation()
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.apply_enrage is False

    def test_compute_transition_enrage_not_applied_when_already_flee(
        self, service, actor_id, actor_coordinate
    ):
        """既に FLEE のときは ENRAGE を適用しないこと（FLEE 優先のため step 0 で ENRAGE にしない）"""
        snapshot = BehaviorStateSnapshot(
            state=BehaviorStateEnum.FLEE,
            hp_percentage=0.2,
            phase_thresholds=(0.5,),
        )
        obs = _observation()
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.apply_enrage is False

    def test_compute_transition_flee_when_visible_threats(
        self, service, actor_id, actor_coordinate
    ):
        """visible_threats がいるとき FLEE 遷移となり最も近い脅威が選ばれること"""
        threat_near = _obj(201, 6, 5)
        threat_far = _obj(202, 0, 0)
        snapshot = BehaviorStateSnapshot(state=BehaviorStateEnum.IDLE)
        obs = _observation(visible_threats=[threat_far, threat_near])
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.apply_enrage is False
        assert result.flee_from_threat_id == threat_near.object_id
        assert result.flee_from_threat_coordinate == threat_near.coordinate
        assert result.spot_target_params is None
        assert result.do_lose_target is False

    def test_compute_transition_spot_target_when_selected_target_no_threats(
        self, service, actor_id, actor_coordinate
    ):
        """selected_target のみで visible_threats がないとき spot_target_params が返ること"""
        target = _obj(1, 7, 5)
        snapshot = BehaviorStateSnapshot(state=BehaviorStateEnum.IDLE)
        growth = GrowthContext(effective_flee_threshold=0.3, allow_chase=True)
        obs = _observation(selected_target=target, growth_context=growth)
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.apply_enrage is False
        assert result.flee_from_threat_id is None
        assert result.spot_target_params is not None
        assert result.spot_target_params.target_id == target.object_id
        assert result.spot_target_params.coordinate == target.coordinate
        assert result.spot_target_params.effective_flee_threshold == 0.3
        assert result.spot_target_params.allow_chase is True
        assert result.do_lose_target is False

    def test_compute_transition_lose_target_when_no_threats_no_selected_has_target_id(
        self, service, actor_id, actor_coordinate
    ):
        """脅威・選択ターゲットなしで target_id を持っているとき do_lose_target が True になること"""
        lost_id = WorldObjectId(1)
        last_coord = Coordinate(8, 8)
        snapshot = BehaviorStateSnapshot(
            state=BehaviorStateEnum.CHASE,
            target_id=lost_id,
            last_known_target_position=last_coord,
        )
        obs = _observation()
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.apply_enrage is False
        assert result.flee_from_threat_id is None
        assert result.spot_target_params is None
        assert result.do_lose_target is True
        assert result.lost_target_id == lost_id
        assert result.last_known_coordinate == last_coord

    def test_compute_transition_lose_target_last_known_none(
        self, service, actor_id, actor_coordinate
    ):
        """lose_target で last_known_target_position が None のとき last_known_coordinate は None のまま返ること"""
        snapshot = BehaviorStateSnapshot(
            state=BehaviorStateEnum.CHASE,
            target_id=WorldObjectId(1),
            last_known_target_position=None,
        )
        obs = _observation()
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.do_lose_target is True
        assert result.lost_target_id == WorldObjectId(1)
        assert result.last_known_coordinate is None


class TestBehaviorStateTransitionServiceBoundary:
    """境界・優先順位のテスト"""

    @pytest.fixture
    def service(self) -> BehaviorStateTransitionService:
        return BehaviorStateTransitionService()

    @pytest.fixture
    def actor_id(self) -> WorldObjectId:
        return WorldObjectId(100)

    @pytest.fixture
    def actor_coordinate(self) -> Coordinate:
        return Coordinate(5, 5)

    def test_visible_threats_take_priority_over_selected_target(
        self, service, actor_id, actor_coordinate
    ):
        """visible_threats と selected_target 両方あるとき FLEE（脅威優先）になること"""
        threat = _obj(200, 6, 5)
        selected = _obj(1, 7, 5)
        snapshot = BehaviorStateSnapshot(state=BehaviorStateEnum.IDLE)
        obs = _observation(visible_threats=[threat], selected_target=selected)
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.flee_from_threat_id is not None
        assert result.flee_from_threat_id == threat.object_id
        assert result.spot_target_params is None

    def test_enrage_then_flee_when_phase_and_visible_threats(
        self, service, actor_id, actor_coordinate
    ):
        """phase 閾値以下かつ visible_threats のとき apply_enrage と flee の両方になること"""
        threat = _obj(200, 6, 5)
        snapshot = BehaviorStateSnapshot(
            state=BehaviorStateEnum.IDLE,
            hp_percentage=0.3,
            phase_thresholds=(0.5,),
        )
        obs = _observation(visible_threats=[threat])
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.apply_enrage is True
        assert result.flee_from_threat_id == threat.object_id

    def test_already_flee_does_not_trigger_spot_target(
        self, service, actor_id, actor_coordinate
    ):
        """既に FLEE のとき selected_target があっても spot_target_params を返さないこと"""
        target = _obj(1, 7, 5)
        snapshot = BehaviorStateSnapshot(state=BehaviorStateEnum.FLEE)
        obs = _observation(selected_target=target)
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.spot_target_params is None

    def test_already_flee_with_visible_threats_no_duplicate_flee(
        self, service, actor_id, actor_coordinate
    ):
        """既に FLEE のとき visible_threats があっても 1a に入らないため flee は設定されないこと"""
        threat = _obj(200, 6, 5)
        snapshot = BehaviorStateSnapshot(state=BehaviorStateEnum.FLEE)
        obs = _observation(visible_threats=[threat])
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.flee_from_threat_id is None
        assert result.flee_from_threat_coordinate is None

    def test_nearest_threat_selected_among_multiple(
        self, service, actor_id, actor_coordinate
    ):
        """複数脅威がいるとき最も近いものが選ばれること"""
        near = _obj(201, 5, 6)
        mid = _obj(202, 8, 5)
        far = _obj(203, 0, 0)
        snapshot = BehaviorStateSnapshot(state=BehaviorStateEnum.IDLE)
        obs = _observation(visible_threats=[far, mid, near])
        result = service.compute_transition(obs, snapshot, actor_id, actor_coordinate)
        assert result.flee_from_threat_id == near.object_id
        assert result.flee_from_threat_coordinate == near.coordinate


class TestBehaviorStateTransitionServiceGrowthContext:
    """growth_context の伝搬"""

    @pytest.fixture
    def service(self) -> BehaviorStateTransitionService:
        return BehaviorStateTransitionService()

    def test_spot_target_params_without_growth_context(self, service):
        """growth_context が None のとき effective_flee / allow_chase は None になること"""
        target = _obj(1, 3, 4)
        snapshot = BehaviorStateSnapshot(state=BehaviorStateEnum.IDLE)
        obs = _observation(selected_target=target, growth_context=None)
        result = service.compute_transition(
            obs, snapshot, WorldObjectId(100), Coordinate(5, 5)
        )
        assert result.spot_target_params is not None
        assert result.spot_target_params.effective_flee_threshold is None
        assert result.spot_target_params.allow_chase is None
