"""P3 (CONFIRMATION 関連性ゲート): world_runtime を通した belief_axis_provider の

配線を end-to-end で確認する。BELIEF_EVIDENCE_ENABLED で作られる転記器に
provider が渡り、seed した belief の (tags, text) を semantic store 経由で
遅延解決できることを固定する (配線漏れ silent failure の防波堤)。

LLM は呼ばない。flag は default OFF なので明示的に ON にする。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _enable_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("BELIEF_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("BELIEF_CONSOLIDATION_ENABLED", "1")
    monkeypatch.setenv("SEMANTIC_SEARCH_ENABLED", "1")


def _transcriber(runtime):
    stack = runtime._episodic_stack
    assert stack is not None
    return stack.chunk_coordinator._belief_evidence_transcriber


class TestWorldRuntimeConfirmationGateWiring:
    def test_belief_axis_provider_is_wired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_flags(monkeypatch)
        runtime = create_world_runtime(_SCENARIO_PATH)
        transcriber = _transcriber(runtime)
        assert transcriber is not None
        assert transcriber._belief_axis_provider is not None

    def test_provider_resolves_seeded_belief_axes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """seed した belief の (tags, text) を provider が返す (遅延ルックアップ

        が semantic store に届いている)。"""
        _enable_flags(monkeypatch)
        runtime = create_world_runtime(_SCENARIO_PATH)
        transcriber = _transcriber(runtime)
        store = runtime._episodic_stack.semantic_memory_store
        assert store is not None

        # player_id=1 の being を解決し、belief を 1 件 seed する。
        being_id = runtime._aux_being_resolver.resolve_being_id(
            runtime._aux_being_default_world_id, PlayerId(1)
        )
        assert being_id is not None
        store.add_by_being(
            being_id,
            SemanticMemoryEntry(
                entry_id="sem-x",
                player_id=1,
                text="浜辺では目立った発見はない",
                evidence_episode_ids=("ep-0",),
                confidence=0.6,
                created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                tags=("浜辺", "explore"),
                belief_id="sem-x",
            ),
        )

        axes = transcriber._belief_axis_provider(being_id, "sem-x")
        assert axes is not None
        tags, text = axes
        assert "explore" in tags
        assert text == "浜辺では目立った発見はない"
        # 存在しない belief_id は None。
        assert transcriber._belief_axis_provider(being_id, "ghost") is None
