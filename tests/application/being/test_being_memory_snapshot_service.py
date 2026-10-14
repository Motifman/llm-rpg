"""BeingMemorySnapshotService の capture / restore 挙動 (Phase 4 Step 4-2b)。

5 memory store の状態を Being 単位で JSON 1 本に save / restore できることを
担保する。in-memory store を使った round-trip テストが中心。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    CURRENT_PAYLOAD_SCHEMA_VERSION,
    BeingMemoryPayloadFormatError,
    BeingMemoryPayloadSchemaError,
    BeingMemorySnapshotService,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import InMemoryMemoryLinkStore
from ai_rpg_world.application.llm.services.in_memory_memo_store import InMemoryMemoStore
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import InMemorySemanticMemoryStore
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import InMemorySubjectiveEpisodeStore
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.memo_book import MemoBook, MemoCertainty, MemoKind, MemoProvenance, MemoSource
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import InMemoryMemoBookRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import MemoryLink, MemoryLinkType
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry

_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)

def _make_service() -> tuple[BeingMemorySnapshotService, dict[str, object]]:
    """新しい in-memory store 群を構築し、service と store ハンドルを返す。"""
    from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
        InMemoryBeliefEvidenceBufferStore,
    )
    memo = InMemoryMemoStore()
    semantic = InMemorySemanticMemoryStore()
    link = InMemoryMemoryLinkStore()
    episode = InMemorySubjectiveEpisodeStore()
    belief_evidence = InMemoryBeliefEvidenceBufferStore()
    acquaintances = InMemoryAcquaintanceRepository()
    being_episodes = InMemoryEpisodeRepository()
    being_memo = InMemoryMemoBookRepository()
    svc = BeingMemorySnapshotService(memo_store=memo, semantic_store=semantic, memory_link_store=link, episodic_episode_store=episode, belief_evidence_buffer_store=belief_evidence, acquaintance_store=acquaintances, being_episode_store=being_episodes, being_memo_store=being_memo, memory_turn_clock=InMemoryMemoryTurnClock())
    return (svc, {'memo': memo, 'semantic': semantic, 'link': link, 'episode': episode, 'belief_evidence': belief_evidence, 'acquaintances': acquaintances, 'being_episodes': being_episodes, 'being_memo': being_memo})

def _populate(stores: dict[str, object], being_id: BeingId) -> None:
    """memo / semantic / memory_link / episode に最小サンプルデータを書き込む。"""
    stores['memo'].add_by_being(being_id, '未完了 memo', current_tick=10)
    completed_id = stores['memo'].add_by_being(being_id, '完了 memo', current_tick=11)
    stores['memo'].complete_by_being(being_id, completed_id)
    stores['semantic'].add_by_being(being_id, SemanticMemoryEntry(entry_id='se-1', player_id=1, being_id=being_id, text='一般化要約', evidence_episode_ids=('ep-1',), confidence=0.8, created_at=_NOW, importance_score=7, tags=('tag-a',)))
    stores['semantic'].register_cluster_signature_if_new_by_being(being_id, 'sig-1')
    stores['link'].upsert_link_by_being(being_id, MemoryLink(link_id='mlk-1', player_id=1, being_id=being_id, episode_id_a='ep-1', episode_id_b='ep-2', link_type=MemoryLinkType.CO_RECALL, strength=0.9, co_activation_count=1, created_at=_NOW, last_activated_at=_NOW, decay_rate=0.001))
    stores['episode'].put_by_being(being_id, SubjectiveEpisode(episode_id='ep-1', player_id=1, being_id=being_id, occurred_at=_NOW, game_time_label='12:00', source=EpisodeSource(event_ids=('e1',)), location=EpisodeLocation(spot_id=42, tile_area_ids=(1, 2)), action=EpisodeAction(tool_name='walk'), who=('ada',), what='what', why='why', observed='observed', expected='expected', outcome='ok', prediction_error=None, felt='felt', interpreted='interpreted', cues=(EpisodicCue(axis='place_spot', value='42', source=EpisodicCueSource.RUNTIME_CONTEXT),), recall_text='recall', recall_count=0, last_recalled_at=None))

class TestCapture:
    """capture の挙動。"""

    def test_returns_empty_store_payload(self) -> None:
        """全 store が空でも payload は schema_version と全 key を持つ。"""
        (svc, _) = _make_service()
        being = BeingId('ada')
        payload = json.loads(svc.capture(being))
        assert payload['schema_version'] == CURRENT_PAYLOAD_SCHEMA_VERSION
        for k in ('memo', 'semantic_entries', 'semantic_cluster_signatures', 'memory_links', 'episodic_episodes'):
            assert payload[k] == []

    def test_includes_all_four_store(self) -> None:
        """memo / semantic / memory_link / episode の 4 store の状態を全て載せる。"""
        (svc, stores) = _make_service()
        being = BeingId('ada')
        _populate(stores, being)
        payload = json.loads(svc.capture(being))
        assert len(payload['memo']) == 2
        assert len(payload['semantic_entries']) == 1
        assert payload['semantic_cluster_signatures'] == ['sig-1']
        assert len(payload['memory_links']) == 1
        assert len(payload['episodic_episodes']) == 1

    def test_being_id_raises_type_error(self) -> None:
        """being id 型違反は TypeError。"""
        (svc, _) = _make_service()
        with pytest.raises(TypeError):
            svc.capture('ada')

class TestRestoreRoundTrip:
    """capture → restore で各 store の状態が完全一致する。"""

    def test_full_round_trip(self) -> None:
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        _populate(src_stores, being)
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_svc.restore(being, payload_json)
        assert json.loads(payload_json) == json.loads(dst_svc.capture(being))

    def test_restore_ignores_keys_of_snapshots_saved_before_removal(self) -> None:
        """部品を消す前 (#1631) に保存した snapshot に残る、消した部品のキーは読み飛ばし、ほかの store は復元する。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        _populate(src_stores, being)
        payload = json.loads(src_svc.capture(being))
        old_payload = {**payload, 'pending_predictions': [{'pending_id': 'p1', 'text': '夕方にカイトと会う'}], 'recall_buffer_received_event_ids': ['exp-3@6'], 'recall_buffer_pending': [{'recall_id': 'r-1'}], 'reinterpretation_journal': [{'entry_id': 'je-1'}], 'afterglow_entries': [{'episode_id': 'e3', 'heading': 'h', 'entered_tick': 85, 'source': 'weak_recall'}], 'recall_success_hit_count': [{'episode_id': 'ep-1', 'hit_count': 2}], 'recall_success_received_event_ids': ['exp-2@4'], 'recall_slot_entries': [{'episode_id': 'e1', 'entered_tick': 80}], 'recall_slot_cooldown': [{'episode_id': 'e2', 'tick': 120}], 'recall_habituation_last_recalled': [{'episode_id': 'e4', 'tick': 88}]}
        (dst_svc, _) = _make_service()

        dst_svc.restore(being, json.dumps(old_payload))

        assert json.loads(dst_svc.capture(being)) == payload

    def test_restore_ignores_expectation_keys_of_snapshots_saved_before_removal(self) -> None:
        """予期を消す前 (#1631) に保存した snapshot の expectations / expectation_undelivered_events は読み飛ばし、ほかの store は復元する。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        _populate(src_stores, being)
        payload = json.loads(src_svc.capture(being))
        old_payload = {**payload, 'expectations': [{'expectation_id': 'exp-1'}], 'expectation_undelivered_events': [{'event_id': 'ev-1'}]}
        (dst_svc, _) = _make_service()

        dst_svc.restore(being, json.dumps(old_payload))

        assert json.loads(dst_svc.capture(being)) == payload

    def test_restore_existing_overwrites(self) -> None:
        """restore 先に古い state が入っていても、payload で完全置換される。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        _populate(src_stores, being)
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_stores['memo'].add_by_being(being, '古い memo')
        dst_svc.restore(being, payload_json)
        memos = dst_stores['memo'].list_all_by_being(being)
        contents = sorted(e.content for e in memos)
        assert contents == ['完了 memo', '未完了 memo']

    def test_belief_evidence_buffer_round_trip(self) -> None:
        """U2 (証拠台帳統一設計): evidence buffer の capture → restore で
        中身が一致することを保証する (snapshot 追従 checklist #27)。"""
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
            BELIEF_EVIDENCE_SALIENCE_LOW,
            BeliefEvidence,
        )
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
            BeliefEvidenceSourceKind,
        )
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        evidence = BeliefEvidence(evidence_id='belief-evidence-1', source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR, episode_ids=('ep-1',), cue_signature='tool:explore|spot:3', text='探索は空振りだった', salience=BELIEF_EVIDENCE_SALIENCE_LOW, occurred_at=_NOW, tick=7, observed_turn=0)
        src_stores['belief_evidence'].append_by_being(being, evidence)
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_svc.restore(being, payload_json)
        restored = dst_stores['belief_evidence'].list_all_by_being(being)
        assert len(restored) == 1
        assert restored[0] == evidence

    def test_received_expectation_event_ids_round_trip(self) -> None:
        """証拠バッファが持つ受け取り済みの出来事の ID は、capture → restore で戻り、戻した先で同じ出来事を積み直さない (#1443)。"""
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
            BeliefEvidence,
        )
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
            BeliefEvidenceSourceKind,
        )
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        evidence = BeliefEvidence(evidence_id='belief-evidence-exp-1@3', source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR, episode_ids=('exp-1',), cue_signature='expectation:miss', text='予期は外れた', salience='low', occurred_at=_NOW, observed_turn=3)
        src_stores['belief_evidence'].append_received_by_being(being, evidence, event_id='exp-1@3')
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_svc.restore(being, payload_json)
        assert dst_stores['belief_evidence'].list_received_event_ids_by_being(being) == ['exp-1@3']
        assert dst_stores['belief_evidence'].append_received_by_being(being, evidence, event_id='exp-1@3') is False


    def test_acquaintances_round_trip(self) -> None:
        """会った相手の記録は、環境の名前・相手の名前・会ったターン・回数・名前を知ったか (知ったターン) ごと capture → restore で戻る。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['acquaintances'].record_meeting(being, environment_name='島', name='ノア', turn=0)
        src_stores['acquaintances'].record_meeting(being, environment_name='島', name='ノア', turn=6)
        src_stores['acquaintances'].record_meeting(being, environment_name='山村', name='リオ', turn=9)
        src_stores['acquaintances'].record_introduction(being, environment_name='山村', name='カイ', turn=9, relation_note='あなたと同じ側')
        src_stores['acquaintances'].record_meeting(being, environment_name='山村', name='ゲン', turn=10, knows_name=False)
        src_stores['acquaintances'].record_meeting(being, environment_name='山村', name='サヨ', turn=10, knows_name=False)
        src_stores['acquaintances'].record_name_learned(being, environment_name='山村', name='サヨ', turn=12)
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_stores['acquaintances'].record_meeting(being, environment_name='島', name='カイ', turn=1)
        dst_svc.restore(being, payload_json)
        assert dst_stores['acquaintances'].list_by_being(being) == src_stores['acquaintances'].list_by_being(being)

    def test_malformed_acquaintance_is_rejected_as_format_error(self) -> None:
        """会って知ったのに会った回数が 0 の知り合いが payload にあると、BeingMemoryPayloadFormatError で拒む。"""
        (src_svc, _) = _make_service()
        being = BeingId('ada')
        payload = json.loads(src_svc.capture(being))
        payload['acquaintances'] = [{'environment_name': '島', 'name': 'ノア', 'how_known': 'MET', 'known_since_turn': 0, 'name_learned_turn': 0, 'relation_note': None, 'met_count': 0, 'first_met_turn': None, 'last_met_turn': None}]
        (dst_svc, _) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError):
            dst_svc.restore(being, json.dumps(payload))

    def test_duplicate_acquaintance_is_rejected_before_any_store_is_written(self) -> None:
        """同じ環境の同じ相手が payload に 2 件あると BeingMemoryPayloadFormatError で拒み、どの store も書き換えない。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['memo'].add_by_being(being, '書かれてはいけない', current_tick=1)
        payload = json.loads(src_svc.capture(being))
        met = {'environment_name': '島', 'name': 'ノア', 'how_known': 'MET', 'known_since_turn': 0, 'name_learned_turn': 0, 'relation_note': None, 'met_count': 1, 'first_met_turn': 0, 'last_met_turn': 0}
        payload['acquaintances'] = [met, dict(met)]
        (dst_svc, dst_stores) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError):
            dst_svc.restore(being, json.dumps(payload))
        assert dst_stores['memo'].list_all_by_being(being) == []
        assert dst_stores['acquaintances'].list_by_being(being) == ()

    def test_acquaintance_without_how_known_is_rejected(self) -> None:
        """知り方 (how_known) の無い古い形式の知り合いは、推測で補わず BeingMemoryPayloadFormatError で拒む。互換は保たない (#1436)。"""
        (src_svc, _) = _make_service()
        being = BeingId('ada')
        payload = json.loads(src_svc.capture(being))
        payload['acquaintances'] = [{'environment_name': '島', 'name': 'ノア', 'first_met_turn': 0, 'last_met_turn': 0, 'met_count': 1}]
        (dst_svc, _) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='acquaintances'):
            dst_svc.restore(being, json.dumps(payload))

    def test_acquaintance_without_name_learned_turn_is_rejected(self) -> None:
        """名前を知ったか (name_learned_turn) の無い古い形式の知り合いは、知っている側へ補わず BeingMemoryPayloadFormatError で拒む。補うと、名前を知らない相手の名前がプロンプトに出る (#1581)。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['acquaintances'].record_meeting(being, environment_name='島', name='ノア', turn=0)
        payload = json.loads(src_svc.capture(being))
        del payload['acquaintances'][0]['name_learned_turn']
        (dst_svc, _) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='acquaintances'):
            dst_svc.restore(being, json.dumps(payload))

    def test_being_episodes_round_trip_with_every_field(self) -> None:
        """目次つきのエピソードは、呼び名 (伸ばした呼び名も)・環境の名前・書いた時・目次・本文・呼び出された回数と時・目次の履歴ごと、足した順のまま capture → restore で戻り、戻す先にあった記録は残らない。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        store = src_stores['being_episodes']
        first = Episode.write(episode_id='3f2a7b9c-1d2e-4f00-8a00-000000000001', environment_name='地下の金庫室', written_turn=3, index=EpisodeIndex(summary='金庫の番号を探した', recall_when='金庫や鍵の話が出たとき'), body='棚の裏に紙が貼ってあり、番号の半分だけが読めた。')
        store.add(being, first.recalled_at(turn=5).recalled_at(turn=8).with_revised_index(EpisodeIndex(summary='番号の半分を見つけた', recall_when='数字を考えるとき'), turn=9))
        store.add(being, Episode.write(episode_id='3f2a7bcc-1d2e-4f00-8a00-000000000002', environment_name='島', written_turn=12, index=EpisodeIndex(summary='浜で火をおこした', recall_when='寒いとき'), body='流木を集めて火をおこした。', taken_handles={first.handle}))
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_stores['being_episodes'].add(being, Episode.write(episode_id='aa11bb22-1d2e-4f00-8a00-000000000003', environment_name='島', written_turn=1, index=EpisodeIndex(summary='消えるはず', recall_when='消えるはず'), body='戻す前にあった記録'))
        dst_svc.restore(being, payload_json)
        restored = dst_stores['being_episodes'].list_by_being(being)
        assert restored == store.list_by_being(being)
        assert [e.handle for e in restored] == ['ep_3f2a7b', 'ep_3f2a7bc']

    def test_no_being_episodes_round_trip_as_empty(self) -> None:
        """エピソードが 1 件も無い Being を capture → restore すると、戻す先の記録も空になる。"""
        (src_svc, _) = _make_service()
        being = BeingId('ada')
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_stores['being_episodes'].add(being, Episode.write(episode_id='aa11bb22-1d2e-4f00-8a00-000000000003', environment_name='島', written_turn=1, index=EpisodeIndex(summary='消えるはず', recall_when='消えるはず'), body='戻す前にあった記録'))
        dst_svc.restore(being, payload_json)
        assert json.loads(payload_json)['being_episodes'] == []
        assert dst_stores['being_episodes'].list_by_being(being) == ()

    def test_being_episode_with_too_long_body_is_rejected_as_format_error(self) -> None:
        """本文が 401 字のエピソードが payload にあると、切り詰めずに BeingMemoryPayloadFormatError で拒む。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_episodes'].add(being, Episode.write(episode_id='3f2a7b9c-1d2e-4f00-8a00-000000000001', environment_name='島', written_turn=1, index=EpisodeIndex(summary='浜', recall_when='寒いとき'), body='火'))
        payload = json.loads(src_svc.capture(being))
        payload['being_episodes'][0]['body'] = 'あ' * 401
        (dst_svc, _) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_episodes'):
            dst_svc.restore(being, json.dumps(payload))

    def test_being_episode_without_handle_is_rejected(self) -> None:
        """呼び名 (handle) の無いエピソードは、ID から作り直さず BeingMemoryPayloadFormatError で拒む。作り直すと伸ばした呼び名が 6 文字に戻り、前の呼び名が別の記録を指す。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_episodes'].add(being, Episode.write(episode_id='3f2a7b9c-1d2e-4f00-8a00-000000000001', environment_name='島', written_turn=1, index=EpisodeIndex(summary='浜', recall_when='寒いとき'), body='火'))
        payload = json.loads(src_svc.capture(being))
        del payload['being_episodes'][0]['handle']
        (dst_svc, _) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_episodes'):
            dst_svc.restore(being, json.dumps(payload))

    def test_duplicate_being_episode_handle_is_rejected_before_any_store_is_written(self) -> None:
        """同じ呼び名のエピソードが payload に 2 件あると BeingMemoryPayloadFormatError で拒み、どの store も書き換えない。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['memo'].add_by_being(being, '書かれてはいけない', current_tick=1)
        src_stores['being_episodes'].add(being, Episode.write(episode_id='3f2a7b9c-1d2e-4f00-8a00-000000000001', environment_name='島', written_turn=1, index=EpisodeIndex(summary='浜', recall_when='寒いとき'), body='火'))
        payload = json.loads(src_svc.capture(being))
        twin = dict(payload['being_episodes'][0], episode_id='3f2a7b00-1d2e-4f00-8a00-000000000002')
        payload['being_episodes'].append(twin)
        (dst_svc, dst_stores) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_episodes'):
            dst_svc.restore(being, json.dumps(payload))
        assert dst_stores['memo'].list_all_by_being(being) == []
        assert dst_stores['being_episodes'].list_by_being(being) == ()

    def _memo_book(self) -> MemoBook:
        heard = MemoProvenance(source=MemoSource.HEARD, certainty=MemoCertainty.GUESS, source_from='ミオ')
        book = MemoBook.empty().add(memo_id='3f2a7b9c-1d2e-4f00-8a00-000000000001', kind=MemoKind.TODO, text='事務所で鍵を取る', provenance=None, turn=2, environment_name='水門の町')
        book = book.add(memo_id='3f2a7bcc-1d2e-4f00-8a00-000000000002', kind=MemoKind.FACT, text='弁の目盛りが関係するかも', provenance=heard, turn=4, environment_name='廃坑の山村')
        book = book.add(memo_id='91c0de00-1d2e-4f00-8a00-000000000003', kind=MemoKind.FACT, text='籠は 3 人まで', provenance=MemoProvenance(source=MemoSource.EPISODE, certainty=MemoCertainty.SURE, source_from='ep_a07c33'), turn=5, environment_name='廃坑の山村', known_episode_handles={'ep_a07c33'})
        book = book.add(memo_id='5be41200-1d2e-4f00-8a00-000000000004', kind=MemoKind.PERSON, text='ミオは水門に詳しい', provenance=None, turn=6, environment_name='水門の町')
        return book.edit('m_3f2a7b', text='事務所の金庫で鍵を取る', turn=7)

    def test_being_memo_book_round_trips_with_every_field(self) -> None:
        """メモ帳は、呼び名 (伸ばした呼び名も)・分類・文・出どころ (誰から・どのエピソードから)・確かさ・書いた時・書き換えた時・環境の名前ごと、書いた順のまま capture → restore で戻り、戻す先にあったメモは残らない。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_memo'].save(being, self._memo_book())
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_stores['being_memo'].save(being, MemoBook.empty().add(memo_id='aa11bb22-1d2e-4f00-8a00-000000000005', kind=MemoKind.TODO, text='消えるはず', provenance=None, turn=1, environment_name='島'))
        dst_svc.restore(being, payload_json)
        restored = dst_stores['being_memo'].get(being)
        assert restored == self._memo_book()
        assert [m.handle for m in restored.memos] == ['m_3f2a7b', 'm_3f2a7bc', 'm_91c0de', 'm_5be412']

    def test_empty_memo_book_round_trips_as_empty(self) -> None:
        """メモが 1 件も無い Being を capture → restore すると、戻す先のメモ帳も空になる。"""
        (src_svc, _) = _make_service()
        being = BeingId('ada')
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_stores['being_memo'].save(being, self._memo_book())
        dst_svc.restore(being, payload_json)
        assert json.loads(payload_json)['being_memo_book'] == []
        assert dst_stores['being_memo'].get(being) == MemoBook.empty()

    def test_memo_book_beyond_the_limit_is_rejected_before_any_store_is_written(self) -> None:
        """やることが 6 件ある payload は、上限で切らずに BeingMemoryPayloadFormatError で拒み、どの store も書き換えない。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['memo'].add_by_being(being, '書かれてはいけない', current_tick=1)
        src_stores['being_memo'].save(being, self._memo_book())
        payload = json.loads(src_svc.capture(being))
        todo = payload['being_memo_book'][0]
        payload['being_memo_book'] += [dict(todo, memo_id=f'{n:06x}aa-1d2e-4f00-8a00-000000000000', handle=f'm_{n:06x}') for n in range(5)]
        (dst_svc, dst_stores) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_memo_book'):
            dst_svc.restore(being, json.dumps(payload))
        assert dst_stores['memo'].list_all_by_being(being) == []
        assert dst_stores['being_memo'].get(being) == MemoBook.empty()

    def test_memo_book_with_the_same_handle_twice_is_rejected(self) -> None:
        """同じ呼び名のメモが payload に 2 件あると、どちらかを選ばずに BeingMemoryPayloadFormatError で拒む。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_memo'].save(being, self._memo_book())
        payload = json.loads(src_svc.capture(being))
        twin = dict(payload['being_memo_book'][3], memo_id='5be41211-1d2e-4f00-8a00-000000000009')
        payload['being_memo_book'].append(twin)
        (dst_svc, dst_stores) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_memo_book'):
            dst_svc.restore(being, json.dumps(payload))
        assert dst_stores['being_memo'].get(being) == MemoBook.empty()

    def test_memo_without_handle_is_rejected(self) -> None:
        """呼び名 (handle) の無いメモは、ID から作り直さず BeingMemoryPayloadFormatError で拒む。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_memo'].save(being, self._memo_book())
        payload = json.loads(src_svc.capture(being))
        del payload['being_memo_book'][1]['handle']
        (dst_svc, _) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_memo_book'):
            dst_svc.restore(being, json.dumps(payload))

    def test_belief_evidence_context_belief_ids_round_trip(self) -> None:
        """U4 (予測誤差統一設計 部品3): attribution 用の in_context_belief_ids も
        evidence buffer の capture → restore を経て失われないことを保証する。
        新規 per-Being store は作らず既存 belief_evidence_buffer の codec を
        拡張しただけなので、EXPECTED_PAYLOAD_KEYS の変更は不要 (U4 の設計判断)。
        """
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
            BELIEF_EVIDENCE_SALIENCE_LOW,
            BeliefEvidence,
        )
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
            BeliefEvidenceSourceKind,
        )
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        evidence = BeliefEvidence(evidence_id='belief-evidence-attr-1', source_kind=BeliefEvidenceSourceKind.CONFIRMATION, episode_ids=('ep-1',), cue_signature='tool:explore|spot:3', text='予測が当たった: 何か見つかるはず', salience=BELIEF_EVIDENCE_SALIENCE_LOW, occurred_at=_NOW, tick=7, in_context_belief_ids=('sem-belief-1', 'sem-belief-2'), observed_turn=0)
        src_stores['belief_evidence'].append_by_being(being, evidence)
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_svc.restore(being, payload_json)
        restored = dst_stores['belief_evidence'].list_all_by_being(being)
        assert len(restored) == 1
        assert restored[0].in_context_belief_ids == ('sem-belief-1', 'sem-belief-2')

    def test_belief_evidence_context_belief_ids_legacy_data_empty_tuple(self) -> None:
        """U4 導入前 (キー自体が無い) payload を decode しても例外にならず
        空タプルになる (旧データとの後方互換)。"""
        from ai_rpg_world.application.being._memory_payload_codecs import dict_to_belief_evidence
        data = {'evidence_id': 'belief-evidence-legacy-1', 'source_kind': 'prediction_error', 'episode_ids': ['ep-1'], 'cue_signature': 'tool:explore', 'text': '何もなかった', 'salience': 'low', 'occurred_at': _NOW.isoformat(), 'observed_turn': 0, 'tick': 3}
        evidence = dict_to_belief_evidence(data)
        assert evidence.in_context_belief_ids == ()

    def test_belief_evidence_source_speaker_round_trip(self) -> None:
        """P9 (伝聞): HEARSAY evidence の source_speaker (話者) が capture →
        restore を経て失われないことを保証する。source_kind 拡張と同じく既存
        codec の拡張なので EXPECTED_PAYLOAD_KEYS の変更は不要。"""
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
            BELIEF_EVIDENCE_SALIENCE_LOW,
            BeliefEvidence,
        )
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
            BeliefEvidenceSourceKind,
        )
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        evidence = BeliefEvidence(evidence_id='belief-evidence-hearsay-1', source_kind=BeliefEvidenceSourceKind.HEARSAY, episode_ids=('ep-1',), cue_signature='player:spot_graph_player_5', text='エイダは頼りになる', salience=BELIEF_EVIDENCE_SALIENCE_LOW, occurred_at=_NOW, observed_turn=0, tick=7, source_speaker='リオ')
        src_stores['belief_evidence'].append_by_being(being, evidence)
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_svc.restore(being, payload_json)
        restored = dst_stores['belief_evidence'].list_all_by_being(being)
        assert len(restored) == 1
        assert restored[0].source_kind == BeliefEvidenceSourceKind.HEARSAY
        assert restored[0].source_speaker == 'リオ'

    def test_belief_evidence_observed_turn_round_trip(self) -> None:
        """証拠の観測のターン数 (#1452) が capture → restore を経て同じ値で戻る。"""
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
            BELIEF_EVIDENCE_SALIENCE_LOW,
            BeliefEvidence,
        )
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
            BeliefEvidenceSourceKind,
        )
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        evidence = BeliefEvidence(evidence_id='belief-evidence-turn-1', source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR, episode_ids=('ep-1',), cue_signature='tool:explore', text='浜に枯れ葉が落ちていた', salience=BELIEF_EVIDENCE_SALIENCE_LOW, occurred_at=_NOW, observed_turn=40)
        src_stores['belief_evidence'].append_by_being(being, evidence)
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()

        dst_svc.restore(being, payload_json)

        assert [e.observed_turn for e in dst_stores['belief_evidence'].list_all_by_being(being)] == [40]

    def test_belief_evidence_what_happened_round_trip(self) -> None:
        """外れの材料が持つ時系列 (#1509) が capture → restore を経て同じ並びで戻る。"""
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
            BELIEF_EVIDENCE_SALIENCE_LOW,
            BeliefEvidence,
        )
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
            BeliefEvidenceSourceKind,
        )
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        lines = ('浜に流木は無かった', 'ノア「波が運んでくる」')
        evidence = BeliefEvidence(evidence_id='belief-evidence-miss-1', source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR, episode_ids=('exp-1',), cue_signature='expectation:miss', text='たぶんと思っていた予期「流木を入手できる」は外れた。', salience=BELIEF_EVIDENCE_SALIENCE_LOW, occurred_at=_NOW, observed_turn=5, what_happened=lines)
        src_stores['belief_evidence'].append_by_being(being, evidence)
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()

        dst_svc.restore(being, payload_json)

        assert [e.what_happened for e in dst_stores['belief_evidence'].list_all_by_being(being)] == [lines]

    def test_belief_evidence_without_what_happened_key_decodes_empty(self) -> None:
        """#1509 より前の (キーが無い) 証拠の payload は、例外にせず時系列の無い材料として読む。"""
        from ai_rpg_world.application.being._memory_payload_codecs import dict_to_belief_evidence
        data = {'evidence_id': 'belief-evidence-legacy-4', 'source_kind': 'prediction_error', 'episode_ids': ['ep-1'], 'cue_signature': 'expectation:miss', 'text': '外れた', 'salience': 'low', 'occurred_at': _NOW.isoformat(), 'observed_turn': 0}

        evidence = dict_to_belief_evidence(data)

        assert evidence.what_happened == ()

    def test_semantic_last_observed_turn_round_trip(self) -> None:
        """信念の last_observed_turn (#1452) が capture → restore を経て同じ値で戻る。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['semantic'].add_by_being(being, SemanticMemoryEntry(entry_id='se-turn', player_id=1, being_id=being, text='浜の枯れ葉は時間がたつと戻る', evidence_episode_ids=('ep-1',), confidence=0.6, created_at=_NOW, last_observed_turn=40))
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()

        dst_svc.restore(being, payload_json)

        assert [e.last_observed_turn for e in dst_stores['semantic'].list_for_being(being)] == [40]

    def test_belief_evidence_without_observed_turn_is_rejected(self) -> None:
        """観測のターン数を持たない証拠の payload (#1452 より前の snapshot) は読み込まず、例外で止める。いつ見たかを捏造しない。"""
        from ai_rpg_world.application.being._memory_payload_codecs import dict_to_belief_evidence
        data = {'evidence_id': 'belief-evidence-legacy-3', 'source_kind': 'prediction_error', 'episode_ids': ['ep-1'], 'cue_signature': 'tool:explore', 'text': '何もなかった', 'salience': 'low', 'occurred_at': _NOW.isoformat(), 'tick': 3}
        with pytest.raises((KeyError, ValueError)):
            dict_to_belief_evidence(data)

    def test_belief_evidence_source_speaker_legacy_data_none(self) -> None:
        """P9 導入前 (キー自体が無い) payload を decode しても例外にならず None。"""
        from ai_rpg_world.application.being._memory_payload_codecs import dict_to_belief_evidence
        data = {'evidence_id': 'belief-evidence-legacy-2', 'source_kind': 'prediction_error', 'episode_ids': ['ep-1'], 'cue_signature': 'tool:explore', 'text': '何もなかった', 'salience': 'low', 'occurred_at': _NOW.isoformat(), 'observed_turn': 0, 'tick': 3}
        evidence = dict_to_belief_evidence(data)
        assert evidence.source_speaker is None

    def test_other_being_does_not_affect(self) -> None:
        """他 being は影響しない。"""
        (src_svc, src_stores) = _make_service()
        ada = BeingId('ada')
        ben = BeingId('ben')
        _populate(src_stores, ada)
        src_stores['memo'].add_by_being(ben, 'ben の memo')
        payload_ada = src_svc.capture(ada)
        (dst_svc, dst_stores) = _make_service()
        dst_stores['memo'].add_by_being(ben, 'ben 固有')
        dst_svc.restore(ada, payload_ada)
        ben_memos = [e.content for e in dst_stores['memo'].list_all_by_being(ben)]
        assert ben_memos == ['ben 固有']

class TestRestoreValidation:
    """restore の payload 検査挙動。"""

    def test_str_payload_raises_type_error(self) -> None:
        """非 str payload は TypeError。"""
        (svc, _) = _make_service()
        with pytest.raises(TypeError):
            svc.restore(BeingId('ada'), {})

    def test_invalid_json_raises_format_error(self) -> None:
        """不正 json は FormatError。"""
        (svc, _) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='not valid JSON'):
            svc.restore(BeingId('ada'), 'not json')

    def test_root_object_raises_format_error(self) -> None:
        """root が object でないと FormatError。"""
        (svc, _) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='object'):
            svc.restore(BeingId('ada'), '[]')

    def test_unsupported_schema_version_raises_schema_error(self) -> None:
        """未サポート schema version は SchemaError。"""
        (svc, _) = _make_service()
        bad = json.dumps({'schema_version': 999, 'memo': []})
        with pytest.raises(BeingMemoryPayloadSchemaError, match='999'):
            svc.restore(BeingId('ada'), bad)

    def test_required_key_missing_raises_format_error(self) -> None:
        """required key 欠落は FormatError。"""
        (svc, _) = _make_service()
        bad = json.dumps({'schema_version': CURRENT_PAYLOAD_SCHEMA_VERSION, 'memo': []})
        with pytest.raises(BeingMemoryPayloadFormatError, match='missing required key'):
            svc.restore(BeingId('ada'), bad)

    def test_memo_element_id_missing_raises_format_error(self) -> None:
        """list 要素内の dict key 欠落は KeyError ではなく FormatError に wrap される。"""
        (svc, _) = _make_service()
        bad = json.dumps({'schema_version': CURRENT_PAYLOAD_SCHEMA_VERSION, 'memo': [{'content': 'no id'}], 'semantic_entries': [], 'semantic_cluster_signatures': [], 'memory_links': [], 'episodic_episodes': [], 'belief_evidence_buffer': [], 'belief_evidence_received_event_ids': [], 'memory_turn': [], 'acquaintances': [], 'being_episodes': [], 'being_memo_book': []})
        with pytest.raises(BeingMemoryPayloadFormatError, match='memo'):
            svc.restore(BeingId('ada'), bad)

    def test_unknown_enum_value_raises_format_error(self) -> None:
        """memory_link の link_type が未知値なら FormatError。"""
        (svc, _) = _make_service()
        bad = json.dumps({'schema_version': CURRENT_PAYLOAD_SCHEMA_VERSION, 'memo': [], 'semantic_entries': [], 'semantic_cluster_signatures': [], 'memory_links': [{'link_id': 'x', 'player_id': 1, 'episode_id_a': 'a', 'episode_id_b': 'b', 'link_type': 'UNKNOWN_TYPE', 'strength': 0.5, 'co_activation_count': 1, 'created_at': '2026-06-14T12:00:00+00:00', 'last_activated_at': '2026-06-14T12:00:00+00:00', 'decay_rate': 0.001}], 'episodic_episodes': [], 'belief_evidence_buffer': [], 'belief_evidence_received_event_ids': [], 'memory_turn': [], 'acquaintances': [], 'being_episodes': [], 'being_memo_book': []})
        with pytest.raises(BeingMemoryPayloadFormatError, match='memory_links'):
            svc.restore(BeingId('ada'), bad)

    def test_required_key_list_raises_format_error(self) -> None:
        """required key の値が list でないと FormatError。"""
        (svc, _) = _make_service()
        bad = json.dumps({'schema_version': CURRENT_PAYLOAD_SCHEMA_VERSION, 'memo': 'not-list', 'semantic_entries': [], 'semantic_cluster_signatures': [], 'memory_links': [], 'episodic_episodes': [], 'belief_evidence_buffer': [], 'belief_evidence_received_event_ids': [], 'memory_turn': [], 'acquaintances': [], 'being_episodes': [], 'being_memo_book': []})
        with pytest.raises(BeingMemoryPayloadFormatError, match='must be list'):
            svc.restore(BeingId('ada'), bad)

class TestConstructor:
    """constructor の型ガード。"""

    def test_memo_store_raises_type_error(self) -> None:
        """memo store 型違反。"""
        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )
        with pytest.raises(TypeError, match='memo_store'):
            BeingMemorySnapshotService(memo_store='bad', semantic_store=InMemorySemanticMemoryStore(), memory_link_store=InMemoryMemoryLinkStore(), episodic_episode_store=InMemorySubjectiveEpisodeStore(), belief_evidence_buffer_store=InMemoryBeliefEvidenceBufferStore(), acquaintance_store=InMemoryAcquaintanceRepository(), being_episode_store=InMemoryEpisodeRepository(), being_memo_store=InMemoryMemoBookRepository(), memory_turn_clock=InMemoryMemoryTurnClock())
