"""宣言に無い値を、読み込み時に落とす。

## なぜ要る

`player_attributes` は取りうる値を書ける。

```json
"trade": {"display_name": "生業", "mutable": false,
          "values": {"picker": "摘み手", "baker": "焼き手"}}
```

ところが `values` を書いても、**どこもそれを見ていなかった**。`"bakerr"` と
書き間違えても世界は起動し、その条件は**誰にも満たせないまま**残る。実行時にも
落ちない — 単に一度も成立しない。

## 「永久に無理」には 2 種類ある

**世界の誰か 1 人でも満たせるか**で分かれる。ここで落とすのは後者だけである。

| 形 | 扱い | なぜ |
|---|---|---|
| `{"trade": "baker"}` を摘み手が要求される | **正しい世界** | 焼き手なら満たせる。**満たせる人が居る** |
| `{"trade": "bakerr"}` (`values` に無い) | **落とす** | **誰も満たせない**。書き間違いしかありえない |

前者は職能の設計そのもので、`#1220` の注記 (`焼き手だけが扱える`) が担当する。
**混ぜてはいけない。** 混ぜると、次に触る人が注記の側を「落とすべき」と読む。

## 書ける値を必ず並べる

「不正です」だけでは、書いた人は次に何を書けばよいか分からない。`destination_label`
の失敗文が有効な値を列挙している形が、いままででいちばん良い失敗文だった。
**同じ形を起動時のエラーにも当てる。**
"""

from __future__ import annotations

from typing import Any, Mapping

from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.infrastructure.scenario.load_error import ScenarioLoadError


def reject_values_the_world_does_not_have(
    state: Mapping[str, Any],
    specs: PlayerAttributeSpecs,
    *,
    what: str,
) -> None:
    """宣言に無い値を書いている属性があれば落とす。

    ``what`` は「何を書いているか」(``initial_state`` / ``state_updates`` /
    ``required_state``)。どこで書かれているかは `declaring()` が足す。

    **``values`` を書いていない属性は素通りする。** 数値や時刻のように列挙の
    無い属性があるので、宣言していないことを誤りにしない。
    """
    for key, value in (state or {}).items():
        spec = specs.spec_of(str(key))
        # `allows` が「列挙が無ければ何でも取りうる」を既に見ている。ここで
        # `not spec.values` を重ねて書くと、**変異させても何も変わらない条件**
        # ができる (実際に変異が生き残って気付いた)。
        if spec is None or spec.allows(value):
            continue
        raise ScenarioLoadError(
            f"{what} が、属性 '{key}' ({spec.display_name}) に宣言されていない値 "
            f"{value!r} を使っています。この値は世界に存在しないので、"
            f"条件なら誰にも満たせず、効果なら誰も到達できない状態を作ります。"
            f"書ける値: {', '.join(spec.values)}"
        )


__all__ = ["reject_values_the_world_does_not_have"]
