"""Quality-check シナリオ ``yesterday_v1``: 「昨日何してた?」に答えられるか。

Issue #526 で議論した「自伝的時系列」「能動想起」の不在を、現状の prompt
構造で見るための baseline harness。LLM は呼ばず prompt 内容を ``.txt``
にダンプする。

シナリオ要旨:
- forbidden_library scenario を runtime として使い、リン (player_b) を題材にする
- Day 1 (= "昨日") にリンが閲覧室と書架 A で活動した episode を episode
  store に直接注入する
- Day 2 朝に、カイトが speech tool で「リン、昨日何してた?」と質問する
  観測を流す
- リンの prompt を組み、user message を ``docs/quality_checks/<id>.prompt.txt``
  に書き出す

2 variant:
- ``in_window``: 注入した episode を sliding window にも append する。
  「短期記憶 section に過去 episode が並んでいる → narrative に再構成
  できるか」を見るための control
- ``out_of_window``: episode store にのみ書き、sliding window には Day 2
  朝の観測しか入らないようにする。「passive recall 経路で過去を引けるか」
  を見る本番側
"""

from __future__ import annotations

# 循環 import 回避の warm-up (= DefaultActionResultStore を先に import
# しておくと、後続の observation contracts 経由の chain が解ける)。
# 詳細は CLAUDE.md "Parallel Branch Note" 参照。
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
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


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)

_DUMP_DIR = Path(__file__).resolve().parents[2] / "docs" / "quality_checks"


def _build_runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    from ai_rpg_world.application.escape_game.escape_game_runtime import (
        create_escape_game_runtime,
    )

    return create_escape_game_runtime(_SCENARIO_PATH)


def _resolve_player_id(runtime, name: str) -> PlayerId:
    for spawn in runtime.scenario.player_spawns:
        if spawn.name == name:
            return PlayerId(spawn.player_id)
    raise AssertionError(f"player {name!r} not found in scenario")


def _resolve_spot_id(runtime, name: str) -> int:
    graph = runtime._spot_graph_repo.find_graph()
    for node in graph._spots.values():
        if node.name == name:
            return int(node.spot_id.value)
    raise AssertionError(f"spot {name!r} not found in scenario")


def _make_past_episode(
    *,
    episode_id: str,
    player_id: int,
    occurred_at: datetime,
    spot_id: int,
    what: str,
    recall_text: str,
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=player_id,
        occurred_at=occurred_at,
        game_time_label=None,
        source=EpisodeSource(event_ids=(f"evt-{episode_id}",)),
        location=EpisodeLocation(spot_id=spot_id),
        action=EpisodeAction(tool_name="spot_graph_travel_to"),
        who=("player_lin",),
        what=what,
        why=None,
        observed=what,
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(
            EpisodicCue(
                axis="place_spot",
                value=str(spot_id),
                source=EpisodicCueSource.RUNTIME_CONTEXT,
            ),
        ),
        recall_text=recall_text,
    )


def _dump_prompt(variant: str, prompt: dict) -> Path:
    """prompt を ``docs/quality_checks/yesterday_v1_<variant>.prompt.txt`` に
    決定論的に書き出す (git diff で前回 PR との変化が見える)。"""
    _DUMP_DIR.mkdir(parents=True, exist_ok=True)
    path = _DUMP_DIR / f"yesterday_v1_{variant}.prompt.txt"
    parts: list[str] = []
    parts.append(f"# yesterday_v1 / {variant}\n")
    parts.append(
        "# このファイルは tests/quality/test_yesterday_v1.py から再生成される。\n"
        "# 手で編集しないこと。baseline 所感は yesterday_v1_baseline.md に書く。\n\n"
    )
    for i, msg in enumerate(prompt.get("messages", [])):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        parts.append(f"=== messages[{i}] role={role} ===\n{content}\n")
    parts.append("\n=== tools ===\n")
    for tool in prompt.get("tools", []) or []:
        if isinstance(tool, dict):
            fn = tool.get("function", {})
            name = fn.get("name") if isinstance(fn, dict) else None
            parts.append(f"- {name or tool.get('name') or '?'}\n")
        else:
            parts.append(f"- {tool}\n")
    path.write_text("".join(parts), encoding="utf-8")
    return path


@pytest.mark.quality
class TestYesterdayV1Baseline:
    """``yesterday_v1`` シナリオの 2 variant を回し、prompt を dump する。

    LLM は呼ばない。失敗するのは「prompt が組めない」「観測注入が
    壊れた」など runtime レベルの regression のみ。質感の判断は dump
    された ``.prompt.txt`` を人が読む。
    """

    def _setup_past_episodes(self, runtime, rin_id: PlayerId) -> list[SubjectiveEpisode]:
        """Day 1 (= 昨日) のリンの活動 episode を 2 件作って store に書く。

        - 昼: 閲覧室で見習い司書の覚書を読んだ
        - 夕方: 書架 A で『水』の断片語を見つけた
        """
        reading_room_id = _resolve_spot_id(runtime, "閲覧室")
        shelf_a_id = _resolve_spot_id(runtime, "書架 A")
        # 「昨日」を表現するため now の 1 日前を使う。runtime の sliding
        # window の最古 entry が今日になるよう、今日の観測を後で別途流す。
        yesterday_noon = datetime.now(timezone.utc) - timedelta(hours=18)
        yesterday_evening = datetime.now(timezone.utc) - timedelta(hours=14)

        episodes = [
            _make_past_episode(
                episode_id="yesterday-noon-reading",
                player_id=int(rin_id.value),
                occurred_at=yesterday_noon,
                spot_id=reading_room_id,
                what="閲覧室で見習い司書の覚書を読んだ",
                recall_text=(
                    "QUALITY_MARKER_NOON: 昨日の昼、閲覧室で見習い司書の覚書を読んだ。"
                ),
            ),
            _make_past_episode(
                episode_id="yesterday-evening-shelf-a",
                player_id=int(rin_id.value),
                occurred_at=yesterday_evening,
                spot_id=shelf_a_id,
                what="書架 A で『水』の断片語を見つけた",
                recall_text=(
                    "QUALITY_MARKER_EVENING: 昨日の夕方、書架Aで『水』の断片語を見つけた。"
                ),
            ),
        ]
        rin_being = runtime._aux_being_resolver.resolve_being_id(
            runtime._aux_being_default_world_id, rin_id
        )
        assert rin_being is not None
        stack = runtime._episodic_stack
        assert stack is not None
        for ep in episodes:
            stack.episode_store.put_by_being(rin_being, ep)
        return episodes

    def _push_kaito_question(self, runtime, rin_id: PlayerId) -> None:
        """Day 2 朝、カイトの質問を観測 buffer に投入する。"""
        runtime._obs_buffer.append(
            rin_id,
            ObservationEntry(
                occurred_at=datetime.now(timezone.utc),
                output=ObservationOutput(
                    prose="カイトの声: 「リン、昨日何してた?」",
                    structured={
                        "type": "speech_message",
                        "speaker": "カイト",
                        "content": "リン、昨日何してた?",
                    },
                    observation_category="social",
                    schedules_turn=True,
                ),
                game_time_label=None,
            ),
        )

    def _push_yesterday_observations_to_sliding_window(
        self, runtime, rin_id: PlayerId, episodes: list[SubjectiveEpisode]
    ) -> None:
        """in_window variant 用: 過去 episode 相当の観測を obs buffer に
        投入する (= drain で sliding window に乗る → 「最近の出来事」
        section に出る)。"""
        for ep in episodes:
            runtime._obs_buffer.append(
                rin_id,
                ObservationEntry(
                    occurred_at=ep.occurred_at,
                    output=ObservationOutput(
                        prose=ep.what,
                        structured={
                            "type": "self_action_log",
                            "what": ep.what,
                        },
                        observation_category="self_only",
                        schedules_turn=False,
                    ),
                    game_time_label=None,
                ),
            )

    def test_in_window_baseline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """in_window variant: Day 1 episode 相当の観測も sliding window に
        乗っている前提で、prompt の中身を見る。短期記憶 section に
        昨日の活動が見えるはずだが、それを narrative にまとめられるかは
        別問題。"""
        runtime = _build_runtime(monkeypatch)
        rin_id = _resolve_player_id(runtime, "リン")
        episodes = self._setup_past_episodes(runtime, rin_id)
        # 過去観測も sliding window に流す (= "in window")
        self._push_yesterday_observations_to_sliding_window(
            runtime, rin_id, episodes
        )
        # Day 2 朝のカイトの質問
        self._push_kaito_question(runtime, rin_id)
        prompt = runtime.build_full_prompt(rin_id)
        dump_path = _dump_prompt("in_window", prompt)
        # 基本構造の sanity check (= prompt build が壊れたら検知)
        assert dump_path.exists()
        messages = prompt.get("messages", [])
        assert len(messages) >= 2, "system + user は最低必要"
        user_content = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )
        assert "昨日何してた" in user_content, (
            "カイトの質問が user prompt に届いていない"
        )

    def test_out_of_window_baseline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """out_of_window variant: 過去 episode は episode store にだけ
        存在し、sliding window には Day 2 朝の観測 (= カイトの質問) しか
        無い。passive recall が cue マッチで過去 episode を引けるかが
        試金石。

        現状の予想 (PR8 #530 直後): カイトの発話には「閲覧室」「書架A」
        「読んだ」「断片語」がいずれも含まれていないため、noun_matcher
        経由でも entity / place cue が立たず、recall は 0 件で着地する
        可能性が高い。dump された prompt の "関連する記憶" section が
        空であれば、Issue #526 の "時間軸の不在" + "agent-driven 想起の
        不在" がここに刺さっていることが具体的に確認できる。
        """
        runtime = _build_runtime(monkeypatch)
        rin_id = _resolve_player_id(runtime, "リン")
        self._setup_past_episodes(runtime, rin_id)
        # 過去観測は sliding window に流さない (= "out of window")
        self._push_kaito_question(runtime, rin_id)
        prompt = runtime.build_full_prompt(rin_id)
        dump_path = _dump_prompt("out_of_window", prompt)
        assert dump_path.exists()
        messages = prompt.get("messages", [])
        assert len(messages) >= 2
        user_content = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )
        assert "昨日何してた" in user_content
