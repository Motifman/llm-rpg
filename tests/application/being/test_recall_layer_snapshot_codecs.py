"""
Recall Slot / Afterglow / Habituation の snapshot codec と
``BeingMemorySnapshotService`` 統合の単体テスト (PR-G)。

PR-F で導入した ``EXPECTED_PAYLOAD_KEYS`` SSOT に 4 key (slot entries /
slot cooldown / afterglow / habituation) を追加し、capture → restore の
往復で 3 store の状態が完全復元されることを保証する。
"""

import json

import pytest

from ai_rpg_world.application.being._memory_payload_codecs import (
    afterglow_entry_to_dict,
    dict_to_afterglow_entry,
    dict_to_episode_tick_pair,
    dict_to_recall_slot_entry,
    episode_tick_pair_to_dict,
    recall_slot_entry_to_dict,
)
from ai_rpg_world.application.llm.services.afterglow_store import (
    AfterglowEntry,
    AfterglowSource,
)
from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
    RecallSlotEntry,
)


class TestRecallSlotEntryCodec:
    """``RecallSlotEntry`` ↔ dict の 1:1 往復が VO のフィールドを保つ。"""

    def test_round_trip_preserves_fields(self):
        original = RecallSlotEntry(episode_id="ep-001", entered_tick=5)
        restored = dict_to_recall_slot_entry(recall_slot_entry_to_dict(original))
        assert restored == original


class TestAfterglowEntryCodec:
    """``AfterglowEntry`` ↔ dict の 1:1 往復。source enum も復元される。"""

    def test_round_trip_preserves_fields(self):
        original = AfterglowEntry(
            episode_id="ep-002",
            heading="シキに今日の話をしたが届かなかった",
            entered_tick=14,
            source=AfterglowSource.WEAK_RECALL,
        )
        restored = dict_to_afterglow_entry(afterglow_entry_to_dict(original))
        assert restored == original

    def test_unknown_source_raises_value_error(self):
        """source の文字列が AfterglowSource に存在しない値ならエラー。"""
        with pytest.raises((ValueError, KeyError)):
            dict_to_afterglow_entry({
                "episode_id": "ep-x",
                "heading": "h",
                "entered_tick": 1,
                "source": "not_a_real_source",
            })


class TestSemanticEntryCodecBeliefJournal:
    """U3a: ``SemanticMemoryEntry`` の belief journal フィールドの codec round-trip。"""

    def test_round_trip_preserves_belief_journal_fields(self):
        from datetime import datetime, timezone

        from ai_rpg_world.application.being._memory_payload_codecs import (
            dict_to_semantic_entry,
            semantic_entry_to_dict,
        )
        from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
            SemanticMemoryEntry,
        )

        original = SemanticMemoryEntry(
            entry_id="e1",
            player_id=1,
            text="ノアは機嫌が悪いと無視する",
            evidence_episode_ids=("ep-1",),
            confidence=0.7,
            created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            belief_id="belief-noah-mood",
            status="superseded",
            supersedes="e0",
            support_evidence_ids=("ev-1", "ev-2"),
            contradict_evidence_ids=("ev-3",),
        )
        restored = dict_to_semantic_entry(semantic_entry_to_dict(original))
        assert restored == original

    def test_旧_snapshot_dict_new_key_無しは_default_に倒れる(self):
        """belief journal キーが無い旧 snapshot dict → status=active / belief_id
        は entry_id にフォールバックする (後方互換)。"""
        from ai_rpg_world.application.being._memory_payload_codecs import (
            dict_to_semantic_entry,
        )

        legacy_dict = {
            "entry_id": "legacy-e1",
            "player_id": 1,
            "text": "旧 snapshot の学び",
            "evidence_episode_ids": ["ep-1"],
            "confidence": 0.5,
            "created_at": "2026-01-01T00:00:00+00:00",
            "importance_score": 5,
            "tags": [],
        }
        restored = dict_to_semantic_entry(legacy_dict)
        assert restored.belief_id == "legacy-e1"
        assert restored.status == "active"
        assert restored.supersedes is None
        assert restored.support_evidence_ids == ()
        assert restored.contradict_evidence_ids == ()


class TestEpisodeTickPairCodec:
    """``cooldown`` と ``habituation`` で共有する {episode_id, tick} の dict 変換。"""

    def test_round_trip(self):
        d = episode_tick_pair_to_dict("ep-001", 42)
        eid, tick = dict_to_episode_tick_pair(d)
        assert eid == "ep-001"
        assert tick == 42


class TestBeingMemorySnapshotRecallLayerRoundTrip:
    """``BeingMemorySnapshotService`` の capture → restore で
    Slot / Afterglow / Habituation の状態が完全復元される。"""

    def _make_service_with_recall_layer(self):
        """既存 6 store + 新規 3 store を全て in-memory で構築する。"""
        from ai_rpg_world.application.being.being_memory_snapshot_service import (
            BeingMemorySnapshotService,
        )
        from ai_rpg_world.application.llm.services.afterglow_store import (
            InMemoryAfterglowStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
            InMemoryEpisodicRecallHabituationStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
            InMemoryEpisodicRecallSlotStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
            InMemoryMemoryLinkStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
            InMemoryEpisodicRecallBufferStore,
            InMemoryEpisodicReinterpretationJournalStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_memo_store import (
            InMemoryMemoStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
            InMemorySemanticMemoryStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
            InMemorySubjectiveEpisodeStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )

        slot = InMemoryEpisodicRecallSlotStore()
        afterglow = InMemoryAfterglowStore()
        habituation = InMemoryEpisodicRecallHabituationStore()
        service = BeingMemorySnapshotService(
            memo_store=InMemoryMemoStore(),
            semantic_store=InMemorySemanticMemoryStore(),
            memory_link_store=InMemoryMemoryLinkStore(),
            recall_buffer_store=InMemoryEpisodicRecallBufferStore(),
            reinterpretation_journal_store=InMemoryEpisodicReinterpretationJournalStore(),
            episodic_episode_store=InMemorySubjectiveEpisodeStore(),
            recall_slot_store=slot,
            afterglow_store=afterglow,
            recall_habituation_store=habituation,
            belief_evidence_buffer_store=InMemoryBeliefEvidenceBufferStore(),
        )
        return service, slot, afterglow, habituation

    def test_capture_emits_new_payload_keys(self):
        """capture() の出力 JSON に 4 新キーが必ず含まれる。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        service, _, _, _ = self._make_service_with_recall_layer()
        payload = json.loads(service.capture(BeingId("being-test")))
        assert "recall_slot_entries" in payload
        assert "recall_slot_cooldown" in payload
        assert "afterglow_entries" in payload
        assert "recall_habituation_last_recalled" in payload

    def test_round_trip_restores_recall_slot_and_cooldown(self):
        """slot に entry を載せ cooldown を設定 → capture → 別 Being で restore
        したら同じ状態に戻る。"""
        from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
            RecallSlotDecision,
            RecallSlotEntry,
        )
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        service, slot, _, _ = self._make_service_with_recall_layer()
        bid = BeingId("being-A")
        # snapshot 復元 API (replace_all_by_being) を直接使って既知の state を作る。
        slot.replace_all_by_being(
            bid,
            slot=(
                RecallSlotEntry(episode_id="ep-001", entered_tick=3),
                RecallSlotEntry(episode_id="ep-002", entered_tick=5),
            ),
            cooldown_until={"ep-old": 15},
        )

        # capture
        payload = service.capture(bid)

        # 別 Being に restore して、状態が同一になることを確認
        bid2 = BeingId("being-B")
        service.restore(bid2, payload)
        assert slot.get_slot(bid2) == slot.get_slot(bid)
        assert slot.get_cooldown_until(bid2) == slot.get_cooldown_until(bid)

    def test_round_trip_restores_afterglow_index(self):
        """afterglow に entry を投入 → capture → 別 Being で restore で復元。"""
        from ai_rpg_world.application.llm.services.afterglow_store import (
            AfterglowEntry,
            AfterglowSource,
        )
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        service, _, afterglow, _ = self._make_service_with_recall_layer()
        bid = BeingId("being-A")
        new_index = (
            AfterglowEntry(
                episode_id="ep-x", heading="海辺で見た光", entered_tick=10,
                source=AfterglowSource.WEAK_RECALL,
            ),
            AfterglowEntry(
                episode_id="ep-y", heading="森で薬草を採った", entered_tick=12,
                source=AfterglowSource.SLOT_EVICTED,
            ),
        )
        afterglow.apply_decision(bid, new_index=new_index)

        payload = service.capture(bid)
        bid2 = BeingId("being-B")
        service.restore(bid2, payload)
        assert afterglow.get_index(bid2) == afterglow.get_index(bid)

    def test_round_trip_restores_habituation_map(self):
        """habituation に record_recall した tick が capture → restore で残る。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        service, _, _, habituation = self._make_service_with_recall_layer()
        bid = BeingId("being-A")
        habituation.record_recall(bid, episode_ids=["ep-1"], tick=7)
        habituation.record_recall(bid, episode_ids=["ep-2"], tick=11)

        payload = service.capture(bid)
        bid2 = BeingId("being-B")
        service.restore(bid2, payload)
        assert habituation.get_last_recalled_tick(bid2, "ep-1") == 7
        assert habituation.get_last_recalled_tick(bid2, "ep-2") == 11

    def test_round_trip_with_empty_stores(self):
        """3 store がすべて空でも capture / restore は通る (= 退化ケース)。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        service, slot, afterglow, habituation = self._make_service_with_recall_layer()
        bid = BeingId("being-empty")
        payload = service.capture(bid)
        service.restore(BeingId("being-restored"), payload)
        # 復元先も空のまま
        assert slot.get_slot(BeingId("being-restored")) == ()
        assert afterglow.get_index(BeingId("being-restored")) == ()
