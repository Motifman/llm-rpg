"""BeliefEvidenceTranscriber — chunk 主観補完完了点でのルールベース転記。

U2 (証拠台帳統一設計 §2 U2): 「証拠の入口はすべてルールベースの転記
(新規 LLM 呼び出しなし)」に従う。PREDICTION_ERROR の判定自体は既存の
chunk 主観補完 LLM (``EpisodicChunkSubjectiveFieldsService``) が唯一の
source であり、本クラスは ``episode.prediction_error`` が非 None かどうか
を見るだけ (文字列一致カウンタ等の独自判定は作らない)。

呼び出し元は 2 経路 (同期 / 非同期) あるが、いずれも「chunk 主観補完 LLM が
episode を merge し終えた直後」という同じタイミングで
``record_if_applicable`` を呼ぶ。呼び出し元が既に being_id を解決済みの
文脈で呼ばれる前提とし、本クラス自身は being 解決ロジックを持たない
(= ``EpisodicChunkCoordinator._put_episode`` /
``*EpisodicSubjectiveScheduler._put_episode`` の解決結果をそのまま渡す)。

feature flag (``BELIEF_EVIDENCE_ENABLED``, default OFF) は「配線 (wire) と
有効化 (enable) の分離」の既存パターンに従い、wiring 層が本クラスを
注入するかどうかで制御する。呼び出し側 (coordinator / scheduler) は
``belief_evidence_transcriber is None`` を見るだけで済み、flag の値そのもの
を知らなくてよい。

# U4 (予測誤差統一設計 部品3): attribution + CONFIRMATION

呼び出し側が ``in_context_belief_ids`` / ``had_expected_result`` を渡すことで
2 つの追加挙動が生まれる:

- PREDICTION_ERROR evidence に、その場面で in-context だった belief_id 群を
  添付する (固着パスの shortlist に必ず載せるための下ごしらえ)
- ``prediction_error`` が None (予測どおり) でも、in-context belief があり
  かつそのターンに ``expected_result`` を伴う行動があった (= 実際に何かを
  予測して行動した) 場合は CONFIRMATION evidence を積む

**flag ゲート**: 本クラス自身は ``BELIEF_ATTRIBUTION_ENABLED`` を知らない。
呼び出し側 (``EpisodicChunkCoordinator`` / スケジューラ群) が flag OFF のとき
常に ``in_context_belief_ids=()`` / ``had_expected_result=False`` を渡すことで
「導入前と挙動が一致する」を保証する (= 「配線と有効化の分離」パターンを
ここでも踏襲。呼び出し側だけが flag の値を知っていればよい)。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional, Sequence, Tuple
from uuid import uuid4

from ai_rpg_world.application.llm.services.belief_evidence_cue_signature import (
    belief_matches_cue_tokens,
    build_belief_evidence_cue_signature,
    build_hearsay_cue_signature,
    cue_tokens,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.memory.semantic.repository.belief_evidence_buffer_repository import (
    BeliefEvidenceBufferRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PENDING_KIND_PLAN,
    PENDING_VERDICT_BROKEN,
    PENDING_VERDICT_FULFILLED,
    PendingPrediction,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_HIGH,
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_STATUS_ABANDONED,
    GOAL_STATUS_ACHIEVED,
    GoalEntry,
)

_logger = logging.getLogger(__name__)

# P9 (伝聞): 主張の対象を特定できなかった HEARSAY evidence の cue。BeliefEvidence
# は空 cue を許さないための sentinel であり、既存 belief とは噛み合わず固着パスの
# discard に流れる (= 実質「対象不明の伝聞」)。
_HEARSAY_UNATTRIBUTED_CUE = "hearsay:unattributed"


def compute_chunk_attribution(
    action_results: Sequence[object],
) -> Tuple[Tuple[str, ...], bool]:
    """chunk を構成する action 群から attribution 用の 2 値を計算する (U4)。

    - in_context_belief_ids: 各 action の ``in_context_belief_ids`` の和集合
      (登場順・重複排除)
    - had_expected_result: いずれかの action が ``expected_result`` を
      持つか (= 「世界に対して何かを予測して行動した」ターンだったかの近似)

    呼び出し元 (``EpisodicChunkCoordinator`` / scheduler 群) が
    ``ChunkEncodingInput.action_results`` (``ActionResultEntry`` の tuple) を
    渡す想定。``getattr`` ベースで読むのは、テストで単純な duck-type オブジェクト
    を渡せるようにするため (既存の transcriber テストの慣習に合わせる)。
    """
    belief_ids: list[str] = []
    seen: set[str] = set()
    had_expected_result = False
    for action in action_results:
        for bid in getattr(action, "in_context_belief_ids", ()) or ():
            if bid not in seen:
                seen.add(bid)
                belief_ids.append(bid)
        if getattr(action, "expected_result", None):
            had_expected_result = True
    return tuple(belief_ids), had_expected_result


def _pending_cue_signature(
    pending: PendingPrediction, episode: SubjectiveEpisode
) -> str:
    """約束の清算 evidence の cue_signature を決める (U10b)。

    人物 (``player:``) の約束は対象 player belief に寄せたいので player cue を
    優先。無ければ最初の resolution cue、それも無ければ episode 由来の
    署名にフォールバックする (resolution_cues は VO 制約で必ず 1 件以上ある
    ため通常は最初の cue が採られる)。
    """
    player_cue = next(
        (c for c in pending.resolution_cues if c.startswith("player:")), None
    )
    if player_cue is not None:
        return player_cue
    if pending.resolution_cues:
        return pending.resolution_cues[0]
    return build_belief_evidence_cue_signature(episode)


class BeliefEvidenceTranscriber:
    """episode の ``prediction_error`` を ``BeliefEvidence`` に転記する。"""

    def __init__(
        self,
        buffer_store: BeliefEvidenceBufferRepository,
        *,
        trace_recorder_provider: Optional[
            Callable[[], Optional[ITraceRecorder]]
        ] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
        belief_axis_provider: Optional[
            Callable[[BeingId, str], Optional[Tuple[Tuple[str, ...], str]]]
        ] = None,
        noun_matcher: Optional[object] = None,
    ) -> None:
        if not isinstance(buffer_store, BeliefEvidenceBufferRepository):
            raise TypeError(
                "buffer_store must be BeliefEvidenceBufferRepository"
            )
        if trace_recorder_provider is not None and not callable(
            trace_recorder_provider
        ):
            raise TypeError("trace_recorder_provider must be callable or None")
        if current_tick_provider is not None and not callable(
            current_tick_provider
        ):
            raise TypeError("current_tick_provider must be callable or None")
        if belief_axis_provider is not None and not callable(belief_axis_provider):
            raise TypeError("belief_axis_provider must be callable or None")
        self._buffer_store = buffer_store
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider
        # P3 (CONFIRMATION 関連性ゲート): belief_id → (tags, text) を返す
        # ルックアップ。注入されているときだけ、CONFIRMATION は「そのターンの
        # 行動 context (cue) と軸一致する in-context belief」に絞って支持を積む。
        # 未注入 (None) なら従来どおり in-context belief 全件に積む (後方互換)。
        self._belief_axis_provider = belief_axis_provider
        # P9 (伝聞): heard_claim の対象を拾って cue にするための noun matcher。
        # 未注入なら伝聞 cue は空文字 (対象不明) になる。noun_matcher は
        # build_episodic_stack 内で scenario から構築されるため、transcriber の
        # 構築が先行する配線では後から attach_noun_matcher で注入する。
        self._noun_matcher = noun_matcher

    def attach_noun_matcher(self, noun_matcher: Optional[object]) -> None:
        """伝聞 cue 生成用の noun matcher を後から注入する (P9 配線用)。"""
        self._noun_matcher = noun_matcher

    def record_if_applicable(
        self,
        being_id: BeingId,
        episode: SubjectiveEpisode,
        *,
        in_context_belief_ids: Tuple[str, ...] = (),
        had_expected_result: bool = False,
    ) -> Optional[BeliefEvidence]:
        """``episode.prediction_error`` の有無で PREDICTION_ERROR / CONFIRMATION
        のいずれかの evidence を積む (U4)。

        - ``prediction_error`` が非 None: PREDICTION_ERROR evidence を積む。
          ``in_context_belief_ids`` を添付する (空でも OK。U4 flag OFF 時は
          呼び出し側が常に空タプルを渡す設計)
        - ``prediction_error`` が None かつ ``in_context_belief_ids`` が非空
          かつ ``had_expected_result`` が True: 「信じて行動して当たった」
          CONFIRMATION evidence を積む。in-context belief が無い、または
          何も予測せず行動しただけのターンでは積まない (水増しガード)
        - それ以外: 何もしない

        積んだ evidence を返す (テストの assert 用。何も積まなければ None)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        if not isinstance(in_context_belief_ids, tuple):
            raise TypeError("in_context_belief_ids must be tuple[str, ...]")
        if not isinstance(had_expected_result, bool):
            raise TypeError("had_expected_result must be bool")

        if episode.prediction_error is not None:
            evidence = BeliefEvidence(
                evidence_id=f"belief-evidence-{uuid4().hex}",
                source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
                episode_ids=(episode.episode_id,),
                cue_signature=build_belief_evidence_cue_signature(episode),
                text=episode.prediction_error,
                # U6 (予測誤差統一設計 / salience): chunk 主観補完 LLM が付けた
                # episode.salience ("low"/"high") をそのまま転記する。
                # SALIENCE_STRUCTURED_FAILURE_ENABLED が OFF のときは
                # episode.salience が常に "low" のままなので、本行の挙動は
                # 導入前 (BELIEF_EVIDENCE_SALIENCE_LOW 固定) と一致する。
                salience=episode.salience,
                occurred_at=episode.occurred_at,
                tick=self._resolve_tick(),
                in_context_belief_ids=in_context_belief_ids,
            )
            self._buffer_store.append_by_being(being_id, evidence)
            self._emit_trace(being_id, evidence)
            return evidence

        if in_context_belief_ids and had_expected_result:
            episode_cue = build_belief_evidence_cue_signature(episode)
            # P3: 関連性ゲート。provider が注入されているときは、in-context
            # belief のうち「今ターンの行動 cue と軸一致するもの」に絞る。
            # 一致が 0 件なら CONFIRMATION を積まない (routine な成功への乱発を
            # 抑える)。provider 未注入なら従来どおり全 in-context belief を対象。
            confirmed_belief_ids = self._filter_relevant_beliefs(
                being_id, in_context_belief_ids, episode_cue
            )
            if not confirmed_belief_ids:
                return None
            confirmed_text = episode.expected or "行動の予測が当たった"
            evidence = BeliefEvidence(
                evidence_id=f"belief-evidence-{uuid4().hex}",
                source_kind=BeliefEvidenceSourceKind.CONFIRMATION,
                episode_ids=(episode.episode_id,),
                cue_signature=episode_cue,
                text=f"予測が当たった: {confirmed_text}",
                # CONFIRMATION は「一撃学習」の対象ではない (的中は反復して
                # こそ意味がある) ため常に low 固定。salience=high は
                # PREDICTION_ERROR 側 (chunk 補完 LLM の判定) にのみ許す。
                salience=BELIEF_EVIDENCE_SALIENCE_LOW,
                occurred_at=episode.occurred_at,
                tick=self._resolve_tick(),
                # ゲート後の (関連する) belief だけを attribution に残す。
                in_context_belief_ids=confirmed_belief_ids,
            )
            self._buffer_store.append_by_being(being_id, evidence)
            self._emit_trace(being_id, evidence)
            return evidence

        return None

    def _filter_relevant_beliefs(
        self,
        being_id: BeingId,
        in_context_belief_ids: Tuple[str, ...],
        episode_cue: str,
    ) -> Tuple[str, ...]:
        """P3: in-context belief を「今ターンの行動 cue と軸一致するもの」に絞る。

        ``belief_axis_provider`` 未注入なら絞り込まず全件返す (後方互換)。
        provider が belief の (tags, text) を返せないもの (既に消えた等) は
        除外する。cue トークンが空 (行動情報なし) のときは一致しようがないので
        空を返す = CONFIRMATION を積まない。
        """
        if self._belief_axis_provider is None:
            return in_context_belief_ids
        tokens = cue_tokens(episode_cue)
        if not tokens:
            return ()
        relevant: list[str] = []
        for belief_id in in_context_belief_ids:
            axes = self._belief_axis_provider(being_id, belief_id)
            if axes is None:
                continue
            tags, text = axes
            if belief_matches_cue_tokens(tuple(tags), text, tokens):
                relevant.append(belief_id)
        return tuple(relevant)

    def record_pending_resolution(
        self,
        being_id: BeingId,
        episode: SubjectiveEpisode,
        pending: PendingPrediction,
        *,
        verdict: str,
    ) -> Optional[BeliefEvidence]:
        """再浮上していた約束の清算を ``PENDING_RESOLUTION`` evidence に転記する (U10b)。

        - ``verdict == "fulfilled"``: 「約束が果たされた」= 相手への信頼の支持。
          的中と同じく反復してこそ意味があるため salience=low。
        - ``verdict == "broken"``: 「約束が破られた」= 反証。裏切りは一撃で
          印象に残る出来事なので salience=high (即時固着候補) にする。

        P11: ``pending.kind`` が ``plan`` (自分の方針への見込み) のときは文面を
        「見込み『…』は当たった/外れた」に変える。破れは「方針レベルの予測誤差」
        として反証に流れ、有害な belief (「この探索は手がかりになる」型) を訂正
        できるようにするのが plan 予測化の狙い。salience は verdict 由来なので
        種別に依らず同じ (fulfilled=low / broken=high)。

        ``cue_signature`` は約束の ``resolution_cues`` のうち人物 (``player:``)
        を優先して採る (清算は「対象 player belief への支持/反証」なので、
        人物の belief クラスタに寄せる)。人物 cue が無ければ最初の cue を使う。
        判定 (fulfilled/broken) は既に chunk 主観補完 LLM が下しており、本
        メソッドは新しい判定基準を作らない (U2 以来の「証拠の入口は転記のみ」)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        if not isinstance(pending, PendingPrediction):
            raise TypeError("pending must be PendingPrediction")
        if verdict not in (PENDING_VERDICT_FULFILLED, PENDING_VERDICT_BROKEN):
            raise ValueError(
                f"verdict must be one of "
                f"({PENDING_VERDICT_FULFILLED!r}, {PENDING_VERDICT_BROKEN!r}), "
                f"got {verdict!r}"
            )

        fulfilled = verdict == PENDING_VERDICT_FULFILLED
        if pending.kind == PENDING_KIND_PLAN:
            text = (
                f"見込み「{pending.text}」は当たった。"
                if fulfilled
                else f"見込み「{pending.text}」は外れた。"
            )
        else:
            text = (
                f"約束「{pending.text}」は果たされた。"
                if fulfilled
                else f"約束「{pending.text}」は破られた。"
            )
        evidence = BeliefEvidence(
            evidence_id=f"belief-evidence-{uuid4().hex}",
            source_kind=BeliefEvidenceSourceKind.PENDING_RESOLUTION,
            episode_ids=(episode.episode_id,),
            cue_signature=_pending_cue_signature(pending, episode),
            text=text,
            salience=(
                BELIEF_EVIDENCE_SALIENCE_LOW
                if fulfilled
                else BELIEF_EVIDENCE_SALIENCE_HIGH
            ),
            occurred_at=episode.occurred_at,
            tick=self._resolve_tick(),
        )
        self._buffer_store.append_by_being(being_id, evidence)
        self._emit_trace(being_id, evidence)
        return evidence

    def record_goal_resolution(
        self,
        being_id: BeingId,
        goal: GoalEntry,
        *,
        outcome: str,
        occurred_at,
    ) -> Optional[BeliefEvidence]:
        """本人が閉じた目的 (achieved / abandoned) を belief evidence に転記する (P8)。

        目的を「選好的な予測」とみなし、その清算を U10b の約束清算と同型に
        転記する (= ``PENDING_RESOLUTION``。goal は自分自身への長期予測、約束は
        他者への予測、という違いだけ)。

        - ``outcome == achieved``: 「目的を成し遂げた」= 支持側の素材
        - ``outcome == abandoned``: 「目的を見切って諦めた」= 誤差側の素材
          (「この島で救助を待つのは現実的でない」型の belief に育つ)

        判定 (achieved / abandoned) は本人が ``goal_outcome`` で宣言済みで、本
        メソッドは新しい判定基準を作らない (U2 以来の「証拠の入口は転記のみ」)。
        目的の達成/断念はどちらも生活の節目として印象に残るため salience=high
        (即時固着候補)。``cue_signature`` は ``goal:<outcome>`` 軸にし、達成の
        反復・断念の反復がそれぞれクラスタを作れるようにする。目的の清算は
        episode に紐づかないので ``episode_ids`` には目的の ``goal_id`` を入れて
        追跡可能にする (evidence を辿ると閉じた目的に行き着く)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(goal, GoalEntry):
            raise TypeError("goal must be GoalEntry")
        if outcome not in (GOAL_STATUS_ACHIEVED, GOAL_STATUS_ABANDONED):
            raise ValueError(
                f"outcome must be one of "
                f"({GOAL_STATUS_ACHIEVED!r}, {GOAL_STATUS_ABANDONED!r}), "
                f"got {outcome!r}"
            )
        achieved = outcome == GOAL_STATUS_ACHIEVED
        text = (
            f"目的「{goal.text}」を成し遂げた。"
            if achieved
            else f"目的「{goal.text}」は見切って諦めた。"
        )
        evidence = BeliefEvidence(
            evidence_id=f"belief-evidence-{uuid4().hex}",
            source_kind=BeliefEvidenceSourceKind.PENDING_RESOLUTION,
            episode_ids=(goal.goal_id,),
            cue_signature=f"goal:{outcome}",
            text=text,
            salience=BELIEF_EVIDENCE_SALIENCE_HIGH,
            occurred_at=occurred_at,
            tick=self._resolve_tick(),
        )
        self._buffer_store.append_by_being(being_id, evidence)
        self._emit_trace(being_id, evidence)
        return evidence

    def record_heard_claims(
        self, being_id: BeingId, episode: SubjectiveEpisode
    ) -> list[BeliefEvidence]:
        """episode.heard_claims を HEARSAY evidence に転記する (P9)。

        各 claim について:
        - text = claim (主張の内容)
        - source_kind = HEARSAY
        - cue_signature = 主張の対象 (noun matcher で spot / player を拾う。
          対象不明なら空文字 = 固着パスの discard に委ねる)
        - source_speaker = 話者 (cue と分離。混ぜると話者についての belief に
          化ける)
        - salience = low (伝聞は反復してこそ意味がある。裏切り等の一撃ものと違う)

        判定 (誰が何を言ったか) は既に chunk 主観補完 LLM が済ませており、本
        メソッドは転記のみ (U2 以来の「証拠の入口は転記のみ」)。空タプルなら何も
        しない。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        recorded: list[BeliefEvidence] = []
        for claim in episode.heard_claims:
            cue = build_hearsay_cue_signature(
                claim.claim,
                self._noun_matcher,
                self_player_id=episode.player_id,
            )
            # 対象を特定できない伝聞は sentinel cue に寄せる (BeliefEvidence は
            # 空 cue を許さないため)。固着パスから見れば実質 cue なしで、既存
            # belief と噛み合わず discard される = 「曖昧な対象は捨てる」の実現。
            evidence = BeliefEvidence(
                evidence_id=f"belief-evidence-{uuid4().hex}",
                source_kind=BeliefEvidenceSourceKind.HEARSAY,
                episode_ids=(episode.episode_id,),
                cue_signature=cue or _HEARSAY_UNATTRIBUTED_CUE,
                text=claim.claim,
                salience=BELIEF_EVIDENCE_SALIENCE_LOW,
                occurred_at=episode.occurred_at,
                tick=self._resolve_tick(),
                source_speaker=claim.speaker,
            )
            self._buffer_store.append_by_being(being_id, evidence)
            self._emit_trace(being_id, evidence)
            recorded.append(evidence)
        return recorded

    def _resolve_tick(self) -> Optional[int]:
        if self._current_tick_provider is None:
            return None
        try:
            return self._current_tick_provider()
        except Exception:
            _logger.debug(
                "current_tick_provider raised; tick left as None",
                exc_info=True,
            )
            return None

    def _emit_trace(self, being_id: BeingId, evidence: BeliefEvidence) -> None:
        recorder: Optional[ITraceRecorder] = None
        if self._trace_recorder_provider is not None:
            try:
                recorder = self._trace_recorder_provider()
            except Exception:
                _logger.debug(
                    "trace_recorder_provider raised; skipping BELIEF_EVIDENCE trace",
                    exc_info=True,
                )
                recorder = None
        if recorder is None:
            return
        try:
            recorder.record(
                TraceEventKind.BELIEF_EVIDENCE,
                tick=evidence.tick,
                being_id=being_id.value,
                evidence_id=evidence.evidence_id,
                source_kind=evidence.source_kind.value,
                episode_ids=list(evidence.episode_ids),
                cue_signature=evidence.cue_signature,
                text_snippet=evidence.text[:120],
                salience=evidence.salience,
                in_context_belief_ids=list(evidence.in_context_belief_ids),
                # P9 (伝聞): HEARSAY のとき誰から来た情報かを trace に残す。
                source_speaker=evidence.source_speaker,
            )
        except Exception:
            # trace 失敗で転記本体を止めない方針 (chunk 書き込みトレースと同じ)。
            _logger.debug(
                "trace recorder.record raised for BELIEF_EVIDENCE; skipping",
                exc_info=True,
            )


__all__ = ["BeliefEvidenceTranscriber"]
