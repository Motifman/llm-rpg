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



class TestTheTurnTriggerGetsTheGate:
    """tick の終わりに回す人を決める trigger に、門が挟まることを保証する。

    門のクラスと trigger の差し込み口が揃っても、本番配線が渡さなければ run では
    全員が回り続ける。単体試験は緑のままなので静かに効かない。
    """

    def test_the_wiring_has_a_gate_when_the_profile_asks_for_judgment(self) -> None:
        """provider が判断を求めていれば、配線は tick 単位の門を持つ。"""
        from ai_rpg_world.application.llm.services.world_llm_turn.turn_gate import TurnGate

        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(
                typed_judgment_provider="stub",
                typed_judgment_turn_gate_skip_below=0.2,
            )
        ):
            gate = wiring.turn_gate
            assert isinstance(gate, TurnGate)
            assert gate.judgment_port is wiring.typed_judgment_port
            assert gate.skip_below == 0.2

    def test_the_wiring_has_no_gate_by_default(self) -> None:
        """profile が求めなければ、配線は門を持たない (**正の対照**)。"""
        for wiring in _session_wiring(ResolvedLlmRuntimeConfig.for_tests()):
            assert wiring.turn_gate is None

    def test_the_gate_can_be_turned_off_while_keeping_the_judgment(self) -> None:
        """門だけを外した profile では、判断ポートは残り配線は門を持たない。"""
        for wiring in _session_wiring(
            ResolvedLlmRuntimeConfig.for_tests(
                typed_judgment_provider="stub",
                typed_judgment_turn_gate_enabled=False,
            )
        ):
            assert wiring.typed_judgment_port is not None
            assert wiring.turn_gate is None
