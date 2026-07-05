"""``application/llm/wiring/episodic_stack.py`` の単体テスト (PR #330)。

検証範囲:
- env 解釈 (``is_episodic_enabled`` / ``is_episodic_subjective_enabled``)
- ``build_scenario_noun_matcher`` が scenario の spot/character を抽出する
- ``build_episodic_stack`` が 4 要素 (chunk_coordinator + passive_recall +
  noun_matcher + episode_store) を組み立てる
- ``episode_store`` 引数で外側 store を共有できる (scheduler 経路の整合性条件)
- 旧名 (``WorldEpisodicStack`` / ``build_world_episodic_stack``) が
  ``demos/world_runtime/world_episodic_wiring.py`` から後方互換 alias で取れる
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


def _stub_graph(
    *,
    spots: dict[int, str],
    interior_objects: dict[int, list[tuple[int, str]]] | None = None,
) -> SimpleNamespace:
    """``graph._spots`` を模した SimpleNamespace を作る。

    builder は ``graph._spots.values()`` を呼ぶだけなので key 型は不問。
    dict key は int を使い、value 側に ``spot_id`` / ``name`` 属性を持たせる。

    ``interior_objects`` を渡すと、各 spot の ``interior.objects`` に
    ``SpotObject`` 風の SimpleNamespace を仕込む (#526 後続 C1)。dict の値は
    ``[(object_id, name), ...]`` のリスト。
    """
    interior_objects = interior_objects or {}
    nodes: dict = {}
    for sid, name in spots.items():
        spot_id_obj = SimpleNamespace(value=sid)
        objs = tuple(
            SimpleNamespace(
                object_id=SimpleNamespace(value=oid),
                name=oname,
            )
            for oid, oname in interior_objects.get(sid, [])
        )
        interior = SimpleNamespace(objects=objs)
        nodes[sid] = SimpleNamespace(
            spot_id=spot_id_obj,
            name=name,
            interior=interior,
        )
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

    def test_world_object_名_を抽出する(self) -> None:
        """#526 後続 C1: 各 spot の ``interior.objects`` から world_object 名を
        抽出し、``object:world_object_{id}`` cue として recall に乗るようにする。

        実 run の trace 解析で「観測 prose に『案内板』『覚書』等の object 名
        が出てくるが、matcher が知らないため write/read 双方で object cue が
        立たない」ことが判明したため、scenario data から object 名を index
        する経路を足す。
        """
        graph = _stub_graph(
            spots={1: "入口広間", 2: "閲覧室"},
            interior_objects={
                1: [(101, "案内板"), (102, "侵入者の手記")],
                2: [(201, "見習い司書の覚書")],
            },
        )
        scenario = _stub_scenario(players=[(10, "カイト")])
        matcher = build_scenario_noun_matcher(scenario=scenario, graph=graph)
        # prose に object 名が出れば object cue にマッチ
        obj_hits = matcher.find_in_text("案内板を読んだ")
        assert any(
            m.axis == "object" and m.value == "world_object_101"
            for m in obj_hits
        ), f"案内板が world_object_101 にマッチしない: {obj_hits}"
        # 別 spot の object も index されている (= グローバル走査)
        obj_hits2 = matcher.find_in_text("見習い司書の覚書には印の順序が書いてあった")
        assert any(
            m.axis == "object" and m.value == "world_object_201"
            for m in obj_hits2
        )

    def test_interior_が_欠落しても_落ちない(self) -> None:
        """``interior`` 属性が無い古い stub / scenario でも落とさない (getattr 安全側)。"""
        # interior 属性そのものを持たない spot を作る
        spot_id_obj = SimpleNamespace(value=1)
        spot_node = SimpleNamespace(spot_id=spot_id_obj, name="広間")
        graph = SimpleNamespace(_spots={1: spot_node})
        scenario = _stub_scenario(players=[(10, "カイト")])
        # 例外なく構築できる
        matcher = build_scenario_noun_matcher(scenario=scenario, graph=graph)
        # spot 名は引き続き拾える
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


class TestRecallHitBoostOptIn:
    """U9b (想起の信用割り当て・的中側): build_episodic_stack の opt-in 配線。"""

    def _io(self):
        return (
            DefaultObservationContextBuffer(),
            DefaultSlidingWindowMemory(),
            DefaultActionResultStore(),
        )

    def test_default_off_では_recall_success_store_は_None(self) -> None:
        """recall_hit_boost_enabled 未指定なら的中側 sidecar は None (従来挙動)。"""
        obs_buf, sliding, action_store = self._io()
        stack = build_episodic_stack(
            scenario=_stub_scenario(players=[(1, "t")]),
            graph=_stub_graph(spots={1: "x"}),
            observation_buffer=obs_buf,
            sliding_window_memory=sliding,
            action_result_store=action_store,
        )
        assert stack.recall_success_store is None

    def test_enabled_なら_recall_success_store_が構築され_chunk_coordinator_に渡る(
        self,
    ) -> None:
        """flag ON で的中側 sidecar が構築され、stack が公開する。"""
        obs_buf, sliding, action_store = self._io()
        stack = build_episodic_stack(
            scenario=_stub_scenario(players=[(1, "t")]),
            graph=_stub_graph(spots={1: "x"}),
            observation_buffer=obs_buf,
            sliding_window_memory=sliding,
            action_result_store=action_store,
            recall_hit_boost_enabled=True,
            recall_hit_boost_strength=2,
        )
        assert stack.recall_success_store is not None
        assert stack.recall_hit_boost_strength == 2
        # chunk_coordinator にも同一インスタンスが配線されている。
        assert stack.chunk_coordinator._recall_success_store is stack.recall_success_store  # noqa: SLF001
        assert stack.chunk_coordinator._recall_hit_boost_enabled is True  # noqa: SLF001

    def test_enabled_なら_passive_recall_にも_同一store_と_strength_が配線される(
        self,
    ) -> None:
        obs_buf, sliding, action_store = self._io()
        stack = build_episodic_stack(
            scenario=_stub_scenario(players=[(1, "t")]),
            graph=_stub_graph(spots={1: "x"}),
            observation_buffer=obs_buf,
            sliding_window_memory=sliding,
            action_result_store=action_store,
            recall_hit_boost_enabled=True,
            recall_hit_boost_strength=3,
            recall_hit_boost_cap=1,
        )
        assert stack.passive_recall._recall_success_store is stack.recall_success_store  # noqa: SLF001
        assert stack.passive_recall._hit_boost_strength == 3  # noqa: SLF001
        assert stack.passive_recall._hit_boost_cap == 1  # noqa: SLF001


class TestBackwardCompatAlias:
    """``world_episodic_wiring`` の旧名 alias が引き続き動く。

    既存のテスト / 外部依存を壊さないことの保証。
    """

    def test_旧名_WorldEpisodicStack_は_EpisodicStack_の_alias(self) -> None:
        from ai_rpg_world.application.world_runtime.world_episodic_wiring import (
            EpisodicStack as NewName,
            WorldEpisodicStack as OldName,
        )
        assert OldName is NewName

    def test_旧名_build_world_episodic_stack_は_build_episodic_stack_の_alias(self) -> None:
        from ai_rpg_world.application.world_runtime.world_episodic_wiring import (
            build_episodic_stack as new_build,
            build_world_episodic_stack as old_build,
        )
        assert old_build is new_build

    def test_旧名_envヘルパ_も_alias_経由で_動く(self) -> None:
        from ai_rpg_world.application.world_runtime.world_episodic_wiring import (
            is_episodic_enabled,
            is_episodic_subjective_enabled,
        )
        assert is_episodic_enabled({"LLM_EPISODIC_ENABLED": "1"}) is True
        assert is_episodic_subjective_enabled({}) is True
