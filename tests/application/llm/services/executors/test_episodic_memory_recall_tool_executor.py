"""``EpisodicMemoryRecallToolExecutor`` の検証 (Issue #526 不在 2)。

エージェントが「思い出そう」と意志して過去 episode を能動的に呼び戻す
``memory_recall_episodes`` tool の executor 単体テスト。
"""

from __future__ import annotations

# 循環 import 回避の warm-up (= 既存テストと同じパターン)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)

from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.application.llm.services.executors.episodic_memory_recall_tool_executor import (
    DEFAULT_MAX_RESULTS,
    EMPTY_RESULT_MESSAGE,
    EpisodicMemoryRecallToolExecutor,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.world_noun_matcher import (
    WorldNounMatcherBuilder,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_RECALL_EPISODES,
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
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import (
    EpisodicCue,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import (
    DEFAULT_SINGLE_WORLD_ID,
)
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


_NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
_PLAYER_ID_INT = 7


def _make_being():
    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    BeingProvisioningService(repo).ensure_attached(PlayerId(_PLAYER_ID_INT))
    return resolver, DEFAULT_SINGLE_WORLD_ID


def _episode(
    *,
    episode_id: str,
    occurred_at: datetime,
    spot_id: int = 1,
    what: str = "閲覧室で覚書を読んだ",
    recall_text: str = "QUALITY_RECALL: 閲覧室で覚書を読んだ",
    cues: Optional[tuple] = None,
) -> SubjectiveEpisode:
    if cues is None:
        cues = (
            EpisodicCue(
                axis="place_spot",
                value=str(spot_id),
                source=EpisodicCueSource.RUNTIME_CONTEXT,
            ),
        )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=_PLAYER_ID_INT,
        occurred_at=occurred_at,
        game_time_label=None,
        source=EpisodeSource(event_ids=(f"evt-{episode_id}",)),
        location=EpisodeLocation(spot_id=spot_id),
        action=EpisodeAction(tool_name="travel_to"),
        who=("player_lin",),
        what=what,
        why=None,
        observed=what,
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=cues,
        recall_text=recall_text,
    )


def _build_matcher():
    builder = WorldNounMatcherBuilder()
    builder.add_spot("閲覧室", spot_id=1)
    builder.add_spot("書架 A", spot_id=2)
    builder.add_character("カイト", player_id=99)
    return builder.build()


def _build_executor(
    store: InMemorySubjectiveEpisodeStore,
    *,
    with_matcher: bool = True,
) -> EpisodicMemoryRecallToolExecutor:
    resolver, world_id = _make_being()
    return EpisodicMemoryRecallToolExecutor(
        episode_store=store,
        being_attachment_resolver=resolver,
        default_world_id=world_id,
        noun_matcher=_build_matcher() if with_matcher else None,
        time_provider=lambda: _NOW,
    )


class TestHandlerRegistration:
    """tool name → handler の登録挙動。"""

    def test_get_handlers_returns_memory_recall_episodes(self) -> None:
        """``get_handlers`` が ``memory_recall_episodes`` のキーで handler を返す。"""
        store = InMemorySubjectiveEpisodeStore()
        executor = _build_executor(store)
        handlers = executor.get_handlers()
        assert TOOL_NAME_MEMORY_RECALL_EPISODES in handlers


class TestEmptyResult:
    """0 件のときの「思い出そうとしたが何も浮かばなかった」を返す経路。"""

    def test_empty_store_returns_empty_message(self) -> None:
        """episode が無いときは ``EMPTY_RESULT_MESSAGE`` を返す (success=True)。"""
        store = InMemorySubjectiveEpisodeStore()
        executor = _build_executor(store)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "昨日のこと"})
        assert result.success is True
        assert result.message == EMPTY_RESULT_MESSAGE

    def test_about_no_match_no_time_match_returns_empty(self) -> None:
        """about の cue がマッチせず、time_range で絞った結果も 0 件なら empty message。"""
        store = InMemorySubjectiveEpisodeStore()
        resolver, world_id = _make_being()
        being = resolver.resolve_being_id(world_id, PlayerId(_PLAYER_ID_INT))
        assert being is not None
        # 1 週間以上前の episode (= today / yesterday には引っかからない)
        store.put_by_being(being, _episode(
            episode_id="too-old",
            occurred_at=_NOW - timedelta(days=10),
        ))
        executor = _build_executor(store)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "謎の場所", "time_range": "yesterday"})
        assert result.success is True
        assert result.message == EMPTY_RESULT_MESSAGE


class TestAboutCueMatching:
    """about に noun_matcher を当てて cue が立つ経路。"""

    def test_about_with_known_spot_name_recalls_matching_episode(self) -> None:
        """about に「閲覧室」が含まれると、閲覧室の過去 episode が引かれる。"""
        store = InMemorySubjectiveEpisodeStore()
        resolver, world_id = _make_being()
        being = resolver.resolve_being_id(world_id, PlayerId(_PLAYER_ID_INT))
        assert being is not None
        store.put_by_being(being, _episode(
            episode_id="reading-room",
            occurred_at=_NOW - timedelta(hours=18),
            spot_id=1,
            recall_text="昨日の昼、閲覧室で覚書を読んだ",
        ))
        store.put_by_being(being, _episode(
            episode_id="shelf-a",
            occurred_at=_NOW - timedelta(hours=18),
            spot_id=2,
            recall_text="書架Aで断片語を見つけた",
        ))
        executor = _build_executor(store)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "閲覧室で何があったか"})
        assert result.success is True
        assert "閲覧室" in result.message
        # 「書架A」を about に含めていないので spot_id=2 episode は出ない
        assert "書架A" not in result.message

    def test_no_noun_in_about_falls_back_to_temporal(self) -> None:
        """about に固有名詞が無いとき、time_range だけで episode を引く (= temporal fallback)。"""
        store = InMemorySubjectiveEpisodeStore()
        resolver, world_id = _make_being()
        being = resolver.resolve_being_id(world_id, PlayerId(_PLAYER_ID_INT))
        assert being is not None
        # yesterday の範囲内
        store.put_by_being(being, _episode(
            episode_id="yesterday-ep",
            occurred_at=_NOW - timedelta(hours=18),
            recall_text="昨日の出来事",
        ))
        executor = _build_executor(store)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(
            _PLAYER_ID_INT,
            {"about": "俺昨日何したっけ?", "time_range": "yesterday"},
        )
        assert result.success is True
        assert "昨日の出来事" in result.message


class TestTimeRange:
    """time_range の絞り込み挙動。"""

    def test_today_excludes_yesterday(self) -> None:
        """time_range='today' は 24h 以内の episode のみ返す。"""
        store = InMemorySubjectiveEpisodeStore()
        resolver, world_id = _make_being()
        being = resolver.resolve_being_id(world_id, PlayerId(_PLAYER_ID_INT))
        assert being is not None
        store.put_by_being(being, _episode(
            episode_id="recent",
            occurred_at=_NOW - timedelta(hours=2),
            recall_text="今日の出来事",
        ))
        store.put_by_being(being, _episode(
            episode_id="old",
            occurred_at=_NOW - timedelta(hours=40),
            recall_text="昨日のさらに前",
        ))
        executor = _build_executor(store)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "何か思い出したい", "time_range": "today"})
        assert result.success is True
        assert "今日の出来事" in result.message
        assert "昨日のさらに前" not in result.message

    def test_any_does_not_filter(self) -> None:
        """time_range='any' は時間で絞らない。"""
        store = InMemorySubjectiveEpisodeStore()
        resolver, world_id = _make_being()
        being = resolver.resolve_being_id(world_id, PlayerId(_PLAYER_ID_INT))
        assert being is not None
        store.put_by_being(being, _episode(
            episode_id="ancient",
            occurred_at=_NOW - timedelta(days=30),
            recall_text="ずっと昔の出来事",
        ))
        executor = _build_executor(store)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "全部", "time_range": "any"})
        assert result.success is True
        assert "ずっと昔" in result.message

    def test_unknown_time_range_treated_as_no_filter(self) -> None:
        """未知の time_range 値は無視 (= 絞らない、エラーにしない)。"""
        store = InMemorySubjectiveEpisodeStore()
        resolver, world_id = _make_being()
        being = resolver.resolve_being_id(world_id, PlayerId(_PLAYER_ID_INT))
        assert being is not None
        store.put_by_being(being, _episode(
            episode_id="recent",
            occurred_at=_NOW - timedelta(hours=2),
            recall_text="出来事",
        ))
        executor = _build_executor(store)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "何か", "time_range": "moon_age"})
        # 未知値は無視され、絞らない default 動作になる
        assert result.success is True
        assert "出来事" in result.message


class TestNounMatcherUnavailable:
    """noun_matcher 未注入時の挙動。"""

    def test_no_matcher_falls_back_to_temporal_recent(self) -> None:
        """matcher が None でも time_range / 直近 K 件で episode は引ける。"""
        store = InMemorySubjectiveEpisodeStore()
        resolver, world_id = _make_being()
        being = resolver.resolve_being_id(world_id, PlayerId(_PLAYER_ID_INT))
        assert being is not None
        store.put_by_being(being, _episode(
            episode_id="recent",
            occurred_at=_NOW - timedelta(hours=2),
            recall_text="直近のこと",
        ))
        executor = _build_executor(store, with_matcher=False)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "閲覧室で何があったか"})
        # matcher 無いので閲覧室 cue は立たないが、直近 K 件で recall
        assert result.success is True
        assert "直近のこと" in result.message


class TestBeingNotProvisioned:
    """Being 未 provisioning なら INVALID_STATE error。"""

    def test_returns_invalid_state_when_being_not_resolved(self) -> None:
        """resolver+world_id 注入済でも Being が attach されてなければ INVALID_STATE。"""
        store = InMemorySubjectiveEpisodeStore()
        repo = InMemoryBeingRepository()
        resolver = BeingAttachmentResolver(repo)
        # provision しない
        executor = EpisodicMemoryRecallToolExecutor(
            episode_store=store,
            being_attachment_resolver=resolver,
            default_world_id=DEFAULT_SINGLE_WORLD_ID,
            noun_matcher=None,
            time_provider=lambda: _NOW,
        )
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "何か"})
        assert result.success is False
        assert result.error_code == "INVALID_STATE"


class TestResultLimit:
    """結果上限の挙動。"""

    def test_caps_at_default_max_results(self) -> None:
        """大量の episode があっても返るのは ``DEFAULT_MAX_RESULTS`` 件まで。"""
        store = InMemorySubjectiveEpisodeStore()
        resolver, world_id = _make_being()
        being = resolver.resolve_being_id(world_id, PlayerId(_PLAYER_ID_INT))
        assert being is not None
        for i in range(DEFAULT_MAX_RESULTS + 5):
            store.put_by_being(being, _episode(
                episode_id=f"ep-{i}",
                occurred_at=_NOW - timedelta(minutes=i),
                recall_text=f"recall-{i}",
            ))
        executor = _build_executor(store, with_matcher=False)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "全部"})
        assert result.success is True
        lines = [ln for ln in result.message.splitlines() if ln.startswith("- ")]
        assert len(lines) == DEFAULT_MAX_RESULTS


class TestNoIdLeakInOutput:
    """ID 露出禁止原則の検証 — message に整数 ID が漏れない。"""

    def test_message_contains_no_internal_ids(self) -> None:
        """recall_text のみで構成され、内部の player_id / spot_id 数値は含まれない。"""
        store = InMemorySubjectiveEpisodeStore()
        resolver, world_id = _make_being()
        being = resolver.resolve_being_id(world_id, PlayerId(_PLAYER_ID_INT))
        assert being is not None
        store.put_by_being(being, _episode(
            episode_id="ep",
            occurred_at=_NOW - timedelta(hours=2),
            spot_id=42,
            recall_text="閲覧室で覚書を読んだ",  # ID なし
        ))
        executor = _build_executor(store, with_matcher=False)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "閲覧室"})
        assert result.success is True
        # 内部 ID の文字列形は出ない
        assert "spot_graph_player" not in result.message
        assert "world_object_" not in result.message
        assert "item_instance_" not in result.message
        assert f"player_id={_PLAYER_ID_INT}" not in result.message
        # spot_id=42 という ID も出ないこと (`recall_text="閲覧室で覚書を読んだ"`
        # に含まれない限り出てはいけない)
        assert "42" not in result.message

    def test_episode_id_not_leaked_when_episode_id_is_numeric(self) -> None:
        """episode_id が数字でも、result 出力は recall_text のみで構成される。"""
        store = InMemorySubjectiveEpisodeStore()
        resolver, world_id = _make_being()
        being = resolver.resolve_being_id(world_id, PlayerId(_PLAYER_ID_INT))
        assert being is not None
        store.put_by_being(being, _episode(
            episode_id="12345-numeric-uuid",
            occurred_at=_NOW - timedelta(hours=2),
            spot_id=42,
            recall_text="昨日の出来事の説明",
        ))
        executor = _build_executor(store, with_matcher=False)
        handler = executor.get_handlers()[TOOL_NAME_MEMORY_RECALL_EPISODES]
        result = handler(_PLAYER_ID_INT, {"about": "何か"})
        assert result.success is True
        assert "12345" not in result.message
        assert "numeric-uuid" not in result.message
        assert "昨日の出来事の説明" in result.message
