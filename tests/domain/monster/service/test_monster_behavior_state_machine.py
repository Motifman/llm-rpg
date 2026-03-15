"""
MonsterBehaviorStateMachine のテスト

正常ケース・例外ケース・境界ケースの網羅的検証。
"""

import pytest

from ai_rpg_world.domain.monster.service.monster_behavior_state_machine import (
    MonsterBehaviorStateMachine,
    AttackedTransitionResult,
    TransitionApplicationOutput,
    EventSpec,
)
from ai_rpg_world.domain.monster.service.behavior_state_transition_service import (
    StateTransitionResult,
    SpotTargetParams,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
    EcologyTypeEnum,
)


class TestAttackedTransitionResult:
    """AttackedTransitionResult の生成と不変性"""

    def test_create_no_transition(self):
        """no_transition=True で何も変更しない結果"""
        result = AttackedTransitionResult(no_transition=True)
        assert result.no_transition is True
        assert result.new_state is None
        assert result.new_target_id is None
        assert result.new_last_known_position is None
        assert result.clear_pursuit is False
        assert result.sync_pursuit is False

    def test_create_flee_transition(self):
        """FLEE 遷移の結果"""
        oid = WorldObjectId(99)
        coord = Coordinate(1, 2, 0)
        result = AttackedTransitionResult(
            new_state=BehaviorStateEnum.FLEE,
            new_target_id=oid,
            new_last_known_position=coord,
            clear_pursuit=True,
            sync_pursuit=False,
        )
        assert result.no_transition is False
        assert result.new_state == BehaviorStateEnum.FLEE
        assert result.new_target_id == oid
        assert result.new_last_known_position == coord
        assert result.clear_pursuit is True
        assert result.sync_pursuit is False

    def test_create_chase_transition_with_sync(self):
        """CHASE 遷移で pursuit 同期あり"""
        oid = WorldObjectId(100)
        coord = Coordinate(5, 5, 0)
        result = AttackedTransitionResult(
            new_state=BehaviorStateEnum.CHASE,
            new_target_id=oid,
            new_last_known_position=coord,
            clear_pursuit=False,
            sync_pursuit=True,
        )
        assert result.sync_pursuit is True
        assert result.clear_pursuit is False


class TestEventSpec:
    """EventSpec の生成"""

    def test_create_target_spotted(self):
        spec = EventSpec(
            kind="target_spotted",
            target_id=WorldObjectId(1),
            coordinate=Coordinate(2, 3, 0),
        )
        assert spec.kind == "target_spotted"
        assert spec.target_id == WorldObjectId(1)
        assert spec.coordinate == Coordinate(2, 3, 0)

    def test_create_target_lost(self):
        spec = EventSpec(
            kind="target_lost",
            target_id=WorldObjectId(2),
            last_known_coordinate=Coordinate(4, 5, 0),
        )
        assert spec.kind == "target_lost"
        assert spec.last_known_coordinate == Coordinate(4, 5, 0)

    def test_create_actor_state_changed(self):
        spec = EventSpec(
            kind="actor_state_changed",
            old_state=BehaviorStateEnum.CHASE,
            new_state=BehaviorStateEnum.SEARCH,
        )
        assert spec.kind == "actor_state_changed"
        assert spec.old_state == BehaviorStateEnum.CHASE
        assert spec.new_state == BehaviorStateEnum.SEARCH


class TestMonsterBehaviorStateMachineComputeAttackedTransition:
    """compute_attacked_transition のテスト"""

    @pytest.fixture
    def sm(self) -> MonsterBehaviorStateMachine:
        return MonsterBehaviorStateMachine()

    @pytest.fixture
    def attacker_id(self) -> WorldObjectId:
        return WorldObjectId(200)

    @pytest.fixture
    def attacker_coord(self) -> Coordinate:
        return Coordinate(5, 5, 0)

    class TestNormalCases:
        """正常ケース"""

        def test_patrol_only_returns_no_transition(self, sm, attacker_id, attacker_coord):
            """PATROL_ONLY は常に no_transition"""
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_coord,
                ecology_type=EcologyTypeEnum.PATROL_ONLY,
                hp_percentage=0.5,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=None,
                ambush_chase_range=None,
            )
            assert result.no_transition is True
            assert result.new_state is None

        def test_flee_only_returns_flee_clear_pursuit(self, sm, attacker_id, attacker_coord):
            """FLEE_ONLY は FLEE に遷移、clear_pursuit"""
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_coord,
                ecology_type=EcologyTypeEnum.FLEE_ONLY,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=None,
                ambush_chase_range=None,
            )
            assert result.no_transition is False
            assert result.new_state == BehaviorStateEnum.FLEE
            assert result.new_target_id == attacker_id
            assert result.new_last_known_position == attacker_coord
            assert result.clear_pursuit is True
            assert result.sync_pursuit is False

        def test_normal_hp_low_returns_flee(self, sm, attacker_id, attacker_coord):
            """HP% が閾値以下なら FLEE"""
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_coord,
                ecology_type=EcologyTypeEnum.NORMAL,
                hp_percentage=0.1,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=None,
                ambush_chase_range=None,
            )
            assert result.no_transition is False
            assert result.new_state == BehaviorStateEnum.FLEE
            assert result.clear_pursuit is True

        def test_normal_hp_high_allow_chase_returns_chase(self, sm, attacker_id, attacker_coord):
            """HP 十分・allow_chase で CHASE、sync_pursuit"""
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_coord,
                ecology_type=EcologyTypeEnum.NORMAL,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=None,
                ambush_chase_range=None,
            )
            assert result.no_transition is False
            assert result.new_state == BehaviorStateEnum.CHASE
            assert result.new_target_id == attacker_id
            assert result.sync_pursuit is True
            assert result.clear_pursuit is False

        def test_normal_enrage_state_does_not_chase(self, sm, attacker_id, attacker_coord):
            """ENRAGE 状態では CHASE に遷移しない（state は維持、sync はする）"""
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_coord,
                ecology_type=EcologyTypeEnum.NORMAL,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.ENRAGE,
                behavior_initial_position=None,
                ambush_chase_range=None,
            )
            assert result.new_state == BehaviorStateEnum.ENRAGE
            assert result.sync_pursuit is True

        def test_normal_allow_chase_false_does_not_chase(self, sm, attacker_id, attacker_coord):
            """allow_chase=False のとき CHASE にしない（target は更新、sync）"""
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_coord,
                ecology_type=EcologyTypeEnum.NORMAL,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=False,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=None,
                ambush_chase_range=None,
            )
            assert result.new_state == BehaviorStateEnum.IDLE
            assert result.new_target_id == attacker_id
            assert result.sync_pursuit is True

    class TestAmbush:
        """AMBUSH 生態タイプ"""

        def test_ambush_out_of_range_returns_no_transition(
            self, sm, attacker_id, attacker_coord
        ):
            """初期位置から ambush_chase_range 外なら no_transition"""
            initial = Coordinate(0, 0, 0)
            attacker_far = Coordinate(100, 0, 0)
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_far,
                ecology_type=EcologyTypeEnum.AMBUSH,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=initial,
                ambush_chase_range=5,
            )
            assert result.no_transition is True

        def test_ambush_in_range_returns_chase(
            self, sm, attacker_id, attacker_coord
        ):
            """初期位置から範囲内なら CHASE"""
            initial = Coordinate(0, 0, 0)
            attacker_near = Coordinate(2, 0, 0)
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_near,
                ecology_type=EcologyTypeEnum.AMBUSH,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=initial,
                ambush_chase_range=5,
            )
            assert result.no_transition is False
            assert result.new_state == BehaviorStateEnum.CHASE

        def test_ambush_without_initial_position_treats_as_chase(
            self, sm, attacker_id, attacker_coord
        ):
            """behavior_initial_position が None なら AMBUSH でも遷移する"""
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_coord,
                ecology_type=EcologyTypeEnum.AMBUSH,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=None,
                ambush_chase_range=5,
            )
            assert result.no_transition is False
            assert result.new_state == BehaviorStateEnum.CHASE

        def test_ambush_without_range_treats_as_chase(
            self, sm, attacker_id, attacker_coord
        ):
            """ambush_chase_range が None なら遷移する"""
            initial = Coordinate(0, 0, 0)
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=Coordinate(50, 0, 0),
                ecology_type=EcologyTypeEnum.AMBUSH,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=initial,
                ambush_chase_range=None,
            )
            assert result.no_transition is False


class TestMonsterBehaviorStateMachineApplyTransition:
    """apply_transition のテスト"""

    @pytest.fixture
    def sm(self) -> MonsterBehaviorStateMachine:
        return MonsterBehaviorStateMachine()

    class TestEmptyResult:
        """空の StateTransitionResult"""

        def test_empty_result_returns_unchanged_state(self, sm):
            """空の result で状態は変わらない"""
            result = StateTransitionResult()
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.IDLE,
                current_target_id=None,
                current_last_known_position=None,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
            )
            assert output.final_state == BehaviorStateEnum.IDLE
            assert output.final_target_id is None
            assert output.final_last_known_position is None
            assert output.clear_pursuit is False
            assert output.sync_pursuit is None
            assert output.preserve_pursuit_last_known is None
            assert len(output.events) == 0

    class TestApplyEnrage:
        """apply_enrage の適用"""

        def test_apply_enrage_updates_state_and_emits_event(self, sm):
            result = StateTransitionResult(apply_enrage=True)
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.IDLE,
                current_target_id=None,
                current_last_known_position=None,
                hp_percentage=0.3,
                effective_flee_threshold=0.5,
                allow_chase=True,
            )
            assert output.final_state == BehaviorStateEnum.ENRAGE
            assert len(output.events) == 1
            ev = output.events[0]
            assert ev.kind == "actor_state_changed"
            assert ev.old_state == BehaviorStateEnum.IDLE
            assert ev.new_state == BehaviorStateEnum.ENRAGE

    class TestFleeFromThreat:
        """flee_from_threat の適用"""

        def test_flee_from_threat_updates_state_clears_pursuit(self, sm):
            flee_id = WorldObjectId(999)
            flee_coord = Coordinate(10, 10, 0)
            result = StateTransitionResult(
                flee_from_threat_id=flee_id,
                flee_from_threat_coordinate=flee_coord,
            )
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.IDLE,
                current_target_id=None,
                current_last_known_position=None,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
            )
            assert output.final_state == BehaviorStateEnum.FLEE
            assert output.final_target_id == flee_id
            assert output.final_last_known_position == flee_coord
            assert output.clear_pursuit is True
            assert output.sync_pursuit is None
            assert any(
                e.kind == "target_spotted" and e.target_id == flee_id
                for e in output.events
            )
            assert any(
                e.kind == "actor_state_changed" and e.new_state == BehaviorStateEnum.FLEE
                for e in output.events
            )

        def test_flee_with_apply_enrage_emits_both(self, sm):
            """apply_enrage と flee 両方のとき適切なイベント"""
            result = StateTransitionResult(
                apply_enrage=True,
                flee_from_threat_id=WorldObjectId(1),
                flee_from_threat_coordinate=Coordinate(2, 2, 0),
            )
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.IDLE,
                current_target_id=None,
                current_last_known_position=None,
                hp_percentage=0.2,
                effective_flee_threshold=0.5,
                allow_chase=True,
            )
            assert output.final_state == BehaviorStateEnum.FLEE
            assert any(e.kind == "actor_state_changed" for e in output.events)
            assert any(e.kind == "target_spotted" for e in output.events)

    class TestSpotTargetParams:
        """spot_target_params の適用"""

        def test_spot_target_chase_sync_pursuit(self, sm):
            target_id = WorldObjectId(2001)
            coord = Coordinate(2, 1, 0)
            result = StateTransitionResult(
                spot_target_params=SpotTargetParams(
                    target_id=target_id,
                    coordinate=coord,
                    effective_flee_threshold=0.0,
                    allow_chase=True,
                )
            )
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.IDLE,
                current_target_id=None,
                current_last_known_position=None,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
            )
            assert output.final_state == BehaviorStateEnum.CHASE
            assert output.final_target_id == target_id
            assert output.final_last_known_position == coord
            assert output.sync_pursuit == (target_id, coord)
            assert output.clear_pursuit is False
            assert any(
                e.kind == "target_spotted" and e.target_id == target_id
                for e in output.events
            )

        def test_spot_target_hp_low_goes_flee_clear_pursuit(self, sm):
            target_id = WorldObjectId(2001)
            coord = Coordinate(2, 1, 0)
            result = StateTransitionResult(
                spot_target_params=SpotTargetParams(
                    target_id=target_id,
                    coordinate=coord,
                    effective_flee_threshold=0.5,
                    allow_chase=True,
                )
            )
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.IDLE,
                current_target_id=None,
                current_last_known_position=None,
                hp_percentage=0.3,
                effective_flee_threshold=0.2,
                allow_chase=True,
            )
            assert output.final_state == BehaviorStateEnum.FLEE
            assert output.final_target_id == target_id
            assert output.clear_pursuit is True
            assert output.sync_pursuit is None

    class TestDoLoseTarget:
        """do_lose_target の適用"""

        def test_lose_target_chase_to_search_preserve_pursuit(self, sm):
            lost_id = WorldObjectId(321)
            last_known = Coordinate(7, 8, 0)
            result = StateTransitionResult(
                do_lose_target=True,
                lost_target_id=lost_id,
                last_known_coordinate=last_known,
            )
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.CHASE,
                current_target_id=lost_id,
                current_last_known_position=last_known,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
            )
            assert output.final_state == BehaviorStateEnum.SEARCH
            assert output.final_target_id == lost_id
            assert output.final_last_known_position == last_known
            assert output.preserve_pursuit_last_known == (lost_id, last_known)
            assert output.clear_pursuit is False
            assert any(
                e.kind == "target_lost" and e.target_id == lost_id
                for e in output.events
            )
            assert any(
                e.kind == "actor_state_changed"
                and e.old_state == BehaviorStateEnum.CHASE
                and e.new_state == BehaviorStateEnum.SEARCH
                for e in output.events
            )

        def test_lose_target_flee_to_return_clear_pursuit(self, sm):
            lost_id = WorldObjectId(321)
            result = StateTransitionResult(
                do_lose_target=True,
                lost_target_id=lost_id,
                last_known_coordinate=Coordinate(7, 8, 0),
            )
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.FLEE,
                current_target_id=lost_id,
                current_last_known_position=Coordinate(7, 8, 0),
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
            )
            assert output.final_state == BehaviorStateEnum.RETURN
            assert output.final_target_id is None
            assert output.final_last_known_position is None
            assert output.clear_pursuit is True
            assert output.preserve_pursuit_last_known is None

        def test_lose_target_reuses_existing_last_known_when_omitted(self, sm):
            """last_known_coordinate が None のとき current_last_known_position を再利用"""
            lost_id = WorldObjectId(2010)
            existing_last = Coordinate(6, 2, 0)
            result = StateTransitionResult(
                do_lose_target=True,
                lost_target_id=lost_id,
                last_known_coordinate=None,
            )
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.CHASE,
                current_target_id=lost_id,
                current_last_known_position=existing_last,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
            )
            assert output.final_state == BehaviorStateEnum.SEARCH
            assert output.final_last_known_position == existing_last
            assert output.preserve_pursuit_last_known == (lost_id, existing_last)


class TestMonsterBehaviorStateMachineShouldReturnToTerritory:
    """should_return_to_territory のテスト"""

    @pytest.fixture
    def sm(self) -> MonsterBehaviorStateMachine:
        return MonsterBehaviorStateMachine()

    def test_returns_false_when_territory_radius_none(self, sm):
        """territory_radius が None のとき False"""
        assert (
            sm.should_return_to_territory(
                actor_coordinate=Coordinate(100, 0, 0),
                behavior_initial_position=Coordinate(0, 0, 0),
                territory_radius=None,
                current_state=BehaviorStateEnum.CHASE,
            )
            is False
        )

    def test_returns_false_when_initial_position_none(self, sm):
        """behavior_initial_position が None のとき False"""
        assert (
            sm.should_return_to_territory(
                actor_coordinate=Coordinate(100, 0, 0),
                behavior_initial_position=None,
                territory_radius=5,
                current_state=BehaviorStateEnum.CHASE,
            )
            is False
        )

    def test_returns_false_when_not_chase_or_enrage(self, sm):
        """IDLE / FLEE / SEARCH / RETURN のとき False"""
        for state in (
            BehaviorStateEnum.IDLE,
            BehaviorStateEnum.FLEE,
            BehaviorStateEnum.SEARCH,
            BehaviorStateEnum.RETURN,
        ):
            assert (
                sm.should_return_to_territory(
                    actor_coordinate=Coordinate(100, 0, 0),
                    behavior_initial_position=Coordinate(0, 0, 0),
                    territory_radius=5,
                    current_state=state,
                )
                is False
            )

    def test_returns_true_when_outside_radius_chase(self, sm):
        """CHASE でテリトリ外なら True"""
        assert (
            sm.should_return_to_territory(
                actor_coordinate=Coordinate(10, 0, 0),
                behavior_initial_position=Coordinate(0, 0, 0),
                territory_radius=5,
                current_state=BehaviorStateEnum.CHASE,
            )
            is True
        )

    def test_returns_true_when_outside_radius_enrage(self, sm):
        """ENRAGE でテリトリ外なら True"""
        assert (
            sm.should_return_to_territory(
                actor_coordinate=Coordinate(10, 0, 0),
                behavior_initial_position=Coordinate(0, 0, 0),
                territory_radius=5,
                current_state=BehaviorStateEnum.ENRAGE,
            )
            is True
        )

    def test_returns_false_when_inside_radius(self, sm):
        """テリトリ内なら False"""
        assert (
            sm.should_return_to_territory(
                actor_coordinate=Coordinate(2, 0, 0),
                behavior_initial_position=Coordinate(0, 0, 0),
                territory_radius=10,
                current_state=BehaviorStateEnum.CHASE,
            )
            is False
        )

    def test_returns_false_when_territory_radius_zero(self, sm):
        """territory_radius が 0 のとき False"""
        assert (
            sm.should_return_to_territory(
                actor_coordinate=Coordinate(100, 0, 0),
                behavior_initial_position=Coordinate(0, 0, 0),
                territory_radius=0,
                current_state=BehaviorStateEnum.CHASE,
            )
            is False
        )
