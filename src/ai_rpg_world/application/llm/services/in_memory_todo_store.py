"""Backward-compat shim: ``InMemoryTodoStore`` was renamed to
``InMemoryMemoStore`` (Issue #188 Phase 1a). Import from the new module.

新規コードは ``in_memory_memo_store`` を import すること。本 shim は既存の
``from .in_memory_todo_store import InMemoryTodoStore`` を壊さないために残す。
"""

from ai_rpg_world.application.llm.services.in_memory_memo_store import (
    InMemoryMemoStore,
    InMemoryTodoStore,
)

__all__ = ["InMemoryMemoStore", "InMemoryTodoStore"]
