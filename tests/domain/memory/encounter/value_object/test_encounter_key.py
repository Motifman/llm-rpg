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

    def test_builds_kind_identifier_canonical(self) -> None:
        """kind + identifier の正常値で canonical が生成される。"""
        key = EncounterKey(kind="player", identifier="noa")
        assert key.canonical == "player:noa"

    def test_kind_empty_string_validation_raises_validation_exception(self) -> None:
        """kind の空文字は不変条件違反。"""
        with pytest.raises(EncounterKeyValidationException, match="kind"):
            EncounterKey(kind="", identifier="noa")

    def test_kind_blank_validation_raises_validation_exception(self) -> None:
        """kind の空白のみも非空判定で弾く。"""
        with pytest.raises(EncounterKeyValidationException, match="kind"):
            EncounterKey(kind="   ", identifier="noa")

    def test_identifier_empty_string_validation_raises_validation_exception(self) -> None:
        """identifier の空文字は不変条件違反。"""
        with pytest.raises(EncounterKeyValidationException, match="identifier"):
            EncounterKey(kind="player", identifier="")

    def test_identifier_blank_validation_raises_validation_exception(self) -> None:
        """identifier の空白のみも非空判定で弾く (= kind と対称)。"""
        with pytest.raises(EncounterKeyValidationException, match="identifier"):
            EncounterKey(kind="player", identifier="   ")

    def test_kind_containing_separator_raises_validation_exception(self) -> None:
        """kind に ``:`` を含むと canonical の往復が壊れるため拒否する。"""
        with pytest.raises(EncounterKeyValidationException, match="kind"):
            EncounterKey(kind="play:er", identifier="noa")

    def test_identifier_separator_validation_raises_validation_exception(self) -> None:
        """identifier に ``:`` を含むと canonical の往復が壊れるため拒否する。"""
        with pytest.raises(EncounterKeyValidationException, match="identifier"):
            EncounterKey(kind="player", identifier="no:a")

    def test_non_string_kind_raises_validation_exception(self) -> None:
        """kind は str 型である必要がある (= ドメイン型の防衛)。"""
        with pytest.raises(EncounterKeyValidationException, match="kind"):
            EncounterKey(kind=42, identifier="noa")  # type: ignore[arg-type]

    def test_identifier_str_validation_raises_validation_exception(self) -> None:
        """identifier は str 型である必要がある。"""
        with pytest.raises(EncounterKeyValidationException, match="identifier"):
            EncounterKey(kind="player", identifier=42)  # type: ignore[arg-type]

    def test_unknown_kind_kinds(self) -> None:
        """forward-compat: 後から ``weather`` / ``emotion`` を追加する余地を残す。"""
        key = EncounterKey(kind="weather", identifier="storm")
        assert key.canonical == "weather:storm"


class TestEncounterKeyFactories:
    """``EncounterKey.player`` / ``.spot`` / ``.event`` factory の挙動。"""

    def test_builds_player_factory_canonical_player_prefix(self) -> None:
        """playerfactory は canonical を playerprefix で組み立てる。"""
        assert EncounterKey.player("noa").canonical == "player:noa"

    def test_builds_spot_factory_canonical_spot_prefix(self) -> None:
        """spotfactory は canonical を spotprefix で組み立てる。"""
        assert EncounterKey.spot("forest_clearing").canonical == "spot:forest_clearing"

    def test_builds_event_factory_canonical_event_prefix(self) -> None:
        """eventfactory は canonical を eventprefix で組み立てる。"""
        assert EncounterKey.event("storm_arrives").canonical == "event:storm_arrives"


class TestEncounterKeyFromCanonical:
    """canonical 文字列からの parse (snapshot restore で使う想定)。"""

    def test_canonical_parse_kind_identifier(self) -> None:
        """canonical を parse して kind と identifier に分解する。"""
        key = EncounterKey.from_canonical("spot:forest_clearing")
        assert key.kind == "spot"
        assert key.identifier == "forest_clearing"

    def test_separator_canonical_validation_raises_validation_exception(self) -> None:
        """separator が無い canonical は validation 例外を投げる。"""
        with pytest.raises(EncounterKeyValidationException, match="canonical"):
            EncounterKey.from_canonical("just_a_string")

    def test_identifier_separator_multiple_separator(
        self,
    ) -> None:
        """identifier に ``:`` を含めば validation で弾かれる (canonical 不変条件)。"""
        # split(":", 1) で kind="event", identifier="a:b" となるが、
        # __post_init__ が identifier 内 ":" を弾く
        with pytest.raises(EncounterKeyValidationException, match="identifier"):
            EncounterKey.from_canonical("event:a:b")


class TestEncounterKeyEquality:
    """frozen dataclass としての等価性 (snapshot dedup / dict key 利用想定)。"""

    def test_same_kind_identifier_key_hash(self) -> None:
        """同じ kindidentifier の key は等価で hash も等価。"""
        a = EncounterKey.player("noa")
        b = EncounterKey.player("noa")
        assert a == b
        assert hash(a) == hash(b)

    def test_kind_key_different(self) -> None:
        """異なる kind の key は別物として扱う。"""
        assert EncounterKey.player("noa") != EncounterKey.event("noa")
