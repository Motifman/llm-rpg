# 設計判断 / 設計思想集

本ドキュメントは、実装の **「なぜこの形になっているか」** を集約した参考資料。
新機能を追加するとき、まずここを読んで既存の哲学と衝突しないかを確認する。
日々の実験 (#356 〜 #413 等) を通じて生まれた判断を、コードコメントに散らさず
ここに集める。

新しい判断を追加する場合:
- 「**何を**」「**なぜ**」「**どうしないと壊れるか**」の 3 点セットで書く
- 個別の PR / Issue 番号を添えて trace 可能にする
- 後から「やめた」場合は削除でなく取り消し線で残し、理由を併記する

---

## 1. Prefix cache を守るため、system prompt と tool list は tick 間で不変にする

**何を**: 1 ターン目と 2 ターン目で system prompt の文字列と tool list (= 並び順 + 各 tool の JSON Schema) を **完全一致** させる。

**なぜ**:
- LLM API (OpenAI / Anthropic / litellm 経由の vLLM 等) は、prefix が一致する prompt の入力 token を **キャッシュして実質無料化** する仕組みを持つ。長い system prompt + tool definitions は普通 4-8K token あり、これがキャッシュに乗るか乗らないかで wall time / cost が桁違いになる
- LLM のターンは数百回繰り返されるので、prefix を壊した瞬間に **全 turn が cold cache** になり 1 run のレイテンシが数倍になる

**どうしないと壊れるか**:
- 「疲労 85+ のとき system prompt 末尾に『朦朧としている』を追加する」のような **動的注入** はやらない
- ツールを動的に表示/非表示にする (`if status.fatigue >= 100: tools.pop("travel_to")` 等) もやらない
- 状態依存の情報は **prompt 後半のプレイヤー状態セクション** (= 毎 turn 変わる前提のところ) に乗せる

**どこでこの判断が出てきたか**:
- 実験 #28 / #29 で `cached_tokens=0` (prefix cache hit 0%) を観測 → wall time スパイクの 1 要因
- PR β (疲労ライフサイクル) でユーザ feedback: 「システムプロンプトはなるべく変えないようにしたい」

---

## 2. 致命的に詰む状態を作らない (例: 疲労 100 でも use_item は通す)

**何を**: ゲーム内で「**取れる手段が完全にゼロ**」になる状態を構造的に避ける。
例えば疲労 100 で動けない時でも、`use_item` / `wait` / `speech` のような **回復ループに乗るためのツール** は必ず通せるようにする。

**なぜ**:
- LLM agent はランダム探索ではなく「最良の手」を 1 つ選ぶ。詰みは無限ループ (同じ tool 呼び続ける) や silent crash になりやすい
- TRPG / survival シナリオでは「**仲間に助けてもらう**」「**食料で持ち直す**」が物語の核。完全詰みは物語を殺す
- 「動けないが、座ったまま回復行動はできる」というモデルは、現実の人間にも適合する直感的な設計

**どうしないと壊れるか**:
- 疲労 100 で use_item を block すると、食料を持っていても食えずに餓死。inventory に解決手段があるのに使えない構造は LLM が困惑する
- HP 0 (DEAD) も同様: dead player に対するアクションは全部 silent にする (#363 で対処)、ただし他 player から見れば「倒れている」観測は届く

**どこでこの判断が出てきたか**:
- PR β (疲労ライフサイクル) の設計議論で「100 のとき use_item を block するか」→ ユーザ判断「絶対通す」

---

## 3. 揮発ラベル (S1 / I2 / P3) を捨て、名前 + ordinal で対象指定する

**何を**: prompt 上に `S1: 扉 → 玄関` のような tick 内で振り直される連番ラベルを出さない。代わりに `- 扉 → 玄関` の名前直書き形式で、同名衝突時のみ `#1` / `#2` で disambiguate する。

**なぜ**:
- ラベルは **揮発的**: 同じ `I2` が次 turn で別アイテムを指す
- memo / episodic memory に「`I2` を渡した」と書かれると **再構築不能** (記憶汚染)
- 名前直書きなら過去 turn のメモがそのまま意味を持つ ("玄関に移動した" は tick を跨いで読める)

**どうしないと壊れるか**:
- 第13/14 回実験のリン「閲覧室 ↔ 入口広間」bouncing がこの構造的原因 (#229 で部分対処 → PR #421 / #425 で完全対処)
- 新規 tool を作るときも `*_label` 引数を増やさず「対象の名前」を渡す設計に揃える

**どこでこの判断が出てきたか**:
- 実験 #29 OFF 分析の feedback「ラベルをやめる」 → PR #421 / #425

---

## 4. travel は「即時 return + per-agent skip」モデルにする

**何を**: `travel_to` ツールは travel state を立てて即返り、その後の world tick で 1 leg ずつ進む。移動中の player は `_can_player_act` filter で turn を skip し、到着時に再起床する。

**なぜ**:
- 旧実装は do_move 内で `advance_tick × 200` のネストループを回し、1 driver tick = 656 秒 / 134 LLM call というスパイクを生んでいた (#404)
- ネストループ中に他 player の post-tick hook が再帰的に発火し、travel が LLM 大量呼び出しのトリガーになっていた

**どうしないと壊れるか**:
- ツール内で `advance_tick` を回す設計を持ち込まない。世界時計の更新は **外側の experiment loop だけが触る** という不変条件
- 移動中の player の turn を空回りさせない (heartbeat / observation 経路で wake up しないよう `is_traveling` フィルタを通す)

**どこでこの判断が出てきたか**:
- 実験 #28 partial run の 656 秒スパイク → #405 (travel non-blocking) / #407 (per-agent idle timer)

---

## 5. silent failure を「構造」で塞ぐ (例外ハンドリングだけに頼らない)

**何を**: 致命的な状態破綻 (orphan item / 状態不整合 / 順序逆転) は、例外 catch ではなく **コードの順序や事前ガード** で塞ぐ。

**なぜ**:
- 例外で catch すると失敗が prose に出ず、LLM も気づかない (= silent)
- 順序由来の破綻は再現条件が見えにくく、trace を grep しないと原因が辿れない

**例**:
- `give_item` で receiver が満杯の場合: 事前に `is_inventory_full()` チェック → 失敗時は ItemTransferException を投げる。送り手から先に抜いてから receiver に渡そうとして失敗するパスを作らない (#400)
- `use_item` で quantity=0 になった時: `inventory.save` → `item_repository.delete` の順に固定。逆順だと delete 成功 / inv save 失敗で orphan instance が残る (#400)
- `ItemUsedEvent` を `publish_all` で必ず流す: aggregate に積んで捨てない (#400)

**どうしないと壊れるか**:
- 似たような silent failure は実走で必ず再発する。「catch して握りつぶす」は使わない
- `try/except: pass` を書きそうになったら、本当に握りつぶしていい理由 (= 親 action と独立 / fail-safe で続行が望ましい) を comment に書く

**どこでこの判断が出てきたか**:
- 実験 #28 のアイテム系 silent failure 群 → #400

---

## 6. 後方互換を過度に守らない

**何を**: 「旧 API も残しておく」「旧フラグも動くようにしておく」のような移行層を、明確な必要性がない限り作らない。

**なぜ**:
- 後方互換層はそれ自体が **継続的に維持** されるべき表面積になり、テストの組み合わせ爆発を生む
- LLM の運用 (= 自分たちで動かしているだけ) では、外部 client 互換性のような重い制約がない
- 旧経路を切り捨てる方が、コードが単純になり読み手にも実装者にも親切

**どうしないと壊れるか**:
- 大きな refactor が「片落ち」状態 (新旧両方が動く中途半端な状態) で凍結すると、後で誰も触れなくなる
- PR #409 (MAX_TICKS → MAX_WORLD_TICKS) は完全 rename にした。env レベルでは旧 `EXPERIMENT_MAX_TICKS` を 1 段だけ backstop で読むが、それ以上の互換層は作らない

**どこでこの判断が出てきたか**:
- CLAUDE.md の repo ルールにも明記 ("後方互換を過度に守らない")
- PR #404 系列の `MAX_TICKS` rename

---

## 7. heartbeat は「最低発火頻度の floor」ではなく「最大沈黙時間の ceiling」

**何を**: 全 agent を `N tick おきに必ず起こす` という旧 heartbeat ではなく、`N tick 何も起きなかったら 1 回だけ起こす` という per-agent idle timer 方式にする。

**なぜ**:
- 旧 heartbeat (5 tick おき全員起床) は、event 駆動で active な agent にまで heartbeat を届けて空回り turn を量産していた
- 1 driver tick で 4 player × ceil(20/5) = 約 20 回の不要な LLM 呼び出しが乗っていた

**どうしないと壊れるか**:
- event 駆動の起床経路 (`schedules_turn=True` 観測) が網羅されていないと、idle_timeout (デフォルト 6 tick) まで重要な変化に気づかない
- `schedules_turn` の audit は重要 (#412): HP 変化 / モンスター出現 / 発話 / アイテム overflow / 救助到達 / etc. を漏れなく `schedules_turn=True` に揃える必要がある

**どこでこの判断が出てきたか**:
- 実験 #28 wall time スパイクの分析 → #407 (per-agent idle timer) + #412 (schedules_turn audit)

---

## 8. 状態依存の表示は「プレイヤー状態セクション」に出す

**何を**: 「疲労が限界」「HP 危険域」「中毒中」など、状態に応じた情報を LLM に伝える必要がある場合、**system prompt は触らず**、毎 turn 再生成されるプレイヤー状態セクション (= snapshot を文字列に展開する箇所) で表現する。

**なぜ**:
- 設計判断 #1 (prefix cache) と直結
- プレイヤー状態セクションは元々 turn ごとに変動する前提なので、追加情報を載せても prefix cache を壊さない

**どうしないと壊れるか**:
- 状態依存ヒントを system prompt に注入すると prefix cache が完全に死ぬ
- 状態セクションが長くなりすぎると LLM が読み切らなくなる懸念はあるので、要約 / 優先度設定を併用する

**どこでこの判断が出てきたか**:
- PR β (疲労ライフサイクル) の設計議論

---

## 10. 実験 env の不正値は silent fallback せず fail-fast

**何を**: `PROMPT_SECTION_ORDER` / `SHORT_TERM_MEMORY_KIND` / `SHORT_TERM_MEMORY_SCHEDULER_MODE` / `SEMANTIC_PASSIVE_TOP_K` / 各種 bool 系 env 等の **解決層**で、未知の値が来たら warning + default に縮退 (silent fallback) ではなく **`ValueError` を投げて即停止**する。

**なぜ**:
- 短縮形や typo (例: `SHORT_TERM_MEMORY_KIND=rolling` ← 正しくは `rolling_summary`) が silent fallback されると、**実験が間違った設定で走る**
- 長 tick の実験では「数時間走らせて trace を見るまで気づけない」状態になる (PR #433 で実際に発生: Parasail A/B 実験 Run B が rolling のつもりで sliding_window だった)
- 不正値は **shell の export ミス / 別の env を混同 / Makefile 引数の typo** など。実験者が意図して入れる事はほぼ無い → 黙って受理する価値より、即時 fail させて打ち直す方が安全

**どう実装するか**:
- enum 系 (`section_order`, `memory_kind`, `scheduler_mode`): 未知文字列で `ValueError(env_name + bad_value + valid_list)`
- 数値系 (`semantic_passive_top_k`): 非整数 / 負数で `ValueError`
- bool 系 (`_parse_bool_env`): TRUTHY と FALSY 両方の明示集合を持ち、どちらにも該当しない値で `ValueError`
- **未設定 / 空文字** は意図的な「default 採用」と解釈し、引き続き default を返す (この決定は維持)

**どうしないと壊れるか**:
- 同じ実験を何度もやり直すコストが膨らむ + 結果の信用も落ちる
- typo の発見が trace を grep するまで遅れる → 設計判断のフィードバックループが鈍る

**どこでこの判断が出てきたか**:
- PR #433 で「Parasail A/B 実験 Run B は sliding_window だった」事実が `run_start` payload から判明 → PR #434 で対策

---

## 9. 速度より「LLM の判断ミス」を優先して直す

**何を**: 並列化 / 非同期化 / cache 最適化のような **wall time 改善** より、LLM が誤判断する原因を 1 つずつ潰す方を優先する。

**なぜ**:
- 並列化済 (#346 Step 1) で wall time はそれなりに改善した
- LLM の判断ミス (ITEM_NOT_CONSUMABLE / 揮発ラベル誤用 / 救助に向かわない etc.) は実走の物語そのものを壊す
- 「速いが頭が悪い」より「やや遅いが賢い」方が物語の検証に役立つ

**どうしないと壊れるか**:
- 「速いから OK」と判断ミスを放置すると、長期的に LLM 出力の信用が落ちる
- 「もっと速いモデルを使えば解決」と Inference 側に解決を委ねると、シナリオ設計のフィードバックが鈍る

**どこでこの判断が出てきたか**:
- 実験 #29 OFF 分析の feedback シリーズ (ラベル / アイテム type tag / scenario realism / batch tools / fatigue lifecycle)

---

## index (時系列)

| Decision | 採用 | 関連 PR / Issue |
|---|---|---|
| 1. Prefix cache 不変 | 2026-06-07 | (新規) PR β |
| 2. 詰み回避 (use_item は通す) | 2026-06-07 | (新規) PR β |
| 3. 揮発ラベルを捨てる | 2026-06-07 | #229 / #421 / #425 |
| 4. travel 即時 return | 2026-06-07 | #404 / #405 |
| 5. silent failure を構造で塞ぐ | 2026-06-07 | #396 / #400 |
| 6. 後方互換を過度に守らない | (継続) | CLAUDE.md / #409 |
| 7. heartbeat → idle timer | 2026-06-07 | #346 / #407 / #412 |
| 8. 状態情報は state section へ | 2026-06-07 | (新規) PR β |
| 9. LLM 判断ミス > wall time | 2026-06-07 | 実験 #29 feedback 群 |
| 10. 実験 env は fail-fast | 2026-06-07 | PR #433 / #434 |
