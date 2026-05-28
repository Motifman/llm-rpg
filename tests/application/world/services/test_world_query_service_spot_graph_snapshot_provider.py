"""WorldQueryService の spot_graph_snapshot_provider 経路の挙動テスト。

Issue #227 PR-6 (tile-map 除去):
    SpotGraphAugmentingWorldQueryService Decorator を廃止し、WorldQueryService が
    PMR=None + Callable 経由で直接 spot_graph 用 DTO を組み立てるよう統合した。
    本ファイルはその経路の挙動を保証する。
"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerCurrentStateQuery,
)
from ai_rpg_world.application.world.services.world_query_service import (
    WorldQueryService,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.connected_spots_provider import (
    IConnectedSpotsProvider,
)
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def _make_service(snapshot_provider=None) -> tuple[WorldQueryService, MagicMock]:
    """tile-map なし (PMR=None) の WorldQueryService を返す。"""
    player_status_repo = MagicMock(spec=PlayerStatusRepository)
    player_profile_repo = MagicMock(spec=PlayerProfileRepository)
    spot_repo = MagicMock(spec=SpotRepository)
    connected_spots_provider = MagicMock(spec=IConnectedSpotsProvider)
    connected_spots_provider.get_connected_spots.return_value = []

    svc = WorldQueryService(
        player_status_repository=player_status_repo,
        player_profile_repository=player_profile_repo,
        physical_map_repository=None,
        spot_repository=spot_repo,
        connected_spots_provider=connected_spots_provider,
        spot_graph_snapshot_provider=snapshot_provider,
    )
    return svc, MagicMock(
        player_status_repo=player_status_repo,
        player_profile_repo=player_profile_repo,
        spot_repo=spot_repo,
    )


def _stub_player_at_spot(svc: WorldQueryService, *, player_id: int) -> None:
    """svc 内部の repo mock に「プレイヤーが SpotId(7) にいる」状態をセットする。"""
    player_status = MagicMock(spec=PlayerStatusAggregate)
    player_status.current_spot_id = SpotId(7)
    player_status.current_coordinate = Coordinate(x=1, y=2, z=0)
    svc._player_status_repository.find_by_id.return_value = player_status  # type: ignore[attr-defined]

    profile = MagicMock()
    profile.name.value = "テスト太郎"
    svc._player_profile_repository.find_by_id.return_value = profile  # type: ignore[attr-defined]

    spot = MagicMock()
    spot.name = "テスト広場"
    spot.description = "テスト用の広場"
    svc._spot_repository.find_by_id.return_value = spot  # type: ignore[attr-defined]


class TestWorldQueryServiceWithoutTileMap:
    """PMR=None 経路の get_player_current_state の挙動。"""

    def test_returns_dto_with_tile_fields_as_none(self) -> None:
        """PMR=None なら DTO の tile 由来 field は None / 空になる。"""
        svc, _ = _make_service()
        _stub_player_at_spot(svc, player_id=1)
        dto = svc.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=1, include_available_moves=False)
        )
        assert dto is not None
        assert dto.current_terrain_type is None
        assert dto.visible_tile_map is None
        assert dto.visible_objects == []
        # 天候は CLEAR デフォルト
        assert dto.weather_type == "CLEAR"
        assert dto.weather_intensity == 0.0

    def test_returns_dto_with_basic_player_info(self) -> None:
        """player_id / 名前 / spot 情報 / 座標は正しく埋まる。"""
        svc, _ = _make_service()
        _stub_player_at_spot(svc, player_id=1)
        dto = svc.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=1, include_available_moves=False)
        )
        assert dto is not None
        assert dto.player_id == 1
        assert dto.player_name == "テスト太郎"
        assert dto.current_spot_id == 7
        assert dto.current_spot_name == "テスト広場"
        assert dto.x == 1
        assert dto.y == 2

    def test_snapshot_provider_is_called_and_result_embedded(self) -> None:
        """snapshot_provider 注入時、player_id で呼ばれ結果が DTO に埋まる。"""
        provider = MagicMock(return_value="SNAP_OBJECT")
        svc, _ = _make_service(snapshot_provider=provider)
        _stub_player_at_spot(svc, player_id=42)
        dto = svc.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=42, include_available_moves=False)
        )
        provider.assert_called_once_with(42)
        assert dto is not None
        assert dto.spot_graph_snapshot == "SNAP_OBJECT"

    def test_snapshot_provider_omitted_means_no_snapshot(self) -> None:
        """provider 未注入時は spot_graph_snapshot=None。"""
        svc, _ = _make_service()
        _stub_player_at_spot(svc, player_id=1)
        dto = svc.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=1, include_available_moves=False)
        )
        assert dto is not None
        assert dto.spot_graph_snapshot is None

    def test_attach_provider_late_binds(self) -> None:
        """attach_spot_graph_snapshot_provider で後付け注入できる。"""
        svc, _ = _make_service()
        _stub_player_at_spot(svc, player_id=99)
        provider = MagicMock(return_value="LATE_BOUND_SNAP")
        svc.attach_spot_graph_snapshot_provider(provider)
        dto = svc.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=99, include_available_moves=False)
        )
        provider.assert_called_once_with(99)
        assert dto is not None
        assert dto.spot_graph_snapshot == "LATE_BOUND_SNAP"

    def test_returns_none_when_player_not_placed(self) -> None:
        """player_status が未配置なら None を返す (既存契約を維持)。"""
        svc, _ = _make_service()
        svc._player_status_repository.find_by_id.return_value = None  # type: ignore[attr-defined]
        dto = svc.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=1, include_available_moves=False)
        )
        assert dto is None
