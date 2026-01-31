from typing import Dict, Optional, List
from ai_rpg_world.domain.monster.monster_repository import MonsterRepository
from ai_rpg_world.infrastructure.mocks.mock_monster import MockMonster, create_mock_monsters


class MonsterRepositoryImpl(MonsterRepository):
    """MonsterRepositoryの実装クラス（モック版）"""

    def __init__(self):
        # 実際の実装ではデータベース接続など
        # ここではメモリ上にデータを保持する簡易実装
        self._monsters: Dict[int, MockMonster] = {}
        self._next_id = 1
        
        # サンプルデータを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプルモンスターデータのセットアップ"""
        mock_monsters = create_mock_monsters()
        for monster in mock_monsters:
            self._monsters[monster.monster_type_id] = monster

    def find_by_id(self, monster_type_id: int) -> Optional[MockMonster]:
        """モンスター種類IDでモンスターを検索"""
        return self._monsters.get(monster_type_id)

    def find_by_ids(self, monster_type_ids: List[int]) -> List[MockMonster]:
        """複数のモンスター種類IDでモンスターを検索"""
        result = []
        for monster_type_id in monster_type_ids:
            monster = self._monsters.get(monster_type_id)
            if monster:
                result.append(monster)
        return result

    def save(self, monster: MockMonster) -> None:
        """モンスターを保存"""
        self._monsters[monster.monster_type_id] = monster

    def delete(self, monster_type_id: int) -> None:
        """モンスターを削除"""
        if monster_type_id in self._monsters:
            del self._monsters[monster_type_id]

    def find_all(self) -> List[MockMonster]:
        """全てのモンスターを取得"""
        return list(self._monsters.values())

    def exists_by_id(self, monster_type_id: int) -> bool:
        """モンスター種類IDが存在するかチェック"""
        return monster_type_id in self._monsters

    def count(self) -> int:
        """モンスターの総数を取得"""
        return len(self._monsters)

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全てのモンスターを削除（テスト用）"""
        self._monsters.clear()
        self._next_id = 1

    def generate_monster_id(self) -> int:
        """新しいモンスターIDを生成（テスト用）"""
        monster_id = self._next_id
        self._next_id += 1
        return monster_id

    def find_by_spot_id(self, spot_id: int) -> List[MockMonster]:
        """指定されたスポットのモンスターを検索（デモ用）"""
        # 実際の実装では、スポットに応じたモンスターを返す
        # ここでは全モンスターを返す簡易実装
        return self.find_all()
