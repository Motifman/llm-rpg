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
from typing import Any, Callable, Optional
from uuid import uuid4

from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.ports.belief_consolidation_completion_port import (
    IBeliefConsolidationCompletionPort,
)
from ai_rpg_world.application.llm.services.belief_confidence import (
    compute_belief_confidence,
)
from ai_rpg_world.application.llm.services.belief_evidence_cue_signature import (
    belief_matches_cue_tokens as _shared_belief_matches_cue_tokens,
    cue_tokens as _shared_cue_tokens,
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
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
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
# P4: 同一目的への停滞内省観測を出す最小 turn 間隔 (乱発防止 cap)。
DEFAULT_STALL_MIN_INTERVAL_TURNS = 15
MAX_BELIEF_TEXT_CHARS = 50
MAX_TAG_CHARS = 30
MAX_TAGS = 8

_ACTION_CREATE = "create"
_ACTION_STRENGTHEN = "strengthen"
_ACTION_REVISE = "revise"
_ACTION_CONTRADICT = "contradict"
_ACTION_DISCARD = "discard"
_ACTION_REFLECT = "reflect"  # P4: 目的への前進評価 (belief journal には書かない)
# P7: reflect が返す判定の種類。停滞 / 達成 / 乖離 (目的と行動の乖離)。いずれも
# 内省観測として本人に返すだけで、goal store の status 変更はしない (不変条件)。
_REFLECT_VERDICT_STALLED = "stalled"
_REFLECT_VERDICT_ACHIEVED = "achieved"
_REFLECT_VERDICT_MISALIGNED = "misaligned"
_REFLECT_VERDICTS = frozenset(
    {_REFLECT_VERDICT_STALLED, _REFLECT_VERDICT_ACHIEVED, _REFLECT_VERDICT_MISALIGNED}
)

_SYSTEM_BELIEF_CONSOLIDATION_JSON = """あなたはある RPG キャラクターの内面で動く「記憶を学びに固着させる機能」です。
直近たまった「学習の素材 (evidence)」群と、すでに持っている「学び (belief)」の候補一覧 (shortlist) を読み、各 evidence についてどう扱うかを決めてください。

【入力の意味】
- evidence: 予測が外れた経験・繰り返し検出された親密度クラスタ等、学習の素材 1 件。cue_signature はその状況を表す決定論キー (例 "tool:explore|spot:浜辺")。text は素材の内容。
- shortlist: 既に固着済みの belief (学び) の候補。belief_id / text / confidence / tags / 支持件数 / 反証件数を持つ。evidence と関連しそうな belief だけを渡している。

【あなたの仕事】
evidence 群を読み、以下のいずれかの決定を **全ての evidence が最終的にどこかの決定でカバーされるように** 宣言してください:

- create: 新しい belief を作る。同じ趣旨の evidence が複数あれば 1 つの create にまとめてよい (畳み込み)。
- strengthen: 既存 belief (shortlist にある) を、この evidence 群が裏付けている。belief_id と対象 evidence_ids を書く。
- revise: 既存 belief の文面を書き換える (belief_id / 新しい text / reason)。2 用途。(a) 反例が来て内容が間違っていたときの訂正。(b) 内容は正しいが言い方が証拠に見合っていないときの言い直し (下の【文面の強さを証拠に合わせる】参照)。
- contradict: 既存 belief に対する反証を記録する (belief_id / 対象 evidence_ids)。訂正までは要らないが確信度を下げるべきとき。
- discard: ノイズ・一時的なタスク情報など、学びに値しない evidence を捨てる (evidence_ids / reason)。

【絶対のルール】
- 命題 (create.text / revise.text) は 50 字以内、命題形式 (例: 「タカシは信頼できる」「北の洞窟は危険」)
- 個別シーンの再話ではなく、一般化された認識を書く
- 確信度に応じて修飾を変える: 確信 → 言い切り / 仮説 → 「〜かもしれない」
- プレイヤー・スポット・オブジェクトは必ず固有名詞で書く。P1, OBJ3 のような短縮ラベルは絶対に使わない
- memo 由来の evidence は「一時的なタスクか、持続する知識か」をあなたが判定する。タスクなら discard、知識なら create/strengthen

【文面の強さを証拠に合わせる】
strengthen を選ぶとき、必ずその belief の**現在の文面**を見ること。文面が「〜かもしれない」「〜ことがある」のような弱い言い方なのに、支持が 3 件以上たまり反証が無いなら、それは証拠に対して弱すぎる。その場合は strengthen ではなく **revise を選び、ヘッジを外して証拠に見合う強さに言い直すこと** (支持 3〜4 件 → 「〜ことが多い」、支持 5 件以上かつ反証 0 → 言い切り)。命題の中身は変えず、確信の度合いだけを上げる。逆に、支持が 1〜2 件しかない belief はヘッジを保つ (弱いままが正しい較正で、無理に言い切らない)。

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


# P4 (reflect / 目的への前進評価): GOAL_REFLECT_ENABLED が ON のときだけ足す節。
# belief journal には書かず、目的に前進があったかを判断させる。停滞と判断した
# ときだけ reflect を宣言させる (前進していれば書かない = 乱発防止の第一段)。
# ユーザメッセージに【現在の目的】が渡っているときだけ意味を持つ。
_REFLECT_INSTRUCTION = """

【目的への前進評価 (reflect)】
ユーザメッセージに「現在の目的」が渡っている場合、evidence 群を通常どおり
create / strengthen 等で処理した**うえで、それとは別に**、この期間の行動を
その目的と照らして評価すること。次の 3 つのいずれかが明らかなときだけ、他の
決定に**加えて** reflect を 1 つ足す (create の代わりではなく、追加で書く):

(1) 停滞 (stalled): 目的に向けた試み (移動・探索など) が続けて 2 回以上ねらいを
    外し、かつこの期間の evidence に目的へ近づけたものが 1 件も無い。
    → {"action":"reflect","verdict":"stalled","statement":"<同じ場所を空回りしている、という気づきを一人称で 1 文>"}
(2) 達成 (achieved): 目的がすでに果たされたことを示す evidence がある
    (探していたものを見つけた・行きたかった場所に着いた等)。
    → {"action":"reflect","verdict":"achieved","statement":"<目指していたことはもう果たした、という気づきを一人称で 1 文>"}
(3) 乖離 (misaligned): 目的と結びつく行動がなく、目的とは無関係なことばかりに
    没頭していて、目的から明らかにそれている。
    → {"action":"reflect","verdict":"misaligned","statement":"<目的から逸れている、という気づきを一人称で 1 文>"}

reflect は belief を作らない (意識に「気づき」を返すだけ)。目的の status を
変えたり目的文を書き換えたりはしない — 気づきを本人に返すだけで、どうするかの
判断は本人 (次の手) に委ねる。
次のときは reflect を書かない:
- 目的に向けて着実に前進している (近づいた evidence があり、逸れてもいない)
- 待ち合わせ・看病のように、動いていないことに正当な理由がある
- どの判断も確信が持てない"""


# P10 (伝聞の固着判断): HEARSAY_ENABLED が ON のときだけ足す節。伝聞 evidence
# (source_kind が "hearsay") は他の evidence と同列に batch に載り、shortlist には
# 話者についての人物 belief も載せている (下記 _build_shortlist)。話者を信じるか
# どうかを数値ではなく文脈判断させるための指示 (設計メモ §2 ステップ 3)。OFF の
# ときは伝聞 evidence 自体が生成されないので、この追記は死んだ指示になる。
_HEARSAY_INSTRUCTION = """

【伝聞 (hearsay) の扱い】
source_kind が "hearsay" の evidence は、自分で確かめたことではなく他者の発言から
得た主張です (source_speaker がその話者)。伝聞は自分の体験より弱い証拠として扱って
ください。shortlist にはその話者についての人物 belief も載せています。話者について
自分が知っていること (例:「あいつは人の話を聞かない」「地形には詳しい」) を踏まえ、
その主張を信じる (create / strengthen) か、鵜呑みにせず捨てる (discard) かを判断して
ください。同じ話者でも話題によって信じ方を変えてよい (人の評判は疑うが地形情報は
信じる、など)。自分が実際に体験して得た belief (shortlist の文面が一人称の体験で
語られているもの) と食い違う伝聞は、伝聞のほうを discard するのが原則です。人づて
一件で自分の体験を覆さないでください。"""


def _build_belief_consolidation_system_prompt(
    *,
    attribution_enabled: bool,
    goal_reflect_enabled: bool = False,
    hearsay_enabled: bool = False,
) -> str:
    """CONFIRMATION 節 / reflect 節 / 伝聞節を条件付きで足した system prompt を組む。

    全 flag OFF のときは ``_SYSTEM_BELIEF_CONSOLIDATION_JSON`` をそのまま返す
    (= 既定 prompt が byte 不変であることをここで保証する)。
    """
    prompt = _SYSTEM_BELIEF_CONSOLIDATION_JSON
    if attribution_enabled:
        assert _CONFIRMATION_ANCHOR in prompt
        prompt = prompt.replace(_CONFIRMATION_ANCHOR, _CONFIRMATION_INSTRUCTION)
    if goal_reflect_enabled:
        prompt = prompt + _REFLECT_INSTRUCTION
    if hearsay_enabled:
        prompt = prompt + _HEARSAY_INSTRUCTION
    return prompt


_logger = logging.getLogger(__name__)


def _cue_tokens(cue_signature: str) -> tuple[str, ...]:
    # P3: shortlist 照合と CONFIRMATION ゲートで同じトークン化を使うため、
    # 実装は belief_evidence_cue_signature.cue_tokens に集約した (挙動は不変)。
    return _shared_cue_tokens(cue_signature)


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
        goal_reflect_enabled: bool = False,
        hearsay_enabled: bool = False,
        objective_text_provider: Optional[Callable[[PlayerId], Optional[str]]] = None,
        reflect_observation_sink: Optional[Callable[[PlayerId, str, str], None]] = None,
        stall_min_interval_turns: int = DEFAULT_STALL_MIN_INTERVAL_TURNS,
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
        if not isinstance(goal_reflect_enabled, bool):
            raise TypeError("goal_reflect_enabled must be bool")
        if not isinstance(hearsay_enabled, bool):
            raise TypeError("hearsay_enabled must be bool")
        if objective_text_provider is not None and not callable(objective_text_provider):
            raise TypeError("objective_text_provider must be callable or None")
        if reflect_observation_sink is not None and not callable(reflect_observation_sink):
            raise TypeError("reflect_observation_sink must be callable or None")
        # P4 fail-fast: goal_reflect を ON にするなら「監査対象の目的 provider」と
        # 「内省観測 sink」の両方が要る。片方でも欠けると reflect 節を prompt に
        # 出しておきながら発火した reflect を黙って捨てる / 目的が渡らず節が死んで
        # token だけ食う、という静かな失敗になる。起動時に構造で弾く (CLAUDE.md
        # 「起動時 fail-fast が最後の砦」)。
        if goal_reflect_enabled and objective_text_provider is None:
            raise ValueError(
                "goal_reflect_enabled requires objective_text_provider "
                "(reflect の監査対象となる目的が渡らないと節が死ぬ)"
            )
        if goal_reflect_enabled and reflect_observation_sink is None:
            raise ValueError(
                "goal_reflect_enabled requires reflect_observation_sink "
                "(発火した reflect を注入できず黙って捨てることになる)"
            )
        if stall_min_interval_turns < 1:
            raise ValueError("stall_min_interval_turns must be positive")
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
        # (OFF = pre-U4 と byte 一致)。P4: goal_reflect も同様に flag ON で reflect
        # 節を足す (OFF なら reflect の指示は一切出ない)。
        self._goal_reflect_enabled = goal_reflect_enabled
        # P10: ON のときだけ伝聞節を system prompt に足し、shortlist に話者 belief を
        # 載せる。OFF なら伝聞 evidence 自体が生成されないので、節も話者 belief 強制も
        # 死んだ経路になる (= pre-P10 と byte / 挙動一致)。
        self._hearsay_enabled = hearsay_enabled
        self._objective_text_provider = objective_text_provider
        self._reflect_observation_sink = reflect_observation_sink
        self._stall_min_interval_turns = stall_min_interval_turns
        self._system_prompt = _build_belief_consolidation_system_prompt(
            attribution_enabled=belief_attribution_enabled,
            goal_reflect_enabled=goal_reflect_enabled,
            hearsay_enabled=hearsay_enabled,
        )
        self._turn_counts: dict[int, int] = defaultdict(int)
        # P4/P7: 同一 being への内省観測の乱発防止 cap。最後に観測を出した turn
        # index を (player, verdict 種別) ごとに覚え、min_interval 未満なら再注入
        # しない。種別ごとに分けるのは、直近の停滞観測が達成の気づきを巻き込んで
        # 抑制してしまわないため (別種の気づきは独立に返せる)。
        self._last_reflect_turn: dict[tuple[int, str], int] = {}
        self._logger = logging.getLogger(self.__class__.__name__)

    def _resolve_being_id(self, player_id: PlayerId) -> Optional[BeingId]:
        if self._resolver is None or self._default_world_id is None:
            return None
        return self._resolver.resolve_being_id(self._default_world_id, player_id)

    def _resolve_objective_text(self, player_id: PlayerId) -> Optional[str]:
        """P4: reflect の監査対象となる現在の目的文を解決する。

        goal_reflect が OFF / provider 未注入 / 例外 / 空文字なら None
        (= reflect 節が意味を持たず、prompt にも目的が載らない)。
        """
        if not self._goal_reflect_enabled or self._objective_text_provider is None:
            return None
        try:
            text = self._objective_text_provider(player_id)
        except Exception:
            self._logger.debug("objective_text_provider raised", exc_info=True)
            return None
        if not isinstance(text, str) or not text.strip():
            return None
        return text.strip()

    def _apply_reflect(self, player_id: int, raw: dict[str, Any]) -> bool:
        """P4/P7: reflect 決定を処理する。停滞 / 達成 / 乖離の気づきを内省観測

        として本人に注入する。**goal store には書かない** — この coordinator は
        goal store への参照を一切持たず、意識に「気づき」を返すだけ。目的の
        status 変更や書き換えは本人 (P6 の goal_update) に委ねる (「無意識が感覚を
        上げ、意識が決断する」の分担を構造で保証する)。以下のときは何もせず
        False を返す (= trace にも残さない):
        - goal_reflect OFF / 観測 sink 未注入
        - verdict が stalled / achieved / misaligned のいずれでもない
        - statement が空
        - 同一 player の同じ種別の観測が直近 ``stall_min_interval_turns`` 以内
          (種別ごとの乱発防止 cap)
        観測を注入したら True。
        """
        if not self._goal_reflect_enabled or self._reflect_observation_sink is None:
            return False
        verdict = raw.get("verdict")
        if verdict not in _REFLECT_VERDICTS:
            return False
        statement = raw.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            return False
        turn = self._turn_counts.get(player_id, 0)
        cap_key = (player_id, verdict)
        last = self._last_reflect_turn.get(cap_key)
        if last is not None and (turn - last) < self._stall_min_interval_turns:
            return False
        try:
            self._reflect_observation_sink(
                PlayerId(player_id), statement.strip(), verdict
            )
        except Exception:
            # cap は注入に成功したときだけ消費する。sink が一時的に失敗した局面で
            # cap を進めてしまうと、注入していないのに次の同種の気づきが
            # stall_min_interval_turns ぶん抑制され、取りこぼしが長引く。
            self._logger.warning(
                "reflect_observation_sink raised for player_id=%s", player_id,
                exc_info=True,
            )
            return False
        self._last_reflect_turn[cap_key] = turn
        return True

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
        objective_text = self._resolve_objective_text(player_id)
        messages = self._build_messages(batch, shortlist, objective_text)
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
        # P10: 伝聞 evidence の話者についての人物 belief を必ず shortlist に載せる。
        # 話者を信じるかの判断 (設計メモ §2 ステップ 3) は話者 belief が見えないと
        # できないので、cue スコアに頼らず in_context と同格で強制する。話者名は
        # 自然文の belief text/tags に現れるので、cue トークン照合を名前で再利用する
        # (信頼を数値で持たない §4 方針。名前が belief に無ければ何も足さない)。
        # flag で明示ガードする: OFF で resume した run に、ON 時代の未 drain な
        # HEARSAY evidence が buffer 残留していても (buffer は snapshot 永続化される)
        # 話者強制を発火させない。「hearsay_enabled=False = pre-P10 と挙動一致」を
        # batch 残留物に依存せず保証する。
        speaker_names = tuple(
            sorted(
                {
                    s.strip().lower()
                    for e in batch
                    if e.source_kind == BeliefEvidenceSourceKind.HEARSAY
                    and isinstance(getattr(e, "source_speaker", None), str)
                    and (s := e.source_speaker) is not None
                    and s.strip()
                }
            )
            if self._hearsay_enabled
            else set()
        )
        if speaker_names:
            for belief in active_beliefs:
                if _shared_belief_matches_cue_tokens(
                    belief.tags, belief.text, speaker_names
                ):
                    forced_ids.add(belief.belief_id)
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

    @staticmethod
    def _build_evidence_payload_entry(evidence: BeliefEvidence) -> dict[str, Any]:
        """evidence 1 件を prompt payload の dict に変換する。

        P10 回帰修正: ``_HEARSAY_INSTRUCTION`` は「source_kind が hearsay の
        evidence には source_speaker がその話者」と LLM に約束しているが、
        payload に ``source_speaker`` が無いと話者ごとの文脈信頼判断が構造的に
        不可能になる。HEARSAY 以外は常に None なので、ノイズを避けるため
        非 None のときだけキーを載せる。
        """
        payload: dict[str, Any] = {
            "evidence_id": evidence.evidence_id,
            "source_kind": evidence.source_kind.value,
            "cue_signature": evidence.cue_signature,
            "text": evidence.text,
            "salience": evidence.salience,
            "episode_ids": list(evidence.episode_ids),
        }
        if evidence.source_speaker is not None:
            payload["source_speaker"] = evidence.source_speaker
        return payload

    def _build_messages(
        self,
        batch: tuple[BeliefEvidence, ...],
        shortlist: tuple[SemanticMemoryEntry, ...],
        objective_text: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        evidence_payload = [
            self._build_evidence_payload_entry(e) for e in batch
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
        # P4: reflect の監査対象。現在の目的が解決できたときだけ載せる
        # (reflect 節は「現在の目的が渡っているとき」を条件に判断するため)。
        if objective_text:
            user_content["現在の目的"] = objective_text
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
                elif action == _ACTION_REFLECT:
                    if not self._apply_reflect(player_id, raw):
                        continue  # 停滞でない / cap / flag OFF なら記録しない
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

    @staticmethod
    def _count_confirmation(
        evidence_ids: tuple[str, ...],
        evidence_by_id: dict[str, BeliefEvidence],
    ) -> int:
        """P3b: evidence_ids のうち CONFIRMATION 由来の件数を数える。

        batch に無い id (既に drain 済みの過去 support 等) は数えられないので
        除く。よって「今回の batch で足された CONFIRMATION 支持」の件数になる。
        """
        return sum(
            1
            for eid in evidence_ids
            if (e := evidence_by_id.get(eid)) is not None
            and e.source_kind == BeliefEvidenceSourceKind.CONFIRMATION
        )

    @staticmethod
    def _count_hearsay(
        evidence_ids: tuple[str, ...],
        evidence_by_id: dict[str, BeliefEvidence],
    ) -> int:
        """P10: evidence_ids のうち HEARSAY (伝聞) 由来の件数を数える。

        ``_count_confirmation`` と同じく batch に無い id は数えない。伝聞由来の
        支持を confidence 計算で自分の体験の半分に軽く数えるための内数。
        """
        return sum(
            1
            for eid in evidence_ids
            if (e := evidence_by_id.get(eid)) is not None
            and e.source_kind == BeliefEvidenceSourceKind.HEARSAY
        )

    def _resolve_evidence_ids(
        self,
        raw: dict[str, Any],
        evidence_by_id: dict[str, BeliefEvidence],
        batch_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        raw_ids = raw.get("evidence_ids")
        if isinstance(raw_ids, list):
            # 重複除去 + strip して順序を保つ。重複を残すと strengthen で
            # support は set 統合で 1 件しか増えないのに CONFIRMATION / HEARSAY
            # 内数 (_count_*) は重複分だけ多く数え、confidence が汚染される /
            # 内数が support 総数を超えて SemanticMemoryEntry の不変条件違反で
            # strengthen が黙って捨てられる (P3b/P10 で内数不変条件が入って以降、
            # 重複が無害でなくなった)。id 判定と採用値を strip 済みに揃える
            # (evidence_by_id のキーと文字列一致させる)。
            valid: list[str] = []
            seen: set[str] = set()
            for x in raw_ids:
                if not isinstance(x, str):
                    continue
                stripped = x.strip()
                if stripped in evidence_by_id and stripped not in seen:
                    seen.add(stripped)
                    valid.append(stripped)
            if valid:
                return tuple(valid)
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
        # P3b: founding evidence のうち CONFIRMATION 由来は confidence を半分に
        # 数える (追認は予測誤差の学びより軽い証拠)。
        confirmation_count = self._count_confirmation(evidence_ids, evidence_by_id)
        # P10: 伝聞由来も同じく半分に数える (人づては直接体験より弱い証拠)。
        hearsay_count = self._count_hearsay(evidence_ids, evidence_by_id)
        entry = SemanticMemoryEntry(
            entry_id=entry_id,
            player_id=player_id,
            text=text,
            evidence_episode_ids=tuple(sorted(set(episode_ids))),
            # founding evidence 件数を初期 confidence に反映
            # (support_evidence_ids を数えているので base 固定は不整合)。
            confidence=compute_belief_confidence(
                len(evidence_ids), 0, confirmation_count, hearsay_count
            ),
            created_at=now,
            importance_score=importance,
            tags=tuple(tags),
            belief_id=entry_id,
            status=SEMANTIC_MEMORY_STATUS_ACTIVE,
            support_evidence_ids=evidence_ids,
            confirmation_support_count=confirmation_count,
            hearsay_support_count=hearsay_count,
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
        existing_support = set(target.support_evidence_ids)
        new_support = tuple(sorted(existing_support | set(evidence_ids)))
        # P3b: 今回 **新規に** 足された support のうち CONFIRMATION 由来だけを
        # 既存カウントに加える (既に support 済みの id は二重計上しない)。
        newly_added = tuple(eid for eid in evidence_ids if eid not in existing_support)
        new_confirmation_count = (
            target.confirmation_support_count
            + self._count_confirmation(newly_added, evidence_by_id)
        )
        # P10: 今回新規に足された support のうち HEARSAY 由来だけを既存カウントに
        # 加える (既に support 済みの id は二重計上しない)。
        new_hearsay_count = (
            target.hearsay_support_count
            + self._count_hearsay(newly_added, evidence_by_id)
        )
        new_confidence = compute_belief_confidence(
            len(new_support),
            len(target.contradict_evidence_ids),
            new_confirmation_count,
            new_hearsay_count,
        )
        updated = replace(
            target,
            support_evidence_ids=new_support,
            confidence=new_confidence,
            confirmation_support_count=new_confirmation_count,
            hearsay_support_count=new_hearsay_count,
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
            # P3b/P10: 命題を言い直すだけなので support/反証/CONFIRMATION/HEARSAY
            # 内数はそのまま引き継ぐ (confidence 計算も同じ重み付けを保つ)。
            confidence=compute_belief_confidence(
                len(target.support_evidence_ids),
                len(target.contradict_evidence_ids),
                target.confirmation_support_count,
                target.hearsay_support_count,
            ),
            created_at=now,
            importance_score=target.importance_score,
            tags=target.tags,
            belief_id=target.belief_id,
            status=SEMANTIC_MEMORY_STATUS_ACTIVE,
            supersedes=target.entry_id,
            support_evidence_ids=target.support_evidence_ids,
            contradict_evidence_ids=target.contradict_evidence_ids,
            confirmation_support_count=target.confirmation_support_count,
            hearsay_support_count=target.hearsay_support_count,
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
        # P3b/P10: 反証を足すだけなので CONFIRMATION/HEARSAY 支持の内数は不変。
        # confidence 計算に渡して重み付けを保つ (渡さないと 0.5 割引が消えて
        # 再膨張する)。
        new_confidence = compute_belief_confidence(
            len(target.support_evidence_ids),
            len(new_contradict),
            target.confirmation_support_count,
            target.hearsay_support_count,
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
