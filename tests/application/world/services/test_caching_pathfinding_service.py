"""CachingPathfindingService の正常・境界・例外ケースの網羅的テスト"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.world.services.caching_pathfinding_service import (
    CachingPathfindingService,
)
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.pathfinding_strategy import PathfindingStrategy, PathfindingMap
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.exception.map_exception import (
    PathNotFoundException,
    InvalidPathRequestException,
)
from ai_rpg_world.domain.common.value_object import WorldTick


class TestCachingPathfindingService:
    """CachingPathfindingService の正常・境界・例外ケース"""

    @pytest.fixture
    def mock_delegate(self):
        """PathfindingService のモック（内部で strategy をモック）"""
        strategy = MagicMock(spec=PathfindingStrategy)
        return PathfindingService(strategy)

    @pytest.fixture
    def map_without_spot_id(self):
        """spot_id を持たないマップ（キャッシュ未使用）"""
        m = MagicMock(spec=PathfindingMap)
        m.is_passable.return_value = True
        # spot_id を意図的に持たせない（getattr(map_data, 'spot_id', None) が None になるように）
        if hasattr(m, "spot_id"):
            del m.spot_id
        return m

    @pytest.fixture
    def map_with_spot_id(self):
        """spot_id を持つマップ（キャッシュ使用）"""
        m = MagicMock(spec=PathfindingMap)
        m.spot_id = SpotId(1)
        m.is_passable.return_value = True
        return m

    @pytest.fixture
    def capability(self):
        return MovementCapability.normal_walk()

    @pytest.fixture
    def caching_service_no_ttl(self, mock_delegate):
        """TTL なしの CachingPathfindingService"""
        return CachingPathfindingService(mock_delegate)

    class TestCalculatePathWhenNoSpotId:
        """map_data に spot_id がない場合は常にデリゲートに委譲する"""

        def test_delegate_called_every_time(self, caching_service_no_ttl, map_without_spot_id, capability):
            """spot_id がないためキャッシュせず、毎回デリゲートが呼ばれる"""
            start = Coordinate(0, 0)
            goal = Coordinate(2, 2)
            path1 = [start, Coordinate(1, 1), goal]
            caching_service_no_ttl._delegate.calculate_path = MagicMock(return_value=path1)

            result1 = caching_service_no_ttl.calculate_path(
                start, goal, map_without_spot_id, capability, smooth_path=False
            )
            result2 = caching_service_no_ttl.calculate_path(
                start, goal, map_without_spot_id, capability, smooth_path=False
            )

            assert result1 == path1
            assert result2 == path1
            assert caching_service_no_ttl._delegate.calculate_path.call_count == 2

        def test_exception_from_delegate_propagates(self, caching_service_no_ttl, map_without_spot_id, capability):
            """spot_id がない場合でもデリゲートの例外はそのまま伝播する"""
            start = Coordinate(0, 0)
            goal = Coordinate(2, 2)
            caching_service_no_ttl._delegate.calculate_path = MagicMock(
                side_effect=InvalidPathRequestException("bad start")
            )

            with pytest.raises(InvalidPathRequestException, match="bad start"):
                caching_service_no_ttl.calculate_path(
                    start, goal, map_without_spot_id, capability
                )

    class TestCalculatePathCacheMissThenHit:
        """同一 (spot_id, goal, capability) で start が経路上にあるとキャッシュヒットする"""

        def test_first_call_delegates_second_call_hits_cache(
            self, caching_service_no_ttl, map_with_spot_id, capability
        ):
            """1回目はデリゲート、2回目は経路上の start でキャッシュヒット"""
            start = Coordinate(0, 0)
            mid = Coordinate(1, 1)
            goal = Coordinate(2, 2)
            full_path = [start, mid, goal]
            caching_service_no_ttl._delegate.calculate_path = MagicMock(return_value=full_path)

            result1 = caching_service_no_ttl.calculate_path(
                start, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert result1 == full_path
            assert caching_service_no_ttl._delegate.calculate_path.call_count == 1

            # 2回目: start を経路の途中 (mid) にするとキャッシュヒット
            result2 = caching_service_no_ttl.calculate_path(
                mid, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert result2 == [mid, goal]
            assert caching_service_no_ttl._delegate.calculate_path.call_count == 1

        def test_start_not_on_path_causes_miss_then_delegate(
            self, caching_service_no_ttl, map_with_spot_id, capability
        ):
            """start がキャッシュ経路上にない場合はミスし、デリゲートが再呼び出しされる"""
            start0 = Coordinate(0, 0)
            goal = Coordinate(2, 2)
            path0 = [start0, Coordinate(1, 1), goal]
            caching_service_no_ttl._delegate.calculate_path = MagicMock(return_value=path0)

            caching_service_no_ttl.calculate_path(
                start0, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert caching_service_no_ttl._delegate.calculate_path.call_count == 1

            # 経路上にない start で呼ぶ
            start_other = Coordinate(3, 3)
            path_other = [start_other, Coordinate(2, 3), goal]
            caching_service_no_ttl._delegate.calculate_path.return_value = path_other

            result = caching_service_no_ttl.calculate_path(
                start_other, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert result == path_other
            assert caching_service_no_ttl._delegate.calculate_path.call_count == 2

    class TestCalculatePathSameStartGoal:
        """開始点と目標が同じ場合の扱い"""

        def test_same_start_goal_delegates_once_then_cached(
            self, caching_service_no_ttl, map_with_spot_id, capability
        ):
            """start == goal はデリゲートが [start] を返す。キャッシュには [start] が入る"""
            start = Coordinate(0, 0)
            caching_service_no_ttl._delegate.calculate_path = MagicMock(return_value=[start])

            result1 = caching_service_no_ttl.calculate_path(
                start, start, map_with_spot_id, capability, smooth_path=False
            )
            assert result1 == [start]

            result2 = caching_service_no_ttl.calculate_path(
                start, start, map_with_spot_id, capability, smooth_path=False
            )
            assert result2 == [start]
            assert caching_service_no_ttl._delegate.calculate_path.call_count == 1

    class TestCalculatePathExceptionsPropagate:
        """デリゲートが投げる例外はそのまま伝播する"""

        def test_invalid_path_request_propagates(
            self, caching_service_no_ttl, map_with_spot_id, capability
        ):
            """InvalidPathRequestException は伝播する"""
            start = Coordinate(0, 0)
            goal = Coordinate(2, 2)
            caching_service_no_ttl._delegate.calculate_path = MagicMock(
                side_effect=InvalidPathRequestException(
                    "Start point (0, 0) is not passable"
                )
            )

            with pytest.raises(InvalidPathRequestException, match="not passable"):
                caching_service_no_ttl.calculate_path(
                    start, goal, map_with_spot_id, capability
                )

        def test_path_not_found_propagates(
            self, caching_service_no_ttl, map_with_spot_id, capability
        ):
            """PathNotFoundException は伝播する"""
            start = Coordinate(0, 0)
            goal = Coordinate(2, 2)
            caching_service_no_ttl._delegate.calculate_path = MagicMock(
                side_effect=PathNotFoundException("No path found")
            )

            with pytest.raises(PathNotFoundException, match="No path found"):
                caching_service_no_ttl.calculate_path(
                    start, goal, map_with_spot_id, capability, ignore_errors=False
                )

        def test_path_not_found_ignore_errors_returns_empty_no_cache(
            self, caching_service_no_ttl, map_with_spot_id, capability
        ):
            """ignore_errors=True で空リストが返る場合、キャッシュには格納しない"""
            start = Coordinate(0, 0)
            goal = Coordinate(2, 2)
            caching_service_no_ttl._delegate.calculate_path = MagicMock(return_value=[])

            result = caching_service_no_ttl.calculate_path(
                start, goal, map_with_spot_id, capability, ignore_errors=True
            )
            assert result == []
            assert len(caching_service_no_ttl._cache) == 0

    class TestCalculatePathReturnValueIsCopy:
        """返却リストの変更がキャッシュに影響しないこと"""

        def test_returned_path_is_copy(self, caching_service_no_ttl, map_with_spot_id, capability):
            """キャッシュヒットで返したリストを変更してもキャッシュの中身は変わらない"""
            start = Coordinate(0, 0)
            mid = Coordinate(1, 1)
            goal = Coordinate(2, 2)
            full_path = [start, mid, goal]
            caching_service_no_ttl._delegate.calculate_path = MagicMock(return_value=full_path)

            caching_service_no_ttl.calculate_path(
                start, goal, map_with_spot_id, capability, smooth_path=False
            )
            result = caching_service_no_ttl.calculate_path(
                mid, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert result == [mid, goal]

            result.append(Coordinate(99, 99))
            # 同じ条件で再度取得するとキャッシュから返るので、変更前の内容であること
            result2 = caching_service_no_ttl.calculate_path(
                mid, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert result2 == [mid, goal]

    class TestCalculatePathDifferentKeys:
        """異なるキーでは別キャッシュエントリになる"""

        def test_different_spot_id_different_cache(
            self, caching_service_no_ttl, map_with_spot_id, capability
        ):
            """spot_id が違うと別キャッシュ"""
            start = Coordinate(0, 0)
            goal = Coordinate(2, 2)
            path1 = [start, Coordinate(1, 1), goal]
            caching_service_no_ttl._delegate.calculate_path = MagicMock(return_value=path1)

            map_with_spot_id.spot_id = SpotId(1)
            caching_service_no_ttl.calculate_path(
                start, goal, map_with_spot_id, capability, smooth_path=False
            )

            map_with_spot_id.spot_id = SpotId(2)
            path2 = [start, Coordinate(1, 0), goal]
            caching_service_no_ttl._delegate.calculate_path.return_value = path2
            result = caching_service_no_ttl.calculate_path(
                start, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert result == path2
            assert caching_service_no_ttl._delegate.calculate_path.call_count == 2

        def test_different_goal_different_cache(
            self, caching_service_no_ttl, map_with_spot_id, capability
        ):
            """goal が違うと別キャッシュ"""
            start = Coordinate(0, 0)
            goal1 = Coordinate(2, 2)
            goal2 = Coordinate(3, 3)
            path1 = [start, Coordinate(1, 1), goal1]
            path2 = [start, Coordinate(2, 2), goal2]
            caching_service_no_ttl._delegate.calculate_path = MagicMock(side_effect=[path1, path2])

            r1 = caching_service_no_ttl.calculate_path(
                start, goal1, map_with_spot_id, capability, smooth_path=False
            )
            r2 = caching_service_no_ttl.calculate_path(
                start, goal2, map_with_spot_id, capability, smooth_path=False
            )
            assert r1 == path1
            assert r2 == path2
            assert caching_service_no_ttl._delegate.calculate_path.call_count == 2

        def test_different_smooth_path_different_cache(
            self, caching_service_no_ttl, map_with_spot_id, capability
        ):
            """smooth_path が違うと別キャッシュ"""
            start = Coordinate(0, 0)
            goal = Coordinate(2, 2)
            raw_path = [start, Coordinate(1, 1), goal]
            smoothed_path = [start, goal]
            map_with_spot_id.is_visible.return_value = True
            caching_service_no_ttl._delegate.calculate_path = MagicMock(
                side_effect=[raw_path, smoothed_path]
            )

            caching_service_no_ttl.calculate_path(
                start, goal, map_with_spot_id, capability, smooth_path=False
            )
            caching_service_no_ttl.calculate_path(
                start, goal, map_with_spot_id, capability, smooth_path=True
            )
            assert caching_service_no_ttl._delegate.calculate_path.call_count == 2

    class TestCalculatePathTTL:
        """TTL が設定されている場合の有効期限"""

        @pytest.fixture
        def time_provider(self):
            provider = MagicMock()
            provider.get_current_tick.return_value = WorldTick(10)
            return provider

        @pytest.fixture
        def caching_service_with_ttl(self, mock_delegate, time_provider):
            return CachingPathfindingService(
                mock_delegate,
                time_provider=time_provider,
                ttl_ticks=3,
            )

        def test_within_ttl_cache_hit(
            self, caching_service_with_ttl, map_with_spot_id, capability, time_provider
        ):
            """TTL 内ならキャッシュヒットする"""
            start = Coordinate(0, 0)
            mid = Coordinate(1, 1)
            goal = Coordinate(2, 2)
            full_path = [start, mid, goal]
            caching_service_with_ttl._delegate.calculate_path = MagicMock(return_value=full_path)

            caching_service_with_ttl.calculate_path(
                start, goal, map_with_spot_id, capability, smooth_path=False
            )
            time_provider.get_current_tick.return_value = WorldTick(12)
            result = caching_service_with_ttl.calculate_path(
                mid, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert result == [mid, goal]
            assert caching_service_with_ttl._delegate.calculate_path.call_count == 1

        def test_beyond_ttl_cache_miss(
            self, caching_service_with_ttl, map_with_spot_id, capability, time_provider
        ):
            """TTL を過ぎるとキャッシュミスし、デリゲートが再呼び出しされる"""
            start = Coordinate(0, 0)
            goal = Coordinate(2, 2)
            full_path = [start, Coordinate(1, 1), goal]
            caching_service_with_ttl._delegate.calculate_path = MagicMock(return_value=full_path)

            caching_service_with_ttl.calculate_path(
                start, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert caching_service_with_ttl._delegate.calculate_path.call_count == 1

            time_provider.get_current_tick.return_value = WorldTick(14)
            result = caching_service_with_ttl.calculate_path(
                start, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert result == full_path
            assert caching_service_with_ttl._delegate.calculate_path.call_count == 2

        def test_ttl_none_when_no_time_provider(self, mock_delegate, map_with_spot_id, capability):
            """time_provider を渡さない場合 TTL は適用されない"""
            service = CachingPathfindingService(mock_delegate, ttl_ticks=1)
            start = Coordinate(0, 0)
            mid = Coordinate(1, 1)
            goal = Coordinate(2, 2)
            full_path = [start, mid, goal]
            service._delegate.calculate_path = MagicMock(return_value=full_path)

            service.calculate_path(start, goal, map_with_spot_id, capability, smooth_path=False)
            result = service.calculate_path(
                mid, goal, map_with_spot_id, capability, smooth_path=False
            )
            assert result == [mid, goal]
            assert service._delegate.calculate_path.call_count == 1

    class TestCalculatePathDelegateArguments:
        """デリゲートに渡す引数が正しく渡ること"""

        def test_all_arguments_passed_to_delegate(
            self, caching_service_no_ttl, map_with_spot_id, capability
        ):
            """キャッシュミス時、全引数がそのままデリゲートに渡る"""
            start = Coordinate(0, 0)
            goal = Coordinate(2, 2)
            path = [start, Coordinate(1, 1), goal]
            caching_service_no_ttl._delegate.calculate_path = MagicMock(return_value=path)

            caching_service_no_ttl.calculate_path(
                start,
                goal,
                map_with_spot_id,
                capability,
                ignore_errors=True,
                max_iterations=500,
                allow_partial_path=True,
                smooth_path=False,
                exclude_object_id=None,
            )

            caching_service_no_ttl._delegate.calculate_path.assert_called_once_with(
                start=start,
                goal=goal,
                map_data=map_with_spot_id,
                capability=capability,
                ignore_errors=True,
                max_iterations=500,
                allow_partial_path=True,
                smooth_path=False,
                exclude_object_id=None,
            )
