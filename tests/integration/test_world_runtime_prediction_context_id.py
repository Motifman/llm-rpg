"""U1 (予測誤差統一設計 部品1): world_runtime を通した prediction_context_id
発行 → 消費の配線を end-to-end で確認する。

DefaultPromptBuilder (build_full_prompt) と ActionResultRecorder
(_record_action_result 経由の do_*) が同じ PredictionContextLedger を
共有していることを、実際の runtime 呼び出し順で検証する。LLM は呼ばない
(build_full_prompt はプロンプト組み立てのみ、do_wait は tool 実行のみ)。

id 機構は ``PREDICTION_CONTEXT_ID_ENABLED`` env で default OFF (共通規約
§0) なので、各テストで明示的に ON にする。OFF 時の後方互換は
``test_id_機構_OFF_なら_prediction_context_id_は常に_None`` で別途確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


@pytest.fixture(autouse=True)
def _enable_prediction_context_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PREDICTION_CONTEXT_ID_ENABLED", "1")


class TestWorldRuntimePredictionContextIdWiring:
    def test_build_full_prompt_の直後の_do_wait_で_id_が_consume_される(self) -> None:
        runtime = create_world_runtime(_SCENARIO_PATH)
        player_id = runtime.get_player_ids()[0]

        prompt = runtime.build_full_prompt(player_id)
        issued_id = prompt["prediction_context_id"]
        assert issued_id is not None
        assert issued_id.startswith("predctx-")

        # builder と recorder が同じ ledger を共有していれば、issue 直後の
        # 状態は「未消費で 1 件 pending」。
        ledger = runtime._get_prediction_context_ledger()
        assert ledger.peek(player_id).prediction_context_id == issued_id

        runtime.do_wait(player_id)

        # record() が consume したので pending は空になり、
        # 実際に積まれた ActionResultEntry に id が焼き込まれている。
        assert ledger.peek(player_id) is None
        entries = runtime._action_result_store.get_recent(player_id, limit=1)
        assert len(entries) == 1
        assert entries[0].prediction_context_id == issued_id

    def test_build_を挟まず_do_wait_だけを呼ぶと_id_は_None(self) -> None:
        """id は build 経由でしか発行されない。build を経ない action 記録は
        引き続き None (= 既存挙動と同じ)。"""
        runtime = create_world_runtime(_SCENARIO_PATH)
        player_id = runtime.get_player_ids()[0]

        runtime.do_wait(player_id)

        entries = runtime._action_result_store.get_recent(player_id, limit=1)
        assert len(entries) == 1
        assert entries[0].prediction_context_id is None

    def test_build_だけ呼んで_record_されないと次の_build_で破棄される(self) -> None:
        """no-tool ターン相当: build だけ 2 回連続で呼ぶと 1 回目の id は
        consume されないまま破棄される。"""
        runtime = create_world_runtime(_SCENARIO_PATH)
        player_id = runtime.get_player_ids()[0]

        first = runtime.build_full_prompt(player_id)["prediction_context_id"]
        second = runtime.build_full_prompt(player_id)["prediction_context_id"]

        assert first != second
        ledger = runtime._get_prediction_context_ledger()
        assert ledger.peek(player_id).prediction_context_id == second


class TestPredictionContextIdDisabledByDefault:
    def test_env_未設定なら_ledger_は_None_で_prediction_context_id_は常に_None(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """共通規約 §0: 新機構は明示的に有効化しない限り動かさない。"""
        monkeypatch.delenv("PREDICTION_CONTEXT_ID_ENABLED", raising=False)
        runtime = create_world_runtime(_SCENARIO_PATH)
        player_id = runtime.get_player_ids()[0]

        assert runtime._get_prediction_context_ledger() is None
        prompt = runtime.build_full_prompt(player_id)
        assert prompt["prediction_context_id"] is None

        runtime.do_wait(player_id)
        entries = runtime._action_result_store.get_recent(player_id, limit=1)
        assert entries[0].prediction_context_id is None
