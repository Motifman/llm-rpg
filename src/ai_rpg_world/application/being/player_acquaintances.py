"""ゲームのプレイヤーと、その Being の知り合いの記録をつなぐ。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.being.application.known_people import render_known_people
from ai_rpg_world.being.contract import EnvironmentEntry
from ai_rpg_world.being.domain.acquaintance import Acquaintance, AcquaintanceRepository
from ai_rpg_world.being.domain.memory_turn_clock import (
    MemoryTurnReader,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput

_logger = logging.getLogger(__name__)

_TYPE_ENTITY_ENTERED_SPOT = "entity_entered_spot"
_TYPE_PLAYER_SPOKE = "player_spoke"
_CHANNEL_WHISPER = "whisper"
# 聞いた言葉。名前を置き換えると、聞こえた言葉が変わる。
_SPOKEN_KEYS = frozenset({"content"})
_QUOTES = {"「": "」", "『": "』"}
_HOW_SELF_INTRODUCTION = "名乗り"
_HOW_CALLED_BY_NAME = "呼びかけ"


class PlayerAcquaintances:
    """記録は Being の持ち物で、鍵に環境の名前と相手の名前の文だけを使う。

    プレイヤー番号から Being を引くのと、名前からプレイヤー番号を引くのは、
    ゲームの側にあるこの部品だけが行う。
    """

    def __init__(
        self,
        *,
        store: AcquaintanceRepository,
        being_id_of: Callable[[PlayerId], BeingId | None],
        turn_reader: MemoryTurnReader,
        environment_name: str,
        names_by_player_id: Mapping[int, str],
        appearances_by_player_id: Mapping[int, str] | None = None,
        co_present: Callable[[PlayerId, PlayerId], bool] | None = None,
        trace_recorder_provider: Callable[[], Any] | None = None,
        current_tick_provider: Callable[[], int] | None = None,
    ) -> None:
        if not environment_name.strip():
            raise ValueError("environment_name must be non-blank")
        names = list(names_by_player_id.values())
        duplicated = sorted({n for n in names if names.count(n) > 1})
        if duplicated:
            raise ValueError(f"participants share a name, so a name cannot tell who met whom: {duplicated}")
        self._store = store
        self._being_id_of = being_id_of
        self._turn_reader = turn_reader
        self._environment_name = environment_name
        self._names_by_player_id = dict(names_by_player_id)
        self._player_id_by_name = {name: pid for pid, name in self._names_by_player_id.items()}
        self._unresolved_warned: set[int] = set()
        self._appearances = dict(appearances_by_player_id or {})
        self._co_present = co_present
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def record_meeting(self, player_id: PlayerId, name: str) -> None:
        if name == self._names_by_player_id.get(player_id.value):
            return
        being_id = self._resolve(player_id)
        if being_id is None:
            return
        other_id = self._player_id_by_name.get(name)
        self._store.record_meeting(
            being_id,
            environment_name=self._environment_name,
            name=name,
            turn=self._turn_reader.current_turn(being_id),
            # 見た目の説明が無い人は、全員が最初から名前を知っている (読み込み時に確かめている)。
            knows_name=other_id is None or other_id not in self._appearances,
        )

    def receive_entry(self, player_id: PlayerId, entry: EnvironmentEntry) -> None:
        """紹介はプロンプトの前提なので、渡せないときは黙って捨てずに止める。"""
        if entry.environment_name != self._environment_name:
            raise ValueError(
                f"entry is for {entry.environment_name!r}, but acquaintances are kept for {self._environment_name!r}"
            )
        being_id = self._resolve(player_id)
        if being_id is None:
            if entry.introductions:
                raise ValueError(f"player_id={player_id.value} has no Being to receive introductions")
            return
        turn = self._turn_reader.current_turn(being_id)
        for introduction in entry.introductions:
            self._store.record_introduction(
                being_id,
                environment_name=self._environment_name,
                name=introduction.name,
                turn=turn,
                relation_note=introduction.relation_note,
            )

    def known_people_text(self, player_id: PlayerId) -> str:
        being_id = self._resolve(player_id)
        if being_id is None:
            return ""
        return render_known_people(
            self._store.list_by_being(being_id),
            environment_name=self._environment_name,
        )

    def find(self, player_id: PlayerId, name: str) -> Acquaintance | None:
        being_id = self._resolve(player_id)
        if being_id is None:
            return None
        return self._store.find(being_id, environment_name=self._environment_name, name=name)

    def find_player(self, viewer: PlayerId, other: PlayerId) -> Acquaintance | None:
        name = self._names_by_player_id.get(other.value)
        return None if name is None else self.find(viewer, name)

    def knows(self, recipient: PlayerId, other: PlayerId) -> bool:
        """引けないときは知らない側へ倒す。知っていると答えると、相手の存在が届く。"""
        if other.value == recipient.value:
            return True
        name = self._names_by_player_id.get(other.value)
        if name is None:
            return False
        try:
            return self.find(recipient, name) is not None
        except Exception:
            _logger.exception(
                "知り合いの記録を引けず、知らない相手として扱う (recipient=%s)",
                recipient.value,
            )
            return False

    def view_for(self, recipient: PlayerId, output: ObservationOutput) -> ObservationOutput | None:
        """受け手の記録に入れる版を選ぶ。None は記録しない。記録したあとで相手を知っても、記録は書き換えない。

        選んだ版の中の、名前を知らない参加者の名前は見た目に置き換える。
        """
        chosen = self._choose_version(recipient, output)
        return None if chosen is None else self._renamed_for(recipient, chosen)

    def _choose_version(self, recipient: PlayerId, output: ObservationOutput) -> ObservationOutput | None:
        view = output.if_subject_unknown
        if output.subject_name is None or view is None:
            return output
        if output.subject_name == self._names_by_player_id.get(recipient.value):
            return output.as_subject_known()
        try:
            known = self.find(recipient, output.subject_name) is not None
        except Exception:
            # 引けないときは伏せる側へ倒す。名前は、あとで記録から消せない。
            _logger.exception(
                "知り合いの記録を引けず、話し手の名前を伏せて記録する (recipient=%s)",
                recipient.value,
            )
            known = False
        return output.as_subject_known() if known else output.as_subject_unknown()

    def on_observation(self, recipient: PlayerId, output: ObservationOutput) -> None:
        """入ってきた人とその場にいた受け手は、互いの姿を見ている。

        入ってきた本人には自分の到着の観測が届かないので、受け手への観測から
        両方の記録を残す。名前の伏せられた観測では、どちらも相手を見ていない。
        参加者に無い名前 (モンスター、名前を引けなかったときの代わりの名前) は
        人として記録しない。
        """
        structured = output.structured or {}
        if structured.get("type") == _TYPE_PLAYER_SPOKE:
            self._learn_names_from_speech(recipient, structured)
            return
        if structured.get("type") != _TYPE_ENTITY_ENTERED_SPOT:
            return
        actor = structured.get("actor")
        if not isinstance(actor, str):
            return
        actor = actor.strip()
        # 名前を知らない受け手には、入ってきた人が見た目で書かれて届く。
        actor_id = self._player_id_by_name.get(actor, self._player_id_by_appearance().get(actor))
        recipient_name = self._names_by_player_id.get(recipient.value)
        if actor_id is None or recipient_name is None:
            return
        self._record_safely(recipient, self._names_by_player_id[actor_id])
        self._record_safely(PlayerId(actor_id), recipient_name)

    def call_name(self, viewer: PlayerId, other: PlayerId) -> str:
        """受け手が相手を呼ぶ言葉。名前を知っていれば名前、知らなければ見た目。

        引けないときは見た目へ倒す。名前は記録に入ったら消せない。
        """
        name = self._names_by_player_id.get(other.value)
        appearance = self._appearances.get(other.value)
        if name is None:
            return appearance or ""
        if appearance is None or other.value == viewer.value:
            return name
        try:
            known = self.find(viewer, name)
        except Exception:
            _logger.exception("知り合いの記録を引けず、相手を見た目で呼ぶ (viewer=%s)", viewer.value)
            return appearance
        return name if known is not None and known.knows_name else appearance

    def learn_name(self, recipient: PlayerId, other: PlayerId, *, how: str) -> None:
        """会ったことの無い相手の名前は、聞いても知ったことにしない。"""
        name = self._names_by_player_id.get(other.value)
        being_id = self._resolve(recipient)
        if name is None or being_id is None or other.value == recipient.value:
            return
        before = self._store.find(being_id, environment_name=self._environment_name, name=name)
        if before is None or before.knows_name:
            return
        self._store.record_name_learned(
            being_id,
            environment_name=self._environment_name,
            name=name,
            turn=self._turn_reader.current_turn(being_id),
        )
        self._trace_name_learned(recipient, name, how)

    def _learn_names_from_speech(self, recipient: PlayerId, structured: Mapping[str, Any]) -> None:
        """名乗りは、話し手が分かる声 (伏せた版でない) でだけ聞き取れる。

        呼びかけは、呼ばれた人が受け手と同じ場所にいて、その声を聞き取れるときだけ
        数える。同じ場所に名前を知らない人が何人いても、エンジンは呼ばれた人を
        知っているので取り違えない。人なら文脈で見分ける、という単純化。
        """
        content = structured.get("content")
        if not isinstance(content, str) or not content:
            return
        speaker_value = structured.get("speaker_player_id")
        speaker = speaker_value if isinstance(speaker_value, int) else None
        for pid_value, name in self._names_by_player_id.items():
            if name not in content or pid_value == recipient.value:
                continue
            other = PlayerId(pid_value)
            if pid_value == speaker:
                how = _HOW_SELF_INTRODUCTION
            elif structured.get("channel") != _CHANNEL_WHISPER and self._is_co_present(recipient, other):
                how = _HOW_CALLED_BY_NAME
            else:
                continue
            try:
                self.learn_name(recipient, other, how=how)
            except Exception:
                _logger.exception(
                    "名前を知った記録を残せなかった (recipient=%s, name=%s)",
                    recipient.value,
                    name,
                )

    def _is_co_present(self, a: PlayerId, b: PlayerId) -> bool:
        if self._co_present is None:
            return False
        try:
            return bool(self._co_present(a, b))
        except Exception:
            _logger.exception("同じ場所にいるかを確かめられなかった")
            return False

    def _trace_name_learned(self, recipient: PlayerId, name: str, how: str) -> None:
        """名前を知った記録はもう残っているので、trace の失敗は外へ出さない。"""
        try:
            recorder = self._trace_recorder_provider() if self._trace_recorder_provider else None
            if recorder is None:
                return
            recorder.record(
                TraceEventKind.NAME_LEARNED,
                tick=self._current_tick_provider() if self._current_tick_provider else None,
                player_id=int(recipient.value),
                learned_name=name,
                appearance=self._appearance_of_name(name),
                how=how,
            )
        except Exception:
            _logger.exception("名前を知った trace を残せなかった")

    def _appearance_of_name(self, name: str) -> str:
        pid = self._player_id_by_name.get(name)
        return self._appearances.get(pid, name) if pid is not None else name

    def _player_id_by_appearance(self) -> dict[str, int]:
        return {look: pid for pid, look in self._appearances.items()}

    def _renamed_for(self, recipient: PlayerId, output: ObservationOutput) -> ObservationOutput:
        """置き換えるのは、structured に参加者として出ている人の名前だけ。

        文の中から全員の名前を探すと、名前を含む別の語まで巻き込む。structured に
        出ていない名前は置き換えないので、新しい観測は参加者を structured に書く。
        """
        mentioned = _names_in_structured(output.structured, frozenset(self._player_id_by_name))
        try:
            renames = {name: self.call_name(recipient, PlayerId(self._player_id_by_name[name])) for name in mentioned}
        except Exception:
            # 引けないときは見た目へ倒す。名前は記録に入ったら消せない。
            _logger.exception(
                "呼び方を決められず、参加者を全員見た目で書く (recipient=%s)",
                recipient.value,
            )
            own = self._names_by_player_id.get(recipient.value)
            renames = {name: self._appearance_of_name(name) for name in mentioned if name != own}
        renames = {name: call for name, call in renames.items() if call != name}
        if not renames:
            return output
        return replace(
            output,
            prose=_rename_outside_quotes(output.prose, renames),
            structured=_rename_structured(output.structured, renames),
        )

    def _record_safely(self, player_id: PlayerId, name: str) -> None:
        try:
            self.record_meeting(player_id, name)
        except Exception:
            _logger.exception(
                "会った記録を残せなかった (player_id=%s, name=%s)",
                player_id.value,
                name,
            )

    def _resolve(self, player_id: PlayerId) -> BeingId | None:
        being_id = self._being_id_of(player_id)
        if being_id is None and player_id.value not in self._unresolved_warned:
            self._unresolved_warned.add(player_id.value)
            _logger.warning(
                "player_id=%s に結び付く Being が無く、会った記録を読み書きしない "
                "(この player については以後再警告しない)",
                player_id.value,
            )
        return being_id


def _names_in_structured(node: Any, names: frozenset[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in names:
                found.add(key)
            if key not in _SPOKEN_KEYS:
                found |= _names_in_structured(value, names)
    elif isinstance(node, (list, tuple)):
        for value in node:
            found |= _names_in_structured(value, names)
    elif isinstance(node, str) and node.strip() in names:
        found.add(node.strip())
    return found


def _rename_structured(node: Any, renames: Mapping[str, str]) -> Any:
    if isinstance(node, Mapping):
        return {
            _rename_outside_quotes(k, renames) if isinstance(k, str) else k: (
                v if k in _SPOKEN_KEYS else _rename_structured(v, renames)
            )
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_rename_structured(v, renames) for v in node]
    if isinstance(node, tuple):
        return tuple(_rename_structured(v, renames) for v in node)
    if isinstance(node, str):
        return _rename_outside_quotes(node, renames)
    return node


def _rename_outside_quotes(text: str, renames: Mapping[str, str]) -> str:
    """「」と『』の中は、聞いた言葉や書かれた文なので変えない。

    閉じない括弧があれば、そこから後ろも置き換える。後ろの文を言葉とみなして
    残すと、名前が漏れる側へ倒れる。
    """
    out: list[str] = []
    plain: list[str] = []
    closers: list[str] = []
    opened_at = 0

    def renamed(chunk: str) -> str:
        for name in sorted(renames, key=len, reverse=True):
            chunk = chunk.replace(name, renames[name])
        return chunk

    def flush() -> None:
        out.append(renamed("".join(plain)))
        plain.clear()

    for ch in text:
        if not closers and ch in _QUOTES:
            flush()
            opened_at = len(out)
            closers.append(_QUOTES[ch])
            out.append(ch)
        elif closers:
            if ch in _QUOTES:
                closers.append(_QUOTES[ch])
            elif ch == closers[-1]:
                closers.pop()
            out.append(ch)
        else:
            plain.append(ch)
    if closers:
        out[opened_at:] = [renamed("".join(out[opened_at:]))]
    flush()
    return "".join(out)


__all__ = ["PlayerAcquaintances"]
