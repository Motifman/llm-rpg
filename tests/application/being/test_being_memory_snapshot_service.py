"""BeingMemorySnapshotService の capture / restore 挙動 (Phase 4 Step 4-2b)。

5 memory store の状態を Being 単位で JSON 1 本に save / restore できることを
担保する。in-memory store を使った round-trip テストが中心。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemoryPayloadFormatError,
    BeingMemoryPayloadSchemaError,
    BeingMemorySnapshotService,
    CURRENT_PAYLOAD_SCHEMA_VERSION,
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
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import (
    EpisodeAction,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import (
    EpisodeLocation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import (
    EpisodeSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import (
    EpisodicReinterpretationStatus,
)
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)


_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _make_service() -> tuple[BeingMemorySnapshotService, dict[str, object]]:
    """新しい in-memory store 群を構築し、service と store ハンドルを返す。"""
    from ai_rpg_world.application.llm.services.afterglow_store import (
        InMemoryAfterglowStore,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
        InMemoryEpisodicRecallHabituationStore,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
        InMemoryEpisodicRecallSlotStore,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
        InMemoryEpisodicRecallSuccessStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
        InMemoryBeliefEvidenceBufferStore,
    )

    memo = InMemoryMemoStore()
    semantic = InMemorySemanticMemoryStore()
    link = InMemoryMemoryLinkStore()
    recall = InMemoryEpisodicRecallBufferStore()
    journal = InMemoryEpisodicReinterpretationJournalStore()
    episode = InMemorySubjectiveEpisodeStore()
    slot = InMemoryEpisodicRecallSlotStore()
    afterglow = InMemoryAfterglowStore()
    habituation = InMemoryEpisodicRecallHabituationStore()
    belief_evidence = InMemoryBeliefEvidenceBufferStore()
    success = InMemoryEpisodicRecallSuccessStore()
    svc = BeingMemorySnapshotService(
        memo_store=memo,
        semantic_store=semantic,
        memory_link_store=link,
        recall_buffer_store=recall,
        reinterpretation_journal_store=journal,
        episodic_episode_store=episode,
        recall_slot_store=slot,
        afterglow_store=afterglow,
        recall_habituation_store=habituation,
        belief_evidence_buffer_store=belief_evidence,
        recall_success_store=success,
    )
    return svc, {
        "memo": memo,
        "semantic": semantic,
        "link": link,
        "recall": recall,
        "journal": journal,
        "episode": episode,
        "belief_evidence": belief_evidence,
        "success": success,
    }


def _populate(stores: dict[str, object], being_id: BeingId) -> None:
    """5 store に最小サンプルデータを書き込む。"""
    stores["memo"].add_by_being(being_id, "未完了 memo", current_tick=10)
    completed_id = stores["memo"].add_by_being(being_id, "完了 memo", current_tick=11)
    stores["memo"].complete_by_being(being_id, completed_id)

    stores["semantic"].add_by_being(
        being_id,
        SemanticMemoryEntry(
            entry_id="se-1",
            player_id=1,
            text="一般化要約",
            evidence_episode_ids=("ep-1",),
            confidence=0.8,
            created_at=_NOW,
            importance_score=7,
            tags=("tag-a",),
        ),
    )
    stores["semantic"].register_cluster_signature_if_new_by_being(being_id, "sig-1")

    stores["link"].upsert_link_by_being(
        being_id,
        MemoryLink(
            link_id="mlk-1",
            player_id=1,
            episode_id_a="ep-1",
            episode_id_b="ep-2",
            link_type=MemoryLinkType.CO_RECALL,
            strength=0.9,
            co_activation_count=1,
            created_at=_NOW,
            last_activated_at=_NOW,
            decay_rate=0.001,
        ),
    )

    stores["recall"].append_by_being(
        being_id,
        EpisodicRecallObservation(
            recall_id="r-1",
            player_id=1,
            episode_id="ep-1",
            recalled_at=_NOW,
            source_axes=("temporal",),
            current_state_snapshot="state",
            recent_events_snapshot="events",
            persona_snapshot="persona",
            situation_cues=("cue-a",),
            turn_index=1,
            # U9a: 誤差駆動再解釈用フィールドも round trip 対象に含める
            # (snapshot 追従 checklist #27)。
            prediction_context_id="pc-1",
            prediction_outcome_error="外れた: 実際は雨だった",
        ),
    )

    stores["journal"].put_active_by_being(
        being_id,
        EpisodicReinterpretationEntry(
            entry_id="je-1",
            player_id=1,
            episode_id="ep-1",
            created_at=_NOW,
            turn_index=1,
            current_interpretation="interp",
            current_recall_text="recall text",
            source_recall_ids=("r-1",),
            status=EpisodicReinterpretationStatus.ACTIVE,
        ),
    )

    stores["episode"].put_by_being(
        being_id,
        SubjectiveEpisode(
            episode_id="ep-1",
            player_id=1,
            occurred_at=_NOW,
            game_time_label="12:00",
            source=EpisodeSource(event_ids=("e1",)),
            location=EpisodeLocation(spot_id=42, tile_area_ids=(1, 2)),
            action=EpisodeAction(tool_name="walk"),
            who=("ada",),
            what="what",
            why="why",
            observed="observed",
            expected="expected",
            outcome="ok",
            prediction_error=None,
            felt="felt",
            interpreted="interpreted",
            cues=(
                EpisodicCue(
                    axis="place_spot",
                    value="42",
                    source=EpisodicCueSource.RUNTIME_CONTEXT,
                ),
            ),
            recall_text="recall",
            recall_count=0,
            last_recalled_at=None,
        ),
    )


class TestCapture:
    """capture の挙動。"""

    def test_空store_からも_有効な_payload_を返す(self) -> None:
        """全 store が空でも payload は schema_version と全 key を持つ。"""
        svc, _ = _make_service()
        being = BeingId("ada")
        payload = json.loads(svc.capture(being))
        assert payload["schema_version"] == CURRENT_PAYLOAD_SCHEMA_VERSION
        for k in (
            "memo",
            "semantic_entries",
            "semantic_cluster_signatures",
            "memory_links",
            "recall_buffer_pending",
            "reinterpretation_journal",
            "episodic_episodes",
        ):
            assert payload[k] == []

    def test_5_store_の状態を全て載せる(self) -> None:
        svc, stores = _make_service()
        being = BeingId("ada")
        _populate(stores, being)
        payload = json.loads(svc.capture(being))
        assert len(payload["memo"]) == 2  # 未完了 + 完了
        assert len(payload["semantic_entries"]) == 1
        assert payload["semantic_cluster_signatures"] == ["sig-1"]
        assert len(payload["memory_links"]) == 1
        assert len(payload["recall_buffer_pending"]) == 1
        assert len(payload["reinterpretation_journal"]) == 1
        assert len(payload["episodic_episodes"]) == 1

    def test_being_id_型違反は_TypeError(self) -> None:
        svc, _ = _make_service()
        with pytest.raises(TypeError):
            svc.capture("ada")  # type: ignore[arg-type]


class TestRestoreRoundTrip:
    """capture → restore で 5 store の状態が完全一致する。"""

    def test_full_round_trip(self) -> None:
        # 元 service にデータを詰める。
        src_svc, src_stores = _make_service()
        being = BeingId("ada")
        _populate(src_stores, being)
        payload_json = src_svc.capture(being)

        # まっさらな別 service に restore して比較。
        dst_svc, dst_stores = _make_service()
        dst_svc.restore(being, payload_json)

        # capture 結果同士が等しければ、状態は一致している。
        assert json.loads(payload_json) == json.loads(dst_svc.capture(being))

    def test_restore_は_既存データを上書きする(self) -> None:
        """restore 先に古い state が入っていても、payload で完全置換される。"""
        src_svc, src_stores = _make_service()
        being = BeingId("ada")
        _populate(src_stores, being)
        payload_json = src_svc.capture(being)

        dst_svc, dst_stores = _make_service()
        # 別 memo を先に詰めておく → restore で消えるはず。
        dst_stores["memo"].add_by_being(being, "古い memo")
        dst_svc.restore(being, payload_json)

        # 復元後 memo は src 由来 2 件のみ。
        memos = dst_stores["memo"].list_all_by_being(being)
        contents = sorted(e.content for e in memos)
        assert contents == ["完了 memo", "未完了 memo"]

    def test_belief_evidence_buffer_の_round_trip(self) -> None:
        """U2 (証拠台帳統一設計): evidence buffer の capture → restore で
        中身が一致することを保証する (snapshot 追従 checklist #27)。"""
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
            BELIEF_EVIDENCE_SALIENCE_LOW,
            BeliefEvidence,
        )
        from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
            BeliefEvidenceSourceKind,
        )

        src_svc, src_stores = _make_service()
        being = BeingId("ada")
        evidence = BeliefEvidence(
            evidence_id="belief-evidence-1",
            source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
            episode_ids=("ep-1",),
            cue_signature="tool:explore|spot:3",
            text="探索は空振りだった",
            salience=BELIEF_EVIDENCE_SALIENCE_LOW,
            occurred_at=_NOW,
            tick=7,
        )
        src_stores["belief_evidence"].append_by_being(being, evidence)
        payload_json = src_svc.capture(being)

        dst_svc, dst_stores = _make_service()
        dst_svc.restore(being, payload_json)

        restored = dst_stores["belief_evidence"].list_all_by_being(being)
        assert len(restored) == 1
        assert restored[0] == evidence

    def test_recall_success_hit_count_の_round_trip(self) -> None:
        """U9b (予測誤差統一設計 部品5・想起の信用割り当て): 的中側 sidecar の

        capture → restore で中身が一致することを保証する
        (snapshot 追従 checklist #27)。"""
        src_svc, src_stores = _make_service()
        being = BeingId("ada")
        src_stores["success"].record_hit_by_being(being, "ep-1")
        src_stores["success"].record_hit_by_being(being, "ep-1")
        src_stores["success"].record_hit_by_being(being, "ep-2")
        payload_json = src_svc.capture(being)

        dst_svc, dst_stores = _make_service()
        dst_svc.restore(being, payload_json)

        restored = dst_stores["success"].list_all_by_being(being)
        assert restored == {"ep-1": 2, "ep-2": 1}

    def test_belief_evidence_の_in_context_belief_ids_も_round_trip_する(self) -> None:
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

        src_svc, src_stores = _make_service()
        being = BeingId("ada")
        evidence = BeliefEvidence(
            evidence_id="belief-evidence-attr-1",
            source_kind=BeliefEvidenceSourceKind.CONFIRMATION,
            episode_ids=("ep-1",),
            cue_signature="tool:explore|spot:3",
            text="予測が当たった: 何か見つかるはず",
            salience=BELIEF_EVIDENCE_SALIENCE_LOW,
            occurred_at=_NOW,
            tick=7,
            in_context_belief_ids=("sem-belief-1", "sem-belief-2"),
        )
        src_stores["belief_evidence"].append_by_being(being, evidence)
        payload_json = src_svc.capture(being)

        dst_svc, dst_stores = _make_service()
        dst_svc.restore(being, payload_json)

        restored = dst_stores["belief_evidence"].list_all_by_being(being)
        assert len(restored) == 1
        assert restored[0].in_context_belief_ids == ("sem-belief-1", "sem-belief-2")

    def test_belief_evidence_の_in_context_belief_ids_欠損の旧データは空タプルに倒れる(
        self,
    ) -> None:
        """U4 導入前 (キー自体が無い) payload を decode しても例外にならず
        空タプルになる (旧データとの後方互換)。"""
        from ai_rpg_world.application.being._memory_payload_codecs import (
            dict_to_belief_evidence,
        )

        data = {
            "evidence_id": "belief-evidence-legacy-1",
            "source_kind": "prediction_error",
            "episode_ids": ["ep-1"],
            "cue_signature": "tool:explore",
            "text": "何もなかった",
            "salience": "low",
            "occurred_at": _NOW.isoformat(),
            "tick": 3,
            # in_context_belief_ids キー自体を欠落させる
        }

        evidence = dict_to_belief_evidence(data)

        assert evidence.in_context_belief_ids == ()

    def test_recall_observation_の_prediction_outcome_error_欠損の旧データは_None_に倒れる(
        self,
    ) -> None:
        """U9a 導入前 (キー自体が無い) payload を decode しても例外にならず
        None になる (旧データとの後方互換)。"""
        from ai_rpg_world.application.being._memory_payload_codecs import (
            dict_to_recall_observation,
        )

        data = {
            "recall_id": "r-legacy-1",
            "player_id": 1,
            "episode_id": "ep-1",
            "recalled_at": _NOW.isoformat(),
            "source_axes": ["temporal"],
            "current_state_snapshot": "state",
            "recent_events_snapshot": "events",
            "persona_snapshot": "persona",
            "situation_cues": ["cue-a"],
            "turn_index": 1,
            # prediction_context_id / prediction_outcome_error キー自体を欠落させる
        }

        obs = dict_to_recall_observation(data)

        assert obs.prediction_context_id is None
        assert obs.prediction_outcome_error is None

    def test_他_being_は影響しない(self) -> None:
        src_svc, src_stores = _make_service()
        ada = BeingId("ada")
        ben = BeingId("ben")
        _populate(src_stores, ada)
        # ben にも独自データを入れる。
        src_stores["memo"].add_by_being(ben, "ben の memo")
        payload_ada = src_svc.capture(ada)

        dst_svc, dst_stores = _make_service()
        dst_stores["memo"].add_by_being(ben, "ben 固有")
        dst_svc.restore(ada, payload_ada)
        # ben の memo は変わらない。
        ben_memos = [e.content for e in dst_stores["memo"].list_all_by_being(ben)]
        assert ben_memos == ["ben 固有"]


class TestRestoreValidation:
    """restore の payload 検査挙動。"""

    def test_非_str_payload_は_TypeError(self) -> None:
        svc, _ = _make_service()
        with pytest.raises(TypeError):
            svc.restore(BeingId("ada"), {})  # type: ignore[arg-type]

    def test_不正_json_は_FormatError(self) -> None:
        svc, _ = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match="not valid JSON"):
            svc.restore(BeingId("ada"), "not json")

    def test_root_が_object_でないと_FormatError(self) -> None:
        svc, _ = _make_service()
        with pytest.raises(BeingMemoryPayloadFormatError, match="object"):
            svc.restore(BeingId("ada"), "[]")

    def test_未サポート_schema_version_は_SchemaError(self) -> None:
        svc, _ = _make_service()
        bad = json.dumps({"schema_version": 999, "memo": []})
        with pytest.raises(BeingMemoryPayloadSchemaError, match="999"):
            svc.restore(BeingId("ada"), bad)

    def test_required_key_欠落は_FormatError(self) -> None:
        svc, _ = _make_service()
        # memo だけ持つ payload。
        bad = json.dumps(
            {"schema_version": CURRENT_PAYLOAD_SCHEMA_VERSION, "memo": []}
        )
        with pytest.raises(BeingMemoryPayloadFormatError, match="missing required key"):
            svc.restore(BeingId("ada"), bad)

    def test_memo_要素の_id_欠落は_FormatError(self) -> None:
        """list 要素内の dict key 欠落は KeyError ではなく FormatError に wrap される。"""
        svc, _ = _make_service()
        bad = json.dumps(
            {
                "schema_version": CURRENT_PAYLOAD_SCHEMA_VERSION,
                "memo": [{"content": "no id"}],  # id / added_at / completed 欠落
                "semantic_entries": [],
                "semantic_cluster_signatures": [],
                "memory_links": [],
                "recall_buffer_pending": [],
                "reinterpretation_journal": [],
                "episodic_episodes": [],
                "recall_slot_entries": [],
                "recall_slot_cooldown": [],
                "afterglow_entries": [],
                "recall_habituation_last_recalled": [],
                # U2: belief_evidence_buffer も実 store の key として揃えておく。
                "belief_evidence_buffer": [],
                # U9b: recall_success_hit_count も実 store の key として揃えておく。
                "recall_success_hit_count": [],
            }
        )
        with pytest.raises(BeingMemoryPayloadFormatError, match="memo"):
            svc.restore(BeingId("ada"), bad)

    def test_unknown_enum_値は_FormatError(self) -> None:
        """memory_link の link_type が未知値なら FormatError。"""
        svc, _ = _make_service()
        bad = json.dumps(
            {
                "schema_version": CURRENT_PAYLOAD_SCHEMA_VERSION,
                "memo": [],
                "semantic_entries": [],
                "semantic_cluster_signatures": [],
                "memory_links": [
                    {
                        "link_id": "x",
                        "player_id": 1,
                        "episode_id_a": "a",
                        "episode_id_b": "b",
                        "link_type": "UNKNOWN_TYPE",
                        "strength": 0.5,
                        "co_activation_count": 1,
                        "created_at": "2026-06-14T12:00:00+00:00",
                        "last_activated_at": "2026-06-14T12:00:00+00:00",
                        "decay_rate": 0.001,
                    }
                ],
                "recall_buffer_pending": [],
                "reinterpretation_journal": [],
                "episodic_episodes": [],
                "recall_slot_entries": [],
                "recall_slot_cooldown": [],
                "afterglow_entries": [],
                "recall_habituation_last_recalled": [],
                # U2: belief_evidence_buffer も実 store の key として揃えておく。
                "belief_evidence_buffer": [],
                # U9b: recall_success_hit_count も実 store の key として揃えておく。
                "recall_success_hit_count": [],
            }
        )
        with pytest.raises(BeingMemoryPayloadFormatError, match="memory_links"):
            svc.restore(BeingId("ada"), bad)

    def test_required_key_の値が_list_でないと_FormatError(self) -> None:
        svc, _ = _make_service()
        bad = json.dumps(
            {
                "schema_version": CURRENT_PAYLOAD_SCHEMA_VERSION,
                "memo": "not-list",
                "semantic_entries": [],
                "semantic_cluster_signatures": [],
                "memory_links": [],
                "recall_buffer_pending": [],
                "reinterpretation_journal": [],
                "episodic_episodes": [],
                # PR-G で追加した key 群も list で渡す (= 「memo が list でない」
                # 検証の手前で fail-fast に化けないよう揃える)。
                "recall_slot_entries": [],
                "recall_slot_cooldown": [],
                "afterglow_entries": [],
                "recall_habituation_last_recalled": [],
                # U2: belief_evidence_buffer も実 store の key として揃えておく。
                "belief_evidence_buffer": [],
                # U9b: recall_success_hit_count も実 store の key として揃えておく。
                "recall_success_hit_count": [],
            }
        )
        with pytest.raises(BeingMemoryPayloadFormatError, match="must be list"):
            svc.restore(BeingId("ada"), bad)


class TestConstructor:
    """constructor の型ガード。"""

    def test_memo_store_型違反(self) -> None:
        from ai_rpg_world.application.llm.services.afterglow_store import (
            InMemoryAfterglowStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
            InMemoryEpisodicRecallHabituationStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
            InMemoryEpisodicRecallSlotStore,
        )
        from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
            InMemoryEpisodicRecallSuccessStore,
        )

        from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
            InMemoryBeliefEvidenceBufferStore,
        )

        with pytest.raises(TypeError, match="memo_store"):
            BeingMemorySnapshotService(
                memo_store="bad",  # type: ignore[arg-type]
                semantic_store=InMemorySemanticMemoryStore(),
                memory_link_store=InMemoryMemoryLinkStore(),
                recall_buffer_store=InMemoryEpisodicRecallBufferStore(),
                reinterpretation_journal_store=InMemoryEpisodicReinterpretationJournalStore(),
                episodic_episode_store=InMemorySubjectiveEpisodeStore(),
                recall_slot_store=InMemoryEpisodicRecallSlotStore(),
                afterglow_store=InMemoryAfterglowStore(),
                recall_habituation_store=InMemoryEpisodicRecallHabituationStore(),
                belief_evidence_buffer_store=InMemoryBeliefEvidenceBufferStore(),
                recall_success_store=InMemoryEpisodicRecallSuccessStore(),
            )
