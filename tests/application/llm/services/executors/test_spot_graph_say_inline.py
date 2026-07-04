"""``say_inline`` 短発話の回帰テスト (PR 5: #404 後続)。

travel_to / give_item / drop_item / pickup_item の args に ``say_inline`` を
渡したとき、speech_service.speak が SAY channel で呼ばれることを確認する。

設計確認ポイント:
- speech_service 未注入なら say_inline 指定でも silent (本処理は走る)
- 80 char 上限を超えると切り詰める
- 空文字 / 未指定 / 型違反は no-op
- speech_service.speak が例外を投げても親 action は success 維持 (fail-safe)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel


def _build_executor(*, speech_service):
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
        speech_service=speech_service,
    )


class TestSayInlineHelper:
    """``_maybe_emit_say_inline`` の境界条件 (#404 後続)。"""

    def test_speech_service_未注入なら_no_op(self) -> None:
        """speech_service=None で say_inline 指定 → 例外なく no-op。"""
        executor = _build_executor(speech_service=None)
        # 例外を投げないことを確認 (return value なし)
        executor._maybe_emit_say_inline(1, {"say_inline": "hello"})

    def test_say_inline_未指定なら_speak_呼ばれない(self) -> None:
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)
        executor._maybe_emit_say_inline(1, {})
        speech.speak.assert_not_called()

    def test_say_inline_空文字なら_speak_呼ばれない(self) -> None:
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)
        executor._maybe_emit_say_inline(1, {"say_inline": ""})
        executor._maybe_emit_say_inline(1, {"say_inline": "   "})
        speech.speak.assert_not_called()

    def test_say_inline_非文字列なら_speak_呼ばれない(self) -> None:
        """JSON で number 等が混入しても落ちない。"""
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)
        executor._maybe_emit_say_inline(1, {"say_inline": 42})  # type: ignore[dict-item]
        executor._maybe_emit_say_inline(1, {"say_inline": None})
        speech.speak.assert_not_called()

    def test_say_inline_有効値で_SAY_channel_で_speak_される(self) -> None:
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)
        executor._maybe_emit_say_inline(1, {"say_inline": "先に行く"})
        speech.speak.assert_called_once()
        cmd = speech.speak.call_args[0][0]
        assert cmd.speaker_player_id == 1
        assert cmd.content == "先に行く"
        assert cmd.channel == SpeechChannel.SAY
        # whisper 用の target は None (= 同 spot 内 broadcast)
        assert cmd.target_player_id is None

    def test_80_char_を超えると切り詰められる(self) -> None:
        """LLM が schema を無視して長文を返した場合の防御。"""
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)
        long_text = "あ" * 200
        executor._maybe_emit_say_inline(1, {"say_inline": long_text})
        cmd = speech.speak.call_args[0][0]
        assert len(cmd.content) == 80

    def test_speak_が例外を投げても親_action_を倒さない(self) -> None:
        """fail-safe: travel/give が say_inline 由来で巻き戻るのを防ぐ。"""
        speech = MagicMock()
        speech.speak.side_effect = RuntimeError("speech boom")
        executor = _build_executor(speech_service=speech)
        # 例外を投げないこと
        executor._maybe_emit_say_inline(1, {"say_inline": "急ぐ"})


class TestSayInlineToolDef:
    """tool catalog 定義に say_inline が含まれている (回帰検知)。"""

    def test_travel_to_definition_に_say_inline_が_optional_で含まれる(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            TRAVEL_TO_DEFINITION,
        )
        props = TRAVEL_TO_DEFINITION.parameters["properties"]
        assert "say_inline" in props
        # required には入っていない (= optional)
        assert "say_inline" not in TRAVEL_TO_DEFINITION.parameters["required"]
        # 80 char 上限
        assert props["say_inline"]["maxLength"] == 80

    def test_give_item_definition_に_say_inline_が_optional_で含まれる(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            GIVE_ITEM_DEFINITION,
        )
        props = GIVE_ITEM_DEFINITION.parameters["properties"]
        assert "say_inline" in props
        assert "say_inline" not in GIVE_ITEM_DEFINITION.parameters["required"]

    def test_drop_item_definition_に_say_inline_が_optional_で含まれる(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            DROP_ITEM_DEFINITION,
        )
        props = DROP_ITEM_DEFINITION.parameters["properties"]
        assert "say_inline" in props
        assert "say_inline" not in DROP_ITEM_DEFINITION.parameters["required"]

    def test_pickup_item_definition_に_say_inline_が_optional_で含まれる(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            PICKUP_ITEM_DEFINITION,
        )
        props = PICKUP_ITEM_DEFINITION.parameters["properties"]
        assert "say_inline" in props
        assert "say_inline" not in PICKUP_ITEM_DEFINITION.parameters["required"]

    # PR-ι (say_inline 拡張): interact / attack / use_item / tend_to_player
    # にも say_inline を追加。物語のコミュニケーションを豊かにするため。

    def test_interact_definition_に_say_inline_が_optional_で含まれる(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            INTERACT_DEFINITION,
        )
        props = INTERACT_DEFINITION.parameters["properties"]
        assert "say_inline" in props
        assert "say_inline" not in INTERACT_DEFINITION.parameters["required"]

    def test_attack_definition_に_say_inline_が_optional_で含まれる(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            ATTACK_DEFINITION,
        )
        props = ATTACK_DEFINITION.parameters["properties"]
        assert "say_inline" in props
        assert "say_inline" not in ATTACK_DEFINITION.parameters["required"]

    def test_use_item_definition_に_say_inline_が_optional_で含まれる(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            USE_ITEM_DEFINITION,
        )
        props = USE_ITEM_DEFINITION.parameters["properties"]
        assert "say_inline" in props
        assert "say_inline" not in USE_ITEM_DEFINITION.parameters["required"]

    def test_tend_to_player_definition_に_say_inline_が_optional_で含まれる(self) -> None:
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            TEND_TO_PLAYER_DEFINITION,
        )
        props = TEND_TO_PLAYER_DEFINITION.parameters["properties"]
        assert "say_inline" in props
        assert (
            "say_inline" not in TEND_TO_PLAYER_DEFINITION.parameters["required"]
        )
