"""interact_display_phrase が、断られた行動の行の句を、成功の行と同じ助詞で作ることを保証する。

成功の行は runtime が書く。物と持ち物は「「X」で〈表示名〉」、人は「「X」に対して〈表示名〉」
(world_runtime の do_interact / do_interact_with_item / do_interact_with_player)。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    interact_display_phrase,
)


class TestInteractDisplayPhrase:
    """対象の種類ごとの助詞と、表示名が無いときの戻り先を保証する。"""

    @pytest.mark.parametrize("kind", ["spot_graph_object", "inventory_item"])
    def test_objects_and_items_take_de(self, kind) -> None:
        """物と持ち物は「で〈表示名〉」になる。"""
        assert interact_display_phrase(kind, "水門を開ける") == "で水門を開ける"

    def test_people_take_ni_taishite(self) -> None:
        """人は「に対して〈表示名〉」になる。"""
        assert interact_display_phrase("spot_graph_player", "殴りかかる") == "に対して殴りかかる"

    @pytest.mark.parametrize("label", [None, ""])
    def test_missing_label_gives_none(self, label) -> None:
        """表示名が引けないときは None を返し、行動の行は従来の「「X」に 〈action_name〉 した」に戻る。"""
        assert interact_display_phrase("spot_graph_object", label) is None
