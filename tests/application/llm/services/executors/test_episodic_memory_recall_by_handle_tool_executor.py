"""``EpisodicMemoryRecallByHandleToolExecutor`` の検証 (Issue #526 PR-D)。

PR-C で導入した AfterglowStore の「ぼんやり覚えてる」見出しを、LLM が handle
指定で本文に展開する経路。ツール呼出後はその episode が slot に再注入され、
afterglow からは取り除かれる「鮮明 → ぼんやり → 再び鮮明」のリハーサル
サイクルを保証する。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

# 循環 import 回避の warm-up
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.services.afterglow_store import (
    AfterglowEntry,
    AfterglowSource,
    InMemoryAfterglowStore,
    make_afterglow_handle,
)
from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
    InMemoryEpisodicRecallSlotStore,
    RecallSlotEntry,
)
from ai_rpg_world.application.llm.services.executors.episodic_memory_recall_by_handle_tool_executor import (
    EpisodicMemoryRecallByHandleToolExecutor,
    FORGOTTEN_MESSAGE,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.domain.being.service.being_attachment_resolver import (
    BeingAttachmentResolver,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import (
    EpisodeAction,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import (
    EpisodeLocation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import (
    EpisodeSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import DEFAULT_SINGLE_WORLD_ID
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


_PLAYER_ID = 7
_EPISODE_ID = "3f2a7b8c-9d0e-4f1a-aaaa-bbbb"
_HEADING = "司書の手記を読んだ"


def _setup():
    """afterglow に 1 件 / episode_store に本文を仕込んだ状態を作る。"""
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    BeingProvisioningService(repo).ensure_attached(PlayerId(_PLAYER_ID))
    being_id = resolver.resolve_being_id(
        DEFAULT_SINGLE_WORLD_ID, PlayerId(_PLAYER_ID)
    )

    episode_store = InMemorySubjectiveEpisodeStore()
    afterglow_store = InMemoryAfterglowStore()
    slot_store = InMemoryEpisodicRecallSlotStore()

    ep = SubjectiveEpisode(
        episode_id=_EPISODE_ID,
        player_id=_PLAYER_ID,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="t"),
        who=("p",),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
        recall_text="水の断片語を見つけた手応えがあった。",
        heading=_HEADING,
    )
    episode_store.put_by_being(being_id, ep)
    afterglow_store.apply_decision(
        being_id,
        (
            AfterglowEntry(
                episode_id=_EPISODE_ID,
                heading=_HEADING,
                entered_tick=10,
                source=AfterglowSource.WEAK_RECALL,
            ),
        ),
    )
    executor = EpisodicMemoryRecallByHandleToolExecutor(
        episode_store=episode_store,
        afterglow_store=afterglow_store,
        slot_store=slot_store,
        slot_capacity=4,
        being_attachment_resolver=resolver,
        default_world_id=DEFAULT_SINGLE_WORLD_ID,
        current_tick_provider=lambda: 15,
    )
    return executor, being_id, episode_store, afterglow_store, slot_store


class TestRecallByHandleSuccess:
    """正常系: 見出しが afterglow に居て、本文を引き戻して slot に再注入される。"""

    def test_returns_recall_text_with_heading_prefix(self) -> None:
        """応答 message は ``[heading] recall_text`` の形で、LLM が
        「何の見出しから何を引いたか」を視認できる。"""
        executor, _, _, _, _ = _setup()
        result = executor._run(
            _PLAYER_ID, {"handle": make_afterglow_handle(_EPISODE_ID)}
        )
        assert result.success is True
        assert _HEADING in result.message
        assert "水の断片語" in result.message

    def test_inserts_into_slot_with_current_tick(self) -> None:
        """slot に当該 episode が force_insert される (= 鮮明な記憶への格上げ)。
        entered_tick は current_tick_provider の値で打刻され、後の L 退去を起点にできる。"""
        executor, being_id, _, _, slot_store = _setup()
        executor._run(
            _PLAYER_ID, {"handle": make_afterglow_handle(_EPISODE_ID)}
        )
        ids = [e.episode_id for e in slot_store.get_slot(being_id)]
        assert _EPISODE_ID in ids
        entry = next(
            e for e in slot_store.get_slot(being_id) if e.episode_id == _EPISODE_ID
        )
        assert entry.entered_tick == 15

    def test_removes_entry_from_afterglow(self) -> None:
        """同 episode が slot と afterglow に二重に並ばないよう、afterglow
        からは取り除く (= 「鮮明な記憶 ⇄ ぼんやり」の階層を排他に保つ)。"""
        executor, being_id, _, afterglow_store, _ = _setup()
        executor._run(
            _PLAYER_ID, {"handle": make_afterglow_handle(_EPISODE_ID)}
        )
        ids = [e.episode_id for e in afterglow_store.get_index(being_id)]
        assert _EPISODE_ID not in ids


class TestRecallByHandleFailures:
    """失敗系: 形式違反 / 既に忘却 / 整合性破綻。"""

    def test_invalid_handle_format_returns_invalid_argument(self) -> None:
        """``ep_`` で始まらない handle は INVALID_ARGUMENT で弾く。
        LLM が prompt 上の handle 以外を入れたら明示的に止める意図。"""
        executor, _, _, _, _ = _setup()
        result = executor._run(_PLAYER_ID, {"handle": "xyz"})
        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"

    def test_forgotten_handle_returns_forgotten_message(self) -> None:
        """afterglow から退去済みの episode を指定された場合、success=True
        だが message は「もう忘れました」。失敗の質感を保ちつつ tool が落ちない。"""
        executor, _, _, _, _ = _setup()
        result = executor._run(
            _PLAYER_ID, {"handle": "ep_deadbeef"}
        )
        assert result.success is True
        assert result.message == FORGOTTEN_MESSAGE
