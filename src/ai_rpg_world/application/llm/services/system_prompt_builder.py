"""システムプロンプト生成のデフォルト実装。

Issue #227 後続レビュー Prompt MEDIUM-7: 旧 .replace() 連鎖は変数 typo
(例: `{{plyer_name}}`) が実行時にもエラーにならず、文字列として残るだけ
だった。本ファイルでは __init__ 時に template を scan し、未知変数を
発見したら構築時 ValueError を投げる「strict mode」を導入する。
"""

import re

from ai_rpg_world.application.llm.contracts.dtos import SystemPromptPlayerInfoDto
from ai_rpg_world.application.llm.contracts.interfaces import ISystemPromptBuilder


DEFAULT_SYSTEM_PROMPT_TEMPLATE = """あなたは「{{player_name}}」という、独自の性格・記憶・感情を持って世界に存在する一人の人物です。
{{game_description}}

【基本情報】
役職: {{role}} / 種族: {{race}} / 属性: {{element}}

{{persona_block}}

【行動の構え】
ユーザーメッセージには「現在の状況」「直近の出来事」「関連する記憶」が並んでいます。
- 「関連する記憶」は、あなた自身が過去に体験し、いまこの状況で自然に思い出された主観的な記憶です。第三者から渡された参考資料ではなく、あなた自身の内側にある記憶として読んでください。
- これら3つを頭の中で並べ、ペルソナ・現在の感情・思い出された記憶の含みを踏まえて、いまのあなたが自然に取る行動を1つ選んでください。
- 直前のターンの行動が失敗していた場合、メッセージ先頭にその補正情報があります。あれば最優先で踏まえ、別の手を選び直してください。

【世界とのやり取りの規約】
- 行動はツール（関数）呼び出しでのみ可能です。1ターンに必ず1つのツールを呼んでください。
- 対象や移動先を指定するときは、「現在の状況」に表示された **名前そのもの** (例: \"焚き火跡\" / \"灰色のオオカミ\" / \"流木\") を使ってください。同じ名前のものが複数並んでいる場合は ``#1`` / ``#2`` の ordinal が付くので、その表記そのままを指定します。
- memo ツール（memo_add / memo_list / memo_done）が利用可能であれば、ターンを跨いで覚えておきたい目標 / 戦略 / 観察などを context に固定できます。完了したら memo_done で記録してください。
"""

# Template 内で許容する変数名。SystemPromptPlayerInfoDto の field と一致させる。
# 新しい変数を template に足すときはここにも追加すること (未知変数なら
# DefaultSystemPromptBuilder.__init__ で ValueError)。
_ALLOWED_TEMPLATE_VARS: frozenset[str] = frozenset({
    "player_name",
    "game_description",
    "role",
    "race",
    "element",
    "persona_block",
})

# `{{name}}` 形式のプレースホルダを抽出する正規表現
_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _validate_template_strict(template: str) -> None:
    """template 内の `{{var}}` を全て scan し、未知変数があれば ValueError。

    typo (例: `{{plyer_name}}`) を構築時に検出する。caller が
    `system_prompt_template=...` でカスタム template を渡したケースで効く。
    """
    found_vars = set(_PLACEHOLDER_PATTERN.findall(template))
    unknown = found_vars - _ALLOWED_TEMPLATE_VARS
    if unknown:
        sorted_unknown = ", ".join(sorted(unknown))
        sorted_allowed = ", ".join(sorted(_ALLOWED_TEMPLATE_VARS))
        raise ValueError(
            f"DefaultSystemPromptBuilder: 未知のテンプレート変数 {{{sorted_unknown}}}。"
            f"許容される変数: {sorted_allowed}"
        )


class DefaultSystemPromptBuilder(ISystemPromptBuilder):
    """SystemPromptPlayerInfoDto からシステムプロンプト文字列を生成する。

    Issue #227 後続レビュー Prompt MEDIUM-7:
        __init__ で template 内の `{{var}}` を全て scan し、未知変数を発見したら
        即時 ValueError を投げる (strict mode)。これにより typo は construction
        time に検出され、実 LLM 呼び出し直前まで気付かないという旧挙動を解消する。
    """

    def __init__(self, template: str = DEFAULT_SYSTEM_PROMPT_TEMPLATE) -> None:
        if not isinstance(template, str):
            raise TypeError("template must be str")
        _validate_template_strict(template)
        self._template = template

    def build(self, player_info: SystemPromptPlayerInfoDto) -> str:
        if not isinstance(player_info, SystemPromptPlayerInfoDto):
            raise TypeError("player_info must be SystemPromptPlayerInfoDto")
        # template 検証が __init__ で済んでいるので、ここは単純置換で OK
        return self._template.replace("{{player_name}}", player_info.player_name).replace(
            "{{game_description}}", player_info.game_description or ""
        ).replace("{{role}}", player_info.role).replace(
            "{{race}}", player_info.race
        ).replace("{{element}}", player_info.element).replace(
            "{{persona_block}}", player_info.persona_block or ""
        )
