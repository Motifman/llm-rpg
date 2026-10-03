# LLM のモデルと provider の選び方

OpenRouter 経由で run を回すときに、モデルの版と provider (同じモデルを配信する
事業者) をどう選ぶかをまとめる。

provider の対応状況・単価・量子化は、予告なく変わる。2026-09-23 には、8 月まで
使えていた deepseek-v4-flash 0423 版 × Baidu が、`tool_choice=required` を
受け付けなくなっていた。**この文書に書くのは判断の条件と確かめ方で、ある時点の
一覧は末尾の記録に日付つきで残す。** 記録を今の状態とみなして選ばないこと。

## 条件

上から順に見る。必須を 1 つでも満たさない組み合わせは使わない。

| # | 条件 | 区分 | なぜ |
|---|---|---|---|
| 1 | `tool_choice=required` が実呼び出しで通る | 必須 | 主ターンは required で呼ぶ。通らない provider は毎回 404 になり、run が止まる。`auto` へ下げると、ツールを返さない応答でエージェントが 1 回の起動を黙って失う (設計判断 #39・#96) |
| 2 | 版を固定したモデル ID を使う | 必須 | `deepseek/deepseek-v4-flash` (0423 版) と `deepseek/deepseek-v4-flash-0731` は別物。`~deepseek/deepseek-v4-flash-latest` のような別名は中身が黙って替わり、過去 run と比べられなくなる (#39) |
| 3 | 共有プールの 429 が続かない | 必須 | `upstream_provider_shared_pool` の 429 は OpenRouter 利用者全体の枠の枯渇で、こちらの並列度を下げても直らない。時間帯で全滅することがある |
| 4 | 応答が API タイムアウト (90 秒) に収まる | 必須 | 超えた呼び出しは失敗として扱われ、その tick の行動を失う |
| 5 | 単価 (入力・キャッシュ読み込み・出力) | 比較 | 1 呼び出しあたり入力は約 9,000 トークン、出力は数百トークンなので、入力とキャッシュ読み込みの単価が費用を決める。同じモデルでも provider で 5 倍違うことがあり、run の途中で値上がりした例もある |
| 6 | プレフィックスキャッシュが効く | 比較 | キャッシュの保持時間は provider ごとに違う。1 tick が長くなり呼び出しの間隔が空くと、キャッシュ率が下がる (Venice では、呼び出し間隔が 15 秒未満なら 0.77、60 秒を超えると 0) |
| 7 | 量子化 (fp8 / fp4 / bf16 など) | 比較 | fp4 はモデル品質を落とすことがある。ただし候補から外す条件にはせず、選んだ provider の量子化を profile の description と run の結果に残す。`quantization` が `unknown` の provider も同じ扱いにする |

補足:

- `supported_parameters` に `tool_choice` があっても、`required` が通るとは限らない。provider の宣言であって、値ごとの動作保証ではない。条件 1 は必ず実呼び出しで見る
- DeepSeek の思考 (thinking) と `required` は両立しないことがある。思考を入れる run では、条件 1 を思考ありの設定で確かめる (#96)
- provider を固定しても、要求した版が答えるとは限らない。provider 一覧に無い組み合わせを指定すると、404 にならず別のモデルが答えることがある。呼び出しが通ったかだけでなく、応答の `model` が要求した ID と一致するかを見る
- 思考トークンは出力トークンの上限に数えられる。上限を小さくしたプローブでは、思考で上限に達してツールが返らないことがある。プローブの `--max-tokens` は 200 以上にする

## 確かめ方

新しい profile を作るとき、または前回の run から日が空いたときに、使う直前に行う。

1. **版を確かめる**: `--list-models` で同じ系統の版を全部出し、日付つきの ID を選ぶ

   ```bash
   uv run python scripts/openrouter_ping.py --list-models --model deepseek-v4
   ```

2. **provider の一覧を見る**: 量子化・単価・直近の稼働率を見て候補を絞る (条件 5・7)

   ```bash
   uv run python scripts/openrouter_ping.py --list-providers --model openrouter/deepseek/deepseek-v4-flash-0731
   ```

3. **required で直列に叩く**: run と同じ `tool_choice=required` で、5 秒おきに 12 回 (条件 1・3・4)。全部通り、出力の `model` が要求した ID と一致することを見る。run を回している最中は、同じ provider の枠を run と取り合うので、プローブは run の前に行う

   ```bash
   uv run python scripts/openrouter_ping.py --model openrouter/deepseek/deepseek-v4-flash-0731 \
       --provider DeepInfra --tools-required --repeat 12 --interval 5 \
       --max-tokens 200 --prompt "ping ツールを呼んで"
   ```

4. **1 tick だけ回す**: profile を作り、`MAX_WORLD_TICKS=1` で回す。`prompt_dataset/calls.jsonl` の `metrics` で、全呼び出しの成功・応答時間・`cached_tokens`・`cost_usd` を見る (条件 4・5・6)

5. **profile の description に残す**: 選んだ理由・確かめた日付・実測値を書く。provider を替えたら、既存 profile は書き換えずに新しい profile を足す (#39。既存 profile は過去の実験条件の記録)

## 記録

ある時点での状況。**今の状態ではない。** 使う前に上の手順で確かめ直すこと。

### 2026-09-23 deepseek-v4-flash

- **0423 版 (`deepseek/deepseek-v4-flash`)**
  - `required` を付けると、Baidu / StreamLake / GMICloud / Venice / DigitalOcean / SiliconFlow / Alibaba / Novita / Parasail / Mancer 2 が OpenRouter のツール互換性の判定で外れる。8 月の Baidu の run は同じ版で通っていた
  - DeepSeek 直営と Cloudflare は、0423 版の provider 一覧から消えた
  - `required` で通ったのは DeepInfra (fp8、入力 0.09 ドル / MTok)
  - `station_drill` / `station_drill_jev` など、0423 版を指す既存 profile はこのままでは動かない
- **0731 版 (`deepseek/deepseek-v4-flash-0731`)**
  - provider は 30 件ある
  - Baidu (fp8、入力 0.44 / キャッシュ 0.014 / 出力 1.32 ドル / MTok): `required` で 12/12 通過。0423 版の約 5 倍の単価
  - DeepInfra (fp8、入力 0.06 / キャッシュ 0.015 / 出力 0.18 ドル / MTok): `required` で通過。設計判断 #39 を書いた時点では fp4 だったが、fp8 に変わっていた
  - `station_drill_jev_deepinfra_0731` profile で使っている。run `station_drill_deepseek0731_deepinfra_001` (37 tick、8 並列) の実測は次のとおり
    - 主ターン 161 回のうち 7 回が失敗し、その手番の行動を失った。共有プールの 429 が 3 回の再試行でも通らなかったのが 4 回、API の失敗が 3 回
    - 応答時間の中央値は 16 秒、90 パーセンタイルは 35 秒、最大は 97 秒
    - キャッシュ率は 0.60、主ターンの費用は 0.07 ドル

### 2026-09-27 量子化の扱いと、0423 版 × DeepInfra

- 量子化を必須の条件から外し、比較の条件に移した。fp4 でも候補から外さない
- gemma-4-31b × Venice は fp4 だった。過去の run の要求 20 回を `required` のまま送り直し、20 回とも通った
- deepseek-v4-flash 0423 版の DeepSeek 直営は、引き続き provider 一覧に無い。この組み合わせを固定した 7 月の run の要求をそのまま送り直すと `NotFoundError` になる
- 0423 版 × DeepInfra (fp8、入力 0.09 / キャッシュ 0.018 / 出力 0.18 ドル / MTok) で、過去の run の要求 40 回を `required` のまま直列に送り直し、40 回とも通った

### 2026-10-03 DeepSeek 直営の差し替え

- DeepSeek 直営は、0731 版の provider 一覧 (28 件) に無い。Cloudflare は残っている
- それでも `only: ["DeepSeek"]` で 0731 版を `required` 付きで呼ぶと通る。応答の `model` は `deepseek/deepseek-v4.1-flash` だった。同じ要求を Cloudflare に固定すると、`model` は `deepseek/deepseek-v4-flash-0731` だった
- 0423 版 (`deepseek/deepseek-v4-flash`) を DeepSeek 直営に固定しても、応答の `model` は `deepseek/deepseek-v4.1-flash` だった。2026-09-27 の時点では `NotFoundError` で止まっていた。`OPENROUTER_PROVIDER` が `DeepSeek` で 0423 版を指す profile (`belief_goal_full` / `ablation_base` など 8 件) は、止まらずに別のモデルで動く
