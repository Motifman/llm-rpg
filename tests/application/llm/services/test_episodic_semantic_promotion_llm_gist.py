"""``EpisodicSemanticClusterPromotionService`` の LLM gist 経路テスト
(Phase 1b)。

- ``gist_service`` 未注入なら従来の決定論 gist (concat) を使う
- ``gist_service`` 注入 + 成功なら LLM 抽象化を使い、importance_score / tags も
  ``SemanticMemoryEntry`` に乗る
- LLM 失敗時は決定論 gist にフォールバック (silent failure 防止のため
  warning ログを出す)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Tuple
from uuid import uuid4

import pytest

from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion import (
    EpisodicSemanticClusterPromotionService,
)
from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
    InMemoryMemoryLinkStore,
)
from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
    InMemorySemanticMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.semantic_gist_service import (
    SemanticGistResult,
)


# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────


def _make_episode(
    *,
    episode_id: str,
    player_id: int = 1,
    occurred_at_minute: int = 0,
    recall_text: str = "ある記憶",
    recall_count: int = 5,
    interpreted: str | None = None,
) -> SubjectiveEpisode:
    cue = EpisodicCue(
        axis="place_spot", value="3", source=EpisodicCueSource.RUNTIME_CONTEXT
    )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=datetime(2026, 6, 1, 12, occurred_at_minute, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(spot_id=3),
        action=EpisodeAction(tool_name="x"),
        who=(),
        what=f"event {episode_id}",
        why=None,
        observed="観測本文",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=interpreted,
        cues=(cue,),
        recall_text=recall_text,
        recall_count=recall_count,
    )


def _strong_link(player_id: int, a: str, b: str) -> MemoryLink:
    now = datetime.now(timezone.utc)
    na, nb = (a, b) if a < b else (b, a)
    return MemoryLink(
        link_id=f"memlink-{uuid4().hex}",
        player_id=player_id,
        episode_id_a=na,
        episode_id_b=nb,
        link_type=MemoryLinkType.CO_RECALL,
        strength=0.9,
        co_activation_count=1,
        created_at=now,
        last_activated_at=now,
        decay_rate=0.001,
    )


@dataclass
class _StubGistService:
    """``SemanticGistService.generate`` 相当を stub する。"""

    result: SemanticGistResult | None = None
    exc: Exception | None = None

    def generate(self, **kwargs) -> SemanticGistResult:
        if self.exc is not None:
            raise self.exc
        assert self.result is not None
        return self.result


def _build_cluster(
    *,
    gist_service=None,
    persona_resolver=None,
):
    """3 episode の強リンククラスタを用意した promotion service を作る。

    Phase 3 Step 3b-3 で semantic は being_id 経路必須となったため、
    ``SemanticBeingTestSetup`` を返して呼出側が ``setup.list_entries(1)`` で
    結果を読めるようにする。
    """
    from tests.application.llm._semantic_being_test_helpers import (
        make_semantic_being_setup,
    )

    episode_store = InMemorySubjectiveEpisodeStore()
    link_store = InMemoryMemoryLinkStore()
    setup = make_semantic_being_setup()
    being_id = setup.provision(1)

    for i, eid in enumerate(["x", "y", "z"]):
        ep = _make_episode(
            episode_id=eid,
            occurred_at_minute=i,
            recall_text=f"記憶{i}",
            recall_count=5,
            interpreted=f"主観文{i}",
        )
        episode_store.put(ep)
    # Phase 3 Step 3c-2: link 走査も being_id 経路で読まれるため同じ being_id で書く
    link_store.upsert_link_by_being(being_id, _strong_link(1, "x", "y"))
    link_store.upsert_link_by_being(being_id, _strong_link(1, "y", "z"))
    link_store.upsert_link_by_being(being_id, _strong_link(1, "x", "z"))

    svc = EpisodicSemanticClusterPromotionService(
        episode_store=episode_store,
        link_store=link_store,
        semantic_store=setup.semantic_store,
        promotion_frontier=None,  # full scan
        gist_service=gist_service,
        persona_resolver=persona_resolver,
        being_attachment_resolver=setup.resolver,
        default_world_id=setup.world_id,
    )
    return svc, setup


# ──────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────


class TestEpisodicSemanticClusterPromotionLlmGist:
    """LLM gist 経路の有無で挙動が分岐する。"""

    def test_gist_service_未注入なら_決定論_gist_を_使う(self) -> None:
        """default の挙動: text に concat、importance=5, tags=()。"""
        svc, sem_store = _build_cluster(gist_service=None)
        svc.on_after_tool_turn(player_id=1)

        entries = sem_store.list_entries(1)
        assert len(entries) == 1
        entry = entries[0]
        # 決定論 gist は interpreted を concat する
        assert "主観文0" in entry.text and "主観文1" in entry.text
        assert entry.importance_score == 5  # default
        assert entry.tags == ()  # default

    def test_gist_service_成功なら_LLM_text_と_importance_と_tags_が乗る(self) -> None:
        """LLM 経路が生きていれば SemanticMemoryEntry に importance / tags が反映される。"""
        stub = _StubGistService(
            result=SemanticGistResult(
                gist_text="タカシは信頼できる",
                importance_score=8,
                tags=("タカシ", "信頼"),
            )
        )
        svc, sem_store = _build_cluster(
            gist_service=stub,
            persona_resolver=lambda pid: ("ハル", "慎重で寡黙"),
        )
        svc.on_after_tool_turn(player_id=1)

        entries = sem_store.list_entries(1)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.text == "タカシは信頼できる"
        assert entry.importance_score == 8
        assert entry.tags == ("タカシ", "信頼")

    def test_gist_service_が_例外なら_決定論_gist_に_fallback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """LLM 失敗時 (API 例外 / ValueError) は決定論 gist に縮退し warning を出す。"""
        stub = _StubGistService(
            exc=LlmApiCallException("simulated", error_code="LLM_API_CALL_FAILED")
        )
        svc, sem_store = _build_cluster(gist_service=stub)
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.episodic_semantic_cluster_promotion",
        ):
            svc.on_after_tool_turn(player_id=1)

        entries = sem_store.list_entries(1)
        assert len(entries) == 1
        # 決定論 gist の形跡
        assert "主観文0" in entries[0].text
        # warning ログ
        assert any(
            "falling back to deterministic gist" in rec.message for rec in caplog.records
        )

    def test_persona_resolver_が_落ちても_LLM_経路は_完走する(self) -> None:
        """persona_resolver の例外は warning を出して空文字 persona で続行。"""
        stub = _StubGistService(
            result=SemanticGistResult(
                gist_text="ok", importance_score=5, tags=()
            )
        )

        def broken_resolver(pid: int):
            raise RuntimeError("oops")

        svc, sem_store = _build_cluster(
            gist_service=stub,
            persona_resolver=broken_resolver,
        )
        svc.on_after_tool_turn(player_id=1)
        entries = sem_store.list_entries(1)
        assert len(entries) == 1
        assert entries[0].text == "ok"

    def test_persona_resolver_未指定なら_default_の_player_X_名で_動く(self) -> None:
        """persona_resolver=None でも LLM gist は動く。"""
        stub = _StubGistService(
            result=SemanticGistResult(
                gist_text="ok", importance_score=5, tags=()
            )
        )
        svc, sem_store = _build_cluster(
            gist_service=stub,
            persona_resolver=None,
        )
        svc.on_after_tool_turn(player_id=1)
        entries = sem_store.list_entries(1)
        assert len(entries) == 1
