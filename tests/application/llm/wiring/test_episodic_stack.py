"""``application/llm/wiring/episodic_stack.py`` の単体テスト (PR #330)。

検証範囲:
- env 解釈 (``is_episodic_enabled`` / ``is_episodic_subjective_enabled``)
- ``build_scenario_noun_matcher`` が scenario の spot/character を抽出する
- ``build_episodic_stack`` が 4 要素 (chunk_coordinator + passive_recall +
  noun_matcher + episode_store) を組み立てる
- ``episode_store`` 引数で外側 store を共有できる (scheduler 経路の整合性条件)
- 旧名 (``EscapeEpisodicStack`` / ``build_escape_episodic_stack``) が
  ``demos/escape_game/escape_episodic_wiring.py`` から後方互換 alias で取れる
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.llm.wiring.episodic_stack import (
    EpisodicStack,
    build_episodic_stack,
    build_scenario_noun_matcher,
    is_episodic_enabled,
    is_episodic_subjective_enabled,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)


def _stub_graph(*, spots: dict[int, str]) -> SimpleNamespace:
    """``graph._spots`` を模した SimpleNamespace を作る。

    builder は ``graph._spots.values()`` を呼ぶだけなので key 型は不問。
    dict key は int を使い、value 側に ``spot_id`` / ``name`` 属性を持たせる。
    """
    nodes: dict = {}
    for sid, name in spots.items():
        spot_id_obj = SimpleNamespace(value=sid)
        nodes[sid] = SimpleNamespace(spot_id=spot_id_obj, name=name)
    return SimpleNamespace(_spots=nodes)


def _stub_scenario(*, players: list[tuple[int, str]]) -> SimpleNamespace:
    """``scenario.player_spawns`` を模した SimpleNamespace を作る。"""
    spawns = [
        SimpleNamespace(player_id=pid, name=name)
        for pid, name in players
    ]
    return SimpleNamespace(player_spawns=spawns)


class TestIsEpisodicEnabled:
    """``LLM_EPISODIC_ENABLED`` の解釈 (シナリオ非依存)。"""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("1", True),
            ("true", True),
            ("YES", True),
            ("on", True),
            ("0", False),
            ("false", False),
            ("", False),
            ("garbage", False),
        ],
    )
    def test_各種値の解釈(self, raw: str, expected: bool) -> None:
        assert is_episodic_enabled({"LLM_EPISODIC_ENABLED": raw}) is expected

    def test_未設定なら_False(self) -> None:
        assert is_episodic_enabled({}) is False


class TestIsEpisodicSubjectiveEnabled:
    """``LLM_EPISODIC_SUBJECTIVE_ENABLED`` の解釈 (既定 ON)。"""

    def test_未設定なら_True(self) -> None:
        """既定 ON (#308): 未設定でも True。"""
        assert is_episodic_subjective_enabled({}) is True

    def test_空文字なら_True(self) -> None:
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": ""}) is True

    @pytest.mark.parametrize("raw", ["0", "false", "no", "off"])
    def test_明示_off_文字列で_False(self, raw: str) -> None:
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": raw}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "yes", "on"])
    def test_明示_on_文字列で_True(self, raw: str) -> None:
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": raw}) is True

    def test_不明値は_True_既定側(self) -> None:
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": "?"}) is True


class TestBuildScenarioNounMatcher:
    """spot / character の名前抽出は duck-type で動く。"""

    def test_spot_と_character_を抽出する(self) -> None:
        graph = _stub_graph(spots={1: "入口広間", 2: "閲覧室"})
        scenario = _stub_scenario(players=[(10, "カイト"), (20, "リン")])
        matcher = build_scenario_noun_matcher(scenario=scenario, graph=graph)
        # spot 名は place_spot axis
        spot_hits = matcher.find_in_text("入口広間に戻った")
        assert any(m.axis == "place_spot" for m in spot_hits)
        # キャラクター名は entity axis
        char_hits = matcher.find_in_text("カイトが探索した")
        assert any(m.axis == "entity" for m in char_hits)

    def test_scenario_に_player_spawns_が_無くても_落ちない(self) -> None:
        """getattr ベースなので欠落しても安全。"""
        graph = _stub_graph(spots={1: "広間"})
        scenario = SimpleNamespace()  # player_spawns 欠落
        matcher = build_scenario_noun_matcher(scenario=scenario, graph=graph)
        # spot だけは取れる
        assert matcher.find_in_text("広間に入った")


class TestBuildEpisodicStack:
    """``build_episodic_stack`` が必須 4 要素 + scheduler を組み立てる。"""

    def _minimal_io(self):
        return (
            DefaultObservationContextBuffer(),
            DefaultSlidingWindowMemory(),
            DefaultActionResultStore(),
        )

    def test_episodic_stack_の_4要素が組み立てられる(self) -> None:
        graph = _stub_graph(spots={1: "広間"})
        scenario = _stub_scenario(players=[(1, "テスター")])
        obs_buf, sliding, action_store = self._minimal_io()
        stack = build_episodic_stack(
            scenario=scenario,
            graph=graph,
            observation_buffer=obs_buf,
            sliding_window_memory=sliding,
            action_result_store=action_store,
        )
        assert isinstance(stack, EpisodicStack)
        assert stack.chunk_coordinator is not None
        assert stack.passive_recall is not None
        assert stack.noun_matcher is not None
        assert isinstance(stack.episode_store, InMemorySubjectiveEpisodeStore)
        # scheduler 未指定なら None
        assert stack.subjective_completion_scheduler is None

    def test_episode_store_を外から渡せる(self) -> None:
        """scheduler と stack で同じ store を共有するための入口。"""
        graph = _stub_graph(spots={1: "x"})
        scenario = _stub_scenario(players=[(1, "y")])
        obs_buf, sliding, action_store = self._minimal_io()
        shared = InMemorySubjectiveEpisodeStore()
        stack = build_episodic_stack(
            scenario=scenario,
            graph=graph,
            observation_buffer=obs_buf,
            sliding_window_memory=sliding,
            action_result_store=action_store,
            episode_store=shared,
        )
        # 渡した store がそのまま使われる
        assert stack.episode_store is shared


class TestReinterpretationOptIn:
    """U3: build_episodic_stack の reinterpretation (段1) opt-in 配線。"""

    def _io(self):
        return (
            DefaultObservationContextBuffer(),
            DefaultSlidingWindowMemory(),
            DefaultActionResultStore(),
        )

    def test_default_off_では_reinterpretation_は全て_None(self) -> None:
        """reinterpretation_enabled 未指定なら coordinator/journal/buffer 全て None (従来挙動)。"""
        obs_buf, sliding, action_store = self._io()
        stack = build_episodic_stack(
            scenario=_stub_scenario(players=[(1, "t")]),
            graph=_stub_graph(spots={1: "x"}),
            observation_buffer=obs_buf,
            sliding_window_memory=sliding,
            action_result_store=action_store,
        )
        assert stack.reinterpretation_coordinator is None
        assert stack.reinterpretation_journal is None
        assert stack.recall_buffer_store is None

    def test_enabled_かつ_completion_None_なら_coordinator_は作るが_prompt_buffer_は_None(self) -> None:
        """completion なし: coordinator/journal は組むが、prompt は recall buffer を覗かない。"""
        obs_buf, sliding, action_store = self._io()
        stack = build_episodic_stack(
            scenario=_stub_scenario(players=[(1, "t")]),
            graph=_stub_graph(spots={1: "x"}),
            observation_buffer=obs_buf,
            sliding_window_memory=sliding,
            action_result_store=action_store,
            reinterpretation_enabled=True,
            reinterpretation_completion=None,
        )
        assert stack.reinterpretation_coordinator is not None
        assert stack.reinterpretation_journal is not None
        # completion 無し = 再解釈 LLM が走らないので prompt には buffer を渡さない
        assert stack.recall_buffer_store is None

    def test_enabled_かつ_completion_あり_なら_prompt_buffer_も_非None(self) -> None:
        """completion あり: prompt 用 recall_buffer_store も非 None になる (想起を pending 化)。"""
        from ai_rpg_world.application.llm.ports.episodic_reinterpretation_completion_port import (
            IEpisodicReinterpretationCompletionPort,
        )

        class _StubCompletion(IEpisodicReinterpretationCompletionPort):
            def complete_episodic_reinterpretation_json(self, messages):
                return "{}"

        obs_buf, sliding, action_store = self._io()
        stack = build_episodic_stack(
            scenario=_stub_scenario(players=[(1, "t")]),
            graph=_stub_graph(spots={1: "x"}),
            observation_buffer=obs_buf,
            sliding_window_memory=sliding,
            action_result_store=action_store,
            reinterpretation_enabled=True,
            reinterpretation_completion=_StubCompletion(),
        )
        assert stack.reinterpretation_coordinator is not None
        assert stack.recall_buffer_store is not None
        # coordinator の current_turn_index が turn_index_provider として使える
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        assert stack.reinterpretation_coordinator.current_turn_index(PlayerId(1)) == 0


class TestBackwardCompatAlias:
    """``escape_episodic_wiring`` の旧名 alias が引き続き動く。

    既存のテスト / 外部依存を壊さないことの保証。
    """

    def test_旧名_EscapeEpisodicStack_は_EpisodicStack_の_alias(self) -> None:
        from ai_rpg_world.application.escape_game.escape_episodic_wiring import (
            EpisodicStack as NewName,
            EscapeEpisodicStack as OldName,
        )
        assert OldName is NewName

    def test_旧名_build_escape_episodic_stack_は_build_episodic_stack_の_alias(self) -> None:
        from ai_rpg_world.application.escape_game.escape_episodic_wiring import (
            build_episodic_stack as new_build,
            build_escape_episodic_stack as old_build,
        )
        assert old_build is new_build

    def test_旧名_envヘルパ_も_alias_経由で_動く(self) -> None:
        from ai_rpg_world.application.escape_game.escape_episodic_wiring import (
            is_episodic_enabled,
            is_episodic_subjective_enabled,
        )
        assert is_episodic_enabled({"LLM_EPISODIC_ENABLED": "1"}) is True
        assert is_episodic_subjective_enabled({}) is True
