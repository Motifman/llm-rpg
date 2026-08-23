"""確定区間必須のapplication serviceを単体試験するための補助。"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from typing import Any


def passthrough_command_scope_factory(**repositories: Any) -> MagicMock:
    """指定repositoryをそのまま公開する副作用のない偽scope factoryを返す。"""
    context = MagicMock()
    context.repositories = SimpleNamespace(**repositories)
    context.__enter__.return_value = context
    factory = MagicMock()
    factory.create.return_value = context
    return factory


__all__ = ["passthrough_command_scope_factory"]
