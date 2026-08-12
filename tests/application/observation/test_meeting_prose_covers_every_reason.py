"""会議の観測文が、始まり方・終わり方のすべてを言い分けることを保証する。

## なぜこの試験が要るか

prose は理由ごとの表で引いていたが、理由が**生の文字列**だったため**網羅を縛る
相手がいなかった**。

    template = self._MEETING_TRIGGER_PROSE.get(
        event.trigger, "招集がかかった。全員が集まる。"
    )

新しい理由を足すと、**誰が何をしたか分からない汎用文へ静かに倒れる**。表に載せ
忘れたことは誰にも見えない。

実測では実 run に出た 4 種 (`body_report` 63 / `vote_concluded` 72 /
`emergency_button` 18 / `tick_limit` 9) はすべて表にあり、**今の実害はゼロ**である。
`silence` だけ未出現。潜在バグを構造で塞ぐのがこの試験の目的。

## 落ちる / 落ちないの線引き

未知の理由が来たとき、**例外は投げない**。#1035 (屋内判定) では投げる判断をしたが、
あちらは「配信先を間違える」= 世界が嘘をつく失敗だった。こちらは「言い方が漠然と
する」= 世界が曖昧になるだけで、嘘ではない。**表示の粒度のために world を止めない。**

代わりに warning を出して見えるようにし、**そもそも未知が来ないこと**を網羅テスト
で保証する。理由の集合は engine の enum なので、テストが通れば実行時に未知は来ない。
"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.application.observation.services.formatters._spot_graph_object_handler import (  # noqa: E501
    SpotGraphObjectHandler,
)
from ai_rpg_world.domain.world_graph.enum.meeting_trigger import (
    MeetingEndReason,
    MeetingStartTrigger,
)


def _start_prose() -> dict:
    return SpotGraphObjectHandler._MEETING_TRIGGER_PROSE


def _end_prose() -> dict:
    return SpotGraphObjectHandler._MEETING_END_PROSE


class TestEveryStartTriggerHasItsOwnProse:
    """会議の始まり方すべてに専用の文がある。"""

    def test_no_start_trigger_is_missing(self) -> None:
        """`MeetingStartTrigger` 全件が表にある。

        足して書き忘れると「招集がかかった」という**誰が何をしたか分からない文**へ
        静かに倒れる。
        """
        missing = sorted(
            t.name for t in MeetingStartTrigger if t.value not in _start_prose()
        )

        assert missing == [], missing

    def test_no_start_entry_is_stale(self) -> None:
        """表に、enum から消えた理由のキーが残っていない。"""
        known = {t.value for t in MeetingStartTrigger}
        stale = sorted(k for k in _start_prose() if k not in known)

        assert stale == [], stale

    def test_every_start_prose_names_the_initiator(self) -> None:
        """始まりの文はすべて「誰が」を差し込める。

        `{who}` が無い文を書くと、招集した人が誰か分からない。既定の汎用文へ倒れた
        ときと同じ情報量になってしまう。
        """
        without_who = sorted(k for k, v in _start_prose().items() if "{who}" not in v)

        assert without_who == [], without_who


class TestEveryEndReasonHasItsOwnProse:
    """会議の終わり方すべてに専用の文がある。"""

    def test_no_end_reason_is_missing(self) -> None:
        """`MeetingEndReason` 全件が表にある。"""
        missing = sorted(
            r.name for r in MeetingEndReason if r.value not in _end_prose()
        )

        assert missing == [], missing

    def test_no_end_entry_is_stale(self) -> None:
        """表に、enum から消えた理由のキーが残っていない。"""
        known = {r.value for r in MeetingEndReason}
        stale = sorted(k for k in _end_prose() if k not in known)

        assert stale == [], stale


class TestTheProseIsDistinguishable:
    """理由ごとに違う文が出る。"""

    def test_start_prose_are_all_different(self) -> None:
        """始まりの文が理由ごとに違う。

        同じ文なら言い分けた意味が無い。
        """
        texts = list(_start_prose().values())

        assert len(set(texts)) == len(texts), texts

    def test_end_prose_are_all_different(self) -> None:
        """終わりの文が理由ごとに違う。"""
        texts = list(_end_prose().values())

        assert len(set(texts)) == len(texts), texts

    def test_no_prose_leaks_an_internal_identifier(self) -> None:
        """文に内部識別子 (英字の並び) が出ない。

        #1043 で閉じた「ID をプロンプトに出さない」方針の裏口を作らない。
        `{who}` は差し込み口なので除く。
        """
        import re

        leaked = {
            key: text
            for table in (_start_prose(), _end_prose())
            for key, text in table.items()
            if re.search(r"[A-Za-z_]{4,}", text.replace("{who}", ""))
        }

        assert leaked == {}, leaked


class TestTheVocabularyIsDeclaredOnce:
    """理由の語彙が 1 か所で宣言されている。"""

    def test_the_producers_use_the_enum_values(self) -> None:
        """生産側が enum の値を使っている。

        `world_runtime` / `game_phase_store` が生の文字列リテラルを書くと、語彙が
        2 か所に分かれて網羅テストが意味を失う (表には無いが実際に飛ぶ理由が
        生まれる)。**ソースを読んで、生リテラルが残っていないことを見る。**
        """
        from pathlib import Path

        root = Path(__file__).resolve().parents[3] / "src" / "ai_rpg_world"
        producers = (
            root / "application" / "world_runtime" / "world_runtime.py",
            root / "application" / "world_graph" / "game_phase_store.py",
        )
        vocabulary = {t.value for t in MeetingStartTrigger} | {
            r.value for r in MeetingEndReason
        }
        offenders = []
        for path in producers:
            text = path.read_text(encoding="utf-8")
            for word in vocabulary:
                if f'"{word}"' in text:
                    offenders.append(f"{path.name}: \"{word}\"")

        assert offenders == [], (
            "生産側に理由の生リテラルが残っています。enum の .value を使ってください: "
            f"{offenders}"
        )

    def test_the_two_vocabularies_do_not_overlap(self) -> None:
        """始まりの理由と終わりの理由が重なっていない。

        重なると、どちらの表を引くべきかが理由だけでは決まらない。
        """
        start = {t.value for t in MeetingStartTrigger}
        end = {r.value for r in MeetingEndReason}

        assert start & end == set(), start & end


class TestAnUnknownReasonIsVisible:
    """未知の理由が来たとき、静かに倒れずに見える。"""

    def test_the_fallback_is_logged(self, caplog) -> None:
        """表に無い理由は warning を出してから汎用文へ倒れる。

        `.get(reason, fallback)` のままだと**何も残らない**ので、理由を足して表に
        書き忘れたことが誰にも見えない。網羅テストが実行時に未知が来ないことを
        保証しているが、**保証が破れたときに気づける口**を残しておく。

        変異で確認した: warning を消すと観測系 882 件が全部通った (= 未知値が来る
        経路をどのテストも通っていなかった)。
        """
        with caplog.at_level(logging.WARNING):
            text = SpotGraphObjectHandler._meeting_prose(
                _end_prose(), "no_such_reason", fallback="汎用文"
            )

        assert text == "汎用文"
        assert any("no_such_reason" in r.getMessage() for r in caplog.records), [
            r.getMessage() for r in caplog.records
        ]

    def test_a_known_reason_is_not_logged(self, caplog) -> None:
        """既知の理由では warning を出さない (正の対照)。

        常に warning を出す実装でも上の試験は通ってしまう。
        """
        with caplog.at_level(logging.WARNING):
            text = SpotGraphObjectHandler._meeting_prose(
                _end_prose(), MeetingEndReason.SILENCE.value, fallback="汎用文"
            )

        assert text != "汎用文"
        assert [r.getMessage() for r in caplog.records] == []
