"""
InMemoryMonsterRepository - 実際のMonsterクラスを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from ai_rpg_world.domain.monster.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.monster import Monster
from ai_rpg_world.domain.monster.drop_reward import DropReward
from ai_rpg_world.domain.player.base_status import BaseStatus
from ai_rpg_world.domain.battle.battle_enum import Race, Element
from ai_rpg_world.domain.battle.action_deck import ActionDeck
from ai_rpg_world.domain.battle.action_slot import ActionSlot
from ai_rpg_world.domain.battle.skill_capacity import SkillCapacity
from ai_rpg_world.domain.common.value_object import Gold, Exp


class InMemoryMonsterRepository(MonsterRepository):
    """実際のMonsterクラスを使用するインメモリリポジトリ"""
    
    def __init__(self):
        self._monsters: Dict[int, Monster] = {}
        
        # サンプルモンスターデータを作成
        self._setup_sample_data()
    
    def _setup_sample_data(self):
        """サンプルモンスターデータのセットアップ"""
        # スライム
        slime = self._create_sample_monster(
            monster_type_id=101,
            name="スライム",
            description="弱いゼリー状のモンスター",
            race=Race.BEAST,
            element=Element.WATER,
            max_hp=80,
            max_mp=20,
            base_status=BaseStatus(
                attack=25,
                defense=15,
                speed=10,
                critical_rate=0.02,
                evasion_rate=0.05
            ),
            drop_reward=DropReward(
                gold=Gold(50),
                exp=Exp(25),
                information=["[スライムは沼地に生息する弱いモンスターだ]"]
            ),
            allowed_areas=[100, 101, 102]
        )
        self._monsters[101] = slime
        
        # ゴブリン
        goblin = self._create_sample_monster(
            monster_type_id=102,
            name="ゴブリン",
            description="小柄で狡猾な緑色のモンスター",
            race=Race.GOBLIN,
            element=Element.EARTH,
            max_hp=120,
            max_mp=30,
            base_status=BaseStatus(
                attack=40,
                defense=25,
                speed=15,
                critical_rate=0.05,
                evasion_rate=0.08
            ),
            drop_reward=DropReward(
                gold=Gold(80),
                exp=Exp(40),
                information=["[ゴブリンは小柄で狡猾な緑色のモンスターだ]"]
            ),
            allowed_areas=[100, 101]
        )
        self._monsters[102] = goblin
        
        # オーク
        orc = self._create_sample_monster(
            monster_type_id=103,
            name="オーク",
            description="力強い戦士タイプのモンスター",
            race=Race.ORC,
            element=Element.FIRE,
            max_hp=200,
            max_mp=40,
            base_status=BaseStatus(
                attack=60,
                defense=40,
                speed=12,
                critical_rate=0.08,
                evasion_rate=0.03
            ),
            drop_reward=DropReward(
                gold=Gold(150),
                exp=Exp(75),
                information=["[オークは力強い戦士タイプのモンスターだ]"]
            ),
            allowed_areas=[101, 102]
        )
        self._monsters[103] = orc
    
    def _create_sample_monster(
        self,
        monster_type_id: int,
        name: str,
        description: str,
        race: Race,
        element: Element,
        max_hp: int,
        max_mp: int,
        base_status: BaseStatus,
        drop_reward: DropReward,
        allowed_areas: List[int]
    ) -> Monster:
        """サンプルモンスターを作成"""
        # アクションデッキ（基本攻撃のみ）
        capacity = SkillCapacity(max_capacity=5)
        basic_attack_slot = ActionSlot(action_id=1, level=1, cost=1)  # 基本攻撃
        action_deck = ActionDeck(slots=[basic_attack_slot], capacity=capacity)
        
        return Monster(
            monster_type_id=monster_type_id,
            name=name,
            description=description,
            race=race,
            element=element,
            base_status=base_status,
            max_hp=max_hp,
            max_mp=max_mp,
            action_deck=action_deck,
            drop_reward=drop_reward,
            allowed_areas=allowed_areas
        )
    
    def find_by_id(self, monster_type_id: int) -> Optional[Monster]:
        """モンスタータイプIDでモンスターを検索"""
        return self._monsters.get(monster_type_id)
    
    def find_by_ids(self, monster_type_ids: List[int]) -> List[Monster]:
        """複数のモンスタータイプIDでモンスターを検索"""
        result = []
        for monster_type_id in monster_type_ids:
            monster = self._monsters.get(monster_type_id)
            if monster:
                result.append(monster)
        return result
    
    def find_by_area(self, area_id: int) -> List[Monster]:
        """指定されたエリアに出現するモンスターを検索"""
        return [monster for monster in self._monsters.values()
                if area_id in monster._allowed_areas]
    
    def find_by_race(self, race: Race) -> List[Monster]:
        """指定された種族のモンスターを検索"""
        return [monster for monster in self._monsters.values()
                if monster.race == race]
    
    def find_by_element(self, element: Element) -> List[Monster]:
        """指定された属性のモンスターを検索"""
        return [monster for monster in self._monsters.values()
                if monster.element == element]
    
    def find_all(self) -> List[Monster]:
        """全てのモンスターを取得"""
        return list(self._monsters.values())
    
    def save(self, monster: Monster) -> Monster:
        """モンスターを保存"""
        self._monsters[monster.monster_type_id] = monster
        return monster
    
    def delete(self, monster_type_id: int) -> bool:
        """モンスターを削除"""
        if monster_type_id in self._monsters:
            del self._monsters[monster_type_id]
            return True
        return False
    
    def exists_by_id(self, monster_type_id: int) -> bool:
        """モンスタータイプIDが存在するかチェック"""
        return monster_type_id in self._monsters
    
    def count(self) -> int:
        """モンスターの総数を取得"""
        return len(self._monsters)
    
    def find_by_spot_id(self, spot_id: int) -> List[Monster]:
        """指定されたスポットに出現するモンスターを検索（エリア経由）"""
        # スポットからエリアを特定し、そのエリアに出現するモンスターを返す
        # 簡易実装: 全モンスターから該当するものを探す
        return [monster for monster in self._monsters.values()
                if spot_id in monster._allowed_areas]
    
    def generate_monster_id(self) -> int:
        """新しいモンスターIDを生成"""
        # 簡易実装: 最大IDに1を加える
        if not self._monsters:
            return 1
        return max(self._monsters.keys()) + 1
    
    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全てのモンスターを削除（テスト用）"""
        self._monsters.clear()
