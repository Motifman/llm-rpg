"""U9b (予測誤差統一設計 部品5・想起の信用割り当て) — 的中側 sidecar store。

「この記憶を思い出して立てた予測が当たった」回数を episode 単位で数える
``InMemoryEpisodicRecallSuccessStore`` の roundtrip / 分離 / snapshot 用
list_all_by_being・replace_all_by_being を保証する。慣化 sidecar
(``test_episodic_recall_habituation.py``) と対称のテスト構成。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
    InMemoryEpisodicRecallSuccessStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


class TestInMemoryEpisodicRecallSuccessStore:
    """sidecar store の roundtrip と分離。"""

    def test_未記録の_episode_に対する_get_は_0(self) -> None:
        """未 hit = 0 を返す。"""
        store = InMemoryEpisodicRecallSuccessStore()
        bid = BeingId("being_w1_p1")
        assert store.get_hit_count_by_being(bid, "ep-1") == 0

    def test_record_hit_後に_get_で_引ける(self) -> None:
        """1 回 record すると hit_count が 1 になる。"""
        store = InMemoryEpisodicRecallSuccessStore()
        bid = BeingId("being_w1_p1")
        store.record_hit_by_being(bid, "ep-1")
        assert store.get_hit_count_by_being(bid, "ep-1") == 1

    def test_複数回_record_すると_加算される(self) -> None:
        """的中を重ねるほど hit_count が積み上がる。"""
        store = InMemoryEpisodicRecallSuccessStore()
        bid = BeingId("being_w1_p1")
        store.record_hit_by_being(bid, "ep-1")
        store.record_hit_by_being(bid, "ep-1")
        store.record_hit_by_being(bid, "ep-1")
        assert store.get_hit_count_by_being(bid, "ep-1") == 3

    def test_別の_episode_は独立に加算される(self) -> None:
        """episode ごとに hit_count は独立。"""
        store = InMemoryEpisodicRecallSuccessStore()
        bid = BeingId("being_w1_p1")
        store.record_hit_by_being(bid, "ep-1")
        store.record_hit_by_being(bid, "ep-2")
        store.record_hit_by_being(bid, "ep-2")
        assert store.get_hit_count_by_being(bid, "ep-1") == 1
        assert store.get_hit_count_by_being(bid, "ep-2") == 2

    def test_別の_being_の_hit_は独立(self) -> None:
        """being が違えば hit_count も独立 (= 二人プレイで干渉しない)。"""
        store = InMemoryEpisodicRecallSuccessStore()
        b1 = BeingId("being_w1_p1")
        b2 = BeingId("being_w1_p2")
        store.record_hit_by_being(b1, "ep-shared")
        assert store.get_hit_count_by_being(b1, "ep-shared") == 1
        assert store.get_hit_count_by_being(b2, "ep-shared") == 0

    def test_being_id_が_BeingId_でなければ_TypeError(self) -> None:
        """境界での型ガード。"""
        store = InMemoryEpisodicRecallSuccessStore()
        with pytest.raises(TypeError):
            store.record_hit_by_being("not-a-being-id", "ep-1")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            store.get_hit_count_by_being("not-a-being-id", "ep-1")  # type: ignore[arg-type]

    def test_episode_id_が空文字なら_ValueError(self) -> None:
        """episode_id は非空文字列。"""
        store = InMemoryEpisodicRecallSuccessStore()
        bid = BeingId("being_w1_p1")
        with pytest.raises(ValueError):
            store.record_hit_by_being(bid, "")


class TestListAllAndReplaceAllByBeing:
    """snapshot capture/restore 用 API の roundtrip。"""

    def test_list_all_by_being_は空なら空dict(self) -> None:
        store = InMemoryEpisodicRecallSuccessStore()
        bid = BeingId("being_w1_p1")
        assert store.list_all_by_being(bid) == {}

    def test_list_all_by_being_は記録内容を反映する(self) -> None:
        store = InMemoryEpisodicRecallSuccessStore()
        bid = BeingId("being_w1_p1")
        store.record_hit_by_being(bid, "ep-1")
        store.record_hit_by_being(bid, "ep-1")
        store.record_hit_by_being(bid, "ep-2")
        assert store.list_all_by_being(bid) == {"ep-1": 2, "ep-2": 1}

    def test_list_all_by_being_の戻り値を書き換えても内部状態は壊れない(self) -> None:
        """copy を返すので呼出側の変更が内部 dict に波及しない。"""
        store = InMemoryEpisodicRecallSuccessStore()
        bid = BeingId("being_w1_p1")
        store.record_hit_by_being(bid, "ep-1")
        snapshot = store.list_all_by_being(bid)
        snapshot["ep-1"] = 999
        assert store.get_hit_count_by_being(bid, "ep-1") == 1

    def test_replace_all_by_being_で一括上書きできる(self) -> None:
        store = InMemoryEpisodicRecallSuccessStore()
        bid = BeingId("being_w1_p1")
        store.record_hit_by_being(bid, "ep-1")
        store.replace_all_by_being(bid, {"ep-9": 5})
        assert store.get_hit_count_by_being(bid, "ep-1") == 0
        assert store.get_hit_count_by_being(bid, "ep-9") == 5

    def test_replace_all_by_being_に空dictを渡すとbeingのstateが消える(self) -> None:
        """capture 時の空状態と bit identity を保つための挙動。"""
        store = InMemoryEpisodicRecallSuccessStore()
        bid = BeingId("being_w1_p1")
        store.record_hit_by_being(bid, "ep-1")
        store.replace_all_by_being(bid, {})
        assert store.list_all_by_being(bid) == {}
