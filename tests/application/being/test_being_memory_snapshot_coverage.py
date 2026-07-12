"""
``BeingMemorySnapshotService`` の payload key 網羅性 fail-fast の単体テスト。

PR-G で Recall Slot / Afterglow / Habituation を snapshot に追加するときに、
「EXPECTED_PAYLOAD_KEYS に追加したのに capture() の dict 生成を忘れた」
「restore() の payload 検証から漏らした」を起動時に検出できることを保証する。
"""

import pytest

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    SnapshotCoverageError,
    _validate_snapshot_payload_coverage,
)


class TestValidateSnapshotPayloadCoverage:
    """``_validate_snapshot_payload_coverage`` が emit/expected の差を検出する挙動。"""

    def test_raises_when_emitted_misses_expected_key(self):
        """expected にあるのに emitted に無いキーがあれば SnapshotCoverageError。"""
        with pytest.raises(SnapshotCoverageError):
            _validate_snapshot_payload_coverage(
                emitted_keys={"memo"},
                expected_keys={"memo", "recall_slot"},
            )

    def test_error_message_lists_missing_keys(self):
        """エラーメッセージに不足キーが含まれ、運用者がどの codec を足せば
        いいか一目で分かる。"""
        with pytest.raises(SnapshotCoverageError) as exc_info:
            _validate_snapshot_payload_coverage(
                emitted_keys={"memo"},
                expected_keys={"memo", "recall_slot", "afterglow"},
            )
        message = str(exc_info.value)
        assert "recall_slot" in message
        assert "afterglow" in message

    def test_passes_when_emitted_covers_expected(self):
        """expected ⊆ emitted なら例外を投げない。"""
        _validate_snapshot_payload_coverage(
            emitted_keys={"memo", "recall_slot"},
            expected_keys={"memo", "recall_slot"},
        )

    def test_allows_extra_emitted_keys(self):
        """emitted が expected の超集合 (= 余分なキーがある) でも許容する。
        schema_version など meta 情報のため。"""
        _validate_snapshot_payload_coverage(
            emitted_keys={"memo", "schema_version"},
            expected_keys={"memo"},
        )

    def test_empty_inputs_are_safe(self):
        """両集合が空でも例外を投げない (= minimal wiring セーフ)。"""
        _validate_snapshot_payload_coverage(
            emitted_keys=set(),
            expected_keys=set(),
        )


def _make_service():
    """既存テストと同じ in-memory store を使って service を作る。"""
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
    from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
        InMemoryEpisodicRecallSuccessStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import (
        InMemoryPendingPredictionStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_goal_journal_store import (
        InMemoryGoalJournalStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
        InMemoryBeliefEvidenceBufferStore,
    )

    return BeingMemorySnapshotService(
        memo_store=InMemoryMemoStore(),
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
        pending_prediction_store=InMemoryPendingPredictionStore(),
        goal_journal_store=InMemoryGoalJournalStore(),
    )


class TestBeingMemorySnapshotServiceCoverage:
    """``BeingMemorySnapshotService`` 本体の網羅性 fail-fast の挙動。

    新 store を追加するときに ``EXPECTED_PAYLOAD_KEYS`` だけ更新して
    ``capture()`` の dict 生成を忘れた状況を再現し、起動時に検出されることを
    保証する。"""

    def test_capture_succeeds_with_default_expected_keys(self):
        """既存 6 store + 既定の EXPECTED_PAYLOAD_KEYS で capture が成功する
        (= 後方互換)。"""
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        service = _make_service()
        payload_json = service.capture(BeingId("being-test"))
        assert "memo" in payload_json

    def test_capture_raises_when_expected_key_is_not_emitted(self, monkeypatch):
        """EXPECTED に key を足したが capture() の生成 dict にその key が
        無い場合、capture() 呼び出し時に SnapshotCoverageError。"""
        from ai_rpg_world.application.being.being_memory_snapshot_service import (
            BeingMemorySnapshotService,
        )
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        # EXPECTED に「capture() が知らない」key を足して、capture() の dict
        # 生成だけ追従し忘れた状況を再現する。
        original = BeingMemorySnapshotService.EXPECTED_PAYLOAD_KEYS
        monkeypatch.setattr(
            BeingMemorySnapshotService,
            "EXPECTED_PAYLOAD_KEYS",
            original | frozenset({"fictional_new_store"}),
        )

        service = _make_service()
        with pytest.raises(SnapshotCoverageError) as exc_info:
            service.capture(BeingId("being-test"))
        assert "fictional_new_store" in str(exc_info.value)

    def test_restore_raises_when_payload_misses_expected_key(self, monkeypatch):
        """EXPECTED に新 key を足した状態で、その key が無い payload を
        渡すと restore() が BeingMemoryPayloadFormatError を投げる
        (= 既存の検証経路に乗っていることを確認)。"""
        import json

        from ai_rpg_world.application.being.being_memory_snapshot_service import (
            BeingMemorySnapshotService,
            BeingMemoryPayloadFormatError,
        )
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        original = BeingMemorySnapshotService.EXPECTED_PAYLOAD_KEYS
        monkeypatch.setattr(
            BeingMemorySnapshotService,
            "EXPECTED_PAYLOAD_KEYS",
            original | frozenset({"fictional_new_store"}),
        )

        service = _make_service()
        payload_without_new_key = {
            "schema_version": 1,
            "memo": [], "semantic_entries": [], "semantic_cluster_signatures": [],
            "memory_links": [], "recall_buffer_pending": [],
            "reinterpretation_journal": [], "episodic_episodes": [],
            # PR-G: 実 store の 4 key は揃えておき、fictional_new_store だけが
            # 欠けている状況を作る (= 「EXPECTED に追加したが restore() の検証が
            # 漏れた」シナリオを最小再現する)。
            "recall_slot_entries": [], "recall_slot_cooldown": [],
            "afterglow_entries": [], "recall_habituation_last_recalled": [],
            # U2: belief_evidence_buffer も実 store の key として揃えておく。
            "belief_evidence_buffer": [],
            # U9b: recall_success_hit_count も実 store の key として揃えておく。
            "recall_success_hit_count": [],
            "pending_predictions": [],
            "goal_journal": [],
        }
        with pytest.raises(BeingMemoryPayloadFormatError) as exc_info:
            service.restore(BeingId("being-test"), json.dumps(payload_without_new_key))
        assert "fictional_new_store" in str(exc_info.value)

    def test_restore_wraps_belief_evidence_domain_exception_as_format_error(self):
        """U2 レビュー MEDIUM 対応: BeliefEvidence VO はドメイン例外
        (BeliefEvidenceValidationException、組み込み例外を継承しない) を
        投げるが、破損 payload (不正 salience) を restore すると生の
        ドメイン例外ではなく BeingMemoryPayloadFormatError に wrap されて
        伝播することを保証する (= _decode_list の except 契約を守る)。"""
        import json

        from ai_rpg_world.application.being.being_memory_snapshot_service import (
            BeingMemoryPayloadFormatError,
        )
        from ai_rpg_world.domain.being.value_object.being_id import BeingId

        service = _make_service()
        # salience は low | high のみ許容。medium は VO 構築で
        # BeliefEvidenceValidationException になる。
        broken_payload = {
            "schema_version": 1,
            "memo": [], "semantic_entries": [], "semantic_cluster_signatures": [],
            "memory_links": [], "recall_buffer_pending": [],
            "reinterpretation_journal": [], "episodic_episodes": [],
            "recall_slot_entries": [], "recall_slot_cooldown": [],
            "afterglow_entries": [], "recall_habituation_last_recalled": [],
            "recall_success_hit_count": [],
            "pending_predictions": [],
            "goal_journal": [],
            "belief_evidence_buffer": [
                {
                    "evidence_id": "e1",
                    "source_kind": "prediction_error",
                    "episode_ids": ["ep-1"],
                    "cue_signature": "tool:explore",
                    "text": "探索は空振りだった",
                    "salience": "medium",  # 不正値
                    "occurred_at": "2026-07-05T09:00:00+00:00",
                    "tick": 7,
                }
            ],
        }
        with pytest.raises(BeingMemoryPayloadFormatError) as exc_info:
            service.restore(BeingId("being-test"), json.dumps(broken_payload))
        assert "belief_evidence_buffer" in str(exc_info.value)


class TestExperimentSnapshotSessionDoesNotSwallowCoverageError:
    """``ExperimentSnapshotSession.capture_all_to_dir`` の ``except Exception`` が
    ``SnapshotCoverageError`` を warning に丸めてしまうと「起動時 fail-fast」の
    目的が果たせない。programming error は呑まずに伝播する挙動を保証する。

    実 Being リポジトリの構築はテストの本筋に不要なので、capture_use_case を
    モックして直接 ``SnapshotCoverageError`` を投げる状況を再現する。"""

    def test_capture_all_reraises_snapshot_coverage_error(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        from ai_rpg_world.application.being.being_memory_snapshot_service import (
            BeingMemorySnapshotService,
        )
        from ai_rpg_world.application.being.being_provisioning_service import (
            BeingProvisioningService,
        )
        from ai_rpg_world.application.being.experiment_snapshot_session import (
            ExperimentSnapshotSession,
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
        from ai_rpg_world.domain.being.service.being_attachment_resolver import (
            BeingAttachmentResolver,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
            InMemoryBeingRepository,
        )

        # EXPECTED に capture() が知らない key を足し、coverage error を強制発火。
        original = BeingMemorySnapshotService.EXPECTED_PAYLOAD_KEYS
        monkeypatch.setattr(
            BeingMemorySnapshotService,
            "EXPECTED_PAYLOAD_KEYS",
            original | frozenset({"fictional_new_store"}),
        )

        repo = InMemoryBeingRepository()
        resolver = BeingAttachmentResolver(repo)
        provisioning = BeingProvisioningService(repo)
        wiring = SimpleNamespace(
            memo_store=InMemoryMemoStore(),
            semantic_memory_store=InMemorySemanticMemoryStore(),
            memory_link_store=InMemoryMemoryLinkStore(),
            episodic_recall_buffer_store=InMemoryEpisodicRecallBufferStore(),
            episodic_reinterpretation_journal_store=InMemoryEpisodicReinterpretationJournalStore(),
            episodic_episode_store=InMemorySubjectiveEpisodeStore(),
            being_repository=repo,
            being_attachment_resolver=resolver,
        )
        provisioning.ensure_attached(PlayerId(1))

        session = ExperimentSnapshotSession(
            wiring_result=wiring, snapshot_dir=tmp_path / "snap"
        )
        with pytest.raises(SnapshotCoverageError):
            session.capture_all([PlayerId(1)])
