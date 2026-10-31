"""BeingAttachment が、居場所を環境の識別子と表示の名前で持ち、ゲームの番号を持たないことを保証する (design_decisions D1928-2)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.exception.being_exceptions import BeingAttachmentValidationException


class TestBeingAttachmentValidation:
    """BeingAttachment が受け取る値の決まりを保証する。"""

    def test_environment_id_and_name_are_kept(self) -> None:
        """環境の識別子と表示の名前をそのまま持つ。"""
        attachment = BeingAttachment(environment_id="mine_village_v1#1", environment_name="廃坑の山村")

        assert (attachment.environment_id, attachment.environment_name) == ("mine_village_v1#1", "廃坑の山村")

    @pytest.mark.parametrize("field_name", ["environment_id", "environment_name"])
    @pytest.mark.parametrize("value", ["", "   ", 1, None])
    def test_blank_or_non_text_raises(self, field_name: str, value: object) -> None:
        """空白だけの文字列か文字列でない値を渡すと BeingAttachmentValidationException を投げる。"""
        fields: dict[str, object] = {"environment_id": "mine_village_v1#1", "environment_name": "廃坑の山村"}
        fields[field_name] = value

        with pytest.raises(BeingAttachmentValidationException, match=field_name):
            BeingAttachment(**fields)  # type: ignore[arg-type]


class TestBeingAttachmentEquality:
    """同じ環境かを、識別子で見分けることを保証する。"""

    def test_same_environment_is_equal_and_hashes_alike(self) -> None:
        """識別子と表示の名前が同じなら等しく、set では 1 つになる。"""
        first = BeingAttachment(environment_id="mine_village_v1#1", environment_name="廃坑の山村")
        second = BeingAttachment(environment_id="mine_village_v1#1", environment_name="廃坑の山村")

        assert first == second
        assert len({first, second}) == 1

    def test_same_name_in_another_world_is_another_environment(self) -> None:
        """同じシナリオの世界が 2 つ立って表示の名前が重なっても、識別子が違えば別の環境。"""
        first = BeingAttachment(environment_id="mine_village_v1#1", environment_name="廃坑の山村")
        second = BeingAttachment(environment_id="mine_village_v1#2", environment_name="廃坑の山村")

        assert first != second
