"""PR7 (R4): WorldNounMatcher の入力拡張と空白吸収正規化の検証。

R4 の狙い:
1. ``WorldNounMatcher`` を最新観測 1 件以外にも当てる
   (= 直近 N 件の観測 prose + 自分の speech / inner_thought に当たる
   ``action_results.action_summary`` / ``result_summary``)
2. 「書架 A」(半角空白) と「書架A」(空白なし) の表記揺れを吸収する
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.episodic_cue_rules import (
    build_situation_episodic_cues,
)
from ai_rpg_world.application.llm.services.world_noun_matcher import (
    AhoCorasickWorldNounMatcher,
    WorldNounMatcherBuilder,
    _normalize_for_matching,
)
from ai_rpg_world.application.llm.services.prompt_builder import (
    _gather_additional_freetexts_for_recall,
    _R4_PER_TEXT_CHAR_CAP,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)


class TestR4WhitespaceNormalization:
    """R4: 空白の有無 / 全角半角空白を吸収する。"""

    def test_normalize_strips_ascii_space(self) -> None:
        """半角空白を含むパターン / text は同じ canonical に正規化される。"""
        assert _normalize_for_matching("書架 A") == _normalize_for_matching("書架A")

    def test_normalize_strips_full_width_space(self) -> None:
        """全角空白も NFKC で半角化 → 除去される。"""
        assert _normalize_for_matching("書架　A") == _normalize_for_matching("書架A")

    def test_normalize_strips_tab_and_newline(self) -> None:
        """tab / newline 等の whitespace も除去される。"""
        assert _normalize_for_matching("World\tObject\n1") == _normalize_for_matching("WorldObject1")

    def test_matcher_finds_spot_when_text_omits_space(self) -> None:
        """パターン「書架 A」を text「書架A」中にマッチさせる (xfail で発覚したケース)。"""
        builder = WorldNounMatcherBuilder()
        builder.add_spot("書架 A", spot_id=42)
        matcher = builder.build()
        matches = matcher.find_in_text("カイトの声: 「リン、書架Aで待ってる！」")
        assert len(matches) == 1
        assert matches[0].axis == "place_spot"
        assert matches[0].value == "42"

    def test_matcher_finds_spot_when_pattern_omits_space(self) -> None:
        """逆方向: パターン「書架A」と text「書架 A」もマッチする (対称性)。"""
        builder = WorldNounMatcherBuilder()
        builder.add_spot("書架A", spot_id=42)
        matcher = builder.build()
        matches = matcher.find_in_text("私は書架 A に向かった")
        assert len(matches) == 1
        assert matches[0].value == "42"

    def test_pattern_collision_after_normalization_emits_warning(self) -> None:
        """異なる cue value を同一 normalized text で登録すると RuntimeWarning。"""
        import warnings

        builder = WorldNounMatcherBuilder()
        builder.add_spot("石の 柱", spot_id=10)
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            builder.add_spot("石の柱", spot_id=20)
        runtime_warnings = [w for w in captured if issubclass(w.category, RuntimeWarning)]
        assert len(runtime_warnings) == 1
        assert "collision" in str(runtime_warnings[0].message)

    def test_same_axis_value_alias_does_not_warn(self) -> None:
        """同一 (axis, value) の alias 再登録は warn しない (= 既存仕様)。"""
        import warnings

        builder = WorldNounMatcherBuilder()
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            builder.add_spot("書架 A", spot_id=42, aliases=("書架A",))
        runtime_warnings = [w for w in captured if issubclass(w.category, RuntimeWarning)]
        assert runtime_warnings == []


class TestR4AdditionalFreetexts:
    """R4: ``build_situation_episodic_cues`` の ``additional_freetexts``。"""

    def _build_matcher(self) -> AhoCorasickWorldNounMatcher:
        builder = WorldNounMatcherBuilder()
        builder.add_spot("書架 A", spot_id=42)
        builder.add_character("アリス", player_id=7)
        result = builder.build()
        assert isinstance(result, AhoCorasickWorldNounMatcher)
        return result

    def test_cue_extracted_from_additional_freetext(self) -> None:
        """observation_prose が None でも additional_freetexts から cue が立つ。"""
        matcher = self._build_matcher()
        cues = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            observation_prose=None,
            noun_matcher=matcher,
            additional_freetexts=["アリスに会った"],
        )
        canonicals = {c.to_canonical() for c in cues}
        assert "entity:spot_graph_player_7" in canonicals

    def test_cues_from_multiple_freetexts_merge(self) -> None:
        """複数 freetext からの cue が dedupe で 1 件ずつ merge される。"""
        matcher = self._build_matcher()
        cues = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            observation_prose=None,
            noun_matcher=matcher,
            additional_freetexts=[
                "私は書架Aへ行った",
                "アリスに会った",
                "また書架Aに戻った",  # 重複 cue
            ],
        )
        canonicals = {c.to_canonical() for c in cues}
        assert "place_spot:42" in canonicals
        assert "entity:spot_graph_player_7" in canonicals
        # 重複しないこと
        place_cues = [c for c in cues if c.to_canonical() == "place_spot:42"]
        assert len(place_cues) == 1

    def test_freetext_source_marked_as_observation_freetext(self) -> None:
        """additional_freetexts 由来の cue は OBSERVATION_FREETEXT source で立つ。"""
        matcher = self._build_matcher()
        cues = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            observation_prose=None,
            noun_matcher=matcher,
            additional_freetexts=["アリスに会った"],
        )
        target = next(c for c in cues if c.to_canonical() == "entity:spot_graph_player_7")
        assert target.source == EpisodicCueSource.OBSERVATION_FREETEXT

    def test_none_or_empty_additional_freetexts_is_noop(self) -> None:
        """None / 空 list / 空文字混在は何もしない (落ちない)。"""
        matcher = self._build_matcher()
        # None
        cues_a = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            observation_prose=None,
            noun_matcher=matcher,
            additional_freetexts=None,
        )
        assert cues_a == ()
        # 空 list
        cues_b = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            observation_prose=None,
            noun_matcher=matcher,
            additional_freetexts=[],
        )
        assert cues_b == ()
        # 空文字 / None 混在
        cues_c = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            observation_prose=None,
            noun_matcher=matcher,
            additional_freetexts=["", "アリスに会った", ""],
        )
        canonicals = {c.to_canonical() for c in cues_c}
        assert "entity:spot_graph_player_7" in canonicals

    def test_matcher_not_injected_skips_additional_freetexts(self) -> None:
        """matcher が None なら additional_freetexts は無視 (= 静かに skip)。"""
        cues = build_situation_episodic_cues(
            runtime_context=None,
            observation_structured=None,
            latest_action=None,
            observation_prose=None,
            noun_matcher=None,
            additional_freetexts=["書架Aに行った"],
        )
        assert cues == ()


class TestR4GatherFreetextsHelper:
    """R4: ``_gather_additional_freetexts_for_recall`` の挙動。"""

    def _obs(self, prose: str) -> ObservationEntry:
        return ObservationEntry(
            occurred_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            output=ObservationOutput(
                prose=prose,
                structured={},
                observation_category="self_only",
            ),
        )

    def _action(self, action_summary: str, result_summary: str = "ok") -> ActionResultEntry:
        return ActionResultEntry(
            occurred_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            action_summary=action_summary,
            result_summary=result_summary,
            success=True,
        )

    def test_skip_latest_observation_prose(self) -> None:
        """observations[0] は別経路 (observation_prose) で渡されるため skip される。"""
        obs = [self._obs("FIRST_OBS"), self._obs("SECOND_OBS")]
        result = _gather_additional_freetexts_for_recall(obs, [])
        assert "FIRST_OBS" not in result
        assert "SECOND_OBS" in result

    def test_includes_action_summary_and_result_summary(self) -> None:
        """action_results の action_summary と result_summary 両方が含まれる。"""
        actions = [self._action("私はアリスに話しかけた", "アリスは応答した")]
        result = _gather_additional_freetexts_for_recall([], actions)
        assert "私はアリスに話しかけた" in result
        assert "アリスは応答した" in result

    def test_caps_per_text_length(self) -> None:
        """各テキストは _R4_PER_TEXT_CHAR_CAP 文字に切られる。"""
        long_prose = "a" * (_R4_PER_TEXT_CHAR_CAP + 100)
        obs = [self._obs("dummy"), self._obs(long_prose)]
        result = _gather_additional_freetexts_for_recall(obs, [])
        # observations[0] (dummy) は除外、[1] (long_prose) が含まれる
        assert any(t.startswith("a") for t in result)
        for t in result:
            if t.startswith("a"):
                assert len(t) == _R4_PER_TEXT_CHAR_CAP

    def test_limits_to_recent_5_observations(self) -> None:
        """直近 5 件まで (= [1:6]) しか取らない。"""
        obs = [self._obs(f"OBS_{i}") for i in range(10)]
        result = _gather_additional_freetexts_for_recall(obs, [])
        # OBS_0 は skip (latest)、OBS_1..OBS_5 が 5 件、OBS_6 以降は cut
        assert "OBS_0" not in result
        assert "OBS_1" in result
        assert "OBS_5" in result
        assert "OBS_6" not in result

    def test_empty_inputs_return_empty(self) -> None:
        """observations / action_results 両方空なら空 list。"""
        assert _gather_additional_freetexts_for_recall([], []) == []
