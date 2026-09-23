"""profile の型付き判断が、本番の session 構築まで届く。

## 差し替え口の単体試験だけでは足りない

ファクトリが正しい実装を返すことと、**本番の配線がそのファクトリを呼ぶこと**は
別の事実である。呼び忘れた配線は、単体試験を緑にしたまま run で効かない
(design_decisions #41)。

実際に踏んでいる。`interact` の引数 resolver は存在したのに experiment の
配線が呼んでおらず、164 件が INVALID_ARGUMENT で落ちた
(tests/presentation/spot_graph_game/test_item_tool_resolver_wiring.py)。

そのため本番と同じ入口 (``GameRuntimeManager.create_session``) から組み、
session が実装を持っているかを見る。

## 足りない設定は起動前に落とす

`provider=jev` でキーが無い run は、1 件目の判断まで進んでから失敗する。
そこまでの時間と API 費用は戻らない。session を作る時点で落とす。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)

_SCENARIO = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "survival_island_v2.json"
)


@pytest.fixture(autouse=True)
def _without_developer_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """開発者の環境に在るキーが、キー無しの試験に混ざらないようにする。"""
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _session_wiring(config: Any) -> Iterator[Any]:
    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
        GameRuntimeManager,
    )
    from ai_rpg_world.presentation.spot_graph_game.schemas import (
        CharacterCreateRequest,
        SessionCreateRequest,
    )

    with TemporaryDirectory() as tmp:
        manager = GameRuntimeManager(
            scenarios_dir=_SCENARIO.parent,
            characters_path=Path(tmp) / "characters.json",
            runtime_config=config,
        )
        character = manager.create_character(CharacterCreateRequest(name="probe"))
        summary = manager.create_session(
            SessionCreateRequest(
                world_id=_SCENARIO.stem, character_ids=[character.id]
            )
        )
        yield manager._sessions[summary.session_id].llm_wiring


class TestTheSessionCarriesWhatTheProfileAskedFor:
    """profile の provider に応じた実装が、session の配線に載ることを保証する。"""

    def test_a_session_has_no_typed_judgment_by_default(self) -> None:
        """profile が求めなければ、配線は型付き判断を持たない。"""
        for wiring in _session_wiring(ResolvedLlmRuntimeConfig.for_tests()):
            assert wiring.typed_judgment_port is None

    def test_a_session_carries_the_stub_when_the_profile_asks_for_it(self) -> None:
        """provider=stub なら、実 API を呼ばない実装が配線に載る。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="stub")
        ):
            assert isinstance(wiring.typed_judgment_port, DeterministicTypedJudgmentPort)


class TestAMissingKeyStopsTheRunBeforeItStarts:
    """使えるキーが無い設定で、session を作る時点で落ちることを保証する。"""

    def test_jev_without_a_key_fails_at_session_creation(self) -> None:
        """provider=jev でキーが無ければ、session を作る時点で ValueError になる。"""
        with pytest.raises(ValueError) as caught:
            list(
                _session_wiring(
                    ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="jev")
                )
            )

        assert "OPENROUTER_API_KEY" in str(caught.value)

    def test_jev_with_a_placeholder_key_fails_at_session_creation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """キー欄が EMPTY のままなら、session を作る時点で落ちる。

        ローカル vLLM 構成では ``OPENAI_API_KEY`` が ``EMPTY`` になる。その値で
        OpenRouter に送ると 401 になるので、run を始めさせない。
        """
        monkeypatch.setenv("OPENAI_API_KEY", "EMPTY")

        with pytest.raises(ValueError):
            list(
                _session_wiring(
                    ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="jev")
                )
            )


class TestTheArgumentResolverGetsTheJudgment:
    """行動名を解決する resolver に、判断が注入されることを保証する。

    ファクトリと配線が揃っても、最後の 1 本を繋ぎ忘れれば run では何も変わら
    ない。単体試験は緑のままなので静かに効かない (design_decisions #41)。
    """

    def test_the_resolver_can_rescue_when_the_profile_asks_for_judgment(self) -> None:
        """provider が判断を求めていれば、resolver が選び直す口を持つ。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="stub")
        ):
            assert wiring.argument_resolver.action_name_rescue is not None

    def test_the_resolver_has_no_rescue_by_default(self) -> None:
        """profile が求めなければ、resolver は選び直さない (**正の対照**)。"""
        for wiring in _session_wiring(ResolvedLlmRuntimeConfig.for_tests()):
            assert wiring.argument_resolver.action_name_rescue is None

    def test_the_threshold_comes_from_the_profile(self) -> None:
        """置き換えの閾値が profile から resolver まで届く。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(
                typed_judgment_provider="stub",
                typed_judgment_action_name_min_confidence=0.85,
            )
        ):
            rescue = wiring.argument_resolver.action_name_rescue
            assert rescue is not None
            assert rescue.min_confidence == 0.85



class TestTheArgumentResolverGetsTheTargetLabelJudgment:
    """対象の名前を解決する resolver にも、判断が注入されることを保証する。"""

    def test_the_resolver_can_rescue_target_labels_when_the_profile_asks_for_judgment(self) -> None:
        """provider が判断を求めていれば、resolver は対象名を選び直す口を持つ。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="stub")
        ):
            assert wiring.argument_resolver.target_label_rescue is not None

    def test_the_resolver_has_no_target_label_rescue_by_default(self) -> None:
        """profile が求めなければ、resolver は対象名を選び直さない (**正の対照**)。"""
        for wiring in _session_wiring(ResolvedLlmRuntimeConfig.for_tests()):
            assert wiring.argument_resolver.target_label_rescue is None

    def test_the_target_label_threshold_comes_from_the_profile(self) -> None:
        """対象名の閾値が profile から resolver まで届き、既定は行動名より高い 0.85。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="stub")
        ):
            assert wiring.argument_resolver.target_label_rescue.min_confidence == 0.85
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(
                typed_judgment_provider="stub",
                typed_judgment_target_label_min_confidence=0.9,
            )
        ):
            assert wiring.argument_resolver.target_label_rescue.min_confidence == 0.9


class TestTheArgumentResolverKnowsWhichToolsExist:
    """「種類が違う」の失敗文に載せるツール名が、この世界の露出判断を通ることを保証する。

    露出判断を注入し忘れると、resolver は全ツールを在るものとして勧める。シナリオが
    `disabled_tools` で落としたツールを失敗文が宣伝し、当人は存在しないツールを呼ぶ。
    """

    def test_the_resolver_answers_exposure_with_the_runtime_decision(self) -> None:
        """session の resolver は runtime.tool_exposure と同じ答えを返す口を持つ。"""
        for wiring in _session_wiring(ResolvedLlmRuntimeConfig.for_tests()):
            asks = wiring.argument_resolver._tool_is_exposed
            assert asks is not None
            exposure = wiring.runtime.tool_exposure
            for tool in ("attack", "travel_to", "give_item", "no_such_tool"):
                assert asks(tool) == exposure.is_exposed(tool)


class TestTheTurnTriggerGetsTheGate:
    """tick の終わりに回す人を決める trigger に、起動判定が挟まることを保証する。

    起動判定のクラスと trigger の差し込み口が揃っても、本番配線が渡さなければ run では
    全員が回り続ける。単体試験は緑のままなので静かに効かない。
    """

    def test_the_wiring_has_a_gate_when_the_profile_turns_it_on(self) -> None:
        """判断ポートがあり、起動判定を明示的に有効にした profile では、配線は tick 単位の起動判定を持つ。"""
        from ai_rpg_world.application.llm.services.world_llm_turn.turn_gate import TurnGate

        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(
                typed_judgment_provider="stub",
                typed_judgment_turn_gate_enabled=True,
                typed_judgment_turn_gate_skip_below=0.2,
            )
        ):
            gate = wiring.turn_gate
            assert isinstance(gate, TurnGate)
            assert gate.judgment_port is wiring.typed_judgment_port
            assert gate.skip_below == 0.2

    def test_the_wiring_has_no_gate_by_default(self) -> None:
        """profile が求めなければ、配線は起動判定を持たない (**正の対照**)。"""
        for wiring in _session_wiring(ResolvedLlmRuntimeConfig.for_tests()):
            assert wiring.turn_gate is None

    def test_judgment_alone_does_not_bring_the_gate(self) -> None:
        """provider だけを入れた profile では、判断ポートは載るが起動判定は入らない (既定 off)。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="stub")
        ):
            assert wiring.typed_judgment_port is not None
            assert wiring.turn_gate is None


class TestTheWiringGetsTheToolNameJudgment:
    """存在しない tool 名への提案を選ぶ口に、判断と profile の閾値が届くことを保証する (#1413)。"""

    def test_the_wiring_can_rescue_tool_names_when_the_profile_asks_for_judgment(self) -> None:
        """provider が判断を求めていれば、配線は tool 名の提案を意味で選ぶ口を持つ。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="stub")
        ):
            assert wiring.tool_name_rescue is not None

    def test_the_wiring_has_no_tool_name_rescue_by_default(self) -> None:
        """profile が判断を求めなければ、配線は判断を問う口を持たない (**正の対照**)。"""
        for wiring in _session_wiring(ResolvedLlmRuntimeConfig.for_tests()):
            assert wiring.tool_name_rescue is None

    def test_the_tool_name_threshold_comes_from_the_profile(self) -> None:
        """閾値が profile から配線まで届き、既定は 0.7。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="stub")
        ):
            assert wiring.tool_name_rescue.min_confidence == 0.7
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(
                typed_judgment_provider="stub",
                typed_judgment_tool_name_min_confidence=0.9,
            )
        ):
            assert wiring.tool_name_rescue.min_confidence == 0.9


class TestTheLoopGuardGetsTheDiagnosis:
    """ループ警告の出し口に、繰り返しの理由の見立て (#1411) が届くことを保証する。"""

    def test_the_loop_guard_has_the_diagnosis_when_the_profile_turns_it_on(self) -> None:
        """判断ポートがあり見立てを有効にした profile では、loop guard は同じポートと profile の閾値で見立てを持つ。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(
                typed_judgment_provider="stub",
                typed_judgment_loop_diagnosis_enabled=True,
                typed_judgment_loop_diagnosis_min_confidence=0.8,
            )
        ):
            diagnosis = wiring.tool_call_loop_guard.loop_diagnosis
            assert diagnosis is not None
            assert diagnosis.port is wiring.typed_judgment_port
            assert diagnosis.min_confidence == 0.8

    def test_judgment_alone_does_not_bring_the_diagnosis(self) -> None:
        """provider だけを入れた profile では、判断ポートは載るが見立ては入らない (既定 off)。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="stub")
        ):
            assert wiring.typed_judgment_port is not None
            assert wiring.tool_call_loop_guard.loop_diagnosis is None

    def test_enabling_without_a_port_brings_no_diagnosis(self) -> None:
        """provider が off なら、見立てを有効にしても入らない。判断ポートが無いため。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_loop_diagnosis_enabled=True)
        ):
            assert wiring.tool_call_loop_guard.loop_diagnosis is None


class TestTheLoopGuardGetsTheSemanticRepeatDetector:
    """ループ警告に、意味上の繰り返しの検出器 (#1412) が届くことを保証する。"""

    def test_the_detector_arrives_with_the_profile_settings(self) -> None:
        """判断ポートがあり検出を有効にした profile では、同じポートと profile の閾値・窓で検出器を持つ。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(
                typed_judgment_provider="stub",
                typed_judgment_semantic_repeat_enabled=True,
                typed_judgment_semantic_repeat_min_probability=0.9,
                typed_judgment_semantic_repeat_window=5,
            )
        ):
            detector = wiring.tool_call_loop_guard.semantic_repeat_detector
            assert detector is not None
            assert detector.judgment_port is wiring.typed_judgment_port
            assert detector.threshold == 0.9
            assert detector.window_size == 5

    def test_judgment_alone_does_not_bring_the_detector(self) -> None:
        """provider だけを入れた profile では、判断ポートは載るが検出器は入らない (既定 off)。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_provider="stub")
        ):
            assert wiring.typed_judgment_port is not None
            assert wiring.tool_call_loop_guard.semantic_repeat_detector is None

    def test_enabling_without_a_port_brings_no_detector(self) -> None:
        """provider が off なら、検出を有効にしても入らない。判断ポートが無いため。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(typed_judgment_semantic_repeat_enabled=True)
        ):
            assert wiring.tool_call_loop_guard.semantic_repeat_detector is None
