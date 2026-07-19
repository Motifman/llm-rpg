"""``give_item`` を batch-always (gives 配列常時) に統合する
(Y_after_pr639_640_200tick 後続、PR-α)。

Y_after_pr639_640 分析での議論:
- 旧 ``give_item`` (単発) と ``give_items`` (batch) の 2 tool が併存し混乱
- ``give_items`` は元々「1 tick で複数配布」を実現する意図で導入されたが、
  PR-BB (廃止提案) は本 PR で撤回。batch 機能は必要
- 解決: ``give_item`` の schema を ``gives: [...]`` 常時配列に変更し、
  単発 (len=1) も batch も同じ tool で表現する。``give_items`` は
  ``give_item`` へ吸収されて消える

## 統合後の give_item schema

```json
{
  "gives": {
    "type": "array",
    "minItems": 1,
    "maxItems": 8,
    "items": {
      "type": "object",
      "properties": {
        "item_label": {...},
        "target_player_label": {...}
      },
      "required": ["item_label", "target_player_label"]
    }
  },
  "inner_thought": {...},
  "say_inline": {...}
}
```

## 単発ケースの LLM 側の書き方

```json
{"gives": [{"item_label": "野いちご", "target_player_label": "ノア"}]}
```

長さ 1 の配列でラップするだけ。パターンが 1 種類 (常に配列) なので LLM が
迷わない。旧単発版の ``item_label`` + ``target_player_label`` トップレベル
指定は廃止する (union 型による schema 複雑化を避ける)。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    GIVE_ITEM_DEFINITION,
    get_spot_graph_specs,
)


class TestGiveItemDefinitionIsBatchAlways:
    """統合後の give_item schema が batch-always である。"""

    def test_give_item_required_gives_included(self) -> None:
        """トップレベルの ``item_label`` / ``target_player_label`` は廃止、
        ``gives`` 配列必須に。"""
        props = GIVE_ITEM_DEFINITION.parameters["properties"]
        required = GIVE_ITEM_DEFINITION.parameters["required"]
        assert "gives" in props
        assert "gives" in required
        # 旧 top-level 引数は廃止
        assert "item_label" not in props, "top-level item_label は廃止"
        assert "target_player_label" not in props, (
            "top-level target_player_label は廃止"
        )

    def test_gives_array_type_length(self) -> None:
        """gives は array 型で length 制約あり。"""
        gives_spec = GIVE_ITEM_DEFINITION.parameters["properties"]["gives"]
        assert gives_spec["type"] == "array"
        assert gives_spec.get("minItems") == 1
        # LLM の 1 turn で無限 give を防ぐ現実的な上限
        assert gives_spec.get("maxItems") is not None
        assert gives_spec["maxItems"] >= 1

    def test_gives_entry_item_label_target_player_label_required(self) -> None:
        """gives の各 entry は itemlabel と targetplayerlabel が required。"""
        gives_items = GIVE_ITEM_DEFINITION.parameters["properties"]["gives"][
            "items"
        ]
        assert gives_items["type"] == "object"
        entry_props = gives_items["properties"]
        entry_required = gives_items["required"]
        assert "item_label" in entry_props
        assert "target_player_label" in entry_props
        assert "item_label" in entry_required
        assert "target_player_label" in entry_required


class TestGiveItemsIsDeleted:
    """旧 ``give_items`` tool は完全削除された (give_item に吸収)。"""

    def test_give_items_spec_get_spot_graph_specs(self) -> None:
        """giveitemsspec は getspotgraphspecs から消えている。"""
        names = {defn.name for defn, _ in get_spot_graph_specs()}
        assert "give_items" not in names, (
            "give_items は give_item (batch-always) に統合されて廃止された"
        )

    def test_give_item_appears_once_in_spot_graph_specs(self) -> None:
        """give item は get spot graph specs に 1件だけ存在する。"""
        names = [defn.name for defn, _ in get_spot_graph_specs()]
        assert names.count("give_item") == 1


class TestGiveItemDescriptionExplainsBatchFormat:
    """統合後の description が「単発でも配列で渡す」を明示する。"""

    def test_description_multiple_batch(self) -> None:
        """description に複数配布または batch の言及あり。"""
        desc = GIVE_ITEM_DEFINITION.description
        # 「複数」「まとめて」「一度」「batch」のいずれかを含む
        assert (
            "複数" in desc
            or "まとめて" in desc
            or "一度" in desc
            or "batch" in desc.lower()
            or "配列" in desc
        )

    def test_description(self) -> None:
        """LLM が単発ケースで戸惑わないよう「1 件でも配列で」を書く。"""
        desc = GIVE_ITEM_DEFINITION.description
        # 「1 件」「単発」「gives: [」のような hint を含む
        assert (
            "1 件" in desc
            or "1件" in desc
            or "単発" in desc
            or "1 つ" in desc
            or "1つ" in desc
        )

    def test_description_string(self) -> None:
        """description は静的文字列。"""
        desc = GIVE_ITEM_DEFINITION.description
        assert isinstance(desc, str)
        assert "{" not in desc
