"""BeliefEvidenceTranscriber の転記条件・trace 出力を保証する。

U2 (証拠台帳統一設計 §2 U2): 転記条件は「prediction_error が非 None」だけ。
それ以外の判定 (文字列一致カウンタ等) は作らない。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
    BeliefEvidenceTranscriber,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode


def _episode(**overrides) -> SubjectiveEpisode:
    base = dict(
        episode_id="ep-1",
        player_id=1,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(spot_id=3),
        action=EpisodeAction(tool_name="explore"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected="何か見つかるはず",
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
    )
    base.update(overrides)
    return SubjectiveEpisode(**base)


def _capture_trace(recorder: NullTraceRecorder) -> list:
    """NullTraceRecorder.record を wrap して返り値の TraceEvent を capture する。

    ``test_episodic_trace_emission.py`` と同じ規約 (専用の in-memory
    recorder クラスは作らず、NullTraceRecorder の戻り値を横取りする)。
    """
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


class TestBeliefEvidenceTranscriberRecordCondition:
    def test_prediction_error_None_does_record(self) -> None:
        """転記条件: prediction_error が None なら evidence を積まない。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(being_id, _episode(prediction_error=None))

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []

    def test_prediction_error_non_None_records_one_evidence(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id, _episode(prediction_error="何もなかった")
        )

        assert result is not None
        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].text == "何もなかった"
        assert rows[0].episode_ids == ("ep-1",)
        assert rows[0].cue_signature == "tool:explore|spot:3"

    def test_records_are_scoped_per_being(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_a = BeingId("being-a")
        being_b = BeingId("being-b")

        transcriber.record_if_applicable(
            being_a, _episode(prediction_error="外れた")
        )

        assert len(buffer_store.list_all_by_being(being_a)) == 1
        assert buffer_store.list_all_by_being(being_b) == []


class TestBeliefEvidenceTranscriberSalience:
    """U6 (予測誤差統一設計 / salience): episode.salience がそのまま
    evidence.salience に転記されること。SALIENCE_STRUCTURED_FAILURE_ENABLED
    が OFF のとき episode.salience は常に "low" (chunk 主観補完 service 側の
    保証) なので、本テストの "low" 系は導入前の固定挙動と一致する。"""

    def test_episode_low_salience_becomes_evidence_low_salience(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="外れた", salience="low")
        )

        assert buffer_store.list_all_by_being(being_id)[0].salience == "low"

    def test_episode_high_salience_becomes_evidence_high_salience(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="大ダメージを受けた", salience="high")
        )

        assert buffer_store.list_all_by_being(being_id)[0].salience == "high"


class TestBeliefEvidenceTranscriberTick:
    def test_tick_comes_from_current_tick_provider(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, current_tick_provider=lambda: 42
        )
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="外れた")
        )

        assert buffer_store.list_all_by_being(being_id)[0].tick == 42

    def test_tick_provider_exception_falls_back_None(self) -> None:
        """current_tick_provider が例外を投げても転記本体は止めない。"""

        def _raising() -> int:
            raise RuntimeError("boom")

        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, current_tick_provider=_raising
        )
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id, _episode(prediction_error="外れた")
        )

        assert result is not None
        assert buffer_store.list_all_by_being(being_id)[0].tick is None


class TestBeliefEvidenceTranscriberTrace:
    def test_emits_belief_evidence_trace_event(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = BeliefEvidenceTranscriber(
            buffer_store,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 5,
        )
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="想定外だった")
        )

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert len(events) == 1
        payload = events[0].payload
        assert payload["being_id"] == "being-1"
        assert payload["source_kind"] == "prediction_error"
        assert payload["cue_signature"] == "tool:explore|spot:3"
        assert payload["episode_ids"] == ["ep-1"]
        assert events[0].tick == 5

    def test_trace_recorder_provider_is_safe(self) -> None:
        """trace_recorder_provider 未注入でも転記自体は成功する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id, _episode(prediction_error="想定外だった")
        )

        assert result is not None

    def test_evidence_means_trace(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, trace_recorder_provider=lambda: recorder
        )
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(being_id, _episode(prediction_error=None))

        events = [e for e in captured if e.kind == TraceEventKind.BELIEF_EVIDENCE]
        assert events == []


class TestBeliefEvidenceTranscriberAttribution:
    """U4 (予測誤差統一設計 部品3): in_context_belief_ids の添付と CONFIRMATION 転記。"""

    def test_prediction_error_evidence_context_belief_ids(
        self,
    ) -> None:
        """prediction error evidence に in context belief ids が添付される。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error="外れた"),
            in_context_belief_ids=("sem-1", "sem-2"),
            had_expected_result=True,
        )

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind == BeliefEvidenceSourceKind.PREDICTION_ERROR
        assert rows[0].in_context_belief_ids == ("sem-1", "sem-2")

    def test_prediction_error_none_context_belief_expected_result_confirmation(
        self,
    ) -> None:
        """prediction error None かつ in context belief あり かつ expected result ありなら CONFIRMATION。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error=None, expected="何か見つかるはず"),
            in_context_belief_ids=("sem-1",),
            had_expected_result=True,
        )

        assert result is not None
        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind == BeliefEvidenceSourceKind.CONFIRMATION
        assert rows[0].in_context_belief_ids == ("sem-1",)
        assert rows[0].text == "予測が当たった: 何か見つかるはず"

    def test_prediction_error_none_context_belief(
        self,
    ) -> None:
        """水増しガード: in-context belief が無いターンでは CONFIRMATION を作らない。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error=None),
            in_context_belief_ids=(),
            had_expected_result=True,
        )

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []

    def test_prediction_error_none_expected_result(
        self,
    ) -> None:
        """水増しガード: 何も予測せず行動しただけのターンでは CONFIRMATION を作らない。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error=None),
            in_context_belief_ids=("sem-1",),
            had_expected_result=False,
        )

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []

    def test_flag_off_call_empty_before_matches(self) -> None:
        """呼び出し側 (coordinator/scheduler) が flag OFF のとき常に空/False を
        渡す設計 (= transcriber 自身は flag を知らない) の安全性を確認する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        # prediction_error あり: in_context_belief_ids は空のまま添付される。
        transcriber.record_if_applicable(
            being_id, _episode(prediction_error="外れた")
        )
        # prediction_error 無し: CONFIRMATION も生まれない。
        transcriber.record_if_applicable(being_id, _episode(prediction_error=None))

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind == BeliefEvidenceSourceKind.PREDICTION_ERROR
        assert rows[0].in_context_belief_ids == ()


class TestConfirmationRelevanceGate:
    """P3: belief_axis_provider 注入時、CONFIRMATION は今ターンの行動 cue と

    軸一致する in-context belief にだけ支持を積む (routine 成功への乱発を抑える)。
    ``_episode()`` の cue は tool:explore|spot:3 (action=explore, spot_id=3)。
    """

    @staticmethod
    def _provider(mapping):
        def lookup(being_id, belief_id):
            return mapping.get(belief_id)

        return lookup

    def test_axis_match_does_record(self) -> None:
        """cue (explore/3) と一致しない belief のみなら CONFIRMATION を積まない。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        provider = self._provider({"b1": (("信頼",), "タカシは信頼できる")})
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, belief_axis_provider=provider
        )
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error=None, expected="何か見つかるはず"),
            in_context_belief_ids=("b1",),
            had_expected_result=True,
        )

        assert result is None
        assert buffer_store.list_all_by_being(being_id) == []

    def test_axis_match_records_with_matched_subset_only(self) -> None:
        """一致する belief だけが attribution に残り、非一致は落ちる。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        provider = self._provider(
            {
                "b1": (("explore",), "この島の探索は空振りが多い"),  # tool:explore と一致
                "b2": (("信頼",), "タカシは信頼できる"),  # 非一致
            }
        )
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, belief_axis_provider=provider
        )
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error=None, expected="何か見つかるはず"),
            in_context_belief_ids=("b1", "b2"),
            had_expected_result=True,
        )

        assert result is not None
        assert result.source_kind == BeliefEvidenceSourceKind.CONFIRMATION
        assert result.in_context_belief_ids == ("b1",)

    def test_canary_beach_explore_belief_survives(self) -> None:
        """妥当性カナリア: 「浜辺では目立った発見はない」型 (tag に explore) が

        探索行動で生き残る (over-gating で正当な CONFIRMATION を殺さない)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        provider = self._provider(
            {"b-beach": (("浜辺", "explore"), "浜辺では目立った発見はない")}
        )
        transcriber = BeliefEvidenceTranscriber(
            buffer_store, belief_axis_provider=provider
        )
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error=None, expected="何か見つかるはず"),
            in_context_belief_ids=("b-beach",),
            had_expected_result=True,
        )

        assert result is not None
        assert result.in_context_belief_ids == ("b-beach",)

    def test_provider_None_keeps_all_beliefs_backward_compat(self) -> None:
        """provider 未注入なら従来どおり in-context belief 全件に積む。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        result = transcriber.record_if_applicable(
            being_id,
            _episode(prediction_error=None, expected="何か見つかるはず"),
            in_context_belief_ids=("b1", "b2"),
            had_expected_result=True,
        )

        assert result is not None
        assert result.in_context_belief_ids == ("b1", "b2")


class TestComputeChunkAttribution:
    """U4: chunk を構成する action 群から attribution 用の値を計算する純関数。"""

    def test_multiple_action_context_belief_ids_deduplicates(self) -> None:
        """複数 action の in context belief ids を重複排除して和集合する。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            compute_chunk_attribution,
        )

        class _Action:
            def __init__(self, in_context_belief_ids=(), expected_result=None):
                self.in_context_belief_ids = in_context_belief_ids
                self.expected_result = expected_result

        actions = [
            _Action(in_context_belief_ids=("sem-1", "sem-2")),
            _Action(in_context_belief_ids=("sem-2", "sem-3"), expected_result="X"),
        ]

        belief_ids, had_expected_result = compute_chunk_attribution(actions)

        assert belief_ids == ("sem-1", "sem-2", "sem-3")
        assert had_expected_result is True

    def test_returns_empty_when_action_empty_false(self) -> None:
        """action群が空なら空タプルとFalseを返す。"""
        from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
            compute_chunk_attribution,
        )

        belief_ids, had_expected_result = compute_chunk_attribution([])

        assert belief_ids == ()
        assert had_expected_result is False


class TestBeliefEvidenceTranscriberTypeGuards:
    def test_rejects_non_being_id(self) -> None:
        transcriber = BeliefEvidenceTranscriber(InMemoryBeliefEvidenceBufferStore())
        with pytest.raises(TypeError):
            transcriber.record_if_applicable("being-1", _episode())

    def test_rejects_non_episode(self) -> None:
        transcriber = BeliefEvidenceTranscriber(InMemoryBeliefEvidenceBufferStore())
        with pytest.raises(TypeError):
            transcriber.record_if_applicable(BeingId("being-1"), "not-an-episode")

    def test_rejects_non_repository_buffer_store(self) -> None:
        with pytest.raises(TypeError):
            BeliefEvidenceTranscriber(object())


# U10b: 約束の清算転記 (record_pending_resolution)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
)


def _pending_for_resolution(
    cues=("spot:3", "player:カイト"), *, kind="promise", text="夕方に木の下でカイトと会う"
) -> PendingPrediction:
    return PendingPrediction(
        pending_id="pending-1",
        text=text,
        resolution_cues=tuple(cues),
        tick_from=10,
        tick_to=20,
        origin_episode_id="ep-origin",
        created_tick=10,
        kind=kind,
    )


class TestBeliefEvidenceTranscriberPendingResolution:
    """record_pending_resolution が履行/破棄を PENDING_RESOLUTION に転記する (U10b)。"""

    def test_fulfilled_records_low_support(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        ev = transcriber.record_pending_resolution(
            being_id, _episode(), _pending_for_resolution(), verdict="fulfilled"
        )

        assert ev is not None
        assert ev.source_kind is BeliefEvidenceSourceKind.PENDING_RESOLUTION
        assert ev.salience == "low"
        assert "果たされた" in ev.text
        # 人物 cue を優先して寄せる
        assert ev.cue_signature == "player:カイト"
        assert buffer_store.list_all_by_being(being_id) == [ev]

    def test_broken_records_high_contradiction(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        ev = transcriber.record_pending_resolution(
            being_id, _episode(), _pending_for_resolution(), verdict="broken"
        )

        assert ev.salience == "high"
        assert "破られた" in ev.text

    def test_cue_signature_falls_back_first_cue_without_player(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        ev = transcriber.record_pending_resolution(
            being_id,
            _episode(),
            _pending_for_resolution(cues=("spot:9",)),
            verdict="fulfilled",
        )

        assert ev.cue_signature == "spot:9"

    def test_invalid_verdict_raises(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        with pytest.raises(ValueError):
            transcriber.record_pending_resolution(
                BeingId("being-1"), _episode(), _pending_for_resolution(), verdict="maybe"
            )

    def test_plan_kind_fulfilled_uses_mikomi_wording(self) -> None:
        """P11: plan (方針の見込み) の履行は「見込み『…』は当たった」文面。

        salience は verdict 由来で promise と同じ (fulfilled=low)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        plan = _pending_for_resolution(
            cues=("spot:3",), kind="plan", text="浜を探索すれば山頂への道が分かるはず"
        )

        ev = transcriber.record_pending_resolution(
            BeingId("being-1"), _episode(), plan, verdict="fulfilled"
        )

        assert "見込み" in ev.text
        assert "当たった" in ev.text
        assert "約束" not in ev.text
        assert ev.salience == "low"

    def test_plan_kind_broken_uses_mikomi_wording_high_salience(self) -> None:
        """P11: plan の破れは「見込み『…』は外れた」= 方針レベルの予測誤差。

        破れは salience=high (即時固着候補)。有害 belief の反証に流れるのが狙い。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        plan = _pending_for_resolution(
            cues=("spot:3",), kind="plan", text="浜を探索すれば山頂への道が分かるはず"
        )

        ev = transcriber.record_pending_resolution(
            BeingId("being-1"), _episode(), plan, verdict="broken"
        )

        assert "見込み" in ev.text
        assert "外れた" in ev.text
        assert ev.salience == "high"


def _goal(goal_id="g1", text="古い地図を手に入れる") -> "GoalEntry":
    from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
        GOAL_ORIGIN_SELF,
        GOAL_STATUS_ACTIVE,
        GoalEntry,
    )

    return GoalEntry(
        goal_id=goal_id, player_id=1, text=text, status=GOAL_STATUS_ACTIVE,
        locked=False, origin=GOAL_ORIGIN_SELF, created_tick=0,
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )


class TestBeliefEvidenceTranscriberGoalResolution:
    """P8: 目的の清算 (achieved / abandoned) を belief evidence に転記する。"""

    def test_achieved_records_support_evidence(self) -> None:
        """achieved は「成し遂げた」= 支持側の素材を PENDING_RESOLUTION に転記する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")
        now = datetime(2026, 7, 2, tzinfo=timezone.utc)

        ev = transcriber.record_goal_resolution(
            being_id, _goal(text="古い地図を手に入れる"), outcome="achieved", occurred_at=now
        )

        assert ev is not None
        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind == BeliefEvidenceSourceKind.PENDING_RESOLUTION
        assert "成し遂げた" in rows[0].text
        assert "古い地図を手に入れる" in rows[0].text
        assert rows[0].cue_signature == "goal:achieved"
        assert rows[0].episode_ids == ("g1",)  # 閉じた目的に辿れる

    def test_abandoned_records_error_evidence(self) -> None:
        """abandoned は「見切って諦めた」= 誤差側の素材を転記する。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")

        transcriber.record_goal_resolution(
            being_id, _goal(text="山頂で救助を待つ"), outcome="abandoned",
            occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        rows = buffer_store.list_all_by_being(being_id)
        assert "見切って諦めた" in rows[0].text
        assert rows[0].cue_signature == "goal:abandoned"

    def test_invalid_outcome_raises(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        with pytest.raises(ValueError):
            transcriber.record_goal_resolution(
                BeingId("being-1"), _goal(), outcome="superseded",
                occurred_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
            )


# ── P9 (伝聞): record_heard_claims ──

from dataclasses import dataclass as _dataclass

from ai_rpg_world.domain.memory.episodic.value_object.heard_claim import HeardClaim


@_dataclass
class _FakeMatch:
    axis: str
    value: str
    start: int


class _FakeMatcher:
    def __init__(self, matches):
        self._matches = matches

    def find_in_text(self, text):  # noqa: ARG002
        return tuple(self._matches)


class TestBeliefEvidenceTranscriberHeardClaims:
    """P9: heard_claims を HEARSAY evidence に転記する (話者と対象を分離)。"""

    def test_empty_heard_claims_records_nothing(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store)
        being_id = BeingId("being-1")
        result = transcriber.record_heard_claims(being_id, _episode(heard_claims=()))
        assert result == []
        assert buffer_store.list_all_by_being(being_id) == []

    def test_speaker_and_cue_are_separated(self) -> None:
        """話者は source_speaker、主張の対象は cue に分離される (混ぜない)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        matcher = _FakeMatcher(
            [_FakeMatch(axis="entity", value="spot_graph_player_5", start=0)]
        )
        transcriber = BeliefEvidenceTranscriber(buffer_store, noun_matcher=matcher)
        being_id = BeingId("being-1")
        episode = _episode(
            heard_claims=(HeardClaim(speaker="リオ", claim="エイダは頼りになる"),)
        )

        transcriber.record_heard_claims(being_id, episode)

        rows = buffer_store.list_all_by_being(being_id)
        assert len(rows) == 1
        assert rows[0].source_kind == BeliefEvidenceSourceKind.HEARSAY
        assert rows[0].text == "エイダは頼りになる"
        assert rows[0].source_speaker == "リオ"  # 誰から来た情報か
        # 何についてか。P10 で直接体験 cue (who = entity:actor:{id}) と同じトークン
        # 形式に揃え、同一人物の伝聞と直接体験が固着 shortlist で同じクラスタに寄る。
        assert rows[0].cue_signature == "player:entity:actor:5"

    def test_self_reference_uses_self_axis(self) -> None:
        """他者が自分について語ったら self: 軸 (episode.player_id で判定)。"""
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        matcher = _FakeMatcher(
            [_FakeMatch(axis="entity", value="spot_graph_player_1", start=0)]
        )
        transcriber = BeliefEvidenceTranscriber(buffer_store, noun_matcher=matcher)
        being_id = BeingId("being-1")
        episode = _episode(
            player_id=1,
            heard_claims=(HeardClaim(speaker="リオ", claim="カイは話を聞かない"),),
        )

        transcriber.record_heard_claims(being_id, episode)

        rows = buffer_store.list_all_by_being(being_id)
        # P10: self: 軸も人物 cue と同じ id トークン形式 (entity:actor:{id}) に揃える。
        assert rows[0].cue_signature == "self:entity:actor:1"
        assert rows[0].source_speaker == "リオ"

    def test_multiple_claims_all_recorded(self) -> None:
        buffer_store = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer_store, noun_matcher=_FakeMatcher([]))
        being_id = BeingId("being-1")
        episode = _episode(
            heard_claims=(
                HeardClaim(speaker="リオ", claim="主張1"),
                HeardClaim(speaker="エイダ", claim="主張2"),
            )
        )
        result = transcriber.record_heard_claims(being_id, episode)
        assert len(result) == 2
        # cue を特定できなくても捨てず積む (対象不明 = sentinel cue)。
        assert all(r.cue_signature == "hearsay:unattributed" for r in result)
        assert {r.source_speaker for r in result} == {"リオ", "エイダ"}
