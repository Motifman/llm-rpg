"""
Recall Slot / Habituation の snapshot codec と
``BeingMemorySnapshotService`` 統合の単体テスト (PR-G)。

PR-F で導入した ``EXPECTED_PAYLOAD_KEYS`` SSOT の 3 key (slot entries /
slot cooldown / habituation) について、capture → restore の往復で 2 store の
状態が完全復元されることを保証する。
"""
import json

import pytest

from ai_rpg_world.application.being._memory_payload_codecs import (
    dict_to_episode_tick_pair,
    dict_to_recall_slot_entry,
    episode_tick_pair_to_dict,
    recall_slot_entry_to_dict,
)
from ai_rpg_world.application.llm.services.episodic_recall_slot_store import RecallSlotEntry
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import InMemoryMemoBookRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock


class TestRecallSlotEntryCodec:
    """``RecallSlotEntry`` ↔ dict の 1:1 往復が VO のフィールドを保つ。"""

    def test_round_trip_preserves_fields(self):
        original = RecallSlotEntry(episode_id='ep-001', entered_tick=5)
        restored = dict_to_recall_slot_entry(recall_slot_entry_to_dict(original))
        assert restored == original

class TestSemanticEntryCodecBeliefJournal:
    """U3a: ``SemanticMemoryEntry`` の belief journal フィールドの codec round-trip。"""

    def test_round_trip_preserves_belief_journal_fields(self):
        from datetime import datetime, timezone

        from ai_rpg_world.application.being._memory_payload_codecs import dict_to_semantic_entry, semantic_entry_to_dict
        from ai_rpg_world.domain.being.value_object.being_id import BeingId
        from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
        original = SemanticMemoryEntry(entry_id='e1', player_id=1, being_id=BeingId("being_w1_p1"), text='ノアは機嫌が悪いと無視する', evidence_episode_ids=('ep-1',), confidence=0.7, created_at=datetime(2026, 7, 1, tzinfo=timezone.utc), belief_id='belief-noah-mood', status='superseded', supersedes='e0', support_evidence_ids=('ev-1', 'ev-2'), contradict_evidence_ids=('ev-3',), confirmation_support_count=1, hearsay_support_count=1)
        restored = dict_to_semantic_entry(semantic_entry_to_dict(original))
        assert restored == original
        assert restored.confirmation_support_count == 1
        assert restored.hearsay_support_count == 1

    def test_round_trip_preserves_last_observed_turn(self):
        """信念の last_observed_turn (#1452) が snapshot の dict を往復して同じ値で戻る。"""
        from datetime import datetime, timezone

        from ai_rpg_world.application.being._memory_payload_codecs import dict_to_semantic_entry, semantic_entry_to_dict
        from ai_rpg_world.domain.being.value_object.being_id import BeingId
        from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
        original = SemanticMemoryEntry(entry_id='e1', player_id=1, being_id=BeingId("being_w1_p1"), text='浜の枯れ葉は時間がたつと戻る', evidence_episode_ids=('ep-1',), confidence=0.7, created_at=datetime(2026, 7, 1, tzinfo=timezone.utc), last_observed_turn=40)

        restored = dict_to_semantic_entry(semantic_entry_to_dict(original))

        assert restored.last_observed_turn == 40

    def test_dict_without_last_observed_turn_restores_none(self):
        """last_observed_turn のキーが無い dict は、観測のターン数が分からない信念 (None) として戻る。0 などの値を捏造しない。"""
        from ai_rpg_world.application.being._memory_payload_codecs import dict_to_semantic_entry
        from ai_rpg_world.domain.being.value_object.being_id import BeingId
        legacy_dict = {'entry_id': 'legacy-e2', 'player_id': 1, 'text': '旧 snapshot の学び', 'evidence_episode_ids': ['ep-1'], 'confidence': 0.5, 'created_at': '2026-01-01T00:00:00+00:00'}

        restored = dict_to_semantic_entry(legacy_dict, fallback_being_id=BeingId("being_w1_p1"))

        assert restored.last_observed_turn is None

    def test_legacy_snapshot_dict_new_key_default(self):
        """belief journal キーが無い旧 snapshot dict → status=active / belief_id
        は entry_id にフォールバックする (後方互換)。"""
        from ai_rpg_world.application.being._memory_payload_codecs import dict_to_semantic_entry
        from ai_rpg_world.domain.being.value_object.being_id import BeingId
        legacy_dict = {'entry_id': 'legacy-e1', 'player_id': 1, 'text': '旧 snapshot の学び', 'evidence_episode_ids': ['ep-1'], 'confidence': 0.5, 'created_at': '2026-01-01T00:00:00+00:00', 'importance_score': 5, 'tags': []}
        restored = dict_to_semantic_entry(
            legacy_dict, fallback_being_id=BeingId("being_w1_p1")
        )
        assert restored.belief_id == 'legacy-e1'
        assert restored.status == 'active'
        assert restored.supersedes is None
        assert restored.support_evidence_ids == ()
        assert restored.contradict_evidence_ids == ()
        assert restored.confirmation_support_count == 0
        assert restored.hearsay_support_count == 0
        assert restored.being_id == BeingId("being_w1_p1")

class TestEpisodeTickPairCodec:
    """``cooldown`` と ``habituation`` で共有する {episode_id, tick} の dict 変換。"""

    def test_round_trip(self):
        d = episode_tick_pair_to_dict('ep-001', 42)
        (eid, tick) = dict_to_episode_tick_pair(d)
        assert eid == 'ep-001'
        assert tick == 42

class TestBeingMemorySnapshotRecallLayerRoundTrip:
    """``BeingMemorySnapshotService`` の capture → restore で
    Slot / Habituation の状態が完全復元される。"""

    def _make_service_with_recall_layer(self):
        """想起階層の 2 store を含む store を全て in-memory で構築する。"""
        from ai_rpg_world.application.being.being_memory_snapshot_service import BeingMemorySnapshotService
        from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
            InMemoryEpisodicRecallHabituationStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_slot_store import InMemoryEpisodicRecallSlotStore
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )
        from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import InMemoryMemoryLinkStore
        from ai_rpg_world.application.llm.services.in_memory_memo_store import InMemoryMemoStore
        from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import InMemorySemanticMemoryStore
        from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
            InMemorySubjectiveEpisodeStore,
        )
        slot = InMemoryEpisodicRecallSlotStore()
        habituation = InMemoryEpisodicRecallHabituationStore()
        service = BeingMemorySnapshotService(memo_store=InMemoryMemoStore(), semantic_store=InMemorySemanticMemoryStore(), memory_link_store=InMemoryMemoryLinkStore(), episodic_episode_store=InMemorySubjectiveEpisodeStore(), recall_slot_store=slot, recall_habituation_store=habituation, belief_evidence_buffer_store=InMemoryBeliefEvidenceBufferStore(), acquaintance_store=InMemoryAcquaintanceRepository(), being_episode_store=InMemoryEpisodeRepository(), being_memo_store=InMemoryMemoBookRepository(), memory_turn_clock=InMemoryMemoryTurnClock())
        return (service, slot, habituation)

    def test_capture_emits_new_payload_keys(self):
        """capture() の出力 JSON に想起階層の 3 キーが必ず含まれ、消した afterglow_entries は含まれない。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId
        (service, _, _) = self._make_service_with_recall_layer()
        payload = json.loads(service.capture(BeingId('being-test')))
        assert 'recall_slot_entries' in payload
        assert 'recall_slot_cooldown' in payload
        assert 'afterglow_entries' not in payload
        assert 'recall_habituation_last_recalled' in payload

    def test_round_trip_restores_recall_slot_and_cooldown(self):
        """slot に entry を載せ cooldown を設定 → capture → 別 Being で restore
        したら同じ状態に戻る。"""
        from ai_rpg_world.application.llm.services.episodic_recall_slot_store import RecallSlotDecision, RecallSlotEntry
        from ai_rpg_world.domain.being.value_object.being_id import BeingId
        (service, slot, _) = self._make_service_with_recall_layer()
        bid = BeingId('being-A')
        slot.replace_all_by_being(bid, slot=(RecallSlotEntry(episode_id='ep-001', entered_tick=3), RecallSlotEntry(episode_id='ep-002', entered_tick=5)), cooldown_until={'ep-old': 15})
        payload = service.capture(bid)
        bid2 = BeingId('being-B')
        service.restore(bid2, payload)
        assert slot.get_slot(bid2) == slot.get_slot(bid)
        assert slot.get_cooldown_until(bid2) == slot.get_cooldown_until(bid)

    def test_round_trip_restores_habituation_map(self):
        """habituation に record_recall した tick が capture → restore で残る。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId
        (service, _, habituation) = self._make_service_with_recall_layer()
        bid = BeingId('being-A')
        habituation.record_recall(bid, episode_ids=['ep-1'], tick=7)
        habituation.record_recall(bid, episode_ids=['ep-2'], tick=11)
        payload = service.capture(bid)
        bid2 = BeingId('being-B')
        service.restore(bid2, payload)
        assert habituation.get_last_recalled_tick(bid2, 'ep-1') == 7
        assert habituation.get_last_recalled_tick(bid2, 'ep-2') == 11

    def test_round_trip_with_empty_stores(self):
        """2 store がすべて空でも capture / restore は通る (= 退化ケース)。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId
        (service, slot, habituation) = self._make_service_with_recall_layer()
        bid = BeingId('being-empty')
        payload = service.capture(bid)
        service.restore(BeingId('being-restored'), payload)
        assert slot.get_slot(BeingId('being-restored')) == ()

