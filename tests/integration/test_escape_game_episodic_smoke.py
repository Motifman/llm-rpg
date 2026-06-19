"""escape_game の episodic pipeline 配線が end-to-end で生きていることを
確認する smoke harness (Issue #283 後続)。

# 目的

PR #292 で配線したばかりの ``LLM_EPISODIC_ENABLED`` フラグが本番実走前に
壊れていないかを早期に検出するための smoke test。
実 LLM を使わず scripted action だけで、次の 4 点を end-to-end で検証する:

1. env=0 (default) なら ``_episodic_stack`` が ``None`` で完全な後方互換
2. env=1 なら chunk coordinator + passive recall + noun_matcher が組み立て
   られ、移動アクションを 1 回実行した後に **episode store に最低 1 件**
   書き込まれている (= 書き手側の経路が alive)
3. その状態で ``build_full_prompt`` が例外なく完走し、messages が空でない
4. recall 経路が alive: 過去の書架A 訪問 episode を手動で store に注入し、
   ``observation buffer`` に「書架A」を含む prose を流した状態で prompt を
   組むと、**過去 episode の recall_text が user prompt に現れる**

実 LLM 試走前の sanity check として CI で常時回す。
"""

from __future__ import annotations

# Phase 3 Step 3e-3 bulk migration: episode_store の player_id 経路撤去に
# 伴い、本ファイルの ``being_id`` 参照を deterministic な ``BeingId`` の
# 既定値で受ける (= テスト内で異なる player_id を使う箇所は個別に上書き)。
# BeingProvisioningService は ``being_w<world>_p<player>`` 形式を使う。
from ai_rpg_world.domain.being.value_object.being_id import (
    BeingId as _MIG_BeingId,
)

being_id = _MIG_BeingId("being_w1_p1")

from datetime import datetime, timezone
from pathlib import Path

import pytest


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _build_runtime(monkeypatch: pytest.MonkeyPatch, enabled: bool):
    """env を設定して runtime を作る共通ヘルパ。"""
    if enabled:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    else:
        monkeypatch.delenv("LLM_EPISODIC_ENABLED", raising=False)
    from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime

    return create_escape_game_runtime(_SCENARIO_PATH)


class TestSmokeOffByDefault:
    """env 未設定では従来挙動を完全に維持する (backward compat smoke)。"""

    def test_env_未設定なら_stack_は_None(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = _build_runtime(monkeypatch, enabled=False)
        assert runtime._episodic_stack is None

    def test_env_未設定での_do_move_は例外なく完走(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OFF 時に action を実行しても何も壊れない。"""
        runtime = _build_runtime(monkeypatch, enabled=False)
        # カイト = player_a を 入口広間 → 閲覧室 に移動
        kaito_id = runtime.get_player_ids()[0]
        runtime.do_move(kaito_id, "reading_room")
        # #404 修正後: do_move は travel 開始のみで return する非同期
        # セマンティクス。テストで「到着まで待つ」場合は advance_until_player_idle
        # で明示的に world tick を進める。
        runtime.advance_until_player_idle(kaito_id)
        assert runtime.get_player_spot_name(kaito_id) == "閲覧室"


class TestSmokeWriteSide:
    """env=1 で chunk coordinator が action 後に episode を書く。"""

    def test_env_1_で_action_の間に観測を挟むと_episode_が書かれる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """chunk boundary は (1) bucket に action が 2 件以上溜まり、
        (2) その時間範囲 [t0, t1] 内に ``schedules_turn=True`` の観測が含まれる
        ときに閉じる (= action 群の最中に重要な観測が来た = チャンクの自然な
        区切り)。

        最低限の boundary シナリオ:
        - カイト 1 回目の wait (action_t0)
        - リン → カイトのスポットへ移動 + speech (カイトの buffer に
          schedules_turn=True の observation が積まれる、occurred_t1)
        - カイト 2 回目の wait (action_t2)
          → after_action_recorded: bucket=[wait_t0, wait_t2], obs_slice は
            [t0, t2] 内に speech 観測あり → boundary close → episode write
        """
        runtime = _build_runtime(monkeypatch, enabled=True)
        stack = runtime._episodic_stack
        assert stack is not None

        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        player_ids = runtime.get_player_ids()
        # scenario は player_a=カイト (entrance_hall), player_b=リン (reading_room)
        kaito_id = player_ids[0]
        rin_id = player_ids[1]

        # PR #322 後続: MIN_ACTIONS_FOR_CLOSE=3 に引き上げ + schedules_turn を
        # salient から除外したため、smoke の最小シナリオを「カイトの 3 件 action +
        # 最終が spot 遷移 (scene_boundary=True)」に拡張する。これで:
        #   - bucket 3 action 達成で MIN ゲートを通過
        #   - 最終 move が SCENE_BOUNDARY_ACTION でクローズ → episode 書き込み
        runtime.do_move(rin_id, "entrance_hall")
        runtime.do_wait(kaito_id)                              # kaito act 1
        runtime.do_speech(rin_id, "カイト、こんにちは", SpeechChannel.SAY)
        runtime.do_wait(kaito_id)                              # kaito act 2
        runtime.do_move(kaito_id, "reading_room")              # kaito act 3 (scene_boundary)

        # カイトの store にエピソードが書き込まれている (= write 側が alive)
        episodes = stack.episode_store.list_recent_by_being(being_id, limit=20
        )
        assert len(episodes) > 0, (
            "env=1 で 3 action + scene_boundary を踏ませても episode が 1 件も "
            "書かれていない。chunk_coordinator フックが alive か確認すべき。"
        )

    def test_env_未設定での_move_では_当然_episode_は書かれない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """対照: OFF では stack 自体が無く、当然 episode も書かれない。"""
        runtime = _build_runtime(monkeypatch, enabled=False)
        # 一応 move しても stack=None なので何も書かれない
        runtime.do_move(runtime.get_player_ids()[0], "reading_room")
        assert runtime._episodic_stack is None

    def test_書かれた_episode_の_cue_に_unknown_tool_が出ない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``action`` 軸の cue は LLM tool 名 (``spot_graph_wait`` 等) で記録される。

        第20回実験で「episode_cues に常に ``action:unknown_tool`` が立つ」
        ノイズを観測した regression: ``_record_action_result`` が tool_name を
        受け取らず、``chunk_episode_draft_builder._tool_name_segment`` が
        ``None → "unknown_tool"`` に fallback していた。
        全 do_* 呼び出し側で tool_name を明示的に渡すよう修正したので、
        書かれた episode の cue に ``unknown_tool`` が現れないことを保証する。
        """
        runtime = _build_runtime(monkeypatch, enabled=True)
        stack = runtime._episodic_stack
        assert stack is not None

        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        player_ids = runtime.get_player_ids()
        kaito_id = player_ids[0]
        rin_id = player_ids[1]

        # PR #322 後続: MIN=3 + scene_boundary が必要 (詳細は上のテスト参照)
        runtime.do_move(rin_id, "entrance_hall")
        runtime.do_wait(kaito_id)
        runtime.do_speech(rin_id, "カイト、こんにちは", SpeechChannel.SAY)
        runtime.do_wait(kaito_id)
        runtime.do_move(kaito_id, "reading_room")  # scene_boundary

        episodes = stack.episode_store.list_recent_by_being(being_id, limit=20
        )
        assert len(episodes) > 0
        all_cues_canonical = [
            c.to_canonical() for ep in episodes for c in ep.cues
        ]
        assert "action:unknown_tool" not in all_cues_canonical, (
            f"episode cue に unknown_tool が混入: {all_cues_canonical}"
        )
        # 期待: spot_graph_wait などの実 tool 名が action 軸に乗っている
        assert any(
            c.startswith("action:spot_graph_") for c in all_cues_canonical
        ), f"action: 軸の tool name cue が立っていない: {all_cues_canonical}"


class TestSmokePromptBuilds:
    """env=1 で prompt 構築が完走する。"""

    def test_env_1_で_build_full_prompt_が_例外なく完走(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """passive_recall + noun_matcher が wire された状態で prompt を組んでも
        例外が出ないこと。messages 配列が空でない。"""
        runtime = _build_runtime(monkeypatch, enabled=True)
        kaito_id = runtime.get_player_ids()[0]
        runtime.do_move(kaito_id, "reading_room")
        prompt = runtime.build_full_prompt(kaito_id)
        assert "messages" in prompt
        assert len(prompt["messages"]) >= 2
        # system + user の content が非空
        for msg in prompt["messages"]:
            assert msg.get("content"), "messages の content が空"


class TestSmokeRecallSide:
    """過去 episode を store に注入し、prose に「書架A」を含む観測を流すと、
    その episode が prompt の user content に現れる (recall 側が alive)。"""

    def test_過去の書架A_episode_が_自由文_cue_経由で_prompt_に_recall_される(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """end-to-end recall smoke:

        1. env=1 で runtime を作成
        2. リン (player_b) の過去 episode (書架A 訪問) を store に直接注入
        3. 観測 buffer に「書架A」を含む prose の観測を流す
        4. リンの prompt を組むと、user message に過去 episode の recall_text が
           現れる
        """
        from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
        from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
        from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
        from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
        from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import EpisodicCueSource
        from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
        from ai_rpg_world.application.observation.contracts.dtos import (
            ObservationEntry,
            ObservationOutput,
        )

        runtime = _build_runtime(monkeypatch, enabled=True)
        stack = runtime._episodic_stack
        assert stack is not None

        # リン (player_b) の player_id を取得
        rin_id = None
        for spawn in runtime.scenario.player_spawns:
            if spawn.name == "リン":
                from ai_rpg_world.domain.player.value_object.player_id import (
                    PlayerId,
                )
                rin_id = PlayerId(spawn.player_id)
                break
        assert rin_id is not None, "リンが scenario に存在しない"

        # 書架A の spot_id を scenario から取得
        graph = runtime._spot_graph_repo.find_graph()
        shelf_a_spot_id = None
        for node in graph._spots.values():
            if node.name == "書架 A":
                shelf_a_spot_id = int(node.spot_id.value)
                break
        assert shelf_a_spot_id is not None, "書架 A が scenario に存在しない"

        # リンの過去 episode (書架A 訪問) を直接注入
        past_episode = SubjectiveEpisode(
            episode_id="smoke-past-shelf-a",
            player_id=int(rin_id.value),
            occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
            game_time_label=None,
            source=EpisodeSource(event_ids=("evt-smoke",)),
            location=EpisodeLocation(spot_id=shelf_a_spot_id),
            action=EpisodeAction(tool_name="spot_graph_travel_to"),
            who=("player_lin",),
            what="書架 A で『水』の断片語を見つけた",
            why=None,
            observed="書架 A",
            expected=None,
            outcome="ok",
            prediction_error=None,
            felt=None,
            interpreted=None,
            cues=(
                EpisodicCue(
                    axis="place_spot",
                    value=str(shelf_a_spot_id),
                    source=EpisodicCueSource.RUNTIME_CONTEXT,
                ),
            ),
            recall_text="SMOKE_RECALL_MARKER: 書架Aで水の断片語を見つけた",
        )
        # Phase 3 Step 3e-3: rin_id 用の being_id で put (= runtime の aux
        # provisioning で attach 済の Being を resolve して使う)
        rin_being = runtime._aux_being_resolver.resolve_being_id(
            runtime._aux_being_default_world_id, rin_id
        )
        assert rin_being is not None, "リンの Being が provision されていない"
        stack.episode_store.put_by_being(rin_being, past_episode)

        # リンの buffer に「書架A」を含む観測 prose を流す (SNS / speech 模倣)
        runtime._obs_buffer.append(
            rin_id,
            ObservationEntry(
                occurred_at=datetime.now(),
                output=ObservationOutput(
                    prose="カイトの声が聞こえる: 「リン、書架Aで待ってる！」",
                    structured={
                        "type": "speech_message",
                        "speaker": "カイト",
                        "content": "リン、書架Aで待ってる！",
                    },
                    observation_category="social",
                    schedules_turn=True,
                ),
                game_time_label=None,
            ),
        )

        # prompt を組んで、recall_text が user message に含まれることを確認
        prompt = runtime.build_full_prompt(rin_id)
        full_text = "\n".join(m.get("content", "") for m in prompt["messages"])
        assert "SMOKE_RECALL_MARKER" in full_text, (
            "観測 prose に「書架A」が含まれているのに、過去の書架A 訪問 episode の "
            "recall_text が prompt に現れていない。自由文 cue 抽出 → passive recall "
            "→ prompt 注入のどこかが切れている。"
        )


class TestSmokeMemoryRecallTool:
    """Issue #526 後続: ``memory_recall_episodes`` tool が end-to-end 配線されている。

    1. tool 定義が ``get_tool_definitions`` で expose される
    2. ``run_llm_auxiliary_tool`` 経由で handler が dispatch される
    3. 過去 episode が能動 recall で引ける
    """

    def test_tool_is_exposed_when_episodic_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """env=1 で episodic stack が wire されているとき、tool 定義に memory_recall_episodes が含まれる。"""
        runtime = _build_runtime(monkeypatch, enabled=True)
        names = {d.name for d in runtime.get_tool_definitions()}
        assert "memory_recall_episodes" in names

    def test_tool_is_not_exposed_when_episodic_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """env 未設定で episodic stack が wire されていないとき、memory_recall_episodes は出ない。"""
        runtime = _build_runtime(monkeypatch, enabled=False)
        names = {d.name for d in runtime.get_tool_definitions()}
        assert "memory_recall_episodes" not in names

    def test_run_llm_auxiliary_tool_dispatches_memory_recall(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``run_llm_auxiliary_tool`` で memory_recall_episodes を呼ぶと、過去 episode が返る。"""
        from datetime import datetime, timedelta, timezone

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

        runtime = _build_runtime(monkeypatch, enabled=True)
        stack = runtime._episodic_stack
        assert stack is not None

        # リン (player_b) の player_id を取得
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        rin_id = None
        for spawn in runtime.scenario.player_spawns:
            if spawn.name == "リン":
                rin_id = PlayerId(spawn.player_id)
                break
        assert rin_id is not None

        # 書架A spot_id を取得
        graph = runtime._spot_graph_repo.find_graph()
        shelf_a_spot_id = None
        for node in graph._spots.values():
            if node.name == "書架 A":
                shelf_a_spot_id = int(node.spot_id.value)
                break
        assert shelf_a_spot_id is not None

        # aux Being を attach (= run_llm_auxiliary_tool が中でやるが、test 内で直接 put するので先に解決)
        runtime._wire_auxiliary_tool_stack()
        runtime._aux_being_provisioning.ensure_attached(rin_id)
        rin_being = runtime._aux_being_resolver.resolve_being_id(
            runtime._aux_being_default_world_id, rin_id
        )
        assert rin_being is not None

        # 過去 episode を直接注入
        stack.episode_store.put_by_being(
            rin_being,
            SubjectiveEpisode(
                episode_id="recall-tool-shelf-a",
                player_id=int(rin_id.value),
                occurred_at=datetime.now(timezone.utc) - timedelta(hours=2),
                game_time_label=None,
                source=EpisodeSource(event_ids=("evt-recall-tool",)),
                location=EpisodeLocation(spot_id=shelf_a_spot_id),
                action=EpisodeAction(tool_name="spot_graph_travel_to"),
                who=("player_lin",),
                what="書架Aで断片語を見つけた",
                why=None,
                observed="書架A",
                expected=None,
                outcome="ok",
                prediction_error=None,
                felt=None,
                interpreted=None,
                cues=(
                    EpisodicCue(
                        axis="place_spot",
                        value=str(shelf_a_spot_id),
                        source=EpisodicCueSource.RUNTIME_CONTEXT,
                    ),
                ),
                recall_text="RECALL_TOOL_MARKER: 書架Aで断片語を見つけた",
            ),
        )

        # LLM が memory_recall_episodes を呼ぶシナリオを模倣
        result = runtime.run_llm_auxiliary_tool(
            rin_id,
            "memory_recall_episodes",
            {"about": "書架Aでのこと", "time_range": "today"},
        )
        assert result.success is True
        assert "RECALL_TOOL_MARKER" in result.message

    def test_returns_empty_message_when_no_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """過去 episode が無い状態で memory_recall_episodes を呼ぶと「思い出そうとしたが何も浮かばなかった」。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        runtime = _build_runtime(monkeypatch, enabled=True)
        rin_id = None
        for spawn in runtime.scenario.player_spawns:
            if spawn.name == "リン":
                rin_id = PlayerId(spawn.player_id)
                break
        assert rin_id is not None
        result = runtime.run_llm_auxiliary_tool(
            rin_id,
            "memory_recall_episodes",
            {"about": "存在しない過去"},
        )
        assert result.success is True
        assert "思い出そうとしたが何も浮かばなかった" in result.message


class TestSmokeSubjectiveServiceWiring:
    """``LLM_EPISODIC_SUBJECTIVE_ENABLED`` の配線挙動 (Issue #295 後続)。

    本クラスは「配線が正しく差分動作する」ことだけ確認する smoke。実 LLM 呼び出しは
    しない (LLM_CLIENT=stub なので LiteLLMClient にならず service 自体が無効化される
    のが本来の挙動。それを assert する)。

    第22回実験以降の方針変更: SUBJECTIVE_ENABLED は **既定 ON**。明示的に
    OFF にしたいときだけ ``LLM_EPISODIC_SUBJECTIVE_ENABLED=0`` を渡す。
    """

    def test_env_未設定でも_subjective_は_既定で_有効_だが_stub_LLM_では_silent_skip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SUBJECTIVE フラグ未設定でも既定 ON なので有効化を試みるが、stub LLM_CLIENT
        だと LiteLLMClient にならず service は wire されない (silent skip)。"""
        runtime = _build_runtime(monkeypatch, enabled=True)
        stack = runtime._episodic_stack
        assert stack is not None
        # 既定 ON でも stub のときは service が wire されない (= 安全な縮退)
        assert stack.chunk_coordinator._chunk_subjective_fields_service is None
        assert stack.chunk_coordinator._persona_block_provider is None

    def test_subjective_明示的に_0_なら_litellm_でも_配線されない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``LLM_EPISODIC_SUBJECTIVE_ENABLED=0`` で明示的に OFF にできる。

        LiteLLMClient が居ても subjective service は wire されない (テスト環境では
        実 LLM を叩かないので LiteLLMClient は通常使わないが、env 解決のみ検証)。
        """
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", "0")
        monkeypatch.delenv("LLM_CLIENT", raising=False)
        from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime

        runtime = create_escape_game_runtime(_SCENARIO_PATH)
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.chunk_coordinator._chunk_subjective_fields_service is None

    def test_subjective_既定_かつ_litellm_未指定なら_service_は_無効化(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_CLIENT=stub (default) のままだと LiteLLMClient にならないので、
        SUBJECTIVE_ENABLED 既定 ON でも service は wire されない (silent skip + info log)。"""
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.delenv("LLM_EPISODIC_SUBJECTIVE_ENABLED", raising=False)
        monkeypatch.delenv("LLM_CLIENT", raising=False)  # = stub default
        from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime

        runtime = create_escape_game_runtime(_SCENARIO_PATH)
        stack = runtime._episodic_stack
        assert stack is not None
        # stub のときは service が wire されないこと (= 安全な縮退)
        assert stack.chunk_coordinator._chunk_subjective_fields_service is None


class TestSmokeSubjectiveServiceMergesText:
    """``build_escape_episodic_stack`` に明示的に subjective service を渡したとき、
    chunk write 時に LLM のテキストで recall_text が上書きされる経路の smoke。

    実 LiteLLM は使わず、``IEpisodicChunkSubjectiveCompletionPort`` の stub を
    直接渡して挙動だけ確認する。
    """

    def test_subjective_service_注入時に_chunk_書き込みで_recall_text_が_LLM_文に_差し替わる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """draft の `compute_template_recall` 結果が、注入した stub の文字列で上書きされる。"""
        from typing import Any
        from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
            IEpisodicChunkSubjectiveCompletionPort,
        )
        from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
            EpisodicChunkSubjectiveFieldsService,
        )
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
        from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime
        from ai_rpg_world.application.escape_game.escape_episodic_wiring import (
            build_escape_episodic_stack,
        )

        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        runtime = create_escape_game_runtime(_SCENARIO_PATH)
        assert runtime._episodic_stack is not None

        class _StubPort(IEpisodicChunkSubjectiveCompletionPort):
            def complete_episode_subjective_json(
                self, messages: list[dict[str, Any]]
            ) -> dict[str, Any]:
                return {
                    "interpreted": "STUB_INTERPRETED",
                    "recall_text": "STUB_RECALL_TEXT_FROM_LLM",
                }

        subjective_service = EpisodicChunkSubjectiveFieldsService(_StubPort())
        # subjective_service 注入版で stack を組み直す (escape_game runtime の private
        # を差し替えるのは smoke なので OK)。
        runtime._episodic_stack = build_escape_episodic_stack(
            scenario=runtime.scenario,
            graph=runtime._spot_graph_repo.find_graph(),
            observation_buffer=runtime._obs_buffer,
            sliding_window_memory=runtime._sliding_window,
            action_result_store=runtime._action_result_store,
            being_attachment_resolver=runtime._aux_being_resolver,
            default_world_id=runtime._aux_being_default_world_id,
            chunk_subjective_fields_service=subjective_service,
            persona_block_provider=lambda pid: "ペルソナ片",
        )

        player_ids = runtime.get_player_ids()
        kaito_id, rin_id = player_ids[0], player_ids[1]
        # PR #322 後続: MIN=3 + scene_boundary を踏ませる最小シナリオ
        runtime.do_move(rin_id, "entrance_hall")
        runtime.do_wait(kaito_id)
        runtime.do_speech(rin_id, "こんにちは", SpeechChannel.SAY)
        runtime.do_wait(kaito_id)
        runtime.do_move(kaito_id, "reading_room")  # scene_boundary

        eps = runtime._episodic_stack.episode_store.list_recent_by_being(being_id, limit=20
        )
        assert len(eps) > 0
        recall_texts = [ep.recall_text for ep in eps]
        assert any(rt == "STUB_RECALL_TEXT_FROM_LLM" for rt in recall_texts), (
            f"subjective service 注入時に LLM の recall_text で上書きされていない: "
            f"{recall_texts}"
        )
        interpreteds = [ep.interpreted for ep in eps]
        assert any(it == "STUB_INTERPRETED" for it in interpreteds)


class TestSmokeAsyncSubjectiveSchedulerIntegration:
    """``ThreadPoolEpisodicSubjectiveScheduler`` を chunk_coordinator に注入し、
    chunk write 後にバックグラウンドで LLM が走り episode が上書きされる経路の
    smoke (PR #309)。"""

    def test_async_scheduler_経由で_chunk_書き込み後に_LLM_文で上書きされる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from typing import Any
        from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
            IEpisodicChunkSubjectiveCompletionPort,
        )
        from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
            EpisodicChunkSubjectiveFieldsService,
        )
        from ai_rpg_world.application.llm.services.episodic_subjective_completion_schedulers import (
            ThreadPoolEpisodicSubjectiveScheduler,
        )
        from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
            InMemorySubjectiveEpisodeStore,
        )
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
        from ai_rpg_world.application.escape_game.escape_game_runtime import create_escape_game_runtime
        from ai_rpg_world.application.escape_game.escape_episodic_wiring import (
            build_escape_episodic_stack,
        )

        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        runtime = create_escape_game_runtime(_SCENARIO_PATH)

        class _StubPort(IEpisodicChunkSubjectiveCompletionPort):
            def complete_episode_subjective_json(
                self, messages: list[dict[str, Any]]
            ) -> dict[str, Any]:
                return {
                    "interpreted": "ASYNC_INTERPRETED",
                    "recall_text": "ASYNC_RECALL_TEXT_FROM_WORKER",
                }

        shared_store = InMemorySubjectiveEpisodeStore()
        service = EpisodicChunkSubjectiveFieldsService(_StubPort())
        scheduler = ThreadPoolEpisodicSubjectiveScheduler(
            service,
            shared_store,
            max_workers=1,
            being_attachment_resolver=runtime._aux_being_resolver,
            default_world_id=runtime._aux_being_default_world_id,
        )
        # scheduler 経由の stack で差し替える
        runtime._episodic_stack = build_escape_episodic_stack(
            scenario=runtime.scenario,
            graph=runtime._spot_graph_repo.find_graph(),
            observation_buffer=runtime._obs_buffer,
            sliding_window_memory=runtime._sliding_window,
            action_result_store=runtime._action_result_store,
            being_attachment_resolver=runtime._aux_being_resolver,
            default_world_id=runtime._aux_being_default_world_id,
            subjective_completion_scheduler=scheduler,
            persona_block_provider=lambda pid: "ペルソナ片",
            episode_store=shared_store,
        )

        player_ids = runtime.get_player_ids()
        kaito_id, rin_id = player_ids[0], player_ids[1]
        # PR #322 後続: MIN=3 + scene_boundary を踏ませる最小シナリオ
        runtime.do_move(rin_id, "entrance_hall")
        runtime.do_wait(kaito_id)
        runtime.do_speech(rin_id, "こんにちは", SpeechChannel.SAY)
        runtime.do_wait(kaito_id)
        runtime.do_move(kaito_id, "reading_room")  # scene_boundary
        # ここまでは chunk_coordinator が draft を put 済み (= テンプレ文)。
        # scheduler の worker がまだ走っている可能性があるので shutdown で drain。
        try:
            runtime.shutdown(timeout=3.0)
        finally:
            # shutdown を 2 回呼んでも安全
            runtime.shutdown(timeout=0.1)

        eps = shared_store.list_recent_by_being(being_id, 20)
        assert len(eps) > 0
        recall_texts = [ep.recall_text for ep in eps]
        assert any(rt == "ASYNC_RECALL_TEXT_FROM_WORKER" for rt in recall_texts), (
            f"非同期 scheduler 経由で LLM の recall_text 上書きが完了していない: "
            f"{recall_texts}"
        )
