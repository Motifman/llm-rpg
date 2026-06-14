"""escape_game の典型シナリオを模した episodic recall 検証ハーネス (Issue #283 後続)。

目的:
- escape_game demo は現在 episodic memory pipeline を wire していないが、
  メカニズム自体は実装済み (`test_episodic_passive_recall_retrieval.py` 等)
- 「未接続スポット問題」の原理ベース解決 = 「過去の経路 episode を cue 経由で
  recall して LLM が route 再構成する」を実現したい
- このハーネスでは、escape_game の典型シナリオ (リンが閲覧室→入口広間→書架A
  を巡って戻ってくる) を episode として store に流し込み、次の各場面で想起が
  期待通り動くかを検証する

検証する 3 シナリオ:
1. **同一スポットへの再訪 (place cue 一致)**:
   閲覧室に戻ったとき、過去の閲覧室訪問 episode が place_spot 軸で recall される ✓
2. **構造化観測経由の他スポット mention (推奨経路)**:
   観測の structured.spot_id_value に 「書架A」が乗っている場合、
   過去の書架A訪問 episode が recall される ✓
3. **自由文での他スポット mention (現状の限界)**:
   speech の prose に「書架A」と書かれていても structured に spot_id_value が
   無ければ recall されない → これが「書架Aで待ってるよ」と SNS で聞いても
   route 記憶が引き出せない原理的な穴。**設計議論の根拠データ**として残す
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.application.llm.services.episodic_cue_rules import (
    build_situation_episodic_cues,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


# ──────────────────────────────────────────────────────────────────
# シナリオ固定値: 沈黙の禁書庫 (forbidden_library_demo) のスポット ID
# ──────────────────────────────────────────────────────────────────
SPOT_ENTRY_HALL = 1   # 入口広間
SPOT_LIBRARY_HALL = 2  # 閲覧室
SPOT_SHELF_A = 3       # 書架A
SPOT_SHELF_B = 5       # 書架B
PLAYER_LIN = 2         # リン


def _resolver_for_lin():
    from ai_rpg_world.application.being.being_provisioning_service import (
        BeingProvisioningService,
    )
    from ai_rpg_world.domain.being.service.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.domain.world.value_object.world_id import (
        DEFAULT_SINGLE_WORLD_ID,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
        InMemoryBeingRepository,
    )

    repo = InMemoryBeingRepository()
    resolver = BeingAttachmentResolver(repo)
    BeingProvisioningService(repo).ensure_attached(PlayerId(PLAYER_LIN))
    return resolver, DEFAULT_SINGLE_WORLD_ID

PLAYER_KAITO = 1       # カイト


def _make_visit_episode(
    *,
    episode_id: str,
    player_id: int,
    spot_id: int,
    spot_name: str,
    occurred_at: datetime,
    what: str = "そのスポットに居た",
    outcome: str = "観察した",
) -> SubjectiveEpisode:
    """『player_id が spot_id に居たときの 1 場面』を encode した episode を作る。

    実装での EpisodicChunkCoordinator が生成するのと同じ形 (place_spot 軸の cue が
    runtime_context source で付く) を模す。
    """
    cue_place = EpisodicCue(
        axis="place_spot",
        value=str(spot_id),
        source=EpisodicCueSource.RUNTIME_CONTEXT,
    )
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=occurred_at,
        game_time_label=None,
        source=EpisodeSource(event_ids=(f"evt-{episode_id}",)),
        location=EpisodeLocation(spot_id=spot_id),
        action=EpisodeAction(tool_name="spot_graph_travel_to"),
        who=(f"player_{player_id}",),
        what=what,
        why=None,
        observed=spot_name,
        expected=None,
        outcome=outcome,
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(cue_place,),
        recall_text=f"[tick episode] {spot_name} を訪れた: {what}",
    )


@pytest.fixture
def lin_visit_history() -> InMemorySubjectiveEpisodeStore:
    """リンが 閲覧室→入口広間→書架A→入口広間→閲覧室 と巡った episode 列。

    各 episode に place_spot 軸の cue が乗っている (chunk_coordinator が出す形を模倣)。
    """
    # Phase 3 Step 3e-3: episode_store は being_id 経路のみ。PLAYER_LIN=2 用の
    # deterministic な BeingId で put する。
    from ai_rpg_world.domain.being.value_object.being_id import BeingId as _BID

    being_lin = _BID(f"being_w1_p{PLAYER_LIN}")
    base = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    store = InMemorySubjectiveEpisodeStore()
    episodes = [
        ("ep1-library", SPOT_LIBRARY_HALL, "閲覧室", "覚書を読んだ", base),
        ("ep2-entry", SPOT_ENTRY_HALL, "入口広間", "案内板を見た", base + timedelta(minutes=5)),
        ("ep3-shelfA", SPOT_SHELF_A, "書架A", "本を examine し『水』の断片語を見つけた", base + timedelta(minutes=10)),
        ("ep4-entry-return", SPOT_ENTRY_HALL, "入口広間", "通り抜けた", base + timedelta(minutes=14)),
        ("ep5-library-return", SPOT_LIBRARY_HALL, "閲覧室", "戻ってきた", base + timedelta(minutes=16)),
    ]
    for ep_id, spot_id, spot_name, what, occurred_at in episodes:
        store.put_by_being(
            being_lin,
            _make_visit_episode(
                episode_id=ep_id,
                player_id=PLAYER_LIN,
                spot_id=spot_id,
                spot_name=spot_name,
                what=what,
                occurred_at=occurred_at,
            ),
        )
    return store


def _runtime_context_at(spot_id: int) -> ToolRuntimeContextDto:
    """『現在 spot_id にいる』だけが分かる最小 runtime_context。"""
    return ToolRuntimeContextDto(
        targets={},
        current_spot_id=spot_id,
        current_sub_location_id=None,
    )


class TestRecallByCurrentLocationCue:
    """シナリオ 1: 同一スポットへの再訪。place_spot 軸で過去訪問が recall される。"""

    def test_閲覧室に戻ると過去の閲覧室訪問が想起される(
        self, lin_visit_history: InMemorySubjectiveEpisodeStore
    ) -> None:
        """リンが閲覧室に戻った場面で、過去の閲覧室訪問 (ep1, ep5) が cue 軸で
        recall される。**place_spot:2 が現在地から自然に作られる**ことを利用。"""
        svc = EpisodicPassiveRecallRetrievalService(
            lin_visit_history,
            being_attachment_resolver=_resolver_for_lin()[0],
            default_world_id=_resolver_for_lin()[1],
        )
        cues = build_situation_episodic_cues(
            runtime_context=_runtime_context_at(SPOT_LIBRARY_HALL),
            observation_structured=None,
            latest_action=None,
        )
        # 現在地 = 閲覧室 → place_spot:2 cue が 1 件できる
        assert ("place_spot", "2") in {(c.axis, c.value) for c in cues}

        result = svc.retrieve(
            player_id=PLAYER_LIN,
            situation_cues=cues,
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = {c.episode.episode_id for c in result.candidates}
        # 閲覧室訪問の 2 件が含まれる
        assert "ep1-library" in ids
        assert "ep5-library-return" in ids
        # 書架A訪問は place cue 一致しないので、cue 経路では出ない
        # (ただし temporal axis で recent 5 件入るので存在はする — ここでは
        # cue 軸での想起が機能していることだけ確認)


class TestRecallByObservationStructuredCue:
    """シナリオ 2: 構造化観測で他スポットが言及された場合。

    speech / SNS イベントが ``structured.spot_id_value`` に「書架A」を載せて
    届けば、自然に書架A の過去 episode が recall される。
    """

    def test_観測_structured_に_書架A_が乗ると書架A訪問が想起される(
        self, lin_visit_history: InMemorySubjectiveEpisodeStore
    ) -> None:
        """リンは閲覧室にいる。SNS / speech 観測の structured に
        spot_id_value=3 (書架A) が乗ったケースを想定。

        ``_cues_from_observation_structured`` が place_spot:3 cue を吐くので、
        書架A 訪問 episode が recall に入る。
        """
        svc = EpisodicPassiveRecallRetrievalService(
            lin_visit_history,
            being_attachment_resolver=_resolver_for_lin()[0],
            default_world_id=_resolver_for_lin()[1],
        )
        observation_structured = {
            "type": "speech_message",
            "speaker_player_id": PLAYER_KAITO,
            # 鍵となるフィールド: 「言及されたスポット」を明示
            "spot_id_value": SPOT_SHELF_A,
            "content": "リン、書架A で待ってるよ",
        }
        cues = build_situation_episodic_cues(
            runtime_context=_runtime_context_at(SPOT_LIBRARY_HALL),
            observation_structured=observation_structured,
            latest_action=None,
        )
        # place_spot:3 (書架A) が cue として立つ
        cue_keys = {(c.axis, c.value) for c in cues}
        assert ("place_spot", "3") in cue_keys

        result = svc.retrieve(
            player_id=PLAYER_LIN,
            situation_cues=cues,
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = {c.episode.episode_id for c in result.candidates}
        # 書架A 訪問 (ep3) が cue 軸で recall される
        assert "ep3-shelfA" in ids


class TestRecallByFreeTextMention:
    """シナリオ 3: 自由文での他スポット mention。

    PR #288 (WorldNounMatcher) + 本 PR (free-text cue extraction) で
    「書架A で待ってる」と SNS で聞くだけで ``place_spot:3`` cue が
    自動付与され、書架A 訪問 episode が recall されるようになった。

    ハードコードな pathfinding は一切無く、「世界の固有名詞 → 想起 cue」
    という単一原則のみで emergent に成立する動作。
    """

    def test_matcher_未注入なら自由文_書架A_は_cue_にならない(
        self, lin_visit_history: InMemorySubjectiveEpisodeStore
    ) -> None:
        """matcher を渡さなければ自由文経路は無効 = 旧挙動を維持する後方互換。
        ``WorldNounMatcher`` を wire しない demo / scenario で動作が
        変わらないことを担保。"""
        svc = EpisodicPassiveRecallRetrievalService(
            lin_visit_history,
            being_attachment_resolver=_resolver_for_lin()[0],
            default_world_id=_resolver_for_lin()[1],
        )
        observation_structured = {
            "type": "speech_message",
            "speaker_player_id": PLAYER_KAITO,
            "spot_id_value": SPOT_LIBRARY_HALL,  # 発話者の居場所のみ
            "content": "リン、書架A で待ってるよ",
        }
        cues = build_situation_episodic_cues(
            runtime_context=_runtime_context_at(SPOT_LIBRARY_HALL),
            observation_structured=observation_structured,
            latest_action=None,
            # observation_prose / noun_matcher 未指定 = 旧挙動
        )
        cue_keys = {(c.axis, c.value) for c in cues}
        assert ("place_spot", "3") not in cue_keys

    def test_matcher_注入で自由文_書架A_が_cue_になり_書架A_episode_が_recall_される(
        self, lin_visit_history: InMemorySubjectiveEpisodeStore
    ) -> None:
        """**Issue #283 後続の主目的動作**:

        scenario load 時に登録した ``WorldNounMatcher`` が SNS / speech prose 中の
        「書架A」を検出し、``OBSERVATION_FREETEXT`` source で ``place_spot:3``
        cue を自動付与する。その結果、リンの過去の書架A 訪問 ep3 が cue 軸で
        recall される (= 「あ、あのルートか」の emergent 動作)。"""
        from ai_rpg_world.application.llm.services.world_noun_matcher import (
            WorldNounMatcherBuilder,
        )

        matcher = (
            WorldNounMatcherBuilder()
            .add_spot("入口広間", spot_id=SPOT_ENTRY_HALL)
            .add_spot("閲覧室", spot_id=SPOT_LIBRARY_HALL)
            .add_spot("書架A", spot_id=SPOT_SHELF_A)
            .add_spot("書架B", spot_id=SPOT_SHELF_B)
            .build()
        )
        svc = EpisodicPassiveRecallRetrievalService(
            lin_visit_history,
            being_attachment_resolver=_resolver_for_lin()[0],
            default_world_id=_resolver_for_lin()[1],
        )
        observation_structured = {
            "type": "speech_message",
            "speaker_player_id": PLAYER_KAITO,
            "spot_id_value": SPOT_LIBRARY_HALL,  # 発話者の居場所 (書架Aではない)
            "content": "リン、書架A で待ってるよ",
        }
        observation_prose = (
            "〈解読室の扉〉の向こうから、カイトの遠くの声が聞こえる: "
            "「リン、書架A で待ってるよ」"
        )
        cues = build_situation_episodic_cues(
            runtime_context=_runtime_context_at(SPOT_LIBRARY_HALL),
            observation_structured=observation_structured,
            latest_action=None,
            observation_prose=observation_prose,
            noun_matcher=matcher,
        )
        cue_keys = {(c.axis, c.value) for c in cues}
        # 「書架A」が prose から拾われて place_spot:3 cue が立つ
        assert ("place_spot", "3") in cue_keys

        result = svc.retrieve(
            player_id=PLAYER_LIN,
            situation_cues=cues,
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = {c.episode.episode_id for c in result.candidates}
        # 書架A 訪問 episode が cue 軸経由で recall される
        assert "ep3-shelfA" in ids
        # place_spot 軸からのヒットだと確認 (= 自由文 cue 経由)
        ep3 = next(c for c in result.candidates if c.episode.episode_id == "ep3-shelfA")
        assert any("place_spot" in axis for axis in ep3.source_axes)


class TestRecallScalesWithRepeatedVisits:
    """ボーナス: 同じスポットを何度も訪れた場合、recall は重複 episode を
    distinct に扱う。"""

    def test_閲覧室_2_回訪問が_distinct_episode_としてrecallされる(
        self, lin_visit_history: InMemorySubjectiveEpisodeStore
    ) -> None:
        svc = EpisodicPassiveRecallRetrievalService(
            lin_visit_history,
            being_attachment_resolver=_resolver_for_lin()[0],
            default_world_id=_resolver_for_lin()[1],
        )
        cues = build_situation_episodic_cues(
            runtime_context=_runtime_context_at(SPOT_LIBRARY_HALL),
            observation_structured=None,
            latest_action=None,
        )
        result = svc.retrieve(
            player_id=PLAYER_LIN,
            situation_cues=cues,
            limit_per_axis=10,
            max_candidates=10,
        )
        ids = [c.episode.episode_id for c in result.candidates]
        # ep1 (初回) と ep5 (戻り) が両方記憶される
        assert "ep1-library" in ids
        assert "ep5-library-return" in ids
