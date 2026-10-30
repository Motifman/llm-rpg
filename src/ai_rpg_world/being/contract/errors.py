"""契約の型を作るときの違反。"""

from __future__ import annotations


class ContractViolation(ValueError):
    """契約の型の欄が決まりを満たさない。"""


def require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(f"{field_name} must be non-blank str")


def require_optional_text(value: object, field_name: str) -> None:
    if value is not None:
        require_text(value, field_name)


def require_bool(value: object, field_name: str) -> None:
    if not isinstance(value, bool):
        raise ContractViolation(f"{field_name} must be bool")
