"""世界の前提が、手書きではなくシナリオのデータから組み立てられることを保証する。

## 写しは腐る

station_drill の ``llm_public_intro`` には、シナリオが既に持っている事実が
手で写されていた。#938 で players / spots / game_end_conditions を変えた
とき、そちらが更新されず **4 箇所ずれた**。

    「参加者 4 人のうち 1 人がインポスター」  → 実際は 5 人 / 1 人
    「クルーの勝利: タスクをすべて終える」    → 実際は 4 個中 3 個
    「タスクは 3 つ」「3 つすべて終える」     → 実際は 4 つ / 3 つ必要
    機関室の発電機がタスク一覧に無い

実 run 009 のエージェントは**存在しない世界の前提で推論していた**。

## 地図をシステムプロンプトに置く

Among Us では会議中も地図を見られる。**消えるのは操作であって、空間の
知識ではない。** 見取り図は run 中変わらないので、システムプロンプトに
置けばプレフィックスキャッシュ (設計判断 #1) に載り、実質ただで常に見える。
「会議のときは地図を出す」というフェーズ分岐を engine に書かずに済む。

移動 tick を出すのが要点。アリバイの検証がこれで初めて可能になる。
run 009 でインポスターが時刻を並べて弁明していたが、**検証する材料が誰にも
無かった**。

## 既定では出さない

初期は閉じている通路を持つシナリオが 11 本ある (abandoned_hospital は
16 部屋中 10 通路)。無条件に出すと鍵の向こうの部屋が最初から見え、探索して
見つける体験がその世界から消える。**世界によって要否が反転するので宣言に
する。**
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_rpg_world.application.llm.services.world_briefing import (
    build_duty_roster_text,
    build_faction_summary_text,
    build_own_state_display_names,
    build_world_map_text,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_DRILL = _SCENARIOS / "station_drill.json"
#: 初期に閉じた通路を持つ世界。地図を出すと鍵の向こうが見える。
_WITH_LOCKED_DOORS = _SCENARIOS / "survival_island_v4_coop.json"


def _system_prompt(path: Path) -> str:
    runtime = create_world_runtime(path)
    return (
        runtime._world_llm_system_prompts_by_player_id.get(1)
        or runtime._world_llm_system_prompt
    )


class TestTheFactsMatchTheData:
    """書かれている事実が、シナリオのデータと一致する。"""

    def test_the_headcount_is_counted_not_written(self) -> None:
        """人数がデータの人数と一致する。

        **手で書くと、人を 1 人足したときに必ず置き去りになる。**
        #938 で 4 人のまま残っていた。
        """
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        expected = len(raw["players"])

        assert f"参加者は {expected} 人" in _system_prompt(_DRILL)

    def test_every_task_owner_is_listed_with_their_place(self) -> None:
        """全クルーの担当と、その場所が載る。

        #938 で 4 つ目の点検 (機関室の発電機) が一覧から漏れていた。
        """
        prompt = _system_prompt(_DRILL)

        for name, place in (
            ("モリ", "集会室"),
            ("セナ", "連絡通路"),
            ("アオイ", "物資庫"),
            ("ハギ", "機関室"),
        ):
            assert name in prompt
            assert place in prompt

    def test_the_old_hand_written_counts_are_gone(self) -> None:
        """古い手書きの数字が残っていない。

        消し忘れると、生成した正しい数字と**並んで矛盾する**。読み手は
        どちらを信じてよいか分からない。
        """
        prompt = _system_prompt(_DRILL)

        for stale in ("参加者 4 人", "3 つすべて終える", "タスクをすべて終える"):
            assert stale not in prompt, stale

    def test_the_objective_matches_the_declared_task_threshold(self) -> None:
        """目的文のタスク総数と必要数は、実際の終了条件と一致する。"""
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        task_end = next(
            condition
            for condition in raw["game_end_conditions"]["win"]
            if condition["type"] == "FLAGS_SET_AT_LEAST"
        )
        total = len(task_end["required_flags"])
        required = task_end["min_set_count"]

        objective = raw["metadata"]["llm_objective_text"]
        assert f"タスクは {total} つ" in objective
        assert f"うち {required} つ" in objective

    def test_every_initially_dark_room_is_named_in_the_llm_copy(self) -> None:
        """初期状態で暗い部屋は、公開導入と目的文の暗所一覧から漏れない。"""
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        dark_rooms = {
            spot["name"]
            for spot in raw["spots"]
            if (spot.get("atmosphere") or {}).get("lighting") == "DARK"
        }
        assert dark_rooms, "暗所が 0 件なら、この試験は何も確かめていない"

        public_intro = raw["metadata"]["llm_public_intro"]
        objective = raw["metadata"]["llm_objective_text"]
        for room in dark_rooms:
            assert room in public_intro, room
            assert room in objective, room


class TestTheMapIsThereForSpatialReasoning:
    """地図が、空間の推論に使える形で載る。"""

    def test_the_rooms_and_their_neighbours_are_listed(self) -> None:
        """部屋と行き先が並ぶ。"""
        prompt = _system_prompt(_DRILL)

        assert "【この場所の造り】" in prompt
        for room in ("集会室", "連絡通路", "物資庫", "機関室"):
            assert room in prompt

    def test_travel_time_is_shown_in_the_worlds_own_clock(self) -> None:
        """移動にかかる時間が、世界の時計と同じ単位で出る。

        **これが無いとアリバイを検証できない。** 「集会室から物資庫は
        10 分かかる」を全員が知っていて初めて、時刻の食い違いを突ける。

        最初は `物資庫 2` と数字だけを並べ、脚注で「tick 数」と説明して
        いた。**数字より後ろに説明があるので、読む時点では意味が分からない。**
        個数にも識別子にも読める。しかも tick は engine の語彙で、世界の
        中に無い単位 (#892)。

        エージェントは毎ターン「現在時刻: 深夜 0:05」を見ている。そこに
        揃える。
        """
        prompt = _system_prompt(_DRILL)
        line = next(l for l in prompt.splitlines() if l.strip().startswith("集会室"))

        assert "物資庫 まで 10 分" in line
        assert "tick" not in line

    def test_the_unit_matches_the_clock_the_agent_sees(self) -> None:
        """地図の分数が、時刻表示の進み方と一致する。

        **別々に計算すると静かにずれる。** 地図は「5 分」なのに時計が
        1 tick で 15 分進む世界では、アリバイの検算が全部狂う。
        """
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        runtime = create_world_runtime(_DRILL)

        def _clock() -> str:
            return next(
                l for l in runtime.build_observation(PlayerId(1)).splitlines()
                if "現在時刻" in l
            )

        before = _clock()
        runtime.advance_tick()
        after = _clock()

        # 0:00 -> 0:05 のように 5 分進む。地図の最短も 5 分。
        assert "0:00" in before and "0:05" in after

    def test_a_two_way_door_is_not_listed_twice(self) -> None:
        """双方向の通路が、同じ行き先を 2 度並べない。

        両向きが別々に返ってくるので、素直に list へ足すと重複する。
        実際に最初の実装がそうで「機関室 1 / 機関室 1 / 連絡通路 1 / …」と
        出ていた。
        """
        prompt = _system_prompt(_DRILL)
        line = next(l for l in prompt.splitlines() if l.strip().startswith("連絡通路"))

        assert line.count("集会室") == 1

    def test_the_shortest_route_is_the_one_shown(self) -> None:
        """同じ相手へ複数の経路があるとき、短いほうが載る。

        アリバイの検証に使う値なので、**最短で何 tick かかるか**が要る。
        遠回りのほうを載せると「1 tick で着けるはずがない」という誤った
        指摘が成り立ってしまう。
        """

        class _Spot:
            def __init__(self, sid, name):
                self.spot_id, self.name, self.atmosphere = sid, name, None

        class _Conn:
            def __init__(self, a, b, t):
                self.from_spot_id, self.to_spot_id = a, b
                self.travel_ticks, self.is_bidirectional = t, True

        text = build_world_map_text(
            [_Spot("a", "手前"), _Spot("b", "奥")],
            # **短いほうを先に置く。** 逆にすると「最後に見た値を採る」実装
            # でも通ってしまい、テストが空振りする。
            [_Conn("a", "b", 2), _Conn("a", "b", 5)],
        )

        assert "奥 まで 2 手ぶん" in text
        assert "5 手ぶん" not in text

    def test_raw_engine_words_are_absent(self) -> None:
        """engine の識別子が出ない (#892)。

        役割キーも明るさの enum も、読み手には意味が無い。
        """
        prompt = _system_prompt(_DRILL)

        for raw in ("crew", "keeper", "BRIGHT", "DARK", "weather", "wiring"):
            assert raw not in prompt, raw


class TestWorldsThatDoNotDeclareIt:
    """宣言していない世界の挙動は変わらない。"""

    def test_a_world_with_locked_doors_gets_no_map(self) -> None:
        """初期に閉じた通路を持つ世界には地図が出ない。

        **鍵の向こうの部屋が最初から見えると、探索の意味が消える。**
        """
        assert "【この場所の造り】" not in _system_prompt(_WITH_LOCKED_DOORS)

    def test_the_default_is_off(self, tmp_path) -> None:
        """宣言が無ければ載せない。"""
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        raw["metadata"].pop("show_world_map", None)
        path = tmp_path / "no_map.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        assert "【この場所の造り】" not in _system_prompt(path)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            pytest.param("show_world_map", "true", id="map_flag_as_string"),
            pytest.param("role_labels", ["crew"], id="labels_as_list"),
            pytest.param("role_labels", {"crew": ""}, id="empty_label"),
        ],
    )
    def test_a_malformed_declaration_is_rejected(self, tmp_path, field, value) -> None:
        """書き方の間違いは読み込み時に落とす。"""
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        raw["metadata"][field] = value
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        with pytest.raises(ScenarioLoadError):
            ScenarioLoader().load_from_file(path)


class TestSectionsVanishWhenTheWorldLacksTheConcept:
    """その世界に無い概念は 1 行も出さない。"""

    def test_no_duty_section_without_duties(self) -> None:
        """担当を宣言していない世界に、割り当ての節が出ない。"""

        class _Player:
            initial_state = {"role": "crew"}
            name = "誰か"

        assert build_duty_roster_text([_Player()], [], {}) == ""

    def test_no_faction_line_with_a_single_role(self) -> None:
        """役割が 1 種類しか無い世界に、内訳の行が出ない。

        全員が同じ側なら「内訳」に意味が無い。
        """

        class _Player:
            initial_state = {"role": "crew"}

        assert build_faction_summary_text([_Player(), _Player()]) == ""

    def test_no_map_without_spots(self) -> None:
        """部屋が無ければ地図も出ない。"""
        assert build_world_map_text([], []) == ""

    def test_counts_are_shown_even_without_labels(self) -> None:
        """呼び名の宣言が無くても、人数だけは伝える。

        呼び名が無いからといって黙ると、**何人いる世界かも分からなくなる**。
        engine のキーを出すよりは、人数だけのほうがよい。
        """

        class _Crew:
            initial_state = {"role": "crew"}

        class _Other:
            initial_state = {"role": "keeper"}

        text = build_faction_summary_text([_Crew(), _Other()])

        assert "参加者は 2 人" in text
        assert "keeper" not in text


class TestDutyStateDisplayFallbacks:
    """担当の場所や物体名が欠けても、入口 action_name つきの表示を残す。"""

    @staticmethod
    def _interaction(action_name, display_label="気象を記録する"):
        condition = SimpleNamespace(required_state={"duty": "weather"})
        return SimpleNamespace(
            action_name=action_name,
            display_label=display_label,
            preconditions=(condition,),
        )

    @pytest.mark.parametrize(
        ("spot_name", "object_name", "expected"),
        (
            ("集会室", "", '気象を記録する (集会室 → "log_weather")'),
            ("", "気象記録簿", '気象を記録する ("log_weather")'),
        ),
    )
    def test_missing_names_reduce_detail_without_hiding_the_duty(
        self, spot_name, object_name, expected
    ) -> None:
        """物体名が無ければ場所へ、場所も無ければ入口名だけへ縮退する。"""
        interaction = self._interaction("log_weather")
        obj = SimpleNamespace(name=object_name, interactions=(interaction,))
        spot = SimpleNamespace(spot_id="internal_hall", name=spot_name)
        interior = SimpleNamespace(objects=(obj,))

        names = build_own_state_display_names(
            [spot], {spot.spot_id: interior}, role_labels={}
        )

        assert names["duty=weather"] == ("担当", expected)

    @pytest.mark.parametrize(
        "later_action", ("log_weather_2", "log_weather_3", "log_weather_pretend")
    )
    def test_later_steps_are_ignored_even_when_declared_before_the_entry(
        self, later_action
    ) -> None:
        """宣言順にかかわらず、途中段・仕上げ・偽装でなく入口名を表示する。"""
        later = self._interaction(later_action, "後続の表示")
        entry = self._interaction("log_weather")
        obj = SimpleNamespace(
            name="気象記録簿",
            interactions=(later, entry),
        )
        spot = SimpleNamespace(spot_id="hall", name="集会室")
        interior = SimpleNamespace(objects=(obj,))

        names = build_own_state_display_names(
            [spot], {spot.spot_id: interior}, role_labels={}
        )

        assert names["duty=weather"] == (
            "担当",
            '気象を記録する (集会室の気象記録簿 → "log_weather")',
        )
