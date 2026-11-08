from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.verb import SightTextsDeclaration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception import NotNoticedLater, NotSeenInDim, NotSeenWithoutActor


class TestSightTextsDeclarationDefaults:
    """SightTextsDeclaration が、作者が書かなかった見え方の文を「その見え方では届かない」として持つことを保証する。"""

    def test_dim_left_unwritten_becomes_not_seen_in_dim(self) -> None:
        """dim を書かずに作ると、dim は NotSeenInDim になり、暗がりでは見えない行為として扱われる。"""
        texts = SightTextsDeclaration(clear=TextWithUnassignedPeople("{actor}がレバーを引いた。"))

        assert texts.dim == NotSeenInDim()

    def test_unseen_actor_left_unwritten_becomes_not_seen_without_actor(self) -> None:
        """unseen_actor を書かずに作ると、unseen_actor は NotSeenWithoutActor になる。"""
        texts = SightTextsDeclaration(clear=TextWithUnassignedPeople("{actor}がレバーを引いた。"))

        assert texts.unseen_actor == NotSeenWithoutActor()

    def test_noticed_later_left_unwritten_becomes_not_noticed_later(self) -> None:
        """noticed_later を書かずに作ると、noticed_later は NotNoticedLater になり、倒れていた本人は起きてから気づかない。"""
        texts = SightTextsDeclaration(clear=TextWithUnassignedPeople("{actor}がレバーを引いた。"))

        assert texts.noticed_later == NotNoticedLater()

    def test_written_texts_are_kept(self) -> None:
        """dim・unseen_actor・noticed_later に文を書くと、書いた文をそのまま持つ。"""
        dim = TextWithUnassignedPeople("{actor}が何かを引いた。")
        unseen = TextWithUnassignedPeople("レバーがひとりでに下りた。")
        later = TextWithUnassignedPeople("気を失っているあいだに、レバーが下りていた。")

        texts = SightTextsDeclaration(
            clear=TextWithUnassignedPeople("{actor}がレバーを引いた。"),
            dim=dim,
            unseen_actor=unseen,
            noticed_later=later,
        )

        assert (texts.dim, texts.unseen_actor, texts.noticed_later) == (dim, unseen, later)
