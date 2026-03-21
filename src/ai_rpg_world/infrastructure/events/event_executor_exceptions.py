"""Event executor 契約違反などの例外 (Phase 9)"""


class InvalidOperationError(Exception):
    """実行コンテキストや契約違反により操作が許可されない場合に投げる例外

    例: AnyIOAsyncEventExecutor を async コンテキスト内から呼んだ場合など。
    """
