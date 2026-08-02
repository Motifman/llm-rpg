"""両陣営がゲームの趣旨を理解できる状態になっていることを保証する。

## 実 run で分かったこと

run 001-005 で、会議は開くのに誰も投票せず、偽装を見ても誰も気に留めなかった。
プロンプトを読んで理由が分かった。**クルーはゲームの趣旨を知らされていな
かった。**

    ペルソナ  : 観測所の気象観測員。几帳面で、手順を決めてから動く。
    世界の前提: 吹雪。定時連絡までに点検を終えなければ救援が遅れる。
    目的      : 点検を 2 つ終わらせる。暗い通路には一人で入らない。

裏切り者が居ることも、襲われる可能性も、投票が意味を持つことも書かれて
いない。**キーパーだけが Among Us を遊んでいて、クルー 3 人は協力型の点検
作業を遊んでいた。**

本家ではクルーもインポスターの存在と人数を知っている。それがあるから、
あらゆる観測が証拠になる。知らなければ、進捗の食い違いを見せても
「機械の不調かな」で終わる。

## メタ開示型にした

「これは秘匿役職ゲームである」と直接書く。世界の中の言葉で書く案もあったが、
**まず動作を確実にする**ことを優先した。質感との兼ね合いは run を見てから
判断する。

## 戦術は書かない

「疑われないよう協力的に振る舞え」のような**行動の指示は書かない**。書くと
エージェントの選択肢を engine 側が狭めることになる。書くのは事実
(誰が何者か) とできること (暗所でだけ襲える / 嘘をついてよい) だけ。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "station_drill.json"
)

_CREW = PlayerId(1)
_IMPOSTOR = PlayerId(3)


@pytest.fixture()
def prompts():
    runtime = create_world_runtime(_SCENARIO)
    return runtime._world_llm_system_prompts_by_player_id


class TestBothSidesKnowTheGame:
    """共通の説明が両陣営に届く。"""

    @pytest.mark.parametrize("player_id", [_CREW, _IMPOSTOR])
    def test_the_shared_explanation_is_present(self, prompts, player_id) -> None:
        """陣営に関係なく、ゲームの説明が入っている。

        **相手陣営が何を狙うかを知らないと、メタな読みができない。**
        クルーが「インポスターは自分を疑わせないよう動く」と分かって
        初めて、観測が証拠になる。
        """
        assert "秘匿役職ゲーム" in prompts[int(player_id)]

    @pytest.mark.parametrize("player_id", [_CREW, _IMPOSTOR])
    def test_both_win_conditions_are_stated(self, prompts, player_id) -> None:
        """両陣営の勝利条件が書かれている。

        自分の勝ち筋だけ知っていても、相手の勝ち筋を知らなければ
        「相手が何を急いでいるか」が読めない。
        """
        text = prompts[int(player_id)]

        # **文言そのものは焼き付けない。** 以前は「クルーの勝利」という
        # 手書きの見出しを見ていたが、その行には古い数字 (3 つすべて) が
        # 並んでいて、**テストが誤った記述を守っていた**。いまは勝ち筋の
        # 数字をデータから組み立てるので、意味のほうを見る。
        assert "終えれば" in text and "勝ち" in text     # クルー側
        assert "インポスターの勝利" in text

    @pytest.mark.parametrize("player_id", [_CREW, _IMPOSTOR])
    def test_the_number_of_impostors_is_stated(self, prompts, player_id) -> None:
        """インポスターが何人かが書かれている。

        推理の計算に要る。「4 人中 1 人」を知らないと、残り人数から
        絞り込めない。
        """
        # 人数はデータから数える。**手書きの「4 人のうち 1 人」は #938 で
        # 5 人になったあとも残っていて、テストがその誤りを守っていた。**
        text = prompts[int(player_id)]

        assert "インポスター 1 人" in text
        assert "参加者は 5 人" in text

    @pytest.mark.parametrize("player_id", [_CREW, _IMPOSTOR])
    def test_the_cost_of_a_wrong_ejection_is_stated(self, prompts, player_id) -> None:
        """誤追放が不利になることが書かれている。

        書かないと軽率に投票する。「疑わしいから追放」を繰り返すと
        クルーが自滅する。
        """
        assert "無実の者を追放すると" in prompts[int(player_id)]


class TestEachSideKnowsItsOwnRole:
    """自分の陣営は分かるが、他人の陣営は分からない。"""

    def test_the_crew_knows_it_is_crew(self, prompts) -> None:
        """クルーは自分がクルーだと知っている。"""
        assert "あなたはクルーである" in prompts[int(_CREW)]

    def test_the_impostor_knows_it_is_the_impostor(self, prompts) -> None:
        """インポスターは自分がインポスターだと知っている。"""
        assert "あなたがインポスターである" in prompts[int(_IMPOSTOR)]

    def test_the_crew_is_not_told_who_the_impostor_is(self, prompts) -> None:
        """クルーに誰がインポスターかは書かれていない。

        **ここが漏れたら成立しない。** 名前が出ていないことを確かめる。
        """
        text = prompts[int(_CREW)]
        assert "クゼ" not in text.split("【同じ局面にいる者】")[0]
        assert "あなたがインポスター" not in text


class TestNoTacticIsPrescribed:
    """戦術は指示しない。"""

    def test_the_impostor_is_not_told_how_to_behave(self, prompts) -> None:
        """「協力的に振る舞え」のような行動の指示が無い。

        engine 側が振る舞いを決めると、エージェントの選択がその分だけ
        減る。**できることを伝えるのと、やり方を指示するのは別。**
        """
        text = prompts[int(_IMPOSTOR)]
        assert "協力的に振る舞う" not in text

    def test_the_impostor_is_told_it_may_lie(self, prompts) -> None:
        """嘘をついてよいことは明示する。

        共通ルールに「意図的に嘘をつく状況でない限り捏造しない」がある
        ので、許可が無いと嘘を避ける方向に働く。これは指示ではなく許可。
        """
        assert "事実と異なることを述べてもよい" in prompts[int(_IMPOSTOR)]


class TestWinConditionsMatchTheGenre:
    """勝敗の宣言が、説明した内容と一致している。"""

    def test_the_crew_can_win_by_ejecting_the_impostor(self) -> None:
        """追放でもクルーが勝てる。

        勝ち筋がタスクだけだと、追放しても試合が続く。**投票する動機が
        生まれない。**
        """
        result = create_world_runtime(_SCENARIO).scenario
        kinds = [c.condition_type.value for c in result.win_conditions]

        assert "SURVIVING_PLAYERS_WITH_STATE_AT_MOST" in kinds

    def test_the_impostor_wins_at_parity_not_extinction(self) -> None:
        """インポスターは同数で勝つ (全滅ではない)。

        全滅を要求すると 3 人殺す必要があり、短い run では届かない。
        本家も人狼も同数で決着する。
        """
        result = create_world_runtime(_SCENARIO).scenario
        (lose,) = result.lose_conditions

        assert lose.max_surviving == 1

    def test_one_strike_is_lethal(self) -> None:
        """一撃で倒れる。

        2 手かかると、襲撃の途中で逃げられて成立しにくい。本家は一撃。
        """
        result = create_world_runtime(_SCENARIO).scenario
        strike = next(
            i for i in result.player_interactions if i.action_name == "strike_down"
        )
        damage = next(
            e.parameters["damage"]
            for e in strike.effects
            if e.effect_type.value == "APPLY_DAMAGE"
        )

        assert damage >= 100
