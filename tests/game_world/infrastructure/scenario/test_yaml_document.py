from __future__ import annotations

from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation
from ai_rpg_world.game_world.infrastructure.scenario.yaml_document import read_yaml_document


class TestReadYamlDocument:
    """read_yaml_document が YAML を素の値に読み、書き方の誤りを場所つきの DesignFlaw にすることを保証する。"""

    def test_mapping_is_read_into_plain_values(self) -> None:
        """地図・列・文字・数・真偽は、dict・list・str・int・bool に読む。"""
        document = read_yaml_document(
            "spots:\n  mine:\n    name: 坑道\n    capacity: 3\n    outdoor: false\n    tags: [a, b]\n"
        )

        assert document.value == {
            "spots": {"mine": {"name": "坑道", "capacity": 3, "outdoor": False, "tags": ["a", "b"]}}
        }
        assert document.flaws == ()

    def test_duplicated_key_becomes_flaw_at_its_place(self) -> None:
        """同じ鍵を 2 回書くと、その鍵の場所を付けた DesignFlaw になる。"""
        document = read_yaml_document("spots:\n  mine:\n    name: 坑道\n    name: 縦穴\n")

        assert [flaw.location for flaw in document.flaws] == [DesignLocation("spot", "mine", "name")]

    def test_duplicated_declaration_name_becomes_flaw(self) -> None:
        """同じ名前の宣言を 2 回書くと、その宣言の場所を付けた DesignFlaw になる。"""
        document = read_yaml_document("spots:\n  mine: {name: a}\n  mine: {name: b}\n")

        assert [flaw.location for flaw in document.flaws] == [DesignLocation("spot", "mine", "")]

    def test_broken_yaml_becomes_flaw_on_the_world(self) -> None:
        """YAML として読めない文は、素の例外を出さず、世界の場所を付けた DesignFlaw 1 つになる。"""
        document = read_yaml_document("spots: [\n")

        assert len(document.flaws) == 1
        assert isinstance(document.flaws[0], DesignFlaw)
        assert document.flaws[0].location == DesignLocation("world", "world", "")
