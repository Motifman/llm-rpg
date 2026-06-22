"""Afterglow index — 「ぼんやり覚えてる」見出し一覧の保持と更新を保証する。

想起スロット (#580 / #583 で導入) は「鮮明な記憶」を扱う希少資源。それに対し
Afterglow は「鮮明には浮かばないがヒントを与えれば思い出せる」状態を 1 行
見出しで保持する layered な記憶階層の下層に当たる。

経路は 2 つ:
- slot から滞在期間超過で退去した episode (= SLOT_EVICTED)
- 想起候補としては上がったが slot の score 閾値で入れなかった弱い hit
  (= WEAK_RECALL)

いずれも heading (PR-B で導入した 1 行サマリ) が乗っている前提で、後段の
prompt section / 復元ツール (PR-D) で使う。

本ファイルは value object と pure policy 関数の境界値を保証する。
store の挙動とリハーサル (= 再投入で entered_tick 更新) もここで押さえる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.afterglow_store import (
    AfterglowEntry,
    AfterglowSource,
    InMemoryAfterglowStore,
    apply_afterglow_policy,
    make_afterglow_handle,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


def _entry(
    episode_id: str = "e1",
    heading: str = "h",
    entered_tick: int = 0,
    source: AfterglowSource = AfterglowSource.SLOT_EVICTED,
) -> AfterglowEntry:
    return AfterglowEntry(
        episode_id=episode_id,
        heading=heading,
        entered_tick=entered_tick,
        source=source,
    )


class TestAfterglowEntryValidation:
    """AfterglowEntry の 4 フィールドが揃って初めて構築できる、空 heading は弾く。"""

    def test_entry_holds_all_four_fields(self) -> None:
        """episode_id / heading / entered_tick / source を保持する。"""
        e = AfterglowEntry(
            episode_id="ep-1",
            heading="司書の手記",
            entered_tick=3,
            source=AfterglowSource.SLOT_EVICTED,
        )
        assert e.episode_id == "ep-1"
        assert e.heading == "司書の手記"
        assert e.entered_tick == 3
        assert e.source == AfterglowSource.SLOT_EVICTED

    def test_empty_heading_raises_value_error(self) -> None:
        """heading が空文字だと afterglow の意味 (= 見出しを並べる) が崩れる。
        SubjectiveEpisode 側でも optional_non_blank で弾いているのと同方針。"""
        with pytest.raises(ValueError):
            _entry(heading="")


class TestApplyAfterglowPolicy:
    """apply_afterglow_policy は前 tick の index + 新規追加 + tick 数 + 上限
    パラメータから、次の index を決める純関数。境界値を厳密に押さえる。"""

    def test_empty_index_accepts_a_new_entry(self) -> None:
        """空 index に新規エントリを 1 件追加すると、その 1 件だけが残る。"""
        new_entry = _entry(episode_id="e1", heading="h1", entered_tick=0)
        result = apply_afterglow_policy(
            prev_index=(),
            incoming=(new_entry,),
            current_tick=0,
            capacity=10,
            max_residence=10,
        )
        assert [e.episode_id for e in result] == ["e1"]

    def test_entry_older_than_max_residence_is_dropped(self) -> None:
        """前 tick の index にある古いエントリは M_L tick 経過で消える。
        現状の tick が entered_tick + M_L を越えたら退去対象。"""
        old = _entry(episode_id="old", heading="h", entered_tick=0)
        result = apply_afterglow_policy(
            prev_index=(old,),
            incoming=(),
            current_tick=10,  # entered_tick=0, M_L=10 → age 10 で退去
            capacity=10,
            max_residence=10,
        )
        assert result == ()

    def test_exceeds_capacity_drops_oldest_first(self) -> None:
        """capacity を超えたら entered_tick が古いものから退去 (FIFO)。
        新規エントリで上限を埋め、古い 1 件を押し出す。"""
        old1 = _entry(episode_id="o1", heading="h", entered_tick=0)
        old2 = _entry(episode_id="o2", heading="h", entered_tick=1)
        new = _entry(episode_id="new", heading="h", entered_tick=2)
        result = apply_afterglow_policy(
            prev_index=(old1, old2),
            incoming=(new,),
            current_tick=2,
            capacity=2,  # 既存 2 + 新規 1 で超過 → o1 が押し出される
            max_residence=10,
        )
        ids = [e.episode_id for e in result]
        assert "o1" not in ids
        assert set(ids) == {"o2", "new"}

    def test_reinsertion_updates_entered_tick(self) -> None:
        """同じ episode_id が再投入されたら entered_tick を更新する
        (= 「もう一度想起された」 = リハーサル)。これで M_L カウントが
        リセットされ、最近想起したものは長く居続ける。"""
        old = _entry(episode_id="e1", heading="h", entered_tick=0)
        re_entered = _entry(episode_id="e1", heading="h", entered_tick=5)
        result = apply_afterglow_policy(
            prev_index=(old,),
            incoming=(re_entered,),
            current_tick=5,
            capacity=10,
            max_residence=10,
        )
        assert len(result) == 1
        assert result[0].entered_tick == 5


class TestMakeAfterglowHandle:
    """make_afterglow_handle は episode_id を「ep_<先頭 6 文字>」に縮める。

    過去事例: spot をラベル (= tick ごとに変わる識別子) で指定させると、
    過去の tool 履歴に古いラベルが残って LLM が混乱した。afterglow handle
    は同じ episode に対して常に同じ値が返るよう、episode_id ベースで決定する。
    """

    def test_handle_uses_ep_prefix_with_first_six_chars(self) -> None:
        """episode_id の先頭 6 文字に ``ep_`` を付けた形を返す。"""
        assert make_afterglow_handle("3f2a-7b8c-9d0e") == "ep_3f2a-7"

    def test_handle_short_id_is_kept_as_is(self) -> None:
        """6 文字未満の episode_id でも crash せずに使える形を返す。"""
        assert make_afterglow_handle("abc") == "ep_abc"


def _being(value: str = "being_w1_p1") -> BeingId:
    return BeingId(value)


class TestInMemoryAfterglowStore:
    """sidecar store の永続性と being 隔離を保証する。"""

    def test_unrecorded_being_returns_empty_index(self) -> None:
        """初期状態の getter は空 tuple を返し、書込みなしで例外も出さない。"""
        store = InMemoryAfterglowStore()
        assert store.get_index(_being()) == ()

    def test_apply_decision_updates_index(self) -> None:
        """apply_decision に new_index を渡すと、それが get_index で読み出せる。"""
        store = InMemoryAfterglowStore()
        being = _being()
        new_index = (_entry(episode_id="e1", heading="h", entered_tick=0),)
        store.apply_decision(being, new_index)
        assert [e.episode_id for e in store.get_index(being)] == ["e1"]

    def test_beings_are_isolated(self) -> None:
        """1P と 2P で index が混ざらない (= 二人プレイでの干渉を防ぐ)。"""
        store = InMemoryAfterglowStore()
        being_a = BeingId("being_w1_p1")
        being_b = BeingId("being_w1_p2")
        store.apply_decision(
            being_a, (_entry(episode_id="e1", heading="h"),)
        )
        assert store.get_index(being_a) != ()
        assert store.get_index(being_b) == ()


class TestFormatAfterglowSection:
    """prompt の【さっき思い出した記憶の見出し】section を組む整形関数の
    挙動を保証する。afterglow が空のときは section を出さず、非空のときは
    handle 付き 1 行で並ぶ。"""

    def test_empty_index_returns_empty_string(self) -> None:
        """index が空 / None のときは section を出さないことで prompt が
        無駄に膨らまないようにする。"""
        from ai_rpg_world.application.llm.services.prompt_builder import (
            _format_afterglow_section,
        )

        assert _format_afterglow_section(None) == ""
        assert _format_afterglow_section(()) == ""

    def test_non_empty_index_renders_heading_with_handle(self) -> None:
        """各エントリが ``[ep_<6 文字>] heading`` 形式の 1 行で並び、
        全体が「【さっき思い出した記憶の見出し】」見出しで始まる。"""
        from ai_rpg_world.application.llm.services.prompt_builder import (
            _format_afterglow_section,
        )

        index = (
            AfterglowEntry(
                episode_id="3f2a7b8c-9d0e",
                heading="司書の手記",
                entered_tick=0,
                source=AfterglowSource.SLOT_EVICTED,
            ),
        )
        section = _format_afterglow_section(index)
        assert "【さっき思い出した記憶の見出し】" in section
        # handle 形式と heading が同じ行に並ぶ
        assert "[ep_3f2a7b" in section
        assert "司書の手記" in section
