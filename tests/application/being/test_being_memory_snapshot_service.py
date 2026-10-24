"""BeingMemorySnapshotService の capture / restore 挙動 (Phase 4 Step 4-2b)。

5 memory store の状態を Being 単位で JSON 1 本に save / restore できることを
担保する。in-memory store を使った round-trip テストが中心。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being._memory_payload_codecs import being_episode_to_dict
from ai_rpg_world.application.being.being_memory_snapshot_service import (
    CURRENT_PAYLOAD_SCHEMA_VERSION,
    BeingMemoryPayloadFormatError,
    BeingMemoryPayloadSchemaError,
    BeingMemorySnapshotService,
)
from ai_rpg_world.being.contract import (
    UNKNOWN,
    AgentMove,
    EnvironmentNotice,
    Observation,
    ObservedTime,
    OccurrenceOrder,
    OwnActionResult,
    OwnBodyState,
    SeenOrHeard,
    ToldOrWritten,
)
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.memo_book import MemoBook, MemoCertainty, MemoKind, MemoProvenance, MemoSource
from ai_rpg_world.being.domain.short_term_memory import (
    Attempt,
    Backstory,
    Lapse,
    MemoryOperationResult,
    Perception,
    ShortTermMemory,
)
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import InMemoryAcquaintanceRepository
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import InMemoryMemoBookRepository
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import InMemoryMemoryTurnClock
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import InMemoryShortTermMemoryRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId

_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)

def _make_service() -> tuple[BeingMemorySnapshotService, dict[str, object]]:
    """新しい in-memory store 群を構築し、service と store ハンドルを返す。"""
    acquaintances = InMemoryAcquaintanceRepository()
    being_episodes = InMemoryEpisodeRepository()
    being_memo = InMemoryMemoBookRepository()
    short_term = InMemoryShortTermMemoryRepository()
    svc = BeingMemorySnapshotService(acquaintance_store=acquaintances, being_episode_store=being_episodes, being_memo_store=being_memo, memory_turn_clock=InMemoryMemoryTurnClock(), being_short_term_memory_store=short_term)
    return (svc, {'acquaintances': acquaintances, 'being_episodes': being_episodes, 'being_memo': being_memo, 'short_term': short_term})

def _populate(stores: dict[str, object], being_id: BeingId) -> None:
    """知り合いに最小サンプルデータを書き込む。"""
    stores['acquaintances'].record_meeting(being_id, environment_name='島', name='カイト', turn=3)

class TestCapture:
    """capture の挙動。"""

    def test_returns_empty_store_payload(self) -> None:
        """全 store が空でも payload は schema_version と全 key を持つ。"""
        (svc, _) = _make_service()
        being = BeingId('ada')
        payload = json.loads(svc.capture(being))
        assert payload['schema_version'] == CURRENT_PAYLOAD_SCHEMA_VERSION
        for k in ('acquaintances', 'being_episodes', 'being_memo_book', 'being_short_term_memory'):
            assert payload[k] == []

    def test_includes_acquaintance_store(self) -> None:
        """知り合いの store の状態を載せる。"""
        (svc, stores) = _make_service()
        being = BeingId('ada')
        _populate(stores, being)
        payload = json.loads(svc.capture(being))
        assert len(payload['acquaintances']) == 1

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
        old_payload = {**payload, 'memo': [{'id': 'm1', 'content': '古いメモ', 'added_at_tick': 4}], 'pending_predictions': [{'pending_id': 'p1', 'text': '夕方にカイトと会う'}], 'recall_buffer_received_event_ids': ['exp-3@6'], 'recall_buffer_pending': [{'recall_id': 'r-1'}], 'reinterpretation_journal': [{'entry_id': 'je-1'}], 'afterglow_entries': [{'episode_id': 'e3', 'heading': 'h', 'entered_tick': 85, 'source': 'weak_recall'}], 'recall_success_hit_count': [{'episode_id': 'ep-1', 'hit_count': 2}], 'recall_success_received_event_ids': ['exp-2@4'], 'recall_slot_entries': [{'episode_id': 'e1', 'entered_tick': 80}], 'recall_slot_cooldown': [{'episode_id': 'e2', 'tick': 120}], 'recall_habituation_last_recalled': [{'episode_id': 'e4', 'tick': 88}], 'belief_evidence_buffer': [{'evidence_id': 'ev-1', 'tick': 9}], 'belief_evidence_received_event_ids': ['exp-1@3'], 'memory_links': [{'link_id': 'mlk-1'}], 'semantic_entries': [{'entry_id': 'se-1', 'text': '一般化要約'}], 'semantic_cluster_signatures': ['sig-1'], 'episodic_episodes': [{'episode_id': 'ep-1'}]}
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
        _populate(src_stores, being)
        payload = json.loads(src_svc.capture(being))
        met = {'environment_name': '島', 'name': 'ノア', 'how_known': 'MET', 'known_since_turn': 0, 'name_learned_turn': 0, 'relation_note': None, 'met_count': 1, 'first_met_turn': 0, 'last_met_turn': 0}
        payload['acquaintances'] = [met, dict(met)]
        (dst_svc, dst_stores) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError):
            dst_svc.restore(being, json.dumps(payload))
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
        first.recall(turn=5)
        first.recall(turn=8)
        first.revise_index(EpisodeIndex(summary='番号の半分を見つけた', recall_when='数字を考えるとき'), turn=9)
        store.add(being, first)
        store.add(being, Episode.write(episode_id='3f2a7bcc-1d2e-4f00-8a00-000000000002', environment_name='島', written_turn=12, index=EpisodeIndex(summary='浜で火をおこした', recall_when='寒いとき'), body='流木を集めて火をおこした。', taken_handles={first.handle}))
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_stores['being_episodes'].add(being, Episode.write(episode_id='aa11bb22-1d2e-4f00-8a00-000000000003', environment_name='島', written_turn=1, index=EpisodeIndex(summary='消えるはず', recall_when='消えるはず'), body='戻す前にあった記録'))
        dst_svc.restore(being, payload_json)
        restored = dst_stores['being_episodes'].list_by_being(being)
        assert [being_episode_to_dict(e) for e in restored] == [being_episode_to_dict(e) for e in store.list_by_being(being)]
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
        _populate(src_stores, being)
        src_stores['being_episodes'].add(being, Episode.write(episode_id='3f2a7b9c-1d2e-4f00-8a00-000000000001', environment_name='島', written_turn=1, index=EpisodeIndex(summary='浜', recall_when='寒いとき'), body='火'))
        payload = json.loads(src_svc.capture(being))
        twin = dict(payload['being_episodes'][0], episode_id='3f2a7b00-1d2e-4f00-8a00-000000000002')
        payload['being_episodes'].append(twin)
        (dst_svc, dst_stores) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_episodes'):
            dst_svc.restore(being, json.dumps(payload))
        assert dst_stores['being_episodes'].list_by_being(being) == ()

    def _memo_book(self, being: BeingId = BeingId('ada')) -> MemoBook:
        heard = MemoProvenance(source=MemoSource.HEARD, certainty=MemoCertainty.GUESS, source_from='ミオ')
        book = MemoBook.empty(being)
        book.add(memo_id='3f2a7b9c-1d2e-4f00-8a00-000000000001', kind=MemoKind.TODO, text='事務所で鍵を取る', provenance=None, turn=2, environment_name='水門の町')
        book.add(memo_id='3f2a7bcc-1d2e-4f00-8a00-000000000002', kind=MemoKind.FACT, text='弁の目盛りが関係するかも', provenance=heard, turn=4, environment_name='廃坑の山村')
        book.add(memo_id='91c0de00-1d2e-4f00-8a00-000000000003', kind=MemoKind.FACT, text='籠は 3 人まで', provenance=MemoProvenance(source=MemoSource.EPISODE, certainty=MemoCertainty.SURE, source_from='ep_a07c33'), turn=5, environment_name='廃坑の山村', known_episode_handles={'ep_a07c33'})
        book.add(memo_id='5be41200-1d2e-4f00-8a00-000000000004', kind=MemoKind.PERSON, text='ミオは水門に詳しい', provenance=None, turn=6, environment_name='水門の町')
        book.edit('m_3f2a7b', text='事務所の金庫で鍵を取る', turn=7)
        return book

    def test_being_memo_book_round_trips_with_every_field(self) -> None:
        """メモ帳は、呼び名 (伸ばした呼び名も)・分類・文・出どころ (誰から・どのエピソードから)・確かさ・書いた時・書き換えた時・環境の名前ごと、書いた順のまま capture → restore で戻り、戻す先にあったメモは残らない。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_memo'].save(self._memo_book(being))
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        stale = MemoBook.empty(being)
        stale.add(memo_id='aa11bb22-1d2e-4f00-8a00-000000000005', kind=MemoKind.TODO, text='消えるはず', provenance=None, turn=1, environment_name='島')
        dst_stores['being_memo'].save(stale)
        dst_svc.restore(being, payload_json)
        restored = dst_stores['being_memo'].get(being)
        assert restored.memos == self._memo_book(being).memos
        assert [m.handle for m in restored.memos] == ['m_3f2a7b', 'm_3f2a7bc', 'm_91c0de', 'm_5be412']

    def test_capture_keeps_the_book_as_it_was_when_taken(self) -> None:
        """capture したあとでメモ帳を書き換えて保存しても、戻すのは capture した時のメモ帳。

        capture はその場で文字列にするので、ここで見るのは取った時点の中身が残ること。保存先が写しを渡すことは、保存先の試験で見る。
        """
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_memo'].save(self._memo_book(being))
        payload_json = src_svc.capture(being)
        later = src_stores['being_memo'].get(being)
        later.remove('m_3f2a7b')
        src_stores['being_memo'].save(later)
        (dst_svc, dst_stores) = _make_service()

        dst_svc.restore(being, payload_json)

        assert dst_stores['being_memo'].get(being).memos == self._memo_book(being).memos

    def test_restored_book_belongs_to_the_restored_being(self) -> None:
        """restore で戻したメモ帳は、戻した先の Being の ID を持ち、イベントを持たない。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_memo'].save(self._memo_book(being))
        (dst_svc, dst_stores) = _make_service()

        dst_svc.restore(being, src_svc.capture(being))

        restored = dst_stores['being_memo'].get(being)
        assert (restored.being_id, restored.get_events()) == (being, [])

    def test_empty_memo_book_round_trips_as_empty(self) -> None:
        """メモが 1 件も無い Being を capture → restore すると、戻す先のメモ帳も空になる。"""
        (src_svc, _) = _make_service()
        being = BeingId('ada')
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()
        dst_stores['being_memo'].save(self._memo_book(being))
        dst_svc.restore(being, payload_json)
        assert json.loads(payload_json)['being_memo_book'] == []
        assert dst_stores['being_memo'].get(being).memos == ()

    def test_memo_book_beyond_the_limit_is_rejected_before_any_store_is_written(self) -> None:
        """やることが 6 件ある payload は、上限で切らずに BeingMemoryPayloadFormatError で拒み、どの store も書き換えない。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        _populate(src_stores, being)
        src_stores['being_memo'].save(self._memo_book(being))
        payload = json.loads(src_svc.capture(being))
        todo = payload['being_memo_book'][0]
        payload['being_memo_book'] += [dict(todo, memo_id=f'{n:06x}aa-1d2e-4f00-8a00-000000000000', handle=f'm_{n:06x}') for n in range(5)]
        (dst_svc, dst_stores) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_memo_book'):
            dst_svc.restore(being, json.dumps(payload))
        assert dst_stores['being_memo'].get(being).memos == ()

    def test_memo_book_with_the_same_handle_twice_is_rejected(self) -> None:
        """同じ呼び名のメモが payload に 2 件あると、どちらかを選ばずに BeingMemoryPayloadFormatError で拒む。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_memo'].save(self._memo_book(being))
        payload = json.loads(src_svc.capture(being))
        twin = dict(payload['being_memo_book'][3], memo_id='5be41211-1d2e-4f00-8a00-000000000009')
        payload['being_memo_book'].append(twin)
        (dst_svc, dst_stores) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_memo_book'):
            dst_svc.restore(being, json.dumps(payload))
        assert dst_stores['being_memo'].get(being).memos == ()

    def test_memo_without_handle_is_rejected(self) -> None:
        """呼び名 (handle) の無いメモは、ID から作り直さず BeingMemoryPayloadFormatError で拒む。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_memo'].save(self._memo_book(being))
        payload = json.loads(src_svc.capture(being))
        del payload['being_memo_book'][1]['handle']
        (dst_svc, _) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_memo_book'):
            dst_svc.restore(being, json.dumps(payload))

    def test_other_being_does_not_affect(self) -> None:
        """他 being は影響しない。"""
        (src_svc, src_stores) = _make_service()
        ada = BeingId('ada')
        ben = BeingId('ben')
        _populate(src_stores, ada)
        src_stores['acquaintances'].record_meeting(ben, environment_name='島', name='ノア', turn=1)
        payload_ada = src_svc.capture(ada)
        (dst_svc, dst_stores) = _make_service()
        dst_stores['acquaintances'].record_meeting(ben, environment_name='島', name='リン', turn=2)
        dst_svc.restore(ada, payload_ada)
        assert [a.name for a in dst_stores['acquaintances'].list_by_being(ben)] == ['リン']

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
        bad = json.dumps({'schema_version': 999, 'memory_turn': []})
        with pytest.raises(BeingMemoryPayloadSchemaError, match='999'):
            svc.restore(BeingId('ada'), bad)

    def test_required_key_missing_raises_format_error(self) -> None:
        """required key 欠落は FormatError。"""
        (svc, _) = _make_service()
        bad = json.dumps({'schema_version': CURRENT_PAYLOAD_SCHEMA_VERSION, 'memory_turn': []})
        with pytest.raises(BeingMemoryPayloadFormatError, match='missing required key'):
            svc.restore(BeingId('ada'), bad)

    def test_memo_book_element_id_missing_raises_format_error(self) -> None:
        """list 要素内の dict key 欠落は KeyError ではなく FormatError に wrap される。"""
        (svc, _) = _make_service()
        bad = json.dumps({'schema_version': CURRENT_PAYLOAD_SCHEMA_VERSION, 'memory_turn': [], 'acquaintances': [], 'being_episodes': [], 'being_memo_book': [{'text': 'no id'}]})
        with pytest.raises(BeingMemoryPayloadFormatError, match='being_memo_book'):
            svc.restore(BeingId('ada'), bad)

    def test_invalid_being_episode_raises_format_error(self) -> None:
        """being_episodes の要素がドメインの検証で弾かれると、ValueError ではなく FormatError に wrap される。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['being_episodes'].add(being, Episode.write(episode_id='aa11bb22-1d2e-4f00-8a00-000000000009', environment_name='島', written_turn=1, index=EpisodeIndex(summary='s', recall_when='r'), body='b'))
        payload = json.loads(src_svc.capture(being))
        payload['being_episodes'][0]['written_turn'] = -1
        (svc, _) = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match=r"being_episodes.*invalid being episode payload"):
            svc.restore(being, json.dumps(payload))

    def test_required_key_list_raises_format_error(self) -> None:
        """required key の値が list でないと FormatError。"""
        (svc, _) = _make_service()
        bad = json.dumps({'schema_version': CURRENT_PAYLOAD_SCHEMA_VERSION, 'memory_turn': [], 'acquaintances': 'not-list', 'being_episodes': [], 'being_memo_book': []})
        with pytest.raises(BeingMemoryPayloadFormatError, match='must be list'):
            svc.restore(BeingId('ada'), bad)

class TestConstructor:
    """constructor の型ガード。"""

    def test_short_term_memory_store_of_wrong_type_raises_type_error(self) -> None:
        """短期記憶の store に ShortTermMemoryRepository でない値を渡すと TypeError を投げる。"""
        with pytest.raises(TypeError, match='being_short_term_memory_store'):
            BeingMemorySnapshotService(acquaintance_store=InMemoryAcquaintanceRepository(), being_episode_store=InMemoryEpisodeRepository(), being_memo_store=InMemoryMemoBookRepository(), memory_turn_clock=InMemoryMemoryTurnClock(), being_short_term_memory_store=InMemoryMemoBookRepository())


class TestPayloadKeyTables:
    """後から足したキーの表が、必須のキーの表と食い違わないことを保証する。"""

    def test_added_keys_are_part_of_expected_keys(self) -> None:
        """ADDED_PAYLOAD_KEYS のキーは、どれも EXPECTED_PAYLOAD_KEYS にもある。ADDED にだけ足すと capture も restore もそのキーを扱わない。"""
        assert BeingMemorySnapshotService.ADDED_PAYLOAD_KEYS <= BeingMemorySnapshotService.EXPECTED_PAYLOAD_KEYS


def _every_field_short_term_memory(being: BeingId = BeingId('ada')) -> ShortTermMemory:
    """5 つの経路、分かる欄と「不明」の両方、入れ子の引数、起きた順のあるものと無いもの、出来事の 3 つの種類と試みの結果の 3 つの形、範囲の始まり、結果を待つ 1 手、いきさつ 2 世代を含む短期記憶。"""
    def observation(route: object, **fields: object) -> Observation:
        base: dict[str, object] = {'body': 'ミオが坑道から戻ってきた', 'route': route, 'time': ObservedTime(display='1日目 朝'), 'subject_is_self': False, 'subject_name': UNKNOWN, 'source': UNKNOWN, 'place': UNKNOWN, 'addressed_to_self': UNKNOWN}
        return Observation(**{**base, **fields})
    experiences = (
        Perception(turn=11, observation=observation(SeenOrHeard(), subject_name='ミオ', source='ミオ', place='坑道の入口', addressed_to_self=False, body_if_subject_unknown='誰かが坑道から戻ってきた', wants_wake=True, time=ObservedTime(display='1日目 朝', seconds=21600.0))),
        Perception(turn=11, observation=observation(ToldOrWritten(), subject_name='カイト', withheld_if_subject_unknown=True, wants_wake=False)),
        Perception(turn=11, observation=observation(OwnBodyState(), body='少し空腹だ', subject_is_self=True)),
        Perception(turn=11, observation=observation(EnvironmentNotice(), body='日が暮れた', order=OccurrenceOrder(environment='廃坑の山村', value=1729000000.25))),
        Attempt(turn=11, move=AgentMove(call_id='call-1', tool_name='interact', arguments={'target': '扉', 'options': {'force': True, 'tries': [1, 2.5, None, 'again']}}, expectation='扉が開く', inner_thought='鍵が要るかもしれない'), result=observation(OwnActionResult(call_id='call-1', succeeded=False), body='扉は開かなかった', subject_is_self=True, addressed_to_self=True)),
        Attempt(turn=12, move=AgentMove(call_id='call-2', tool_name='speak', arguments={}), result=observation(OwnActionResult(call_id='call-2', succeeded=True), body='挨拶した', subject_is_self=True, order=OccurrenceOrder(environment='廃坑の山村', value=1729000001.5))),
        Attempt(turn=13, move=AgentMove(call_id='call-3', tool_name='memo_add', arguments={'text': '鍵を探す'}), result=MemoryOperationResult(call_id='call-3', body='[行動] メモを書いた → [結果] メモを追加しました', time=ObservedTime(display='1日目 昼', seconds=43200.0), order=OccurrenceOrder(environment='廃坑の山村', value=1729000002.0))),
        Attempt(turn=14, move=AgentMove(call_id='call-4', tool_name='interact', arguments={'target': '弁'})),
        Lapse(turn=15, body='[行動] 迷い → [失敗] | 決められなかった', time=ObservedTime(display='1日目 昼'), order=OccurrenceOrder(environment='廃坑の山村', value=1729000003.0)),
    )
    backstories = (Backstory(flow='坑道の奥で鍵を探していた', mood='少し焦っている', written_turn=10), Backstory(flow='鍵を見つけて村へ戻った', mood='', written_turn=10))
    awaiting = Attempt(turn=16, move=AgentMove(call_id='call-6', tool_name='wait', arguments={}))
    return ShortTermMemory(being, experiences=experiences, backstories=backstories, recent_from=11, awaiting=awaiting)


def _state(memory: ShortTermMemory) -> tuple[object, ...]:
    return (memory.being_id, memory.experiences, memory.backstories, memory.recent_from, memory.awaiting)


class TestShortTermMemoryPayload:
    """短期記憶 (#1824) を Being の snapshot で往復させ、キーを足す前の snapshot も読めることを保証する。"""

    def test_empty_short_term_memory_round_trips_as_empty_list(self) -> None:
        """まだ誰も書いていない短期記憶は [] で保存され、戻しても空のまま。"""
        (src_svc, _) = _make_service()
        being = BeingId('ada')
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()

        dst_svc.restore(being, payload_json)

        assert json.loads(payload_json)['being_short_term_memory'] == []
        assert dst_stores['short_term'].get(being).is_empty()

    def test_snapshot_saved_before_the_key_was_added_restores_the_other_stores(self) -> None:
        """短期記憶のキーを足す前に保存した snapshot は、キーが無くても落ちず、短期記憶は空、ほかの store は元どおりに戻る。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        _populate(src_stores, being)
        payload = json.loads(src_svc.capture(being))
        old_payload = {k: v for (k, v) in payload.items() if k != 'being_short_term_memory'}
        (dst_svc, dst_stores) = _make_service()
        dst_stores['short_term'].save(_every_field_short_term_memory())

        dst_svc.restore(being, json.dumps(old_payload))

        assert dst_stores['short_term'].get(being).is_empty()
        assert json.loads(dst_svc.capture(being)) == payload

    def test_every_field_round_trips(self) -> None:
        """5 つの経路、「不明」の欄、入れ子の引数、出来事と試みの結果のすべての形、範囲の始まり、結果を待つ 1 手、いきさつを持つ短期記憶が、保存して戻すと元と等しい。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['short_term'].save(_every_field_short_term_memory())
        payload_json = src_svc.capture(being)
        (dst_svc, dst_stores) = _make_service()

        dst_svc.restore(being, payload_json)

        assert _state(dst_stores['short_term'].get(being)) == _state(_every_field_short_term_memory())

    def test_more_than_one_memory_is_rejected(self) -> None:
        """1 つの Being に短期記憶が 2 つ書かれた payload は FormatError。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['short_term'].save(_every_field_short_term_memory())
        payload = json.loads(src_svc.capture(being))
        payload['being_short_term_memory'] = payload['being_short_term_memory'] * 2
        (svc, _) = _make_service()

        with pytest.raises(BeingMemoryPayloadFormatError, match='being_short_term_memory'):
            svc.restore(being, json.dumps(payload))

    def test_experiences_out_of_turn_order_are_rejected_before_any_store_is_written(self) -> None:
        """出来事がターンの順に並んでいない payload は FormatError になり、どの store も書き換えない。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        _populate(src_stores, being)
        src_stores['being_episodes'].add(being, Episode.write(episode_id='aa11bb22-1d2e-4f00-8a00-000000000009', environment_name='島', written_turn=1, index=EpisodeIndex(summary='s', recall_when='r'), body='b'))
        book = MemoBook.empty(being)
        book.add(memo_id='3f2a7b9c-1d2e-4f00-8a00-000000000001', kind=MemoKind.TODO, text='鍵を取る', provenance=None, turn=1, environment_name='島')
        src_stores['being_memo'].save(book)
        src_stores['short_term'].save(_every_field_short_term_memory())
        payload = json.loads(src_svc.capture(being))
        payload['being_short_term_memory'][0]['experiences'].reverse()
        (svc, stores) = _make_service()

        with pytest.raises(BeingMemoryPayloadFormatError, match='invalid being short-term memory payload'):
            svc.restore(being, json.dumps(payload))
        assert tuple(stores['acquaintances'].list_by_being(being)) == ()
        assert tuple(stores['being_episodes'].list_by_being(being)) == ()
        assert stores['being_memo'].get(being).memos == ()
        assert stores['short_term'].get(being).is_empty()

    def test_unknown_route_kind_is_rejected(self) -> None:
        """経路の種類が 5 つのどれでもない payload は FormatError。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['short_term'].save(_every_field_short_term_memory())
        payload = json.loads(src_svc.capture(being))
        payload['being_short_term_memory'][0]['experiences'][0]['observation']['route']['kind'] = 'dreamed'
        (svc, _) = _make_service()

        with pytest.raises(BeingMemoryPayloadFormatError, match='being_short_term_memory'):
            svc.restore(being, json.dumps(payload))


    def test_unknown_experience_kind_is_rejected(self) -> None:
        """出来事の種類が見たこと・試み・出せなかったことのどれでもない payload は FormatError。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['short_term'].save(_every_field_short_term_memory())
        payload = json.loads(src_svc.capture(being))
        payload['being_short_term_memory'][0]['experiences'][0]['kind'] = 'dream'
        (svc, _) = _make_service()

        with pytest.raises(BeingMemoryPayloadFormatError, match='being_short_term_memory'):
            svc.restore(being, json.dumps(payload))

    def test_memory_saved_before_the_aggregate_restores_as_perceptions_and_attempts(self) -> None:
        """集約に作り直す前の形 (events に観測と 1 手) の payload は、1 手の無い出来事を Perception、1 手のある出来事を結果つきの Attempt として戻し、範囲の始まりは 1、待っている 1 手は無い (design_decisions D1824-9)。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        payload = json.loads(src_svc.capture(being))
        seen = {'body': '鐘が鳴った', 'route': {'kind': 'seen_or_heard'}, 'time': {'display': '1日目 朝', 'seconds': None}, 'subject_is_self': False, 'subject_name': None, 'source': None, 'place': None, 'addressed_to_self': None, 'wants_wake': None, 'body_if_subject_unknown': None, 'withheld_if_subject_unknown': False}
        result = {**seen, 'body': '待った', 'route': {'kind': 'own_action_result', 'call_id': 'call-1', 'succeeded': True}, 'subject_is_self': True}
        move = {'call_id': 'call-1', 'tool_name': 'wait', 'arguments': {}, 'expectation': None, 'inner_thought': None}
        payload['being_short_term_memory'] = [{'events': [{'turn': 1, 'observation': seen, 'move': None}, {'turn': 1, 'observation': result, 'move': move}], 'backstories': []}]
        (svc, stores) = _make_service()

        svc.restore(being, json.dumps(payload))

        memory = stores['short_term'].get(being)
        assert [type(e) for e in memory.experiences] == [Perception, Attempt]
        assert (memory.recent_from, memory.awaiting) == (1, None)


class TestCapturedSnapshotIsACopy:
    """snapshot を取ったあとで集約を書き換えても、取った snapshot が変わらないことを保証する。"""

    def test_changes_after_capture_do_not_reach_the_snapshot(self) -> None:
        """snapshot を取ったあとで観測を足して保存しても、取った snapshot から戻した短期記憶には入らない。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['short_term'].save(_every_field_short_term_memory())
        payload_json = src_svc.capture(being)
        memory = src_stores['short_term'].get(being)
        memory.perceive(Observation(body='後から届いた', route=SeenOrHeard(), time=ObservedTime(display='1日目 夜'), subject_is_self=False, subject_name=UNKNOWN, source=UNKNOWN, place=UNKNOWN, addressed_to_self=UNKNOWN), current_turn=16)
        src_stores['short_term'].save(memory)
        (dst_svc, dst_stores) = _make_service()

        dst_svc.restore(being, payload_json)

        assert _state(dst_stores['short_term'].get(being)) == _state(_every_field_short_term_memory())


class TestOccurrenceOrderPayload:
    """起きた順を足す前に保存した短期記憶も読めることを保証する (design_decisions D1824-8)。"""

    def test_events_saved_before_the_order_was_added_restore_without_order(self) -> None:
        """観測の payload に order が無ければ、起きた順の無い観測として戻る。"""
        (src_svc, src_stores) = _make_service()
        being = BeingId('ada')
        src_stores['short_term'].save(_every_field_short_term_memory())
        payload = json.loads(src_svc.capture(being))
        observations = [
            e.get('observation') or (e.get('result') or {}).get('observation')
            for e in payload['being_short_term_memory'][0]['experiences']
        ]
        popped = [o.pop('order') for o in observations if o is not None]
        assert any(order is not None for order in popped)
        (svc, stores) = _make_service()

        svc.restore(being, json.dumps(payload))

        restored = [
            e.observation if isinstance(e, Perception) else e.result
            for e in stores['short_term'].get(being).experiences
            if isinstance(e, Perception) or isinstance(getattr(e, 'result', None), Observation)
        ]
        assert len(restored) == len(popped)
        assert all(o.order is None for o in restored)
