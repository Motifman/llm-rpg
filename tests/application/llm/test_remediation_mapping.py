"""remediation_mapping（get_remediation）のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.llm.remediation_mapping import (
    get_remediation,
    DEFAULT_REMEDIATION_BY_ERROR_CODE,
)


class TestGetRemediation:
    """get_remediation の正常・例外ケース"""

    def test_get_remediation_returns_known_error_code_message(self):
        """定義済み error_code を渡すと対応する対処法が返る"""
        result = get_remediation("PLAYER_NOT_FOUND")
        assert result == "指定したプレイヤーが存在しません。"

    def test_get_remediation_returns_message_for_each_defined_code(self):
        """全定義済み error_code で対処法が返る"""
        for error_code, expected in DEFAULT_REMEDIATION_BY_ERROR_CODE.items():
            result = get_remediation(error_code)
            assert result == expected

    def test_get_remediation_returns_default_for_unknown_error_code(self):
        """未定義の error_code を渡すと汎用メッセージが返る"""
        result = get_remediation("UNKNOWN_CODE")
        assert result == "エラー内容を確認し、別の行動を選んでください。"

    def test_get_remediation_returns_default_for_empty_string(self):
        """空文字の error_code を渡すと汎用メッセージが返る"""
        result = get_remediation("")
        assert result == "エラー内容を確認し、別の行動を選んでください。"

    def test_invalid_target_kind_remediation_hides_internal_terms(self):
        """INVALID_TARGET_KIND の対処法は LLM に内部用語や不自然な対象名を見せない"""
        result = get_remediation("INVALID_TARGET_KIND")
        forbidden = (
            "地面アイテム",
            "item_spec_id",
            "slot",
            "instance",
            "player_id",
            "monster_id",
        )
        assert "その場に落ちているものの名前" in result
        assert not any(term in result for term in forbidden), result

    def test_give_target_not_same_spot_remediation_uses_natural_movement_hint(self):
        """give_item の相手不在対処法は tool 名や spot ではなく自然な移動指示にする"""
        result = get_remediation("GIVE_ITEM_TARGET_NOT_IN_SAME_SPOT")
        assert "先に相手のいる場所へ移動" in result
        assert "同じ場所にいる別の相手" in result
        assert "travel_to" not in result
        assert "spot" not in result

    def test_get_remediation_error_code_none_raises_type_error(self):
        """error_code が None のとき TypeError"""
        with pytest.raises(TypeError, match="error_code must be str"):
            get_remediation(None)  # type: ignore[arg-type]

    def test_get_remediation_error_code_not_str_raises_type_error(self):
        """error_code が str でないとき TypeError"""
        with pytest.raises(TypeError, match="error_code must be str"):
            get_remediation(123)  # type: ignore[arg-type]

    def test_get_remediation_error_code_list_raises_type_error(self):
        """error_code が list のとき TypeError"""
        with pytest.raises(TypeError, match="error_code must be str"):
            get_remediation(["PLAYER_NOT_FOUND"])  # type: ignore[arg-type]
