"""
InMemorySnsUserRepositoryWithUow - Unit of Workと統合されたインメモリSNSユーザーリポジトリ
"""
from typing import List, Optional, Dict, Tuple, Set, Callable
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class InMemorySnsUserRepositoryWithUow(InMemorySnsUserRepository):
    """Unit of Workと統合されたUserAggregateを使用するインメモリリポジトリ"""

    def __init__(self, unit_of_work: InMemoryUnitOfWork):
        # 親クラスの初期化をスキップして手動で初期化
        self._users: Dict = {}
        self._username_to_user_id: Dict = {}
        self._next_user_id = 1
        self._unit_of_work = unit_of_work

        # サンプルデータをセットアップ
        self._setup_sample_data()

    def save(self, user):
        """集約を保存（Unit of Work対応版）"""
        def save_operation():
            self._users[user.user_id] = user
            # ユーザー名マッピングも更新
            self._username_to_user_id[user.profile.user_name] = user.user_id

        # トランザクション内でのみ保存可能
        if self._unit_of_work.is_in_transaction():
            self._unit_of_work.add_operation(save_operation)
        else:
            # トランザクション外の場合は即時実行（テスト用）
            save_operation()
