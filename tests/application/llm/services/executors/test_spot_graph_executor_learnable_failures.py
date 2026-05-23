"""Issue #168 PR-2: ``SpotGraphToolExecutor`` の失敗 DTO が learnable に
なっているか検証する。

PR #167 (escape_game 経路) と PR #170 (sns/trade enter) で確立した不変条件
を spot_graph 経路にも展開する:

- 失敗 DTO に ``error_code`` が必ず付く
- 失敗 DTO に ``remediation`` が必ず付く
- 例外メッセージ (path / 内部 ID 含みうる) は LLM 向け message に漏らさない
- 引数バリデーション失敗は ``build_invalid_arg_failure`` の learnable な形式
  (arg 名と期待値を message に含む)
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)


def _build_executor() -> SpotGraphToolExecutor:
    """最小限の wiring で executor を構築する (state mutation はテストしない)。"""
    movement = MagicMock()
    services = SpotGraphWorldServices(
        interaction=MagicMock(),
        exploration=MagicMock(),
        world_flags=MagicMock(as_frozen_set=MagicMock(return_value=frozenset())),
        game_end_evaluator=MagicMock(),
        exploration_progress=MagicMock(),
        movement=movement,
        simulation=None,
    )
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
    )


def _assert_learnable_failure(result, expected_error_code: str | None = None) -> None:
    """failure DTO の最低限の体裁 (error_code + remediation 必須) を確認。"""
    assert result.success is False
    assert result.error_code, f"error_code が空: {result!r}"
    if expected_error_code is not None:
        assert result.error_code == expected_error_code
    assert result.remediation, f"remediation が空: {result!r}"


class TestTravelToInvalidArgs:
    """``destination_spot_id`` の検証失敗。"""

    def test_negative_destination_is_learnable(self) -> None:
        """負の destination_spot_id は INVALID_ARGUMENT で learnable に返る。"""
        executor = _build_executor()
        result = executor._travel_to(player_id=1, args={"destination_spot_id": -1})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        assert "destination_spot_id" in result.message
        # 期待値 (正の整数) が message に含まれる
        assert "正の整数" in result.message

    def test_zero_destination_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._travel_to(player_id=1, args={"destination_spot_id": 0})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")

    def test_non_integer_destination_is_learnable(self) -> None:
        """non-int も learnable な形式で返る。"""
        executor = _build_executor()
        result = executor._travel_to(
            player_id=1, args={"destination_spot_id": "abc"}
        )
        _assert_learnable_failure(result, "INVALID_ARGUMENT")


class TestSetSubLocationInvalidArgs:
    def test_non_integer_sub_location_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._set_sub_location(player_id=1, args={"sub_location_id": "x"})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        assert "sub_location_id" in result.message


class TestInteractInvalidArgs:
    def test_missing_action_name_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._interact(
            player_id=1, args={"object_id": 5, "action_name": ""}
        )
        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        assert "action_name" in result.message

    def test_zero_object_id_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._interact(
            player_id=1, args={"object_id": 0, "action_name": "examine"}
        )
        _assert_learnable_failure(result, "INVALID_ARGUMENT")


class TestUseItemInvalidArgs:
    def test_missing_item_spec_id_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._use_item(player_id=1, args={})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        assert "item_spec_id" in result.message

    def test_non_integer_item_spec_id_is_learnable(self) -> None:
        executor = _build_executor()
        result = executor._use_item(player_id=1, args={"item_spec_id": "foo"})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")


class TestPrepareActionValidationLeak:
    """``_prepare_action`` の ValueError が str(exc) で LLM に漏れないこと。"""

    def test_empty_action_id_is_learnable_arg_failure(self) -> None:
        """空 action_id は build_invalid_arg_failure 経由で安全に返る。"""
        executor = _build_executor()
        result = executor._prepare_action(player_id=1, args={"action_id": ""})
        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        assert "action_id" in result.message

    def test_value_error_is_sanitized(self, caplog) -> None:
        """registry が ValueError を投げても、str(exc) は LLM 向け message に出ない。

        PR #170 と同じ pattern: 内部 path/ID を含みうる ValueError メッセージ
        を漏らさず、サーバログには warning レベルで全文脈を残す。
        """
        executor = _build_executor()
        # PreparedActionRegistry.prepare をモンキーパッチして機微 ValueError を投げる
        sensitive = "/internal/secret_action_path: token=xyz"
        import ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor as mod

        class _StubRegistry:
            def __init__(self, *_, **__): ...
            def prepare(self, **__):
                raise ValueError(sensitive)

        original = mod.PreparedActionRegistry
        mod.PreparedActionRegistry = _StubRegistry  # type: ignore[attr-defined]
        try:
            with caplog.at_level(
                logging.WARNING,
                logger="ai_rpg_world.application.llm.services.failure_helpers",
            ):
                result = executor._prepare_action(
                    player_id=1, args={"action_id": "OPEN_VAULT"}
                )
        finally:
            mod.PreparedActionRegistry = original  # type: ignore[attr-defined]

        _assert_learnable_failure(result, "INVALID_ARGUMENT")
        # 機微情報が message に漏れていない
        assert "/internal/secret_action_path" not in result.message
        assert "token=xyz" not in result.message
        # action_id 自体は LLM が次の試行に使えるよう残してよい
        assert "OPEN_VAULT" in result.message


class TestInventoryNotFound:
    """インベントリ未取得時の失敗。"""

    def test_use_item_returns_learnable_on_missing_inventory(self) -> None:
        executor = _build_executor()
        executor._player_inventory_repository.find_by_id.return_value = None
        result = executor._use_item(player_id=1, args={"item_spec_id": 1})
        _assert_learnable_failure(result, "PLAYER_NOT_FOUND")

    def test_travel_to_returns_learnable_on_missing_inventory(self) -> None:
        executor = _build_executor()
        executor._player_inventory_repository.find_by_id.return_value = None
        result = executor._travel_to(
            player_id=1, args={"destination_spot_id": 5}
        )
        _assert_learnable_failure(result, "PLAYER_NOT_FOUND")
