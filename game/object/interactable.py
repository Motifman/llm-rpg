from typing import List, Dict, Set, Optional, TYPE_CHECKING
from abc import ABC, abstractmethod
from collections import deque

if TYPE_CHECKING:
    from game.action.action_strategy import ActionStrategy


class InteractableObject(ABC):
    def __init__(self, object_id: str, description: str):
        self.object_id = object_id
        self.description = description
        self._possible_actions: Dict[str, 'ActionStrategy'] = {}

    def get_possible_actions(self) -> Dict[str, 'ActionStrategy']:
        return self._possible_actions

    def get_object_id(self) -> str:
        return self.object_id
    
    def get_description(self) -> str:
        return self.description
    
    def __str__(self):
        return f"InteractableObject(id='{self.object_id}')"
    
    def __repr__(self):
        return f"InteractableObject(id='{self.object_id}')"


class BulletinBoard(InteractableObject):
    """掲示板オブジェクト - 4つのスペースを持つ書き込み可能な掲示板"""
    
    def __init__(self, object_id: str, description: str = "木製の掲示板"):
        super().__init__(object_id, description)
        self._posts = deque(maxlen=4)  # 最大4つの投稿を保持
        self.display_name = "掲示板"
    
    def get_display_name(self) -> str:
        return self.display_name
    
    def write_post(self, content: str) -> bool:
        """掲示板に投稿を書き込む"""
        if not content or not content.strip():
            return False
        
        # 投稿を追加（最大4つまで、超えた場合は古いものから削除）
        self._posts.append(content.strip())
        return True
    
    def read_posts(self) -> List[str]:
        """掲示板の全ての投稿を読み取る"""
        return list(self._posts)
    
    def get_post_count(self) -> int:
        """現在の投稿数を取得"""
        return len(self._posts)
    
    def is_full(self) -> bool:
        """掲示板が満杯かどうかを確認"""
        return len(self._posts) >= 4
    
    def clear_posts(self):
        """全ての投稿を削除"""
        self._posts.clear()


class Monument(InteractableObject):
    """石碑オブジェクト - 読み取り専用の歴史情報を持つ石碑"""
    
    def __init__(self, object_id: str, description: str, historical_text: str):
        super().__init__(object_id, description)
        self.historical_text = historical_text
        self.display_name = "石碑"
    
    def get_display_name(self) -> str:
        return self.display_name
    
    def read_historical_text(self) -> str:
        """石碑に刻まれた歴史的テキストを読み取る"""
        return self.historical_text
    
    def get_historical_text(self) -> str:
        """石碑の歴史的テキストを取得（読み取り専用）"""
        return self.historical_text