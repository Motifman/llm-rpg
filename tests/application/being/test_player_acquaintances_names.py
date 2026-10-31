"""PlayerAcquaintances が、名前を知らない相手を見た目で呼び、名乗りや呼びかけを聞いて名前を知ることを保証する (#1581)。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    SubjectUnknownView,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
    InMemoryAcquaintanceRepository,
)
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (
    InMemoryMemoryTurnClock,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

ADA = PlayerId(1)
NOA = PlayerId(2)
RIO = PlayerId(3)
NAMES = {1: "エイダ", 2: "ノア", 3: "リオ"}
LOOKS = {1: "外套の女", 2: "背の高い男", 3: "赤い頭巾の人"}


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, **payload: Any) -> None:
        self.events.append((kind, payload))


def _make(
    *, together: set[frozenset[int]] | None = None, appearances: dict[int, str] | None = None
) -> tuple[PlayerAcquaintances, _Recorder]:
    recorder = _Recorder()
    pairs = together if together is not None else set()
    acquaintances = PlayerAcquaintances(
        store=InMemoryAcquaintanceRepository(),
        being_id_of=lambda pid: BeingId(f"being_p{pid.value}") if pid.value in NAMES else None,
        turn_reader=InMemoryMemoryTurnClock(),
        environment_name="山村",
        names_by_player_id=NAMES,
        appearances_by_player_id=LOOKS if appearances is None else appearances,
        co_present=lambda a, b: frozenset({a.value, b.value}) in pairs,
        trace_recorder_provider=lambda: recorder,
    )
    return acquaintances, recorder


def _entered(actor: str) -> ObservationOutput:
    return ObservationOutput(
        prose=f"{actor}が「坑口」からやってきた。",
        structured={"type": "entity_entered_spot", "actor": actor, "spot_name": "広間"},
        observation_category="social",
    )


def _spoke(speaker: PlayerId, content: str, *, channel: str = "say") -> ObservationOutput:
    name = NAMES[speaker.value]
    structured = {
        "type": "player_spoke",
        "speaker": name,
        "speaker_player_id": speaker.value,
        "channel": channel,
        "content": content,
        "role": "other",
    }
    return ObservationOutput(
        prose=f"{name}が言った: 「{content}」",
        structured=structured,
        observation_category="social",
        subject_name=name,
        if_subject_unknown=SubjectUnknownView(
            prose=f"誰かが言った: 「{content}」",
            structured={k: v for k, v in structured.items() if k not in ("speaker", "speaker_player_id")},
        ),
    )


def _hear(acquaintances: PlayerAcquaintances, recipient: PlayerId, output: ObservationOutput) -> ObservationOutput:
    """受け手の記録に入れる版を選び、そのあと観測者として知らせる (ObservationAppender と同じ順)。"""
    chosen = acquaintances.view_for(recipient, output)
    assert chosen is not None
    acquaintances.on_observation(recipient, chosen)
    return chosen


class TestMeetingWithoutTheName:
    """会うことと名前を知ることを分けて記録することを保証する。"""

    def test_meeting_someone_with_an_appearance_does_not_teach_the_name(self) -> None:
        """見た目の説明がある相手と会うと、会った記録は残るが名前は知らない。"""
        acquaintances, _ = _make()

        acquaintances.record_meeting(ADA, "ノア")

        met = acquaintances.find(ADA, "ノア")
        assert met is not None and not met.knows_name

    def test_meeting_someone_without_an_appearance_teaches_the_name(self) -> None:
        """見た目の説明が無い相手 (全員に紹介されている人) と会うと、これまでどおり名前を知る。"""
        acquaintances, _ = _make(appearances={})

        acquaintances.record_meeting(ADA, "ノア")

        met = acquaintances.find(ADA, "ノア")
        assert met is not None and met.knows_name

    def test_arrival_seen_by_its_appearance_records_both_sides(self) -> None:
        """入ってきた人が見た目で書かれた観測でも、受け手と入ってきた人の双方に、名前を知らない会った記録が残る。"""
        acquaintances, _ = _make()

        acquaintances.on_observation(ADA, _entered("背の高い男"))

        assert not acquaintances.find(ADA, "ノア").knows_name  # type: ignore[union-attr]
        assert not acquaintances.find(NOA, "エイダ").knows_name  # type: ignore[union-attr]


class TestCallName:
    """受け手が相手をどう呼ぶか (名前か見た目か) を決めることを保証する。"""

    def test_stranger_is_called_by_appearance(self) -> None:
        """会っていない相手も、会ったが名前を知らない相手も、見た目で呼ぶ。"""
        acquaintances, _ = _make()
        before = acquaintances.call_name(ADA, NOA)
        acquaintances.record_meeting(ADA, "ノア")

        assert (before, acquaintances.call_name(ADA, NOA)) == ("背の高い男", "背の高い男")

    def test_named_acquaintance_and_oneself_are_called_by_name(self) -> None:
        """名前を知った相手と自分自身は、名前で呼ぶ。"""
        acquaintances, _ = _make()
        acquaintances.record_meeting(ADA, "ノア")
        acquaintances.learn_name(ADA, NOA, how="名乗り")

        assert (acquaintances.call_name(ADA, NOA), acquaintances.call_name(ADA, ADA)) == ("ノア", "エイダ")

    def test_lookup_failure_falls_back_to_appearance(self) -> None:
        """知り合いの記録を引けないときは、名前ではなく見た目で呼ぶ。名前は記録に入ったら消せない。"""
        acquaintances, _ = _make()
        acquaintances._store.find = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]

        assert acquaintances.call_name(ADA, NOA) == "背の高い男"


class TestRenamingObservations:
    """受け手の記録に入る観測で、名前を知らない参加者の名前を見た目に置き換えることを保証する。"""

    def test_arrival_of_a_stranger_is_written_with_the_appearance(self) -> None:
        """名前を知らない人の到着は、本文も structured の actor も見た目になる。"""
        acquaintances, _ = _make()

        chosen = acquaintances.view_for(ADA, _entered("ノア"))

        assert chosen is not None
        assert chosen.prose == "背の高い男が「坑口」からやってきた。"
        assert chosen.structured["actor"] == "背の高い男"

    def test_names_in_spoken_words_are_heard_as_they_are(self) -> None:
        """会ったが名前を知らない話し手は見た目で書かれ、言葉の中の名前は変えない。"""
        acquaintances, _ = _make()
        acquaintances.record_meeting(ADA, "ノア")

        chosen = acquaintances.view_for(ADA, _spoke(NOA, "リオとノアを探している"))

        assert chosen is not None
        assert chosen.prose == "背の高い男が言った: 「リオとノアを探している」"
        assert chosen.structured["speaker"] == "背の高い男"
        assert chosen.structured["content"] == "リオとノアを探している"

    def test_every_participant_named_in_structured_is_renamed(self) -> None:
        """受け渡しのように 2 人が出る観測では、structured に出る参加者を 2 人とも置き換える。知っている人は名前のまま。"""
        acquaintances, _ = _make()
        acquaintances.record_meeting(ADA, "リオ")
        acquaintances.learn_name(ADA, RIO, how="名乗り")
        output = ObservationOutput(
            prose="ノアがランプをリオに渡した。",
            structured={"type": "item_given", "actor": "ノア", "receiver": "リオ"},
            observation_category="social",
        )

        chosen = acquaintances.view_for(ADA, output)

        assert chosen is not None
        assert chosen.prose == "背の高い男がランプをリオに渡した。"
        assert chosen.structured == {"type": "item_given", "actor": "背の高い男", "receiver": "リオ"}

    def test_names_that_are_dict_keys_are_renamed(self) -> None:
        """投票の内訳のように名前が structured の鍵に出ても、置き換える。"""
        acquaintances, _ = _make()
        output = ObservationOutput(
            prose="投票が終わった。ノア 2 票。",
            structured={"type": "meeting_vote_resolved", "ballots": {"ノア": 2}},
            observation_category="social",
        )

        chosen = acquaintances.view_for(ADA, output)

        assert chosen is not None
        assert chosen.prose == "投票が終わった。背の高い男 2 票。"
        assert chosen.structured["ballots"] == {"背の高い男": 2}

    def test_names_inside_written_text_are_left_alone(self) -> None:
        """『』で囲んだ書かれた文と、「」の中の『』に出る名前は変えず、外の名前だけを置き換える。"""
        acquaintances, _ = _make()
        output = ObservationOutput(
            prose="ノアが看板を読んだ: 『ノアここに眠る』。ノアが言った: 「『ノア』と書いてある」",
            structured={"type": "x", "actor": "ノア"},
            observation_category="social",
        )

        chosen = acquaintances.view_for(ADA, output)

        assert chosen is not None
        assert (
            chosen.prose == "背の高い男が看板を読んだ: 『ノアここに眠る』。背の高い男が言った: 「『ノア』と書いてある」"
        )

    def test_name_absent_from_structured_is_left_alone(self) -> None:
        """structured に参加者として出ていない名前は、文の中で探して置き換えない。参加者は構造で分かる人に限る。"""
        acquaintances, _ = _make()
        output = ObservationOutput(
            prose="看板に「ノア参上」と刻まれている。",
            structured={"type": "sign_read"},
            observation_category="environment",
        )

        assert acquaintances.view_for(ADA, output) == output


class TestLearningNames:
    """名乗りを聞く、同じ場所にいる人が名前で呼ばれるのを聞く、のどちらかで名前を知ることを保証する。"""

    def test_hearing_a_self_introduction_teaches_the_name_from_the_next_observation(self) -> None:
        """会ったが名前を知らない話し手が自分の名前を口にすると、その声は見た目のまま記録され、次の観測から名前で書かれる。"""
        acquaintances, _ = _make()
        acquaintances.record_meeting(ADA, "ノア")

        first = _hear(acquaintances, ADA, _spoke(NOA, "俺はノアだ"))
        second = acquaintances.view_for(ADA, _entered("ノア"))

        assert first.prose.startswith("背の高い男が言った")
        assert second is not None and second.prose.startswith("ノアが")
        assert acquaintances.find(ADA, "ノア").knows_name  # type: ignore[union-attr]

    def test_unrecognised_voice_does_not_teach_the_speakers_name(self) -> None:
        """会っていない話し手の声は「誰か」の声として届き、名乗っても名前を知ったことにしない。"""
        acquaintances, recorder = _make()

        _hear(acquaintances, ADA, _spoke(NOA, "俺はノアだ"))

        assert acquaintances.find(ADA, "ノア") is None
        assert recorder.events == []

    def test_hearing_someone_present_called_by_name_teaches_it(self) -> None:
        """同じ場所にいる会った相手が、別の人に名前で呼ばれるのを聞くと、その相手の名前を知り、trace に「呼びかけ」で残る。"""
        acquaintances, recorder = _make(together={frozenset({1, 2})})
        acquaintances.record_meeting(ADA, "ノア")
        acquaintances.record_meeting(ADA, "リオ")

        _hear(acquaintances, ADA, _spoke(RIO, "ノア、こっちだ"))

        assert acquaintances.find(ADA, "ノア").knows_name  # type: ignore[union-attr]
        assert not acquaintances.find(ADA, "リオ").knows_name  # type: ignore[union-attr]
        assert [(e[1]["learned_name"], e[1]["how"]) for e in recorder.events] == [("ノア", "呼びかけ")]

    def test_name_of_someone_elsewhere_is_not_learned(self) -> None:
        """呼ばれた人が同じ場所にいなければ、会ったことがあっても名前を知ったことにしない。"""
        acquaintances, recorder = _make(together=set())
        acquaintances.record_meeting(ADA, "ノア")

        _hear(acquaintances, ADA, _spoke(RIO, "ノア、こっちだ"))

        assert not acquaintances.find(ADA, "ノア").knows_name  # type: ignore[union-attr]
        assert recorder.events == []

    def test_name_of_someone_never_met_is_not_learned(self) -> None:
        """同じ場所にいても会ったことの無い相手の名前は、聞いても知ったことにしない。"""
        acquaintances, recorder = _make(together={frozenset({1, 2})})

        _hear(acquaintances, ADA, _spoke(RIO, "ノア、こっちだ"))

        assert acquaintances.find(ADA, "ノア") is None
        assert recorder.events == []

    def test_whisper_does_not_teach_the_name_of_a_bystander(self) -> None:
        """囁きの中の名前は、呼ばれた人に聞こえない声なので、その人の名前を知ったことにしない。"""
        acquaintances, recorder = _make(together={frozenset({1, 2})})
        acquaintances.record_meeting(ADA, "ノア")

        _hear(acquaintances, ADA, _spoke(RIO, "あれはノアだ", channel="whisper"))

        assert not acquaintances.find(ADA, "ノア").knows_name  # type: ignore[union-attr]
        assert recorder.events == []

    def test_learning_a_name_is_traced_once(self) -> None:
        """名前を知ると、誰が誰の名前をどう知ったかを trace に 1 件残す。もう一度聞いても増えない。"""
        acquaintances, recorder = _make()
        acquaintances.record_meeting(ADA, "ノア")

        _hear(acquaintances, ADA, _spoke(NOA, "ノアだ"))
        _hear(acquaintances, ADA, _spoke(NOA, "ノアだってば"))

        assert recorder.events == [
            (
                TraceEventKind.NAME_LEARNED,
                {"tick": None, "player_id": 1, "learned_name": "ノア", "appearance": "背の高い男", "how": "名乗り"},
            )
        ]


class TestFallingBackToAppearance:
    """置き換えや記録の途中で失敗しても、名前を出す側へ倒れないことを保証する。"""

    def test_failure_while_renaming_writes_every_participant_by_appearance(self) -> None:
        """呼び方を決める途中で例外が出ると、受け手の知り方を問わず、structured に出る参加者を全員見た目で書く。"""
        acquaintances, _ = _make()
        acquaintances.call_name = lambda viewer, other: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]

        chosen = acquaintances.view_for(ADA, _entered("ノア"))

        assert chosen is not None
        assert chosen.prose == "背の高い男が「坑口」からやってきた。"

    def test_learning_a_name_is_traced_with_the_tick(self) -> None:
        """名前を知った trace には、そのときの世界の tick を付ける。同じ tick の発言と突き合わせるため。"""
        recorder = _Recorder()
        acquaintances = PlayerAcquaintances(
            store=InMemoryAcquaintanceRepository(),
            being_id_of=lambda pid: BeingId(f"being_p{pid.value}"),
            turn_reader=InMemoryMemoryTurnClock(),
            environment_name="山村",
            names_by_player_id=NAMES,
            appearances_by_player_id=LOOKS,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 17,
        )
        acquaintances.record_meeting(ADA, "ノア")

        acquaintances.learn_name(ADA, NOA, how="名乗り")

        assert recorder.events[0][1]["tick"] == 17

    def test_trace_provider_failure_keeps_the_learned_name(self) -> None:
        """trace の取り出しで例外が出ても、名前を知った記録は残り、例外は外へ出ない。"""
        acquaintances, _ = _make()
        acquaintances._trace_recorder_provider = lambda: (_ for _ in ()).throw(AttributeError("no runtime"))
        acquaintances.record_meeting(ADA, "ノア")

        acquaintances.learn_name(ADA, NOA, how="名乗り")

        assert acquaintances.find(ADA, "ノア").knows_name  # type: ignore[union-attr]

    def test_unclosed_quote_does_not_shield_the_rest(self) -> None:
        """閉じない「があると、そこから後ろも置き換える。言葉とみなして残すと名前が漏れる。"""
        acquaintances, _ = _make()
        output = ObservationOutput(
            prose="ノアが言った: 「待て。ノアが来る",
            structured={"type": "x", "actor": "ノア"},
            observation_category="social",
        )

        chosen = acquaintances.view_for(ADA, output)

        assert chosen is not None and "ノア" not in chosen.prose
