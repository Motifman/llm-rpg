"""
テスト・デモ用のモックプレイヤークラス
実際のPlayerクラスの実装が完了するまでの暫定実装
"""

from typing import List
from src.domain.player.enum.player_enum import Role
from src.domain.battle.battle_enum import Element, Race
from src.domain.battle.action_deck import ActionDeck
from src.domain.battle.action_slot import ActionSlot
from src.domain.battle.skill_capacity import SkillCapacity
from src.domain.player.value_object.hp import Hp
from src.domain.player.value_object.mp import Mp


class MockPlayer:
    """モックプレイヤークラス"""
    
    def __init__(
        self,
        player_id: int,
        name: str,
        role: Role,
        race: Race,
        element: Element,
        current_spot_id: int,
        hp: Hp,
        mp: Mp,
        action_deck: ActionDeck,
        attack: int = 20,
        defense: int = 10,
        speed: int = 15,
        critical_rate: float = 0.1,
        evasion_rate: float = 0.1
    ):
        self.player_id = player_id
        self.name = name
        self.role = role
        self.race = race
        self.element = element
        self.current_spot_id = current_spot_id
        self.hp = hp
        self.mp = mp
        self.action_deck = action_deck
        self.attack = attack
        self.defense = defense
        self.speed = speed
        self.critical_rate = critical_rate
        self.evasion_rate = evasion_rate

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


def create_mock_players() -> List[MockPlayer]:
    """テスト用のモックプレイヤーを作成"""
    
    # プレイヤー1: 冒険者
    player_deck1 = ActionDeck(
        slots=[ActionSlot(1, 1, 1), ActionSlot(2, 1, 1)],  # 基本攻撃、防御
        capacity=SkillCapacity(10)
    )
    
    player1 = MockPlayer(
        player_id=1,
        name="テスト冒険者",
        role=Role.ADVENTURER,
        race=Race.HUMAN,
        element=Element.NEUTRAL,
        current_spot_id=1,
        hp=Hp(100, 100),
        mp=Mp(50, 50),
        action_deck=player_deck1,
        attack=25,
        defense=15,
        speed=12
    )
    
    # プレイヤー2: 魔法使い
    player_deck2 = ActionDeck(
        slots=[ActionSlot(1, 1, 1), ActionSlot(4, 1, 2), ActionSlot(6, 1, 2)],  # 基本攻撃、ファイアボール、ヒール
        capacity=SkillCapacity(15)
    )
    
    player2 = MockPlayer(
        player_id=2,
        name="テスト魔法使い",
        role=Role.ALCHEMIST,
        race=Race.HUMAN,
        element=Element.FIRE,
        current_spot_id=1,
        hp=Hp(80, 80),
        mp=Mp(100, 100),
        action_deck=player_deck2,
        attack=18,
        defense=8,
        speed=16
    )
    
    return [player1, player2]
