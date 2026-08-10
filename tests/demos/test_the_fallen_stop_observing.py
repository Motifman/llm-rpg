"""倒れている人が、周りのことを観測しなくなることを保証する。

## 何が起きていたか

実 run 008 で、tick 4 に殺されたセナが tick 5 に生者の声を拾っていた。

    t=5 セナ <- 〈物資庫の扉〉の向こうから、アオイの声がかすかに聞こえる

倒れている player は LLM ターンが回らないので観測を消化できない。復帰時に
buffer を clear する仕様 (復活直前の他者発話を引きずらない) とも整合しない。

## 判定が 1 つの strategy の中にしか無かった

除外は `SpotGraphRecipientStrategy` の末尾だけにあり、発話は別経路
(`SpeechRecipientStrategy` 系) を通るので効いていなかった。当時のコメント
自身が「別経路で同等の制御を入れる」と書いていて、**書かれないまま実 run で
出た**。

各 strategy に同じ判定を配ると、strategy を 1 つ足した人が忘れる。
**resolver の出口は 1 つしかないので、そこに置けば忘れようがない。**

## 「何も観測しない」ではない

一律に落とすと、倒れた本人に「倒れて動けなくなった」が届かなくなる。
復帰の通知も同じ。規則は **「倒れている人は周りのことを観測しない」**
であって、自分のことは届く。event の主体だけは残す。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI, _SENA, _KUZE, _AOI, _HAGI = (PlayerId(i) for i in range(1, 6))


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _prose_since(runtime, player_id: PlayerId, since: int) -> list[str]:
    return [
        e.output.prose
        for e in runtime._obs_buffer.get_observations(player_id)[since:]
    ]


@pytest.fixture()
def after_sena_falls():
    """セナが暗い通路で倒れ、アオイが同じ場所に居る世界。

    聞き手に灯りを持つ人を使わない。**灯りがあると通路が暗くなくなって
    襲えない。** 襲撃を先に済ませてから入れる手もあるが、灯りを持たない人を
    選ぶほうが素直。

    最初はハギを聞き手にしていたが、run 010 の後にハギへランタンを渡した
    (暗所の担当が誰も仕事を始められなかった) ので、アオイに替えた。
    **灯りの持ち主が変わると、この fixture は「襲えない」で落ちる。**
    それでよい。灯りが身を守ることを、テストの側からも縛っている。
    """
    runtime = create_world_runtime(_DRILL)
    _move(runtime, _KUZE, "storage")
    runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
    for player_id in (_SENA, _KUZE, _AOI):
        _move(runtime, player_id, "corridor")
    runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
    return runtime


class TestTheFallenDoNotHearTheLiving:
    """倒れている人に、周りの出来事が届かない。"""

    def test_speech_does_not_reach_them(self, after_sena_falls) -> None:
        """同じ場所での発話が届かない。

        **これが実 run 008 で出た形。** 死んだセナが生者の声を拾っていた。
        """
        runtime = after_sena_falls
        before = len(runtime._obs_buffer.get_observations(_SENA))

        runtime.do_say(_AOI, "誰かいませんか")

        assert _prose_since(runtime, _SENA, before) == []

    def test_the_living_still_hear_it(self, after_sena_falls) -> None:
        """生きている人には今までどおり届く。

        塞ぎすぎると会話そのものが成立しない。**「誰にも届かない」でも
        テストは通ってしまう**ので、届く側を必ず一緒に見る。
        """
        runtime = after_sena_falls
        before = len(runtime._obs_buffer.get_observations(_KUZE))

        runtime.do_say(_AOI, "誰かいませんか")

        assert any("誰かいませんか" in p for p in _prose_since(runtime, _KUZE, before))

    def test_arrival_reaches_them_after_death_is_confirmed(self, after_sena_falls) -> None:
        """確定前の昏倒者は観測せず、死亡確定後の幽霊は生者の到着を知覚する。

        ``advance_tick`` で DEAD が確定し、去った主体が有効な station_drill
        では既存の距離内にいる生者を知覚できる。蘇生可能な昏倒と死亡確定を
        同じ状態へ潰さないことを、この遷移で固定する。
        """
        runtime = after_sena_falls
        before = len(runtime._obs_buffer.get_observations(_SENA))

        _move(runtime, _HAGI, "corridor")
        runtime.advance_tick()

        assert _prose_since(runtime, _SENA, before) == [
            "ハギが連絡通路にやってきた。"
        ]


class TestTheirOwnFateStillReachesThem:
    """自分のことは届く。"""

    def test_they_learn_their_departed_state(self, after_sena_falls) -> None:
        """即死後も動ける存在状態は本人に届く。

        **一律に落とすとここが消える。** 何が起きたか分からないまま退場する。
        規則は「周りのことを観測しない」であって「何も観測しない」ではない。
        """
        runtime = after_sena_falls

        assert any(
            "死亡した後も移動できる" in e.output.prose
            for e in runtime._obs_buffer.get_observations(_SENA)
        )


class TestTheRuleIsAboutWhoTheEventIsAbout:
    """残す / 落とすを決めているのは「誰のことか」。

    復帰の通知 (`PlayerRevivedEvent`) は**倒れている状態で起きる**ので、
    主体を残す規則が無いと、起き上がった本人がそれを知らないまま終わる。
    executor を組み立てて実際に蘇生させるより、規則を直接縛るほうが
    取り違えにくい。
    """

    def _resolver(self, *, down: bool):
        from unittest.mock import MagicMock

        from ai_rpg_world.application.observation.services.observation_recipient_resolver import (  # noqa: E501
            ObservationRecipientResolver,
        )

        repository = MagicMock()
        repository.find_by_id.return_value = MagicMock(is_down=down)
        return ObservationRecipientResolver(
            strategies=[], player_status_repository=repository
        )

    def _event_about(self, player_id: PlayerId):
        """その player の身に起きたことを表す event。

        ``aggregate_type`` を必ず立てる。**spot graph の event は
        aggregate_id が graph を指す**ので、種別を見ないと graph の id と
        同じ番号の player が「主体」に化ける。
        """
        from unittest.mock import MagicMock

        return MagicMock(
            aggregate_id=MagicMock(value=int(player_id)),
            aggregate_type="PlayerStatusAggregate",
        )

    def test_the_subject_is_kept_even_while_down(self) -> None:
        """倒れていても、自分のことなら残る。"""
        resolver = self._resolver(down=True)

        kept = resolver._without_the_fallen(self._event_about(_SENA), [_SENA])

        assert kept == [_SENA]

    def test_a_bystander_is_dropped_while_down(self) -> None:
        """倒れていて、他人のことなら落ちる。"""
        resolver = self._resolver(down=True)

        kept = resolver._without_the_fallen(self._event_about(_MORI), [_SENA])

        assert kept == []

    def test_nobody_is_dropped_while_standing(self) -> None:
        """立っていれば、誰のことでも残る。"""
        resolver = self._resolver(down=False)

        kept = resolver._without_the_fallen(self._event_about(_MORI), [_SENA])

        assert kept == [_SENA]

    def test_an_event_about_nobody_still_drops_the_fallen(self) -> None:
        """主体が player でない event でも、倒れている人からは落ちる。

        天候の変化などがこれ。**主体が取れないときに全員残す実装にすると、
        塞いだつもりの経路がそこだけ開く。**
        """
        from unittest.mock import MagicMock

        resolver = self._resolver(down=True)
        weather = MagicMock(
            aggregate_id=MagicMock(value="not-a-player"),
            aggregate_type="WorldAggregate",
        )

        assert resolver._without_the_fallen(weather, [_SENA]) == []


    def test_a_graph_event_does_not_make_a_player_the_subject(self) -> None:
        """spot graph の event で、番号の一致した player が主体に化けない。

        **これを見落としていた。** spot graph の event は aggregate_id が
        graph を指し、その値も int なので、種別を見ない実装だと graph id と
        同じ番号の player だけが観測を受け取り続ける。既存テストが捕まえた。
        """
        from unittest.mock import MagicMock

        resolver = self._resolver(down=True)
        graph_event = MagicMock(
            aggregate_id=MagicMock(value=int(_SENA)),
            aggregate_type="SpotGraphAggregate",
        )

        assert resolver._without_the_fallen(graph_event, [_SENA]) == []


class TestTheGuardSitsAtTheOnlyExit:
    """判定が resolver の出口にある。"""

    def test_the_strategies_no_longer_carry_their_own_filter(self) -> None:
        """strategy 側に同じ判定が残っていない。

        両方に置くと、**片方だけ直したときに食い違う**。判定は出口 1 か所に
        しかない、を記述として固定する。

        `hasattr` で「出口に関数がある」ことだけを見ても意味が無い。関数が
        あっても呼ばれていなければ通ってしまう。呼ばれていることは上の
        振る舞いのテストが見ているので、ここでは**重複が無いこと**を見る。
        """
        strategies = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "ai_rpg_world"
            / "application"
            / "observation"
            / "services"
            / "recipient_strategies"
        )
        offenders = [
            path.name
            for path in strategies.glob("*.py")
            if "_is_player_down" in path.read_text(encoding="utf-8")
        ]

        assert offenders == []

    def test_it_does_nothing_without_a_repository(self) -> None:
        """status を引けない組み立てでは何も落とさない。

        この口を知らない既存の組み立て経路 (テスト用の直接構築など) の挙動を
        変えないため。塞ぐ側に倒すと、無関係なテストが黙って観測を失う。
        """
        from ai_rpg_world.application.observation.services.observation_recipient_resolver import (  # noqa: E501
            ObservationRecipientResolver,
        )

        resolver = ObservationRecipientResolver(strategies=[])

        assert resolver._is_player_down(_SENA) is False
