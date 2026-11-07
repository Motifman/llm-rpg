from __future__ import annotations

from ai_rpg_world.game_world.domain.sound import SoundLink, SoundLoss, SoundNetwork
from ai_rpg_world.game_world.domain.value_object import SpotId
from ai_rpg_world.game_world.domain.whereabouts import PassageInState
from tests.game_world.domain.whereabouts._builders import CLOSED, OPEN, door, path


class TestSoundNetworkThrough:
    """SoundNetwork.through が、通路ごとに、通路の減衰と今の状態の減衰を足した音のつながりを作ることを保証する。"""

    def test_each_passage_becomes_a_link_between_its_ends(self) -> None:
        """通路 1 本は、その両端を結ぶ SoundLink 1 本になる。"""
        street = path("street", "plaza", "hall")

        network = SoundNetwork.through((PassageInState(passage=street, state=OPEN),), per_passage=SoundLoss(5))

        assert network.links == (SoundLink(ends=(SpotId("plaza"), SpotId("hall")), loss=SoundLoss(5)),)

    def test_loss_adds_the_loss_of_the_current_state_to_the_loss_per_passage(self) -> None:
        """閉じた扉 (状態の減衰 20) の音のつながりは、通路ごとの減衰 5 と足して 25 になり、開ければ 5 になる。"""
        cellar_door = door("cellar_door", "hall", "cellar")

        closed = SoundNetwork.through((PassageInState(passage=cellar_door, state=CLOSED),), per_passage=SoundLoss(5))
        opened = SoundNetwork.through((PassageInState(passage=cellar_door, state=OPEN),), per_passage=SoundLoss(5))

        assert (closed.links[0].loss, opened.links[0].loss) == (SoundLoss(25), SoundLoss(5))

    def test_links_keep_the_order_of_the_given_passages(self) -> None:
        """渡した通路の順に SoundLink を並べる。"""
        first = path("street", "plaza", "hall")
        second = path("lane", "hall", "well")

        network = SoundNetwork.through(
            iter((PassageInState(passage=first, state=OPEN), PassageInState(passage=second, state=OPEN))),
            per_passage=SoundLoss(0),
        )

        assert [link.ends for link in network.links] == [
            (SpotId("plaza"), SpotId("hall")),
            (SpotId("hall"), SpotId("well")),
        ]
