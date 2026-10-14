"""``SemanticMemoryEntry`` の snapshot codec が belief journal とターン数の欄を往復させることを保証する。"""


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
