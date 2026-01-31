"""
テスト・デモ用のモックモンスタークラス
実際のMonsterクラスの実装が完了するまでの暫定実装
"""

from typing import List
from ai_rpg_world.domain.battle.battle_enum import Element, Race
from ai_rpg_world.domain.battle.action_deck import ActionDeck
from ai_rpg_world.domain.battle.action_slot import ActionSlot
from ai_rpg_world.domain.battle.skill_capacity import SkillCapacity
from ai_rpg_world.domain.monster.drop_reward import DropReward


class MockMonster:
    """モックモンスタークラス"""
    
    def __init__(
        self,
        monster_type_id: int,
        name: str,
        race: Race,
        element: Element,
        max_hp: int,
        max_mp: int,
        attack: int,
        defense: int,
        speed: int,
        critical_rate: float,
        evasion_rate: float,
        action_deck: ActionDeck
    ):
        self.monster_type_id = monster_type_id
        self.name = name
        self.race = race
        self.element = element
        self.max_hp = max_hp
        self.max_mp = max_mp
        self.attack = attack
        self.defense = defense
        self.speed = speed
        self.critical_rate = critical_rate
        self.evasion_rate = evasion_rate
        self.action_deck = action_deck

    def calculate_status_including_equipment(self):
        """装備を含むステータス計算（モック版）"""
        from dataclasses import dataclass
        
        @dataclass
        class MockStatus:
            attack: int
            defense: int
            speed: int
            critical_rate: float
            evasion_rate: float
        
        return MockStatus(
            attack=self.attack,
            defense=self.defense,
            speed=self.speed,
            critical_rate=self.critical_rate,
            evasion_rate=self.evasion_rate
        )

    def get_drop_reward(self) -> DropReward:
        """ドロップ報酬を取得（モック版）"""
        # 簡易的なドロップ報酬を返す
        return DropReward(
            gold=10 * self.monster_type_id,
            experience=5 * self.monster_type_id,
            items={}
        )


def create_mock_monsters() -> List[MockMonster]:
    """テスト用のモックモンスターを作成"""
    
    # モンスター1: スライム
    slime_deck = ActionDeck(
        slots=[ActionSlot(1, 1, 1)],  # 基本攻撃
        capacity=SkillCapacity(5)
    )
    
    slime = MockMonster(
        monster_type_id=1,
        name="スライム",
        race=Race.GOBLIN,  # 利用可能なRaceに変更
        element=Element.WATER,
        max_hp=50,
        max_mp=20,
        attack=15,
        defense=5,
        speed=10,
        critical_rate=0.05,
        evasion_rate=0.1,
        action_deck=slime_deck
    )
    
    # モンスター2: ゴブリン
    goblin_deck = ActionDeck(
        slots=[ActionSlot(1, 1, 1), ActionSlot(4, 1, 2)],  # 基本攻撃、ファイアボール
        capacity=SkillCapacity(10)
    )
    
    goblin = MockMonster(
        monster_type_id=2,
        name="ゴブリン",
        race=Race.GOBLIN,
        element=Element.FIRE,
        max_hp=80,
        max_mp=40,
        attack=25,
        defense=10,
        speed=15,
        critical_rate=0.1,
        evasion_rate=0.15,
        action_deck=goblin_deck
    )
    
    # モンスター3: オーク
    orc_deck = ActionDeck(
        slots=[ActionSlot(1, 1, 1), ActionSlot(6, 1, 2)],  # 基本攻撃、ヒール
        capacity=SkillCapacity(15)
    )
    
    orc = MockMonster(
        monster_type_id=3,
        name="オーク",
        race=Race.ORC,
        element=Element.EARTH,
        max_hp=120,
        max_mp=30,
        attack=35,
        defense=20,
        speed=8,
        critical_rate=0.08,
        evasion_rate=0.05,
        action_deck=orc_deck
    )
    
    return [slime, goblin, orc]
