"""型付き判断を profile から入れ、足りない設定は起動前に落とす。

## 実験設定は profile からだけ入れる

有効化・接続先・モデル・timeout は profile / 実験設定 JSON に集約する
(design_decisions #28)。環境変数で実験フラグを直接渡す経路は作らない。
例外は秘密情報だけで、**キーの値は profile に書かせない**。

## 足りない設定は run の途中で気づかせない

`provider=jev` なのにキーが無い run は、1 件目の判断まで進んでから失敗する。
そこまでに使った時間と API 費用は戻らない。起動前に落とす
(design_decisions #10)。

とくに ``EMPTY`` を弾く。ローカル vLLM 構成では ``OPENAI_API_KEY`` が
``EMPTY`` になる。その値で OpenRouter に送ると 401 になるので、キーが
「在る」と数えてはいけない。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)
from ai_rpg_world.application.llm.wiring._typed_judgment_factory import (
    create_typed_judgment_port_from_config,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.infrastructure.llm.jev_typed_judgment_adapter import (
    JevTypedJudgmentAdapter,
)


def _config(**values: str) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(values=values)


class TestTheProfileDecidesWhetherTypedJudgmentIsOn:
    """有効化と接続先が profile から入り、未知値は起動前に落ちることを保証する。"""

    def test_typed_judgment_is_off_unless_the_profile_asks_for_it(self) -> None:
        """何も書かなければ provider は off で、現行の run と同じ設定になる。"""
        assert _config().typed_judgment_provider == "off"

    def test_a_profile_can_turn_typed_judgment_on(self) -> None:
        """profile に TYPED_JUDGMENT_PROVIDER を書くと、解決済み設定に載る。"""
        assert _config(TYPED_JUDGMENT_PROVIDER="jev").typed_judgment_provider == "jev"

    def test_an_unknown_provider_is_rejected_before_the_run_starts(self) -> None:
        """綴りを間違えた provider は ValueError になる。off へ黙って縮退しない。"""
        with pytest.raises(ValueError):
            _config(TYPED_JUDGMENT_PROVIDER="jvev")

    def test_the_endpoint_model_and_timeout_have_defaults(self) -> None:
        """接続先・モデル・timeout は書かなければ既定値になる。"""
        config = _config()

        assert config.typed_judgment_endpoint == ("https://openrouter.ai/api/alpha/decisions")
        assert config.typed_judgment_model == "typesafe/jev-1.13"
        assert config.typed_judgment_timeout_seconds == 10.0

    def test_the_endpoint_model_and_timeout_can_be_overridden(self) -> None:
        """TypeSafe 直叩きへ差し替えるなど、接続先を profile から変えられる。"""
        config = _config(
            TYPED_JUDGMENT_ENDPOINT="https://api.typesafe.ai/v1/systemone",
            TYPED_JUDGMENT_MODEL="jev-latest",
            TYPED_JUDGMENT_TIMEOUT_SECONDS="3.5",
        )

        assert config.typed_judgment_endpoint == "https://api.typesafe.ai/v1/systemone"
        assert config.typed_judgment_model == "jev-latest"
        assert config.typed_judgment_timeout_seconds == 3.5

    def test_a_non_positive_timeout_is_rejected(self) -> None:
        """timeout に 0 以下を書くと ValueError になる。"""
        with pytest.raises(ValueError):
            _config(TYPED_JUDGMENT_TIMEOUT_SECONDS="0")

    def test_the_key_itself_cannot_be_written_in_the_profile(self) -> None:
        """キーの値を profile に書くと「秘密は env から」と言って拒まれる。

        ``ValueError`` だけを見ると、未知のキーとして弾かれた場合と区別できない。
        秘密として弾いたのか、名前を知らないだけなのかで、読み手が次に取る手が
        変わる。文面まで見る。
        """
        with pytest.raises(ValueError) as caught:
            _config(OPENROUTER_API_KEY="sk-or-v1-leaked")

        message = str(caught.value)
        assert "secret" in message
        assert "process environment" in message

    def test_the_profile_names_which_env_var_holds_the_key(self) -> None:
        """キーの値ではなく、キーの在り処 (env の名前) を profile に書く。"""
        config = _config(TYPED_JUDGMENT_API_KEY_ENV="MY_JEV_KEY")

        assert config.typed_judgment_api_key_env == "MY_JEV_KEY"

    def test_the_default_key_env_is_the_openrouter_one(self) -> None:
        """既定のキーの在り処は OPENROUTER_API_KEY になる。"""
        assert _config().typed_judgment_api_key_env == "OPENROUTER_API_KEY"


class TestTheFactoryBuildsWhatTheProfileAskedFor:
    """provider に応じた実装が組まれること、組めない設定で落ちることを保証する。"""

    def test_off_builds_nothing(self) -> None:
        """off なら None を返す。呼び出し側は判断を引かない。"""
        assert create_typed_judgment_port_from_config(_config(), env={}) is None

    def test_stub_builds_the_deterministic_port(self) -> None:
        """stub なら実 API を呼ばない決定論の実装が組まれる。キーは要らない。"""
        port = create_typed_judgment_port_from_config(_config(TYPED_JUDGMENT_PROVIDER="stub"), env={})

        assert isinstance(port, DeterministicTypedJudgmentPort)

    def test_jev_builds_the_adapter_when_the_key_is_there(self) -> None:
        """jev でキーが在れば、実 API を呼ぶアダプタが組まれる。"""
        port = create_typed_judgment_port_from_config(
            _config(TYPED_JUDGMENT_PROVIDER="jev"),
            env={"OPENROUTER_API_KEY": "sk-or-v1-real"},
        )

        assert isinstance(port, JevTypedJudgmentAdapter)

    def test_jev_without_a_key_fails_before_the_run_starts(self) -> None:
        """jev でキーが無ければ ValueError。1 件目の判断まで進ませない。"""
        with pytest.raises(ValueError) as caught:
            create_typed_judgment_port_from_config(_config(TYPED_JUDGMENT_PROVIDER="jev"), env={})

        assert "OPENROUTER_API_KEY" in str(caught.value)

    def test_a_placeholder_key_is_not_counted_as_a_key(self) -> None:
        """EMPTY は ValueError になる。

        ローカル vLLM 構成では ``OPENAI_API_KEY`` が ``EMPTY`` になる。その値で
        OpenRouter に送ると 401 になるので、在ると数えてはいけない。
        """
        with pytest.raises(ValueError):
            create_typed_judgment_port_from_config(
                _config(TYPED_JUDGMENT_PROVIDER="jev"),
                env={"OPENROUTER_API_KEY": "EMPTY"},
            )

    def test_the_openai_key_is_used_as_a_fallback(self) -> None:
        """指定の env が無ければ OPENAI_API_KEY を使う。

        この repo では OpenRouter のキーが ``OPENAI_API_KEY`` に入っている。
        名前が実体とずれているので、落ちたことは警告に残す。
        """
        port = create_typed_judgment_port_from_config(
            _config(TYPED_JUDGMENT_PROVIDER="jev"),
            env={"OPENAI_API_KEY": "sk-or-v1-real"},
        )

        assert isinstance(port, JevTypedJudgmentAdapter)

    def test_the_named_env_wins_over_the_fallback(self) -> None:
        """指定の env に使える値が在れば、fallback が壊れていても組める。

        逆順に読んでいたら ``EMPTY`` を拾って落ちる。優先順を値の側から見る。
        """
        port = create_typed_judgment_port_from_config(
            _config(TYPED_JUDGMENT_PROVIDER="jev"),
            env={"OPENROUTER_API_KEY": "sk-or-v1-real", "OPENAI_API_KEY": "EMPTY"},
        )

        assert isinstance(port, JevTypedJudgmentAdapter)

    def test_the_failure_says_why_a_placeholder_is_not_a_key(self) -> None:
        """EMPTY で落ちたときは、その値だったことを文面で伝える。

        「キーが無い」とだけ言われると、設定したのに読まれていないと読める。
        置いた値が使えないことと、置いていないことを同じ文面にしない。
        """
        with pytest.raises(ValueError) as caught:
            create_typed_judgment_port_from_config(
                _config(TYPED_JUDGMENT_PROVIDER="jev"),
                env={"OPENROUTER_API_KEY": "EMPTY"},
            )

        assert "EMPTY" in str(caught.value)


class TestTheRemovedTurnGateKeysAreRejected:
    """消した起動判定 (#1631) のキーを profile に書くと、未知のキーとして起動前に落ちることを保証する。

    黙って無視すると、起動判定を入れたつもりの run が全員を回したまま走る。
    """

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("TYPED_JUDGMENT_TURN_GATE_ENABLED", "1"),
            ("TYPED_JUDGMENT_TURN_GATE_SKIP_BELOW", "0.2"),
        ],
    )
    def test_a_removed_turn_gate_key_is_rejected_as_unknown(self, key: str, value: str) -> None:
        """起動判定の有効化と閾値のキーを書くと、unknown runtime_config key の ValueError になる。"""
        with pytest.raises(ValueError, match=f"unknown runtime_config key.*{key}"):
            _config(**{key: value})


class TestTheRemovedThresholdKeysAreRejected:
    """閾値を外した問い (#1427) の閾値キーを profile に書くと、未知のキーとして起動前に落ちることを保証する。

    黙って無視すると、閾値を動かしたつもりの run が何も変えずに走る。
    """

    @pytest.mark.parametrize(
        "key",
        [
            "TYPED_JUDGMENT_TOOL_NAME_MIN_CONFIDENCE",
            "TYPED_JUDGMENT_LOOP_DIAGNOSIS_MIN_CONFIDENCE",
        ],
    )
    def test_a_removed_threshold_key_is_rejected_as_unknown(self, key: str) -> None:
        """tool 名の提案・繰り返しの理由の判定の閾値キーを書くと、unknown runtime_config key の ValueError になる。"""
        with pytest.raises(ValueError, match=f"unknown runtime_config key.*{key}"):
            _config(**{key: "0.7"})


class TestTheLoopDiagnosisSettingsComeFromTheProfile:
    """繰り返しの理由の判定 (#1411) の有効化が profile から入ることを保証する。"""

    def test_the_diagnosis_is_off_by_default(self) -> None:
        """何も書かなければ判定は無効。provider を jev にしても入らない。"""
        config = _config(TYPED_JUDGMENT_PROVIDER="jev")
        assert config.typed_judgment_loop_diagnosis_enabled is False

    def test_a_profile_can_turn_the_diagnosis_on(self) -> None:
        """TYPED_JUDGMENT_LOOP_DIAGNOSIS_ENABLED=1 と書くと、解決済み設定に載る。"""
        config = _config(TYPED_JUDGMENT_LOOP_DIAGNOSIS_ENABLED="1")
        assert config.typed_judgment_loop_diagnosis_enabled is True


class TestTheSemanticRepeatSettingsComeFromTheProfile:
    """意味上の繰り返しの検出 (#1412) の有効化・閾値・窓の大きさが profile から入り、範囲外は起動前に落ちる。"""

    def test_the_detector_is_off_by_default_even_with_jev(self) -> None:
        """何も書かなければ無効。provider を jev にしても入らない。閾値の既定は 0.8、窓は 4 件。"""
        config = _config(TYPED_JUDGMENT_PROVIDER="jev")

        assert config.typed_judgment_semantic_repeat_enabled is False
        assert config.typed_judgment_semantic_repeat_min_probability == 0.8
        assert config.typed_judgment_semantic_repeat_window == 4

    def test_a_profile_can_turn_the_detector_on_and_move_its_settings(self) -> None:
        """有効化・閾値・窓の大きさは profile の値が解決済み設定に載る。"""
        config = _config(
            TYPED_JUDGMENT_SEMANTIC_REPEAT_ENABLED="1",
            TYPED_JUDGMENT_SEMANTIC_REPEAT_MIN_PROBABILITY="0.9",
            TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW="5",
        )

        assert config.typed_judgment_semantic_repeat_enabled is True
        assert config.typed_judgment_semantic_repeat_min_probability == 0.9
        assert config.typed_judgment_semantic_repeat_window == 5

    def test_a_threshold_outside_the_unit_interval_is_rejected(self) -> None:
        """閾値が (0, 1] の外なら ValueError になる。黙って丸めない。"""
        with pytest.raises(ValueError, match="must be in"):
            _config(TYPED_JUDGMENT_SEMANTIC_REPEAT_MIN_PROBABILITY="1.5")

    @pytest.mark.parametrize("window", ["1", "0", "four"])
    def test_a_window_smaller_than_two_is_rejected(self, window: str) -> None:
        """窓が 2 件未満か整数でなければ ValueError になる。繰り返しを材料にできない。"""
        with pytest.raises(ValueError, match="must be|is not an integer"):
            _config(TYPED_JUDGMENT_SEMANTIC_REPEAT_WINDOW=window)

    def test_the_test_defaults_keep_the_detector_off(self) -> None:
        """テスト用の既定設定でも検出は無効で、閾値と窓は profile の既定と同じ。"""
        config = ResolvedLlmRuntimeConfig.for_tests()

        assert config.typed_judgment_semantic_repeat_enabled is False
        assert config.typed_judgment_semantic_repeat_min_probability == 0.8
        assert config.typed_judgment_semantic_repeat_window == 4
