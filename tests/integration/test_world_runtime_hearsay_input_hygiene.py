"""H-1 (伝聞の入力衛生 / 横断レビュー): HEARSAY_ENABLED は BELIEF_EVIDENCE_ENABLED

(evidence buffer + transcriber) が前提であることを world_runtime の配線で保証する。

抽出側 (chunk 主観補完 LLM の heard_claims 節) だけを HEARSAY_ENABLED=1 で ON にし、
転記側 (BeliefEvidenceTranscriber) の前提である BELIEF_EVIDENCE_ENABLED を OFF の
ままにすると、抽出コスト (prompt 節 + LLM 出力) を払うだけで転記点が transcriber
None のため黙って捨てる「誘うのに黙って捨てる」静かな失敗になる (MEMO_DISTILL
事件と同じ構造)。GOAL_REVISION_ENABLED × GOAL_STORE_ENABLED (P6) と同じパターンで、
BELIEF_EVIDENCE が OFF なら HEARSAY も実効 OFF に畳む。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from tests.runtime_config_helpers import episodic_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


class TestHearsayFoldedIntoBeliefEvidence:
    """HEARSAY_ENABLED は BELIEF_EVIDENCE_ENABLED が ON でなければ実効 OFF に畳まれる。"""

    def test_hearsay_on_かつ_belief_evidence_off_なら実効offに畳まれ警告が出る(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """config ミス (HEARSAY ON / BELIEF_EVIDENCE OFF) でも heard_claims

        抽出を有効化しない = 「誘うのに黙って捨てる」静かな失敗を作らない。
        併せて、config ミスに気付けるよう WARNING ログを出す。
        """
        with caplog.at_level(logging.WARNING):
            runtime = create_world_runtime(
                _SCENARIO_PATH,
                config=episodic_config(hearsay_enabled=True),
            )
        assert runtime._hearsay_enabled is False
        assert any(
            "HEARSAY_ENABLED" in r.message and "BELIEF_EVIDENCE_ENABLED" in r.message
            for r in caplog.records
        )

    def test_hearsay_on_かつ_belief_evidence_on_なら実効onになる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=episodic_config(
                hearsay_enabled=True,
                belief_evidence_enabled=True,
            ),
        )
        assert runtime._hearsay_enabled is True

    def test_hearsay_未設定なら_belief_evidence_onでも実効offのまま(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HEARSAY_ENABLED 自体を要求していないときは、BELIEF_EVIDENCE_ENABLED

        が ON でも HEARSAY は ON にならない (畳み込みは「要求を弱める」方向のみ)。
        """
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=episodic_config(belief_evidence_enabled=True),
        )
        assert runtime._hearsay_enabled is False

    def test_両方offなら実効offで警告も出ない(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            runtime = create_world_runtime(_SCENARIO_PATH, config=episodic_config())
        assert runtime._hearsay_enabled is False
        assert not any("HEARSAY_ENABLED" in r.message for r in caplog.records)
