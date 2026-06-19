"""memory_recall_episodes (Issue #526 不在 2 「agent-driven 想起」の実装)。

# 何を解くか

これまでの recall は **prompt 構築時に自動で走る passive 経路** のみだった。
LLM 側に「思い出そう」と意志して過去を呼び戻す経路が無く、Issue #526 で
洗い出した「初対面の人の名前を聞いて過去の伝聞を思い出す」「『昨日何してた?』
に答える」のような agent-driven の能動想起ができなかった。

本 tool は LLM が ``about`` (= 自由文の手がかり) + ``time_range`` (= 時間範囲) を
渡し、過去 episode を能動的に取り戻すための経路。

# 設計指針

- **疎結合**: 引数に整数 ID は出さない。``about`` は自然文、``time_range`` は
  enum 文字列 (= 主観時間ラベルと対応)
- **noun_matcher の限界を許容**: ``about`` は LLM 側が書く自然文。固有名詞が
  含まれていれば cue が立つ、含まれていなければ time_range が主に働く
- **失敗の質感を許容**: 0 件なら「思い出そうとしたが何も浮かばなかった」を
  自然な response として返す (= ``LlmCommandResultDto.success`` は True のまま)
- **外部 observation は発生させない**: v0 では完全 internal。他エージェントから
  見えない (= 観測発生 hook は将来追加できる構造のまま)
- **副作用なし**: 世界状態は変えない
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.episodic_cue_rules import (
    build_situation_episodic_cues,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_RECALL_EPISODES,
)
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


DEFAULT_MAX_RESULTS = 5
MAX_RESULTS_CAP = 16

# store からの fetch 上限。time_range で post-filter する都合上、結果の上限
# (DEFAULT_MAX_RESULTS) より大きく取る必要がある (= 古い episode が大量に
# あるとき、time_range で削った後も DEFAULT_MAX_RESULTS 件を確保したい)。
# 4 倍にしているのは経験則: 「直近 4h を出したい時に、過去 7 日ぶんの 32 件
# fetch だと recent 期間がほぼ含まれない」ケースを避ける現実的バッファ。
# 完全な保証ではないが、scenario の常用 episode 数では十分。
_STORE_FETCH_OVERFETCH = MAX_RESULTS_CAP * 4  # = 64

EMPTY_RESULT_MESSAGE = "思い出そうとしたが何も浮かばなかった。"

# time_range の自然語彙 → 時間 delta マッピング (= 主観時間 v0 と対応)
#
# NOTE: 「yesterday」は **「過去 48h 以内」** で定義する (= 今日 + 昨日)。
# 「昨日だけ」のような厳密 calendar 範囲は v0 では取らない:
#   - LLM が "yesterday" を「昨日に厳密一致」の意味で使うとは限らない
#   - 「昨日のうち何時か覚えてないけど」のあいまいさを許容したい
#   - subjective_time の "今日のうち" / "昨日" の閾値とも整合 (= 4h 以上前は
#     ラベル切り替わり、24h 以上前で calendar 日跨ぎ確実)
# 厳密な前日 0:00-24:00 range が必要になったら別 enum 値を追加する。
_TIME_RANGE_DELTAS: Dict[str, Optional[timedelta]] = {
    "recent": timedelta(hours=4),
    "today": timedelta(hours=24),
    "yesterday": timedelta(hours=48),
    "this_week": timedelta(days=7),
    "any": None,
}


class _BeingNotProvisionedError(Exception):
    """Being が attach されていない / wiring 未設定で recall tool を呼んだとき。

    RuntimeError を広く catch すると BeingAttachmentResolver 内部の別の
    RuntimeError も飲み込まれて INVALID_STATE 扱いになるため、本 tool 専用
    の specific 例外を用意する。
    """


@dataclass
class EpisodicMemoryRecallToolExecutor:
    """``memory_recall_episodes`` の実装。

    ``about`` から noun_matcher 経由で cue を抽出 + ``time_range`` で時間
    範囲を絞り、 episode store から候補を取り出す。両方とも実質指定なし
    の場合は直近 K 件 (= 「ぼんやり思い出す」) を返す。
    """

    episode_store: EpisodicEpisodeRepository
    being_attachment_resolver: Optional[BeingAttachmentResolver] = None
    default_world_id: Optional[WorldId] = None
    # WorldNounMatcher (任意。注入されていない場合は cue 抽出を skip)
    noun_matcher: Optional[Any] = None
    # wall-clock の datetime を返す関数。未指定なら datetime.now(utc)
    time_provider: Optional[Callable[[], datetime]] = None

    def __post_init__(self) -> None:
        if self.being_attachment_resolver is not None and not isinstance(
            self.being_attachment_resolver, BeingAttachmentResolver
        ):
            raise TypeError(
                "being_attachment_resolver must be BeingAttachmentResolver"
            )
        if self.default_world_id is not None and not isinstance(
            self.default_world_id, WorldId
        ):
            raise TypeError("default_world_id must be WorldId")
        if self.time_provider is not None and not callable(self.time_provider):
            raise TypeError("time_provider must be callable or None")

    def get_handlers(
        self,
    ) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        return {TOOL_NAME_MEMORY_RECALL_EPISODES: self._run_recall_episodes}

    # ──────────────────────────────────────────────────────────────
    # main entry point
    # ──────────────────────────────────────────────────────────────

    def _run_recall_episodes(
        self,
        player_id: int,
        arguments: Dict[str, Any],
    ) -> LlmCommandResultDto:
        about_raw = arguments.get("about", "")
        about = str(about_raw).strip() if isinstance(about_raw, str) else ""

        time_range_raw = arguments.get("time_range")
        time_range: Optional[str] = None
        if isinstance(time_range_raw, str):
            normalized = time_range_raw.strip().lower()
            if normalized in _TIME_RANGE_DELTAS:
                time_range = normalized

        try:
            being_id = self._require_being_id(player_id)
        except _BeingNotProvisionedError as exc:
            return LlmCommandResultDto(
                success=False,
                message=str(exc),
                error_code="INVALID_STATE",
            )

        now = self._resolve_now()
        min_occurred_at = self._time_range_to_min_occurred_at(time_range, now)

        # about から cue を立てる (= noun_matcher が wire されていれば)
        cues = self._extract_cues_from_about(about)

        episodes = self._fetch_episodes(
            being_id=being_id,
            cues=cues,
            min_occurred_at=min_occurred_at,
        )

        if not episodes:
            return LlmCommandResultDto(
                success=True,
                message=EMPTY_RESULT_MESSAGE,
            )

        lines = [
            ep.recall_text for ep in episodes[:DEFAULT_MAX_RESULTS] if ep.recall_text
        ]
        if not lines:
            # episodes はあるが recall_text が無い (= 異常系)
            return LlmCommandResultDto(
                success=True,
                message=EMPTY_RESULT_MESSAGE,
            )
        return LlmCommandResultDto(
            success=True,
            message="\n".join(f"- {line}" for line in lines),
        )

    # ──────────────────────────────────────────────────────────────
    # helpers
    # ──────────────────────────────────────────────────────────────

    def _require_being_id(self, player_id: int) -> BeingId:
        """Resolver+WorldId+Being が揃わなければ ``_BeingNotProvisionedError``。"""
        if self.being_attachment_resolver is None or self.default_world_id is None:
            raise _BeingNotProvisionedError(
                "EpisodicMemoryRecallToolExecutor requires being_attachment_resolver "
                "and default_world_id"
            )
        being_id = self.being_attachment_resolver.resolve_being_id(
            self.default_world_id, PlayerId(player_id)
        )
        if being_id is None:
            raise _BeingNotProvisionedError(
                f"Being not provisioned for player_id={player_id} in world="
                f"{self.default_world_id.value}"
            )
        return being_id

    def _resolve_now(self) -> datetime:
        if self.time_provider is None:
            return datetime.now(timezone.utc)
        return self.time_provider()

    def _time_range_to_min_occurred_at(
        self,
        time_range: Optional[str],
        now: datetime,
    ) -> Optional[datetime]:
        """time_range 文字列 → ``min_occurred_at`` (= now - delta)。

        list_recent_by_being / list_by_cue_by_being の ``min_occurred_at``
        は「これより**新しい** episode のみ返す」**下限** semantics だが、
        ここでは「この時間範囲内 = now - delta より新しい」の絞り込みに
        使う。None / "any" / 未知の値はフィルタなし。
        """
        if time_range is None:
            return None
        delta = _TIME_RANGE_DELTAS.get(time_range)
        if delta is None:
            return None
        return now - delta

    def _extract_cues_from_about(self, about: str) -> List[EpisodicCue]:
        """``about`` に noun_matcher を当てて cue を立てる。

        noun_matcher 未注入 or about が空文字なら空 list で返す。
        """
        if not about or self.noun_matcher is None:
            return []
        # build_situation_episodic_cues 経由で cue を抽出する。runtime / 観測
        # 構造化は渡さず、``observation_prose=about`` を使って noun_matcher に
        # 通すだけにする (= 「about を観測 prose として扱う」)。
        cues = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            observation_prose=about,
            noun_matcher=self.noun_matcher,
        )
        return list(cues)

    def _fetch_episodes(
        self,
        *,
        being_id: BeingId,
        cues: List[EpisodicCue],
        min_occurred_at: Optional[datetime],
    ) -> List[SubjectiveEpisode]:
        """cue があれば各 cue で list_by_cue + 重複除去、無ければ list_recent。

        list_by_cue / list_recent の ``min_occurred_at`` パラメタは
        「これより古い episode のみ返す」(= sliding window 範囲外フィルタ
        用に PR5 R1 で追加された) semantics で、本 tool で欲しい
        「time_range 内 = より新しい」とは方向が逆。よって store の
        ``min_occurred_at`` には渡さず、取得後に Python 側で filter する。
        """
        candidates: Dict[str, SubjectiveEpisode] = {}
        if cues:
            for cue in cues:
                rows = self.episode_store.list_by_cue_by_being(
                    being_id,
                    cue,
                    _STORE_FETCH_OVERFETCH,
                )
                for ep in rows:
                    candidates[ep.episode_id] = ep
        else:
            rows = self.episode_store.list_recent_by_being(
                being_id,
                _STORE_FETCH_OVERFETCH,
            )
            for ep in rows:
                candidates[ep.episode_id] = ep

        episodes = list(candidates.values())

        if min_occurred_at is not None:
            min_norm = _normalize_to_utc(min_occurred_at)
            episodes = [
                ep
                for ep in episodes
                if _normalize_to_utc(ep.occurred_at) >= min_norm
            ]

        # occurred_at 降順 (= 新しい順)
        episodes.sort(
            key=lambda ep: _normalize_to_utc(ep.occurred_at),
            reverse=True,
        )
        return episodes


def _normalize_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


__all__ = [
    "EpisodicMemoryRecallToolExecutor",
    "DEFAULT_MAX_RESULTS",
    "MAX_RESULTS_CAP",
    "EMPTY_RESULT_MESSAGE",
]
