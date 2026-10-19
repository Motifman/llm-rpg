"""
MonsterBehaviorState のテスト

正常ケース・例外ケース・境界ケースの網羅的検証。
"""

import pytest

from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterStatsValidationException,
)
from ai_rpg_world.domain.monster.service.monster_behavior_state_machine import (
    AttackedTransitionResult,
    EventSpec,
    TransitionApplicationOutput,
)
from ai_rpg_world.domain.monster.value_object.monster_behavior_state import MonsterBehaviorState
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestMonsterBehaviorStateCreateIdle:
    """create_idle のテスト"""

    def test_creates_idle_state_with_defaults(self):
        """IDLE 状態、target 等は None"""
        state = MonsterBehaviorState.create_idle()
        assert state.state == BehaviorStateEnum.IDLE
        assert state.target_id is None
        assert state.last_known_position is None
        assert state.initial_position is None
        assert state.patrol_index == 0
        assert state.search_timer == 0
        assert state.failure_count == 0

    def test_creates_idle_with_initial_position(self):
        """initial_position を指定"""
        coord = Coordinate(10, 20, 0)
        state = MonsterBehaviorState.create_idle(initial_position=coord)
        assert state.initial_position == coord


class TestMonsterBehaviorStateFromParts:
    """from_parts のテスト"""

    def test_builds_from_individual_fields(self):
        """個別フィールドから構築"""
        target_id = WorldObjectId(1001)
        last_known = Coordinate(5, 6, 0)
        initial = Coordinate(1, 2, 0)
        state = MonsterBehaviorState.from_parts(
            state=BehaviorStateEnum.CHASE,
            target_id=target_id,
            last_known_position=last_known,
            initial_position=initial,
            patrol_index=2,
            search_timer=5,
            failure_count=1,
        )
        assert state.state == BehaviorStateEnum.CHASE
        assert state.target_id == target_id
        assert state.last_known_position == last_known
        assert state.initial_position == initial
        assert state.patrol_index == 2
        assert state.search_timer == 5
        assert state.failure_count == 1

    def test_clamps_negative_values_to_zero(self):
        """負の値は 0 にクランプ"""
        state = MonsterBehaviorState.from_parts(
            state=BehaviorStateEnum.IDLE,
            target_id=None,
            last_known_position=None,
            initial_position=None,
            patrol_index=-1,
            search_timer=-2,
            failure_count=-1,
        )
        assert state.patrol_index == 0
        assert state.search_timer == 0
        assert state.failure_count == 0


class TestMonsterBehaviorStateValidation:
    """バリデーションのテスト"""

    def test_rejects_negative_patrol_index(self):
        """patrol_index < 0 で例外"""
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            MonsterBehaviorState(
                state=BehaviorStateEnum.IDLE,
                target_id=None,
                last_known_position=None,
                initial_position=None,
                patrol_index=-1,
                search_timer=0,
                failure_count=0,
            )
        assert "patrol_index" in str(exc_info.value).lower()

    def test_rejects_negative_search_timer(self):
        """search_timer < 0 で例外"""
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            MonsterBehaviorState(
                state=BehaviorStateEnum.IDLE,
                target_id=None,
                last_known_position=None,
                initial_position=None,
                patrol_index=0,
                search_timer=-1,
                failure_count=0,
            )
        assert "search_timer" in str(exc_info.value).lower()

    def test_rejects_negative_failure_count(self):
        """failure_count < 0 で例外"""
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            MonsterBehaviorState(
                state=BehaviorStateEnum.IDLE,
                target_id=None,
                last_known_position=None,
                initial_position=None,
                patrol_index=0,
                search_timer=0,
                failure_count=-1,
            )
        assert "failure_count" in str(exc_info.value).lower()


class TestMonsterBehaviorStateWithAttacked:
    """with_attacked のテスト"""

    @pytest.fixture
    def base_state(self) -> MonsterBehaviorState:
        return MonsterBehaviorState.from_parts(
            state=BehaviorStateEnum.IDLE,
            target_id=None,
            last_known_position=None,
            initial_position=Coordinate(0, 0, 0),
        )

    def test_no_transition_returns_self(self, base_state: MonsterBehaviorState):
        """no_transition のときは self を返す"""
        transition = AttackedTransitionResult(no_transition=True)
        result = base_state.with_attacked(transition)
        assert result is base_state

    def test_applies_transition_when_not_no_transition(self, base_state: MonsterBehaviorState):
        """遷移結果を適用"""
        transition = AttackedTransitionResult(
            no_transition=False,
            new_state=BehaviorStateEnum.FLEE,
            new_target_id=WorldObjectId(2001),
            new_last_known_position=Coordinate(10, 10, 0),
            clear_pursuit=True,
            sync_pursuit=False,
        )
        result = base_state.with_attacked(transition)
        assert result.state == BehaviorStateEnum.FLEE
        assert result.target_id == WorldObjectId(2001)
        assert result.last_known_position == Coordinate(10, 10, 0)
        assert result.initial_position == Coordinate(0, 0, 0)
        assert result.patrol_index == 0
        assert result is not base_state


class TestMonsterBehaviorStateWithTransition:
    """with_transition のテスト"""

    @pytest.fixture
    def base_state(self) -> MonsterBehaviorState:
        return MonsterBehaviorState.from_parts(
            state=BehaviorStateEnum.CHASE,
            target_id=WorldObjectId(3001),
            last_known_position=Coordinate(1, 1, 0),
            initial_position=Coordinate(0, 0, 0),
        )

    @pytest.mark.parametrize(
        "target_id",
        [WorldObjectId(3001), WorldObjectId(3002)],
        ids=["original_target", "different_target"],
    )
    def test_applies_transition_output(self, base_state: MonsterBehaviorState, target_id):
        """出力の状態・位置・対象を適用し、元の初期位置を保持する。"""
        output = TransitionApplicationOutput(
            final_state=BehaviorStateEnum.SEARCH,
            final_target_id=target_id,
            final_last_known_position=Coordinate(2, 2, 0),
            clear_pursuit=False,
            sync_pursuit=None,
            preserve_pursuit_last_known=None,
            events=[],
        )
        result = base_state.with_transition(output)
        assert result.state == BehaviorStateEnum.SEARCH
        assert result.target_id == target_id
        assert result.last_known_position == Coordinate(2, 2, 0)
        assert result.initial_position == base_state.initial_position
        assert result is not base_state

    def test_handles_none_target_and_position(self, base_state: MonsterBehaviorState):
        """target_id と last_known_position が None のケース"""
        output = TransitionApplicationOutput(
            final_state=BehaviorStateEnum.RETURN,
            final_target_id=None,
            final_last_known_position=None,
        )
        result = base_state.with_transition(output)
        assert result.target_id is None
        assert result.last_known_position is None


class TestMonsterBehaviorStateWithTerritoryReturn:
    """with_territory_return のテスト"""

    @pytest.fixture
    def chase_state(self) -> MonsterBehaviorState:
        return MonsterBehaviorState.from_parts(
            state=BehaviorStateEnum.CHASE,
            target_id=WorldObjectId(4001),
            last_known_position=Coordinate(5, 5, 0),
            initial_position=Coordinate(0, 0, 0),
            patrol_index=3,
        )

    def test_sets_return_and_clears_target(self, chase_state: MonsterBehaviorState):
        """RETURN に遷移し target をクリア"""
        result = chase_state.with_territory_return()
        assert result.state == BehaviorStateEnum.RETURN
        assert result.target_id is None
        assert result.last_known_position is None
        assert result.initial_position == chase_state.initial_position
        assert result.patrol_index == chase_state.patrol_index


class TestMonsterBehaviorStateWithSpawnReset:
    """with_spawn_reset のテスト"""

    @pytest.mark.parametrize(
        ("search_timer", "failure_count"),
        [(0, 0), (5, 3)],
        ids=["original_zero_counters", "nonzero_counters"],
    )
    def test_resets_to_idle_with_initial_position(self, search_timer, failure_count):
        """出現時はIDLEと新しい初期位置へ戻し、非ゼロの探索・失敗回数も消す。"""
        state = MonsterBehaviorState.from_parts(
            state=BehaviorStateEnum.SEARCH,
            target_id=WorldObjectId(5001),
            last_known_position=Coordinate(1, 1, 0),
            initial_position=Coordinate(0, 0, 0),
            patrol_index=2,
            search_timer=search_timer,
            failure_count=failure_count,
        )
        assert state.search_timer == search_timer
        assert state.failure_count == failure_count
        new_pos = Coordinate(100, 200, 0)
        result = state.with_spawn_reset(new_pos)
        assert result.state == BehaviorStateEnum.IDLE
        assert result.target_id is None
        assert result.last_known_position is None
        assert result.initial_position == new_pos
        assert result.patrol_index == 0
        assert result.search_timer == 0
        assert result.failure_count == 0


class TestMonsterBehaviorStateWithTargetCleared:
    """with_target_cleared のテスト"""

    def test_clears_target_keeps_state(self):
        """target と last_known をクリア、state は維持"""
        state = MonsterBehaviorState.from_parts(
            state=BehaviorStateEnum.SEARCH,
            target_id=WorldObjectId(6001),
            last_known_position=Coordinate(3, 4, 0),
            initial_position=Coordinate(0, 0, 0),
        )
        result = state.with_target_cleared()
        assert result.state == BehaviorStateEnum.SEARCH
        assert result.target_id is None
        assert result.last_known_position is None
        assert result.initial_position == state.initial_position
        assert result.patrol_index == state.patrol_index


class TestMonsterBehaviorStateAdvancePatrolIndex:
    """advance_patrol_index のテスト"""

    def test_advances_index(self):
        """パトロールインデックスが進む"""
        state = MonsterBehaviorState.from_parts(
            state=BehaviorStateEnum.IDLE,
            target_id=None,
            last_known_position=None,
            initial_position=None,
            patrol_index=1,
        )
        result = state.advance_patrol_index(4)
        assert result.patrol_index == 2
        assert result is not state

    def test_wraps_around_at_count(self):
        """patrol_points_count でラップする"""
        state = MonsterBehaviorState.from_parts(
            state=BehaviorStateEnum.IDLE,
            target_id=None,
            last_known_position=None,
            initial_position=None,
            patrol_index=2,
        )
        result = state.advance_patrol_index(3)
        assert result.patrol_index == 0

    @pytest.mark.parametrize(
        ("make_state", "patrol_points_count"),
        [
            pytest.param(MonsterBehaviorState.create_idle, 0, id="zero_count"),
            pytest.param(MonsterBehaviorState.create_idle, -1, id="minus_one_count"),
            pytest.param(
                lambda: MonsterBehaviorState.from_parts(
                    state=BehaviorStateEnum.IDLE,
                    target_id=None,
                    last_known_position=None,
                    initial_position=None,
                    patrol_index=1,
                ),
                -5,
                id="minus_five_nonzero_index",
            ),
        ],
    )
    def test_nonpositive_count_returns_self(self, make_state, patrol_points_count):
        """点数0/-1/-5では巡回を進めず、元の同じ実体を返す。"""
        state = make_state()
        result = state.advance_patrol_index(patrol_points_count)
        assert result is state


class TestMonsterBehaviorStateImmutability:
    """既存6操作は初期状態の公開値を変えず、新しい実体を返す。"""

    @pytest.mark.parametrize(
        "update",
        [
            pytest.param(
                lambda state: state.with_attacked(
                    AttackedTransitionResult(
                        no_transition=False,
                        new_state=BehaviorStateEnum.FLEE,
                        new_target_id=WorldObjectId(1),
                        new_last_known_position=Coordinate(1, 1, 0),
                        clear_pursuit=True,
                        sync_pursuit=False,
                    )
                ),
                id="attacked",
            ),
            pytest.param(
                lambda state: state.with_transition(
                    TransitionApplicationOutput(
                        final_state=BehaviorStateEnum.IDLE,
                        final_target_id=None,
                        final_last_known_position=None,
                    )
                ),
                id="transition_noop",
            ),
            pytest.param(lambda state: state.with_territory_return(), id="territory_return"),
            pytest.param(
                lambda state: state.with_spawn_reset(Coordinate(1, 1, 0)),
                id="spawn_reset",
            ),
            pytest.param(lambda state: state.with_target_cleared(), id="clear_empty_target"),
            pytest.param(lambda state: state.advance_patrol_index(3), id="advance_patrol"),
        ],
    )
    def test_updates_preserve_original_state_and_return_new_instance(self, update):
        """初期IDLEへの6操作は別実体を返し、元の公開11項目は初期値を保つ。"""
        state = MonsterBehaviorState.create_idle(initial_position=Coordinate(0, 0, 0))
        result = update(state)
        assert result is not state
        assert (
            state.state,
            state.target_id,
            state.last_known_position,
            state.initial_position,
            state.patrol_index,
            state.search_timer,
            state.failure_count,
            state.last_observed_target_spot_id,
            state.flee_until_tick,
            state.chase_attacker_ref,
            state.chase_started_at_tick,
        ) == (
            BehaviorStateEnum.IDLE,
            None,
            None,
            Coordinate(0, 0, 0),
            0,
            0,
            0,
            None,
            None,
            None,
            None,
        )
