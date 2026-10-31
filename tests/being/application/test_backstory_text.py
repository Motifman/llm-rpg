"""Being の短期記憶のいきさつから、毎ターンのプロンプトの【ここまでのいきさつ】の本文を作る規則を保証する (#1824)。"""

from __future__ import annotations

from ai_rpg_world.being.application.backstory_text import backstory_text
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.short_term_memory import Backstory, ShortTermMemory

ADA = BeingId("being_p1")


def _memory(*backstories: Backstory) -> ShortTermMemory:
    return ShortTermMemory(
        ADA, backstories=backstories, recent_from=backstories[-1].until_turn + 1 if backstories else 1
    )


class TestBackstoryText:
    """backstory_text が、いきさつを新しい順に世代の印と気分の続き行を付けて並べることを保証する。"""

    def test_no_backstory_gives_empty_text(self) -> None:
        """いきさつが 1 つも無ければ空文字を返し、【ここまでのいきさつ】は出ない。"""
        assert backstory_text(ShortTermMemory.empty(ADA)) == ""

    def test_backstories_are_listed_newest_first_with_generation_labels_and_mood(self) -> None:
        """いきさつは新しい順に並び、先頭は「[最新] 流れ」、次から「[N 世代前] 流れ」、気分は「  気分: 」の続き行になる。"""
        memory = _memory(
            Backstory(flow="坑道に入った", mood="不安", written_turn=20, until_turn=10),
            Backstory(flow="鍵を探した", mood="焦り", written_turn=30, until_turn=20),
            Backstory(flow="扉が開いた", mood="安堵", written_turn=40, until_turn=30),
        )

        assert backstory_text(memory) == (
            "[最新] 扉が開いた\n  気分: 安堵\n\n[2 世代前] 鍵を探した\n  気分: 焦り\n\n[3 世代前] 坑道に入った\n  気分: 不安"
        )

    def test_blank_mood_omits_the_mood_line(self) -> None:
        """気分が空白だけなら、気分の続き行を出さない。流れと気分の前後の空白は落とす。"""
        memory = _memory(Backstory(flow=" 扉が開いた ", mood="  ", written_turn=20, until_turn=10))

        assert backstory_text(memory) == "[最新] 扉が開いた"
