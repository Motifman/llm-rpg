"""memory_recall_by_handle (Issue #526 後続 PR-D)。

# 何を解くか

PR-C で「ぼんやり覚えてる」見出し index (= AfterglowStore) を導入し、
prompt に「【さっき思い出した記憶の見出し】」section が並ぶようになった。
ただし LLM 側にはそれを能動的に展開する経路が無く、

  「見出しを並べたけど、本文を思い出す方法が無いので結局忘れたまま」

という片手落ち状態だった。本 executor は LLM が handle (= ``ep_<6 文字>``) を
渡して、その episode の本文を引き戻すツール経路を提供する。引き戻し時:

1. afterglow から entry を引く
2. episode_store から本文 (recall_text) を取り出す
3. slot に **force_insert** で再注入 (= 「もう一度鮮明に浮かんだ」状態)
4. afterglow からはその entry を取り除く (= 重複表示を防ぐ)
5. 本文を LlmCommandResultDto.message に乗せて返す

# 失敗ケース

- handle 形式違反 (``ep_`` で始まらない、prefix が空) → INVALID_ARGUMENT
- handle に該当する entry が afterglow に居ない → 成功扱いで「もう忘れた」
- 該当 episode が episode_store に居ない (= 整合性破綻) → INVALID_STATE
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.afterglow_store import (
    IAfterglowStore,
    resolve_episode_id_prefix_from_handle,
)
from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
    IEpisodicRecallSlotStore,
    RecallSlotEntry,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_RECALL_BY_HANDLE,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)


FORGOTTEN_MESSAGE = (
    "もう忘れました。その見出しはぼんやり覚えていた範囲から既に消えています。"
)


@dataclass
class EpisodicMemoryRecallByHandleToolExecutor:
    """``memory_recall_by_handle`` の executor。

    afterglow / slot / episode_store を統合し、handle 指定で本文を引き戻し
    つつ slot に再注入する。
    """

    episode_store: EpisodicEpisodeRepository
    afterglow_store: IAfterglowStore
    slot_store: IEpisodicRecallSlotStore
    slot_capacity: int
    current_tick_provider: Optional[Callable[[], Optional[int]]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.slot_capacity, int) or self.slot_capacity <= 0:
            raise ValueError("slot_capacity must be a positive int")

    def get_handlers(
        self,
    ) -> Dict[str, Callable[[ActingBeing, Dict[str, Any]], LlmCommandResultDto]]:
        return {TOOL_NAME_MEMORY_RECALL_BY_HANDLE: self._run}

    def _run(
        self,
        acting: ActingBeing,
        arguments: Dict[str, Any],
    ) -> LlmCommandResultDto:
        # 引数バリデーション。失敗時は INVALID_ARGUMENT で明示。
        handle_raw = arguments.get("handle")
        try:
            resolve_episode_id_prefix_from_handle(handle_raw or "")
        except (TypeError, ValueError) as e:
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code="INVALID_ARGUMENT",
            )

        being_id = acting.being_id

        # afterglow から entry を引く。
        entry = self.afterglow_store.find_by_handle(being_id, handle_raw)
        if entry is None:
            # 見出しが既に退去している。「失敗の質感」を success=True で返す。
            return LlmCommandResultDto(
                success=True,
                message=FORGOTTEN_MESSAGE,
            )

        # episode 本文を取り出す。get_by_being が None なら整合性破綻
        # (= afterglow に居るのに store に居ない) で INVALID_STATE。
        episode = self.episode_store.get_by_being(being_id, entry.episode_id)
        if episode is None:
            return LlmCommandResultDto(
                success=False,
                message=(
                    f"episode_id={entry.episode_id} is in afterglow but not in "
                    "episode_store; consistency violation"
                ),
                error_code="INVALID_STATE",
            )

        # slot 再注入 + afterglow から取り除く。current_tick が無ければ 0 で
        # 入れる (= ツール呼び出し直後の entered_tick の意味付けが弱まるが、
        # 機構そのものは動かす)。
        current_tick = self._resolve_current_tick()
        self.slot_store.force_insert(
            being_id,
            RecallSlotEntry(episode_id=entry.episode_id, entered_tick=current_tick),
            capacity=self.slot_capacity,
        )
        self.afterglow_store.remove(being_id, entry.episode_id)

        # 本文を message に。heading も先頭に添えて「何を引き戻したか」を
        # LLM に視認させる。
        body = episode.recall_text or "(本文なし)"
        return LlmCommandResultDto(
            success=True,
            message=f"[{entry.heading}] {body}",
        )

    def _resolve_current_tick(self) -> int:
        if self.current_tick_provider is None:
            return 0
        try:
            v = self.current_tick_provider()
        except Exception:
            return 0
        if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
            return v
        return 0


__all__ = [
    "EpisodicMemoryRecallByHandleToolExecutor",
    "FORGOTTEN_MESSAGE",
]
