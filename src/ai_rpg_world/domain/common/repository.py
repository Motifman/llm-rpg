from abc import ABC, abstractmethod
from typing import Optional, List, TypeVar, Generic

T = TypeVar('T')
ID = TypeVar('ID')


class Repository(ABC, Generic[T, ID]):
    """リポジトリの基底インターフェース"""

    @abstractmethod
    def find_by_id(self, entity_id: ID) -> Optional[T]:
        """IDでエンティティを検索"""
        pass

    @abstractmethod
    def find_by_ids(self, entity_ids: List[ID]) -> List[T]:
        """IDのリストでエンティティを検索"""
        pass

    @abstractmethod
    def save(self, entity: T) -> T:
        """エンティティを保存"""
        pass

    @abstractmethod
    def delete(self, entity_id: ID) -> bool:
        """エンティティを削除"""
        pass

    @abstractmethod
    def find_all(self) -> List[T]:
        """全てのエンティティを取得"""
        pass
