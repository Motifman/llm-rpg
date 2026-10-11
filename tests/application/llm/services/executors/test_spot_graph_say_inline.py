"""``say_inline`` 短発話の回帰テスト (PR 5: #404 後続)。

行動ツールの args に ``say_inline`` を渡したとき、
speech_service.speak が SAY channel で呼ばれることを確認する。

設計確認ポイント:
- speech_service 未注入、または speak が断られたら NOT_DELIVERED を返す
- 200 char 上限を超えると切り詰める
- 空文字 / 未指定 / 型違反は NOTHING_TO_SAY
- handler 単体は発言を出さない。dispatch の包みが行動の結果を問わず出す (D1601)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SayInlineDelivery,
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.llm.services.tool_catalog.say_inline import (
    SAY_INLINE_DEFAULT_DESCRIPTION,
    SAY_INLINE_MAX_LENGTH,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_MARKET_BID,
    TOOL_NAME_SPOT_GRAPH_MARKET_BUY,
    TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
    TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
    TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
    TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
    TOOL_NAME_SPOT_GRAPH_MARKET_VIEW,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
    TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
    TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
    TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
    TOOL_NAME_SPOT_GRAPH_TRADE_OFFER,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_VOTE,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel


def _build_executor(*, speech_service, runtime=None):
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
        runtime=runtime,
    )


class TestSpeakSayInline:
    """``speak_say_inline`` が発言を出し、出せたかを返す境界条件を保証する。"""

    def test_uninjected_speech_service_reports_not_delivered(self) -> None:
        """speech_service が未注入のとき、例外を投げず NOT_DELIVERED を返す。"""
        executor = _build_executor(speech_service=None)

        delivery = executor.speak_say_inline(1, {"say_inline": "hello"})

        assert delivery is SayInlineDelivery.NOT_DELIVERED

    def test_missing_say_inline_does_not_speak(self) -> None:
        """say_inline が無いとき、speak を呼ばず NOTHING_TO_SAY を返す。"""
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)

        delivery = executor.speak_say_inline(1, {})

        assert delivery is SayInlineDelivery.NOTHING_TO_SAY
        speech.speak.assert_not_called()

    def test_blank_say_inline_does_not_speak(self) -> None:
        """空文字と空白だけの say_inline は、speak を呼ばず NOTHING_TO_SAY を返す。"""
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)

        deliveries = [
            executor.speak_say_inline(1, {"say_inline": ""}),
            executor.speak_say_inline(1, {"say_inline": "   "}),
        ]

        assert deliveries == [SayInlineDelivery.NOTHING_TO_SAY] * 2
        speech.speak.assert_not_called()

    def test_non_string_say_inline_does_not_speak(self) -> None:
        """JSON で数値や null が混ざった say_inline は、落ちずに NOTHING_TO_SAY を返す。"""
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)

        deliveries = [
            executor.speak_say_inline(1, {"say_inline": 42}),  # type: ignore[dict-item]
            executor.speak_say_inline(1, {"say_inline": None}),
        ]

        assert deliveries == [SayInlineDelivery.NOTHING_TO_SAY] * 2
        speech.speak.assert_not_called()

    def test_valid_say_inline_speaks_on_the_say_channel(self) -> None:
        """有効な say_inline は宛先なしの SAY channel で speak され、SPOKEN を返す。"""
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)

        delivery = executor.speak_say_inline(1, {"say_inline": "先に行く"})

        assert delivery is SayInlineDelivery.SPOKEN
        speech.speak.assert_called_once()
        cmd = speech.speak.call_args[0][0]
        assert cmd.speaker_player_id == 1
        assert cmd.content == "先に行く"
        assert cmd.channel == SpeechChannel.SAY
        assert cmd.target_player_id is None

    def test_200_char_exactly_speaks_without_truncation(self) -> None:
        """200 字ちょうどの say_inline は切り詰めず SAY channel で発話される。"""
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)
        text = "あ" * SAY_INLINE_MAX_LENGTH

        executor.speak_say_inline(1, {"say_inline": text})

        cmd = speech.speak.call_args[0][0]
        assert cmd.content == text
        assert len(cmd.content) == SAY_INLINE_MAX_LENGTH

    def test_say_inline_over_the_cap_is_truncated(self) -> None:
        """LLM が schema を無視して 201 字以上を返すと、200 字に切り詰めて発話する。"""
        speech = MagicMock()
        executor = _build_executor(speech_service=speech)
        long_text = "あ" * (SAY_INLINE_MAX_LENGTH + 1)

        executor.speak_say_inline(1, {"say_inline": long_text})

        cmd = speech.speak.call_args[0][0]
        assert len(cmd.content) == SAY_INLINE_MAX_LENGTH

    def test_cap_holds_a_typical_coordination_utterance(self) -> None:
        """実測の段取り発話が専用ターンへ戻らないよう、上限は speak 中央値 104 字を超える。"""
        assert SAY_INLINE_MAX_LENGTH >= 104

    def test_refused_speak_reports_not_delivered(self) -> None:
        """speech_service.speak が例外を投げると、例外を外へ出さず NOT_DELIVERED を返す。"""
        speech = MagicMock()
        speech.speak.side_effect = RuntimeError("speech boom")
        executor = _build_executor(speech_service=speech)

        delivery = executor.speak_say_inline(1, {"say_inline": "急ぐ"})

        assert delivery is SayInlineDelivery.NOT_DELIVERED

    def test_wait_handler_alone_does_not_speak(self) -> None:
        """wait の handler 単体は発言を出さない。発言は dispatch の包みが 1 回だけ出す (D1601)。"""
        speech = MagicMock()
        runtime = MagicMock()
        runtime.do_wait.return_value = 12
        executor = _build_executor(speech_service=speech, runtime=runtime)

        result = executor._wait(
            1,
            {"reason": "夜明けを待つ", "say_inline": "夜明けまでここで待とう", "inner_thought": "疲労を抑える"},
        )

        assert result.success is True
        speech.speak.assert_not_called()


class TestSayInlineToolDef:
    """tool catalog 定義に say_inline が含まれている (回帰検知)。"""

    def _assert_say_inline_optional(self, definition) -> None:
        props = definition.parameters["properties"]
        assert "say_inline" in props
        assert "say_inline" not in definition.parameters["required"]
        assert props["say_inline"]["maxLength"] == SAY_INLINE_MAX_LENGTH

    def test_travel_definition_say_inline_optional_included(self) -> None:
        """travel to definition に say inline が optional で含まれる。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            TRAVEL_TO_DEFINITION,
        )
        self._assert_say_inline_optional(TRAVEL_TO_DEFINITION)

    def test_give_item_definition_say_inline_optional_included(self) -> None:
        """give item definition に say inline が optional で含まれる。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            GIVE_ITEM_DEFINITION,
        )
        self._assert_say_inline_optional(GIVE_ITEM_DEFINITION)

    def test_drop_item_definition_say_inline_optional_included(self) -> None:
        """drop item definition に say inline が optional で含まれる。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            DROP_ITEM_DEFINITION,
        )
        self._assert_say_inline_optional(DROP_ITEM_DEFINITION)

    def test_pickup_item_definition_say_inline_optional_included(self) -> None:
        """pickup item definition に say inline が optional で含まれる。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            PICKUP_ITEM_DEFINITION,
        )
        self._assert_say_inline_optional(PICKUP_ITEM_DEFINITION)

    # PR-ι (say_inline 拡張): interact / attack / use_item / tend_to_player
    # にも say_inline を追加。物語のコミュニケーションを豊かにするため。

    def test_interact_definition_say_inline_optional_included(self) -> None:
        """interact definition に say inline が optional で含まれる。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            INTERACT_DEFINITION,
        )
        self._assert_say_inline_optional(INTERACT_DEFINITION)

    def test_attack_definition_say_inline_optional_included(self) -> None:
        """attack definition に say inline が optional で含まれる。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            ATTACK_DEFINITION,
        )
        self._assert_say_inline_optional(ATTACK_DEFINITION)

    def test_use_item_definition_say_inline_optional_included(self) -> None:
        """use item definition に say inline が optional で含まれる。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            USE_ITEM_DEFINITION,
        )
        self._assert_say_inline_optional(USE_ITEM_DEFINITION)

    def test_tend_player_definition_say_inline_optional_included(self) -> None:
        """tend to player definition に say inline が optional で含まれる。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            TEND_TO_PLAYER_DEFINITION,
        )
        self._assert_say_inline_optional(TEND_TO_PLAYER_DEFINITION)

    def test_wait_definition_say_inline_optional_included(self) -> None:
        """wait definition に say_inline が optional で含まれる。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            WAIT_DEFINITION,
        )
        self._assert_say_inline_optional(WAIT_DEFINITION)

    def test_explore_definition_say_inline_optional_included(self) -> None:
        """explore definition に say_inline が optional で含まれる。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            EXPLORE_DEFINITION,
        )
        self._assert_say_inline_optional(EXPLORE_DEFINITION)

    def test_default_description_no_longer_guides_to_dedicated_speech_turn(self) -> None:
        """say_inline の共通説明文から旧誘導を消し、行動同時発話の用途を示す。"""
        assert "立ち去り際" not in SAY_INLINE_DEFAULT_DESCRIPTION
        assert "付随発話" not in SAY_INLINE_DEFAULT_DESCRIPTION
        assert "長い speech" not in SAY_INLINE_DEFAULT_DESCRIPTION
        # 用途の案内は system prompt の【独白と一言の書き方】へ寄せた。全ツールの
        # schema に同じ段落を複製する代わりに、1 度だけ書いて指す形にしている。
        # ここには「何を書く引数か」と参照だけが残る。
        assert "一言" in SAY_INLINE_DEFAULT_DESCRIPTION
        assert "【独白と一言の書き方】" in SAY_INLINE_DEFAULT_DESCRIPTION

    def test_speech_definition_keeps_channel_description_and_adds_inline_priority(self) -> None:
        """speak は到達範囲説明を保ち、通常報告は say_inline 優先と説明する。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            SPEECH_DEFINITION,
        )
        description = SPEECH_DEFINITION.description
        assert "- whisper:" in description
        assert "- say:" in description
        assert "- shout:" in description
        assert "このツールは発話だけに 1 手を使う" in description
        assert "say_inline に添える方が同じ時間で行動も進む" in description

    def test_say_inline_tool_coverage_is_explicit_for_all_spot_graph_tools(self) -> None:
        """spot_graph tool の say_inline 採否を一覧で固定し、追加時の判断漏れを防ぐ。"""
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            get_spot_graph_specs,
        )
        expected_with_say_inline = {
            TOOL_NAME_SPOT_GRAPH_ATTACK,
            # 売買は「これを買っていくよ」と声を掛けながら行うのが自然で、
            # 同席者に取引が観測されることとも噛み合う。
            TOOL_NAME_SPOT_GRAPH_BUY_ITEM,
            TOOL_NAME_SPOT_GRAPH_SELL_ITEM,
            # 取引は「これでどう?」と声を掛けながら行うのが自然で、同席者に
            # 観測されることとも噛み合う。
            TOOL_NAME_SPOT_GRAPH_TRADE_OFFER,
            TOOL_NAME_SPOT_GRAPH_TRADE_ACCEPT,
            TOOL_NAME_SPOT_GRAPH_TRADE_DECLINE,
            # 板の前での売り買いも、声を掛けながら行うのが自然。値を下げた
            # ことを一言添えられると、値動きが場の会話に乗る。
            #
            # 読むだけの market_view にも添えられる。**読んだことは誰の観測にも
            # ならない**ので、板を見ていると他人に伝える道はこれしかない。
            TOOL_NAME_SPOT_GRAPH_MARKET_VIEW,
            TOOL_NAME_SPOT_GRAPH_MARKET_LIST_ITEM,
            TOOL_NAME_SPOT_GRAPH_MARKET_BUY,
            TOOL_NAME_SPOT_GRAPH_MARKET_REPRICE,
            TOOL_NAME_SPOT_GRAPH_MARKET_CANCEL,
            TOOL_NAME_SPOT_GRAPH_MARKET_BID,
            TOOL_NAME_SPOT_GRAPH_MARKET_SELL,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            TOOL_NAME_SPOT_GRAPH_WAIT,
        }
        expected_without_say_inline = {
            TOOL_NAME_SPEECH,
            TOOL_NAME_SPOT_GRAPH_LISTEN,
            TOOL_NAME_SPOT_GRAPH_REPORT_BODY,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
            TOOL_NAME_SPOT_GRAPH_VOTE,
        }
        definitions = [definition for definition, _ in get_spot_graph_specs()]
        all_tool_names = {definition.name for definition in definitions}
        actual_with_say_inline = {
            definition.name
            for definition in definitions
            if "say_inline" in definition.parameters["properties"]
        }
        actual_without_say_inline = all_tool_names - actual_with_say_inline

        assert actual_with_say_inline == expected_with_say_inline
        assert actual_without_say_inline == expected_without_say_inline
        assert expected_with_say_inline | expected_without_say_inline == all_tool_names
        assert expected_with_say_inline & expected_without_say_inline == set()
        # 件数は集合の assert と重複するが、**集合を書き換えたときに件数の
        # 変化が目に入る**ようにしてある。経済統合 Phase 1 で買いと売りが
        # 加わって 12。
        # 経済統合 Phase 2 で取引 3 つが加わって 15。
        # 経済統合 Phase 3 で市場 4 つが加わって 19、買い板 2 つで 21、
        # 板を読む market_view で 22。
        assert len(actual_with_say_inline) == 22
