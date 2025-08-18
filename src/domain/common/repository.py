from abc import ABC, abstractmethod
from typing import Optional, List, TypeVar, Generic

T = TypeVar('T')


class Repository(ABC, Generic[T]):
    """リポジトリの基底インターフェース"""
    
    @abstractmethod
    def find_by_id(self, entity_id: int) -> Optional[T]:
        """IDでエンティティを検索"""
        pass
    
    @abstractmethod
    def save(self, entity: T) -> T:
        """エンティティを保存"""
        pass
    
    @abstractmethod
    def delete(self, entity_id: int) -> bool:
        """エンティティを削除"""
        pass
    
    @abstractmethod
    def find_all(self) -> List[T]:
        """全てのエンティティを取得"""
        pass
