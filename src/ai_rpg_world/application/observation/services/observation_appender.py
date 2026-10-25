"""バッファへの観測追加と game_time_label 付与を行うサービス"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
    SubjectUnknownView,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

# PR3 (Encounter Memory) 後付け hook の signature。
# ``ObservationAppender`` から ``encounter`` を直接 import すると application 層
# 内に観測 → 出来事認識という別軸の依存が生まれる。observer-style の Callable
# slot を介すことで、ObservationAppender は「observation を 1 件届けたことを
# 副次的に観測者に知らせる」という最小責務だけを引き受ける形にできる。
# PR3 では encounter collector がこの slot に入るが、将来別目的の observer
# (例えば metrics, debug visualization) も同じ slot に挿せる。
ObservationObserver = Callable[[PlayerId, ObservationOutput], None]
# #1520: 受け手の記録に入れる版を選ぶ口。話し手を知っているかは受け手の Being が
# 決めるので、ObservationAppender は中身を知らずに呼ぶだけにする。
# None を返したら、その受け手には届けない。
RecipientView = Callable[[PlayerId, ObservationOutput], ObservationOutput | None]


class ObservationAppender:
    """
    観測エントリを構築し、バッファに append する。
    occurred_at と game_time_label を付与した ObservationEntry を作成して buffer に渡す。

    Issue #276: trace_recorder が注入されていれば、buffer に積んだ観測を
    ``TraceEventKind.OBSERVATION`` として trace にも残す (LLM の prompt に
    届いた観測を後から追跡できるよう、buffer append と同じ場所で記録する)。

    PR3 (Encounter Memory): ``observers`` に Callable を渡すと、buffer append の
    後に順次呼ばれる。``ObservationAppender`` は observer の中身を知らない
    (= encounter / metrics / debug 等、任意の観察者に開かれている)。空 list /
    省略時は完全に既存挙動と一致する (= 後方互換)。
    """

    def __init__(
        self,
        buffer: IObservationContextBuffer,
        runtime_context_provider: Callable[[PlayerId], ToolRuntimeContextDto | None] | None = None,
        *,
        trace_recorder: ITraceRecorder | None = None,
        trace_recorder_provider: Callable[[], ITraceRecorder | None] | None = None,
        current_tick_provider: Callable[[], int | None] | None = None,
        observers: list[ObservationObserver] | None = None,
        recipient_view: RecipientView | None = None,
    ) -> None:
        self._buffer = buffer
        self._runtime_context_provider = runtime_context_provider
        if runtime_context_provider is not None and not callable(runtime_context_provider):
            raise TypeError("runtime_context_provider must be callable or None")
        if trace_recorder is not None and not isinstance(trace_recorder, ITraceRecorder):
            raise TypeError("trace_recorder must be ITraceRecorder or None")
        if trace_recorder_provider is not None and not callable(trace_recorder_provider):
            raise TypeError("trace_recorder_provider must be callable or None")
        if current_tick_provider is not None and not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable or None")
        if observers is not None:
            for i, obs in enumerate(observers):
                if not callable(obs):
                    raise TypeError(f"observers[{i}] must be callable (got {type(obs)!r})")
        self._trace_recorder = trace_recorder
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider
        self._observers: tuple[ObservationObserver, ...] = tuple(observers) if observers else ()
        if recipient_view is not None and not callable(recipient_view):
            raise TypeError("recipient_view must be callable or None")
        self._recipient_view = recipient_view
        self._warned_without_view = False

    def append(
        self,
        player_id: PlayerId,
        output: ObservationOutput,
        occurred_at: datetime,
        game_time_label: str | None = None,
    ) -> bool:
        """
        指定プレイヤーに観測エントリを追加する。記録しなかったときは False を返す。
        ObservationEntry を構築して buffer.append に委譲し、合わせて trace
        に observation event を記録する (recorder 注入時)。

        ``recipient_view`` があれば、先に受け手の記録に入れる版を選び、バッファ・
        trace・observer のすべてにその版を渡す。
        """
        if not isinstance(output, ObservationOutput):
            raise TypeError("output must be ObservationOutput")
        chosen = self._choose_view(player_id, output)
        if chosen is None:
            self._record_trace(
                player_id,
                output.as_subject_known(),
                game_time_label,
                withheld_subject_name=output.subject_name,
            )
            return False
        view = output.if_subject_unknown
        hidden = (
            isinstance(view, SubjectUnknownView) and chosen.prose == view.prose and chosen.structured == view.structured
        )
        hidden_subject_name = output.subject_name if hidden else None
        output = chosen
        entry = ObservationEntry(
            occurred_at=occurred_at,
            output=output,
            game_time_label=game_time_label,
        )
        rtc = self._runtime_context_provider(player_id) if self._runtime_context_provider is not None else None
        self._buffer.append(player_id, entry, runtime_context=rtc)
        self._record_trace(player_id, output, game_time_label, hidden_subject_name=hidden_subject_name)
        # PR3: 各 observer に通知する。observer は副次的な観察 (encounter 抽出
        # / metrics / debug) を意図し、append の本流は止めない契約。例外は
        # observer 側で握ることを期待するが、念のためここでも握って続行する。
        for observer in self._observers:
            try:
                observer(player_id, output)
            except Exception:
                # observer 自身がログを残すべきだが、誤った observer が裸の
                # raise を残しても append 本流を倒さない構造的防衛。
                import logging

                logging.getLogger(__name__).exception(
                    "ObservationAppender observer raised; skipping (player_id=%s)",
                    int(player_id.value),
                )
        return True

    def _choose_view(self, player_id: PlayerId, output: ObservationOutput) -> ObservationOutput | None:
        """選ぶ口が無い、または選べないときは伏せる側へ倒す。名前は記録に入ったら消せない。"""
        if self._recipient_view is None:
            if output.if_subject_unknown is not None and not self._warned_without_view:
                # 配線漏れで、紹介済みの相手の観測まで黙って伏せたり落としたりしないよう知らせる。
                self._warned_without_view = True
                import logging

                logging.getLogger(__name__).warning(
                    "recipient_view is not wired; recording the subject-unknown view of %s for every recipient",
                    output.structured.get("type"),
                )
            return output.as_subject_unknown()
        try:
            return self._recipient_view(player_id, output)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "recipient_view raised; recording the subject-unknown view (player_id=%s)",
                int(player_id.value),
            )
            return output.as_subject_unknown()

    def _resolve_trace_recorder(self) -> ITraceRecorder | None:
        """use 時に最新の trace_recorder を取得する (provider 優先)。"""
        if self._trace_recorder_provider is not None:
            try:
                return self._trace_recorder_provider()
            except Exception:
                return None
        return self._trace_recorder

    def _record_trace(
        self,
        player_id: PlayerId,
        output: ObservationOutput,
        game_time_label: str | None,
        *,
        hidden_subject_name: str | None = None,
        withheld_subject_name: str | None = None,
    ) -> None:
        recorder = self._resolve_trace_recorder()
        if recorder is None:
            return
        tick: int | None = None
        if self._current_tick_provider is not None:
            try:
                tick = self._current_tick_provider()
            except Exception:
                tick = None
        # payload: LLM に届く prose (人間が読む列で最重要) と structured
        # (機械可読、grep / jq 用)、category と schedules_turn (turn が
        # 積まれたかの判定に使う) を保存する。
        payload: dict[str, Any] = {
            "prose": output.prose,
            "structured": dict(output.structured) if output.structured else {},
            "observation_category": output.observation_category,
            "schedules_turn": bool(output.schedules_turn),
        }
        if game_time_label:
            payload["game_time_label"] = game_time_label
        if hidden_subject_name is not None:
            # trace は人が読む記録で、エージェントには届かない。誰の声を伏せたかを残す。
            payload["subject_hidden"] = True
            payload["hidden_subject_name"] = hidden_subject_name
        if withheld_subject_name is not None:
            # 受け手には届けていない。trace だけが、届かなかった観測と相手を残す。
            payload["subject_withheld"] = True
            payload["hidden_subject_name"] = withheld_subject_name
        try:
            recorder.record(
                TraceEventKind.OBSERVATION,
                tick=tick,
                player_id=int(player_id.value),
                **payload,
            )
        except Exception:
            # trace 失敗で本来の append を止めない
            pass
