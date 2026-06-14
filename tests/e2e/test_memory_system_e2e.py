"""記憶システム end-to-end smoke test (Phase 0 ~ Phase 3)。

実 LLM を使わず deterministic stub に差し替えた状態で、これまで実装した
memory 機能が **1 つのシナリオの中で一貫して動く** ことを確認する。

検証範囲:
- Phase 0: prompt section の順序 (stable_to_volatile)
- Phase 1c: §「【関連する学び】」 (semantic passive top-K)
- Phase 1d: ``memory_search_semantic`` tool が tools 配列に出る
- Phase 2: §「【最近の流れ】」 (L4 mid summary) が 15 raw 観測で生成
- Phase 2.1: scheduler 経由で L4 生成 (Inline で同期実行)
- Phase 3: §「【自己像と世界観】」 (L5 long summary) が 4 世代目 L4 evict で
  生成、3 世代を超えると最古が L5 に統合される
- 全 trace event の経路が alive (``SEMANTIC_PASSIVE_RECALL`` / ``PROMPT_SECTION_BREAKDOWN`` 等)
- silent failure 防止: LLM stub が例外を投げた場合 template fallback ＋
  warning ログが出る

LLM port は ``_StubLLMClient`` が all-in-one で satisfy する。実 ``LiteLLMClient``
を継承して各 ``complete_*_json`` を deterministic な dict で上書きしているため、
``isinstance(client, LiteLLMClient)`` を見て service 構築する wiring 側のロジック
を素通りできる。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
    L4MidSummary,
)
from ai_rpg_world.domain.memory.short_term.value_object.l5_long_summary import (
    L5LongSummary,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
    DEFAULT_L1_SOFT_CAP,
    RollingSummaryShortTermMemory,
)
from ai_rpg_world.application.llm.services.semantic_gist_service import (
    SemanticGistService,
)
from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
    SemanticPassiveRecallService,
    format_semantic_recall_section,
)
from ai_rpg_world.application.llm.services.short_term_memory_long_summary_service import (
    ShortTermMemoryLongSummaryService,
)
from ai_rpg_world.application.llm.services.short_term_memory_schedulers import (
    InlineShortTermMemoryScheduler,
    ThreadPoolShortTermMemoryScheduler,
)
from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
    ShortTermMemorySummaryService,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.trace import (
    NullTraceRecorder,
    TraceEventKind,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.application.llm._semantic_being_test_helpers import (
    make_semantic_being_setup,
)


# ──────────────────────────────────────────────────────────────────
# Stub LLM ports
# ──────────────────────────────────────────────────────────────────


class _StubSummaryPort:
    """L4 / L5 / semantic gist 用の deterministic LLM port。

    呼び出しごとに call_count を増やし、テストで「LLM が何回呼ばれたか」を
    確認できる。``raise_on_n_th`` で N 回目だけ例外を投げる挙動も模擬可能
    (template fallback の検証用)。
    """

    def __init__(
        self,
        l4_response: Dict[str, Any],
        l5_response: Dict[str, Any],
        gist_response: Dict[str, Any],
    ) -> None:
        self.l4_response = l4_response
        self.l5_response = l5_response
        self.gist_response = gist_response
        self.l4_calls = 0
        self.l5_calls = 0
        self.gist_calls = 0
        self.raise_on_l4_call: Optional[int] = None

    # --- L4 port -----------------------------------------------------
    def complete_short_term_summary_json(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        self.l4_calls += 1
        if self.raise_on_l4_call == self.l4_calls:
            raise LlmApiCallException(
                "simulated LLM failure", error_code="LLM_API_CALL_FAILED"
            )
        # nth 別の payload を返したい場合に拡張余地あり
        return dict(self.l4_response)

    # --- L5 port -----------------------------------------------------
    def complete_short_term_long_summary_json(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        self.l5_calls += 1
        return dict(self.l5_response)

    # --- semantic gist port ------------------------------------------
    def complete_semantic_gist_json(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        self.gist_calls += 1
        return dict(self.gist_response)


# ──────────────────────────────────────────────────────────────────
# Trace recorder helper
# ──────────────────────────────────────────────────────────────────


def _capture_trace(recorder: NullTraceRecorder) -> list:
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────


_PID = PlayerId(7)
_PERSONA = ("ハル", "慎重で寡黙な漁師")


def _persona_resolver(pid: int) -> tuple[str, str]:
    return _PERSONA


def _make_observation(prose: str, seq: int = 0) -> ObservationEntry:
    return ObservationEntry(
        occurred_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        output=ObservationOutput(prose=prose, structured={}),
    )


def _make_semantic_entry(
    *,
    entry_id: str,
    text: str,
    importance: int = 5,
    tags: tuple = (),
) -> SemanticMemoryEntry:
    return SemanticMemoryEntry(
        entry_id=entry_id,
        player_id=_PID.value,
        text=text,
        evidence_episode_ids=("ep-1",),
        confidence=0.7,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        importance_score=importance,
        tags=tags,
    )


def _build_memory(
    stub: _StubSummaryPort,
    *,
    scheduler_kind: str = "inline",
) -> RollingSummaryShortTermMemory:
    """全 LLM サービスを stub 接続した RollingSummaryShortTermMemory を返す。"""
    if scheduler_kind == "thread_pool":
        scheduler = ThreadPoolShortTermMemoryScheduler(max_workers=1)
    else:
        scheduler = InlineShortTermMemoryScheduler()
    return RollingSummaryShortTermMemory(
        summary_service=ShortTermMemorySummaryService(stub),  # type: ignore[arg-type]
        long_summary_service=ShortTermMemoryLongSummaryService(stub),  # type: ignore[arg-type]
        persona_resolver=_persona_resolver,
        scheduler=scheduler,
    )


# ──────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────


class TestRollingSummaryE2E:
    """L1 → L4 → L5 一気通貫 (Inline scheduler)。"""

    def test_15件で_L4_45件で_L5_60件で_L5世代2(self) -> None:
        stub = _StubSummaryPort(
            l4_response={
                "compressed_activity": "北東を探索",
                "emotional_summary": "疲労",
                "unresolved": ["水源"],
            },
            l5_response={
                "self_image": "私は慎重な漁師",
                "world_view": "島は資源豊富だが北は危険",
            },
            gist_response={
                "gist_text": "タカシは信頼できる",
                "importance_score": 7,
                "tags": ["タカシ"],
            },
        )
        mem = _build_memory(stub)

        # 15 件で L4 生成
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _make_observation(f"obs-{i}", seq=i))
        assert stub.l4_calls == 1
        assert stub.l5_calls == 0
        assert len(mem._mid_generations(_PID.value)) == 1
        assert mem._long_summary(_PID.value) is None

        # 45 件 (3 世代分): L4 = 3 件、L5 はまだ
        for batch in range(1, 3):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _make_observation(f"b{batch}-{i}", seq=batch * 100 + i))
        assert stub.l4_calls == 3
        assert stub.l5_calls == 0
        assert len(mem._mid_generations(_PID.value)) == 3

        # 60 件 (4 世代目): L4 4 回目 + L5 1 回目 (最古 L4 evict)
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _make_observation(f"b3-{i}", seq=300 + i))
        assert stub.l4_calls == 4
        assert stub.l5_calls == 1
        l5_v1 = mem._long_summary(_PID.value)
        assert l5_v1 is not None
        assert l5_v1.self_image == "私は慎重な漁師"
        assert l5_v1.generation_index == 1
        assert l5_v1.is_fallback is False

        # 75 件 (5 世代目): L5 2 回目 (次の最古 L4 evict)
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _make_observation(f"b4-{i}", seq=400 + i))
        assert stub.l5_calls == 2
        l5_v2 = mem._long_summary(_PID.value)
        assert l5_v2 is not None
        assert l5_v2.generation_index == 2


class TestRollingSummaryE2EAsync:
    """同じシナリオを ThreadPool scheduler で実行し、shutdown 完了後に
    最終状態が同等になることを確認する。"""

    def test_thread_pool_でも_最終的に_L4_3件_L5_1件(self) -> None:
        """ThreadPool で 60 raw を流し、L4=4, L5=1 が完了するまで待つ。

        注意: ``mem.shutdown()`` を直接呼ぶと、L4 worker が L5 task を
        submit する前に scheduler が閉じてしまい drop されるため、ここでは
        ポーリングで L5 完了を待ち、その後で shutdown する。

        これは Phase 2.1 architectural note: 「worker から submit」する経路
        があるので、graceful shutdown には完了待ちポーリングが必要。
        """
        import time as _time

        stub = _StubSummaryPort(
            l4_response={
                "compressed_activity": "ok",
                "emotional_summary": "",
                "unresolved": [],
            },
            l5_response={
                "self_image": "self",
                "world_view": "world",
            },
            gist_response={"gist_text": "g", "importance_score": 5, "tags": []},
        )
        mem = _build_memory(stub, scheduler_kind="thread_pool")
        try:
            for i in range(DEFAULT_L1_SOFT_CAP * 4):
                mem.append(_PID, _make_observation(f"obs-{i}", seq=i))
            # L5 が install されるまで待つ (最大 3 秒)
            deadline = _time.monotonic() + 3.0
            while _time.monotonic() < deadline:
                if mem._long_summary(_PID.value) is not None:
                    break
                _time.sleep(0.02)
        finally:
            mem.shutdown()
        assert stub.l4_calls == 4
        assert stub.l5_calls == 1
        assert len(mem._mid_generations(_PID.value)) == 3
        l5 = mem._long_summary(_PID.value)
        assert l5 is not None
        assert l5.generation_index == 1


class TestRollingSummaryFallbackChain:
    """LLM 失敗時の二段フォールバックが silent failure にならない。

    - L4 LLM が落ちる → template fallback で L4 を生やす (is_fallback=True)
    - L5 LLM は別 stub で動く前提 (gist は固定値)
    - WARNING ログが出る
    """

    def test_L4_LLM_失敗時の_template_fallback_と_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        stub = _StubSummaryPort(
            l4_response={
                "compressed_activity": "should-not-appear-if-failing",
                "emotional_summary": "",
                "unresolved": [],
            },
            l5_response={"self_image": "s", "world_view": "w"},
            gist_response={"gist_text": "g", "importance_score": 5, "tags": []},
        )
        stub.raise_on_l4_call = 1  # 最初の L4 だけ失敗
        mem = _build_memory(stub)
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.rolling_summary_short_term_memory",
        ):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _make_observation(f"obs-{i}", seq=i))
        gens = mem._mid_generations(_PID.value)
        assert len(gens) == 1
        assert gens[0].is_fallback is True
        assert any("L4 LLM 生成失敗" in rec.message for rec in caplog.records)


class TestPromptSectionsE2E:
    """``SectionBasedContextFormatStrategy`` に全 section を渡すと、
    Phase 0 / 1c / 2 / 3 の section が正しい順序で並ぶ。"""

    def test_全部入り_stable_to_volatile_順序(self) -> None:
        strategy = SectionBasedContextFormatStrategy()
        text = strategy.format(
            current_state_text="現在地: 海岸",
            recent_events_text="- 直近の出来事",
            relevant_memories_text="- 過去シーン",
            active_memos_text="- メモ",
            objective_text="生き延びる",
            inventory_text="- 流木 x3",
            learned_text="- タカシは信頼できる",
            mid_summary_text="[最新] 北東を探索",
            long_summary_text="私について: 慎重な漁師",
        )
        # 全 section が出ている
        assert "【現在の目的】" in text
        assert "【自己像と世界観】" in text  # Phase 3
        assert "【関連する学び】" in text    # Phase 1c
        assert "【最近の流れ】" in text       # Phase 2
        assert "【進行中のメモ】" in text
        assert "【所持・判明した物証】" in text
        assert "【関連する記憶】" in text
        assert "【直近の出来事】" in text
        assert "【現在地と周囲】" in text

        # stable_to_volatile 順序 (Phase 3 design doc §5):
        # objective → L5 → learned → L4 → memos → inventory → memories → events → current
        idx = {
            "obj": text.index("【現在の目的】"),
            "l5": text.index("【自己像と世界観】"),
            "learned": text.index("【関連する学び】"),
            "l4": text.index("【最近の流れ】"),
            "memos": text.index("【進行中のメモ】"),
            "inv": text.index("【所持・判明した物証】"),
            "mem": text.index("【関連する記憶】"),
            "events": text.index("【直近の出来事】"),
            "current": text.index("【現在地と周囲】"),
        }
        # 「最も安定」→「最も volatile」の順
        assert (
            idx["obj"] < idx["l5"] < idx["learned"] < idx["l4"]
            < idx["memos"] < idx["inv"] < idx["mem"] < idx["events"] < idx["current"]
        )

    def test_L5_あり_L4_あり_で_両_section_が_見える(self) -> None:
        """RollingSummary が L4 / L5 両方を生成した後の text が正しく組み立つ。"""
        stub = _StubSummaryPort(
            l4_response={
                "compressed_activity": "北東を探索した",
                "emotional_summary": "やや疲労",
                "unresolved": ["水源を見つける"],
            },
            l5_response={
                "self_image": "私は寡黙な漁師",
                "world_view": "島は資源豊富だが北は危険",
            },
            gist_response={"gist_text": "g", "importance_score": 5, "tags": []},
        )
        mem = _build_memory(stub)
        # 60 件積んで L4 3 / L5 1
        for i in range(DEFAULT_L1_SOFT_CAP * 4):
            mem.append(_PID, _make_observation(f"obs-{i}", seq=i))
        mid = mem.get_mid_summary_text(_PID)
        long_text = mem.get_long_summary_text(_PID)
        # L4 text に compressed_activity / emotional / unresolved 全部入っている
        assert "北東を探索した" in mid
        assert "やや疲労" in mid
        assert "水源を見つける" in mid
        # L5 text に self_image / world_view 両方
        assert "寡黙な漁師" in long_text
        assert "島は資源豊富だが北は危険" in long_text

        # strategy で組み立てると正しい順序
        strategy = SectionBasedContextFormatStrategy()
        full = strategy.format(
            current_state_text="now",
            recent_events_text="recent",
            mid_summary_text=mid,
            long_summary_text=long_text,
        )
        assert full.index("【自己像と世界観】") < full.index("【最近の流れ】")
        assert full.index("【最近の流れ】") < full.index("【現在地と周囲】")


class TestSemanticPassiveRecallE2E:
    """Phase 1c: semantic store の top-K が prompt §learned に出る。"""

    def test_passive_recall_と_section_format_の_連動(self) -> None:
        # Phase 3 Step 3b-3: semantic は being_id 経路必須。
        setup = make_semantic_being_setup()
        setup.provision(_PID.value)
        setup.populate(_PID.value, _make_semantic_entry(
            entry_id="s1",
            text="タカシは信頼できる",
            importance=8,
            tags=("タカシ", "信頼"),
        ))
        setup.populate(_PID.value, _make_semantic_entry(
            entry_id="s2",
            text="北の洞窟は危険",
            importance=9,
            tags=("北の洞窟", "危険"),
        ))
        setup.populate(_PID.value, _make_semantic_entry(
            entry_id="s3",
            text="嵐の前は鳥が消える",
            importance=4,
            tags=("嵐",),
        ))
        svc = SemanticPassiveRecallService(
            setup.semantic_store,
            being_attachment_resolver=setup.resolver,
            default_world_id=setup.world_id,
        )
        # cue が "タカシ" のとき top-2 を出すと s1 が上位
        cues = (
            EpisodicCue(
                axis="entity", value="タカシ", source=EpisodicCueSource.RUNTIME_CONTEXT
            ),
        )
        candidates = svc.retrieve(
            player_id=_PID.value,
            situation_cues=cues,
            top_k=2,
            now=datetime(2026, 6, 2, tzinfo=timezone.utc),
        )
        assert len(candidates) == 2
        assert candidates[0].entry.entry_id == "s1"  # tag 完全一致で最上位

        learned_text = format_semantic_recall_section(candidates)
        # strategy に渡すと §「【関連する学び】」 section が出る
        strategy = SectionBasedContextFormatStrategy()
        full = strategy.format(
            current_state_text="x",
            recent_events_text="y",
            learned_text=learned_text,
        )
        assert "【関連する学び】" in full
        assert "タカシは信頼できる" in full


class TestSemanticGistE2E:
    """Phase 1b: semantic gist 生成 (LLM 化された場合の経路)。"""

    def test_LLM_gist_が_生成され_SemanticMemoryEntry_に_反映される(self) -> None:
        stub = _StubSummaryPort(
            l4_response={"compressed_activity": "x", "emotional_summary": "", "unresolved": []},
            l5_response={"self_image": "x", "world_view": ""},
            gist_response={
                "gist_text": "タカシは漁の名手で信頼できる",
                "importance_score": 8,
                "tags": ["タカシ", "信頼"],
            },
        )
        gist_svc = SemanticGistService(stub)  # type: ignore[arg-type]

        # cluster 役の episode を作る
        eps = []
        for i in range(3):
            eps.append(SubjectiveEpisode(
                episode_id=f"ep-{i}",
                player_id=_PID.value,
                occurred_at=datetime(2026, 6, 1, 12, i, tzinfo=timezone.utc),
                game_time_label=None,
                source=EpisodeSource(event_ids=("evt-1",)),
                location=EpisodeLocation(spot_id=3),
                action=EpisodeAction(tool_name="x"),
                who=(),
                what=f"event-{i}",
                why=None,
                observed="観測",
                expected=None,
                outcome="ok",
                prediction_error=None,
                felt=None,
                interpreted=f"タカシが私を助けてくれた #{i}",
                cues=(),
                recall_text=f"recall-{i}",
                recall_count=3,
            ))

        result = gist_svc.generate(
            player_name="ハル",
            persona_block="慎重",
            cluster_episodes=eps,
        )
        assert result.gist_text == "タカシは漁の名手で信頼できる"
        assert result.importance_score == 8
        assert result.tags == ("タカシ", "信頼")
        assert stub.gist_calls == 1


class TestMemoryE2ETraceObservability:
    """fallback / drop の経路が必ず trace + warning で観測可能。

    silent failure 防止の最終確認。
    """

    def test_scheduler_drop_時に_WARNING_ログ_が出る(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """scheduler が False を返したら consumed 件数を WARNING で残す。"""

        class _DroppingScheduler(InlineShortTermMemoryScheduler):
            def submit(self, player_id, task):  # type: ignore[override]
                return False

        stub = _StubSummaryPort(
            l4_response={"compressed_activity": "x", "emotional_summary": "", "unresolved": []},
            l5_response={"self_image": "x", "world_view": ""},
            gist_response={"gist_text": "g", "importance_score": 5, "tags": []},
        )
        mem = RollingSummaryShortTermMemory(
            summary_service=ShortTermMemorySummaryService(stub),  # type: ignore[arg-type]
            scheduler=_DroppingScheduler(),
        )
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.rolling_summary_short_term_memory",
        ):
            for i in range(DEFAULT_L1_SOFT_CAP):
                mem.append(_PID, _make_observation(f"obs-{i}", seq=i))
        # drop されたので L4 は生まれない
        assert mem._mid_generations(_PID.value) == []
        # WARNING に件数が乗る
        assert any(
            "drop" in rec.message and "15" in rec.message for rec in caplog.records
        )

    def test_thread_pool_例外時に_generation_failed_trace_が_出る(self) -> None:
        """Phase 2.2: worker 例外で SHORT_TERM_SUMMARY_GENERATION_FAILED が出る。"""
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        sch = ThreadPoolShortTermMemoryScheduler(
            max_workers=1,
            trace_recorder_provider=lambda: recorder,
        )
        try:
            import threading

            done = threading.Event()

            def _raise() -> None:
                try:
                    raise ValueError("worker boom")
                finally:
                    done.set()

            sch.submit(player_id=_PID.value, task=_raise)
            assert done.wait(timeout=2.0)
        finally:
            sch.shutdown()

        fails = [
            ev for ev in captured
            if ev.kind == TraceEventKind.SHORT_TERM_SUMMARY_GENERATION_FAILED
        ]
        assert len(fails) == 1
        assert fails[0].payload["error_type"] == "ValueError"
        assert "worker boom" in fails[0].payload["error_message_snippet"]


class TestL5PersonaDriftSurvivesFailure:
    """Phase 3 の核心: LLM 失敗が連続しても persona が drift しない。

    1. L4 4 世代目で L5 v1 を成功 LLM で作る
    2. L4 5 世代目で L5 LLM を例外にする → previous_l5 (v1) を延命
    3. v1 と v2 で self_image / world_view が一致することを確認
    """

    def test_LLM_失敗の連鎖でも_self_image_は_v1_の_ままで_延命(self) -> None:
        class _FailingL5Port:
            """L5 だけ常に例外、L4 / gist は普通に動く port。"""

            def __init__(self) -> None:
                self.l4_calls = 0
                self.l5_calls = 0
                self.gist_calls = 0
                self._fail_l5 = False

            def complete_short_term_summary_json(self, messages):
                self.l4_calls += 1
                return {"compressed_activity": "ok", "emotional_summary": "", "unresolved": []}

            def complete_short_term_long_summary_json(self, messages):
                self.l5_calls += 1
                if self._fail_l5:
                    raise LlmApiCallException("sim", error_code="LLM_API_CALL_FAILED")
                return {"self_image": "私はV1の自己像", "world_view": "V1の世界観"}

            def complete_semantic_gist_json(self, messages):
                self.gist_calls += 1
                return {"gist_text": "g", "importance_score": 5, "tags": []}

        port = _FailingL5Port()
        mem = RollingSummaryShortTermMemory(
            summary_service=ShortTermMemorySummaryService(port),  # type: ignore[arg-type]
            long_summary_service=ShortTermMemoryLongSummaryService(port),  # type: ignore[arg-type]
            persona_resolver=_persona_resolver,
        )
        # 60 件 → L5 v1 (LLM 成功) が生成
        for i in range(DEFAULT_L1_SOFT_CAP * 4):
            mem.append(_PID, _make_observation(f"obs-{i}", seq=i))
        v1 = mem._long_summary(_PID.value)
        assert v1 is not None
        assert v1.self_image == "私はV1の自己像"
        assert v1.is_fallback is False
        assert v1.generation_index == 1

        # L5 LLM を失敗モードに切替えて、もう 15 件追加 → L5 v2 は fallback
        port._fail_l5 = True
        for i in range(DEFAULT_L1_SOFT_CAP):
            mem.append(_PID, _make_observation(f"more-{i}", seq=500 + i))
        v2 = mem._long_summary(_PID.value)
        assert v2 is not None
        assert v2.generation_index == 2  # 進む
        assert v2.is_fallback is True  # でも fallback
        # persona drift していない: previous_l5 がそのまま延命
        assert v2.self_image == v1.self_image
        assert v2.world_view == v1.world_view
