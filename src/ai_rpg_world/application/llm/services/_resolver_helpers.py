"""ToolArgumentResolver 用の共通ヘルパー関数。"""

from typing import Any, Optional, Type

from ai_rpg_world.application.llm.contracts.dtos import (
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.domain.world.value_object.facing import Facing


class ToolArgumentResolutionException(Exception):
    """UI ラベル引数を解決できないときの例外。"""

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


def require_target(
    label: Any,
    runtime_context: ToolRuntimeContextDto,
    label_name: str,
    *,
    invalid_label_code: str = "INVALID_TARGET_LABEL",
) -> ToolRuntimeTargetDto:
    """ラベルに対応する target を取得する。存在しない場合は例外。"""
    if not isinstance(label, str) or not label:
        raise ToolArgumentResolutionException(
            f"{label_name}が指定されていません。",
            invalid_label_code,
        )
    target = runtime_context.targets.get(label)
    if target is None:
        raise ToolArgumentResolutionException(
            f"指定された対象ラベルは現在の候補にありません: {label}",
            invalid_label_code,
        )
    return target


def require_target_type(
    label: Any,
    runtime_context: ToolRuntimeContextDto,
    label_name: str,
    expected_types: tuple[Type[ToolRuntimeTargetDto], ...],
    *,
    invalid_label_code: str = "INVALID_TARGET_LABEL",
    invalid_kind_code: str = "INVALID_TARGET_KIND",
) -> ToolRuntimeTargetDto:
    """ラベルに対応する target を期待型で取得する。型が合わない場合は例外。"""
    target = require_target(
        label,
        runtime_context,
        label_name,
        invalid_label_code=invalid_label_code,
    )
    if not isinstance(target, expected_types):
        raise ToolArgumentResolutionException(
            f"{label_name}として使えないラベルです: {label}",
            invalid_kind_code,
        )
    return target


def safe_int(
    value: Any,
    field_name: str,
    *,
    min_val: Optional[int] = None,
) -> int:
    """整数に変換し、失敗時は ToolArgumentResolutionException を投げる。"""
    try:
        if value is None:
            raise ToolArgumentResolutionException(
                f"{field_name} が指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        result = int(value) if isinstance(value, (int, float, str)) else None
    except (ValueError, TypeError):
        raise ToolArgumentResolutionException(
            f"{field_name} は整数で指定してください。",
            "INVALID_TARGET_LABEL",
        ) from None
    if result is None:
        raise ToolArgumentResolutionException(
            f"{field_name} は整数で指定してください。",
            "INVALID_TARGET_LABEL",
        )
    if min_val is not None and result < min_val:
        raise ToolArgumentResolutionException(
            f"{field_name} は {min_val} 以上で指定してください。",
            "INVALID_TARGET_LABEL",
        )
    return result


def resolve_direction_from_context(
    target: ToolRuntimeTargetDto,
    runtime_context: ToolRuntimeContextDto,
) -> str:
    """target の相対座標から方向文字列を解決する。"""
    if target.relative_dx is None or target.relative_dy is None:
        raise ToolArgumentResolutionException(
            f"対象の方向を特定できません: {target.label}",
            "INVALID_TARGET_KIND",
        )
    if target.relative_dx == 0 and target.relative_dy == 0:
        raise ToolArgumentResolutionException(
            f"対象の方向を特定できません: {target.label}",
            "INVALID_TARGET_KIND",
        )
    resolved = Facing.from_delta(
        target.relative_dx,
        target.relative_dy,
        getattr(target, "relative_dz", None) or 0,
    )
    return resolved.to_direction().value
