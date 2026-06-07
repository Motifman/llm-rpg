"""``spot_graph_give_items`` batch tool の回帰テスト (PR 5b)。

memo_done の ``keys: [...]`` パターンを踏襲した「同 tick 複数 give」ツール。
各 entry を partial success で処理し、結果は 1 行 1 entry の OK/NG サマリ。

設計確認:
- gives_resolved の各 entry を loop で give_item に渡す
- 1 件でも成功すれば success=True、全失敗なら success=False
- resolve 段階で失敗した entry は error_code を持ち、NG 行で報告
- say_inline は **1 件でも成功した時のみ** 発火 (整合性)
- item_transfer_service 未配線時は NOT_WIRED で即時失敗
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    ItemTransferException,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)


def _build_executor(
    *,
    transfer_service=None,
    speech_service=None,
):
    services = SpotGraphWorldServices(
        interaction=MagicMock(),
        exploration=MagicMock(),
        world_flags=MagicMock(as_frozen_set=MagicMock(return_value=frozenset())),
        game_end_evaluator=MagicMock(),
        exploration_progress=MagicMock(),
        movement=MagicMock(),
        simulation=None,
    )
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        item_transfer_service=transfer_service,
        speech_service=speech_service,
    )


def _resolved(index: int, item: str, target: str, slot_id=0, to_id=2):
    return {
        "index": index,
        "slot_id": slot_id,
        "target_player_id": to_id,
        "target_display_name": target,
        "item_display_name": item,
        "item_label": item,
        "target_player_label": target,
    }


class TestGiveItemsHappy:
    """全 entry 成功時。"""

    def test_2件全部成功なら_OK_行が_2件_集約される(self) -> None:
        transfer = MagicMock()
        executor = _build_executor(transfer_service=transfer)

        result = executor._give_items(
            player_id=1,
            args={
                "gives_resolved": [
                    _resolved(0, "流木", "ノア", slot_id=0, to_id=2),
                    _resolved(1, "火打ち石", "リオ", slot_id=1, to_id=3),
                ],
                "inner_thought": "配って先へ行く",
            },
        )

        assert result.success is True
        assert "流木 → ノア: OK" in result.message
        assert "火打ち石 → リオ: OK" in result.message
        # transfer service が 2 回呼ばれる
        assert transfer.give_item.call_count == 2


class TestGiveItemsPartialFailure:
    """一部の give が失敗するケース (受け手満杯など)。"""

    def test_1件目失敗_2件目成功で_success_True_と両方の行が出る(self) -> None:
        transfer = MagicMock()
        # 1 件目は ItemTransferException、2 件目は成功
        transfer.give_item.side_effect = [
            ItemTransferException("受け手のインベントリが満杯"),
            None,
        ]
        executor = _build_executor(transfer_service=transfer)

        result = executor._give_items(
            player_id=1,
            args={
                "gives_resolved": [
                    _resolved(0, "流木", "ノア"),
                    _resolved(1, "火打ち石", "リオ"),
                ],
                "inner_thought": "",
            },
        )

        assert result.success is True  # 1 件でも成功すれば True
        assert "流木 → ノア: NG (受け手のインベントリが満杯)" in result.message
        assert "火打ち石 → リオ: OK" in result.message

    def test_全件失敗なら_success_False_と_ITEM_TRANSFER_FAILED(self) -> None:
        transfer = MagicMock()
        transfer.give_item.side_effect = ItemTransferException("受け手満杯")
        executor = _build_executor(transfer_service=transfer)

        result = executor._give_items(
            player_id=1,
            args={
                "gives_resolved": [
                    _resolved(0, "流木", "ノア"),
                    _resolved(1, "火打ち石", "リオ"),
                ],
                "inner_thought": "",
            },
        )

        assert result.success is False
        assert result.error_code == "ITEM_TRANSFER_FAILED"
        assert "全て失敗" in result.message


class TestGiveItemsResolveError:
    """resolve 段階で失敗した entry は error_code を持って NG 行に出る。"""

    def test_resolve_失敗_entry_は_NG_行で_理由が表示される(self) -> None:
        transfer = MagicMock()
        executor = _build_executor(transfer_service=transfer)

        result = executor._give_items(
            player_id=1,
            args={
                "gives_resolved": [
                    {
                        "index": 0,
                        "error_code": "INVALID_TARGET_LABEL",
                        "message": "未知のアイテム名: 銀のロザリオ",
                        "item_label": "銀のロザリオ",
                        "target_player_label": "ノア",
                    },
                    _resolved(1, "流木", "リオ"),
                ],
                "inner_thought": "",
            },
        )

        # 1 件目は resolve 段階 NG、2 件目は successful give
        assert "NG (未知のアイテム名: 銀のロザリオ)" in result.message
        assert "流木 → リオ: OK" in result.message
        # 1 件 OK なので success=True
        assert result.success is True
        # transfer.give_item は 2 件目だけ呼ばれる (1 件目は resolve 失敗で skip)
        assert transfer.give_item.call_count == 1


class TestGiveItemsSayInline:
    """say_inline は 1 件でも成功した時のみ発火。"""

    def test_全部成功なら_say_inline_が_発火する(self) -> None:
        transfer = MagicMock()
        speech = MagicMock()
        executor = _build_executor(transfer_service=transfer, speech_service=speech)

        executor._give_items(
            player_id=1,
            args={
                "gives_resolved": [_resolved(0, "流木", "ノア")],
                "say_inline": "持って行ってくれ",
                "inner_thought": "",
            },
        )

        speech.speak.assert_called_once()
        cmd = speech.speak.call_args[0][0]
        assert cmd.content == "持って行ってくれ"

    def test_全失敗なら_say_inline_は_発火しない(self) -> None:
        transfer = MagicMock()
        transfer.give_item.side_effect = ItemTransferException("満杯")
        speech = MagicMock()
        executor = _build_executor(transfer_service=transfer, speech_service=speech)

        executor._give_items(
            player_id=1,
            args={
                "gives_resolved": [_resolved(0, "流木", "ノア")],
                "say_inline": "持って行ってくれ",
                "inner_thought": "",
            },
        )

        speech.speak.assert_not_called()


class TestGiveItemsNotWired:
    """item_transfer_service 未注入時は NOT_WIRED で即時失敗。"""

    def test_transfer_service_None_で_NOT_WIRED(self) -> None:
        executor = _build_executor(transfer_service=None)
        result = executor._give_items(
            player_id=1,
            args={
                "gives_resolved": [_resolved(0, "流木", "ノア")],
                "inner_thought": "",
            },
        )
        assert result.success is False
        assert result.error_code == "NOT_WIRED"


class TestGiveItemsArgumentValidation:
    """gives_resolved が空 / 不正な引数の防御。"""

    def test_gives_resolved_が_空配列なら_INVALID_ARGUMENT(self) -> None:
        executor = _build_executor(transfer_service=MagicMock())
        result = executor._give_items(
            player_id=1,
            args={"gives_resolved": [], "inner_thought": ""},
        )
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"

    def test_gives_resolved_が_欠落していたら_INVALID_ARGUMENT(self) -> None:
        executor = _build_executor(transfer_service=MagicMock())
        result = executor._give_items(player_id=1, args={"inner_thought": ""})
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"


class TestGiveItemsToolDef:
    """tool catalog 定義の回帰テスト。"""

    def test_GIVE_ITEMS_DEFINITION_に_gives_配列が_required(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            GIVE_ITEMS_DEFINITION,
        )
        props = GIVE_ITEMS_DEFINITION.parameters["properties"]
        assert "gives" in props
        assert props["gives"]["type"] == "array"
        assert props["gives"]["minItems"] == 1
        # 各 entry は item_label と target_player_label が required
        item_props = props["gives"]["items"]["properties"]
        assert "item_label" in item_props
        assert "target_player_label" in item_props
        # say_inline は optional
        assert "say_inline" in props
        assert "say_inline" not in GIVE_ITEMS_DEFINITION.parameters["required"]
