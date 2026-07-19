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
from tests.runtime_config_helpers import belief_consolidation_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _transcriber(runtime):
    stack = runtime._episodic_stack
    assert stack is not None
    return stack.chunk_coordinator._belief_evidence_transcriber


class TestWorldRuntimeConfirmationGateWiring:
    def test_belief_axis_provider_is_wired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=belief_consolidation_config(),
        )
        transcriber = _transcriber(runtime)
        assert transcriber is not None
        assert transcriber._belief_axis_provider is not None

    def test_provider_resolves_seeded_belief_axes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """seed した belief の (tags, text) を provider が返す (遅延ルックアップ

        が semantic store に届いている)。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=belief_consolidation_config(),
        )
        transcriber = _transcriber(runtime)
        store = runtime._episodic_stack.semantic_memory_store
        assert store is not None

        # player_id=1 の being を解決し、belief を 1 件 seed する。
        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, PlayerId(1)
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

    def test_provider_resolves_revised_belief_by_entry_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """revise 済み belief (entry_id != belief_id) を、recall が渡す

        現在の entry_id で解決できる。passive recall は entry_id を
        in_context_belief_ids に流すため、belief_id で照合すると revise 済み
        belief が永久にゲートに一致しなくなる回帰を防ぐ。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=belief_consolidation_config(),
        )
        transcriber = _transcriber(runtime)
        store = runtime._episodic_stack.semantic_memory_store
        being_id = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, PlayerId(1)
        )
        # revise 後の状態を模す: 新 entry は別 entry_id を持ち、belief_id は
        # 元の lineage id を継ぐ。recall はこの新 entry の entry_id を流す。
        store.add_by_being(
            being_id,
            SemanticMemoryEntry(
                entry_id="sem-new-after-revise",
                player_id=1,
                text="干潟へ行く道は危険",
                evidence_episode_ids=("ep-0",),
                confidence=0.8,
                created_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
                tags=("干潟", "travel_to"),
                belief_id="sem-orig",
                supersedes="sem-orig",
            ),
        )
        # recall が流すのは現在の entry_id。これで解決できること。
        axes = transcriber._belief_axis_provider(being_id, "sem-new-after-revise")
        assert axes is not None
        assert axes[1] == "干潟へ行く道は危険"
        # 旧 lineage id (belief_id) では解決しない (もう active entry ではない)。
        assert transcriber._belief_axis_provider(being_id, "sem-orig") is None
