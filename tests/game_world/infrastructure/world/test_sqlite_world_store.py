from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ai_rpg_world.game_world.application.world_store import AggregateWithMemento
from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.value_object import WorldTick
from ai_rpg_world.game_world.domain.world_progress import WorldEnding, WorldEndingMemento
from ai_rpg_world.game_world.domain.world_records import WorldFlags
from ai_rpg_world.game_world.infrastructure.persistence.aggregate_codecs import GAME_WORLD_CODECS, StoredMemento
from ai_rpg_world.game_world.infrastructure.persistence.stored_memento_exception import MementoNotStorableException
from ai_rpg_world.game_world.infrastructure.world.seedable_random_source import SeedableRandomSource
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import (
    _ONE_PER_WORLD,
    _OWNER_OF_MEMENTO,
    STORAGE_VERSION,
    SqliteWorldStore,
)
from ai_rpg_world.game_world.infrastructure.world.stored_world_exception import (
    StoredWorldMismatchException,
    WorldSessionEndedException,
    WorldSessionStillOpenException,
)
from tests.game_world.application.world_store_contract import (
    BELL,
    WORLD,
    WorldStoreContract,
    design_with_bell,
)

_HASH = "hash-of-the-scenario"


def _empty(path: Path | str, design: WorldDesign) -> SqliteWorldStore:
    SqliteWorldStore.create(
        path,
        world_id=WORLD,
        scenario="contract.yaml",
        scenario_hash=_HASH,
        design=design,
        random=SeedableRandomSource(1),
    ).close()
    return SqliteWorldStore.open(path, scenario_hash=_HASH, design=design, random=SeedableRandomSource(1))


def _created(path: Path | str, design: WorldDesign, *aggregates: AggregateWithMemento) -> SqliteWorldStore:
    store = _empty(path, design)
    store.start_world(aggregates)
    return store


class TestSqliteWorldStoreContract(WorldStoreContract):
    """SqliteWorldStore が、WorldStore の共通の約束を守ることを保証する。"""

    @pytest.fixture(autouse=True)
    def _directory(self, tmp_path: Path) -> None:
        self._path = tmp_path / "world.sqlite"

    def empty_store(self, design: WorldDesign) -> SqliteWorldStore:
        return _empty(self._path, design)


class TestSqliteWorldStoreKeysAtStart:
    """始まりの集約の行の key を、どの集約の種類についても決められることを保証する。"""

    def test_every_codec_kind_is_either_one_per_world_or_has_an_owner(self) -> None:
        """変換が登録されたすべての memento の型は、世界に 1 つの型か、持ち主の決まった型の、どちらか一方にだけ入っている。"""
        assert _ONE_PER_WORLD.isdisjoint(_OWNER_OF_MEMENTO)
        assert _ONE_PER_WORLD | set(_OWNER_OF_MEMENTO) == GAME_WORLD_CODECS.memento_types()


class TestSqliteWorldStoreOpening:
    """SqliteWorldStore.open が、開き直す DB のシナリオの中身と表の版を確かめることを保証する。"""

    def test_open_with_different_scenario_hash_raises(self, tmp_path: Path) -> None:
        """create のときと違うシナリオのハッシュで open すると StoredWorldMismatchException を投げる。"""
        path = tmp_path / "world.sqlite"
        _created(path, design_with_bell()).close()

        with pytest.raises(StoredWorldMismatchException):
            SqliteWorldStore.open(
                path, scenario_hash="another-hash", design=design_with_bell(), random=SeedableRandomSource(1)
            )

    def test_open_with_different_storage_version_raises(self, tmp_path: Path) -> None:
        """表の版が今のコードと違う DB を open すると StoredWorldMismatchException を投げる。"""
        path = tmp_path / "world.sqlite"
        _created(path, design_with_bell()).close()
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE world SET storage_version = ?", (STORAGE_VERSION + 1,))

        with pytest.raises(StoredWorldMismatchException):
            SqliteWorldStore.open(path, scenario_hash=_HASH, design=design_with_bell(), random=SeedableRandomSource(1))

    def test_create_on_file_already_holding_a_world_raises(self, tmp_path: Path) -> None:
        """すでに世界のある DB に create すると StoredWorldMismatchException を投げる。"""
        path = tmp_path / "world.sqlite"
        _created(path, design_with_bell()).close()

        with pytest.raises(StoredWorldMismatchException):
            SqliteWorldStore.create(
                path,
                world_id=WORLD,
                scenario="contract.yaml",
                scenario_hash=_HASH,
                design=design_with_bell(),
                random=SeedableRandomSource(1),
            )


class TestSqliteWorldSessionWriting:
    """SqliteWorldSession.commit が、範囲の中で変わった集約の行だけを書くことを保証する。"""

    def test_commit_does_not_write_aggregate_left_unchanged(self, tmp_path: Path) -> None:
        """引いただけで変えていない集約は、commit で UPDATE を出さない。"""
        store = _created(tmp_path / "world.sqlite", design_with_bell(), WorldFlags.start(WORLD))
        session = store.session()
        session.facts().flags()
        statements: list[str] = []
        store._connection.set_trace_callback(statements.append)

        session.commit()

        assert [s for s in statements if s.startswith("UPDATE")] == []

    def test_commit_writes_aggregate_changed_in_scope(self, tmp_path: Path) -> None:
        """範囲の中で変えた集約は、commit で 1 回 UPDATE を出す。"""
        store = _created(tmp_path / "world.sqlite", design_with_bell(), WorldFlags.start(WORLD))
        session = store.session()
        session.aggregates().flags().raise_flag(BELL, WorldTimePassing(WorldTick(3)))
        statements: list[str] = []
        store._connection.set_trace_callback(statements.append)

        session.commit()

        assert len([s for s in statements if s.startswith("UPDATE")]) == 1


class TestSqliteWorldSessionEnding:
    """確定か巻き戻しで終わった範囲は、続けて使えないことを保証する。"""

    def test_session_used_after_commit_raises(self, tmp_path: Path) -> None:
        """commit したあとの範囲から集約を引くと WorldSessionEndedException を投げる。"""
        store = _created(tmp_path / "world.sqlite", design_with_bell(), WorldFlags.start(WORLD))
        session = store.session()
        session.commit()

        with pytest.raises(WorldSessionEndedException):
            session.facts().flags()

    def test_session_rolled_back_cannot_commit(self, tmp_path: Path) -> None:
        """roll_back したあとの範囲で commit すると WorldSessionEndedException を投げる。"""
        store = _created(tmp_path / "world.sqlite", design_with_bell(), WorldFlags.start(WORLD))
        session = store.session()
        session.roll_back()

        with pytest.raises(WorldSessionEndedException):
            session.commit()


class TestSqliteWorldSessionFailingCommit:
    """commit が途中で失敗したとき、書きかけの行が残らず、次の範囲を始められることを保証する。"""

    def test_commit_failing_after_first_update_leaves_no_row_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """旗の行を書いたあと終わりの行で JSON にできずに止まると、例外が出て、次の範囲では旗が立っていない。"""
        store = _created(
            tmp_path / "world.sqlite", design_with_bell(), WorldFlags.start(WORLD), WorldEnding.start(WORLD)
        )
        session = store.session()
        session.aggregates().flags().raise_flag(BELL, WorldTimePassing(WorldTick(3)))
        session.ending().end(WorldTick(3))
        stored = GAME_WORLD_CODECS.stored

        def stored_refusing_ending(memento: object) -> StoredMemento:
            if isinstance(memento, WorldEndingMemento):
                raise MementoNotStorableException("refused for the test")
            return stored(memento)

        monkeypatch.setattr(GAME_WORLD_CODECS, "stored", stored_refusing_ending)

        with pytest.raises(MementoNotStorableException):
            session.commit()
        monkeypatch.undo()

        assert store.session().facts().flags().is_raised(BELL) is False


class TestSqliteWorldStoreSessionsInTurn:
    """範囲は 1 つずつしか開けないことを保証する。"""

    def test_session_while_previous_is_open_raises(self, tmp_path: Path) -> None:
        """前の範囲を commit も roll_back もせずに次の範囲を始めると WorldSessionStillOpenException を投げる。"""
        store = _created(tmp_path / "world.sqlite", design_with_bell(), WorldFlags.start(WORLD))
        store.session()

        with pytest.raises(WorldSessionStillOpenException):
            store.session()


class TestSqliteWorldStoreStartingWhileSessionOpen:
    """範囲が開いているあいだは、始まりの集約を書けないことを保証する。"""

    def test_start_world_while_a_session_is_open_raises(self, tmp_path: Path) -> None:
        """範囲を開いたまま start_world を呼ぶと WorldSessionStillOpenException を投げる。"""
        store = _empty(tmp_path / "world.sqlite", design_with_bell())
        store.session()

        with pytest.raises(WorldSessionStillOpenException):
            store.start_world([WorldFlags.start(WORLD)])
