"""CommandScopeの有効期間だけrepository呼出しを許可するproxy。"""

from functools import wraps
from typing import Any, Callable, Generic, TypeVar


RepositoryT = TypeVar("RepositoryT")


class ScopeBoundRepository(Generic[RepositoryT]):
    """各repository呼出しの直前にscopeの有効性を検査する。"""

    def __init__(self, repository: RepositoryT, guard: Callable[[], None]) -> None:
        self._repository = repository
        self._guard = guard

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._repository, name)
        if not callable(attribute):
            self._guard()
            return attribute

        @wraps(attribute)
        def guarded_call(*args: Any, **kwargs: Any) -> Any:
            self._guard()
            return attribute(*args, **kwargs)

        return guarded_call


__all__ = ["ScopeBoundRepository"]
