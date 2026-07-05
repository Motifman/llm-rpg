"""想起後再解釈 buffer / journal / coordinator の検証。"""

from __future__ import annotations

# Phase 3 Step 3e-3 bulk migration: episode_store の player_id 経路撤去に
# 伴い、本ファイルの ``being_id`` 参照を deterministic な ``BeingId`` の
# 既定値で受ける (= テスト内で異なる player_id を使う箇所は個別に上書き)。
# BeingProvisioningService は ``being_w<world>_p<player>`` 形式を使う。
from ai_rpg_world.domain.being.value_object.being_id import (
    BeingId as _MIG_BeingId,
)

being_id = _MIG_BeingId("being_w1_p1")

from datetime import datetime, timedelta, timezone
from typing import Any

from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.application.llm.ports.episodic_reinterpretation_completion_port import (
    IEpisodicReinterpretationCompletionPort,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import EpisodicRecallObservation
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import EpisodicReinterpretationEntry
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import EpisodicRecallBufferRepository
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.episodic_reinterpretation_coordinator import (
    EpisodicReinterpretationCoordinator,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
    InMemoryEpisodicRecallBufferStore,
    InMemoryEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _FakeReinterpretationPort(IEpisodicReinterpretationCompletionPort):
    def __init__(self, outcome: dict[str, Any] | BaseException) -> None:
        self.outcome = outcome
        self.calls: list[list[dict[str, Any]]] = []

    def complete_episodic_reinterpretation_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(messages)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _BrokenRecallBufferStore(EpisodicRecallBufferRepository):
    """sidecar 失敗の伝播テスト用 stub (Phase 3 Step 3d-3 で by_being のみ残す)。"""

    def append_by_being(
        self, being_id: BeingId, observation: EpisodicRecallObservation
    ) -> None:
        """常に RuntimeError。"""
        raise RuntimeError("broken")

    def peek_batch_by_being(
        self,
        being_id: BeingId,
        *,
        batch_size: int,
        max_contexts_per_episode: int,
    ) -> tuple[EpisodicRecallObservation, ...]:
        """常に RuntimeError。"""
        raise RuntimeError("broken")

    def mark_processed_by_being(
        self, being_id: BeingId, recall_ids: tuple[str, ...]
    ) -> None:
        """常に RuntimeError。"""
        raise RuntimeError("broken")

    def pending_count_by_being(self, being_id: BeingId) -> int:
        """常に RuntimeError。"""
        raise RuntimeError("broken")

    def list_pending_by_being(
        self, being_id: BeingId
    ) -> list[EpisodicRecallObservation]:
        """常に RuntimeError。"""
        raise RuntimeError("broken")

    def replace_all_pending_by_being(
        self,
        being_id: BeingId,
        observations: list[EpisodicRecallObservation],
    ) -> None:
        """常に RuntimeError。"""
        raise RuntimeError("broken")

    def stamp_prediction_outcome_by_being(
        self,
        being_id: BeingId,
        prediction_context_id: str,
        prediction_error: str,
    ) -> None:
        """常に RuntimeError。"""
        raise RuntimeError("broken")


def _episode(
    *,
    episode_id: str,
    player_id: int = 7,
    recall_text: str = "初期の一人称回想。",
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=datetime(2026, 5, 4, 1, 0, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-a",)),
        location=EpisodeLocation(spot_id=10),
        action=EpisodeAction(tool_name="world_no_op"),
        who=("player:self",),
        what="古い扉を調べた",
        why=None,
        observed="古い扉は固く閉ざされていた。",
        expected=None,
        outcome="未解決",
        prediction_error=None,
        felt="caution",
        interpreted="閉ざされた場所だと思った。",
        cues=(
            EpisodicCue(
                axis="place_spot",
                value="10",
                source=EpisodicCueSource.RUNTIME_CONTEXT,
            ),
        ),
        recall_text=recall_text,
    )


def _recall(
    *,
    recall_id: str,
    episode_id: str,
    at: datetime,
    turn_index: int,
    player_id: int = 7,
    prediction_context_id: str | None = None,
    prediction_outcome_error: str | None = None,
) -> EpisodicRecallObservation:
    return EpisodicRecallObservation(
        recall_id=recall_id,
        player_id=player_id,
        episode_id=episode_id,
        recalled_at=at,
        source_axes=("temporal",),
        current_state_snapshot="現在地: 古い廊下",
        recent_events_snapshot="扉の前で立ち止まった。",
        persona_snapshot="一人称: 私",
        situation_cues=("place_spot:10",),
        turn_index=turn_index,
        prediction_context_id=prediction_context_id,
        prediction_outcome_error=prediction_outcome_error,
    )


_BEING_7 = BeingId("being_w1_p7")


class TestInMemoryEpisodicRecallBufferStore:
    """想起 observation を episode 単位で束ねる。"""

    def test_peek_batch_deduplicates_episode_and_caps_contexts(self) -> None:
        """同じ episode の想起は 1 episode として数え、contexts は上限で切る。"""
        base = datetime(2026, 5, 4, tzinfo=timezone.utc)
        store = InMemoryEpisodicRecallBufferStore()
        for i in range(5):
            store.append_by_being(
                _BEING_7,
                _recall(
                    recall_id=f"r{i}",
                    episode_id="ep-a",
                    at=base + timedelta(minutes=i),
                    turn_index=i,
                ),
            )
        store.append_by_being(
            _BEING_7,
            _recall(
                recall_id="r-b",
                episode_id="ep-b",
                at=base + timedelta(minutes=10),
                turn_index=10,
            ),
        )
        batch = store.peek_batch_by_being(
            _BEING_7, batch_size=1, max_contexts_per_episode=3
        )
        assert [r.recall_id for r in batch] == ["r0", "r1", "r2"]
        assert store.pending_count_by_being(_BEING_7) == 6


class TestInMemoryEpisodicReinterpretationJournalStore:
    """active entry だけが通常参照に残る。"""

    def test_put_active_supersedes_previous_active_entry(self) -> None:
        """新 active 保存時に旧 active は superseded となり get_active から外れる。"""
        store = InMemoryEpisodicReinterpretationJournalStore()
        t0 = datetime(2026, 5, 4, tzinfo=timezone.utc)
        first = EpisodicReinterpretationEntry(
            entry_id="j1",
            player_id=7,
            episode_id="ep-a",
            created_at=t0,
            turn_index=1,
            current_interpretation="古い意味。",
            current_recall_text="古い回想。",
            source_recall_ids=("r1",),
        )
        second = EpisodicReinterpretationEntry(
            entry_id="j2",
            player_id=7,
            episode_id="ep-a",
            created_at=t0 + timedelta(minutes=1),
            turn_index=2,
            current_interpretation="新しい意味。",
            current_recall_text="新しい回想。",
            source_recall_ids=("r2",),
        )
        store.put_active_by_being(_BEING_7, first)
        store.put_active_by_being(_BEING_7, second)
        assert store.get_active_by_being(_BEING_7, "ep-a") == second
        history = store.list_by_episode_by_being(_BEING_7, "ep-a")
        assert [e.entry_id for e in history] == ["j2", "j1"]
        assert history[1].status.value == "superseded"


class TestEpisodicReinterpretationCoordinator:
    """10 ターンごとの flush と失敗時 pending 維持。

    Phase 3 Step 3d-3: legacy player_id 経路撤去後、Coordinator は
    Resolver+WorldId が必須となった (= 未注入なら silent no-op)。
    各テストで provision 済 BeingId を準備した上で、Coordinator にも
    Resolver+WorldId を渡す。
    """

    def _stores(self):
        from tests.application.llm._reinterpretation_being_test_helpers import (
            make_reinterpretation_being_setup,
        )

        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_reinterpretation_being_setup()
        being_id = setup.provision(7)
        # Phase 3 Step 3e-2: Coordinator が being_id 経由で episode を引くため、
        # episode も being_id 経路で書く必要がある
        episodes.put_by_being(being_id, _episode(episode_id="ep-a"))
        episodes.put_by_being(being_id, _episode(episode_id="ep-b"))
        return episodes, setup, being_id

    def test_after_turn_completed_flushes_only_on_tenth_turn(self) -> None:
        """9 ターン目までは LLM を呼ばず、10 ターン目で active entry を保存する。"""
        episodes, setup, being_id = self._stores()
        buffer = setup.recall_buffer
        journal = setup.journal
        buffer.append_by_being(
            being_id,
            _recall(
                recall_id="r1",
                episode_id="ep-a",
                at=datetime(2026, 5, 4, tzinfo=timezone.utc),
                turn_index=0,
            ),
        )
        port = _FakeReinterpretationPort(
            {
                "episode_updates": [
                    {
                        "episode_id": "ep-a",
                        "current_interpretation": "今なら、この扉は単なる障害ではなく合図に見える。",
                        "current_recall_text": "私はあの古い扉の前で、ただ立ち止まっていたわけではない。冷たい取っ手に触れたとき、閉ざされた先に何かが待つ気配を感じ、慎重になった。今思えば、その重さは道を拒む壁ではなく、私に準備を促す合図だったのだと思う。",
                    }
                ]
            }
        )
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=buffer,
            journal_store=journal,
            completion=port,
            turn_interval=10,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        for _ in range(9):
            coord.after_turn_completed(PlayerId(7))
        assert port.calls == []
        assert journal.get_active_by_being(being_id, "ep-a") is None
        coord.after_turn_completed(PlayerId(7))
        assert len(port.calls) == 1
        active = journal.get_active_by_being(being_id, "ep-a")
        assert active is not None
        assert "合図" in active.current_interpretation
        assert buffer.pending_count_by_being(being_id) == 0

    def test_llm_failure_keeps_pending_recall_and_existing_active(self) -> None:
        """LLM 失敗時は pending を消さず、既存 active entry も保持する。"""
        episodes, setup, being_id = self._stores()
        buffer = setup.recall_buffer
        journal = setup.journal
        t0 = datetime(2026, 5, 4, tzinfo=timezone.utc)
        buffer.append_by_being(
            being_id, _recall(recall_id="r1", episode_id="ep-a", at=t0, turn_index=0)
        )
        old = EpisodicReinterpretationEntry(
            entry_id="old",
            player_id=7,
            episode_id="ep-a",
            created_at=t0,
            turn_index=0,
            current_interpretation="既存の意味。",
            current_recall_text="既存の回想。",
            source_recall_ids=("r0",),
        )
        journal.put_active_by_being(being_id, old)
        port = _FakeReinterpretationPort(
            LlmApiCallException("down", error_code="LLM_API_CALL_FAILED")
        )
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=buffer,
            journal_store=journal,
            completion=port,
            turn_interval=1,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        coord.after_turn_completed(PlayerId(7))
        assert buffer.pending_count_by_being(being_id) == 1
        assert journal.get_active_by_being(being_id, "ep-a") == old

    def test_invalid_llm_json_keeps_pending_recall(self) -> None:
        """JSON shape 不正や必須 field 欠落では pending を消さず retry 可能にする。"""
        episodes, setup, being_id = self._stores()
        buffer = setup.recall_buffer
        journal = setup.journal
        t0 = datetime(2026, 5, 4, tzinfo=timezone.utc)
        buffer.append_by_being(
            being_id, _recall(recall_id="r1", episode_id="ep-a", at=t0, turn_index=0)
        )
        port = _FakeReinterpretationPort({"episode_updates": []})
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=buffer,
            journal_store=journal,
            completion=port,
            turn_interval=1,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        assert coord.flush_player(PlayerId(7)) == 0
        assert buffer.pending_count_by_being(being_id) == 1
        assert journal.get_active_by_being(being_id, "ep-a") is None

    def test_partial_llm_updates_mark_only_successful_episode_recalls_processed(self) -> None:
        """batch の一部だけ成功したら、成功 episode の recall_id だけ pending から除く。"""
        episodes, setup, being_id = self._stores()
        buffer = setup.recall_buffer
        journal = setup.journal
        t0 = datetime(2026, 5, 4, tzinfo=timezone.utc)
        buffer.append_by_being(
            being_id, _recall(recall_id="r-a", episode_id="ep-a", at=t0, turn_index=0)
        )
        buffer.append_by_being(
            being_id,
            _recall(
                recall_id="r-b",
                episode_id="ep-b",
                at=t0 + timedelta(minutes=1),
                turn_index=1,
            ),
        )
        port = _FakeReinterpretationPort(
            {
                "episode_updates": [
                    {
                        "episode_id": "ep-a",
                        "current_interpretation": "ep-a だけ成功。",
                        "current_recall_text": "私は ep-a の出来事だけを、今の文脈から改めて思い返した。",
                    }
                ]
            }
        )
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=buffer,
            journal_store=journal,
            completion=port,
            turn_interval=1,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        assert coord.flush_player(PlayerId(7)) == 1
        assert journal.get_active_by_being(being_id, "ep-a") is not None
        pending = buffer.peek_batch_by_being(
            being_id, batch_size=8, max_contexts_per_episode=3
        )
        assert [row.recall_id for row in pending] == ["r-b"]

    def test_after_turn_completed_does_not_propagate_sidecar_store_failure(self) -> None:
        """再解釈 sidecar の store 例外は本体ターンへ伝播させない。"""
        from tests.application.llm._reinterpretation_being_test_helpers import (
            make_reinterpretation_being_setup,
        )

        episodes = InMemorySubjectiveEpisodeStore()
        episodes.put_by_being(being_id, _episode(episode_id="ep-a"))
        setup = make_reinterpretation_being_setup()
        # _BrokenRecallBufferStore で peek_batch_by_being が即 raise する経路
        # を踏ませるため、Being の provision は必要 (= Resolver が being_id を
        # 引けないと sidecar 実行が始まらず、本テストの意図が崩れる)。
        setup.provision(7)
        port = _FakeReinterpretationPort({"episode_updates": []})
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=_BrokenRecallBufferStore(),
            journal_store=setup.journal,
            completion=port,
            turn_interval=1,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        coord.after_turn_completed(PlayerId(7))


class TestEpisodicReinterpretationCoordinatorErrorDrivenFraming:
    """U9a (予測誤差統一設計 部品5・誤差駆動再解釈): flag 連動の system prompt /
    recall_context payload の切り替え。

    LLM は呼ばず (``_FakeReinterpretationPort`` が固定 JSON を返すだけ)、
    ``flush_player`` が組み立てる messages の中身を検査する質感テスト。
    """

    def _stores(self):
        from tests.application.llm._reinterpretation_being_test_helpers import (
            make_reinterpretation_being_setup,
        )

        episodes = InMemorySubjectiveEpisodeStore()
        setup = make_reinterpretation_being_setup()
        being_id = setup.provision(7)
        episodes.put_by_being(being_id, _episode(episode_id="ep-a"))
        return episodes, setup, being_id

    def test_flag_ON_で誤差付き_recall_は_prediction_outcome_error_を含む(
        self,
    ) -> None:
        episodes, setup, being_id = self._stores()
        buffer = setup.recall_buffer
        buffer.append_by_being(
            being_id,
            _recall(
                recall_id="r1",
                episode_id="ep-a",
                at=datetime(2026, 5, 4, tzinfo=timezone.utc),
                turn_index=0,
                prediction_context_id="pc-1",
                prediction_outcome_error="実際には扉は開いていた",
            ),
        )
        port = _FakeReinterpretationPort({"episode_updates": []})
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=buffer,
            journal_store=setup.journal,
            completion=port,
            turn_interval=1,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
            error_driven_reinterpretation_enabled=True,
        )
        coord.flush_player(PlayerId(7))

        assert len(port.calls) == 1
        messages = port.calls[0]
        system_content = messages[0]["content"]
        assert "誤差駆動の再解釈" in system_content
        user_content = messages[1]["content"]
        assert "実際には扉は開いていた" in user_content
        assert '"prediction_outcome_error"' in user_content

    def test_flag_ON_でも誤差の無い_recall_には_キーが付かない(self) -> None:
        episodes, setup, being_id = self._stores()
        buffer = setup.recall_buffer
        buffer.append_by_being(
            being_id,
            _recall(
                recall_id="r1",
                episode_id="ep-a",
                at=datetime(2026, 5, 4, tzinfo=timezone.utc),
                turn_index=0,
            ),
        )
        port = _FakeReinterpretationPort({"episode_updates": []})
        coord = EpisodicReinterpretationCoordinator(
            episode_store=episodes,
            recall_buffer_store=buffer,
            journal_store=setup.journal,
            completion=port,
            turn_interval=1,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
            error_driven_reinterpretation_enabled=True,
        )
        coord.flush_player(PlayerId(7))

        user_content = port.calls[0][1]["content"]
        assert '"prediction_outcome_error"' not in user_content

    def test_flag_OFF_既定なら誤差があっても_system_prompt_と_payload_が導入前と_byte一致(
        self,
    ) -> None:
        """flag OFF (既定) は U9a 導入前と完全に一致する。"""
        episodes_off, setup_off, being_id_off = self._stores()
        buffer_off = setup_off.recall_buffer
        buffer_off.append_by_being(
            being_id_off,
            _recall(
                recall_id="r1",
                episode_id="ep-a",
                at=datetime(2026, 5, 4, tzinfo=timezone.utc),
                turn_index=0,
                prediction_context_id="pc-1",
                prediction_outcome_error="実際には扉は開いていた",
            ),
        )
        port_off = _FakeReinterpretationPort({"episode_updates": []})
        coord_off = EpisodicReinterpretationCoordinator(
            episode_store=episodes_off,
            recall_buffer_store=buffer_off,
            journal_store=setup_off.journal,
            completion=port_off,
            turn_interval=1,
            being_attachment_resolver=setup_off.resolver,
            default_world_id=setup_off.world_id,
            error_driven_reinterpretation_enabled=False,
        )
        coord_off.flush_player(PlayerId(7))

        # 誤差がまだ刻まれている recall があっても、flag OFF なら system
        # prompt に誤差駆動節が乗らず、payload にも prediction_outcome_error
        # キーが乗らない (= U9a 導入前と一致する安全な縮退)。
        messages = port_off.calls[0]
        assert "誤差駆動の再解釈" not in messages[0]["content"]
        assert '"prediction_outcome_error"' not in messages[1]["content"]
