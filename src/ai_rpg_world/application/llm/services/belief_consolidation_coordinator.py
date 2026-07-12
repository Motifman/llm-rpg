"""固着パス — evidence buffer を belief journal に統合する協調サービス (U3b)。

semantic_learning_consolidation_design.md「固着パス:
BeliefConsolidationCoordinator」節の本体。``EpisodicReinterpretationCoordinator``
(``episodic_reinterpretation_coordinator.py``) を型紙にした batch 型
coordinator で、**semantic store (belief journal) への書き込みはここが
唯一の入口**になる。

# 発火 (ルール)

- N ターン周期 (まず 10) で evidence buffer を drain する
- ただし「同一 cue_signature の evidence が k 件 (まず 3) 以上」または
  「salience=high の evidence がある」場合は interval を待たず次周期を待たず
  flush する

# 入力の組み立て (ルール)

- drain した evidence batch (まず先頭 8 件、``list_all_by_being`` は
  ``occurred_at`` 昇順を返すので古いものから優先)
- shortlist: 既存 active belief の tags / text と、evidence の cue_signature
  由来トークンの一致で top-K (まず 5) を決定論選択

# LLM の仕事

evidence batch + shortlist を読み、evidence ごと (またはまとめて) に
create / strengthen / revise / contradict / discard を宣言する
(decisions JSON)。

# 保存 (ルール)

belief journal (``SemanticMemoryRepository``) への反映は全てルールベース:
confidence は ``compute_belief_confidence`` で再計算し、単調増加の機械値は
使わない。

# 失敗時の振る舞い

LLM 呼び出し失敗時は evidence を buffer に残し、次周期の flush で再試行する
(決定論 fallback で belief を作らない、という設計の共通方針)。batch 取得に
成功し decisions が返った場合は、batch 全体を「処理済み」として buffer から
除去する (discard 対象の evidence も含め、batch は 1 単位として drain する)。
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.ports.belief_consolidation_completion_port import (
    IBeliefConsolidationCompletionPort,
)
from ai_rpg_world.application.llm.services.belief_confidence import (
    compute_belief_confidence,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.repository.belief_evidence_buffer_repository import (
    BeliefEvidenceBufferRepository,
)
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import (
    SemanticMemoryRepository,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_HIGH,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SEMANTIC_MEMORY_STATUS_ACTIVE,
    SEMANTIC_MEMORY_STATUS_INACTIVE,
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId

DEFAULT_BELIEF_CONSOLIDATION_TURN_INTERVAL = 10
DEFAULT_BELIEF_CONSOLIDATION_BATCH_SIZE = 8
DEFAULT_BELIEF_CONSOLIDATION_SHORTLIST_TOP_K = 5
# 「同一 cue_signature の evidence が k 件」の k。この件数に達したら interval を
# 待たず次の flush 対象に含める (S1: 反復誤差の一般化を確実に拾うため)。
DEFAULT_CUE_SIGNATURE_REPEAT_THRESHOLD = 3
# contradict で confidence がこの値を割ったら inactive 化する (想起から消える。
# 削除はしない)。
DEFAULT_CONTRADICT_INACTIVE_THRESHOLD = 0.2
# U6 (予測誤差統一設計 / salience 乱発対策): 1 batch に採用する
# salience=high evidence の上限。salience=high は件数閾値なしで早期 flush
# されるため (S2 一撃学習)、乱発すると prompt が high だらけになる懸念が
# design 段階から指摘されていた (「不確実性 (中)」節)。まず 3 件から始める。
DEFAULT_HIGH_SALIENCE_BATCH_CAP = 3
MAX_BELIEF_TEXT_CHARS = 50
MAX_TAG_CHARS = 30
MAX_TAGS = 8

_ACTION_CREATE = "create"
_ACTION_STRENGTHEN = "strengthen"
_ACTION_REVISE = "revise"
_ACTION_CONTRADICT = "contradict"
_ACTION_DISCARD = "discard"

_SYSTEM_BELIEF_CONSOLIDATION_JSON = """あなたはある RPG キャラクターの内面で動く「記憶を学びに固着させる機能」です。
直近たまった「学習の素材 (evidence)」群と、すでに持っている「学び (belief)」の候補一覧 (shortlist) を読み、各 evidence についてどう扱うかを決めてください。

【入力の意味】
- evidence: 予測が外れた経験・繰り返し検出された親密度クラスタ等、学習の素材 1 件。cue_signature はその状況を表す決定論キー (例 "tool:explore|spot:浜辺")。text は素材の内容。
- shortlist: 既に固着済みの belief (学び) の候補。belief_id / text / confidence / tags / 支持件数 / 反証件数を持つ。evidence と関連しそうな belief だけを渡している。

【あなたの仕事】
evidence 群を読み、以下のいずれかの決定を **全ての evidence が最終的にどこかの決定でカバーされるように** 宣言してください:

- create: 新しい belief を作る。同じ趣旨の evidence が複数あれば 1 つの create にまとめてよい (畳み込み)。
- strengthen: 既存 belief (shortlist にある) を、この evidence 群が裏付けている。belief_id と対象 evidence_ids を書く。
- revise: 既存 belief の内容を訂正する / 言い直す (belief_id / 新しい text / reason)。次の 2 つの場面で使う。(a)「学びを信じて行動したら外れた」ような反例が来たとき。(b) strengthen を選ぶ場面でも、その belief の文面が積み上がった証拠より弱い言い方 (「〜かもしれない」「〜ことがある」) のままなら、strengthen の代わりに revise を選び、証拠に見合う強さに言い直してよい (例: 支持 3 件なら「〜ことが多い」、支持 5 件かつ反証 0 なら言い切り)。この (b) の revise は同じ命題の強化であり、新しい主張を混ぜない。
- contradict: 既存 belief に対する反証を記録する (belief_id / 対象 evidence_ids)。訂正までは要らないが確信度を下げるべきとき。
- discard: ノイズ・一時的なタスク情報など、学びに値しない evidence を捨てる (evidence_ids / reason)。

【絶対のルール】
- 命題 (create.text / revise.text) は 50 字以内、命題形式 (例: 「タカシは信頼できる」「北の洞窟は危険」)
- 個別シーンの再話ではなく、一般化された認識を書く
- 確信度に応じて修飾を変える: 確信 → 言い切り / 仮説 → 「〜かもしれない」
- プレイヤー・スポット・オブジェクトは必ず固有名詞で書く。P1, OBJ3 のような短縮ラベルは絶対に使わない
- memo 由来の evidence は「一時的なタスクか、持続する知識か」をあなたが判定する。タスクなら discard、知識なら create/strengthen

【予測との食い違い (予測誤差) を重視する】
同じ食い違いが繰り返されている / 食い違いが大きいほど、その学びは重要です。strengthen と create を迷ったら、shortlist に近い belief が無いか確認してから create してください。

【importance の付け方】(create のときのみ)
- 10: 命や根本的目標に関わる学び
- 7-9: 信頼/裏切り、重大な世界ルール、予測が繰り返し大きく外れた経験からの学び
- 4-6: 中程度の関係性・行動指針
- 1-3: 軽い嗜好・観察

【出力形式】
JSON オブジェクトのみ（説明文・コードフェンス禁止）。キーは decisions のみ。
decisions は次のいずれかの形の要素からなる配列:
{"action": "create", "text": "<50字命題>", "importance": <1-10>, "tags": ["..."], "evidence_ids": ["..."]}
{"action": "strengthen", "belief_id": "...", "evidence_ids": ["..."]}
{"action": "revise", "belief_id": "...", "text": "<50字命題>", "reason": "..."}
{"action": "contradict", "belief_id": "...", "evidence_ids": ["..."]}
{"action": "discard", "evidence_ids": ["..."], "reason": "..."}
"""

# U4 (予測誤差統一設計 部品3 / attribution + CONFIRMATION): BELIEF_ATTRIBUTION_ENABLED
# が OFF のときは CONFIRMATION evidence が一切生成されないため、この追記は
# 死んだ指示 (無意味なトークン増) になる。U6 salience 節と同じ作法で、flag ON の
# ときだけ文字列追記(置換)して足す。OFF のときは pre-U4 の system prompt と
# byte 一致することを保証する (U1 で確立した flag 規律)。
_CONFIRMATION_ANCHOR = "- evidence: 予測が外れた経験・繰り返し検出された親密度クラスタ等、学習の素材 1 件。cue_signature はその状況を表す決定論キー (例 \"tool:explore|spot:浜辺\")。text は素材の内容。"
_CONFIRMATION_INSTRUCTION = (
    _CONFIRMATION_ANCHOR
    + "\n"
    + '  - source_kind が "confirmation" の evidence は「その belief を信じて行動し、予測が当たった」という支持の証拠です。反証ではなく support として扱い、strengthen の有力な根拠にしてください。'
)


def _build_belief_consolidation_system_prompt(*, attribution_enabled: bool) -> str:
    """CONFIRMATION 節を条件付きで足した system prompt を組み立てる。

    flag OFF のときは ``_SYSTEM_BELIEF_CONSOLIDATION_JSON`` をそのまま返す
    (= 既定 prompt が byte 不変であることをここで保証する)。
    """
    if not attribution_enabled:
        return _SYSTEM_BELIEF_CONSOLIDATION_JSON
    assert _CONFIRMATION_ANCHOR in _SYSTEM_BELIEF_CONSOLIDATION_JSON
    return _SYSTEM_BELIEF_CONSOLIDATION_JSON.replace(
        _CONFIRMATION_ANCHOR, _CONFIRMATION_INSTRUCTION
    )


_logger = logging.getLogger(__name__)


def _cue_tokens(cue_signature: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for part in cue_signature.split("|"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            _, _, value = part.partition(":")
            value = value.strip().lower()
        else:
            value = part.lower()
        if value:
            tokens.append(value)
    return tuple(tokens)


class BeliefConsolidationCoordinator:
    """ターン後に evidence buffer をまとめて LLM 固着へ送る。"""

    def __init__(
        self,
        *,
        evidence_buffer_store: BeliefEvidenceBufferRepository,
        semantic_store: SemanticMemoryRepository,
        completion: Optional[IBeliefConsolidationCompletionPort],
        turn_interval: int = DEFAULT_BELIEF_CONSOLIDATION_TURN_INTERVAL,
        batch_size: int = DEFAULT_BELIEF_CONSOLIDATION_BATCH_SIZE,
        shortlist_top_k: int = DEFAULT_BELIEF_CONSOLIDATION_SHORTLIST_TOP_K,
        cue_signature_repeat_threshold: int = DEFAULT_CUE_SIGNATURE_REPEAT_THRESHOLD,
        contradict_inactive_threshold: float = DEFAULT_CONTRADICT_INACTIVE_THRESHOLD,
        high_salience_batch_cap: int = DEFAULT_HIGH_SALIENCE_BATCH_CAP,
        being_attachment_resolver: Optional[BeingAttachmentResolver] = None,
        default_world_id: Optional[WorldId] = None,
        trace_recorder_provider: Optional[Any] = None,
        current_tick_provider: Optional[Any] = None,
        belief_attribution_enabled: bool = False,
    ) -> None:
        if not isinstance(evidence_buffer_store, BeliefEvidenceBufferRepository):
            raise TypeError(
                "evidence_buffer_store must be BeliefEvidenceBufferRepository"
            )
        if not isinstance(semantic_store, SemanticMemoryRepository):
            raise TypeError("semantic_store must be SemanticMemoryRepository")
        if completion is not None and not isinstance(
            completion, IBeliefConsolidationCompletionPort
        ):
            raise TypeError(
                "completion must be IBeliefConsolidationCompletionPort or None"
            )
        if turn_interval < 1:
            raise ValueError("turn_interval must be positive")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if shortlist_top_k < 1:
            raise ValueError("shortlist_top_k must be positive")
        if cue_signature_repeat_threshold < 1:
            raise ValueError("cue_signature_repeat_threshold must be positive")
        if not (0.0 <= contradict_inactive_threshold <= 1.0):
            raise ValueError("contradict_inactive_threshold must be in [0, 1]")
        if high_salience_batch_cap < 1:
            raise ValueError("high_salience_batch_cap must be positive")
        if being_attachment_resolver is not None and not isinstance(
            being_attachment_resolver, BeingAttachmentResolver
        ):
            raise TypeError(
                "being_attachment_resolver must be BeingAttachmentResolver"
            )
        if default_world_id is not None and not isinstance(default_world_id, WorldId):
            raise TypeError("default_world_id must be WorldId")
        if not isinstance(belief_attribution_enabled, bool):
            raise TypeError("belief_attribution_enabled must be bool")
        self._evidence_buffer_store = evidence_buffer_store
        self._semantic_store = semantic_store
        self._completion = completion
        self._turn_interval = turn_interval
        self._batch_size = batch_size
        self._shortlist_top_k = shortlist_top_k
        self._cue_signature_repeat_threshold = cue_signature_repeat_threshold
        self._contradict_inactive_threshold = contradict_inactive_threshold
        self._high_salience_batch_cap = high_salience_batch_cap
        self._resolver = being_attachment_resolver
        self._default_world_id = default_world_id
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider
        # U4: ON のときだけ CONFIRMATION 節を system prompt に足す
        # (OFF = pre-U4 と byte 一致)。
        self._system_prompt = _build_belief_consolidation_system_prompt(
            attribution_enabled=belief_attribution_enabled
        )
        self._turn_counts: dict[int, int] = defaultdict(int)
        self._logger = logging.getLogger(self.__class__.__name__)

    def _resolve_being_id(self, player_id: PlayerId) -> Optional[BeingId]:
        if self._resolver is None or self._default_world_id is None:
            return None
        return self._resolver.resolve_being_id(self._default_world_id, player_id)

    def current_turn_index(self, player_id: PlayerId) -> int:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return self._turn_counts.get(player_id.value, 0)

    def after_turn_completed(self, player_id: PlayerId) -> None:
        """1 ターン完了後に呼び、発火条件を満たしたときだけ pending batch を処理する。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        pid = player_id.value
        self._turn_counts[pid] += 1
        if self._completion is None:
            return
        being_id = self._resolve_being_id(player_id)
        if being_id is None:
            return
        interval_reached = self._turn_counts[pid] % self._turn_interval == 0
        if not interval_reached and not self._has_early_trigger(being_id):
            return
        try:
            self.flush_player(player_id)
        except Exception as e:
            self._logger.warning(
                "Belief consolidation sidecar failed after turn; keeping game turn successful: %s",
                e,
                exc_info=True,
            )

    def _has_early_trigger(self, being_id: BeingId) -> bool:
        """salience=high の evidence がある、または同一 cue_signature が
        閾値以上たまっているとき True (= interval を待たず flush 対象に含める)。"""
        evidences = self._evidence_buffer_store.list_all_by_being(being_id)
        if not evidences:
            return False
        if any(e.salience == BELIEF_EVIDENCE_SALIENCE_HIGH for e in evidences):
            return True
        counts = Counter(e.cue_signature for e in evidences)
        return any(c >= self._cue_signature_repeat_threshold for c in counts.values())

    def _select_batch(
        self, all_evidence: list[BeliefEvidence]
    ) -> tuple[BeliefEvidence, ...]:
        """batch_size を上限に、salience=high の件数を
        ``high_salience_batch_cap`` (U6) までに絞って batch を組む。

        salience=high は件数閾値なしで早期 flush される (``_has_early_trigger``)
        ため、乱発すると 1 batch の prompt が high だらけになり得る (design
        の「乱発対策」)。上限を超えた high evidence は選ばず buffer に残し、
        次周期以降で拾う (捨てない)。順序は ``list_all_by_being`` の
        occurred_at 昇順を維持する (古いものを優先)。
        """
        selected: list[BeliefEvidence] = []
        high_count = 0
        for evidence in all_evidence:
            if len(selected) >= self._batch_size:
                break
            if evidence.salience == BELIEF_EVIDENCE_SALIENCE_HIGH:
                if high_count >= self._high_salience_batch_cap:
                    continue
                high_count += 1
            selected.append(evidence)
        return tuple(selected)

    def flush_player(self, player_id: PlayerId) -> int:
        """pending evidence を 1 batch 処理する。処理した evidence 件数を返す。

        Being 未解決 / completion 未注入時は silent no-op (= turn の副作用な
        ので止めない。次回 turn で再試行)。
        """
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if self._completion is None:
            return 0
        being_id = self._resolve_being_id(player_id)
        if being_id is None:
            return 0
        all_evidence = self._evidence_buffer_store.list_all_by_being(being_id)
        if not all_evidence:
            return 0
        batch = self._select_batch(all_evidence)
        shortlist = self._build_shortlist(being_id, batch)
        messages = self._build_messages(batch, shortlist)
        try:
            raw_obj = self._completion.complete_belief_consolidation_json(messages)
        except LlmApiCallException as e:
            self._logger.warning(
                "Belief consolidation LLM failed (%s); pending evidence kept",
                getattr(e, "error_code", "LLM_ERROR"),
            )
            return 0
        except Exception as e:
            self._logger.warning(
                "Belief consolidation failed; pending evidence kept: %s", e
            )
            return 0
        decisions = self._apply_decisions(
            being_id,
            player_id.value,
            batch,
            raw_obj,
        )
        batch_ids = tuple(e.evidence_id for e in batch)
        # LLM 呼び出しは成功したが有効な decisions が 0 件だったのに batch を
        # drain するケースを warning で可視化する。プロンプト/LLM 側の不具合で
        # decisions が空を返し続けると evidence が静かに失われ続けるため
        # (本プロジェクトが最も嫌う silent failure)。drain 自体は温存しない
        # 現行仕様のまま (温存するとリトライ地獄になる)。
        if not decisions:
            self._logger.warning(
                "Belief consolidation: batch %d件を drain したが適用された decision は "
                "0 件。LLM 応答に有効な decisions が無い可能性",
                len(batch_ids),
            )
        self._evidence_buffer_store.remove_by_being(being_id, batch_ids)
        self._emit_trace(being_id, batch, shortlist, decisions)
        return len(batch_ids)

    def _build_shortlist(
        self,
        being_id: BeingId,
        batch: tuple[BeliefEvidence, ...],
    ) -> tuple[SemanticMemoryEntry, ...]:
        """evidence の cue_signature 由来トークンと belief の tags/text の一致で
        top-K を決定論選択する。

        U4 (予測誤差統一設計 部品3): batch 内 evidence の
        ``in_context_belief_ids`` が指す active belief は、cue スコアが 0
        (= cue_signature からは無関係に見える) でも **必ず** shortlist に
        含める。「信じて行動して外れた/当たった」の attribution を見逃すと
        LLM が contradict/revise/CONFIRMATION による strengthen を判断する
        機会を丸ごと失う (=固着パス外の書き込み経路が無い設計では致命的)
        ため、cue スコアより優先する。

        top_k との関係: in-context 由来 (forced) の belief は top_k の
        cap を **超えても全件残す**。cue スコアだけの追加候補 (extra) は
        forced 分を差し引いた残り枠だけ選ぶ。U4 flag OFF (または batch の
        evidence が in-context belief を持たない) なら forced は常に空になり、
        本メソッドの挙動は導入前と完全に一致する。
        """
        active_beliefs = [
            e
            for e in self._semantic_store.list_for_being(being_id)
            if e.status == SEMANTIC_MEMORY_STATUS_ACTIVE
        ]
        if not active_beliefs:
            return ()
        beliefs_by_id = {b.belief_id: b for b in active_beliefs}
        forced_ids: set[str] = set()
        for evidence in batch:
            forced_ids.update(getattr(evidence, "in_context_belief_ids", ()) or ())
        forced_beliefs = sorted(
            (beliefs_by_id[bid] for bid in forced_ids if bid in beliefs_by_id),
            key=lambda b: b.belief_id,
        )
        forced_belief_ids = {b.belief_id for b in forced_beliefs}

        cue_tokens: set[str] = set()
        for evidence in batch:
            cue_tokens.update(_cue_tokens(evidence.cue_signature))
        scored: list[tuple[int, SemanticMemoryEntry]] = []
        if cue_tokens:
            for belief in active_beliefs:
                tag_set = {t.lower() for t in belief.tags}
                text_lower = belief.text.lower()
                score = 0
                for token in cue_tokens:
                    if token in tag_set or token in text_lower:
                        score += 1
                if score > 0:
                    scored.append((score, belief))
            scored.sort(key=lambda pair: (-pair[0], pair[1].belief_id))

        remaining_slots = max(0, self._shortlist_top_k - len(forced_beliefs))
        extra = [
            belief
            for _, belief in scored
            if belief.belief_id not in forced_belief_ids
        ][:remaining_slots]
        return tuple(forced_beliefs) + tuple(extra)

    def _build_messages(
        self,
        batch: tuple[BeliefEvidence, ...],
        shortlist: tuple[SemanticMemoryEntry, ...],
    ) -> list[dict[str, Any]]:
        evidence_payload = [
            {
                "evidence_id": e.evidence_id,
                "source_kind": e.source_kind.value,
                "cue_signature": e.cue_signature,
                "text": e.text,
                "salience": e.salience,
                "episode_ids": list(e.episode_ids),
            }
            for e in batch
        ]
        shortlist_payload = [
            {
                "belief_id": b.belief_id,
                "text": b.text,
                "confidence": b.confidence,
                "tags": list(b.tags),
                "support_count": len(b.support_evidence_ids),
                "contradict_count": len(b.contradict_evidence_ids),
            }
            for b in shortlist
        ]
        user_content = {
            "evidence": evidence_payload,
            "shortlist": shortlist_payload,
        }
        return [
            {"role": "system", "content": self._system_prompt},
            {
                "role": "user",
                "content": (
                    "以下の evidence / shortlist を読み、decisions を JSON だけで返してください。\n"
                    f"{json.dumps(user_content, ensure_ascii=False)}"
                ),
            },
        ]

    def _apply_decisions(
        self,
        being_id: BeingId,
        player_id: int,
        batch: tuple[BeliefEvidence, ...],
        raw_obj: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """decisions を belief journal に適用する。適用に使った decisions を返す
        (trace payload 用)。"""
        if not isinstance(raw_obj, dict):
            return []
        raw_decisions = raw_obj.get("decisions")
        if not isinstance(raw_decisions, list):
            return []
        evidence_by_id = {e.evidence_id: e for e in batch}
        batch_ids = tuple(e.evidence_id for e in batch)
        now = datetime.now(timezone.utc)
        applied: list[dict[str, Any]] = []
        for raw in raw_decisions:
            if not isinstance(raw, dict):
                continue
            action = raw.get("action")
            try:
                if action == _ACTION_CREATE:
                    self._apply_create(being_id, player_id, raw, evidence_by_id, batch_ids, now)
                elif action == _ACTION_STRENGTHEN:
                    self._apply_strengthen(being_id, raw, evidence_by_id, batch_ids, now)
                elif action == _ACTION_REVISE:
                    self._apply_revise(being_id, player_id, raw, now)
                elif action == _ACTION_CONTRADICT:
                    self._apply_contradict(being_id, raw, evidence_by_id, batch_ids, now)
                elif action == _ACTION_DISCARD:
                    pass  # evidence は batch drain で自動的に消える
                else:
                    continue
            except Exception as e:  # pragma: no cover - 想定外の1件で全体を壊さない
                self._logger.warning(
                    "Belief consolidation decision application failed (action=%s): %s",
                    action,
                    e,
                    exc_info=True,
                )
                continue
            applied.append(raw)
        return applied

    def _resolve_evidence_ids(
        self,
        raw: dict[str, Any],
        evidence_by_id: dict[str, BeliefEvidence],
        batch_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        raw_ids = raw.get("evidence_ids")
        if isinstance(raw_ids, list):
            valid = tuple(
                str(x) for x in raw_ids if isinstance(x, str) and x.strip() in evidence_by_id
            )
            if valid:
                return valid
        # 未指定 / 無効なら batch 全体を根拠とみなす (create がどの evidence を
        # 使ったか明示しない decisions スキーマへの対応)。
        return batch_ids

    def _apply_create(
        self,
        being_id: BeingId,
        player_id: int,
        raw: dict[str, Any],
        evidence_by_id: dict[str, BeliefEvidence],
        batch_ids: tuple[str, ...],
        now: datetime,
    ) -> None:
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        text = text.strip()[:MAX_BELIEF_TEXT_CHARS]
        importance = raw.get("importance", 5)
        try:
            importance = int(importance)
        except (TypeError, ValueError):
            importance = 5
        importance = max(1, min(10, importance))
        evidence_ids = self._resolve_evidence_ids(raw, evidence_by_id, batch_ids)
        # LLM 生成タグに加えて、根拠 evidence の cue_signature 由来トークン
        # (英語の tool token を含む) を tags に混ぜて索引を自己一貫させる。
        # こうしないと tool 軸の cue token (例: "explore") は日本語 belief の
        # tags/text と永久に一致せず、次回の同 cue evidence が既存 belief を
        # shortlist に載せられないため、strengthen できず重複 create を生む
        # (shortlist の tool 軸言語ミスマッチの構造的修復)。
        tags: list[str] = []
        seen: set[str] = set()

        def _add_tag(candidate: str) -> None:
            if len(tags) >= MAX_TAGS:
                return
            trimmed = candidate.strip()[:MAX_TAG_CHARS]
            if not trimmed:
                return
            key = trimmed.lower()
            if key in seen:
                return
            seen.add(key)
            tags.append(trimmed)

        tags_raw = raw.get("tags", [])
        if isinstance(tags_raw, list):
            for t in tags_raw:
                if isinstance(t, str):
                    _add_tag(t)
        for eid in evidence_ids:
            evidence = evidence_by_id.get(eid)
            if evidence is None:
                continue
            for token in _cue_tokens(evidence.cue_signature):
                _add_tag(token)
        episode_ids: list[str] = []
        for eid in evidence_ids:
            evidence = evidence_by_id.get(eid)
            if evidence is not None:
                episode_ids.extend(evidence.episode_ids)
        entry_id = f"sem-{uuid4().hex}"
        entry = SemanticMemoryEntry(
            entry_id=entry_id,
            player_id=player_id,
            text=text,
            evidence_episode_ids=tuple(sorted(set(episode_ids))),
            # founding evidence 件数を初期 confidence に反映
            # (support_evidence_ids を数えているので base 固定は不整合)。
            confidence=compute_belief_confidence(len(evidence_ids), 0),
            created_at=now,
            importance_score=importance,
            tags=tuple(tags),
            belief_id=entry_id,
            status=SEMANTIC_MEMORY_STATUS_ACTIVE,
            support_evidence_ids=evidence_ids,
        )
        self._semantic_store.add_by_being(being_id, entry)

    def _find_active_entry(
        self, being_id: BeingId, belief_id: str
    ) -> Optional[SemanticMemoryEntry]:
        for entry in self._semantic_store.list_for_being(being_id):
            if entry.belief_id == belief_id and entry.status == SEMANTIC_MEMORY_STATUS_ACTIVE:
                return entry
        return None

    def _apply_strengthen(
        self,
        being_id: BeingId,
        raw: dict[str, Any],
        evidence_by_id: dict[str, BeliefEvidence],
        batch_ids: tuple[str, ...],
        now: datetime,
    ) -> None:
        belief_id = raw.get("belief_id")
        if not isinstance(belief_id, str) or not belief_id.strip():
            return
        target = self._find_active_entry(being_id, belief_id.strip())
        if target is None:
            return
        evidence_ids = self._resolve_evidence_ids(raw, evidence_by_id, batch_ids)
        new_support = tuple(sorted(set(target.support_evidence_ids) | set(evidence_ids)))
        new_confidence = compute_belief_confidence(
            len(new_support), len(target.contradict_evidence_ids)
        )
        updated = replace(
            target,
            support_evidence_ids=new_support,
            confidence=new_confidence,
            created_at=now,
        )
        self._semantic_store.add_by_being(being_id, updated)

    def _apply_revise(
        self,
        being_id: BeingId,
        player_id: int,
        raw: dict[str, Any],
        now: datetime,
    ) -> None:
        belief_id = raw.get("belief_id")
        text = raw.get("text")
        if not isinstance(belief_id, str) or not belief_id.strip():
            return
        if not isinstance(text, str) or not text.strip():
            return
        target = self._find_active_entry(being_id, belief_id.strip())
        if target is None:
            return
        new_text = text.strip()[:MAX_BELIEF_TEXT_CHARS]
        new_entry_id = f"sem-{uuid4().hex}"
        new_entry = SemanticMemoryEntry(
            entry_id=new_entry_id,
            player_id=player_id,
            text=new_text,
            evidence_episode_ids=target.evidence_episode_ids,
            confidence=compute_belief_confidence(
                len(target.support_evidence_ids), len(target.contradict_evidence_ids)
            ),
            created_at=now,
            importance_score=target.importance_score,
            tags=target.tags,
            belief_id=target.belief_id,
            status=SEMANTIC_MEMORY_STATUS_ACTIVE,
            supersedes=target.entry_id,
            support_evidence_ids=target.support_evidence_ids,
            contradict_evidence_ids=target.contradict_evidence_ids,
        )
        self._semantic_store.supersede_by_being(
            being_id, old_entry_id=target.entry_id, new_entry=new_entry
        )

    def _apply_contradict(
        self,
        being_id: BeingId,
        raw: dict[str, Any],
        evidence_by_id: dict[str, BeliefEvidence],
        batch_ids: tuple[str, ...],
        now: datetime,
    ) -> None:
        belief_id = raw.get("belief_id")
        if not isinstance(belief_id, str) or not belief_id.strip():
            return
        target = self._find_active_entry(being_id, belief_id.strip())
        if target is None:
            return
        evidence_ids = self._resolve_evidence_ids(raw, evidence_by_id, batch_ids)
        new_contradict = tuple(
            sorted(set(target.contradict_evidence_ids) | set(evidence_ids))
        )
        new_confidence = compute_belief_confidence(
            len(target.support_evidence_ids), len(new_contradict)
        )
        updated = replace(
            target,
            contradict_evidence_ids=new_contradict,
            confidence=new_confidence,
            created_at=now,
        )
        self._semantic_store.add_by_being(being_id, updated)
        if new_confidence < self._contradict_inactive_threshold:
            self._semantic_store.update_status_by_being(
                being_id, target.entry_id, SEMANTIC_MEMORY_STATUS_INACTIVE
            )

    def _emit_trace(
        self,
        being_id: BeingId,
        batch: tuple[BeliefEvidence, ...],
        shortlist: tuple[SemanticMemoryEntry, ...],
        decisions: list[dict[str, Any]],
    ) -> None:
        recorder: Optional[ITraceRecorder] = None
        if self._trace_recorder_provider is not None:
            try:
                recorder = self._trace_recorder_provider()
            except Exception:
                _logger.debug(
                    "trace_recorder_provider raised; skipping BELIEF_CONSOLIDATION trace",
                    exc_info=True,
                )
                recorder = None
        if recorder is None:
            return
        tick: Optional[int] = None
        if self._current_tick_provider is not None:
            try:
                tick = self._current_tick_provider()
            except Exception:
                tick = None
        try:
            recorder.record(
                TraceEventKind.BELIEF_CONSOLIDATION,
                tick=tick,
                being_id=being_id.value,
                batch_evidence_ids=[e.evidence_id for e in batch],
                shortlist_belief_ids=[b.belief_id for b in shortlist],
                decisions=decisions,
            )
        except Exception:
            _logger.debug(
                "trace recorder.record raised for BELIEF_CONSOLIDATION; skipping",
                exc_info=True,
            )


__all__ = [
    "BeliefConsolidationCoordinator",
    "DEFAULT_BELIEF_CONSOLIDATION_TURN_INTERVAL",
    "DEFAULT_BELIEF_CONSOLIDATION_BATCH_SIZE",
    "DEFAULT_BELIEF_CONSOLIDATION_SHORTLIST_TOP_K",
    "DEFAULT_CUE_SIGNATURE_REPEAT_THRESHOLD",
    "DEFAULT_CONTRADICT_INACTIVE_THRESHOLD",
]
