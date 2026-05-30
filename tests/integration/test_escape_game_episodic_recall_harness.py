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
from ai_rpg_world.application.llm.contracts.episodic_memory import (
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    EpisodicCue,
    EpisodicCueSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.services.episodic_cue_rules import (
    build_situation_episodic_cues,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)


# ──────────────────────────────────────────────────────────────────
# シナリオ固定値: 沈黙の禁書庫 (forbidden_library_demo) のスポット ID
# ──────────────────────────────────────────────────────────────────
SPOT_ENTRY_HALL = 1   # 入口広間
SPOT_LIBRARY_HALL = 2  # 閲覧室
SPOT_SHELF_A = 3       # 書架A
SPOT_SHELF_B = 5       # 書架B
PLAYER_LIN = 2         # リン
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
        store.put(
            _make_visit_episode(
                episode_id=ep_id,
                player_id=PLAYER_LIN,
                spot_id=spot_id,
                spot_name=spot_name,
                what=what,
                occurred_at=occurred_at,
            )
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
        svc = EpisodicPassiveRecallRetrievalService(lin_visit_history)
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
        svc = EpisodicPassiveRecallRetrievalService(lin_visit_history)
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
    """シナリオ 3: 自由文での他スポット mention は recall できない (現状の限界)。

    speech の prose に「書架A」と書かれていても、observation_structured に
    spot_id_value が乗っていなければ cue 抽出は走らない。
    **「書架A で待ってるよ」と SNS で聞いた瞬間に route 記憶が思い出される**
    という user の理想動作のためには、speech / SNS event の構造化タギングが
    必要 = 設計議論ポイント。
    """

    def test_観測_structured_に_spot_id_value_が無ければ書架A_episode_はrecall_されない(
        self, lin_visit_history: InMemorySubjectiveEpisodeStore
    ) -> None:
        """structured には spot_id_value=2 (= 発話者カイトの居場所、閲覧室) しか
        乗っていない。prose に「書架A」と書いてあっても cue にはならない。"""
        svc = EpisodicPassiveRecallRetrievalService(lin_visit_history)
        observation_structured = {
            "type": "speech_message",
            "speaker_player_id": PLAYER_KAITO,
            # 発話者の現在地 (書架Aではない). 「書架A」は content の自由文だけ
            "spot_id_value": SPOT_LIBRARY_HALL,
            "content": "リン、書架A で待ってるよ",
        }
        cues = build_situation_episodic_cues(
            runtime_context=_runtime_context_at(SPOT_LIBRARY_HALL),
            observation_structured=observation_structured,
            latest_action=None,
        )
        cue_keys = {(c.axis, c.value) for c in cues}
        # place_spot:3 は cue として立たない (自由文を NLP 解析していないため)
        assert ("place_spot", "3") not in cue_keys

        # cue 軸では recall されないが、temporal 軸では recent な episodes は
        # 入る。**cue 軸単独で見れば書架A は出ない**ことを確認するために、
        # episode が temporal で出るのとは別に source_axes でフィルタ。
        result = svc.retrieve(
            player_id=PLAYER_LIN,
            situation_cues=cues,
            limit_per_axis=10,
            max_candidates=10,
        )
        for cand in result.candidates:
            if cand.episode.episode_id == "ep3-shelfA":
                # 書架A episode が候補に出ているなら、それは temporal 軸由来の
                # はずで、place_spot:3 由来ではない
                assert "temporal" in cand.source_axes
                assert "place_spot" not in str(cand.source_axes)


class TestRecallScalesWithRepeatedVisits:
    """ボーナス: 同じスポットを何度も訪れた場合、recall は重複 episode を
    distinct に扱う。"""

    def test_閲覧室_2_回訪問が_distinct_episode_としてrecallされる(
        self, lin_visit_history: InMemorySubjectiveEpisodeStore
    ) -> None:
        svc = EpisodicPassiveRecallRetrievalService(lin_visit_history)
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
