"""
MonsterBehaviorStateMachine のテスト

正常ケース・例外ケース・境界ケースの網羅的検証。
"""

import pytest

from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
    EcologyTypeEnum,
)
from ai_rpg_world.domain.monster.service.behavior_state_transition_service import (
    SpotTargetParams,
    StateTransitionResult,
)
from ai_rpg_world.domain.monster.service.monster_behavior_state_machine import (
    MonsterBehaviorStateMachine,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


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
            assert result.new_target_id is None
            assert result.new_last_known_position is None
            assert result.clear_pursuit is False
            assert result.sync_pursuit is False

        @pytest.mark.parametrize(
            ("attacker_id", "attacker_coord"),
            [
                (WorldObjectId(200), Coordinate(5, 5, 0)),
                (WorldObjectId(99), Coordinate(1, 2, 0)),
            ],
            ids=["original_attacker", "former_result_input"],
        )
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

        @pytest.mark.parametrize(
            ("hp_percentage", "expected_state", "expected_clear", "expected_sync"),
            [
                (0.1, BehaviorStateEnum.FLEE, True, False),
                (0.2, BehaviorStateEnum.FLEE, True, False),
                (0.21, BehaviorStateEnum.CHASE, False, True),
            ],
            ids=["below_threshold", "at_threshold", "above_threshold"],
        )
        def test_normal_hp_boundary_selects_flee_or_chase(
            self, sm, attacker_id, attacker_coord,
            hp_percentage, expected_state, expected_clear, expected_sync,
        ):
            """NORMALはHP割合が閾値以下なら逃走し、直上なら攻撃者を追跡して情報を同期する。"""
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_coord,
                ecology_type=EcologyTypeEnum.NORMAL,
                hp_percentage=hp_percentage,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=None,
                ambush_chase_range=None,
            )
            assert result.no_transition is False
            assert result.new_state == expected_state
            assert result.new_target_id == attacker_id
            assert result.new_last_known_position == attacker_coord
            assert result.clear_pursuit is expected_clear
            assert result.sync_pursuit is expected_sync

        @pytest.mark.parametrize(
            ("attacker_id", "attacker_coord"),
            [
                (WorldObjectId(200), Coordinate(5, 5, 0)),
                (WorldObjectId(100), Coordinate(5, 5, 0)),
            ],
            ids=["original_attacker", "former_result_input"],
        )
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

        @pytest.mark.parametrize(
            "attacker_coordinate",
            [Coordinate(100, 0, 0), Coordinate(3, 3, 0)],
            ids=["distant_axis", "diagonal_manhattan_outside"],
        )
        def test_ambush_out_of_range_returns_no_transition(
            self, sm, attacker_id, attacker_coordinate
        ):
            """初期位置からのマンハッタン距離が範囲を超えれば、対角でも被弾遷移を拒否する。"""
            initial = Coordinate(0, 0, 0)
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_coordinate,
                ecology_type=EcologyTypeEnum.AMBUSH,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
                current_behavior_state=BehaviorStateEnum.IDLE,
                behavior_initial_position=initial,
                ambush_chase_range=5,
            )
            assert result.no_transition is True

        @pytest.mark.parametrize(
            "attacker_coordinate",
            [Coordinate(2, 0, 0), Coordinate(3, 2, 0)],
            ids=["inside_range", "at_manhattan_limit"],
        )
        def test_ambush_in_range_returns_chase(
            self, sm, attacker_id, attacker_coordinate
        ):
            """初期位置からのマンハッタン距離が範囲以下なら、境界ちょうどもCHASEを許可する。"""
            initial = Coordinate(0, 0, 0)
            result = sm.compute_attacked_transition(
                attacker_id=attacker_id,
                attacker_coordinate=attacker_coordinate,
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

        @pytest.mark.parametrize(
            ("current_state", "target_id", "position"),
            [
                (BehaviorStateEnum.IDLE, None, None),
                (BehaviorStateEnum.CHASE, WorldObjectId(4001), Coordinate(4, 6, 0)),
            ],
            ids=["original_idle_empty", "chase_with_target"],
        )
        def test_empty_result_preserves_current_state_and_target(
            self, sm, current_state, target_id, position
        ):
            """空の指示は状態・対象・位置を保持し、追跡の操作と通知を生成しない。"""
            result = StateTransitionResult()
            output = sm.apply_transition(
                result=result,
                current_state=current_state,
                current_target_id=target_id,
                current_last_known_position=position,
                hp_percentage=1.0,
                effective_flee_threshold=0.2,
                allow_chase=True,
            )
            assert output.final_state == current_state
            if target_id is None:
                assert output.final_target_id is None
            else:
                assert output.final_target_id == target_id
            if position is None:
                assert output.final_last_known_position is None
            else:
                assert output.final_last_known_position == position
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
            """単独の脅威逃走は対象と解除命令を返し、発見とIDLE→FLEEを各1件出力する。"""
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
            assert len(output.events) == 2
            spotted = [e for e in output.events if e.kind == "target_spotted"]
            assert len(spotted) == 1
            assert spotted[0].target_id == flee_id
            assert spotted[0].coordinate == flee_coord
            changed = [e for e in output.events if e.kind == "actor_state_changed"]
            assert len(changed) == 1
            assert changed[0].old_state == BehaviorStateEnum.IDLE
            assert changed[0].new_state == BehaviorStateEnum.FLEE

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

        @pytest.mark.parametrize(
            ("target_id", "coord", "hp_percentage", "param_flee", "param_allow",
             "default_flee", "default_allow", "expected_state"),
            [
                (WorldObjectId(2001), Coordinate(2, 1, 0), 1.0, 0.0, True,
                 0.2, True, BehaviorStateEnum.CHASE),
                (WorldObjectId(1), Coordinate(2, 3, 0), 1.0, 0.0, True,
                 0.2, True, BehaviorStateEnum.CHASE),
                (WorldObjectId(2001), Coordinate(2, 1, 0), 0.1, 0.0, True,
                 0.2, True, BehaviorStateEnum.CHASE),
                (WorldObjectId(2001), Coordinate(2, 1, 0), 1.0, 0.0, True,
                 0.2, False, BehaviorStateEnum.CHASE),
                (WorldObjectId(2001), Coordinate(2, 1, 0), 1.0, 0.0, False,
                 0.2, True, BehaviorStateEnum.IDLE),
                (WorldObjectId(2001), Coordinate(2, 1, 0), 1.0, None, None,
                 0.2, True, BehaviorStateEnum.CHASE),
            ],
            ids=[
                "original_chase", "former_spotted_spec", "explicit_zero_threshold",
                "explicit_true_chase_override", "explicit_false_chase_override",
                "unspecified_uses_defaults",
            ],
        )
        def test_spot_target_parameters_select_state_and_pursuit(
            self, sm, target_id, coord, hp_percentage, param_flee, param_allow,
            default_flee, default_allow, expected_state
        ):
            """明示した0/True/Falseを優先し、未指定だけ既定値を使って発見と追跡命令を返す。"""
            result = StateTransitionResult(
                spot_target_params=SpotTargetParams(
                    target_id=target_id,
                    coordinate=coord,
                    effective_flee_threshold=param_flee,
                    allow_chase=param_allow,
                )
            )
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.IDLE,
                current_target_id=None,
                current_last_known_position=None,
                hp_percentage=hp_percentage,
                effective_flee_threshold=default_flee,
                allow_chase=default_allow,
            )
            assert output.final_state == expected_state
            assert output.final_target_id == target_id
            assert output.final_last_known_position == coord
            if expected_state == BehaviorStateEnum.CHASE:
                assert output.sync_pursuit == (target_id, coord)
            else:
                assert output.sync_pursuit is None
            assert output.clear_pursuit is False
            assert output.preserve_pursuit_last_known is None
            spotted = [e for e in output.events if e.kind == "target_spotted"]
            assert len(spotted) == 1
            assert spotted[0].target_id == target_id
            assert spotted[0].coordinate == coord
            changed = [e for e in output.events if e.kind == "actor_state_changed"]
            if expected_state == BehaviorStateEnum.CHASE:
                assert len(output.events) == 2
                assert len(changed) == 1
                assert changed[0].old_state == BehaviorStateEnum.IDLE
                assert changed[0].new_state == BehaviorStateEnum.CHASE
            else:
                assert len(output.events) == 1
                assert len(changed) == 0

        @pytest.mark.parametrize(
            ("hp_percentage", "param_flee", "default_flee", "expected_state", "expected_clear"),
            [
                (0.3, 0.5, 0.2, BehaviorStateEnum.FLEE, True),
                (0.5, 0.5, 0.2, BehaviorStateEnum.FLEE, True),
                (0.51, 0.5, 0.2, BehaviorStateEnum.CHASE, False),
                (0.3, None, 0.5, BehaviorStateEnum.FLEE, True),
            ],
            ids=["original_below", "equal_threshold", "above_threshold", "unspecified_flee_uses_default"],
        )
        def test_spot_target_hp_boundary_selects_flee_or_chase(
            self, sm, hp_percentage, param_flee, default_flee, expected_state, expected_clear
        ):
            """HPが有効閾値以下なら逃走と解除、直上なら追跡を指示し、通知仕様を各1件返す。"""
            target_id = WorldObjectId(2001)
            coord = Coordinate(2, 1, 0)
            result = StateTransitionResult(
                spot_target_params=SpotTargetParams(
                    target_id=target_id,
                    coordinate=coord,
                    effective_flee_threshold=param_flee,
                    allow_chase=True,
                )
            )
            output = sm.apply_transition(
                result=result,
                current_state=BehaviorStateEnum.IDLE,
                current_target_id=None,
                current_last_known_position=None,
                hp_percentage=hp_percentage,
                effective_flee_threshold=default_flee,
                allow_chase=True,
            )
            assert output.final_state == expected_state
            assert output.final_target_id == target_id
            assert output.final_last_known_position == coord
            assert output.clear_pursuit is expected_clear
            if expected_clear:
                assert output.sync_pursuit is None
            else:
                assert output.sync_pursuit == (target_id, coord)
            assert output.preserve_pursuit_last_known is None
            assert len(output.events) == 2
            spotted = [e for e in output.events if e.kind == "target_spotted"]
            assert len(spotted) == 1
            assert spotted[0].target_id == target_id
            assert spotted[0].coordinate == coord
            changed = [e for e in output.events if e.kind == "actor_state_changed"]
            assert len(changed) == 1
            assert changed[0].old_state == BehaviorStateEnum.IDLE
            assert changed[0].new_state == expected_state

    class TestDoLoseTarget:
        """do_lose_target の適用"""

        @pytest.mark.parametrize(
            ("lost_id", "last_known"),
            [
                (WorldObjectId(321), Coordinate(7, 8, 0)),
                (WorldObjectId(2), Coordinate(4, 5, 0)),
            ],
            ids=["original_lost", "former_lost_spec"],
        )
        def test_lose_target_chase_to_search_preserve_pursuit(self, sm, lost_id, last_known):
            """CHASEの対象喪失は対象情報を保ってSEARCHへ移り、喪失と状態変更を各1件返す。"""
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
            assert len(output.events) == 2
            lost = [e for e in output.events if e.kind == "target_lost"]
            assert len(lost) == 1
            assert lost[0].target_id == lost_id
            assert lost[0].last_known_coordinate == last_known
            changed = [e for e in output.events if e.kind == "actor_state_changed"]
            assert len(changed) == 1
            assert changed[0].old_state == BehaviorStateEnum.CHASE
            assert changed[0].new_state == BehaviorStateEnum.SEARCH

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

    @pytest.mark.parametrize(
        ("actor_coordinate", "territory_radius", "expected"),
        [
            (Coordinate(2, 0, 0), 10, False),
            (Coordinate(3, 3, 0), 5, False),
            (Coordinate(3, 4, 0), 5, False),
            (Coordinate(4, 4, 0), 5, True),
        ],
        ids=["original_inside", "diagonal_inside", "exact_radius", "diagonal_outside"],
    )
    def test_return_decision_uses_euclidean_radius_boundary(
        self, sm, actor_coordinate, territory_radius, expected
    ):
        """CHASE は直線距離が半径を超えたときだけ帰還し、等値では帰還しない。"""
        assert (
            sm.should_return_to_territory(
                actor_coordinate=actor_coordinate,
                behavior_initial_position=Coordinate(0, 0, 0),
                territory_radius=territory_radius,
                current_state=BehaviorStateEnum.CHASE,
            )
            is expected
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
