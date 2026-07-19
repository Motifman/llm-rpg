"""InMemoryEncounterMemory の挙動テスト。

PR1 範囲の単体テスト。observation pipeline 連携 / snapshot codec は別 PR。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)
from ai_rpg_world.application.encounter.contracts.interfaces import (
    IEncounterMemory,
)
from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
    EncounterRecordRuleException,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@pytest.fixture
def memory() -> InMemoryEncounterMemory:
    return InMemoryEncounterMemory()


@pytest.fixture
def kai() -> PlayerId:
    return PlayerId(1)


@pytest.fixture
def rin() -> PlayerId:
    return PlayerId(2)


@pytest.fixture
def noa_key() -> EncounterKey:
    return EncounterKey.player("noa")


@pytest.fixture
def clearing_key() -> EncounterKey:
    return EncounterKey.spot("forest_clearing")


class TestInMemoryEncounterMemoryProtocolConformance:
    """``IEncounterMemory`` protocol を満たすことの確認。"""

    def test_protocol(self, memory: InMemoryEncounterMemory) -> None:
        """protocol に適合する。"""
        assert isinstance(memory, IEncounterMemory)


class TestObserve:
    """``observe`` の upsert セマンティクス。"""

    def test_returns_first_observe_count1_record(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        noa_key: EncounterKey,
    ) -> None:
        """初回 observe は count1 の record を返す。"""
        record = memory.observe(kai, noa_key, current_tick=10)
        assert record.is_first is True
        assert record.count == 1
        assert record.first_seen_tick == 10
        assert record.last_seen_tick == 10

    def test_two_observe_count_two(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        noa_key: EncounterKey,
    ) -> None:
        """2 度目 observe は count が 2 になる。"""
        memory.observe(kai, noa_key, current_tick=10)
        record = memory.observe(kai, noa_key, current_tick=42)
        assert record.count == 2
        assert record.first_seen_tick == 10  # 不変
        assert record.last_seen_tick == 42  # 更新

    def test_observe_raises_exception(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        noa_key: EncounterKey,
    ) -> None:
        """observation pipeline の bug 検出のため fail-fast する。"""
        memory.observe(kai, noa_key, current_tick=10)
        with pytest.raises(EncounterRecordRuleException):
            memory.observe(kai, noa_key, current_tick=5)

    def test_current_tick_argument_current_tick_raises_exception(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        noa_key: EncounterKey,
    ) -> None:
        """observation pipeline からの debug 性のため、observe 段階で fail-fast する
        (= EncounterRecord 内部の "first_seen_tick" エラーに化けない)。"""
        from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
            EncounterRecordValidationException,
        )

        with pytest.raises(
            EncounterRecordValidationException, match="current_tick"
        ):
            memory.observe(kai, noa_key, current_tick=-1)

    def test_current_tick_int_bool_raises_exception(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        noa_key: EncounterKey,
    ) -> None:
        """bool は int サブクラスだが意味的に tick として扱うべきでない (silent
        failure 防止)。"""
        from ai_rpg_world.domain.memory.encounter.exception.encounter_exception import (
            EncounterRecordValidationException,
        )

        with pytest.raises(
            EncounterRecordValidationException, match="current_tick"
        ):
            memory.observe(kai, noa_key, current_tick=True)  # type: ignore[arg-type]

    def test_player_id_record_independent(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        rin: PlayerId,
        noa_key: EncounterKey,
    ) -> None:
        """kai が noa に会った経験は、rin が noa に会った経験と分離されている。"""
        memory.observe(kai, noa_key, current_tick=10)
        record_rin = memory.observe(rin, noa_key, current_tick=42)
        assert record_rin.is_first is True
        assert record_rin.count == 1
        # kai 側は影響なし
        kai_record = memory.lookup(kai, noa_key)
        assert kai_record is not None and kai_record.count == 1

    def test_kind_record_independent(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
    ) -> None:
        """同一 identifier でも kind が違えば別物として扱う。"""
        as_player = memory.observe(
            kai, EncounterKey.player("noa"), current_tick=10
        )
        as_event = memory.observe(
            kai, EncounterKey.event("noa"), current_tick=42
        )
        assert as_player.is_first is True
        assert as_event.is_first is True  # 別の key として first 扱い

    def test_player_id_player_id_raises_type_error_3(
        self,
        memory: InMemoryEncounterMemory,
        noa_key: EncounterKey,
    ) -> None:
        """player id が PlayerId でなければ TypeError。"""
        with pytest.raises(TypeError, match="player_id"):
            memory.observe(1, noa_key, current_tick=0)  # type: ignore[arg-type]

    def test_key_en_count_er_key_raises_type_error_2(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
    ) -> None:
        """key が EncounterKey でなければ TypeError。"""
        with pytest.raises(TypeError, match="key"):
            memory.observe(kai, "player:noa", current_tick=0)  # type: ignore[arg-type]


class TestLookup:
    """``lookup`` は record があれば返し、無ければ None を返す。"""

    def test_observe_key_lookup_none(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        noa_key: EncounterKey,
    ) -> None:
        """未 observe な key の lookup は None。"""
        assert memory.lookup(kai, noa_key) is None

    def test_returns_observe_key_lookup_record(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        noa_key: EncounterKey,
    ) -> None:
        """observe 済みの key の lookup は record を返す。"""
        memory.observe(kai, noa_key, current_tick=10)
        record = memory.lookup(kai, noa_key)
        assert record is not None
        assert record.count == 1
        assert record.last_seen_tick == 10

    def test_player_unregistered_lookup_none(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        rin: PlayerId,
        noa_key: EncounterKey,
    ) -> None:
        """player が未登録なら lookup は None。"""
        memory.observe(kai, noa_key, current_tick=10)
        assert memory.lookup(rin, noa_key) is None

    def test_player_id_player_id_raises_type_error_2(
        self,
        memory: InMemoryEncounterMemory,
        noa_key: EncounterKey,
    ) -> None:
        """player id が PlayerId でなければ TypeError。"""
        with pytest.raises(TypeError, match="player_id"):
            memory.lookup(1, noa_key)  # type: ignore[arg-type]

    def test_key_en_count_er_key_raises_type_error(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
    ) -> None:
        """observe と同じく key の型不正は debug 性のため fail-fast する。"""
        with pytest.raises(TypeError, match="key"):
            memory.lookup(kai, "player:noa")  # type: ignore[arg-type]


class TestRecordsFor:
    """``get_records_for`` は player ごとの全 record を読み取り専用で返す。"""

    def test_records_empty_dict_observe_player_get(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
    ) -> None:
        """未 observe な player の getrecordsfor は空 dict。"""
        assert memory.get_records_for(kai) == {}

    def test_records_all_record_returns_multiple_observe_after(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        noa_key: EncounterKey,
        clearing_key: EncounterKey,
    ) -> None:
        """複数 observe 後 recordsfor は全 record を返す。"""
        memory.observe(kai, noa_key, current_tick=10)
        memory.observe(kai, clearing_key, current_tick=20)
        memory.observe(kai, noa_key, current_tick=30)

        records = memory.get_records_for(kai)
        assert set(records.keys()) == {noa_key, clearing_key}
        assert records[noa_key].count == 2
        assert records[clearing_key].count == 1

    def test_records_key_encounter_key_type_canonical_round_trips(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
    ) -> None:
        """snapshot codec が EncounterKey で iterate しやすくする。"""
        memory.observe(
            kai, EncounterKey.event("storm_arrives"), current_tick=5
        )
        records = memory.get_records_for(kai)
        assert len(records) == 1
        key = next(iter(records.keys()))
        assert isinstance(key, EncounterKey)
        assert key.canonical == "event:storm_arrives"

    def test_records_value_state(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        noa_key: EncounterKey,
    ) -> None:
        """返した dict を mutate しても内部 store は変わらない。"""
        memory.observe(kai, noa_key, current_tick=10)
        records = memory.get_records_for(kai)
        records.clear()  # type: ignore[attr-defined]
        # 再 lookup で record が残っていることを確認
        assert memory.lookup(kai, noa_key) is not None

    def test_player_id_player_id_raises_type_error(
        self,
        memory: InMemoryEncounterMemory,
    ) -> None:
        """player id が PlayerId でなければ TypeError。"""
        with pytest.raises(TypeError, match="player_id"):
            memory.get_records_for(1)  # type: ignore[arg-type]
