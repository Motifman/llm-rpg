"""ChunkEpisodeDraftBuilder が ChunkEncodingInput からルールのみで草案を埋めることの検証。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    build_chunk_encoding_input,
    chunk_encoding_episode_generation_allowed,
    format_unified_timeline_as_recent_events_bullets,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import ChunkEpisodeDraftBuilder
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput, ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestChunkEpisodeDraftBuilder:
    """チャンク入力から SubjectiveEpisode のルールフィールドが決定論的に埋まる。"""

    def test_rejects_chunk_without_actions(self) -> None:
        """ActionResultEntry が 0 件のときは ValueError（起動ゲートと整合）。"""
        inp = build_chunk_encoding_input(PlayerId(1), (), ())
        assert chunk_encoding_episode_generation_allowed(inp) is False
        with pytest.raises(ValueError, match="ActionResultEntry"):
            ChunkEpisodeDraftBuilder().build(inp)

    def test_observed_matches_unified_timeline_bullets(self) -> None:
        """observed は merge 済みタイムラインの箇条書きと一致（プロンプト一次情報に揃える）。"""
        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        obs = ObservationEntry(
            occurred_at=t0,
            output=ObservationOutput(
                prose="雷が鳴った。",
                structured={},
                observation_category="environment",
            ),
            game_time_label="昼",
        )
        act = ActionResultEntry(
            occurred_at=t0 + timedelta(minutes=1),
            action_summary="避難を試みた",
            result_summary="成功した。",
            tool_name="move",
        )
        inp = build_chunk_encoding_input(PlayerId(2), (obs,), (act,))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.observed == format_unified_timeline_as_recent_events_bullets(inp.unified_timeline)
        assert "[昼]" in ep.observed
        assert "move" in ep.what

    def test_interpreted_and_recall_filled_with_template_fallback(self) -> None:
        """interpreted / recall_text はテンプレで draft 時点から埋まる。

        LLM 補完サービス未配線でも recall 時に「何か」が prompt に載るようにする
        ため、``compute_template_interpreted`` / ``compute_template_recall`` の結果を
        ``ChunkEpisodeDraftBuilder`` が draft に埋める (#295 r2 trace で
        ``recall_text_snippet`` 0/21 件問題が発覚)。LLM 補完が走るときは
        ``EpisodicChunkSubjectiveFieldsService.merge_llm_subjective_fields`` が
        上書きするので副作用なし。
        """
        act = ActionResultEntry(
            occurred_at=datetime(2026, 5, 4, 11, 0, 0, tzinfo=timezone.utc),
            action_summary="x",
            result_summary="y",
            tool_name="inspect",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        # None ではなく非空文字 (テンプレが埋まっている)
        assert isinstance(ep.interpreted, str) and ep.interpreted
        assert isinstance(ep.recall_text, str) and ep.recall_text
        # interpreted は what (= action_summary 連結) ベース
        assert "x" in ep.interpreted
        # recall_text は observed の最初の非空行 or what ベース
        assert ep.recall_text  # 内容ベースの詳細 assert は別 unit test に分離

    def test_occurred_at_is_latest_action_time(self) -> None:
        """occurred_at はチャンク内行動の最大 occurred_at（境界の「いつ」）。"""
        early = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        late = early + timedelta(seconds=30)
        a1 = ActionResultEntry(
            occurred_at=early,
            action_summary="a",
            result_summary="r1",
            tool_name="t1",
        )
        a2 = ActionResultEntry(
            occurred_at=late,
            action_summary="b",
            result_summary="r2",
            tool_name="t2",
            success=False,
            error_code="E1",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (a1, a2))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.occurred_at == late
        assert "失敗" in ep.outcome

    def test_who_and_location_from_observation_structured(self) -> None:
        """観測 structured から who 相当・spot（where）をルールで抽出する。"""
        t = datetime(2026, 5, 4, 13, 0, 0, tzinfo=timezone.utc)
        obs = ObservationEntry(
            occurred_at=t,
            output=ObservationOutput(
                prose="誰かが近づいた。",
                structured={"actor": 501, "spot_id_value": 77},
                observation_category="social",
            ),
        )
        act = ActionResultEntry(
            occurred_at=t + timedelta(minutes=1),
            action_summary="話しかけた",
            result_summary="無視された。",
            tool_name="talk",
        )
        inp = build_chunk_encoding_input(PlayerId(9), (obs,), (act,))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert "entity:actor:501" in ep.who
        assert ep.location.spot_id == 77
        canon = {c.to_canonical() for c in ep.cues}
        assert "place_spot:77" in canon
        assert any(k.startswith("entity:") for k in canon)

    def test_overflow_observation_contributes_to_cues_not_timeline(self) -> None:
        """
        observation_overflow_from_window は unified には入らないが、
        cue / who / 場所ヒントの材料には含まれる。
        """
        t0 = datetime(2026, 5, 4, 14, 0, 0, tzinfo=timezone.utc)
        overflow = ObservationEntry(
            occurred_at=t0,
            output=ObservationOutput(
                prose="溢れ",
                structured={"spot_id_value": 88},
                observation_category="environment",
            ),
        )
        act = ActionResultEntry(
            occurred_at=t0 + timedelta(hours=1),
            action_summary="行動",
            result_summary="結果",
            tool_name="noop",
        )
        inp = build_chunk_encoding_input(
            PlayerId(1),
            (),
            (act,),
            observation_overflow_from_window=(overflow,),
        )
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert "88" not in ep.observed  # タイムラインに観測行が無い
        assert ep.location.spot_id == 88
        assert any(c.to_canonical() == "place_spot:88" for c in ep.cues)

    def test_action_tool_field_joins_distinct_tools(self) -> None:
        """EpisodeAction.tool_name は複数 tool の辞書順連結。"""
        t = datetime(2026, 5, 4, 15, 0, 0, tzinfo=timezone.utc)
        acts = (
            ActionResultEntry(
                occurred_at=t,
                action_summary="a",
                result_summary="r",
                tool_name="beta",
            ),
            ActionResultEntry(
                occurred_at=t + timedelta(seconds=1),
                action_summary="b",
                result_summary="r",
                tool_name="alpha",
            ),
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), acts)
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.action is not None
        assert ep.action.tool_name == "alpha,beta"

    def test_expected_why_felt_composed_from_action_subjective_fields(self) -> None:
        """expected/why/felt が action results の主観入力から決定論的に埋まる (PR2a)。"""
        t0 = datetime(2026, 5, 4, 16, 0, 0, tzinfo=timezone.utc)
        a1 = ActionResultEntry(
            occurred_at=t0,
            action_summary="ノアに挨拶",
            result_summary="ok",
            tool_name="speech_say",
            expected_result="ノアが返事をする",
            intention="ノアの様子を確かめる",
            emotion_hint="curiosity",
        )
        a2 = ActionResultEntry(
            occurred_at=t0 + timedelta(minutes=1),
            action_summary="灯台へ移動",
            result_summary="ok",
            tool_name="travel",
            expected_result="灯台に着く",
            intention="灯台で手がかりを探す",
            emotion_hint="determination",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (a1, a2))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.expected == "- speech_say: ノアが返事をする\n- travel: 灯台に着く"
        assert ep.why == "- speech_say: ノアの様子を確かめる\n- travel: 灯台で手がかりを探す"
        assert ep.felt == "curiosity、determination"
        # prediction_error は質的乖離判定なので LLM 補完 (PR2b) に委ね、ここでは None
        assert ep.prediction_error is None

    def test_subjective_fields_none_when_actions_lack_them(self) -> None:
        """action が主観入力を持たないとき expected/why/felt は None のまま。"""
        act = ActionResultEntry(
            occurred_at=datetime(2026, 5, 4, 17, 0, 0, tzinfo=timezone.utc),
            action_summary="x",
            result_summary="y",
            tool_name="inspect",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.expected is None
        assert ep.why is None
        assert ep.felt is None

    def test_expected_compresses_beyond_three_actions(self) -> None:
        """expected は最大3件 + 「ほか N 件」に畳む (トークン肥大防止)。"""
        t0 = datetime(2026, 5, 4, 18, 0, 0, tzinfo=timezone.utc)
        acts = tuple(
            ActionResultEntry(
                occurred_at=t0 + timedelta(minutes=i),
                action_summary=f"a{i}",
                result_summary="ok",
                tool_name=f"tool{i}",
                expected_result=f"予測{i}",
            )
            for i in range(5)
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), acts)
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.expected is not None
        assert "ほか 2 件" in ep.expected
        # 3 bullets + 「ほか N 件」 = 4 行
        assert len(ep.expected.splitlines()) == 4

    def test_felt_dedups_repeated_emotion(self) -> None:
        """同じ emotion_hint が続いても felt では 1 回だけ。"""
        t0 = datetime(2026, 5, 4, 19, 0, 0, tzinfo=timezone.utc)
        acts = (
            ActionResultEntry(
                occurred_at=t0,
                action_summary="a",
                result_summary="ok",
                tool_name="t1",
                emotion_hint="fear",
            ),
            ActionResultEntry(
                occurred_at=t0 + timedelta(minutes=1),
                action_summary="b",
                result_summary="ok",
                tool_name="t2",
                emotion_hint="fear",
            ),
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), acts)
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.felt == "fear"


class _FakeNounMatcher:
    """テスト用の固定 noun_matcher。``find_in_text`` で渡された text の中から
    事前登録した語を見つけたら NounMatch を返す (Aho-Corasick の代替)。"""

    def __init__(self, patterns: list[tuple[str, str, str]]) -> None:
        # patterns: list of (word, axis, value)
        self._patterns = patterns

    def find_in_text(self, text):
        from ai_rpg_world.application.llm.services.world_noun_matcher import NounMatch
        out = []
        for word, axis, value in self._patterns:
            idx = text.find(word)
            if idx >= 0:
                out.append(
                    NounMatch(
                        axis=axis,
                        value=value,
                        matched_text=word,
                        start=idx,
                        end=idx + len(word),
                    )
                )
        return tuple(out)


class TestChunkEpisodeDraftBuilderNounMatcher:
    """#526 後続 Fix A: write 側で noun_matcher を使い、観測 prose 中の
    固有名詞から place_spot / entity / object cue を episode に貼る。"""

    def test_noun_matcher_未注入なら_既存挙動と同一(self) -> None:
        """``noun_matcher=None`` (default) では prose 由来 cue は付かない。
        既存の structured / action / outcome cue のみ。"""
        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        obs = ObservationEntry(
            occurred_at=t0,
            output=ObservationOutput(
                prose="書架Aで青い背表紙の本を見つけた。",
                structured={},
                observation_category="environment",
            ),
            game_time_label=None,
        )
        act = ActionResultEntry(
            occurred_at=t0 + timedelta(minutes=1),
            action_summary="examine",
            result_summary="ok",
            tool_name="interact",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (obs,), (act,))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        axes_in_episode = {c.axis for c in ep.cues}
        assert "place_spot" not in axes_in_episode
        assert "entity" not in axes_in_episode
        assert "object" not in axes_in_episode

    def test_noun_matcher_注入時_観測_prose_由来_cue_が_episode_に_乗る(self) -> None:
        """matcher が「書架A」を spot_id=3 として登録していれば、
        観測 prose にその語が含まれる episode の cues に place_spot:3 が乗る。"""
        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        obs = ObservationEntry(
            occurred_at=t0,
            output=ObservationOutput(
                prose="書架Aで青い背表紙の本を見つけた。",
                structured={},
                observation_category="environment",
            ),
            game_time_label=None,
        )
        act = ActionResultEntry(
            occurred_at=t0 + timedelta(minutes=1),
            action_summary="examine",
            result_summary="ok",
            tool_name="interact",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (obs,), (act,))
        matcher = _FakeNounMatcher(
            [("書架A", "place_spot", "3"), ("青", "object", "world_object_1")]
        )
        ep = ChunkEpisodeDraftBuilder(noun_matcher=matcher).build(inp)
        canons = {c.to_canonical() for c in ep.cues}
        assert "place_spot:3" in canons
        assert "object:world_object_1" in canons

    def test_noun_matcher_注入時_観測_prose_が_None_なら_cue_は_増えない(self) -> None:
        """observation の prose が None / 空でも例外を投げず、追加 cue 0 件。"""
        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        obs = ObservationEntry(
            occurred_at=t0,
            output=ObservationOutput(
                prose="",
                structured={"type": "x"},
                observation_category="environment",
            ),
            game_time_label=None,
        )
        act = ActionResultEntry(
            occurred_at=t0 + timedelta(minutes=1),
            action_summary="examine",
            result_summary="ok",
            tool_name="t",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (obs,), (act,))
        matcher = _FakeNounMatcher([("書架A", "place_spot", "3")])
        ep = ChunkEpisodeDraftBuilder(noun_matcher=matcher).build(inp)
        axes_in_episode = {c.axis for c in ep.cues}
        assert "place_spot" not in axes_in_episode


class TestChunkEpisodeDraftBuilderRuntimeContext:
    """#526 後続 C2: chunk write 時に runtime_context provider が呼ばれ、
    現在の player の場所 / 視界 object / 同席者が episode の cue に固定される。
    """

    def test_runtime_context_provider_未注入なら_既存挙動と同一(self) -> None:
        """provider が ``None`` のときは place_spot / object cue が運ばれない
        (Fix A 単独の挙動を維持)。"""
        from ai_rpg_world.application.llm.contracts.dtos import (
            ToolRuntimeContextDto,
        )
        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t0,
            action_summary="x",
            result_summary="ok",
            tool_name="t",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        axes_in_episode = {c.axis for c in ep.cues}
        assert "place_spot" not in axes_in_episode
        assert "object" not in axes_in_episode

    def test_runtime_context_provider_注入時_current_spot_id_が_place_spot_cue_に乗る(self) -> None:
        """provider が ``current_spot_id=5`` を返せば、episode に
        ``place_spot:5`` cue が貼られる。これにより memo_add のような
        prose / structured が乏しいターンでも場所文脈が episode に残る。"""
        from ai_rpg_world.application.llm.contracts.dtos import (
            ToolRuntimeContextDto,
        )
        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t0,
            action_summary="memo_add",
            result_summary="ok",
            tool_name="memo_add",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))

        context = ToolRuntimeContextDto(targets={}, current_spot_id=5)
        provider_calls = []

        def provider(pid):
            provider_calls.append(pid)
            return context

        ep = ChunkEpisodeDraftBuilder(
            runtime_context_provider=provider
        ).build(inp)

        # provider は player_id を引数に呼ばれる
        assert provider_calls == [PlayerId(1)]
        canons = {c.to_canonical() for c in ep.cues}
        assert "place_spot:5" in canons, f"current_spot_id が cue 化されていない: {canons}"

    def test_runtime_context_provider_例外を投げても_episode_は_書ける(self) -> None:
        """provider が例外を投げても chunk write 自体は止めない (graceful)。
        cue は付かないが episode は成立する。"""
        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t0,
            action_summary="x",
            result_summary="ok",
            tool_name="t",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))

        def provider(pid):
            raise RuntimeError("simulated runtime broken")

        # 例外を握りつぶし、episode は書ける
        ep = ChunkEpisodeDraftBuilder(
            runtime_context_provider=provider
        ).build(inp)
        assert ep.episode_id  # 正常に id が振られている

    def test_runtime_context_provider_が_None_を返したら_cue_は_増えない(self) -> None:
        """provider が ``None`` (= 「context が取れない」明示) を返すケースでも
        例外を投げず既存挙動と同一。"""
        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t0,
            action_summary="x",
            result_summary="ok",
            tool_name="t",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))

        ep = ChunkEpisodeDraftBuilder(
            runtime_context_provider=lambda pid: None
        ).build(inp)
        axes_in_episode = {c.axis for c in ep.cues}
        assert "place_spot" not in axes_in_episode


class TestChunkEpisodeDraftBuilderCoPresent:
    """PR-M: chunk write 時の runtime_context の「同席プレイヤー」を co_present
    として episode に刻印する。約束清算の共在ゲートが who (= 動作した人) だけ
    でなく co_present (= その場に居た人) も照合できるようにするため。
    """

    def test_co_present_is_empty_when_no_runtime_context(self) -> None:
        """runtime_context provider 未注入なら co_present は空 (= 導入前と一致)。"""
        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t0,
            action_summary="x",
            result_summary="ok",
            tool_name="t",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))
        ep = ChunkEpisodeDraftBuilder().build(inp)
        assert ep.co_present == ()

    def test_player_targets_become_co_present(self) -> None:
        """runtime_context.targets の PlayerToolRuntimeTargetDto の表示名が、

        黙っている同席者も含めて co_present に (ラベル昇順・重複除去で) 入る。
        """
        from ai_rpg_world.application.llm.contracts.dtos import (
            PlayerToolRuntimeTargetDto,
            QuestToolRuntimeTargetDto,
            ToolRuntimeContextDto,
        )

        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t0,
            action_summary="memo_add",
            result_summary="ok",
            tool_name="memo_add",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))
        context = ToolRuntimeContextDto(
            targets={
                "E2": PlayerToolRuntimeTargetDto(
                    label="E2",
                    kind="spot_graph_player",
                    display_name="ノア",
                    player_id=3,
                ),
                "E1": PlayerToolRuntimeTargetDto(
                    label="E1",
                    kind="spot_graph_player",
                    display_name="カイ",
                    player_id=2,
                ),
                # プレイヤー以外の target (クエスト等) は co_present に含めない。
                "Q1": QuestToolRuntimeTargetDto(
                    label="Q1",
                    kind="quest",
                    display_name="クエストX",
                ),
            }
        )
        ep = ChunkEpisodeDraftBuilder(
            runtime_context_provider=lambda pid: context
        ).build(inp)
        assert ep.co_present == ("カイ", "ノア")

    def test_co_present_empty_when_no_player_targets(self) -> None:
        """同席プレイヤーが居ない (player target が無い) なら co_present は空。"""
        from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto

        t0 = datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t0,
            action_summary="x",
            result_summary="ok",
            tool_name="t",
        )
        inp = build_chunk_encoding_input(PlayerId(1), (), (act,))
        ep = ChunkEpisodeDraftBuilder(
            runtime_context_provider=lambda pid: ToolRuntimeContextDto(
                targets={}, current_spot_id=5
            )
        ).build(inp)
        assert ep.co_present == ()
