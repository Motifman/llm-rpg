"""受動想起を一定ターンごとにまとめ、現在文脈から再解釈する協調サービス。"""

from __future__ import annotations

import logging
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.application.llm.contracts.episodic_memory import SubjectiveEpisode
from ai_rpg_world.application.llm.contracts.episodic_reinterpretation import (
    EpisodicRecallObservation,
    EpisodicReinterpretationEntry,
    IEpisodicRecallBufferStore,
    IEpisodicReinterpretationCompletionPort,
    IEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

DEFAULT_REINTERPRETATION_TURN_INTERVAL = 10
DEFAULT_REINTERPRETATION_BATCH_SIZE = 8
DEFAULT_REINTERPRETATION_MAX_CONTEXTS_PER_EPISODE = 3
MAX_REINTERPRETATION_FIELD_CHARS = 700
MAX_RECALL_TEXT_FIELD_CHARS = 700

_SYSTEM_REINTERPRETATION_JSON = """あなたは RPG エージェントの「主観的なエピソード記憶」を、いまこの瞬間の状況に置き直して再解釈する助手です。

【入力の意味】
- episode: 過去にエージェント自身が体験し、そのとき注意を向けた光景だけが言語化された記憶。observed / source / cues / 場所ID / 人物ID / 成否 / 実際の出来事は不変の事実。
- latest_active_recall_text: 直前まで保持されていた一人称の回想テキスト（あれば）。
- recall_contexts: その記憶を思い出した瞬間の「いま」の知覚。
  - current_state: 今そこにある状況
  - recent_events: 直近に起きた出来事
  - persona: 本人の現在の性格・心情
  - situation_cues: 今の場所や対象に紐づく手がかり

【再解釈の構え】
過去 episode と recall_contexts を、頭の中で**並べて**読み直してください。これは差分を機械的に探す作業ではありません。人間の記憶がそうであるように、
- 同じ場所に再び立ち、当時のまま変わらない要素を見て懐かしさや確信が湧くこともあれば、
- 当時注意を向けていた何かが今は失われていたり、違って見えたりすることに、自然と心が引っかかることもあります。
そうした感覚が「いまの本人」に実際に湧いたと言える場合にだけ、その違和感や懐かしさを current_recall_text / current_interpretation に自然に織り込んでください。何も湧かないなら、現在の意味づけだけを素直に書いて構いません。差分を無理に作ろうとしないでください。

【出力】
JSON オブジェクトのみ（説明文・コードフェンス禁止）。キーは episode_updates のみ。
episode_updates は { episode_id, current_interpretation, current_recall_text } を持つ配列。

- current_interpretation: いまの状況から見たこの記憶の意味づけ。日本語 1〜3 文。
- current_recall_text: キャラクター本人の一人称による回想。TRPG リプレイ風で、当時の身体感覚・感情・見立てに、いまこの場で再び浮かんだ含みを重ねる。日本語 250〜450 字（目安 320〜420 字、最低 5 文）。短い要約で終えず、十分にふくらませてください。

【厳守】
- observed / source / cues / 場所ID / 人物ID / 成否 / 実際の出来事は絶対に改変しない。
- 入力に無い人物・場所・アイテム・結果・動機・会話を創作しない。
- recall_contexts に明示されていない「いまの様子」を勝手に作らない（書かれていない物の有無を断定しない）。"""


def _truncate(raw: str, *, max_chars: int) -> str:
    text = raw.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _normalize_llm_str(raw: Any, *, max_chars: int) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    return _truncate(text, max_chars=max_chars)


@dataclass(frozen=True)
class _EpisodeBatchItem:
    episode: SubjectiveEpisode
    recalls: tuple[EpisodicRecallObservation, ...]
    active_recall_text: str | None


class EpisodicReinterpretationCoordinator:
    """ターン後に pending recall をまとめて LLM 再解釈へ送る。"""

    def __init__(
        self,
        *,
        episode_store: IEpisodicEpisodeStore,
        recall_buffer_store: IEpisodicRecallBufferStore,
        journal_store: IEpisodicReinterpretationJournalStore,
        completion: IEpisodicReinterpretationCompletionPort | None,
        turn_interval: int = DEFAULT_REINTERPRETATION_TURN_INTERVAL,
        batch_size: int = DEFAULT_REINTERPRETATION_BATCH_SIZE,
        max_contexts_per_episode: int = DEFAULT_REINTERPRETATION_MAX_CONTEXTS_PER_EPISODE,
    ) -> None:
        if not isinstance(episode_store, IEpisodicEpisodeStore):
            raise TypeError("episode_store must be IEpisodicEpisodeStore")
        if not isinstance(recall_buffer_store, IEpisodicRecallBufferStore):
            raise TypeError("recall_buffer_store must be IEpisodicRecallBufferStore")
        if not isinstance(journal_store, IEpisodicReinterpretationJournalStore):
            raise TypeError("journal_store must be IEpisodicReinterpretationJournalStore")
        if completion is not None and not isinstance(
            completion, IEpisodicReinterpretationCompletionPort
        ):
            raise TypeError(
                "completion must be IEpisodicReinterpretationCompletionPort or None"
            )
        if turn_interval < 1:
            raise ValueError("turn_interval must be positive")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if max_contexts_per_episode < 1:
            raise ValueError("max_contexts_per_episode must be positive")
        self._episode_store = episode_store
        self._recall_buffer_store = recall_buffer_store
        self._journal_store = journal_store
        self._completion = completion
        self._turn_interval = turn_interval
        self._batch_size = batch_size
        self._max_contexts_per_episode = max_contexts_per_episode
        self._turn_counts: dict[int, int] = defaultdict(int)
        self._logger = logging.getLogger(self.__class__.__name__)

    def current_turn_index(self, player_id: PlayerId) -> int:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        return self._turn_counts.get(player_id.value, 0)

    def after_turn_completed(self, player_id: PlayerId) -> None:
        """1 ターン完了後に呼び、interval 到達時だけ pending batch を処理する。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        pid = player_id.value
        self._turn_counts[pid] += 1
        if self._completion is None:
            return
        if self._turn_counts[pid] % self._turn_interval != 0:
            return
        try:
            self.flush_player(player_id)
        except Exception as e:
            self._logger.warning(
                "Episodic reinterpretation sidecar failed after turn; keeping game turn successful: %s",
                e,
                exc_info=True,
            )

    def flush_player(self, player_id: PlayerId) -> int:
        """pending recall を 1 batch 処理する。処理済みにした recall 観測数を返す。"""
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if self._completion is None:
            return 0
        batch = self._recall_buffer_store.peek_batch(
            player_id.value,
            batch_size=self._batch_size,
            max_contexts_per_episode=self._max_contexts_per_episode,
        )
        if not batch:
            return 0
        items = self._build_episode_items(player_id.value, batch)
        if not items:
            self._recall_buffer_store.mark_processed(
                player_id.value,
                tuple(row.recall_id for row in batch),
            )
            return 0
        messages = self._build_messages(items)
        try:
            raw_obj = self._completion.complete_episodic_reinterpretation_json(messages)
        except LlmApiCallException as e:
            self._logger.warning(
                "Episodic reinterpretation LLM failed (%s); pending recalls kept",
                getattr(e, "error_code", "LLM_ERROR"),
            )
            return 0
        except Exception as e:
            self._logger.warning(
                "Episodic reinterpretation failed; pending recalls kept: %s",
                e,
            )
            return 0
        processed_ids = self._apply_updates(player_id.value, items, raw_obj)
        if processed_ids:
            self._recall_buffer_store.mark_processed(player_id.value, processed_ids)
        return len(processed_ids)

    def _build_episode_items(
        self,
        player_id: int,
        batch: tuple[EpisodicRecallObservation, ...],
    ) -> tuple[_EpisodeBatchItem, ...]:
        grouped: dict[str, list[EpisodicRecallObservation]] = defaultdict(list)
        for row in batch:
            grouped[row.episode_id].append(row)
        items: list[_EpisodeBatchItem] = []
        for episode_id, recalls in grouped.items():
            ep = self._episode_store.get(player_id, episode_id)
            if ep is None:
                continue
            active = self._journal_store.get_active(player_id, episode_id)
            items.append(
                _EpisodeBatchItem(
                    episode=ep,
                    recalls=tuple(recalls),
                    active_recall_text=active.current_recall_text if active is not None else None,
                )
            )
        return tuple(items)

    def _build_messages(self, items: tuple[_EpisodeBatchItem, ...]) -> list[dict[str, Any]]:
        payload = []
        for item in items:
            ep = item.episode
            payload.append(
                {
                    "episode": {
                        "episode_id": ep.episode_id,
                        "what": ep.what,
                        "observed": ep.observed,
                        "expected": ep.expected,
                        "outcome": ep.outcome,
                        "prediction_error": ep.prediction_error,
                        "felt": ep.felt,
                        "interpreted": ep.interpreted,
                        "recall_text": ep.recall_text,
                        "cues": [c.to_canonical() for c in ep.cues],
                    },
                    "latest_active_recall_text": item.active_recall_text,
                    "recall_contexts": [
                        {
                            "recall_id": r.recall_id,
                            "turn_index": r.turn_index,
                            "source_axes": list(r.source_axes),
                            "current_state": r.current_state_snapshot,
                            "recent_events": r.recent_events_snapshot,
                            "persona": r.persona_snapshot,
                            "situation_cues": list(r.situation_cues),
                        }
                        for r in item.recalls
                    ],
                }
            )
        return [
            {"role": "system", "content": _SYSTEM_REINTERPRETATION_JSON},
            {
                "role": "user",
                "content": (
                    "以下の episode_updates を JSON だけで返してください。\n"
                    f"{json.dumps(payload, ensure_ascii=False)}"
                ),
            },
        ]

    def _apply_updates(
        self,
        player_id: int,
        items: tuple[_EpisodeBatchItem, ...],
        raw_obj: dict[str, Any],
    ) -> tuple[str, ...]:
        if not isinstance(raw_obj, dict):
            return ()
        updates = raw_obj.get("episode_updates")
        if not isinstance(updates, list):
            return ()
        by_episode = {item.episode.episode_id: item for item in items}
        processed_recall_ids: list[str] = []
        now = datetime.now(timezone.utc)
        for raw in updates:
            if not isinstance(raw, dict):
                continue
            episode_id_raw = raw.get("episode_id")
            if not isinstance(episode_id_raw, str):
                continue
            episode_id = episode_id_raw.strip()
            item = by_episode.get(episode_id)
            if item is None:
                continue
            interp = _normalize_llm_str(
                raw.get("current_interpretation"),
                max_chars=MAX_REINTERPRETATION_FIELD_CHARS,
            )
            recall = _normalize_llm_str(
                raw.get("current_recall_text"),
                max_chars=MAX_RECALL_TEXT_FIELD_CHARS,
            )
            if interp is None or recall is None:
                continue
            source_recall_ids = tuple(r.recall_id for r in item.recalls)
            latest_turn = max((r.turn_index for r in item.recalls), default=0)
            entry = EpisodicReinterpretationEntry(
                entry_id=f"reinterpret-{uuid4().hex}",
                player_id=player_id,
                episode_id=episode_id,
                created_at=now,
                turn_index=latest_turn,
                current_interpretation=interp,
                current_recall_text=recall,
                source_recall_ids=source_recall_ids,
            )
            self._journal_store.put_active(entry)
            processed_recall_ids.extend(source_recall_ids)
        return tuple(processed_recall_ids)


__all__ = [
    "DEFAULT_REINTERPRETATION_BATCH_SIZE",
    "DEFAULT_REINTERPRETATION_MAX_CONTEXTS_PER_EPISODE",
    "DEFAULT_REINTERPRETATION_TURN_INTERVAL",
    "EpisodicReinterpretationCoordinator",
]
