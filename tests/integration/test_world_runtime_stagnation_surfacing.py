"""P-U3/P-U4 (停滞感の表出): world_runtime を通した実プロンプトへの配線を固定する。

P-U2 (停滞感 store) が保持するカウンタを、``stagnation_band_provider`` 1 本
経由で自己 (P-U3) / 他者 (P-U4) の両方に表出できることを、``create_world_runtime``
から ``build_llm_context`` までの実配線で確認する。LLM は呼ばない。

STAGNATION_PRESSURE_ENABLED は新設せず P-U2 の flag を再利用するため、OFF
(既定) のときは stagnation_band_provider が常に none を返し、導入前と
プロンプトが完全一致することも合わせて固定する (プレフィックスキャッシュ
不変・docs/design_decisions.md #1 に抵触しないことの確認も兼ねる: ツール
スキーマ自体は変わらず、user メッセージの state section だけが変わる)。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.runtime_config_helpers import belief_consolidation_config

_UNRESOLVED_BEING_LOG_SUBSTRING = "に attach 済みの being が見つからず"


class _AlwaysNoneBeingResolver:
    """resolve_being_id が常に None を返す stub resolver。

    「player が being に未 attach」の状況を、実シナリオの player_id を
    差し替えることなく再現するための代役。runtime 構築後に
    ``runtime._aux_being_resolver`` を本 stub へ差し替えて使う。
    """

    def resolve_being_id(self, world_id, player_id):  # noqa: ANN001, ARG002
        return None

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "single_relic_contention_demo.json"
)


def _stagnation_config(**overrides):
    return belief_consolidation_config(goal_reflect_enabled=True, **overrides)


def _being_id(runtime, player_id: int):
    return runtime.aux_being_resolver.resolve_being_id(
        runtime.aux_being_default_world_id, PlayerId(player_id)
    )


class TestOwnStagnationSurfacingWiring:
    """P-U3: 自分の停滞感カウンタが自分の身体の状態 section に出る。"""

    def test_カウンタ3以上で_strong_の自己hintが出る(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_stagnation_config(stagnation_pressure_enabled=True),
        )
        being_id = _being_id(runtime, 1)
        assert being_id is not None
        for _ in range(3):
            runtime._stagnation_pressure_store.increment_by_being(being_id)

        dto = runtime.build_llm_context(PlayerId(1))
        assert "同じことばかり繰り返している焦りが拭えない" in dto.current_state_text

    def test_カウンタ1_2で_light_の自己hintが出る(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_stagnation_config(stagnation_pressure_enabled=True),
        )
        being_id = _being_id(runtime, 1)
        assert being_id is not None
        runtime._stagnation_pressure_store.increment_by_being(being_id)

        dto = runtime.build_llm_context(PlayerId(1))
        assert "何かが前に進んでいない気がする" in dto.current_state_text

    def test_カウンタ0では_自己hintは出ない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_stagnation_config(stagnation_pressure_enabled=True),
        )
        # カウンタに一切触れない (= 0 のまま)。
        dto = runtime.build_llm_context(PlayerId(1))
        assert "前に進んでいない" not in dto.current_state_text
        assert "繰り返している" not in dto.current_state_text


class TestOtherStagnationSurfacingWiring:
    """P-U4: 同 spot の他 player の停滞感カウンタが nearby_entities 側に出る。"""

    def test_相手のカウンタが3以上なら_苛立って落ち着かない様子_が見える(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_stagnation_config(stagnation_pressure_enabled=True),
        )
        being_id_p1 = _being_id(runtime, 1)
        assert being_id_p1 is not None
        for _ in range(3):
            runtime._stagnation_pressure_store.increment_by_being(being_id_p1)

        # player 2 視点から player 1 (停滞中) がどう見えるか。
        dto = runtime.build_llm_context(PlayerId(2))
        assert "苛立って落ち着かない様子" in dto.current_state_text

    def test_自分自身の停滞感は自分のnearby_entities欄には出ない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """自分自身は同席者リストに出ない前提の回帰ガード。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_stagnation_config(stagnation_pressure_enabled=True),
        )
        being_id_p1 = _being_id(runtime, 1)
        assert being_id_p1 is not None
        for _ in range(3):
            runtime._stagnation_pressure_store.increment_by_being(being_id_p1)

        dto = runtime.build_llm_context(PlayerId(1))
        # 自己 hint (→ 行) では出るが、同席者向け suffix (苛立って...) は
        # 自分自身の行には付かない (対象は他者のみ)。
        assert "同じことばかり繰り返している焦りが拭えない" in dto.current_state_text
        assert "苛立って落ち着かない様子" not in dto.current_state_text


class TestStagnationSurfacingOffByDefault:
    """flag (STAGNATION_PRESSURE_ENABLED) OFF のとき、導入前とプロンプトが
    完全一致すること (= 表出が一切乗らない)。"""

    def test_flag_off_なら_store_が_none_で_自己他者とも表出しない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(_SCENARIO_PATH, config=_stagnation_config())
        assert runtime._stagnation_pressure_store is None

        dto1 = runtime.build_llm_context(PlayerId(1))
        dto2 = runtime.build_llm_context(PlayerId(2))
        for text in (dto1.current_state_text, dto2.current_state_text):
            assert "前に進んでいない" not in text
            assert "繰り返している" not in text
            assert "手詰まり" not in text
            assert "苛立って" not in text

    def test_flag_off_のプロンプトは_flag導入前_相当と一致する(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P-U3/P-U4 の provider は常時配線されるが、store が None のときは
        常に none を返すため、STAGNATION_PRESSURE_ENABLED=1 でもカウンタに
        一切触れなければ (= 実質 OFF と同じ状態) OFF 時と同一のテキストになる
        ことを確認し、プレフィックスキャッシュ不変への影響が無いことを保証
        する。"""
        runtime_off = create_world_runtime(_SCENARIO_PATH, config=_stagnation_config())
        text_off = runtime_off.build_llm_context(PlayerId(1)).current_state_text

        runtime_on_untouched = create_world_runtime(
            _SCENARIO_PATH,
            config=_stagnation_config(stagnation_pressure_enabled=True),
        )
        text_on_untouched = runtime_on_untouched.build_llm_context(
            PlayerId(1)
        ).current_state_text

        assert text_off == text_on_untouched


class TestStagnationBandUnresolvedBeingDiagnostics:
    """MEDIUM-1: being 未解決の無言 none 縮退に診断ログを 1 本足す挙動を保証する。

    ``being_id is None`` は「player が being に未 attach」等で正当に起こり
    得る一方、配線漏れでも同じ none 縮退になり見分けが付かない。ログが無い
    と「停滞感が永久に出ない」を「前進中で count==0」と区別できないため、
    store が組めているのに being だけ解決できない経路に限定して警告を残す。
    """

    def test_store非Noneでbeing未解決なら警告が1回だけ出てbandはnoneのまま(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_stagnation_config(stagnation_pressure_enabled=True),
        )
        assert runtime._stagnation_pressure_store is not None
        # being を未 attach 状態に見立てるため resolver を stub に差し替える。
        runtime._aux_being_resolver = _AlwaysNoneBeingResolver()

        # 1 回目の build_llm_context は「本人 (player_id=1)」と「同室の
        # 他 player (player_id=2)」の両方の band を解決するため、それぞれ
        # 1 回ずつ警告が出るのが正しい (スロットルは player_id 単位)。
        # 2 回目の呼び出しでは player_id=1 の分だけ再警告されないことを見る。
        with caplog.at_level(logging.WARNING):
            dto1 = runtime.build_llm_context(PlayerId(1))
            dto2 = runtime.build_llm_context(PlayerId(1))

        for text in (dto1.current_state_text, dto2.current_state_text):
            assert "前に進んでいない" not in text
            assert "繰り返している" not in text

        player1_warnings = [
            record
            for record in caplog.records
            if _UNRESOLVED_BEING_LOG_SUBSTRING in record.getMessage()
            and "player_id=1 " in record.getMessage()
        ]
        assert len(player1_warnings) == 1
        assert player1_warnings[0].levelno == logging.WARNING

    def test_store未構築_flag_offなら被attach警告は出ずbandはnoneのまま(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        runtime = create_world_runtime(_SCENARIO_PATH, config=_stagnation_config())
        assert runtime._stagnation_pressure_store is None
        # 機能自体が無効な経路では resolver を差し替えなくても being 未解決
        # 判定に到達しないはずだが、念のため常に None を返す stub にしておき
        # 「resolver が None を返すこと」自体は警告の起点にならないことを
        # 確認する。
        runtime._aux_being_resolver = _AlwaysNoneBeingResolver()

        with caplog.at_level(logging.WARNING):
            dto = runtime.build_llm_context(PlayerId(1))

        assert "前に進んでいない" not in dto.current_state_text
        assert "繰り返している" not in dto.current_state_text
        unresolved_warnings = [
            record
            for record in caplog.records
            if _UNRESOLVED_BEING_LOG_SUBSTRING in record.getMessage()
        ]
        assert unresolved_warnings == []
