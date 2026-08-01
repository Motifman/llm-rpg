"""隠す世界では、殺しがその場に居ない者へ一切届かないことを保証する。

## なぜイベント名を見ないテストを別に書くか

同じ穴を **2 回** 踏んだ。

- #914: `player_downed` が全員へ届いていた
- #917: `player_outcome_resolved` が全員へ届いていた

どちらも原因は同じで、「死を隠す」という **1 つの世界設定が、複数の別々の
コードに手書きで反映されなければならない**ことだった。既存のテストは
イベントごとに書いてあるので、**3 つ目のイベントが増えたら 3 回目が起きる**。

観測の到達範囲を決めている箇所は約 60 あり (recipient strategy 16 個の中の
分岐と、resolver を通らない直接配信 9 箇所)、すべてを宣言的な仕組みに
載せ替えるのは現実的でない。載せ替えたとしても、#917 の書き手は「全員へ」
と宣言しただけなので防げない。

なので **イベントの名前を見ない**。宣言した世界設定そのものを不変条件に
する。

> 隠す世界では、同席していない者の観測に被害者も加害者も現れない

これなら 3 つ目のイベントが何という名前で増えても落ちる。**漏れという
概念が無い**のが、イベントごとのテストとの違い。

## prose だけでなく structured も見る

`player_downed` の structured には設計上 `killer_player_id` が残っている。
prose だけを見て「隠せている」と判断すると、機械可読な側から漏れる。
いまは cue 抽出がこの key を読んでいないので実害は無いが、**読む側が
増えたときに静かに破れる**ので不変条件の側で押さえておく。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_DRILL = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"

_MORI, _SENA, _KUZE, _AOI = (PlayerId(i) for i in (1, 2, 3, 4))

#: 殺しの現場から離れたまま、最後まで何も知らないはずの 2 人。
_ELSEWHERE = (_MORI, _AOI)

#: 被害者と加害者。どちらの名前も、離れた者の観測に現れてはいけない。
_VICTIM_NAME = "セナ"
_KILLER_NAME = "クゼ"

#: 殺害後に世界を進める tick 数。倒れる → 確定 → その後始末まで通す。
#: 1 tick では #917 (確定が次の tick で漏れる) を取り逃がす。
_TICKS_AFTER_THE_KILL = 5


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


@pytest.fixture()
def after_a_hidden_kill():
    """暗い通路での殺害から数 tick 進めた世界と、離れた者が受けた観測を返す。"""
    runtime = create_world_runtime(_DRILL)

    _move(runtime, _KUZE, "storage")
    runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
    for player_id, spot in (
        (_SENA, "corridor"),
        (_KUZE, "corridor"),
        (_MORI, "hall"),
        (_AOI, "hall"),
    ):
        _move(runtime, player_id, spot)

    before = {
        int(p): len(runtime._obs_buffer.get_observations(p)) for p in _ELSEWHERE
    }
    runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
    for _ in range(_TICKS_AFTER_THE_KILL):
        runtime.advance_tick()

    received = {
        int(p): runtime._obs_buffer.get_observations(p)[before[int(p)] :]
        for p in _ELSEWHERE
    }
    return runtime, received


def _searchable_text(entry) -> str:
    """1 件の観測を、prose と structured をまとめた 1 本の文字列にする。

    structured は入れ子や非文字列の値を持つので JSON にしてから探す。
    key 名を列挙して回ると、**列挙から漏れた key が素通りする**。
    それは今回避けたい失敗そのものなので、丸ごと文字列にして探す。
    """
    return "\n".join(
        (
            entry.output.prose,
            json.dumps(entry.output.structured, ensure_ascii=False, default=str),
        )
    )


class TestNothingAboutTheKillReachesThoseElsewhere:
    """離れた者の観測に、殺しの痕跡が一切残らない。"""

    @pytest.mark.parametrize("name", [_VICTIM_NAME, _KILLER_NAME])
    def test_neither_the_victim_nor_the_killer_is_named(
        self, after_a_hidden_kill, name
    ) -> None:
        """被害者の名前も加害者の名前も現れない。

        離れた 2 人は集会室に居続けるので、この 2 人の名前が観測に出る
        正当な理由が無い。名前が出たら、それは殺しの漏れ。
        """
        _, received = after_a_hidden_kill

        for player_id in _ELSEWHERE:
            for entry in received[int(player_id)]:
                assert name not in _searchable_text(entry), (
                    f"{player_id} に漏れた: {_searchable_text(entry)}"
                )

    def test_the_killers_player_id_does_not_leak_through_structured(
        self, after_a_hidden_kill
    ) -> None:
        """加害者を指す player_id が structured に現れない。

        prose を隠しても、機械可読な側に id が残っていれば隠せていない。
        **prose だけを見て安心しないための行。**
        """
        _, received = after_a_hidden_kill

        for player_id in _ELSEWHERE:
            for entry in received[int(player_id)]:
                structured = entry.output.structured
                assert "killer_player_id" not in structured, structured

    def test_the_death_is_not_described_in_any_wording(
        self, after_a_hidden_kill
    ) -> None:
        """死や負傷を表す語が、どの言い回しでも現れない。

        名前を伏せたまま「遠くで誰かが倒れた気配がした」を配ると、**居場所を
        絞り込む手がかりになる**。名前だけでなく出来事そのものを隠す。
        """
        _, received = after_a_hidden_kill

        for player_id in _ELSEWHERE:
            for entry in received[int(player_id)]:
                text = _searchable_text(entry)
                for word in ("倒れ", "死亡", "気配", "血", "遺体", "死体"):
                    assert word not in text, f"{player_id} に漏れた: {text}"


class TestTheInvariantIsNotVacuous:
    """この不変条件が、実際に何かを見張っていることを示す。

    離れた者が 1 件も観測を受け取らない世界では、上の 3 つは中身を見ずに
    通る。**空集合に対する全称は常に真**なので、テストが生きているのか
    死んでいるのか区別が付かなくなる。
    """

    def test_those_elsewhere_still_receive_other_observations(
        self, after_a_hidden_kill
    ) -> None:
        """離れた者も、殺し以外の観測は受け取っている。"""
        _, received = after_a_hidden_kill

        assert any(received[int(p)] for p in _ELSEWHERE)

    def test_someone_at_the_scene_does_learn_of_it(
        self, after_a_hidden_kill
    ) -> None:
        """現場に来た者には届く。

        隠しすぎて**誰にも届かない**なら、通報も会議も起こらずゲームが
        成立しない。塞ぐ方向にだけ倒れていないことを確かめる。
        """
        runtime, _ = after_a_hidden_kill
        _move(runtime, _MORI, "corridor")

        assert _VICTIM_NAME in runtime.build_observation(_MORI)
