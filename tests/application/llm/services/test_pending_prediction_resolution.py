"""resolve_pending_predictions_if_applicable (U10b 清算) の挙動を保証する。

U10b (予測誤差統一設計 部品6・pending prediction 清算):

- 履行 (fulfilled) / 破棄 (broken) 判定は PENDING_RESOLUTION evidence に
  転記され、決着した約束は store から除かれる
- tick_to を過ぎても決着しなかった約束は黙って失効し store から除かれる
- flag OFF / store 未配線 / being 未解決なら何もしない (導入前と一致)
- transcriber 未配線でも store の後始末 (清算・失効) は行う
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.llm.services._pending_prediction_resolution import (
    resolve_pending_predictions_if_applicable,
)
from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
    BeliefEvidenceTranscriber,
)
from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import (
    InMemoryPendingPredictionStore,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
    PendingResolutionVerdict,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)

_BEING = BeingId("being-1")


def _pending(
    pending_id: str, *, tick_from: int, tick_to: int, cues=("player:カイト",), kind="promise"
) -> PendingPrediction:
    return PendingPrediction(
        pending_id=pending_id,
        text=f"約束-{pending_id}",
        resolution_cues=tuple(cues),
        tick_from=tick_from,
        tick_to=tick_to,
        origin_episode_id="ep-origin",
        created_tick=tick_from,
        kind=kind,
    )


def _episode(verdicts=(), who=(), co_present=()) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id="ep-1",
        player_id=1,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(spot_id=12),
        action=EpisodeAction(tool_name="explore"),
        who=tuple(who),
        co_present=tuple(co_present),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
        pending_resolution_verdicts=tuple(verdicts),
    )


def _capture_trace(recorder: NullTraceRecorder) -> list:
    captured: list = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


def _resolve(*, store, episode, transcriber=None, current_tick=20, enabled=True, being=_BEING, recorder=None):
    resolve_pending_predictions_if_applicable(
        pending_prediction_store=store,
        pending_prediction_enabled=enabled,
        being_id=being,
        episode=episode,
        belief_evidence_transcriber=transcriber,
        current_tick_provider=(lambda: current_tick),
        trace_recorder=recorder,
    )


class TestResolutionTranscription:
    """LLM 判定を evidence に転記し store から除く。"""

    def test_fulfilled_verdict_records_low_support_and_removes_pending(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        # PR-C 共在ゲート: player cue の相手 (カイト) が who に実在することを
        # fulfilled 受理の前提にしているため、共在した状態を明示する。
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")], who=("カイト",))

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert store.list_all_by_being(_BEING) == []
        evidences = buffer.list_all_by_being(_BEING)
        assert len(evidences) == 1
        ev = evidences[0]
        assert ev.source_kind is BeliefEvidenceSourceKind.PENDING_RESOLUTION
        assert ev.salience == "low"
        assert "果たされた" in ev.text
        # 人物 cue に寄せる
        assert ev.cue_signature == "player:カイト"

    def test_broken_verdict_records_high_contradiction(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode([PendingResolutionVerdict("p1", "broken")])

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        ev = buffer.list_all_by_being(_BEING)[0]
        assert ev.salience == "high"
        assert "破られた" in ev.text
        assert store.list_all_by_being(_BEING) == []

    def test_verdict_for_unknown_pending_id_is_ignored(self) -> None:
        """store に無い pending_id の判定は転記も除去もしない。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode([PendingResolutionVerdict("ghost", "fulfilled")])

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert buffer.list_all_by_being(_BEING) == []
        assert len(store.list_all_by_being(_BEING)) == 1

    def test_resolved_trace_emitted(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        episode = _episode([PendingResolutionVerdict("p1", "broken")])

        _resolve(
            store=store,
            episode=episode,
            transcriber=transcriber,
            current_tick=20,
            recorder=recorder,
        )

        kinds = [ev.kind for ev in captured]
        assert TraceEventKind.PENDING_PREDICTION_RESOLVED in kinds

    def test_resolved_trace_carries_pending_kind(self) -> None:
        """P11: RESOLVED trace の payload に種別 (pending_kind) が載る。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("p1", tick_from=10, tick_to=25, cues=("spot:3",), kind="plan")
        )
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        episode = _episode([PendingResolutionVerdict("p1", "broken")])

        _resolve(
            store=store,
            episode=episode,
            transcriber=transcriber,
            current_tick=20,
            recorder=recorder,
        )

        resolved = [
            ev for ev in captured if ev.kind == TraceEventKind.PENDING_PREDICTION_RESOLVED
        ]
        assert len(resolved) == 1
        assert resolved[0].payload["pending_kind"] == "plan"

    def test_resolved_trace_tick_is_current_tick_not_window_end(self) -> None:
        """LOW-2: RESOLVED trace の tick は実際に清算された現在 tick であり、

        窓の終端 (tick_to) ではない。窓の早い時点で果たされた約束が trace 上は
        未来の tick に記録される非対称を防ぐ (CREATED / EXPIRED は現在 tick)。
        窓の情報自体は payload の tick_from / tick_to として残す。
        """
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")], who=("カイト",))

        # tick_to=25 だが、実際に清算されたのは current_tick=15 (窓の早い時点)。
        _resolve(
            store=store,
            episode=episode,
            transcriber=transcriber,
            current_tick=15,
            recorder=recorder,
        )

        resolved = [
            ev for ev in captured if ev.kind == TraceEventKind.PENDING_PREDICTION_RESOLVED
        ]
        assert len(resolved) == 1
        assert resolved[0].tick == 15
        assert resolved[0].payload["tick_from"] == 10
        assert resolved[0].payload["tick_to"] == 25


class TestExpiry:
    """tick_to を過ぎた未決着の約束は黙って失効する。"""

    def test_expired_pending_is_removed_silently(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("old", tick_from=1, tick_to=5))
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode()  # 判定なし

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert store.list_all_by_being(_BEING) == []
        # 失効は evidence を積まない (黙って消える)
        assert buffer.list_all_by_being(_BEING) == []

    def test_pending_within_window_is_kept(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("live", tick_from=10, tick_to=30))
        episode = _episode()

        _resolve(store=store, episode=episode, current_tick=20)

        assert len(store.list_all_by_being(_BEING)) == 1

    def test_expired_trace_emitted(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("old", tick_from=1, tick_to=5))
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)

        _resolve(store=store, episode=_episode(), current_tick=20, recorder=recorder)

        kinds = [ev.kind for ev in captured]
        assert TraceEventKind.PENDING_PREDICTION_EXPIRED in kinds

    def test_expired_trace_carries_pending_kinds(self) -> None:
        """P11: EXPIRED trace の payload に id→種別 (pending_kinds) が載る

        (CREATED / RESOLVED と揃え、方針予測の失効を約束の失効と区別する)。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("plan1", tick_from=1, tick_to=5, cues=("spot:3",), kind="plan")
        )
        store.add_by_being(_BEING, _pending("prom1", tick_from=1, tick_to=5))
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)

        _resolve(store=store, episode=_episode(), current_tick=20, recorder=recorder)

        expired = [
            ev for ev in captured if ev.kind == TraceEventKind.PENDING_PREDICTION_EXPIRED
        ]
        assert len(expired) == 1
        assert expired[0].payload["pending_kinds"] == {"plan1": "plan", "prom1": "promise"}


class TestSafeDegradation:
    def test_flag_off_is_noop(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("old", tick_from=1, tick_to=5))
        episode = _episode([PendingResolutionVerdict("old", "broken")])

        _resolve(store=store, episode=episode, current_tick=20, enabled=False)

        # 何も除かれない (清算も失効もしない)
        assert len(store.list_all_by_being(_BEING)) == 1

    def test_store_none_is_noop(self) -> None:
        # 例外を投げずに黙って返る
        _resolve(store=None, episode=_episode(), current_tick=20)

    def test_being_none_is_noop(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("old", tick_from=1, tick_to=5))
        _resolve(store=store, episode=_episode(), current_tick=20, being=None)
        assert len(store.list_all_by_being(_BEING)) == 1

    def test_transcriber_none_still_prunes(self) -> None:
        """evidence 経路が OFF でも、決着・失効による store 後始末は行う。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(_BEING, _pending("p1", tick_from=10, tick_to=25))
        store.add_by_being(_BEING, _pending("old", tick_from=1, tick_to=5))
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")], who=("カイト",))

        _resolve(store=store, episode=episode, transcriber=None, current_tick=20)

        # p1 は清算で、old は失効で除かれる
        assert store.list_all_by_being(_BEING) == []


class TestCopresenceGate:
    """PR-C: fulfilled 判定 + player cue のとき、episode.who による共在確認を必須にする。

    m7_v3coop_001 t188 (「下山してカイたちと合流する」と*思っただけ*なのに
    chunk 主観補完 LLM が fulfilled と誤判定した事故) の再発防止。ゲート対象は
    「fulfilled かつ resolution_cues に player:X を含む」場合のみで、broken
    判定・player cue の無い約束は一切変更しない。
    """

    def test_fulfilled_with_absent_player_cue_target_is_rejected_and_pending_kept(
        self,
    ) -> None:
        """t188 型の再現: player:X cue つき fulfilled で who に X が不在なら、

        清算を棄却して約束を store に残す (evidence も積まない)。
        """
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("p1", tick_from=10, tick_to=25, cues=("player:カイ",))
        )
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        # 「下山してカイたちと合流する」と思っただけで、実際にはカイは
        # まだ観測 (who) に登場していない。
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")], who=())

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        remaining = store.list_all_by_being(_BEING)
        assert len(remaining) == 1
        assert remaining[0].pending_id == "p1"
        assert buffer.list_all_by_being(_BEING) == []

    def test_fulfilled_with_absent_player_cue_target_emits_rejected_trace(self) -> None:
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("p1", tick_from=10, tick_to=25, cues=("player:カイ",))
        )
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")], who=())

        _resolve(store=store, episode=episode, current_tick=20, recorder=recorder)

        rejected = [
            ev
            for ev in captured
            if ev.kind == TraceEventKind.PENDING_PREDICTION_VERDICT_REJECTED
        ]
        assert len(rejected) == 1
        payload = rejected[0].payload
        assert payload["pending_id"] == "p1"
        assert payload["being_id"] == str(_BEING.value)
        assert payload["verdict"] == "fulfilled"
        assert payload["required_players"] == ["カイ"]
        assert payload["present_players"] == []
        assert payload["missing_players"] == ["カイ"]
        # 棄却しただけで RESOLVED は emit しない
        resolved = [
            ev for ev in captured if ev.kind == TraceEventKind.PENDING_PREDICTION_RESOLVED
        ]
        assert resolved == []

    def test_fulfilled_with_present_player_cue_target_resolves_as_before(self) -> None:
        """実際に共在した (who に X あり) fulfilled は従来どおり清算される。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("p1", tick_from=10, tick_to=25, cues=("player:カイ",))
        )
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")], who=("カイ",))

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert store.list_all_by_being(_BEING) == []
        evidences = buffer.list_all_by_being(_BEING)
        assert len(evidences) == 1
        assert evidences[0].source_kind is BeliefEvidenceSourceKind.PENDING_RESOLUTION

    def test_broken_verdict_ignores_copresence_regardless_of_who(self) -> None:
        """broken 判定は who に関係なく従来どおり清算される (ゲート対象外)。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("p1", tick_from=10, tick_to=25, cues=("player:カイ",))
        )
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode([PendingResolutionVerdict("p1", "broken")], who=())

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert store.list_all_by_being(_BEING) == []
        evidences = buffer.list_all_by_being(_BEING)
        assert len(evidences) == 1
        assert "破られた" in evidences[0].text

    def test_fulfilled_without_player_cue_ignores_copresence(self) -> None:
        """player cue の無い約束 (spot cue のみ) の fulfilled は従来どおり清算される。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("p1", tick_from=10, tick_to=25, cues=("spot:12",))
        )
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")], who=())

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert store.list_all_by_being(_BEING) == []
        assert len(buffer.list_all_by_being(_BEING)) == 1

    def test_fulfilled_with_multiple_player_cues_requires_all_present(self) -> None:
        """複数 player cue のときは「約束の相手全員」が who にいることを要求する。

        1 人しか観測されていない場合は棄却し、約束を保留のまま残す。
        """
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING,
            _pending("p1", tick_from=10, tick_to=25, cues=("player:カイ", "player:ノア")),
        )
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        # カイのみ合流し、ノアはまだ来ていない。
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")], who=("カイ",))

        _resolve(store=store, episode=episode, current_tick=20, recorder=recorder)

        assert len(store.list_all_by_being(_BEING)) == 1
        rejected = [
            ev
            for ev in captured
            if ev.kind == TraceEventKind.PENDING_PREDICTION_VERDICT_REJECTED
        ]
        assert len(rejected) == 1
        assert rejected[0].payload["present_players"] == ["カイ"]
        assert rejected[0].payload["missing_players"] == ["ノア"]

    def test_fulfilled_with_multiple_player_cues_all_present_resolves(self) -> None:
        """全員 (カイ・ノア) が who にいれば従来どおり清算される。"""
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING,
            _pending("p1", tick_from=10, tick_to=25, cues=("player:カイ", "player:ノア")),
        )
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")], who=("カイ", "ノア"))

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert store.list_all_by_being(_BEING) == []
        assert len(buffer.list_all_by_being(_BEING)) == 1

    def test_rejected_pending_expires_normally_once_window_passes(self) -> None:
        """棄却で保留に戻った約束は、fulfilled を捏造されず、期限切れで静かに失効する

        (broken への書き換えは絶対に行わない、という設計上の安全弁)。
        """
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("p1", tick_from=1, tick_to=5, cues=("player:カイ",))
        )
        # 1 回目: 共在なしの fulfilled → 棄却され保留のまま残る。
        episode = _episode([PendingResolutionVerdict("p1", "fulfilled")], who=())
        _resolve(store=store, episode=episode, current_tick=3)
        assert len(store.list_all_by_being(_BEING)) == 1

        # 2 回目: 期限 (tick_to=5) を過ぎ、判定なしで失効。
        _resolve(store=store, episode=_episode(), current_tick=20)
        assert store.list_all_by_being(_BEING) == []


class TestCopresenceGateWithCoPresent:
    """PR-M: 共在ゲートの照合材料を who だけでなく co_present との和集合にする。

    バグの再現: episode.who は「観測窓で structured.actor として動作した人」だけ
    を集めたもので、同じスポットに居るが黙っている相手は入らない。相手が実在
    するのに fulfilled が誤棄却され、約束がそのまま期限切れで消えていた
    (r1_003 で 12 件が誤棄却)。co_present (= その場に居た人 = エンジン由来の
    確定事実) を照合材料に加え、「相手が黙っていても同席していれば清算を通す」。
    """

    def test_fulfilled_with_silent_copresent_target_resolves(self) -> None:
        """r1_003 tick53 型の再現: 相手 (ノア) は黙っていて who には入らないが、

        同じスポットに実在する (co_present にノアあり)。この fulfilled は誤棄却
        されず清算が通り、rejected trace は出ない。
        """
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("p1", tick_from=10, tick_to=25, cues=("player:ノア",))
        )
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        # エイダが行動し (who=エイダ)、ノアは黙っているが同席 (co_present=ノア)。
        episode = _episode(
            [PendingResolutionVerdict("p1", "fulfilled")],
            who=("エイダ",),
            co_present=("ノア",),
        )

        _resolve(
            store=store,
            episode=episode,
            transcriber=transcriber,
            current_tick=20,
            recorder=recorder,
        )

        assert store.list_all_by_being(_BEING) == []
        assert len(buffer.list_all_by_being(_BEING)) == 1
        rejected = [
            ev
            for ev in captured
            if ev.kind == TraceEventKind.PENDING_PREDICTION_VERDICT_REJECTED
        ]
        assert rejected == []

    def test_fulfilled_with_target_absent_from_both_who_and_copresent_is_rejected(
        self,
    ) -> None:
        """相手が who にも co_present にも不在なら、従来どおり棄却して保留に残す。

        共在の材料が正しくなっても「相手がその場に居ない fulfilled」は依然として
        誤判定として弾く (虚偽の履行 evidence を belief に刻まない安全弁を維持)。
        """
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING, _pending("p1", tick_from=10, tick_to=25, cues=("player:ノア",))
        )
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        episode = _episode(
            [PendingResolutionVerdict("p1", "fulfilled")],
            who=("エイダ",),
            co_present=("カイ",),
        )

        _resolve(store=store, episode=episode, current_tick=20, recorder=recorder)

        remaining = store.list_all_by_being(_BEING)
        assert len(remaining) == 1
        assert remaining[0].pending_id == "p1"
        rejected = [
            ev
            for ev in captured
            if ev.kind == TraceEventKind.PENDING_PREDICTION_VERDICT_REJECTED
        ]
        assert len(rejected) == 1
        assert rejected[0].payload["missing_players"] == ["ノア"]

    def test_multiple_player_cues_split_between_who_and_copresent_resolves(self) -> None:
        """複数 player cue の相手が who と co_present に分かれて実在していても、

        和集合で全員そろっていれば清算が通る (片方が黙っていても成立)。
        """
        store = InMemoryPendingPredictionStore()
        store.add_by_being(
            _BEING,
            _pending("p1", tick_from=10, tick_to=25, cues=("player:カイ", "player:ノア")),
        )
        buffer = InMemoryBeliefEvidenceBufferStore()
        transcriber = BeliefEvidenceTranscriber(buffer)
        # カイは発話して who に、ノアは黙っていて co_present に。
        episode = _episode(
            [PendingResolutionVerdict("p1", "fulfilled")],
            who=("カイ",),
            co_present=("ノア",),
        )

        _resolve(store=store, episode=episode, transcriber=transcriber, current_tick=20)

        assert store.list_all_by_being(_BEING) == []
        assert len(buffer.list_all_by_being(_BEING)) == 1
