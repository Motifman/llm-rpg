from typing import Dict, Optional, List, Set
from ai_rpg_world.domain.spot.area_repository import AreaRepository
from ai_rpg_world.domain.spot.area import Area


class AreaRepositoryImpl(AreaRepository):
    """AreaRepositoryの実装クラス"""

    def __init__(self):
        # 実際の実装ではデータベース接続など
        # ここではメモリ上にデータを保持する簡易実装
        self._areas: Dict[int, Area] = {}
        self._spot_area_mapping: Dict[int, int] = {}  # spot_id -> area_id
        self._next_id = 1
        
        # サンプルデータを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプルデータのセットアップ"""
        # テスト用のエリアを作成
        from ai_rpg_world.domain.spot.area import Area
        
        # エリア1: 森林地帯
        area1 = Area(
            area_id=1,
            name="森林地帯",
            description="モンスターが出現する森",
            spawn_monster_type_ids={1, 2, 3}  # スライム、ゴブリン、オーク
        )
        self._areas[1] = area1
        self._spot_area_mapping[1] = 1  # スポット1は森林地帯
        self._spot_area_mapping[2] = 1  # スポット2も森林地帯
        
        # エリア2: 洞窟
        area2 = Area(
            area_id=2,
            name="暗い洞窟",
            description="危険なモンスターが潜む洞窟",
            spawn_monster_type_ids={3, 4, 5}  # オーク、ドラゴン、デーモン
        )
        self._areas[2] = area2
        self._spot_area_mapping[3] = 2  # スポット3は洞窟

    def find_by_id(self, area_id: int) -> Optional[Area]:
        """エリアIDでエリアを検索"""
        return self._areas.get(area_id)

    def find_by_spot_id(self, spot_id: int) -> Optional[Area]:
        """スポットIDでエリアを検索"""
        area_id = self._spot_area_mapping.get(spot_id)
        if area_id:
            return self._areas.get(area_id)
        return None

    def save(self, area: Area) -> None:
        """エリアを保存"""
        self._areas[area.area_id] = area

    def delete(self, area_id: int) -> None:
        """エリアを削除"""
        if area_id in self._areas:
            del self._areas[area_id]

    def find_all(self) -> List[Area]:
        """全てのエリアを取得"""
        return list(self._areas.values())

    def exists_by_id(self, area_id: int) -> bool:
        """エリアIDが存在するかチェック"""
        return area_id in self._areas

    def count(self) -> int:
        """エリアの総数を取得"""
        return len(self._areas)

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全てのエリアを削除（テスト用）"""
        self._areas.clear()
        self._spot_area_mapping.clear()
        self._next_id = 1

    def generate_area_id(self) -> int:
        """新しいエリアIDを生成（テスト用）"""
        area_id = self._next_id
        self._next_id += 1
        return area_id

    def find_by_ids(self, area_ids: List[int]) -> List[Area]:
        """複数のエリアIDでエリアを検索"""
        result = []
        for area_id in area_ids:
            area = self._areas.get(area_id)
            if area:
                result.append(area)
        return result
