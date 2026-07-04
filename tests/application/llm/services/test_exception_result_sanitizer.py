"""``exception_result`` の LLM 向け sanitizer (Y_after_pr639_640 audit、PR-δ)。

## なぜ

``tool_executor_helpers.exception_result(e)`` は 20+ 箇所の executor から
「予期せぬ例外を捕捉した last resort」として呼ばれる共通 helper。従来は
``message=str(e)`` の直渡しで、以下の問題があった:

- 生の Exception (``KeyError``, ``ValueError``, ``RuntimeError``) は英語
  message + 内部 ID を含む (例: ``"key 'inventory_slot_id' not found"``)
- Domain 層でも「稀な整合性違反」の raise は英語のまま
- LLM は英語 + 内部 ID を受け取っても次アクションを取れない

## 何を

``exception_result`` に「LLM 向け sanitizer」を追加:

1. **Domain exception (``error_code`` 属性あり)**: 従来通り str(e) を尊重
   (domain 層の日本語 message が既に整備されている前提)
2. **非 domain exception + str(e) に日本語文字が含まれる**: 尊重 (application
   層で日本語 message を組んで raise した ApplicationException 等)
3. **非 domain exception + 純 ASCII / 空 message**: 汎用日本語 fallback に
   置き換える (「システムエラーが発生しました。少し tick を進めてから
   再試行するか、別の tool を選んでください。」)

3 の判定は「str(e) に少なくとも 1 文字の日本語 (hiragana / katakana / kanji)
が含まれるか」で行う。英語混じり (「〜が not found」等) は日本語文字が
含まれるので尊重される — 完全に英語だけの Exception (Python 組み込み系)
だけを fallback にする、保守的な設計。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
)


class TestExceptionResultDomainException:
    """``error_code`` 属性を持つ domain exception。error_code は保持されるが
    message は「日本語判定」に基づいて sanitize される (下記 English case 参照)。"""

    def test_error_code_付きの_domain_exception_は_message_と_code_を_使う(self) -> None:
        class MyDomainError(Exception):
            error_code = "GIVE_ITEM_TARGET_IS_SELF"

        exc = MyDomainError("自分自身にアイテムを渡すことはできません。")
        result = exception_result(exc)
        assert result.success is False
        assert result.error_code == "GIVE_ITEM_TARGET_IS_SELF"
        assert result.message == "自分自身にアイテムを渡すことはできません。"

    def test_error_code_付きだが_message_が英語の_domain_exception_も_message_は_fallback(self) -> None:
        """PR-δ v1 抜け穴修正: ``ItemNotInSlotException("No item in slot 3")``
        のように「error_code は日本語じゃないカテゴリだが message 側が
        整備されていない」ケースを塞ぐ。error_code / remediation は保持し、
        message は英語漏れを防ぐため fallback に置換。"""
        class MyDomainError(Exception):
            error_code = "PLAYER.ITEM_NOT_IN_SLOT"

        exc = MyDomainError("No item in slot 3")
        result = exception_result(exc)
        assert result.error_code == "PLAYER.ITEM_NOT_IN_SLOT"
        # 英語 message は漏れない
        assert "No item" not in result.message
        assert "slot 3" not in result.message
        # 汎用日本語 fallback
        assert "システム" in result.message or "エラー" in result.message


class TestExceptionResultEnglishFallback:
    """domain exception ではない英語 exception は汎用日本語 fallback。"""

    def test_KeyError_の英語_message_は_日本語_fallback_に置換される(self) -> None:
        exc = KeyError("inventory_slot_id")
        result = exception_result(exc)
        assert result.success is False
        assert result.error_code == "SYSTEM_ERROR"
        # 英語文字列 (内部 ID) が LLM に漏れていない
        assert "inventory_slot_id" not in result.message
        # 日本語 fallback が入っている
        assert "システム" in result.message or "エラー" in result.message

    def test_ValueError_英語_の_message_も_日本語_fallback_に置換される(self) -> None:
        exc = ValueError("invalid literal for int() with base 10: 'foo'")
        result = exception_result(exc)
        assert "invalid literal" not in result.message
        # LLM が次アクションを取るための日本語 hint がある
        assert "エラー" in result.message or "再試" in result.message or "別" in result.message

    def test_message_が_空の_exception_も_日本語_fallback(self) -> None:
        """str(e) が空の Exception でも汎用日本語で埋める。"""
        exc = RuntimeError()
        result = exception_result(exc)
        # 空 message ではなく日本語がある
        assert len(result.message) > 0
        assert "エラー" in result.message or "システム" in result.message


class TestExceptionResultJapaneseMessagePreserved:
    """日本語 message は (domain exception でなくても) 尊重される。"""

    def test_日本語混じり_の_exception_message_は_そのまま_LLM_に届く(self) -> None:
        """application 層で日本語 raise する ApplicationException 等の互換性を保つ。
        「〜 not found」のような英語混じりでも日本語文字が 1 個でもあれば尊重。"""
        exc = RuntimeError("アイテムが見つかりませんでした。再度確認してください。")
        result = exception_result(exc)
        assert result.message == "アイテムが見つかりませんでした。再度確認してください。"

    def test_ひらがなだけでも_日本語判定_される(self) -> None:
        exc = RuntimeError("あ")  # 極端ケース
        result = exception_result(exc)
        assert result.message == "あ"

    def test_漢字だけでも_日本語判定_される(self) -> None:
        exc = RuntimeError("失敗")
        result = exception_result(exc)
        assert result.message == "失敗"

    def test_カタカナだけでも_日本語判定_される(self) -> None:
        exc = RuntimeError("エラー")
        result = exception_result(exc)
        assert result.message == "エラー"


class TestExceptionResultRemediation:
    """remediation は error_code に対応するものを埋める。"""

    def test_domain_exception_の_remediation_は_error_code_由来(self) -> None:
        class MyErr(Exception):
            error_code = "GIVE_ITEM_TARGET_IS_SELF"

        result = exception_result(MyErr("自分に渡せません"))
        # PR-α で登録済み
        assert "自分自身" in result.remediation or "別" in result.remediation

    def test_english_fallback_の_remediation_は_SYSTEM_ERROR_由来(self) -> None:
        result = exception_result(RuntimeError("something broke internally"))
        assert result.error_code == "SYSTEM_ERROR"
        # SYSTEM_ERROR は既存 mapping で「しばらくしてから再度お試しください。」
        assert "しばらく" in result.remediation or "再度" in result.remediation
