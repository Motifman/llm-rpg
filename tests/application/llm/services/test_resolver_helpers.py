"""ToolArgumentResolver 用共通ヘルパー（_resolver_helpers）のテスト。"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
    require_target,
    require_target_type,
    resolve_direction_from_context,
    safe_int,
)


def _make_context() -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(
        targets={
            "P1": PlayerToolRuntimeTargetDto(
                label="P1",
                kind="player",
                display_name="Bob",
                player_id=2,
                world_object_id=100,
            ),
            "P2": PlayerToolRuntimeTargetDto(
                label="P2",
                kind="player",
                display_name="Alice",
                player_id=3,
                world_object_id=101,
                relative_dx=1,
                relative_dy=0,
                relative_dz=0,
            ),
            "P3": PlayerToolRuntimeTargetDto(
                label="P3",
                kind="player",
                display_name="Charlie",
                player_id=4,
                world_object_id=102,
                relative_dx=0,
                relative_dy=0,
                relative_dz=0,
            ),
        }
    )


class TestRequireTarget:
    """require_target のテスト"""

    def test_returns_target_when_label_exists(self):
        ctx = _make_context()
        result = require_target("P1", ctx, "プレイヤーラベル")
        assert result.label == "P1"
        assert result.player_id == 2

    def test_raises_when_label_is_none(self):
        ctx = _make_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            require_target(None, ctx, "プレイヤーラベル")
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "指定されていません" in str(exc_info.value)

    def test_raises_when_label_is_empty_string(self):
        ctx = _make_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            require_target("", ctx, "プレイヤーラベル")
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_raises_when_label_not_in_targets(self):
        ctx = _make_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            require_target("X99", ctx, "プレイヤーラベル")
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "候補にありません" in str(exc_info.value)

    def test_raises_when_label_is_not_str(self):
        ctx = _make_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            require_target(123, ctx, "プレイヤーラベル")  # type: ignore[arg-type]
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_uses_custom_invalid_label_code(self):
        ctx = _make_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            require_target(
                "X99", ctx, "移動先ラベル", invalid_label_code="INVALID_DESTINATION_LABEL"
            )
        assert exc_info.value.error_code == "INVALID_DESTINATION_LABEL"


class TestRequireTargetType:
    """require_target_type のテスト"""

    def test_returns_target_when_type_matches(self):
        ctx = _make_context()
        result = require_target_type(
            "P1", ctx, "プレイヤーラベル", (PlayerToolRuntimeTargetDto,)
        )
        assert result.label == "P1"
        assert isinstance(result, PlayerToolRuntimeTargetDto)

    def test_raises_when_type_mismatch(self):
        from ai_rpg_world.application.llm.contracts.dtos import MonsterToolRuntimeTargetDto

        ctx = _make_context()
        ctx.targets["M1"] = MonsterToolRuntimeTargetDto(
            label="M1",
            kind="monster",
            display_name="スライム",
            world_object_id=200,
        )
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            require_target_type(
                "M1", ctx, "プレイヤーラベル", (PlayerToolRuntimeTargetDto,)
            )
        assert exc_info.value.error_code == "INVALID_TARGET_KIND"
        assert "使えないラベル" in str(exc_info.value)

    def test_raises_when_label_missing_delegates_to_require_target(self):
        ctx = _make_context()
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            require_target_type(
                "X99", ctx, "プレイヤーラベル", (PlayerToolRuntimeTargetDto,)
            )
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_uses_custom_invalid_kind_code(self):
        from ai_rpg_world.application.llm.contracts.dtos import MonsterToolRuntimeTargetDto

        ctx = _make_context()
        ctx.targets["M1"] = MonsterToolRuntimeTargetDto(
            label="M1",
            kind="monster",
            display_name="スライム",
            world_object_id=200,
        )
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            require_target_type(
                "M1",
                ctx,
                "プレイヤーラベル",
                (PlayerToolRuntimeTargetDto,),
                invalid_kind_code="INVALID_DESTINATION_KIND",
            )
        assert exc_info.value.error_code == "INVALID_DESTINATION_KIND"


class TestSafeInt:
    """safe_int のテスト"""

    def test_returns_int_from_int(self):
        assert safe_int(42, "value") == 42

    def test_returns_int_from_float(self):
        assert safe_int(42.0, "value") == 42

    def test_returns_int_from_str(self):
        assert safe_int("42", "value") == 42

    def test_raises_when_none(self):
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            safe_int(None, "value")
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "指定されていません" in str(exc_info.value)

    def test_raises_when_invalid_str(self):
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            safe_int("abc", "value")
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "整数" in str(exc_info.value)

    def test_raises_when_list(self):
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            safe_int([1, 2], "value")
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_respects_min_val(self):
        assert safe_int(5, "value", min_val=0) == 5
        assert safe_int(0, "value", min_val=0) == 0

    def test_raises_when_below_min_val(self):
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            safe_int(-1, "value", min_val=0)
        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "0 以上" in str(exc_info.value)

    def test_raises_when_below_min_val_with_custom_field_name(self):
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            safe_int(0, "objectives[0].required_count", min_val=1)
        assert "objectives[0].required_count" in str(exc_info.value)
        assert "1 以上" in str(exc_info.value)


class TestResolveDirectionFromContext:
    """resolve_direction_from_context のテスト"""

    def test_returns_direction_when_delta_valid(self):
        ctx = _make_context()
        target = ctx.targets["P2"]
        result = resolve_direction_from_context(target, ctx)
        assert result == "EAST"

    def test_raises_when_relative_dx_is_none(self):
        from ai_rpg_world.application.llm.contracts.dtos import MonsterToolRuntimeTargetDto

        ctx = _make_context()
        ctx.targets["M1"] = MonsterToolRuntimeTargetDto(
            label="M1",
            kind="monster",
            display_name="ゴブリン",
            world_object_id=301,
            relative_dx=None,
            relative_dy=1,
            relative_dz=0,
        )
        target = ctx.targets["M1"]
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolve_direction_from_context(target, ctx)
        assert exc_info.value.error_code == "INVALID_TARGET_KIND"
        assert "方向を特定できません" in str(exc_info.value)

    def test_raises_when_relative_dy_is_none(self):
        from ai_rpg_world.application.llm.contracts.dtos import MonsterToolRuntimeTargetDto

        ctx = _make_context()
        ctx.targets["M1"] = MonsterToolRuntimeTargetDto(
            label="M1",
            kind="monster",
            display_name="ゴブリン",
            world_object_id=301,
            relative_dx=1,
            relative_dy=None,
            relative_dz=0,
        )
        target = ctx.targets["M1"]
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolve_direction_from_context(target, ctx)
        assert exc_info.value.error_code == "INVALID_TARGET_KIND"

    def test_raises_when_both_deltas_zero(self):
        ctx = _make_context()
        target = ctx.targets["P3"]
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolve_direction_from_context(target, ctx)
        assert exc_info.value.error_code == "INVALID_TARGET_KIND"
        assert "方向を特定できません" in str(exc_info.value)

    def test_uses_relative_dz_when_present(self):
        from ai_rpg_world.application.llm.contracts.dtos import MonsterToolRuntimeTargetDto

        ctx = _make_context()
        ctx.targets["M1"] = MonsterToolRuntimeTargetDto(
            label="M1",
            kind="monster",
            display_name="ゴブリン",
            world_object_id=301,
            relative_dx=1,
            relative_dy=-1,
            relative_dz=0,
        )
        target = ctx.targets["M1"]
        result = resolve_direction_from_context(target, ctx)
        assert result == "NORTHEAST"


class TestToolArgumentResolutionException:
    """ToolArgumentResolutionException のテスト"""

    def test_exception_has_message_and_error_code(self):
        exc = ToolArgumentResolutionException("テストメッセージ", "TEST_CODE")
        assert str(exc) == "テストメッセージ"
        assert exc.error_code == "TEST_CODE"

    def test_exception_is_raiseable(self):
        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            raise ToolArgumentResolutionException("エラー", "ERROR_CODE")
        assert exc_info.value.error_code == "ERROR_CODE"
