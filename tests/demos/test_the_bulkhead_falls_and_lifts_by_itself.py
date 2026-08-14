"""隔壁が降りて、しばらくして自分で上がる。誰が降ろしたかは残らない。

## なぜ妨害が要るか

run 011 のクルーには、**インポスターを疑う理由が生まれなかった**。仕事は
各自の持ち場で完結し、誰かが居ないことに意味が無い。モリはクゼを正しく
名指したが、根拠は「近くに居た」だけだった。

妨害は「誰かが世界に手を加えた」という**否定しようのない事実**を置く。
犯人は分からないが、起きたことは全員が知る。そこから初めて「あのとき誰が
どこに居たか」が意味を持つ。

## この妨害の形

手元の制御端末を操作すると、観測室から医務室・通信室へ出る二つの隔壁が
同時に降りる。観測室は一時的に孤立するが、しばらくすると自分で上がる。

- **誰が降ろしたかは伝わらない。** 扉が降りた事実と、盤を操作した行為は
  別のイベントで、前者に行為者が乗らない
- **降りた事実は両側の部屋に伝わる。** さらにその隣にも「遠くで何かが動く
  音がした」として届く
- **放っておいても直る。** クルーが対処しなくても負けない (妨害B)。
  無視すると負ける妨害A は別に作る

## engine には妨害という概念が無い

書いたのはシナリオ JSON だけで、engine のコードは 1 行も足していない。
使ったのは資源の再生 (survival_island_v2 の流木・椰子) と同じ仕組みで、
engine が知っているのは「記録した手番から N 経過したか」だけ。

    流木の山: 採ると last_harvest_tick を記録 → 16 手番後にまた採れる
    隔壁:     降ろすと sealed_at_tick を記録 → 4 手番後にまた上がる
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
#: モリ / セナ / クゼ / アオイ / ハギ / ユラ / サキ / ジン
(_MORI, _SENA, _KUZE, _AOI, _HAGI, _YURA, _SAKI, _JIN) = (
    PlayerId(i) for i in range(1, 9)
)

_SEALED_CONNECTIONS = ("observatory_to_medbay", "observatory_to_comms")

#: 隔壁が降りている手番数。シナリオ宣言と揃える。
_SEALED_TICKS = 4
#: 隔壁盤を続けて使えるようになるまでの手番数。シナリオ宣言と揃える。
_COOLDOWN_TICKS = 20


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _advance(runtime, ticks: int) -> None:
    for _ in range(ticks):
        runtime.advance_tick()


def _is_open(runtime, connection: str = "observatory_to_medbay") -> bool:
    """その接続が、いま通れるか。"""
    graph = runtime._spot_graph_repo.find_graph()
    conn = graph.get_connection(
        ConnectionId.create(runtime.id_mapper.get_int("connection", connection))
    )
    return conn.passage.traversable


def _seal(runtime, actor: PlayerId = _KUZE):
    """手元の制御端末から、隔壁盤へ記録手番を遠隔で書き込む。"""
    terminal = ItemSpecId.create(
        runtime.id_mapper.get_int("item_spec", "control_terminal")
    )
    return runtime.do_interact_with_item(actor, terminal, "seal_bulkhead")


def _spot_of(runtime, player_id: PlayerId) -> str:
    graph = runtime._spot_graph_repo.find_graph()
    spot = graph.get_entity_spot(EntityId.create(int(player_id)))
    return runtime.id_mapper.get_str("spot", int(spot))


def _observations(runtime, viewer: PlayerId) -> str:
    """現在状態のプロンプト。いま何が見えているか。"""
    return runtime.build_observation(viewer)


def _terminal_row(runtime, viewer: PlayerId) -> str:
    """所持品にある制御端末の行だけを取り出す。

    観測全文を見ると、他の節の語 (``作業の進み: 0/16 (あと 12)``) のおかげで
    通ってしまう。**端末について何が書かれているか**を見る。
    """
    lines = runtime.build_full_prompt(viewer)["messages"][1]["content"].splitlines()
    index = next(
        index
        for index, line in enumerate(lines)
        if line.lstrip().startswith('- "制御端末"')
    )
    return "\n".join(lines[index : index + 2])


def _delivered(runtime, viewer: PlayerId) -> tuple:
    """その人に届いた観測の文。**起きた瞬間**に伝わるのはこちら。

    現在状態には「通行不可」と書かれるが、それは今の姿であって出来事ではない。
    妨害が伝わったかは、届いた観測で見る。
    """
    return tuple(
        entry.output.prose
        for entry in runtime._obs_buffer.get_observations(viewer)
    )


class TestOnlyTheKeeperCanDropIt:
    """隔壁を降ろす手は、インポスターにしか見えない。"""

    def test_the_keeper_sees_the_action(self, runtime) -> None:
        """インポスターの所持品には隔壁を降ろす手が並ぶ。"""

        assert "seal_bulkhead" in _terminal_row(runtime, _KUZE)

    def test_a_crew_member_never_sees_it(self, runtime) -> None:
        """クルーの現在状態には、同じ盤の前に立っても端末の手が出ない。

        **「誰にも見えない」でも上のテストは通らない**ので、見える側と
        見えない側を必ず一緒に見る。``PLAYER_STATE_IS`` は HIDDEN 扱いで、
        不成立の理由ごと行が消える (#860)。
        """
        _move(runtime, _HAGI, "observatory")

        assert "隔壁盤" in _observations(runtime, _HAGI)  # 盤そのものは見えている

        assert "seal_bulkhead" not in _observations(runtime, _HAGI)
        assert "制御端末" not in runtime.build_full_prompt(_HAGI)["messages"][1]["content"]


class TestTheDoorIsOpenUntilSomeoneDropsIt:
    """始まった時点では二つの扉が開いている。"""

    def test_the_door_starts_open(self, runtime) -> None:
        """誰も何もしていないうちは扉が通れる。

        自動で上げ直す条件は「降ろしてから N 手番」で書く。一度も降ろして
        いない状態を「まだ経過していない」と読むと、**開始時点で扉が
        閉じたまま**になる。``treat_missing_as_passed`` がそれを防ぐ。
        """
        _advance(runtime, 3)

        assert all(_is_open(runtime, connection) for connection in _SEALED_CONNECTIONS)


class TestTheDoorFallsAndLiftsByItself:
    """降ろした扉が、しばらくして自分で上がる。"""

    def test_the_door_closes_when_dropped(self, runtime) -> None:
        """隔壁盤を操作すると扉が通れなくなる。"""
        _seal(runtime)
        _advance(runtime, 1)

        assert all(
            not _is_open(runtime, connection) for connection in _SEALED_CONNECTIONS
        )

    def test_the_door_stays_closed_for_a_while(self, runtime) -> None:
        """待ち時間の途中では、まだ閉じたままになっている。

        **「すぐ上がる」でも下のテストは通る**ので、上がらない側を一緒に
        見る。すぐ上がるなら妨害として成立しない。
        """
        _seal(runtime)
        _advance(runtime, _SEALED_TICKS - 1)

        assert all(
            not _is_open(runtime, connection) for connection in _SEALED_CONNECTIONS
        )

    def test_the_door_lifts_without_anyone_touching_it(self, runtime) -> None:
        """誰も触らないまま待つと、扉がまた通れるようになる。

        クルーが対処しなくても直る。**無視すると負ける妨害はこれとは別**に
        用意する。
        """
        _seal(runtime)
        _advance(runtime, _SEALED_TICKS + 1)

        assert all(_is_open(runtime, connection) for connection in _SEALED_CONNECTIONS)

    def test_the_door_can_be_dropped_again_later(self, runtime) -> None:
        """一度上がったあと、また降ろせる。

        一度きりだと、盤は「使い切りの仕掛け」になってしまう。記録した
        手番を上書きすることで、同じ宣言のまま何度でも繰り返せる。
        """
        _seal(runtime)
        _advance(runtime, _COOLDOWN_TICKS + 1)
        assert all(_is_open(runtime, connection) for connection in _SEALED_CONNECTIONS)

        _seal(runtime)
        _advance(runtime, 1)

        assert all(
            not _is_open(runtime, connection) for connection in _SEALED_CONNECTIONS
        )


class TestTheDoorCannotBeDroppedAgainRightAway:
    """続けて降ろせないだけの待ち時間がある。"""

    def test_dropping_it_twice_in_a_row_is_refused(self, runtime) -> None:
        """上がった直後にもう一度降ろそうとすると弾かれ、扉は開いたままになる。

        待ち時間が短いと、インポスターは扉を降ろし続けるだけで勝てる。
        **妨害は取り返しのつく形でしか置かない。**
        """
        _seal(runtime)
        _advance(runtime, _SEALED_TICKS + 1)
        assert all(_is_open(runtime, connection) for connection in _SEALED_CONNECTIONS)

        # 例外の種類と文面まで絞る。`Exception` だけだと AttributeError でも
        # 緑になり、**待ち時間で断ったことを確かめていない** (claude の指摘)。
        with pytest.raises(InteractionNotAllowedException, match="まだそれはできない"):
            _seal(runtime)
        _advance(runtime, 1)

        assert all(_is_open(runtime, connection) for connection in _SEALED_CONNECTIONS)

    def test_the_wait_is_shown_in_world_terms(self, runtime) -> None:
        """待っている間、隔壁盤の行に残り時間が分で出る。

        ``tick`` は世界の中に無い語 (#892)。1 手番 5 分で宣言は 10 手番。
        降ろした次の手番に見るので残りは 9 手番 = 45 分。

        **観測全文から ``あと`` を探すと常に通る。** 盤に触っていない状態でも
        ``作業の進み: 0/16 (あと 12)`` が出ているので、待ち時間の宣言を丸ごと
        消しても緑のままだった (claude の指摘)。行に絞る。
        """
        _seal(runtime)
        _advance(runtime, 1)

        row = _terminal_row(runtime, _KUZE)

        assert "あと 45 分" in row
        assert "tick" not in row

    def test_the_terminal_row_shows_no_wait_before_the_first_use(
        self, runtime
    ) -> None:
        """一度も降ろしていないうちは、盤の行に待ち時間が出ない。

        **「常に出る」でも上のテストは通る**ので、出ない側を一緒に見る。
        """
        assert "あと" not in _terminal_row(runtime, _KUZE)


class TestTheDoorTellsBothRoomsButNotWho:
    """扉が降りたことは両側に伝わり、誰が降ろしたかは伝わらない。"""

    def _seal_with_everyone_placed(self, runtime):
        """遠隔で降ろし、観測室・医務室・隣室に一人ずつ置く。"""
        _move(runtime, _MORI, "observatory")  # 扉のこちら側
        _move(runtime, _SENA, "medbay")  # 扉の向こう側
        _move(runtime, _HAGI, "hall")  # さらに隣
        _seal(runtime)
        _advance(runtime, 1)
        return runtime

    def test_the_room_on_one_side_learns_the_door_shut(self, runtime) -> None:
        """観測室に居る人に「通行不能になった」が届く。"""
        self._seal_with_everyone_placed(runtime)

        assert any("通行不能になった" in line for line in _delivered(runtime, _MORI))

    def test_the_room_on_the_other_side_learns_it_too(self, runtime) -> None:
        """医務室に居る人にも届く。

        片側だけだと、扉の向こうの人は**理由の分からない足止め**を食う。
        """
        self._seal_with_everyone_placed(runtime)

        assert any("通行不能になった" in line for line in _delivered(runtime, _SENA))

    def test_the_next_room_only_hears_a_sound(self, runtime) -> None:
        """さらに隣の部屋には「音がした」だけが届く。

        扉の状態そのものは、そこからは知りようがない。**何かが起きたことだけ**が
        伝わるので、確かめに行くかどうかがその人の判断になる。
        """
        self._seal_with_everyone_placed(runtime)

        heard = _delivered(runtime, _HAGI)

        assert any("音がした" in line for line in heard)
        assert not any("通行不能になった" in line for line in heard)

    def test_nobody_learns_who_dropped_it(self, runtime) -> None:
        """扉が降りた知らせに、行為者の名前が入らない。

        **これが無いと妨害が成立しない。** 誰がやったか分かるなら、
        インポスターは一度使った時点で終わる。

        誰が部屋に入ってきたかは別の観測として届き、そちらには名前が乗る。
        **それは伏せるものではない。** 「あのとき誰が居たか」はクルーが推理の
        材料にするもので、消したら妨害を置いた意味が無くなる。ここで見るのは
        扉の知らせだけ。
        """
        self._seal_with_everyone_placed(runtime)

        for viewer in (_MORI, _SENA, _HAGI):
            door_lines = [
                line
                for line in _delivered(runtime, viewer)
                if "通行不能になった" in line or "音がした" in line
            ]
            # 1 件も拾えないと assert が 0 回になり、**何も確かめずに緑**に
            # なる (claude の指摘)。拾えていること自体を先に見る。
            assert door_lines, viewer
            for line in door_lines:
                assert "クゼ" not in line, (viewer, line)

    def test_remote_use_does_not_claim_the_keeper_was_in_the_hall(self, runtime) -> None:
        """別室から端末を使っても、隔壁側の観測に実行者の居場所を捏造しない。"""
        _move(runtime, _KUZE, "machine_room")
        _move(runtime, _MORI, "observatory")

        _seal(runtime)
        _advance(runtime, 1)

        assert not any("クゼ" in line for line in _delivered(runtime, _MORI))

    def test_even_someone_with_the_actor_does_not_see_the_hand(
        self, runtime
    ) -> None:
        """行為者と同じ集会室に居る人にも、端末を操作したこと自体が届かない。

        目撃文を書かなければ黙る、ではない。**書かないと「{行為者}が「隔壁を
        降ろす」を行った」という既定文が出る。** ``witness_policy`` で明示的に
        伏せる必要がある。
        """
        _move(runtime, _MORI, "hall")
        _seal(runtime)
        _advance(runtime, 1)

        for line in _delivered(runtime, _MORI):
            assert "隔壁" not in line, line

    def test_the_room_says_the_way_is_shut_from_then_on(self, runtime) -> None:
        """届いた知らせが流れたあとも、現在状態に「通行不可」と残る。

        観測は起きた瞬間だけのもの。**後から来た人や、忘れた人**が読むのは
        現在状態のほうで、そちらにも出ていないと足止めの理由が分からない。
        """
        self._seal_with_everyone_placed(runtime)

        row = next(
            line
            for line in _observations(runtime, _MORI).splitlines()
            if "観測室と医務室の通路" in line
        )

        assert "通行不可" in row

    def test_the_closed_door_does_not_explain_how_to_operate_it(
        self, runtime
    ) -> None:
        """封鎖中の扉は通行不可と伝えるが、隔壁盤の操作方法までは教えない。

        誰が仕掛けを動かしたかを推理する材料は、世界で実際に観測した出来事から
        得る。扉の説明文が毎回「盤から降ろせる」と種明かししてはいけない。
        観測室側だけでなく、盤を見ていない医務室側にも同じ境界を適用する。
        """
        self._seal_with_everyone_placed(runtime)

        for viewer in (_MORI, _SENA):
            row = next(
                line
                for line in _observations(runtime, viewer).splitlines()
                if "観測室と医務室の通路" in line
            )

            assert "通行不可" in row
            assert "隔壁盤" not in row
            assert "降ろせば" not in row


class TestTheClosedDoorsIsolateTheObservatory:
    """二つの隔壁は観測室を閉じ込めるが、会議の集合は妨げない。"""

    def test_both_directions_of_both_exits_are_closed(self, runtime) -> None:
        """二辺とその逆向きが同時に閉じ、一方通行や片側だけの封鎖を作らない。"""
        _seal(runtime)
        _advance(runtime, 1)

        for connection in _SEALED_CONNECTIONS:
            assert not _is_open(runtime, connection)
            assert not _is_open(runtime, f"{connection}__reverse")

    def test_a_meeting_inside_the_sealed_observatory_gathers_everyone(
        self, runtime
    ) -> None:
        """封鎖中でも会議は物理的な隔壁を越え、全生存者を開催室へ集める。

        会議で一部の参加者が構造的に発言できない状態より、集合が一時的に
        隔壁を越えることを選ぶ。隔壁は四手番で自動復帰するため、集合後も
        恒久的な閉じ込めにはならない。
        """
        _move(runtime, _MORI, "observatory")
        _seal(runtime)
        _advance(runtime, 1)

        result = runtime.call_emergency_meeting(_MORI)

        assert result.success
        assert {
            _spot_of(runtime, player_id)
            for player_id in (
                _MORI,
                _SENA,
                _KUZE,
                _AOI,
                _HAGI,
                _YURA,
                _SAKI,
                _JIN,
            )
        } == {"observatory"}


class TestTheDeclaredSoundStaysTrue:
    """扉の音の通りが、宣言と食い違わない。"""

    def test_the_sealable_door_declares_no_sound_override(self) -> None:
        """降ろせる扉には ``sound_permeability`` の上書きを書かない。

        ``Passage.with_state`` は状態が変わると上書きを捨て、kind と state の
        既定値に戻す。上書きを宣言した扉を一度開閉すると、**作家が書いた値が
        黙って失われて二度と戻らない** (#967)。

        直すのは #967 の仕事で、この妨害はそれに依存しない。**宣言しなければ
        失うものが無い**ので、ここでは書かないことを仕様として固定する。
        """
        import json

        data = json.loads(_DRILL.read_text(encoding="utf-8"))
        door = next(
            conn
            for conn in data["connections"]
            if conn["id"] == "observatory_to_medbay"
        )

        assert door["passage"]["kind"] == "DOOR"
        assert "sound_permeability" not in door["passage"]
        assert "traversable" not in door["passage"]
