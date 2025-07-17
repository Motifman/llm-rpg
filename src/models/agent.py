from typing import List
from .item import Item


class Agent:
    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name
        # エージェントの状態
        self.items: List[Item] = []
        self.discovered_info: List[str] = []
        self.current_spot_id: str = ""
        self.experience_points: int = 0
        self.money: int = 0

    def add_item(self, item: Item):
        self.items.append(item)

    def remove_item(self, item: Item):
        self.items.remove(item)
    
    # TODO アイテムの所持状況を確認するメソッド、アイテムが重複所持が許さない場合にこれを使用する
    def has_item(self, item_id: str) -> bool:
        return any(item.item_id == item_id for item in self.items)
    
    def get_items(self) -> List[Item]:
        return self.items
    
    def get_item_by_id(self, item_id: str) -> Item:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None
    
    def get_current_spot_id(self) -> str:
        return self.current_spot_id
    
    def set_current_spot_id(self, spot_id: str):
        self.current_spot_id = spot_id
    
    # TODO 探索情報を取得するメソッド、探索情報の管理方法は今後変更する可能性がある
    def get_discovered_info(self) -> List[str]:
        return self.discovered_info
    
    def add_discovered_info(self, discovered_info: str):
        self.discovered_info.append(discovered_info)
    
    def get_experience_points(self) -> int:
        return self.experience_points
    
    def add_experience_points(self, experience_points: int):
        self.experience_points += experience_points
        if self.experience_points < 0:
            self.experience_points = 0
    
    def get_money(self) -> int:
        return self.money
    
    def add_money(self, money: int):
        self.money += money
        if self.money < 0:
            self.money = 0
    
    def __str__(self):
        return f"Agent(agent_id={self.agent_id}, name={self.name}, items={self.items}, current_spot_id={self.current_spot_id}, experience_points={self.experience_points}, money={self.money})"
    
    def __repr__(self):
        return f"Agent(agent_id={self.agent_id}, name={self.name}, items={self.items}, current_spot_id={self.current_spot_id}, experience_points={self.experience_points}, money={self.money})"