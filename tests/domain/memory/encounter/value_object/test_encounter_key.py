"""EncounterKey の不変条件と factory / parse の挙動テスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
    EncounterKeyValidationException,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)


class TestEncounterKeyConstruction:
    """``EncounterKey`` 直接構築時の不変条件検証。"""

    def test_kind_と_identifier_の_canonical_を_組み立てる(self) -> None:
        """kind + identifier の正常値で canonical が生成される。"""
        key = EncounterKey(kind="player", identifier="noa")
        assert key.canonical == "player:noa"

    def test_kind_が_空文字なら_validation_例外を投げる(self) -> None:
        """kind の空文字は不変条件違反。"""
        with pytest.raises(EncounterKeyValidationException, match="kind"):
            EncounterKey(kind="", identifier="noa")

    def test_kind_が_空白のみなら_validation_例外を投げる(self) -> None:
        """kind の空白のみも非空判定で弾く。"""
        with pytest.raises(EncounterKeyValidationException, match="kind"):
            EncounterKey(kind="   ", identifier="noa")

    def test_identifier_が_空文字なら_validation_例外を投げる(self) -> None:
        """identifier の空文字は不変条件違反。"""
        with pytest.raises(EncounterKeyValidationException, match="identifier"):
            EncounterKey(kind="player", identifier="")

    def test_identifier_が_空白のみなら_validation_例外を投げる(self) -> None:
        """identifier の空白のみも非空判定で弾く (= kind と対称)。"""
        with pytest.raises(EncounterKeyValidationException, match="identifier"):
            EncounterKey(kind="player", identifier="   ")

    def test_kind_に_separator_を_含むと_validation_例外を投げる(self) -> None:
        """kind に ``:`` を含むと canonical の往復が壊れるため拒否する。"""
        with pytest.raises(EncounterKeyValidationException, match="kind"):
            EncounterKey(kind="play:er", identifier="noa")

    def test_identifier_に_separator_を_含むと_validation_例外を投げる(self) -> None:
        """identifier に ``:`` を含むと canonical の往復が壊れるため拒否する。"""
        with pytest.raises(EncounterKeyValidationException, match="identifier"):
            EncounterKey(kind="player", identifier="no:a")

    def test_kind_が_str_でないなら_validation_例外を投げる(self) -> None:
        """kind は str 型である必要がある (= ドメイン型の防衛)。"""
        with pytest.raises(EncounterKeyValidationException, match="kind"):
            EncounterKey(kind=42, identifier="noa")  # type: ignore[arg-type]

    def test_identifier_が_str_でないなら_validation_例外を投げる(self) -> None:
        """identifier は str 型である必要がある。"""
        with pytest.raises(EncounterKeyValidationException, match="identifier"):
            EncounterKey(kind="player", identifier=42)  # type: ignore[arg-type]

    def test_未知_kind_でも_既知_kinds_に_含まれていなくても_受け入れる(self) -> None:
        """forward-compat: 後から ``weather`` / ``emotion`` を追加する余地を残す。"""
        key = EncounterKey(kind="weather", identifier="storm")
        assert key.canonical == "weather:storm"


class TestEncounterKeyFactories:
    """``EncounterKey.player`` / ``.spot`` / ``.event`` factory の挙動。"""

    def test_player_factory_は_canonical_を_player_prefix_で_組み立てる(self) -> None:
        assert EncounterKey.player("noa").canonical == "player:noa"

    def test_spot_factory_は_canonical_を_spot_prefix_で_組み立てる(self) -> None:
        assert EncounterKey.spot("forest_clearing").canonical == "spot:forest_clearing"

    def test_event_factory_は_canonical_を_event_prefix_で_組み立てる(self) -> None:
        assert EncounterKey.event("storm_arrives").canonical == "event:storm_arrives"


class TestEncounterKeyFromCanonical:
    """canonical 文字列からの parse (snapshot restore で使う想定)。"""

    def test_canonical_を_parse_して_kind_と_identifier_に_分解する(self) -> None:
        key = EncounterKey.from_canonical("spot:forest_clearing")
        assert key.kind == "spot"
        assert key.identifier == "forest_clearing"

    def test_separator_が_無い_canonical_は_validation_例外を_投げる(self) -> None:
        with pytest.raises(EncounterKeyValidationException, match="canonical"):
            EncounterKey.from_canonical("just_a_string")

    def test_identifier_側に_separator_が_複数_あっても_最初の_separator_で_分割する(
        self,
    ) -> None:
        """identifier に ``:`` を含めば validation で弾かれる (canonical 不変条件)。"""
        # split(":", 1) で kind="event", identifier="a:b" となるが、
        # __post_init__ が identifier 内 ":" を弾く
        with pytest.raises(EncounterKeyValidationException, match="identifier"):
            EncounterKey.from_canonical("event:a:b")


class TestEncounterKeyEquality:
    """frozen dataclass としての等価性 (snapshot dedup / dict key 利用想定)。"""

    def test_同じ_kind_identifier_の_key_は_等価で_hash_も_等価(self) -> None:
        a = EncounterKey.player("noa")
        b = EncounterKey.player("noa")
        assert a == b
        assert hash(a) == hash(b)

    def test_異なる_kind_の_key_は_別物として扱う(self) -> None:
        assert EncounterKey.player("noa") != EncounterKey.event("noa")
