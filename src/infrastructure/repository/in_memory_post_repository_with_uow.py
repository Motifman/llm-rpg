"""
InMemoryPostRepositoryWithUow - Unit of Workと統合されたインメモリポストリポジトリ
"""
from typing import List, Optional, Dict, Set, Callable
from datetime import datetime, timedelta
import random
from src.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from src.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class InMemoryPostRepositoryWithUow(InMemoryPostRepository):
    """Unit of Workと統合されたPostAggregateを使用するインメモリリポジトリ"""

    def __init__(self, unit_of_work: InMemoryUnitOfWork):
        # 親クラスの初期化をスキップして手動で初期化
        self._posts: Dict = {}
        self._next_post_id = 1
        self._unit_of_work = unit_of_work

        # サンプルデータをセットアップ
        self._setup_sample_data()

    def save(self, post):
        """集約を保存（Unit of Work対応版）"""
        def save_operation():
            self._posts[post.post_id] = post
            post.clear_events()  # 発行済みのイベントをクリア

        # トランザクション内でのみ保存可能
        if self._unit_of_work.is_in_transaction():
            self._unit_of_work.add_operation(save_operation)
        else:
            # トランザクション外の場合は即時実行（テスト用）
            save_operation()
