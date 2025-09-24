"""
InMemoryAreaRepository - 実際のAreaクラスを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from src.domain.spot.area_repository import AreaRepository
from src.domain.spot.area import Area


class InMemoryAreaRepository(AreaRepository):
    """実際のAreaクラスを使用するインメモリリポジトリ"""
    
    def __init__(self):
        self._areas: Dict[int, Area] = {}
        self._spot_to_area: Dict[int, int] = {}  # spot_id -> area_id のマッピング
        self._next_id = 1
        
        # サンプルエリアデータを作成
        self._setup_sample_data()
    
    def _setup_sample_data(self):
        """サンプルエリアデータのセットアップ"""
        # エリア1: 初心者の森
        forest_area = Area(
            area_id=1,
            name="初心者の森",
            description="冒険者が最初に訪れる安全な森",
            spawn_monster_type_ids={101, 102}  # スライム、ゴブリン
        )
        # スポット100を森エリアに追加
        forest_area.add_spot(100)
        self._areas[1] = forest_area
        self._spot_to_area[100] = 1
        
        # エリア2: 危険な洞窟
        cave_area = Area(
            area_id=2,
            name="危険な洞窟",
            description="強いモンスターが潜む危険な洞窟",
            spawn_monster_type_ids={102, 103}  # ゴブリン、オーク
        )
        # スポット101を洞窟エリアに追加
        cave_area.add_spot(101)
        self._areas[2] = cave_area
        self._spot_to_area[101] = 2
        
        # エリア3: 平和な街
        town_area = Area(
            area_id=3,
            name="平和な街",
            description="モンスターが出現しない安全な街",
            spawn_monster_type_ids=set()  # モンスター出現なし
        )
        # スポット102を街エリアに追加
        town_area.add_spot(102)
        self._areas[3] = town_area
        self._spot_to_area[102] = 3
        
        self._next_id = 4
    
    def find_by_id(self, area_id: int) -> Optional[Area]:
        """エリアIDでエリアを検索"""
        return self._areas.get(area_id)
    
    def find_by_ids(self, area_ids: List[int]) -> List[Area]:
        """複数のエリアIDでエリアを検索"""
        result = []
        for area_id in area_ids:
            area = self._areas.get(area_id)
            if area:
                result.append(area)
        return result
    
    def find_by_spot_id(self, spot_id: int) -> Optional[Area]:
        """スポットIDでエリアを検索"""
        area_id = self._spot_to_area.get(spot_id)
        if area_id:
            return self._areas.get(area_id)
        return None
    
    def find_by_name(self, name: str) -> Optional[Area]:
        """名前でエリアを検索"""
        for area in self._areas.values():
            if area.name == name:
                return area
        return None
    
    def find_all(self) -> List[Area]:
        """全てのエリアを取得"""
        return list(self._areas.values())
    
    def save(self, area: Area) -> Area:
        """エリアを保存"""
        self._areas[area.area_id] = area
        
        # スポットマッピングを更新
        for spot_id in area.spot_ids:
            self._spot_to_area[spot_id] = area.area_id
        
        return area
    
    def delete(self, area_id: int) -> bool:
        """エリアを削除"""
        if area_id in self._areas:
            area = self._areas[area_id]
            # スポットマッピングからも削除
            for spot_id in area.spot_ids:
                if spot_id in self._spot_to_area:
                    del self._spot_to_area[spot_id]
            del self._areas[area_id]
            return True
        return False
    
    def exists_by_id(self, area_id: int) -> bool:
        """エリアIDが存在するかチェック"""
        return area_id in self._areas
    
    def count(self) -> int:
        """エリアの総数を取得"""
        return len(self._areas)
    
    def generate_area_id(self) -> int:
        """新しいエリアIDを生成"""
        area_id = self._next_id
        self._next_id += 1
        return area_id
    
    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全てのエリアを削除（テスト用）"""
        self._areas.clear()
        self._spot_to_area.clear()
        self._next_id = 1
    
    def add_spot_to_area(self, area_id: int, spot_id: int) -> bool:
        """エリアにスポットを追加"""
        if area_id in self._areas:
            self._areas[area_id].add_spot(spot_id)
            self._spot_to_area[spot_id] = area_id
            return True
        return False
    
    def remove_spot_from_area(self, area_id: int, spot_id: int) -> bool:
        """エリアからスポットを削除"""
        if area_id in self._areas:
            self._areas[area_id].remove_spot(spot_id)
            if spot_id in self._spot_to_area:
                del self._spot_to_area[spot_id]
            return True
        return False
