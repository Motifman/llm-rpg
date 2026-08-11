"""会議と投票の決まりが、engine の実装から書き起こされて全員に伝わる。

## 写した規則は、実装とずれる

station_drill は決まりを ``llm_public_intro`` に手で写していた。

    投票は最多票の 1 人が追放される。同数なら誰も追放されない。
    棄権も 1 票として数える。

素直に読めば「1 票入った人が追放される」。**実装はそう動かない。**
``resolve_vote`` は最多票が棄権の数を **上回る** ことを求める。

実 run 011 はこうなった。クゼ 1 票・棄権 2 票 → **誰も追放されなかった**。
モリはインポスターを正しく当てていた。

    クゼが死体を二つも見つけたと言いながら棚卸しは進んでいない。

ハギの独白が、そのまま欠落の証拠になっている。

    確証がないまま名指しはできない。棄権だ。

**自分の棄権が犯人を守ることを知らないまま棄権した。** 文から導けない以上、
これは推理力の問題ではない。

## 人数も写されていた

インポスターのペルソナに「他の 3 人はクルーで」とあった。実際は 4 人。
#949 でルール節はデータから生成するようにしたが、ペルソナの本文は手書きの
まま残り、**同じプロンプトの中で矛盾していた**。#938 で人を 1 人増やした
ときの置き去りが 5 箇所目。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.world_briefing import (
    build_meeting_rules_text,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from tests.demos.station_drill_lighting_helpers import darken_spot
from ai_rpg_world.domain.world_graph.service.vote_tally import resolve_vote
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIOS = Path(__file__).resolve().parents[2] / "data" / "scenarios"
_DRILL = _SCENARIOS / "station_drill.json"
#: 話し合いの仕組みを宣言していない世界。
_WITHOUT_MEETING = _SCENARIOS / "survival_island_v3_coop.json"
_ABSTENTION_COST = (
    "棄権が誰も追放しない結果につながれば、"
    "襲う者には次に襲える機会が残る"
)


def _system_prompt(path: Path, player_id: int = 1) -> str:
    runtime = create_world_runtime(path)
    return (
        runtime._world_llm_system_prompts_by_player_id.get(player_id)
        or runtime._world_llm_system_prompt
    )


class TestTheVotingRulesReachEveryone:
    """投票の決まりが、全員のシステムプロンプトに載る。"""

    def test_the_section_is_there(self) -> None:
        """話し合いを宣言した世界に、決まりの節が出る。"""
        assert "【話し合いと投票の決まり】" in _system_prompt(_DRILL)

    def test_abstaining_is_told_to_shield_the_accused(self) -> None:
        """棄権が名指しの最多と並ぶか上回ると追放されない、と書いてある。

        **run 011 でこれだけが抜けていた。** 「棄権も 1 票として数える」
        までは書いてあったが、そこから帰結は導けない。
        """
        prompt = _system_prompt(_DRILL)

        assert "棄権の数が名指しの最多と並ぶか上回ると、誰も追放されない" in prompt

    def test_abstention_is_explained_as_a_choice_with_a_consequence(self) -> None:
        """棄権で追放を止めると、襲う者に次の機会が残ると説明する。

        run 016 / 017 のクルーは、棄権を「確信がないときに何もしない」
        選択として扱い、誰も追放しない場合の代償を判断理由に載せなかった。
        投票先を指示せず、棄権が生む結果だけを集計規則の隣で伝える。
        """
        text = build_meeting_rules_text(meeting_enabled=True)

        assert _ABSTENTION_COST in text

    def test_the_abstention_consequence_reaches_the_real_prompt(self) -> None:
        """生成した棄権の代償が、station_drill の実 prompt に届く。"""
        assert _ABSTENTION_COST in _system_prompt(_DRILL)

    def test_the_words_match_what_the_tally_actually_does(self) -> None:
        """書いてある帰結が、集計の実装と一致する。

        **文だけを見るテストは、実装が変わった日に嘘を守る。** run 011 の
        再現 (1 票対棄権 2 票) を実際に集計して、誰も追放されないことを
        確かめる。ここが崩れたら文も直す必要がある。
        """
        mori, hagi, kuze = PlayerId(1), PlayerId(5), PlayerId(3)
        ballots = {mori: kuze, hagi: None, kuze: None}

        result = resolve_vote(ballots)

        assert result.counts == {kuze: 1}
        assert result.skip_count == 2
        assert result.ejected_player_id is None

    def test_a_split_vote_ejects_nobody(self) -> None:
        """名指しが割れたときも追放されない、と書いてあり、実装もそうである。"""
        a, b, c, d = (PlayerId(i) for i in (1, 2, 3, 4))

        result = resolve_vote({a: c, b: d})

        assert "名指しが割れて最多が複数居るときも、誰も追放されない" in _system_prompt(
            _DRILL
        )
        assert result.ejected_player_id is None

    def test_a_clear_majority_still_ejects(self) -> None:
        """名指しが棄権を上回れば追放される。

        **「常に追放されない」でも上の 2 件は通る**ので、追放される側を
        必ず一緒に見る。
        """
        a, b, c = (PlayerId(i) for i in (1, 2, 3))

        result = resolve_vote({a: c, b: c})

        assert result.ejected_player_id == c


class TestTheNumbersUseTheWorldsOwnClock:
    """持ち時間が、世界の時計と同じ単位で出る。"""

    def test_the_limits_are_shown_in_minutes(self) -> None:
        """打ち切り・沈黙・再招集の長さが分で出る。

        シナリオの宣言は 6 / 3 / 6 で、1 手番 5 分の世界なので 30 / 15 / 30。
        """
        prompt = _system_prompt(_DRILL)

        assert "話し合いには 30 分の持ち時間がある" in prompt
        assert "誰も口を開かない時間が 15 分続くと" in prompt
        assert "次に集まれるまで 30 分かかる" in prompt

    def test_the_engines_own_unit_never_appears(self) -> None:
        """決まりの節に tick が出ない (#892)。"""
        prompt = _system_prompt(_DRILL)
        section = prompt[prompt.index("【話し合いと投票の決まり】") :]
        section = section[: section.index("\n\n")] if "\n\n" in section else section

        assert "tick" not in section

    def test_a_world_without_a_clock_counts_turns_instead(self) -> None:
        """分に直せない世界では「手番 N 回ぶん」と書く。

        裸の数だけを置くと、個数にも識別子にも読める (#949 で地図が
        踏んだ形)。
        """
        text = build_meeting_rules_text(
            meeting_enabled=True, tick_limit=4, minutes_per_tick=None
        )

        assert "手番 4 回ぶん" in text
        assert "tick" not in text


class TestSilenceWhereTheConceptIsAbsent:
    """その世界に無い決まりは 1 行も出さない。"""

    def test_a_world_without_meetings_gets_no_section(self) -> None:
        """話し合いを宣言していない世界に、節が出ない。"""
        assert "【話し合いと投票の決まり】" not in _system_prompt(_WITHOUT_MEETING)

    def test_a_world_without_meetings_gets_no_abstention_consequence(self) -> None:
        """話し合いの無い世界に、棄権の代償だけが漏れ出さない。"""
        text = build_meeting_rules_text(meeting_enabled=False)

        assert _ABSTENTION_COST not in text

    def test_undeclared_limits_get_no_line(self) -> None:
        """宣言していない調整値の行は出ない。

        既定値を勝手に書くと、**その世界に無い決まりを教えることになる**。
        """
        text = build_meeting_rules_text(meeting_enabled=True)

        assert "持ち時間" not in text
        assert "口を開かない" not in text
        assert "次に集まれるまで" not in text
        # 集計の決まりは調整値と無関係なので、必ず出る。
        assert "棄権" in text


class TestTheHandWrittenCopiesAreGone:
    """シナリオに残った写しが、生成した文と並んで矛盾しない。"""

    def test_the_scenario_no_longer_states_the_tally_rule(self) -> None:
        """集計の決まりがシナリオ本文から消えている。

        消し忘れると、生成した正しい文と**並んで食い違う**。読み手は
        どちらを信じてよいか分からない。
        """
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        intro = raw["metadata"]["llm_public_intro"]

        for stale in ("最多票の 1 人が追放される", "話し合いには制限時間がある"):
            assert stale not in intro, stale

    def test_no_persona_writes_down_a_headcount(self) -> None:
        """ペルソナ本文に参加者の人数が書かれていない。

        インポスターのペルソナが「他の 3 人はクルーで」と言い、ルール節が
        「クルー 4 人」と言っていた。**同じプロンプトの中で矛盾していた。**
        人数はデータから数えて 1 か所で書く。
        """
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))
        crew_count = sum(
            1 for p in raw["players"] if p["initial_state"].get("role") == "crew"
        )

        for player in raw["players"]:
            for value in player.values():
                if not isinstance(value, str):
                    continue
                for wrong in (f"他の {crew_count} 人", f"他の {crew_count - 1} 人"):
                    assert wrong not in value, f"{player['id']}: {wrong}"

    def test_the_generated_headcount_is_still_right(self) -> None:
        """人数がデータと一致したまま出ている。"""
        raw = json.loads(_DRILL.read_text(encoding="utf-8"))

        assert f"参加者は {len(raw['players'])} 人" in _system_prompt(_DRILL)


class TestWaitingIsExplainedInWorldTerms:
    """再使用の間隔を伝える文に、engine の単位が出ない。"""

    def _after_one_strike(self):
        runtime = create_world_runtime(_DRILL)
        kuze, sena, aoi = PlayerId(3), PlayerId(2), PlayerId(4)

        def move(player_id, spot):
            graph = runtime._spot_graph_repo.find_graph()
            graph.unplace_entity(EntityId.create(int(player_id)))
            graph.place_entity(
                EntityId.create(int(player_id)),
                SpotId.create(runtime.id_mapper.get_int("spot", spot)),
            )
            runtime._spot_graph_repo.save(graph)

        move(kuze, "storage")
        runtime.do_interact(kuze, "supply_shelf", "find_cutter")
        for player_id in (sena, kuze, aoi):
            move(player_id, "corridor")
        darken_spot(runtime)
        runtime.do_interact_with_player(kuze, sena, "strike_down")
        return runtime, kuze, aoi

    def test_the_remaining_wait_is_shown_in_minutes(self) -> None:
        """続けて仕掛けると、残りが分で返る。

        ``あと 13 tick`` と返していた。**tick は世界の中に無い語** (#892)。
        実 run 011 でインポスターがこの文を読んでいる。宣言は 15 手番、
        1 手番 5 分なので 75 分。
        """
        runtime, kuze, aoi = self._after_one_strike()

        with pytest.raises(Exception) as caught:
            runtime.do_interact_with_player(kuze, aoi, "strike_down")

        assert "あと 75 分" in str(caught.value)
        assert "tick" not in str(caught.value)
