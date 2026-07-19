"""MemoToolExecutor と MemoDistillEvidenceTranscriber の統合を保証する。

U5 (予測誤差統一設計 §2 U5): memo_done 成功時、transcriber が注入されて
いれば MEMO_DISTILL evidence を無条件で積む。転記条件のドメインロジック
自体は ``test_memo_distill_evidence_transcriber.py`` でカバーするため、
本ファイルは「memo_executor がいつ・どう呼ぶか」(配線側の責務) に絞る。
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.llm.services.executors.memo_executor import (
    MemoToolExecutor,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.memo_distill_evidence_transcriber import (
    MemoDistillEvidenceTranscriber,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_DONE,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from tests.application.llm._memo_being_test_helpers import make_memo_being_setup


def _episode(episode_id: str) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=1,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="memo_add"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
    )


def _make_executor_with_transcriber(*, inject_transcriber: bool):
    setup = make_memo_being_setup()
    being_id = setup.provision(1)
    memo_id = setup.memo_store.add_by_being(being_id, "岩礁海岸は山方面に通じず×")

    buffer_store = InMemoryBeliefEvidenceBufferStore()
    episode_store = InMemorySubjectiveEpisodeStore()
    episode_store.put_by_being(being_id, _episode("ep-1"))
    transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)

    executor = MemoToolExecutor(
        setup.memo_store,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
        memo_distill_transcriber=transcriber if inject_transcriber else None,
    )
    return executor, memo_id, buffer_store, being_id


class TestMemoExecutorMemoDistillIntegration:
    def test_memo_done_success_transcriber_memo_distill_evidence(
        self,
    ) -> None:
        """memo done 成功時に transcriber が注入されていれば MEMO DISTILL evidence を積む。"""
        executor, memo_id, buffer_store, being_id = _make_executor_with_transcriber(
            inject_transcriber=True
        )
        handlers = executor.get_handlers()

        result = handlers[TOOL_NAME_MEMO_DONE](1, {"memo_ids": [memo_id]})

        assert result.success
        evidences = buffer_store.list_all_by_being(being_id)
        assert len(evidences) == 1
        assert evidences[0].source_kind == BeliefEvidenceSourceKind.MEMO_DISTILL
        assert "岩礁海岸は山方面に通じず×" in evidences[0].text

    def test_transcriber_uninjected_memo_distill_evidence(self) -> None:
        """flag OFF (= constructor に transcriber を渡さない) のときは
        転記コードパス自体が no-op になる。"""
        executor, memo_id, buffer_store, being_id = _make_executor_with_transcriber(
            inject_transcriber=False
        )
        handlers = executor.get_handlers()

        result = handlers[TOOL_NAME_MEMO_DONE](1, {"memo_ids": [memo_id]})

        assert result.success
        assert buffer_store.list_all_by_being(being_id) == []

    def test_set_memo_distill_transcriber_post_hoc_works(self) -> None:
        """world_runtime.create_world_runtime は executor 構築後に
        belief_evidence_buffer_store を確定させるため、post-hoc setter で
        差し込む経路も同じ挙動になることを保証する。"""
        setup = make_memo_being_setup()
        being_id = setup.provision(1)
        memo_id = setup.memo_store.add_by_being(being_id, "拠点に資源はない")
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        episode_store.put_by_being(being_id, _episode("ep-1"))
        transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)

        executor = MemoToolExecutor(
            setup.memo_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        executor.set_memo_distill_transcriber(transcriber)
        handlers = executor.get_handlers()

        result = handlers[TOOL_NAME_MEMO_DONE](1, {"memo_ids": [memo_id]})

        assert result.success
        assert len(buffer_store.list_all_by_being(being_id)) == 1

    def test_memo(self) -> None:
        """discard 判定は固着パスの LLM に委ねるため、一般化不能に見える
        タスクメモでも memo_executor 側では判定せず積む。"""
        setup = make_memo_being_setup()
        being_id = setup.provision(1)
        memo_id = setup.memo_store.add_by_being(being_id, "扉固定スイッチを押す")
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        episode_store = InMemorySubjectiveEpisodeStore()
        episode_store.put_by_being(being_id, _episode("ep-1"))
        transcriber = MemoDistillEvidenceTranscriber(buffer_store, episode_store)
        executor = MemoToolExecutor(
            setup.memo_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
            memo_distill_transcriber=transcriber,
        )
        handlers = executor.get_handlers()

        result = handlers[TOOL_NAME_MEMO_DONE](1, {"memo_ids": [memo_id]})

        assert result.success
        assert len(buffer_store.list_all_by_being(being_id)) == 1

    def test_memo_done_failure_memo_distill_evidence(self) -> None:
        """memo done 失敗時は MEMO DISTILL evidence を積まない。"""
        executor, _memo_id, buffer_store, being_id = _make_executor_with_transcriber(
            inject_transcriber=True
        )
        handlers = executor.get_handlers()

        result = handlers[TOOL_NAME_MEMO_DONE](1, {"memo_ids": ["non-existent"]})

        assert not result.success
        assert buffer_store.list_all_by_being(being_id) == []

    def test_transcriber_memo_done_raises_exception(self) -> None:
        """転記失敗が memo_done の成功応答を巻き込まない (silent failure より
        「本体は成功、転記だけ諦めて warning ログ」を選ぶ既存方針)。"""
        setup = make_memo_being_setup()
        being_id = setup.provision(1)
        memo_id = setup.memo_store.add_by_being(being_id, "岩礁海岸は山方面に通じず×")

        class _RaisingTranscriber:
            def record_from_memo(self, *args, **kwargs):
                raise RuntimeError("boom")

        executor = MemoToolExecutor(
            setup.memo_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        # isinstance ガードを迂回するテスト専用の直接代入
        # (本番は必ず MemoDistillEvidenceTranscriber を渡す)。
        executor._memo_distill_transcriber = _RaisingTranscriber()
        handlers = executor.get_handlers()

        result = handlers[TOOL_NAME_MEMO_DONE](1, {"memo_ids": [memo_id]})

        assert result.success
