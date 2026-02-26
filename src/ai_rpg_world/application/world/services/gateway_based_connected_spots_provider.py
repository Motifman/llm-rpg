"""ゲートウェイから接続グラフを導出する接続スポットプロバイダ。"""

from typing import List
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class GatewayBasedConnectedSpotsProvider(IConnectedSpotsProvider):
    """全 PhysicalMap のゲートウェイ定義から「from_spot_id → [to_spot_id, ...]」を組み立てて接続を提供する。"""

    def __init__(self, physical_map_repository: PhysicalMapRepository):
        self._physical_map_repository = physical_map_repository

    def get_connected_spots(self, spot_id: SpotId) -> List[SpotId]:
        connected: List[SpotId] = []
        for physical_map in self._physical_map_repository.find_all():
            if physical_map.spot_id != spot_id:
                continue
            for gateway in physical_map.get_all_gateways():
                connected.append(gateway.target_spot_id)
        return list(dict.fromkeys(connected))  # 重複除去・順序保持
