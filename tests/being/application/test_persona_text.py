from __future__ import annotations

from ai_rpg_world.being.application.persona_text import persona_text
from ai_rpg_world.being.domain.persona import Persona

GEN = Persona(
    name="ゲン",
    first_person="俺",
    speech="ぶっきらぼうな常体",
    traits=("口数は少ないが、坑道の空気には敏い",),
    values=("身内を無事に家へ帰すこと",),
    fears=("坑道のガス",),
    background="元鉱夫。",
)
GEN_KNOWS = "この鉱山で働いていた。家族のサヨと村に戻ってきた。\n働いていた頃に、事務所の金庫の番号は 1907 だと覚えた。"


class TestPersonaText:
    """persona_text が、人柄の欄とこの世界で知っていることを、古い run の【ペルソナ】の並びの文にすることを保証する。"""

    def test_gen_reads_like_the_old_run(self) -> None:
        """名前と生い立ちと性格の文、大事にしていること・苦手なこと、知っていることの段落、話し方の行の順に、空行で区切って並ぶ。"""
        assert persona_text(GEN, GEN_KNOWS) == (
            "あなたはゲン、元鉱夫。口数は少ないが、坑道の空気には敏い。\n"
            "大事にしていること: 身内を無事に家へ帰すこと。\n"
            "苦手なこと: 坑道のガス。\n"
            "\n"
            f"{GEN_KNOWS}\n"
            "\n"
            "話し方: ぶっきらぼうな常体。一人称は「俺」。"
        )

    def test_fields_left_empty_are_left_out(self) -> None:
        """決まっていない欄の行は出さない。名前だけなら「あなたは名前。」だけになる。"""
        assert persona_text(Persona(name="サヨ"), None) == "あなたはサヨ。"

    def test_several_traits_values_and_fears_are_joined(self) -> None:
        """性格は文を続け、大事にしていること・苦手なことは読点でつなぐ。末尾の句点は重ねない。"""
        mio = Persona(
            name="ミオ",
            traits=("元気。", "機械いじりが好き"),
            values=("自分の目で確かめること", "仲間"),
            fears=("じっと待たされること。",),
        )

        assert persona_text(mio, None) == (
            "あなたはミオ。元気。機械いじりが好き。\n"
            "大事にしていること: 自分の目で確かめること、仲間。\n"
            "苦手なこと: じっと待たされること。"
        )
