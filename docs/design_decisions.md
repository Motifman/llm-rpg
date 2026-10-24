# 設計判断 / 設計思想集

本ドキュメントは、実装の **「なぜこの形になっているか」** を集約した参考資料。
新機能を追加するとき、まずここを読んで既存の哲学と衝突しないかを確認する。
日々の実験 (#356 〜 #413 等) を通じて生まれた判断を、コードコメントに散らさず
ここに集める。

新しい判断を追加する場合:
- 「**何を**」「**なぜ**」「**どうしないと壊れるか**」の 3 点セットで書く
- 個別の PR / Issue 番号を添えて trace 可能にする
- 後から「やめた」場合は削除でなく取り消し線で残し、理由を併記する
- 見出しには通し番号ではなく、判断が生まれた Issue の番号から作った ID を付ける (`## D1448. 〜`)。同じ Issue から 2 つ以上足すときは `D1448-2`、`D1448-3` と続ける。並行する PR が同じ次の番号を取り合わないようにするため。Issue が無い判断は、先に Issue を立てる
- 本文や他の文書から参照するときは `design_decisions D1448` と書く。`#1448` と書くと GitHub が Issue へのリンクにしてしまう
- 238 までの通し番号の判断は、そのままの番号で残す。既存の参照 (`design_decisions 234` など) は書き換えない

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

## 4. travel / wait は「ツール内で tick を進めない」モデルにする

**何を**:
- `travel_to` ツールは travel state を立てて即返り、その後の world tick で 1 leg ずつ進む。移動中の player は `_can_player_act` filter で turn を skip し、到着時に再起床する
- `spot_graph_wait` ツールも同様に「今ターンは行動を控える」という意思決定だけを記録し、`advance_tick` は呼ばない (#471)

**なぜ**:
- 旧 `do_move` は内部で `advance_tick × 200` のネストループを回し、1 driver tick = 656 秒 / 134 LLM call というスパイクを生んでいた (#404)
- 旧 `do_wait` も nested `advance_tick` を 1 回呼んでおり、`_run_post_tick_hooks` → `run_scheduled_turns` → 他プレイヤー LLM ターン → `spot_graph_wait` → `do_wait` … の再帰カスケードを起こしていた。L run で 1 driver iteration 内に world tick が +104 ジャンプし、`MAX_WORLD_TICKS=140` を黙ってバイパス (#471)
- driver loop の `while current_tick < max_world_ticks` ガードは **iteration 先頭でしか効かない**ため、ネストカスケード中は上限を守れない

**どうしないと壊れるか**:
- ツール / handler / observation hook の中で `advance_tick` / `simulation.tick` を呼ぶ設計を持ち込まない。世界時計の更新は **外側の experiment loop / driver thread だけが触る** という不変条件
- wait は「skip ターン」記録だけにする。「tick を 1 進めるショートカット」として使う設計にすると #471 と同じ再帰カスケードが復活する
- 移動中の player の turn を空回りさせない (heartbeat / observation 経路で wake up しないよう `is_traveling` フィルタを通す)

**どこでこの判断が出てきたか**:
- 実験 #28 partial run の 656 秒スパイク → #404 / #405 (travel non-blocking) / #407 (per-agent idle timer)
- 実験 #468 L run の 1878 秒スパイク / +104 tick ジャンプ → #471 (do_wait nested advance 除去)

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
- `schedules_turn` の audit は重要 (#412): HP 変化 / モンスター出現 / 発話 / アイテム overflow / 救助到達 / アイテムの受け渡し (drop / pickup / give) / etc. を漏れなく `schedules_turn=True` に揃える必要がある
- アイテム移動 3 種は初回 audit から漏れていた。v4 第 3 回 run で「`say_inline` を伴う受け渡しは発話観測が同席者を起こすので回るが、黙って渡すと相手が idle_timeout まで気づかない」と判明して追加した。audit 表の正本は `tests/application/observation/test_schedules_turn_audit.py` の docstring

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

**何を**: `SHORT_TERM_MEMORY_KIND` / `SEMANTIC_PASSIVE_TOP_K` / 各種 bool 系 env 等の **解決層**で、未知の値が来たら warning + default に縮退 (silent fallback) ではなく **`ValueError` を投げて即停止**する。

**なぜ**:
- 短縮形や typo (例: `SHORT_TERM_MEMORY_KIND=rolling` ← 正しくは `rolling_summary`) が silent fallback されると、**実験が間違った設定で走る**
- 長 tick の実験では「数時間走らせて trace を見るまで気づけない」状態になる (PR #433 で実際に発生: Parasail A/B 実験 Run B が rolling のつもりで sliding_window だった)
- 不正値は **shell の export ミス / 別の env を混同 / Makefile 引数の typo** など。実験者が意図して入れる事はほぼ無い → 黙って受理する価値より、即時 fail させて打ち直す方が安全

**どう実装するか**:
- enum 系 (`memory_kind` など。`section_order` と `scheduler_mode` は #1631 で消した): 未知文字列で `ValueError(env_name + bad_value + valid_list)`
- 数値系 (`semantic_passive_top_k`): 非整数 / 負数で `ValueError`
- bool 系 (`_parse_bool_env`): TRUTHY と FALSY 両方の明示集合を持ち、どちらにも該当しない値で `ValueError`
- **未設定 / 空文字** は意図的な「default 採用」と解釈し、引き続き default を返す (この決定は維持)

**どうしないと壊れるか**:
- 同じ実験を何度もやり直すコストが膨らむ + 結果の信用も落ちる
- typo の発見が trace を grep するまで遅れる → 設計判断のフィードバックループが鈍る

**どこでこの判断が出てきたか**:
- PR #433 で「Parasail A/B 実験 Run B は sliding_window だった」事実が `run_start` payload から判明 → PR #434 で対策

`PROMPT_SECTION_ORDER` は、どの profile も `stable_to_volatile` だったので、記憶ではない設定の片付け (#1631) の #1754 でキーごと消した。
`SHORT_TERM_MEMORY_SCHEDULER_MODE` も #1759 でキーごと消した。ThreadPool の scheduler (`ThreadPoolShortTermMemoryScheduler`) を設定から組んでいたのは、2026-06-07 (a9eded93b) から 2026-06-21 (2bfd0d3a1) まで full wiring (`wiring/__init__.py`) だけだった。実験と本番が通る escape の経路 (いまの world_runtime) は一度も組んでおらず、`thread_pool` と記録された run も、短期記憶の要約は同期 (inline) で作っていた。非同期の部品は、非同期化を作り直すときのために残す。

---

## 11. 設定は単一 DTO で集約、構築は「全部揃ってから 1 回 build」

**何を**: env / scenario JSON / 引数由来の設定は `ResolvedLlmRuntimeConfig` のような **1 つの frozen DTO** に集約してから wiring に渡す。サービスは **「依存が揃ってから ctor で全部注入」** で構築し、setter で後注入する経路は作らない。

**なぜ**:
- 「env を 2 箇所で別解釈する」silent failure が大量発生した (PR #439 / PR #446: section_order や memory_kind が trace に書かれた値と実体でズレる)
- 「setter で後注入する Future work が忘れられる」silent failure も発生した (PR #444: `set_summary_services` setter は作ったが呼び出し側 wiring が未実装で 1 ヶ月放置 → 実機実験で L4/L5 が全件 template fallback)
- 「`Optional[X] = None` + 後注入」は呼び忘れを型エラーに昇格できない設計上の弱点

**どう実装するか**:
- env を読むのは `ResolvedLlmRuntimeConfig.from_env()` の 1 箇所だけ。entrypoint で 1 度だけ呼び、cfg を引数で渡し回す
- cfg は frozen dataclass。構築後の改変を封じる
- `to_trace_dict()` で trace 用 dict を出すとき API key は `***` にマスク
- 不正値は `ValueError` で fail-fast (= 設計判断 10 と併用)
- サービス構築は `_build_*(cfg, *args)` 形式で、依存物 (llm_client / persona_resolver) を ctor で全部受け取る
- setter は禁止ではないが、Optional dependency に対して使ったら **同時に「呼ばないと動かない場面」を構造的に作らない**こと

**どうしないと壊れるか**:
- 2 箇所目の env 解釈が必ずいつか追加される → silent failure 再発
- setter の呼び忘れが型チェックや CI で捕まらない → 実機実験で初めて発覚
- 「動いてるように見える別モード」が増える

**どこでこの判断が出てきたか**:
- PR #439 / #441 / #444 / #446 の 4 連続 silent failure
- architect レビュー (PR #444 後) → リファクタリング 6 PR (#446 / #447 / #448 / #449 / #450 / #451) で構造的対処

---

## 12. Future work は xfail-strict pytest で可視化する

**何を**: 「次の PR で対応する」という TODO を、**コメントではなく `@pytest.mark.xfail(strict=True, reason="PR #N: ...")`** で表現する。

**なぜ**:
- PR #439 で `set_summary_services` setter を作ったが「後で wiring が呼ぶ」が忘れられ PR #444 まで放置された
- リポジトリ内に散在する `# TODO` / `# 後で` / `# 仮` コメントは grep しないと発見できず、レビュー時にも見落とされる
- pytest なら CI で必ず実行され、強い可視性がある

**どう実装するか**:
- 「将来の PR で動くべきテスト」を `xfail(strict=True)` で書く。strict=True なので、対応した瞬間に "expected fail but passed" で CI が落ち、修正完了を強制 unmark させる
- reason に PR 番号 / target PR を必ず明記
- 例 (架空):
  ```python
  @pytest.mark.xfail(strict=True, reason="PR #439: setter is wired but no caller yet (target: PR #444)")
  def test_rolling_summary_llm_path_is_actually_wired_in_production():
      ...
  ```

**どうしないと壊れるか**:
- `# 後で` コメントが恒久放置される
- レビュー時に「ここ後で誰かが直すから OK」と通された scope split が忘れられる

**どこでこの判断が出てきたか**:
- PR #439 → PR #444 の 1 ヶ月放置事案
- architect レビュー (PR #444 後)

---

## 13. memory caller の Being 未解決時挙動は「役割」で分岐する

**何を**: Being / Resolver / WorldId のいずれかが未注入 / 未 provision で memory store の being_id 経路を引けないとき、caller の挙動は **役割によって 3 種類** を使い分ける。

| caller の役割 | 未解決時の挙動 | 理由 |
|---|---|---|
| LLM-visible tool (例: `SemanticMemorySearchToolExecutor`) | **fail-fast** (`INVALID_STATE` で `success=False`) | 「該当 0 件」と「内部状態未準備」を LLM が区別できないと、誤った判断につながる |
| turn の副作用 (例: `EpisodicSemanticClusterPromotionService`) | **silent no-op** | promotion 失敗で turn を止めない。次回 turn で再試行できる |
| prompt 強化 (例: `SemanticPassiveRecallService`) | **graceful empty list** | side feature なので turn を止めない。 wiring 漏れは別途 wiring level の test で塞ぐ責務 |

**なぜ**:
- すべて fail-fast にすると prompt 系の side feature で turn が落ちる
- すべて silent にすると LLM が「該当なし」と誤認して間違った行動を取る
- すべて graceful にすると wiring 漏れが本番で見えなくなる
- 「caller がどう失敗してほしいか」は本質的に **caller 側の関心** なので Repository 側でなく caller で判定する

**どうしないと壊れるか**:
- 一律 silent: LLM-visible tool で「該当なし」と「内部 bug」が判別不能になり、誤判断が trace から追えない
- 一律 fail-fast: passive recall や promotion の小さな失敗で turn 全体が止まる

**残るリスク**: graceful empty (passive recall) は wiring 漏れを隠す可能性がある。これは wiring-level test (= Resolver+WorldId が必ず注入される) で補完する責務とし、本 caller では「prompt が痩せるだけ」の縮退に留める。

**どこでこの判断が出てきたか**:
- PR #491 / #492 (Phase 3 Step 3b-2 / 3b-3 = semantic legacy 撤去)
- code-reviewer (MEDIUM-1) でも「Optional 設計は wiring 漏れを隠しうる」と指摘あり、トレードオフ込みで採用

---

## 14. promotion_frontier は Phase 3 Step 3c の scope 外 (= player_id keyed のまま)

**何を**: ``EpisodicPromotionFrontier`` は ``memory_link`` / ``recall_buffer`` /
``reinterpretation_journal`` の 3 連携 store とは別レイヤーで、現状は
player_id keyed のまま残す。``EpisodicMemoryLinkApplicationService`` から frontier
に追記するとき、Resolver で BeingId → player_id を逆引きする
``_player_id_for(being_id)`` helper を経由する。

**なぜ**:
- frontier は「次回 promotion で対象にすべき episode_id の集合」を保持する
  小さな in-memory ストア。run 跨ぎ identity を保つ必要が無く、Being 化の
  優先度が低い
- Step 3c は 3 store の being_id keyed 移行に集中するスコープで、frontier
  まで含めると変更範囲が膨らみすぎる
- 「caller 入口で being_id を 1 度だけ解決する」 resolve-once パターンを
  維持するには、frontier への追記時のみ player_id が必要 → 逆引き helper で
  橋渡しする方が、frontier 自体を Being 化するより安く済む

**どうしないと壊れるか**:
- frontier ごと一気に Being 化しようとすると、関連 service (
  ``EpisodicSemanticClusterPromotionService.drain`` / ``add`` /
  ``EpisodicMemoryLinkApplicationService.note_promotion_frontier_episodes``) を
  すべて同時に書き換える羽目になり、PR が肥大化してレビュー困難になる
- 逆引き helper を撤去し忘れると「Resolver の余分な lookup が turn ごとに
  走る」 dead code が残る

**どこでこの判断が出てきたか**:
- PR #495 (Phase 3 Step 3c-3) のレビュー指摘 MEDIUM-2
- 後続 Phase で frontier を being_id 化したら ``_player_id_for`` helper は
  撤去する

**その後**: 昇格フロンティア (`EpisodicPromotionFrontier`) は、クラスタ昇格と一緒に記憶の部品の撤去 (#1631) の #1792 で消した。

---

## 15. BeingSnapshot v2 は memory payload を「オペーク JSON」として持つ

**何を**: BeingSnapshot に memory payload を載せるとき、各 memory context
(memo / semantic / memory_link / recall_buffer / reinterpretation_journal /
episodic_episode) の VO や aggregate を直接フィールド化せず、`memory_payload_json:
str | None` という **オペーク な JSON 文字列** として保持する。JSON の内訳
schema は application 層の `BeingMemorySnapshotService` (Phase 4-2) が版管理
する。

**なぜ**:
- `domain/being/` から各 memory context の VO へ依存すると、本来独立すべき
  bounded context 間に逆方向の import が走る (= snapshot のために being が
  全 memory 文脈を知る必要が出る)
- memory store の内部 schema は将来も増減 / 改変が見込まれる (現状でも 5
  store ある)。VO field として固定すると BeingSnapshot version が memory
  schema の変更ごとに上がってしまい、Being 集約 root と memory の責務が
  混ざる
- オペーク JSON なら「Being 集約 root の不変条件」と「memory schema の版
  管理」を別軸で進化させられる (= 関心の分離)

**どうしないと壊れるか**:
- snapshot を VO 直入れにすると、新しい memory context が増えるたびに
  domain/being 配下の import 行と snapshot_version がドミノ式に動く
- 逆向き import が増えると将来の context 分離 (例: memory パッケージ独立化)
  が困難になる
- v1 (memory なし) と v2 (memory あり) を別 schema で扱うことで、Phase 2 で
  保存済みの v1 snapshot を後方互換で読み続けられる (= 既存 SQLite 行を
  捨てずに済む)

**どこでこの判断が出てきたか**:
- Phase 4 Step 4-1 着手時 (= 本 PR)
- 既存 `BeingSnapshot` docstring の「(b) 後で payload field を増やす」方針
  を具体化する形

**その後**: memory payload の `recall_buffer_pending` / `reinterpretation_journal` は、再解釈と一緒に Issue #1631 で消した。消す前の snapshot も読める (restore は足りないキーだけを拒む)。

---

## 21. world snapshot は scenario 一致を hard-error で要求する (= cross-scenario load は不可)

**何を**: ``WorldStateSnapshot`` の ``source_scenario`` が現 scenario と
異なる場合、``restore`` で ``WorldStateScenarioMismatchError`` を投げて
**fail-fast** する。memory snapshot の cross-scenario transfer (warning のみ)
とは **正反対の方針**。

**なぜ**:
- world state は scenario と密結合 (= ``spot_id`` / ``item_spec`` /
  ``scenario_events`` がすべて scenario 定義に依存)。別 scenario に load
  しても spot_id が存在しない等の壊れ方をする
- memory はキャラクターの「経験」なので scenario 跨ぎが意味を持つ (= 同じ
  キャラを別世界に転送)。world state は逆に「世界そのもの」なので、
  別世界の状態を持ち込むのは矛盾
- 両者が **別ファイル** (``being_*.json`` と ``world.json``) に分かれて
  いることで、cross-scenario use case は「Being snapshot のみコピー、
  world.json は転送先のものを別途用意」という運用で実現できる

**どうしないと壊れるか**:
- world snapshot を warning のみで通すと、別 scenario の world state を
  load した後 advance_tick で「存在しない spot_id を踏む」等の見えにくい
  エラーを引き起こす
- memory を hard-error にすると user の「同じキャラを別世界に転送する」
  use case (= 設計判断 #19 で許容済) が壊れる

**どこでこの判断が出てきたか**:
- Phase 9-1 着手時 (= 本 PR)、user との議論で「world は scenario 一致
  fail-fast」を確認

---

## 23. monster / quest codec は Phase 9-5 では未実装 (= 実需要待ち)

**何を**: ``world_subsystems/`` に ``MonsterAggregateSubsystemCodec`` /
``QuestProgressSubsystemCodec`` は存在しない。``MonsterAggregate`` は HP /
位置 / aggro / pursuit_state 等 15+ field の deep nested aggregate で、quest
も同様の構造を持つ。書けば書ける (Phase 9-3b の戦略 C パターン適用可能) が、
**現在 resume が必要とされている scenario (decay_demo / survival_island_v2)
が monster combat / quest を core mechanic にしていない** ため、未実装で
defer する。

**なぜ**:
- 必要のない codec を書くと「scenario JSON は変えてないのに codec の static
  metadata 部分が肥大化」する負債が生まれる
- monster / quest を使う scenario が登場した時に、その scenario の実需要に
  合わせて codec を書く方が schema が現実に即する
- Phase 9 の本来のゴール (= make experiment で resume が機能する) は 21
  subsystem で達成済

**どうしないと壊れるか**:
- 「将来必要かも」で全 aggregate に codec を書くと test と本体の維持コスト
  が累積する (= YAGNI 違反)
- 一方で「monster / quest を使う scenario で snapshot を取る」と、Phase 9-1
  設計判断 #22 により未登録 subsystem は forward-compat で skip され、resume
  時に monster/quest だけ scenario 初期状態に戻る (= 既知の制限として明示)

**どこでこの判断が出てきたか**:
- Phase 9-5 着手時 (= 本 PR)
- code-reviewer subagent の指摘 (= 「実需要待ちは妥当だが docs に明記すべき」)
- monster / quest を使う scenario が登場したら ``world_subsystems/`` に
  codec 追加 + ``_default_world_subsystem_codecs()`` に 1 行追加するだけ

---

## 22. world snapshot は subsystem ごとに codec を持ち、登録外は forward-compat で skip

**何を**: ``WorldStateSnapshotService`` は ``WorldSubsystemCodec`` を複数
登録できる構造にし、各 codec は独立して ``capture`` / ``restore`` を担当。
JSON 内 ``subsystems`` dict の各 key (= ``player_status`` / ``spot_interior``
等) が codec の ``subsystem_key`` と紐づく。

**登録外 subsystem は ``info`` ログを残して skip する** (= 例外を投げない)。

**なぜ**:
- world state は多くの独立した subsystem (player / spot / weather /
  monster / ...) の集合体で、scenario によって使う subsystem が異なる
- Phase 9-2 以降で 1 subsystem ずつ追加していく長期計画。新 subsystem が
  入る前の旧 snapshot を新 code で load できるよう、後方互換を保つ
- 逆に「新 snapshot を旧 code で load」(= 旧 code には codec 未登録) で
  fail-fast すると、forward 互換が壊れて運用が硬直する
- 各 subsystem の ``schema_version`` は codec 自身が管理 (= 中央集権でなく
  分散)。``WorldStateSnapshot`` 自体の ``schema_version`` は「subsystems
  dict の構造形式」の version だけを表す

**どうしないと壊れるか**:
- 「新 snapshot を旧 code で読む」が hard-error だと、Phase 9-2 が
  リリースされるまで Phase 9-3 以降の snapshot が使えなくなる
- 「subsystem を 1 つの hard-coded list で管理」する案だと、新 subsystem
  追加のたびに既存 code を変える必要がある (= 結合度が上がる)

**どこでこの判断が出てきたか**:
- Phase 9-1 着手時 (= 本 PR)
- 既存 ``BeingSnapshotCodec.SUPPORTED_VERSIONS`` の単純な version 集合と
  違い、world は **2 階層** (snapshot 自体の version + subsystem ごとの
  内部 version) になるので、別アプローチが必要だった

---

## 20. snapshot の schema 進化は (a) 厳格モード — 未サポート version は load 失敗

**何を**: ``BeingSnapshot.snapshot_version`` および ``memory_payload_json``
の ``schema_version`` が現行 supported 集合に含まれない場合、**load 経路で
fail-fast で例外を投げる**。``BeingSnapshotCodec.SUPPORTED_VERSIONS`` /
``SUPPORTED_PAYLOAD_SCHEMA_VERSIONS`` をシングルソース。

``RestoreBeingSnapshotFromFileUseCase.execute`` は ``repo.save_snapshot``
の前に明示的に version をチェックする (= 部分状態を repo に残さない)。

**なぜ**:
- run 途中再開の想定 use case は「同じ code バージョン同士で save / load」。
  schema が変わるほど離れた run を救う必要性は低い
- migration ルートを書くと「v1→v2 で意味の変質」が silent に起きうる
  (= 旧 file の値が新 schema で別の意味になる)。データを救うより data
  integrity を優先する
- 「(c) best-effort」(= 未知 field 無視 + 欠落 default 補完) は柔軟だが、
  「snapshot は完全な再現を保証する」設計判断 (= all-or-nothing #15) に反する

**どうしないと壊れるか**:
- v1 のまま新 code で load → ``snapshot_version=1`` を ``Codec.SUPPORTED_VERSIONS
  = {1, 2}`` のままにしておけば読める。互換性のために旧 version も
  ``SUPPORTED`` に **明示的に残す**。これは方針 (a) 厳格 と矛盾しない
  (= unsupported なら fail-fast、supported なら通る)
- 「migration が必要になったら」: ``SUPPORTED_VERSIONS`` を変えずに新 codec
  クラス (``BeingSnapshotCodecV3`` 等) を追加する案を検討。本 PR scope 外

**どこでこの判断が出てきたか**:
- Phase 8 着手時 (= 本 PR)、user が「一旦 (a) で行こう」と明示

---

## 19. snapshot ファイルは scenario 名メタデータを持ち、別シナリオ転送は warning だけで許容する

**何を**: snapshot JSON の root に ``_metadata`` ブロックを追加し、
``source_scenario`` (= 取得時のシナリオ名) と ``captured_at`` (= UTC ISO 8601)
を埋め込む。restore 時に現 scenario と ``source_scenario`` が異なる場合は
warning + trace event (``snapshot_load`` の payload に
``cross_scenario_transfers``) で記録するが、**エラーにはしない**。

**なぜ**:
- 「同じキャラクターを別シナリオに転送して前の memory を引き継ぐ」use case
  が将来ありうる (= forest_world でやり遂げた agent を desert_world に
  送り込んで挙動を見る、等)
- ただし「うっかり別シナリオに load して気付かない」事態は避けたい。
  warning + trace event で **意図せぬ転送は気付ける** が、意図した転送は
  そのまま走らせる、というバランス
- BeingSnapshot VO 本体は触らない (= 「VO は primitive-only」の設計判断
  #15 と整合)。メタデータは file gateway 層で独立に管理する

**どうしないと壊れるか**:
- 旧 snapshot ファイル (``_metadata`` キー無し) を後方互換で読めなくなる
  → ``data.get("_metadata")`` で ``None`` fallback。古い file も読める
- mismatch を hard error にすると cross-transfer use case が実装できない
- mismatch を silent に通すと、誤 load を発見できない

**どこでこの判断が出てきたか**:
- Phase 7 着手時 (= 本 PR)、user が「同じキャラを別世界に転送したい」と
  明示的に意図を示したこと

---

## 17. experiment runner の snapshot は escape_game runtime の限定 store だけを拾う

**何を**: ``scripts/run_scenario_experiment.py`` の Phase 6 統合では、
``_wiring_stub_from_escape_runtime`` が ``EscapeGameRuntime`` の private
attribute から **拾える分だけ** store を集めて
``ExperimentSnapshotSession`` に渡す。escape_game runtime には semantic /
memory_link / recall_buffer / reinterpretation_journal の 4 store がそもそも
存在しないため、これらは ``None`` で渡され、session 側で空 in-memory store
に fallback される。

**なぜ**:
- escape_game runtime は ``EpisodicStack`` (memo + episode のみ) を使う
  構成で、semantic / memory_link 等の高度 memory pipeline は
  ``create_llm_agent_wiring`` 経路でしか組まれない
- ここで「足りない store を後付けで配線する」と既存実験の挙動を変えてしまう
  (= 既存 trace との比較ができなくなる)
- 「snapshot に乗らない情報は空 array でも整合性が取れる」のが Phase 4-2b
  の JSON schema 設計の素敵な性質。fallback で問題が起きない

**どうしないと壊れるか**:
- 強制配線を入れると prompt 構築 / observation pipeline に副作用が混じる
- 「拾えない store → silent に snapshot off」だと、後で気付かれず復元に
  失敗する。info ログで fallback 使用を明示する (= silent failure を構造で
  防ぐ #5 と整合)

**どこでこの判断が出てきたか**:
- Phase 6 着手時 (= 本 PR)
- 将来 escape_game runtime に semantic stores を入れたら、wiring stub の
  attribute lookup を増やすだけで済む

---

## 18. snapshot save は SIGINT を flag 化して run 終了経路に合流させる

**何を**: ``run_scenario_experiment.py`` で ``--snapshot-save-dir`` を指定した
ときだけ SIGINT (Ctrl+C) を ``_interrupted = True`` フラグ立てに変える。
``KeyboardInterrupt`` を直接 raise させず、main loop が次の iteration で
正常に break する。break 後の通常終了経路 (= snapshot save + runtime.shutdown)
を必ず通すため。

**なぜ**:
- ``runtime.advance_tick()`` の中に LLM 呼び出し / async scheduler / 観測
  pipeline が絡んでいる。``KeyboardInterrupt`` が突然 raise されると
  partial state (= 観測が途中で止まる、scheduler が drain されない) で
  snapshot を取るリスクがある
- flag 化すれば「現 iteration の advance_tick() が綺麗に終わってから break」
  になる。snapshot は **整合性の取れた状態** から取れる
- ``--snapshot-save-dir`` 未指定なら SIGINT ハンドラを触らない (= 既存挙動
  完全互換)。snapshot を使わない実験では Ctrl+C は引き続き
  ``KeyboardInterrupt`` を即時 raise する

**どうしないと壊れるか**:
- グローバルに SIGINT を flag 化すると、snapshot を使わない既存実験の
  Ctrl+C の即時性が失われる (= ユーザーが Ctrl+C を 2 回押す習慣に行き着く)
- 直接 ``except KeyboardInterrupt`` で受けると、advance_tick の途中で止まる
  ので scheduler の drain が呼ばれず ``"recorder is already closed"``
  RuntimeError が後追いで出る (= 第21回実験の既知 silent failure と同型)

**どこでこの判断が出てきたか**:
- Phase 6 着手時 (= 本 PR)、user が「実験後にエラーが出られると困る」と
  明示的に要求した点をきっかけに

---

## 16. run 途中再開 CLI は 4 SQLite DB + in-memory memo の構成で動く

**何を**: ``scripts/being_snapshot_cli.py`` の ``_build_stack`` は 4 つの SQLite
ファイル (``being`` / ``memory_graph`` / ``episode`` / ``reinterpretation``) を
明示引数で取り、memo store だけは ``InMemoryMemoStore`` で新規に作る。

**なぜ**:
- 5 memory store のうち memo にだけ SQLite 実装がなく、in-memory にしか
  住んでいない (= Phase 3 までの整理で必要にならなかった)
- 「memo は持たないと困るが永続化先がない」を解決するのが snapshot JSON。
  CLI 起動ごとに memo store は新規になるが、 ``capture`` で payload に
  乗り、``restore`` で書き戻されるので **JSON ファイル自体が memo の
  永続化媒体** として機能する
- semantic + memory_link は同一 SQLite ファイルに共住 (=
  ``apply_memory_graph_migrations`` が両 schema を一括適用) なので CLI も
  同じ接続を共有

**どうしないと壊れるか**:
- memo の SQLite 実装を急いで作ると、Phase 5 のマイルストーン (= JSON 経由
  の途中再開) が遅れる。「memo は in-memory + JSON 経由保存」という整理で
  最短 path を取る
- 4 DB の役割を CLI 引数で明示することで、将来 DB 配置が変わっても CLI を
  作り直す必要がない (= 既存 game DB と同じ path を指定すれば動く)

**どこでこの判断が出てきたか**:
- Phase 5 着手時 (= 本 PR)
- 将来 memo SQLite を入れるときは ``--memo-db`` 引数を追加する


**その後**: 再解釈の保存先を消したので、CLI の `--reinterpretation-db` を Issue #1631 で外した。見出しと本文の「4 SQLite DB」は消す前の構成で、いまは 3 つの SQLite DB と in-memory memo で動く。

**その後**: 意味記憶の store (`SqliteSemanticMemoryStore`) は記憶の部品の撤去 (#1631) の #1794 で消した。`--memory-db` の SQLite ファイルにはいま memory_link だけが入る。意味記憶の表を作る版はマイグレーションの履歴として残るので、古い DB ファイルも開ける。

記憶リンクも #1799 で消したので、CLI の `--memory-db` を外した。いまは Being の DB とエピソードの DB の 2 つと、in-memory の memo で動く。

古いエピソードの store (`SqliteSubjectiveEpisodeStore`) も #1805 で消したので、CLI の `--episode-db` を外した。いまは Being の DB と、in-memory の memory store で動く。

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
| 4. travel / wait は tool 内で tick を進めない | 2026-06-07 / 2026-06-14 | #404 / #405 / #471 |
| 5. silent failure を構造で塞ぐ | 2026-06-07 | #396 / #400 |
| 6. 後方互換を過度に守らない | (継続) | CLAUDE.md / #409 |
| 7. heartbeat → idle timer | 2026-06-07 | #346 / #407 / #412 |
| 8. 状態情報は state section へ | 2026-06-07 | (新規) PR β |
| 9. LLM 判断ミス > wall time | 2026-06-07 | 実験 #29 feedback 群 |
| 10. 実験 env は fail-fast | 2026-06-07 | PR #433 / #434 |
| 11. 設定 DTO 集約 + ctor 注入 | 2026-06-09 | PR #446-#451 (リファクタ 6 PR) |
| 12. Future work は xfail-strict で可視化 | 2026-06-09 | PR #451 (慣習化) |
| 13. memory caller の未解決時挙動は役割で分岐 | 2026-06-14 | PR #491 / #492 |
| 14. promotion_frontier は Phase 3 Step 3c scope 外 | 2026-06-14 | PR #495 |
| 15. BeingSnapshot v2 は memory payload をオペーク JSON で持つ | 2026-06-14 | Phase 4 Step 4-1 |
| 16. run 途中再開 CLI は 4 DB + in-memory memo で動く | 2026-06-14 | Phase 5 |
| 17. experiment runner の snapshot は escape_game runtime 限定 store のみ拾う | 2026-06-14 | Phase 6 |
| 18. snapshot save 経路の SIGINT は flag 化 (KeyboardInterrupt を抑制) | 2026-06-14 | Phase 6 |
| 19. snapshot メタデータで cross-scenario transfer を可視化 (warning のみ) | 2026-06-14 | Phase 7 |
| 20. snapshot schema 進化は (a) 厳格 — 未サポート version は load 失敗 | 2026-06-14 | Phase 8 |
| 21. world snapshot は scenario 一致を hard-error で要求 (= cross-scenario 不可) | 2026-06-14 | Phase 9-1 |
| 22. world snapshot は subsystem 分散 / 登録外 subsystem は forward-compat で skip | 2026-06-14 | Phase 9-1 |
| 23. monster / quest codec は Phase 9-5 では未実装 (= 実需要待ち) | 2026-06-14 | Phase 9-5 |
| 24. ObservationAppender ↔ encounter は observer slot で疎結合 | 2026-06-17 | PR3 (Encounter Memory wiring) |
| 25. application 層の circular import は test 側で warm-up import で回避 (= 既知債務) | 2026-06-17 | PR3 / observation.contracts ↔ llm.services |
| 26. 勝敗は runtime でなくシナリオ専管 → game_end_conditions を書かなければ「永続世界」 | 2026-06-25 | U5 経路統一 |
| 27. 新しい per-Being store は snapshot に乗せる前提で実装する (4 step checklist) | 2026-06-27 | PR #593 / #594 (PR-F + PR-G) |
| 30. ローカルLLMはレプリカ単位で常駐管理し、実験を同じレプリカへ固定する | 2026-07-25 | v108 夜間実験基盤 |
| 39. 実験モデルは版固定 ID を使い、接続先の能力は実呼び出しで確かめる | 2026-08-01 | PR #898 |

---

## 24. ObservationAppender ↔ encounter は observer slot で疎結合

**何を**: ``ObservationAppender`` は ``observers: list[Callable]`` を受け取り、append
の度に各 observer を呼ぶ。``EncounterObservationCollector`` は collector の
``on_observation`` を bound method として slot に渡される。``ObservationAppender``
側は ``encounter`` への import を持たない。

**なぜ**:
- ``observation`` 層と ``encounter`` 層を疎結合に保つ。``application/`` は単一
  layer として扱われているが、責務が違うサブシステムを直接 import しないことで
  「観察を受け取る側 (appender) は観察者 (encounter / metrics / debug) を知らない」
  形を保てる
- observer 追加時の負担が低い: 別目的の Callable (例えば trace metrics) を後
  から差し込みやすい
- import grpah が浅くなり、循環 import の起こりやすさが下がる (= #25 とも整合)

**どうしないと壊れるか**:
- ``ObservationAppender`` の constructor で concrete collector を isinstance
  チェックする pattern を持ち込むと、observation → encounter の hard import が
  生まれて応用範囲を狭める
- 後で「append のたびに ○○ もしたい」が来るたびに ``ObservationAppender`` 改修
  が必要になる

**どこで出てきたか**: PR3 (Encounter Memory wiring) の subagent code-reviewer
レビューでカップリングを指摘され、Callable slot 化で対応した

---

## 25. application 層の circular import は test 側で warm-up import で回避 (= 既知債務)

**何を**: ``application/observation/contracts/__init__.py`` が
``llm.contracts.dtos`` を import し、その先で ``llm/__init__`` 経由で
``llm.services.agent_orchestrator`` → ``episodic_chunk_coordinator`` →
``observation.contracts.interfaces`` への参照が走り、partial initialization 中
の ``observation.contracts.interfaces`` を import しようとして
``ImportError`` (circular) が起きる。

回避策として、test ファイルでは ``llm.services.*`` を先に import して `llm` 側
を warm up してから ``observation.contracts.dtos`` を import する。新規 module
側は ``TYPE_CHECKING`` のみで ``ObservationOutput`` を参照する。

**なぜ債務として残すか**:
- 本質的な解は ``observation.contracts`` 側の package-level import を遅延化
  する (= ``__init__.py`` で interfaces を eager import しない) 構造的な改修。
  これは観測 / llm 双方の import 経路を整理する大きな refactor で、PR3 の
  スコープを越える
- 既存テストもこの順序に依存しており、暗黙の前提として運用されている
- 既知債務として明示化することで、次に再発見した時に同じ調査をやり直さない

**どうしないと壊れるか**:
- 新規 module で何も考えずに ``ObservationOutput`` を eager import すると、
  別の import 経路で ``observation.contracts`` を先に初期化する側が circular に
  巻き込まれる
- test の import 順序を「アルファベット順に整理する」ような自動 formatter で
  並べ替えると壊れる (= test 側に明示コメントを残す責務がある)

**どこで出てきたか**: PR3 (Encounter Memory) の collector / test 追加時に再現。
subagent reviewer が「pre-existing だが新規 file が増えるたびに workaround が
拡散する」と指摘したのを受けて、債務として明示化

## 26. 勝敗は runtime でなくシナリオ専管 → game_end_conditions を書かなければ「永続世界」になる

**何を**: ゲームの勝敗 (win/lose) と終了条件は runtime にハードコードせず、
シナリオの ``game_end_conditions`` ブロック (``win`` / ``lose`` の条件配列) だけが
source of truth。``check_game_end`` は ``scenario.win_conditions`` /
``lose_conditions`` を評価するだけで、**両方が空 (= JSON に ``game_end_conditions``
を書かない) なら決して ``is_ended=True`` を返さない**。その世界は外的停止
(driver の ``MAX_WORLD_TICKS``) でしか止まらない「永続世界」になる。

参照シナリオ: ``data/scenarios/persistent_world_demo.json`` (勝敗条件を一切宣言
しない最小デモ)。回帰固定: ``tests/integration/test_persistent_world.py``。

**なぜこの形か**:
- escape / survival のような「クリア/失敗で終わる世界」と、勝敗のない「ただ
  生きる世界」を **同じ turn engine** で両立させたい (経路統一の目的)。勝敗を
  runtime の前提にすると永続世界が書けなくなる。
- 勝敗をシナリオ宣言に寄せることで、runtime は「終了条件を評価して報告するだけ」
  の world 非依存な部品になる (`docs/agent_design_principles.md` の疎結合)。
- ``ResolvedLlmRuntimeConfig`` (runtime 設定) には勝敗概念のフィールドを **持たせ
  ない**。config 側に win/lose を足すと、宣言しない永続世界にも勝敗が漏れる。
  これも ``test_persistent_world.py`` で固定する。

**どうしないと壊れるか**:
- escape 固有の集団 WIN/LOSE や outcome 判定を runtime のデフォルト挙動として
  再注入すると、``game_end_conditions`` を書かないシナリオが勝手に終了したり、
  永続世界の prompt に「脱出できない」等の勝敗前提テキストが漏れる
  (後者は別途 escape prompt の world 中立化で扱う)。

**どこで出てきたか**: 経路統一アーク U5。「勝敗なく永続的な世界を実現したい」と
いう要望に対し、capability は既にあった (空条件 → 終了しない) が、それを行使する
シナリオもテストも無かったため、参照シナリオ + 回帰テスト + 本項で固定した。

## 27. 新しい per-Being store は snapshot に乗せる前提で実装する (4 step checklist)

**何を**: 新しく per-Being scope の state を持つ store (= `BeingId` をキーに
保持する store) を追加するときは、その時点で `BeingMemorySnapshotService`
への配線まで含めて 1 PR にまとめる。「あとで足す」と後回しにすると、長走
実験の終了 → 再開で連続性が静かに壊れる silent failure になる。

実際 PR #580 (想起スロット) / #588 (afterglow) / #526 段階 2 (慣化) は
追加時に snapshot への追従が忘れられたまま main に入り、半年弱気付けな
かった。PR-F (#593) / PR-G (#594) で構造的 fail-fast と既存 3 store の
追従を入れたあと、次は「追加し忘れの再発を docs で 1 段目止める」のが本項。

**手順 (= 新 store 追加 PR でやること)**:

1. `BeingMemorySnapshotService.EXPECTED_PAYLOAD_KEYS` に新 key を追加
   - 1 store = 1 key が原則。値の形が dict だが list 規約に合わせるため
     split が必要なら 2 key にしてよい (例: slot は entries と cooldown)
2. `BeingMemorySnapshotService.__init__` に新 store の引数を追加 (keyword-only)
   - Protocol 越しに渡せるなら `runtime_checkable` Protocol を使い、
     `isinstance()` で wiring 漏れを early detection する
3. `capture()` の payload dict に新 key の生成ロジックを追加
   - VO ↔ dict の codec は `_memory_payload_codecs.py` に集める
   - 1 を足して 3 を忘れると初回 capture で `SnapshotCoverageError` が
     起動時に投げられる (= PR-F の fail-fast)
4. `restore()` のデコード + 書き戻しを追加
   - store interface に `replace_all_by_being(...)` を必ず生やす。中身が
     空なら being の state を pop して「capture 時に空だった状態と完全に
     同じ姿で復元される」よう揃える
   - 実装の参照先: `InMemoryEpisodicRecallSlotStore.replace_all_by_being`
     (slot + cooldown) / `InMemoryAfterglowStore.replace_all_by_being`
     (entries のみ) / `InMemoryEpisodicRecallHabituationStore.replace_all_by_being`
     (mapping)。戻り値は `None`。
   - 1 を足して 4 を忘れると restore で `BeingMemoryPayloadFormatError` に
     化け、これも起動時に止まる

**追加で守ること**:

- `ExperimentSnapshotSession` の `fallback_used` ログ対象に新 store の属性名
  を追加する (= wiring 漏れで空 store が静かに使われる状態に気付ける)
- store interface に capture 用の read API (`list_all_by_being` 等) が
  無ければ追加する
- snapshot CLI (`scripts/being_snapshot_cli.py`) が新 store にアクセスできない
  in-memory sidecar なら、`cmd_save` で warning を残してユーザに「CLI 経由
  では dump されない」事実を伝える

**どうしないと壊れるか**:

- 1-4 のうちどれかを忘れると、`capture()` または `restore()` のどちらかが
  fail-fast で止まる。**全部を忘れた場合は構造で検出できない** ので、本項の
  チェックリストが最後の砦になる
- 「あとで snapshot 対応する」と後回しにすると、間に走った長走実験の trace
  に「想起階層の連続性が壊れた事実」が混入する。データに混入したノイズは
  後から取り除けない

**どこで出てきたか**: PR #594 (PR-G) で 3 store ぶんの追従漏れを一度に
解消した際、それ以前の 3 store を追加した一連の経路 (#580 / #583 が想起
スロット、#588 が afterglow、Issue #526 段階 2 が慣化 store) すべてが本
手順を踏んでいなかったことが判明したため、再発防止として本項を追加。

**その後**: 見出しの欄 (afterglow) の store と、役に立った回数の store (`recall_success`) は、Issue #1631 の段 9 で snapshot のキー (`afterglow_entries` / `recall_success_hit_count` / `recall_success_received_event_ids`) ごと消した。手順の 1〜4 を逆にたどって外した。restore は足りないキーだけを拒むので、消す前の snapshot も読める。replay で世界の時計を巻き戻すときは、古い snapshot に残る `afterglow_entries` を読まずに捨てる (`world_clock_restart.py`)。

残る想起の枠と慣れの store も、Issue #1631 の #1777 で snapshot のキー (`recall_slot_entries` / `recall_slot_cooldown` / `recall_habituation_last_recalled`) ごと消した。この項が生まれた PR-G の 3 store は、すべて無くなった。replay では、この 3 キーも読まずに捨てる。

消したキーを捨てる処理は、#1804 で `removed_memory_payload_keys.py` の表に移り、replay かどうかに関わらず同じ表を通るようになった。`world_clock_restart.py` は段 13 で消した (#1810)。

古いメモの store を外した段 11-2b (design_decisions D1631-5) からは、消したキーを `removed_memory_payload_keys.py` の表に足す。読み込みは replay かどうかに関わらず表のキーを捨て、件数を trace に残す。`fallback_used` のログは対象が無くなったので消した。新しい store は `ExperimentSnapshotSession` の必須の一覧に足す。

## 28. 実験に意味を持つ設定は profile/config だけから入れる

**何を**: LLM 実験の挙動を変える設定は、`data/experiment_profiles/*.json`
または `--experiment-config` の `runtime_config` だけから
`ResolvedLlmRuntimeConfig` に解決する。環境変数から同じ値を入れる互換経路は
作らない。例外は API キー、サーバのホスト/ポート、ローカル DB パスのような
秘密情報または実行基盤の設定に限る。

**なぜこの形か**:

- 1 つの値に複数の入力経路があると、run_start trace に残った値と実 runtime の
  値がずれる。過去の rolling_summary / prompt section / provider routing 系の
  静かな失敗はこの形で起きた。
- 実 LLM run はコストが高い。外側 shell に残った古い環境変数が混ざるだけで、
  比較不能な run ができてしまう。
- profile/config は成果物として `experiment.config.source.json` と
  `experiment.config.resolved.json` に保存できる。環境変数の履歴を後から完全に
  復元するより、入力を 1 本にする方が事故が少ない。

**実装上の決まり**:

- `run_scenario_experiment.py` は profile/config を process env に注入しない。
  `runtime_config` の mapping を直接 `ResolvedLlmRuntimeConfig.from_mapping(...)`
  に渡す。
- `create_world_runtime(..., config=cfg)` / `GameRuntimeManager(runtime_config=cfg)`
  / `create_llm_client_from_config(cfg)` のように、解決済み config を引数で渡す。
- 低レベル resolver は `env=None` でも `os.environ` を読まない。テストや移行用に
  mapping を渡す場合だけ、その mapping を読む。
- 新しい実験設定を足すときは、`ResolvedLlmRuntimeConfig`、profile、manifest、
  配線契約テストを同じ PR に含める。

**どうしないと壊れるか**:

- 「後方互換」として `LLM_*` や `BELIEF_*` を環境変数から読む経路を戻すと、
  profile に書いた条件と実 runtime の条件が分岐する。
- `LiteLLMClient` 内部で provider / model / reasoning / timeout を環境変数から
  読むと、manifest に残らないコスト条件が混ざる。
- 並列度や idle timeout も観測結果に影響しうるため、実験 run では config に
  固定して trace に残す。

**どこで出てきたか**: `v3coop_stagnation_001` / `002` 相当の「全部盛り」
実験条件を profile 化する作業中、ユーザから「API キー以外の env 入力経路は
廃止したい。一つの値に複数経路があることで過去にも苦しんだ」と指摘された。
そのため、後方互換よりも経路の単一化を優先する判断として固定した。

## 29. 再開境界で未通知観測を勝手に flush しない

**何を**: snapshot capture の直前に、日次集約などの未通知バッファを
強制 flush しない。未通知バッファ自体を world snapshot の subsystem として
保存・復元し、既存の tick 境界条件で後から配信する。

**なぜこの形か**:

- capture 前 flush は、連続 run なら日付境界で出る観測を snapshot 時刻に前倒し
  してしまう。これは resume run と連続 run の観測時刻をずらす。
- 観測駆動の LLM では、観測時刻のズレ自体が次の行動を変える。状態を保存する
  ために観測の発生時刻を変えるのは、再開品質として筋が悪い。
- 未通知バッファは「世界状態そのもの」ではなくても、未来に配信される予定の
  観測であり、実験の解釈に影響する。

**実装上の決まり**:

- `WorldRuntime._pending_spoiled` / `_pending_spoiled_day` のような
  未通知バッファは、専用 `WorldSubsystemCodec` で保存・復元する。
- codec は flush を呼ばない。復元後、既存の `advance_tick` / 日付境界処理に
  任せる。
- 追加時は「capture → restore 後に既存 flush 経路で観測が失われない」ことを
  テストで固定する。

**どうしないと壊れるか**:

- snapshot save が日付境界前に走ると、resume 後に「今日は X が腐った」という
  未通知観測が消える。食料管理の観察 run では、LLM が腐敗に気づく機会が
  静かに失われる。
- 逆に capture 前 flush にすると、観測は消えないが時刻が変わり、連続 run と
  resume run の比較可能性が落ちる。

**どこで出てきたか**: `belief_goal_full` の 200 tick 観察前に
snapshot/resume を主経路にできるかレビューした際、`_pending_spoiled` が
snapshot 対象外であることが見つかった。食料・腐敗が今回の重要観察対象なので、
flush ではなく codec による保存を採用した。

## 30. ローカルLLMはレプリカ単位で常駐管理し、実験を同じレプリカへ固定する

**何を**: v108のGemma 4 31BはH100 1枚につき1つの独立レプリカとして
GPU 0〜3、8100〜8103番へ固定する。プロセス寿命はユーザーsystemdで管理し、
異常終了時の再起動、HTTP死活確認、安全停止時の要求排出を共通の管理入口へ
集約する。実験を接続するときは、1 runの全要求を同じレプリカへ固定する。

**なぜこの形か**:

- 31Bの量子化モデルはH100 1枚に収まるため、4枚をテンソル並列で束ねるより、
  独立レプリカ4個の方が複数実験の総処理量と故障分離に向く。
- vLLMのプレフィックスキャッシュとKVキャッシュはレプリカ間で共有されない。
  要求ごとの単純なラウンドロビンでは、同じ実験の共通プロンプトが4台へ散る。
- 夜間実験では端末やCodexの会話寿命と推論サーバーの寿命を分離する必要がある。
  systemdへ寄せることで、開始、準備完了、異常再起動、正常停止の意味を一つにする。
- 停止前に`/metrics`の実行中・待機中要求を確認すれば、処理途中の要求を
  「終了したように見せる」静かな失敗を避けられる。

**どうしないと壊れるか**:

- `nohup`や端末上の親スクリプトだけで常駐させると、ログアウト、親プロセス終了、
  部分的な異常終了時の状態が曖昧になる。
- HTTP死活確認1回の失敗ですぐ再起動すると、起動時コンパイルや一時的な高負荷を
  障害と誤認する。連続失敗にだけ反応する。
- メトリクス欠落を要求0へ縮退すると、壊れたサーバーを排出完了と誤認して停止する。
- 推論サーバーの安全停止だけでは新しい実験の投入競合を防げない。後続の実験
  起動器では「新規割り当て停止」を要求排出より先に行う。

**どこで出てきたか**: v108のH100 4枚を使い、OpenRouterに依存せず複数の
長走実験を夜間に自走させる運用を検討した際、単純なロードバランサーでは
キャッシュ局所性と実験ごとの性能解釈が崩れることを確認したため。

## 31. テレポートの秘匿性は visibility ではなく「誰が居たか」で決まる

`TELEPORT_ENTITY` 効果 (隠し通路・ベント・魔法陣) を実装するにあたり、移動が
第三者に見えるかどうかを何で決めるかを選んだ。

**採用**: 出発スポットと到着スポットの presence だけで決まる。`teleport_entity`
は `move_entity` と同じ `EntityLeftSpotEvent` / `EntityEnteredSpotEvent` を
発火し、既存の観測経路がそれぞれのスポットの居合わせた者へ配る。誰も居なければ
誰にも観測されない = 秘密の移動が成立する。

**棄却**: `InteractionEffect.visibility` (ACTOR_DIRECT / PUBLIC_OBSERVABLE /
HIDDEN) で制御する案。物理的にその場に居る者が「消えた人」を見落とす表現は
不自然で、`HIDDEN` を許すと「目の前から人が消えたのに誰も気づかない」世界に
なる。他の効果 (ダメージ・状態異常) は身体の内側で起きるので visibility が
意味を持つが、移動は外形的な事実である。

ただし visibility を書いても黙って無視されると「HIDDEN にしたから見られない」
と誤解したまま秘密の移動を期待されるので、`TELEPORT_ENTITY` に visibility を
書いたシナリオは **読み込み時に `ScenarioLoadError` で落とす**。効かない設定を
黙って受け取らない。

同じ理由で、行き先 (`parameters.target_spot`) を欠いた `TELEPORT_ENTITY` も
読み込み時に落とす。domain 側は `spot_id <= 0` なら spec を作らない実装なので、
放置すると「書いたのに何も起きない」静かな失敗になる。`target_spot` を effect の
直下 (parameters の外) に書いた場合も同様に無言で消えるため、両方を弾く。

### 現在地と同じスポットへのテレポートは no-op

出発していないのに `EntityLeftSpotEvent` を流すと、同席者に幽霊のような出入りが
観測される。例外にはしない (ランダム転送などで正当に起こりうるため)。

### 複数 tick 移動との衝突は未解決 (既知の制約)

`PlayerSpotNavigationState` は本集約とは別に「どの接続を辿っている途中か」を
保持する。移動中の entity をテレポートさせると、次の `advance_spot_travel_one_tick`
が「接続の始点に居ない」として `EntityNotAtSpotException` を投げる。

現在この経路は踏めない。`teleport_entity` の呼び出し元は interact だけで、
行為者自身しか飛ばせず、移動中のプレイヤーはターンが回らないためである。ただし
この不変条件は別の層 (ターン割り当て) が担保しており、`teleport_entity` 自身は
何も知らない。**他者を飛ばす効果や trap 由来のテレポートを足すときは、呼び出し
側で移動状態を先に解消すること。** 症状は
`tests/domain/world_graph/aggregate/test_spot_graph_teleport_entity.py` の
`TestTeleportVersusConnectionMovement` が固定している。

## 32. 環境変化 (CHANGE_ATMOSPHERE) は部分更新にする

`CHANGE_ATMOSPHERE` 効果 (停電・気温変化・危険度上昇) の適用にあたり、
`SpotAtmosphere` をまるごと置き換えるか、指定項目だけ差し替えるかを選んだ。

**採用**: 部分更新。`update_spot_atmosphere` は渡された項目だけを差し替え、
指定しなかった項目 (`sound_ambient` / `smell` / `sound_intensity` など) は元の
値を保つ。停電で明るさだけ変えたいときに環境音や匂いまで既定値へ巻き戻ると、
その spot の描写が静かに壊れるため。`SpotNode` も `SpotAtmosphere` も frozen
なので `dataclasses.replace` を二段重ねる。

**棄却**: spec の内容でまるごと差し替える案。シナリオ作者が「明るさだけ変えた
つもり」で全部を消す事故が避けられない。

### 未設定 spot の既定は BRIGHT

`atmosphere` を持たない spot に `hazard_level` だけを指定した場合、明るさは
既定の `BRIGHT` が入る。「未設定 = 明るい」を安全側の既定とする — 暗いと視認
(`monster_visibility_service`) や戦闘の判定が変わるので、書かれていない spot を
勝手に暗くしない。

なお `hazard_description` を `None` に戻す (クリアする) 用途には非対応。
部分更新は「渡した項目だけ差し替える」ため、`None` は「指定なし」と区別できない。
クリアが必要になったら別途 sentinel を設計する。

### イベントは発火しない

環境変化の観測は interaction 側の `AppliedEffectSummary(kind=ATMOSPHERE_UPDATE)`
が `SpotPublicEffectObservedEvent` として同 spot の第三者へ届ける。集約側でも
イベントを出すと同じ変化が二重に観測される (#812 で直した interact の二重発火と
同型)。

### 読み込み時に弾くもの

`#31` (テレポート) と同じ方針で、書いたのに何も起きない経路を loader で塞ぐ。

- `parameters.target_spot` が無い: domain 側は `spot_id <= 0` なら spec を作らない
- `lighting` / `temperature` が enum 名として未知: 綴り間違いが実行時まで気づけない
- 変更項目が 1 つも無い: 何も変えない宣言は書き忘れとみなす

いずれも `ScenarioLoadError`。効かない設定を黙って受け取らない。

### interaction と scenario_events の両方から適用する

停電や気温低下は「誰かが操作した結果」だけでなく「時刻や条件で世界の側が変わる」
形でも起きる。`SpotGraphScenarioEventStageService` でも `atmosphere_update_specs`
を消費し、ON_TICK で照明を落とす表現を書けるようにした。

一方 `TELEPORT_ENTITY` は scenario_events では意味を持てない (行為者が居ないので
誰を飛ばすか決まらない)。黙って捨てると気づけないので、この経路で宣言された
場合は警告ログを残す。

## 33. 能動想起ツールは測定条件が整うまで profile 側で OFF にする

`SEMANTIC_SEARCH_ENABLED` と `EPISODIC_EXPLORE_RELATED_ENABLED` は、もともと
「`memory_search_semantic` / `memory_explore_related` を LLM に露出する」
設定として profile に書かれていた。しかし実験 runtime 側の露出制御が未配線で、
過去 run ではどちらのツールも一度も LLM に提示されていなかった。つまり true と
宣言していたが、実験条件としては実質 OFF だった。

#851 で露出制御が実際に効くようになったため、profile の true をそのまま残すと
次の run から突然 2 つの能動想起ツールが増える。これは正しい実装挙動ではあるが、
直近 run との比較条件を変え、さらに memo ツール表示制御の A/B 実験と干渉する。
どちらもターンを消費する能動想起であり、memo を減らして行動枠を返す効果を測る
局面では逆方向の圧力になる。

そのため `belief_goal_full` と `ablation_base` では、当面
`SEMANTIC_SEARCH_ENABLED=false` / `EPISODIC_EXPLORE_RELATED_ENABLED=false`
に明示する。これは「宣言したのに効いていなかった」状態から「意図して切っている」
状態へ移すための変更である。`EPISODIC_RECALL_ENABLED` は run 003 で実際に使われた
既存条件なので true のまま維持する。能動検索・関連探索は、後でまとまりとして
評価するときに profile で再度有効化する。

**その後**: `belief_goal_full` と `ablation_base` は、古い記憶の部品を使う profile として Issue #1631 で退役させた。過去の run の結果は `var/runs` に残る。

能動想起の 4 つの道具 (`memory_recall_episodes` / `memory_recall_by_handle` / `memory_explore_related` / `memory_search_semantic`) と、その露出の設定 (`EPISODIC_RECALL_ENABLED` / `EPISODIC_EXPLORE_RELATED_ENABLED` / `SEMANTIC_SEARCH_ENABLED`) は、Issue #1631 の #1767 で消した。いまは目次つきのエピソード (`episode_recall`、D1623) が呼び出しの道具になる。

## 34. memo A/B は「蒸留ありの手帳」と「手帳なし」を比較する

v4 第3回 run では `memo_add` / `memo_done` / `memo_list` が全行動の約15%を
占めた。memo section の文字量は小さい一方、1ターン1ツール制約では memo を書いた
ターンに移動・探索・会話ができない。記憶システムが強くなった状態で、この手帳枠が
まだ必要かを測るため、`belief_goal_full` を基準にした A/B profile を分ける。

採用する腕は2本にする。A は `belief_goal_memo_ab_keep_memo` で、
`MEMO_TOOLS_ENABLED=true` のまま memo tool を露出し、`MEMO_DISTILL_ENABLED=true`
により `memo_done` を semantic 記憶の `BeliefEvidence` へ蒸留する。これは
docs/memory_system/short_term_memory_design.md が想定していた「memo = 目標・計画層」
を実際に動かす腕である。B は `belief_goal_memo_ab_hide_memo` で、
`MEMO_TOOLS_ENABLED=false` により memo tool と未完了 memo section、memo 完了 hint を
隠す。記憶本体 (episodic / semantic / passive recall / rolling summary) は止めない。

`ablation_base` は stagnation reasoning を落とした比較土台であり、memo A/B とは目的が
違う。したがって memo A/B の2 profile は `belief_goal_full` 系として置き、互いの差分は
`MEMO_TOOLS_ENABLED` の1キーだけにする。#33 で OFF にした
`SEMANTIC_SEARCH_ENABLED=false` / `EPISODIC_EXPLORE_RELATED_ENABLED=false` は両腕で維持し、
能動想起ツールの増加を memo 実験に混ぜない。

memo A/B の scenario は `survival_island_v4_coop.json` に固定する。v4 第3回 run との
比較可能性を保つためであり、v3 には position / area / distant cue が無く #35 の
「拠点から山影が見える」変更が効かないためである。run 時の `SCENARIO=` 上書きには
頼らず、profile を読めば実験条件が分かる状態にする。

**その後**: memo A/B の 2 profile と `belief_goal_v4` は、Issue #1631 で退役させた。memo A/B の結果は `var/runs/v4coop_memo_keep_004` と `v4coop_memo_hide_005` に残る。

メモの蒸留 (`MEMO_DISTILL_ENABLED`) は、記憶の部品の撤去 (#1631) の #1654 で消した。

## 35. `is_outdoor` 未宣言の屋内扱いは validator で見える化する

`SpotNode.is_outdoor` は既定 false のまま維持する。洞窟・廃屋・小屋など、空や
遠景が見えない spot を壊さないためである。一方で、未宣言が黙って屋内扱いになると、
遠景 (`distant_view`) や天候表示が抑止され、症状は「なぜか目標が見えない」として
しか表れない。

v4 第3回 run では、最長滞在拠点だった `hidden_cove` が `is_outdoor` 未宣言で屋内扱い
になり、拠点から山影が一度も見えていなかった。description 上は海に開けた入江であり、
屋内意図は読み取れないため、v3/v4 では `is_outdoor: true` を明示する。ただし v3 は
position / area / distant cue が未整備なので、この宣言だけでは遠景は出ない。v3 側の
宣言は、将来 v3 に遠景材料を足したときに同じ屋内抑止を再発させないための前準備である。

v4 ではこの変更により、次の本命 run で拠点から「切り立った山影」が見える。run 003
との比較では、この目標 cue の露出条件が変わったことを明記する。

既定値は変えず、`validate_spot_map` が屋内扱い spot と `is_outdoor` 未宣言 spot を
info / metrics に出す。シナリオ作者が map 検査時に「本当に屋内扱いでよいか」を確認
できるようにし、既存シナリオの意味を反転させない。

## 36. object.state の prompt 表示は scenario 側で宣言し、未宣言値は隠さない

`SpotObject.state` は interaction の前提条件や effect の真実源であり、`opened=false`
や `lit=false` のような値がそのまま prompt に出ると、エージェントには意味の薄い
内部表現として見える。一方で、状態表示をコード側で key ごとに決めると、シナリオ固有の
文脈 (「宝箱はまだ開いていない」「狼煙台に火はついていない」など) を失う。

そのため `StateDisplayRule(key, value, text)` を scenario の object に宣言し、
`visible_state()` が一致する key/value を日本語 tag に変換する。`available=false`
だけを `unavailable_hint` で特別扱いしていた既存設計を一般化した形であり、
`available` も明示 `state_display` があればそちらを優先する。

重要なのは、宣言の無い key/value を隠さないこと。key に rule があっても現在値に
対応する rule が無い場合は、従来どおり raw state を出す。ここで隠すと、
シナリオ作者の宣言漏れが prompt からもテストからも見えなくなり、再び静かな失敗になる。
v4 だけは hard audit で raw state を禁止し、他シナリオは quality テストで棚卸しする。

値比較では `False == 0` / `True == 1` を同一扱いしない。bool state と数値 state は
別概念なので、型を含む同一性キーで rule を照合する。

累積カウンタは完全一致だけでは上限の次の値で raw state に戻るため、整数下限の
`at_least` ルールも許可する。完全一致を最優先し、該当しない場合だけ、現在値以下の
`at_least` のうち最大閾値を使う。閾値に届かない値や整数以外には規則を広げず、従来
どおり raw state を出す。これにより「3 本以上なら次の判断は同じ」という表示はまとめ
つつ、宣言漏れを隠す #36 の安全策は維持する。bool は整数下限の対象にしない。

## 37. いまできない object action は候補から消さず、選べる行動とは別行に出す

object 行の `[...]` は LLM にとって「ここから action_name を選ぶ」欄として働く。
その中に `search(棚を調べた後)` のような現在必ず失敗する action を並べると、
選べる行動に見える。一方で、候補から消すと説明文だけが操作を誘う状態になり、
存在しない action_name を発明する実測がある。

そのため、`SpotGraphInteractionEntry` ではヒントを 2 種に分ける。

- `condition_hints`: 時刻・天候・明るさのような宣言由来の制約。選べる行動欄の
  `action(夜不可)` に残す
- `blocking_hints`: OBJECT_STATE や OBJECT_STOCK_AT_LEAST のように、現在値を読んだ
  結果いま満たしていない理由。`[...]` から外し、`いまできない:` 行へ出す

`ToolRuntimeTargetDto.available_interactions` は表示とは独立して、従来どおり全
action_name を持つ。これは resolver の入力候補であり、prompt の整形都合で削っては
いけない。表示は「選べるもの」と「いまできないもの」を分けるが、解決可能な候補集合は
変えない。

同席者への `give_item` 手がかりも、各 player 行に同じ文を繰り返さず見出しへ集約する。
ただし死亡・ダウン中の相手には渡せないため、見出し文は「倒れていない相手には」と
条件を含める。行ごとの死亡・ダウン表示と所持品表示は維持する。

## 38. action_name は意味ラベルで補い、多義語は動詞 + 目的語へ寄せる

interaction には `display_label` が既に宣言されており、観測側では「持ち物を奪う」の
ような意味表示に使われていた。しかし選択前の prompt では `action_name` だけが出ており、
エージェントは裸の識別子から意味を推測していた。`take` を「診る・手当てする」と解釈し、
失敗文を読んでも治療行為だという前提が剥がれなかったのは、この非対称が原因である。

そのため、選択前の表示でも `display_label` を必須の意味情報として扱う。空や
`action_name` と同一の `display_label` は、意味を持つ文字列が無いのと同じなので
監査で落とす。欠落・空白は `ScenarioLoader` で読み込み時に止め、KeyError や後段の
別エラーに流さない。

ただし表示だけでは足りない。LLM が実際に tool 引数へ渡すのは `action_name` であり、
介入実験でもラベルを添えた側が `take` と書き続けた。そのため action 名自体も
「動詞 + 目的語」に寄せる。`loot_from_downed` のように前提条件の一部を名前へ埋め込むと、
立っている相手に撃つことが名前の時点で矛盾になる。

改名前の段階では、多義語 denylist を quality 棚卸しとして置く。既存シナリオにはまだ
違反が残るため通常 CI では落とさず、改名 PR で違反を消してから hard audit に昇格する。
改名後は `take` / `search` / `light` などの裸動詞を通常監査で落とす。新しい
interaction を足すときは、`search_wreck_hold` や `loot_from_downed` のように
動詞と対象を名前に含める。

## 39. 実験モデルは版固定 ID を使い、接続先の能力は実呼び出しで確かめる

**何を**: OpenRouter 経由の実験では、特定の版を指すモデル ID を profile に固定する。
DeepSeek V4 Flash の 2026-07-31 更新版は、新しい `belief_goal_v4` profile から
`deepseek/deepseek-v4-flash-0731` を使う。接続先は、同モデルを fp8 で提供し、
`tool_choice=required` の実呼び出しに成功する Cloudflare に固定する。既存 profile は
過去の実験意図を表す記録なので書き換えず、新しい実験条件には新しい profile を足す。

**なぜ**:

- DeepSeek 直結 API の `deepseek-v4-flash` は常に最新版を指す。一方、OpenRouter は
  4月版を `deepseek/deepseek-v4-flash`、7月31日版を
  `deepseek/deepseek-v4-flash-0731` と別 ID にしている。この版固定により、実験の
  途中で同じ ID の中身が黙って変わり、過去 run と比較できなくなる事故を避けられる。
- 7月31日版の DeepSeek 公式 endpoint は `supported_parameters` に
  `tool_choice` を掲げながら、`required` と特定関数指定を 404 で拒否した。
  `supported_parameters` は接続先の宣言であって、値ごとの動作保証ではない。
  実験で必須の値は、本番と同じ provider 固定・reasoning 無効・tool schema で
  実際に呼び出して確かめる必要がある。
- `tool_choice=auto` に下げると tool call の無い応答を許し、エージェントが1回の
  起動を黙って失う静かな失敗になる。Cloudflare は総当たりした接続先のうち、
  fp8 と `required` を両立した唯一の選択肢だった。DeepInfra も `required` は通るが
  fp4 のため、モデル品質を上げる目的に合わない。
- Cloudflare の cache read 単価は DeepSeek 公式の10倍だが、run 004 の実測量では
  200 tick あたり約 0.10 USD の増加に収まる。速度、prompt 単価、completion 単価、
  キャッシュ動作は同等だったため許容した。

**その後**: `belief_goal_v4` は、古い記憶の部品を使う profile として Issue #1631 で退役させた。版固定 ID と、実呼び出しで確かめる手順は残る (docs/llm_provider_selection.md)。

**どうしないと壊れるか**:

- 日付の無い可変 ID を固定版だとみなすと、モデル更新時点を後から特定できず、
  同じ profile 名の run 同士が比較不能になる。
- 既存 profile を新しいモデルへ上書きすると、過去 run がどの条件と意図で設計されたかを
  profile 自体から読めなくなる。`experiment.config.resolved.json` が実測条件を残していても、
  profile が担う実験計画の履歴は代替できない。
- `supported_parameters` だけを見て対応済みと判断すると、実行時の 404 を
  profile 読み込みや単体テストで検出できない。外部 endpoint の能力差には、通常の
  試験から除外した `tests/quality/` の実呼び出しプローブを置く。
- DeepSeek 公式が `required` に対応した後も Cloudflare 固定を惰性で残さない。
  プローブは「まだ拒否される」間だけ成功し、対応した瞬間に失敗して再検討を促す。
- 新しいモデル条件を既存 profile 群へ一括反映しない。新しい profile と継承元の差を
  テストで限定し、意図していない設定差や継承元の書き換えを許さない。

**どこで出てきたか**: DeepSeek V4 Flash 0731 への更新調査と接続先の総当たりを
行い、公開メタデータと実際の `tool_choice=required` 対応が一致しないことを確認した
PR #898。

**追記 (2026-09-23)**: 0731 版の DeepInfra は fp8 に変わっていた。provider の
対応状況は予告なく変わるので、選ぶときの条件と確かめ方は
[llm_provider_selection.md](llm_provider_selection.md) にまとめ、この節の provider の
記述はその時点の記録として読む。

## 40. `CALL_MEETING.trigger` は宣言値を実行まで運び、未知値へ縮退しない

`CALL_MEETING` の `parameters.trigger` は、会議状態と観測に残る招集理由である。
domain の効果結果までは値を保持していたが、application の callback が行為者しか
受け取らず、`WorldRuntime` が常に `emergency_button` を記録していた。この形では
シナリオに別の値を書いても成功扱いのまま宣言が消える。

そのため callback の契約を `(player_id, trigger)` とし、効果結果から
`begin_meeting` まで同じ値を運ぶ。効果側で既定値を補わず、省略・未知値は loader と
domain の両方で拒否する。許可値は domain の `CALL_MEETING_EFFECT_TRIGGERS` を
単一の出所とし、現在は `emergency_button` だけを認める。

`body_report` は死体との同席や重複報告を検査する別の招集入口であり、
`CALL_MEETING` の許可値には含めない。まだ存在しない2種類目の effect trigger のために
回数・クールダウンの規則表は先回りして作らず、実際の宣言を追加するときに、その値と
規則と試験を同時に追加する。

## 41. 差し替え口の単体試験だけでなく、本物の接続を通す

モンスター攻撃の状態異常は、`SpotAttackOrchestrator` に provider を差せる設計と
確率適用の単体試験を持っていた。しかし実runtimeの provider は
`monster.template_id` という存在しない属性を読み、例外を空の候補へ縮退させていた。
実際の属性は `monster.template.template_id` であり、2026-06-21の一括改名以降、
狼・野犬・毒蛇・大型カニの状態異常は一度も発火していなかった。

差し替え口 (seam) を用意して単体試験することは、効果適用ロジックの検証には有効で
ある。しかしスタブを直接差す試験だけでは、production の組み立てが正しい provider を
接続しているかは保証できない。差し替え可能な設計ほど、少なくとも1本は本物のloaderと
runtime組み立てを通り、公開入口の最終的な振る舞いを観測する試験が必要である。

モンスター攻撃では `execute_monster_attack` からプレイヤーの `active_effects` までを
観測し、4テンプレートの効果種別・確率境界・持続tick・強度を固定する。既知
テンプレートの効果が欠ければ公開入口の試験が失敗するため、配線不良を成功扱いの
まま通さない。

この修正以降は、狼・野犬が50%で12 tickの出血、毒蛇が60%で10 tickの毒、
大型カニが35%で8 tickの出血を実際に付与する。生存難易度が上がるため、修正前の
runと比較するときは実験条件の差として明記する。

## 42. モンスター固有の攻撃能力はテンプレート宣言を単一の出所にする

攻撃時状態異常の種別・確率・継続tick・強度は、モンスターの識別子をruntimeの
固定辞書へ照合して決めず、`MonsterTemplate.attack_status_effects` に宣言する。
識別子の逆引きproviderは、テンプレート定義と実行規則を別々に発展させ、実在しない
属性参照を空の効果へ縮退させた直接原因だったため、互換経路を残さず削除する。

`ScenarioLoader` は文字列の `effect_type` を `StatusEffectType` へ変換し、確率の
値域、正の継続tick、数値の強度を起動時に検証する。実行時に未知種別を無視したり、
確率や継続tickを丸めたりしない。ロード済みテンプレートはすでに有効なので、
`SpotAttackOrchestrator` は宣言を直接確率判定するだけにする。新しいモンスターは
コードの対応表を変えず、JSON宣言だけで新しい状態異常能力を持てる。

静的定義をSQLiteへ保存する経路でも同じ一覧を正規化した子表へ保存し、順序を含めて
復元する。シナリオから直接起動する経路だけを直してSQLite経路を空にすると、起動方法で
能力が分岐するためである。状態異常を持たないテンプレートは空タプルで表し、旧provider
や別形式への分岐は置かない。

この全面移行では、同じ4種を含む島シナリオ5本すべてへ宣言を追加する。過去シナリオの
hashは変わるが、二重経路を残して数週間後に別々の仕様へ発展させないことを優先する。
過去runの実測条件は各runの `experiment.config.resolved.json` とscenario hashで確認する。

## 43. 個人結果・終了・生存圧を別々の宣言にし、旧一体型経路を残さない

島シナリオの救助判定は、救助時刻・狼煙・山頂在席・取り残し期限・飢餓ダメージを
`outcome_resolution` という一つの専用設定にまとめ、runtime の固定サービスが解釈して
いた。この形では救助以外の個人結果を持つ新しいシナリオを追加するたびに、シナリオと
コードを一緒に変える必要がある。

個人結果は `player_outcome_rules`、混合集団結果の終了は
`game_end_conditions.end`、生存圧は `needs` に分ける。個人結果規則の発火条件には
既存の `ScenarioEventCondition` と `ScenarioConditionEvaluator` を再利用し、
`trigger` と `player_conditions` を分離する。前者は救助船のような機会が来たか、後者は
その機会の対象者を表す。対象者が0人でも `once` の機会は消費済みにし、後から同じ船を
利用できないようにする。発火済み状態は既存の scenario event 進捗ストアに保存し、
snapshot 再開でも再発火させない。

RESCUED / STRANDED / DEAD が混在する世界終了を `win` や `lose` に置くと宣言が嘘に
なるため、中立の `end` 配列で `ALL_PLAYER_OUTCOMES_RESOLVED` を宣言する。対象者0人を
全員確定とみなさず、終了条件を持たない永続世界は自動終了させない。

旧 `outcome_resolution` は互換経路として残さない。4本の島シナリオを一度に新形式へ
移し、旧設定型・旧サービス・runtime 分岐を削除し、旧キーは読み込み時に明示的に拒否
する。過去シナリオの hash は変わるが、過去 run の実測条件は各 run の
`experiment.config.resolved.json` と scenario hash で確認する。二つの経路を並存させて
別々に発展させるより、シナリオ作者が使う入口を一つに保つことを優先する。

`END_ON_ALL_DOWN` は世界内の勝敗や個人結果を決める規則ではなく、全員が行動不能な
実験を回し続けないための外的停止として扱う。特定の個人結果モードへ埋め込まず、
`check_game_end` の共通入口でシナリオ宣言より先に評価する。終了理由には設定名を含め、
世界内の `game_end_conditions` が成立した終了と後から区別できるようにする。

**その後**: どの profile でも全員が行動不能なら止めるので、`END_ON_ALL_DOWN` のキーは記憶ではない設定の片付け (#1631) の #1793 で消した。あわせて評価の順を入れ替え、世界の判定が続行のときだけ外的停止を見るようにした。先に評価する形では、全員の結果が確定して世界の終了条件も成り立つ tick で、終了理由が外的停止に置き換わる。これは上の「後から区別できるようにする」に反していた。実際、`var/runs/mine_v1_009` は全員の結果が確定して tick 37 で終わったのに、report の終了理由は「外的停止 END_ON_ALL_DOWN: …」だった。勝敗は別に計算していたので変わっていない。共通の入口に置く形はそのまま残す。終了理由の文字列は、過去の run と同じ grep で拾えるように変えない。

## 44. ツール露出は世界・フェーズ・本人状態を公開入口で合成する

run 011 では、投票済みのエージェントへ次のターンでも `vote` が提示され、
`ALREADY_VOTED` が 2 回発生した。`GamePhaseStore` は投票済みを把握していたが、
`get_tool_definitions()` と実際の LLM payload 生成が `player_id` を受け取らず、
本人固有の利用可否を判断できなかった。

投票後は票を変更できないため、本人にとって `vote` は「選べるが必ず失敗する手」になる。
この判定を prompt builder や実行器へ個別に足さず、`ToolExposure.split_for_phase` を
静的な世界宣言・会議フェーズ・本人の投票状態を合成する単一の入口とする。
`get_tool_definitions(player_id=...)` から最終的な LLM payload まで同じ本人 ID を運び、
投票済み本人からだけ `vote` を外す。未投票者の `vote` と全員の `speak` は残す。

`get_tool_definitions` は、本人向けの `player_id` と起動時の全員検査向けの
`for_every_player=True` のどちらか一方を必須とする。対象を省略した呼び出しを
全員向けとして扱うと、本人状態の運び忘れが従来動作へ黙って縮退し、今回と同じ
欠陥を再導入できるためである。`ToolExposure.split_for_phase` の
`voting_completed` も既定値を持たせず、呼び出し側が本人状態を明示する。

本人状態には生死も加わった。死者に出すツールの集合 (`DEPARTED_TOOLS`) を runtime から
`ToolExposure` へ移し、`split_for_phase` は必須引数 `departed` で受ける。幽霊ルール・
会議の状況行・会議開始の観測も同じ判断 (`offers_to_departed` と
`_split_spot_tool_names_for`) から文を決め、会議中の死者や投票済みの人に、出していない
`travel_to` / `interact` / `vote` を勧めない。`departed` に既定値を置くと、渡し忘れが
生者扱いへ黙って縮退し、死者に出さないツールが payload にも本文にも戻るためである。

投票の進捗は `MeetingVoteCastEvent` で全参加者に知らせるが、イベント自体に投票先を
持たせない。締切前に公開するのは投票者名と残り人数だけであり、構造化観測や trace の
別経路から投票先が漏れるのを防ぐ。投票者本人はツール結果で把握しているため配信対象から
外し、同じ事実による重複観測と余分な自己起床を作らない。

## 45. scenario event の世界文脈条件は既存の語義と状態の出所を再利用する

妨害の進行停止と複数人での解除をシナリオから宣言できるよう、
`ScenarioEventCondition` に `GAME_PHASE_IS` と `PLAYERS_AT_SPOT` を加える。
別の条件評価器は作らず、scenario event・reactive binding・個人結果規則が共有する
`ScenarioConditionEvaluator` に集約する。条件名と評価分岐の網羅性は
`KNOWN_CONDITION_TYPES` の双方向監査で固定し、未知名を永久に偽の条件として通さない。

`GAME_PHASE_IS.game_phase` は `GamePhase.value` の既知値だけを読み込み時に許可する。
評価時は `WorldRuntime` と同じ唯一の `GamePhaseStore` を provider 経由で読み、未配線を
`False` に縮退させず構成エラーとして止める。別 store を作ると、会議へ遷移しても条件が
自由時間を見続けるためである。

人数条件には新しい `PLAYER_COUNT_AT_SPOT` を作らない。interaction 条件に既にある
`PLAYERS_AT_SPOT` を scenario event でも同じ意味で使い、`target_spot` の
`graph.presence_at(...).present_entity_ids` が必要人数以上なら成立する。必要人数の既定値は
既存と同じ2人とする。`PlayerStatusRepository` と突き合わせると「その場に居る」の出所が
二つになり、同じ語が利用箇所ごとに異なる意味を持つため採らない。

この語義では down 状態の人物も在席数に含む。これは妨害操作に適した人物を意味するから
ではなく、既存の `PLAYERS_AT_SPOT` と意味を分岐させないためである。将来「動ける人数」が
必要になった場合は、既存語の意味を静かに変更せず、`is_down` を除外する別の条件として
意図を名前に表す。

どちらの条件も engine 内部の述語であり、tick や秘密の状態をプロンプトへ直接表示しない。
新しい永続状態も持たないため snapshot の追加配線は不要である。

## 46. 物体の存在・操作の公開・視認性を同じ空集合へ潰さない

物体が現在地に存在すること、その行為者へ公開できる操作があること、暗さの中で
物体を視認できることは別の事実である。公開操作が0件という理由だけで物体を
resolver候補から外すと、目の前に存在する物体へ「この場所に無い」と返してしまう。
一方、世界に操作が1件も宣言されていない情景用物体は、従来どおりinteract候補に
しない。

行為者の `PLAYER_STATE_IS` により全操作を伏せた物体は、操作名を空のまま対象として
解決する。未定義の操作名を送られた場合も、秘密の操作名や件数を列挙せず、条件に
宣言された本人向け `failure_message` だけを返す。これにより「担当ではない」という
次の判断材料を届けつつ、偽装版の存在は漏らさない。

暗さで見えない物体はresolver候補へ入れない。現在状態を作る同じ視認判定から、
暗さで伏せた名前を内部contextへ運び、LLMがその名前を指定した場合だけ
「暗くて見えない」と返す。候補一覧へ名前を出したり、暗所でも操作を実行可能に
したりはしない。これにより、不存在と視界不良を同じ失敗文へ潰さず、灯りを探す
行動へつなげる。

## 47. 提示後の状況変化と一覧外の選択を同じ失敗へ潰さない

LLM の判断はプレイヤーごとに並列で作り、世界への適用は順番に行う。同じ tick の
先行者が会議を始めると、後続者が自由時間の一覧から正しく選んだ `interact` でも、
適用時には会議中なので実行できない。このとき「一覧に出ているものから選ぶこと」と
返すのは、本人が実際に見た一覧と矛盾する。

「いま使えるか」は従来どおり `get_tool_definitions` を唯一の出所として実行時に判定する。
「選んだ時点で一覧に載っていたか」は `_LlmPhaseAResult.tools_payload` に保持された、実際に
LLM へ送った内容だけを出所とする。prompt 時の条件を後から引き直す経路は作らない。

現在は使えず、送信済み一覧には載っていた場合を `TOOL_BECAME_UNAVAILABLE` とし、状況が
変わったため実行できないことを伝える。最初から一覧に無かった場合は従来の
`TOOL_NOT_OFFERED_NOW` と案内を維持する。両者は本人の選択の正しさも、trace で分析すべき
原因も異なるため、同じ error code にまとめない。どちらも次 tick に起こし、変化後の一覧
から選び直せるようにする。

## 48. 襲撃の可否と目撃可能性を分け、派生 action は待ち時間を共有する

暗所だけで襲撃できる規則では、光源を持つ本人が部屋を `DARK` から `DIM` へ変える
だけで襲撃を受けなくなる。同室全体が明るくなること自体は光の性質として正しいが、
灯りが本人を無敵にするのは社会的推理の駆け引きにならない。一方、襲撃の
`witness_policy` が常に `ACTOR_ONLY` だと、明るい場所に第三者が居ても加害者を
目撃できず、「居合わせた者にしか見えない」という公開説明とも食い違う。

襲撃できるかと、誰の仕業か特定できるかを別の問いとして扱う。暗所用の
`strike_down` は従来どおり匿名かつ第三者へ対人観測を出さない。暗所以外で使う
`strike_down_in_light` は `SAME_SPOT` とし、居合わせた者へ加害者名と対象名を
届ける。暗所へ匿名の目撃文は足さない。倒れた身体の発見だけを情報源として残し、
襲撃だったと即座に確定させないためである。灯りは免疫ではなく、その場で起きた
ことに加害者の名前を与える道具になる。

明暗の action を別々に宣言しても、再使用間隔は一つである。同じ意味の action を
交互に使って待ち時間を迂回できないよう、`InteractionDef.cooldown_group` を共有キー
として宣言し、省略時だけ従来の `action_name` へ戻す。対人操作と物体操作の両方が
このキーを読み、物体操作では従来どおり object id も組み合わせる。待ち時間ストアを
分けず、既存 snapshot の文字列キー形式も変えない。

`cooldown_group` は空文字や `object:` 接頭辞を読み込み時に拒否する。後者は物体操作の
内部キーに予約済みで、許すと対人と物体の待ち時間が静かに衝突するためである。
既存 snapshot では、group が旧 action 名と異なる宣言だけキーが変わり、その行為の
過去の待ち時間が一度失われる。`station_drill` は既存 action 名の `strike_down` を group
に使うため、暗所襲撃の保存済み待ち時間は維持される。

エージェントへ灯りの意味を伝える経路は、prompt に出ない item description に頼らない。
全員が読める当番表の `read_board` 結果へ共有規則を置く。item description も作者向け
宣言として実態に合わせるが、エージェントへの伝達を担ったとはみなさない。

## 49. tool にそのまま渡せる文字列だけを引用符で囲む

run 016 / 017 で、LLM が action の意味ラベルや、条件ヒントまで含む
表示行を `action_name` に送り、計 8 件失敗した。物体名・人名・移動先名は
引用符つきだったが、action だけが `当番表を読む (read_board)` のように
「渡す値」と「渡さない説明」を同じ括弧に入れていた。

プロンプトの規約を「引用符で囲まれた文字列だけが、tool 引数へそのまま
渡せる値」とする。action は `当番表を読む → "read_board"`、必須パラメータは
`"text" が要る`、接続は `"集会室の扉" → "連絡通路"` と表す。意味ラベルや
条件ヒントは引用符で囲まない。

整形処理ごとのテストだけでは、新しい表示経路の書き忘れを止められない。
`build_llm_context` が同時に作る `current_state_text` と `tool_runtime_context` を照合し、
全 target の `display_name` と `available_interactions` が引用符つきで本文にあることを
確かめる。起動時は全 player を検査して落とし、run 中は実験データを失わないよう
`prompt_argument_contract_violation` trace に残して続行する。

起動時検査の snapshot 構築では、monster や倒れた人の初回観測通知を一時的に
止める。検査は読み取り専用であり、Encounter Memory の「一度きり」を先に消費
してはならない。observer は検査終了時に必ず復元し、最初の prompt 構築で通常どおり
観測と `schedules_turn` を発火させる。

除外リストは持たない。暗所で伏せた物体は snapshot 構築時に落ち、targets に登録
されないため検査入力に現れない。将来それを targets に載せるなら、本文から
指定できない候補を作ることになるため、この検査が止めるのが正しい。
この変更は tick ごとに変わる `current_state_text` の書式だけを変え、プレフィックス
キャッシュに載る静的セクションは変えない。

## 50. 直近の出来事の時刻は記録時の世界内絶対時刻で固定する

「直近の出来事」は一度追加した行が変わらない安定した接頭辞として設計されている。
しかし描画時刻から「たった今 / 数分前 / さっき」を毎回計算すると、同じ entry の
本文が時間経過だけで書き換わる。この不変条件を回復するため、観測と行動結果へ
記録時の `game_time_label` を焼き込み、描画側は保存済みのラベルだけを使う。

相対ラベルを記録時に凍結する案は採らない。実 run
`v4coop_0731_007` の 6,983 行を測ると、凍結ラベルと描画時点の本来のラベルが
食い違う行は 4,143 行 (59.3%)、行動行では 3,669 / 4,980 行 (73.7%) だった。
「たった今」のまま古くなる文面は安定していても嘘になる。世界内絶対時刻なら、
記録後に変わらず、エージェントが暮らす世界の時間としても正しい。

調査で絶対時刻が欠けていたのは、通常の観測ではなく4つの配線だった。行動結果、
heartbeat、行動失敗、ループ警告の各境界で時刻または provider を必須にし、5つ目の
渡し忘れを既定の `None` へ縮退させない。旧 prompt の欠落479行は heartbeat 207行、
行動失敗261行、ループ警告11行で、通常の trace 観測416件には欠落がなかった。

この判断が保証するのは「追加済みの行本文が後から変わらないこと」と「時刻表現が
真実であること」だけである。行動結果ストアは最新20件のスライディングウィンドウで、
追加のたびに先頭行が落ちるため、この変更単独でプレフィックスキャッシュの命中率が
上がるとは主張しない。

## 51. 観測と行動結果は記録時から一つの時系列へ置く

観測と行動結果は届く入口が違うため別々のストアに保存され、描画時にだけ時刻順へ
合流していた。この分割は記憶の意味によるものではなく、観測は15件でL4へ畳む一方、
行動は20件の窓から古いものを落とすという別々の政策を生んだ。中期記憶へ自分の行動が
一件も渡らない原因にもなっていた。

記録時の表現を `UnifiedRecentEventEntry` に統一する。共通の外枠は
`occurred_at`、`game_time_label`、`kind` だけとし、観測と行動結果の固有項目は既存DTOを
payloadとして保持する。18項目ある行動DTOを平坦化して観測へ多数の `None` を持たせない。
既存の消費側には種類別の読み取り口を渡し、この段階では描画件数、観測15件でのL4生成、
行動・観測それぞれの保持上限を変えない。「格納場所の統一」と「窓の政策変更」を別PRに
して、本文の変化がどちらに由来するかを切り分けられるようにする。

`DefaultPromptBuilder` には統一ストアを必須依存として明示的に渡す。旧2リストから描画する
退避経路は残さない。任意配線やprivate属性の検査で旧経路へ縮退できると、後続で窓の政策を
変えたときに「変えたつもりが効いていない」状態が静かに生まれるためである。

world snapshot は `recent_event_store` 一つだけを保存する。旧
`sliding_window`、`observation_buffer`、`action_result_store` の3 payloadは復元入口で
新形式へ変換してから、通常の厳格なsubsystem網羅検査へ渡す。一部だけ存在する旧形式や、
旧形式と新形式の同居は部分復元を招くため拒否する。保存は新形式だけとし、旧形式を
再生産しない。

## 52. prompt dataset の Being 配線を episodic 記憶から独立させる

prompt dataset の各行は、世界内 player ではなく継続する主体を表す `being_id` を必須と
する。しかし従来は、この ID を解決する補助 Being 配線が episodic 記憶の有効化に
偶然依存していた。そのため記憶を省いた lean profile では、記録を有効にすると設定検証で
拒否され、run 016 / 017 の prompt を後から再生できなかった。

記録機能と記憶機能は別の関心事として扱う。`PROMPT_DATASET_CAPTURE_ENABLED` が有効なら、
episodic 記憶が無効でも `create_world_runtime` の起動中に補助 Being を配線し、全参加者を
provision する。設定上の相互依存は削除し、最初の LLM 呼び出しより前に実際の `being_id`
を解決できない構成は起動時に止める。公開 tool の集合や世界の振る舞いは変えない。

capture も episodic 記憶も無効な構成でも、いまは起動時に配線する。会った相手の記録を
Being が持つようになり (design_decisions D1520)、初期配置の同席を最初の手番より前に
Being へ記録するため。

**その後**: `PROMPT_DATASET_CAPTURE_ENABLED` は記憶ではない設定の片付け (#1631) の #1795 で消し、`make experiment` の run はいつも保存する。起動時の Being の配線も、条件の無い 1 か所にまとめた。

**その後**: 古いエピソードの配線 (`LLM_EPISODIC_ENABLED` / `LLM_EPISODIC_SUBJECTIVE_ENABLED`) は記憶の部品の撤去 (#1631) の #1801 で runtime から外した。Being の配線は、もともとどちらにも依存しない形で組んである。

## 53. semantic top-K は選抜順位と表示順を分ける

`【関連する学び】` の候補は recency、importance、relevance の score で top-K を
選ぶ。recency は描画時刻で変わるため、同じ集合でも候補の順位だけが入れ替わり、
プロンプト本文が変わっていた。見出しは関連度順を約束しておらず、表示順位を
エージェントへ伝える意味もない。

選抜は従来どおり score 順で行い、表示だけを `entry_id` 順へ固定する。同じ集合なら
時間が進んでも同じ文字列になり、集合が変われば本文も変わる。score 順を失うのではなく、
選抜と描画へ別々の責務を持たせる判断である。

`stable_to_volatile` では、実測で 36〜62% 変化する semantic top-K を L4 より上へ
置かない。安定した L4 と直近出来事の先頭を先に置き、予測の後ろで
`【関連する学び】`、`【関連する記憶】`、その本文に内包される想起見出しをまとめる。
直近の出来事が想起を引き起こすという読み順にも合う。`legacy` は A/B 比較用の旧順序
そのものに価値があるため変更しない。この変更は原則との不整合と順位の揺れを直すが、
キャッシュ改善量は実測前に主張しない。

【関連する学び】 (`SEMANTIC_PASSIVE_TOP_K` と `SemanticPassiveRecallService`) は、記憶の部品の撤去 (#1631) の #1786 で消した。

## 54. 直近の出来事は自分のターンを単位に、まとめて畳む

観測と行動結果を一つのストアへ統一しても、観測15件と行動20件という旧来の別々な
表示政策を残すと、流入の多い観測のほうが先に消え、自分の行動だけが長く残る。
出来事の種類を一方だけ数えて窓を決めず、前回の自分のターン完了から今回の完了までを
一つの bucket とし、直近 N bucket を同じ時系列で保持する。

境界は episodic 再解釈の内側ではなく、直列・並列の両方が通る LLM wave の決算地点に
置く。reason-first の複数回の評価と行動は一つの判断なので1ターン、自己再スケジュールで
別 wave に進めば別ターンとする。短期記憶の全実装が `complete_turn` を必須実装するため、
lean profile や新しい実装で通知が黙って消える任意配線は作らない。

窓は毎ターン最古を落とすスライド方式にしない。既定では cap 20ターンまで追記し、到達時に
古い10ターンをまとめてL4へ畳み、残る10ターンから再び積む。これにより先頭が変わるのは
10ターンに一度となり、畳んだ直後も窓が空にならない。cap と畳む数は profile で変更できるが、
`0 < 畳む数 < cap` を起動時に強制する。

この段階のL4入力は従来どおり観測だけとし、行動を含める変更は別に測る。ターン bucket の
見出しも prompt へ出さず、表示は従来の一つの時系列を保つ。この判断が保証するのは窓の
単位と先頭の安定性であり、プレフィックスキャッシュの改善量は実 run の前に主張しない。

## 55. L4 へ観測と自分の行動を一つの時系列で渡す

観測だけを L4 入力にすると、自分の行動はターン窓から外れた時点で短期記憶から消え、
中期記憶には周囲の出来事から推測した行動しか残らない。観測を受けて行動した因果を保つ
ため、畳んだターン群の `UnifiedRecentEventEntry` を種類で分けず、`occurred_at` 順の
一つの時系列として L4 生成へ渡す。

入力行は【直近の出来事】と同じ描画規則を使う。これにより、エージェントが読んだ出来事と
要約器が読んだ出来事を同じ表記で比較でき、行動には `[行動]` の区別も残る。見出しには
畳んだターン数と出来事数を併記し、観測だけ・行動だけのターンも同じ入口で扱う。

この段階では L4 の system prompt と出力形式を変えない。何を優先して残すかは入力を実際に
通した結果を見てから別に決める。LLM 失敗時の template fallback も通常入力と同じ統一時系列
を使い、失敗したときだけ行動が消える差を作らない。L5 は引き続き退避された L4 一件だけを
入力とする。

## 56. 行動履歴の tool 引数は引数名で分類して構造化保存する

行動の自然文表示は意味を読み返すためのもので、tool に渡した値を復元する材料ではない。
表示名と正規名が異なる interaction では、自然文を写したエージェントが
`action_name` の解決に失敗した。特定の tool だけを補修すると同じ問題が別の引数で
再発するため、JSON Schema の property 名を単位に扱いを分類する。

完全一致が必要な名前・列挙値・構造化値は `identifier_arguments` に文字列として保存し、
配列内部の名前も引用符を含む正規 JSON のまま保つ。自由文は履歴を重複して肥大化させず、
呼び出し形を示せるよう `free_text_argument_names` に引数名だけを残す。
`inner_thought` と `expected_result` は直後の専用行に既に出るため省略する。分類は tool 名で
分岐せず、同名の引数には同じ規則を適用する。

露出可能な tool catalog の全 property は起動時に分類漏れを検査する。検査は実行器の
配線確認とは分離し、分類忘れと別の構成不備を同じ失敗へ潰さない。成功した core action と
generic な失敗経路の両方が同じ射影関数を通り、snapshot は構造化した値を保存する。旧 payload
には存在しないため空へ倒し、復元できない引数を捏造しない。この段階では記録だけを変え、
プロンプトへの表示は別 PR で扱う。

**その後**: 行動ごとの結果の予想 `expected_result` は Issue #1631 で消した。分類の表からも外したので、`inner_thought` だけが専用行に出るため省略される。

## 57. 行動履歴は意味の表示と再利用できる呼び出しを併記する

行動の自然文は物語として読み返せる表示名を優先する。一方、表示名は tool の正規引数とは
限らず、引用符で囲むと「そのまま引数へ写せる値」という prompt の規約に反する。
自然文を内部名だけの機械的な表記へ戻さず、全行動の直後に `呼び出し:` の続き行を置いて
二つの目的を分ける。

完全一致が必要な文字列は JSON の引用符で囲み、配列内の文字列も引用符を保つ。自由文は
値を再掲せず、`content=本文` のように引用符なしの日本語プレースホルダで書く。
`inner_thought` と `expected_result` は既存の専用行を使い、呼び出しには重複させない。
成功した行動は引数が無くても `listen()` のように必ず表示し、行動ごとに省略規則を
推測させない。失敗した行動は例外とし、通らなかった値を引用符つきの手本として
残さない。失敗行には `[失敗]`、`error_code`、復帰文が並ぶため、省略理由はその場で
読める。

続き行は既存の行動エントリと一緒に一度だけ描画し、別 section や描画時刻への依存を
増やさない。後続 entry の追記で既存行は変わらず、ターン窓の先頭安定性を保つ。
自然文側では対象名の引用符だけを残し、tool へ渡せない interaction の表示名からは
引用符を外す。

tool の静的な説明や失敗後の復帰文に、シナリオに存在するとは限らない
`action_name` の具体例は書かない。run 018 では静的に例示した名前をモデルが写し、
実際には宣言されていない操作を繰り返した。使える名前の真実の出所は毎回の
「現在の状況」の対象行だけとし、静的文面はそこの引用値をそのまま写す規則だけを伝える。

**その後**: `expected_result` の専用行 (`[予測: …]`) は Issue #1631 で消した。専用行を使うのは `inner_thought` だけになった。

## 58. 個別 outcome を world snapshot の独立 subsystem として保存する

`PlayerOutcomeRegistry` の `DEAD` / `EJECTED` / `RESCUED` / `STRANDED` は、
勝敗上の確定状態である。身体の可動状態を表す `is_down` や、graph の配置からは
正しく復元できない。`is_down=True` は死亡確定前の蘇生可能な状態でもあり、
未配置は追放だけでなく初期未配置でもあり得るためである。

個別 outcome は `player_vitals` へ混ぜず、`player_outcome` world subsystem として
独立保存する。復元は `set_outcome` を再実行せず、player 集合を検証した後に
callback 無しで registry 全体を置換する。再開時に過去の死亡・追放を新しい観測や
trace として再通知しないためである。

この subsystem より前の world snapshot には outcome を推定する情報が無い。
分からない値を `UNRESOLVED` として補うと、死者や追放者が勝敗・投票母数へ戻った
壊れた世界で実験を続けてしまう。そのため完全な再開形式の top-level
`schema_version` を 3 に上げ、旧版の strict restore は理由を示して開始前に拒否する。
通常の非 strict 読み込みは調査・互換用途として旧版を引き続き受理するが、実験再開
には使わない。

## 59. world flag は状態の反復ではなく変化を因果つきで記録する

作業完了などの `SET_FLAG` は観測を生まない場合があり、最終状態や登場人物の発言だけ
では、どの行動で何が進んだかを実験後に確かめられない。flag を変更する各サービスで
個別に trace を書くと、新しい変更経路を足したときに観測だけを忘れる。そのため
`MutableWorldFlagState` を単一の絞り点とし、変更前後の集合差分を flag ごとの
`world_flag_changed` として通知する。

変更経路と行為者は状態だけから復元できないため、`add` / `remove` /
`replace_from_interaction` は `WorldFlagMutationContext` を必須とする。行為者が存在しない
経路でも `None` を明記させ、呼び出し元の渡し忘れを既定値で隠さない。同じ値への再設定は
記録せず、複数 flag が変われば安定した順序で一件ずつ記録する。現在の状態の集計はこの
変化列から分析側で作り、毎 tick 同じ値を重ねて因果を薄めない。

snapshot 復元も同じ状態置換 API を通すが、過去の成立を新しい出来事として再通知しては
ならない。復元側は `snapshot_restore` という変更元を明示し、状態オブジェクトではなく
trace への配線で除外する。これにより差分検出の真実の源を一つに保ちつつ、復元と実行中の
変化を混同しない。

## 60. 生死状態は一つの層へ潰さず、問いごとの query で読む

プレイヤーの生死に関する判断は、手番、世界観測、投票資格、通報できる身体で意味が
異なる。`is_down` と `PlayerOutcomeEnum` を各入口で別々に読むと、新しい状態を足した
とき一部だけが古い規則を使い続ける。一方、すべてを「活動中か」という一つの真偽値へ
潰すと、現在でも意図して異なる答えを返している状態を壊す。

そのため `PlayerLifeQuery` に問いを分け、各公開入口は同じ instance を共有する。
`can_take_turn` は確定済み outcome 全般と `status.can_act()` を見る。
`can_receive_world_observation` と `has_reportable_body` は現在の `is_down` を見る。
`can_vote` は `is_eliminated` と身体の有無を見る。特に `RESCUED` / `STRANDED` は手番を
持たないが投票資格を持つため、`can_take_turn` を投票判定へ流用しない。移動中の手番抑止は
生死の問いではないので、従来どおり手番入口に残す。

追放者は `is_down=False` なので、世界観測の受信条件だけを見れば受信可能である。実際に観測が
届かず身体も通報されないのは、graph から配置が消えて宛先や対象として見つからないためで
ある。この偶然の守りを query の規則として捏造しない。将来、去った主体へ別の位置を与える
ときは、知覚や身体の規則を明示的に変える必要がある。

この整理では活動中、蘇生可能な昏倒、死亡確定、追放、救助、取り残しの六状態について、
query 自体の答えと実際の公開入口を同時に固定する。query の単体試験だけでは、正しく作った
判定が本番配線から呼ばれない欠陥を検出できないためである。この段階では層の概念や幽霊の
手番を導入せず、既存の振る舞いを変えない。

## 61. 終局結果の世界固有文はシナリオが宣言する

`DEAD` / `EJECTED` / `RESCUED` / `STRANDED` は世界を跨いで使う結果であり、汎用ランタイム
の語彙である。一方、「島に取り残された」「宇宙船へ帰還した」のような場所・世界観を含む
通知文はシナリオの表現である。結果の意味と、その世界でどう語るかを同じ層へ置かない。

シナリオ固有の文型は `metadata.player_outcome_messages` に結果名ごとに宣言し、未宣言時は
場所を決めつけない汎用文を使う。文型は `{player_name}` だけを許可し、未知の結果、未知の
置換項目、書式指定、変換指定、人物名を含まない文型は読込時に拒否する。実行時に不正な
文型を握りつぶしたり、別世界の既定文へ縮退させたりしない。

文の整形は application の小さなサービスへ置き、`WorldRuntime` は読込済みの表示方針を
渡して結果文を受け取るだけにする。通知範囲、構造化観測、起床指定は表示文とは別の判断
なので、文型の差し替えに連動させない。新しい舞台で既存 outcome を使うとき、世界固有の
名詞を汎用ランタイムへ条件分岐として追加しない。

## 62. 確率条件の乱数位置は世界状態として保存する

`PROBABILITY` 条件は scenario event、reactive binding、player outcome rule が
一つの乱数源を共有し、条件木の短絡順に値を消費する。seed だけを設定へ残しても、
snapshot 再開時に乱数列の先頭へ戻るため、連続実行とは異なる出来事が発火する。
したがって完全な world snapshot は seed ではなく `random.Random.getstate()` が
表す現在位置を独立 subsystem として保存する。

乱数源は特定の評価器の非公開属性ではなく `WorldRuntime` が所有し、評価器には同じ
実体を注入する。復元時も新しい乱数源へ差し替えず、既に各 stage が参照している実体に
`setstate()` する。これにより条件評価器を共通基盤へ置き換えても、保存形式と所有境界を
維持できる。

内部状態は pickle ではなく、版、整数列、ガウス分布用キャッシュを明示した JSON として
保存する。復元値は別の実体で完全に検証してから本番の乱数源へ適用し、壊れた入力で
稼働中の位置を半端に変えない。この状態を欠く旧 world snapshot は確率的な因果を再現
できないため、完全な再開形式を top-level `schema_version=6` とし、旧版の strict restore
は開始前に理由つきで拒否する。
## 63. 述語評価は真偽値の互換入口より内側で理由を保持する

条件評価を真偽値だけで返すと、正常な未成立、評価入力の不足、評価器の未対応がすべて
`False` へ潰れる。呼び出し側は発火しなかった理由を観測できず、interaction では判定時に
分かっていた失敗条件を一度捨て、後から表示文を手掛かりに推測する問題も起きた。

用途を跨ぐ評価結果は、成立可否に加えて `reason_code`、失敗した述語、根からの子番号列、
不足した文脈名、任意の失敗文を持つ `PredicateResult` で表す。成立結果に失敗情報を混ぜる、
文脈不足なのに不足項目を示さない、といった矛盾は値オブジェクトの構築時に拒否する。
`failed_path=()` は根そのもの、`(1, 2)` は2番目の子の3番目の子を表し、将来の trace と
合成条件でも同じ規則を使う。

既存利用側を一度に壊さないため、各評価器では `PredicateResult` を返す入口を正本とし、
従来の真偽値や tuple はそこからの薄い射影として段階移行する。最初の移行対象は、すでに
失敗条件を返す必要があった interaction の前提条件とする。公開済みの `can_interact` と
`evaluate_preconditions` の戻り値は保ち、実行経路は正本の結果から例外へ失敗条件を運ぶ。

この段階では既存の未成立を新たに文脈不足へ分類せず、ゲーム挙動を変えない。scenario
条件へ適用するときは、`NOT` が文脈不足を真へ反転しない規則、AND / OR の短絡順、確率条件
の乱数消費数、reactive binding と一度限りの player outcome rule が文脈不足をどう扱うかを
試験で固定してから移行する。
## 64. 判定に文字列を使わない。値を持っているなら値を渡す

**何を**: 分岐の判定材料に、自分たちが組み立てた表示文やシナリオ作者の自由文を
使わない。判定に要る値を持っている層から、値のまま渡す。

同じ形の欠陥が 2 箇所にあり、どちらも「値はあるのに文字列から読み直す」だった。

**#380 (系統1): シナリオ作者の自由文に依存していた**

`interact` の失敗 remediation を `failure_message` の日本語キーワード
(`"採り尽く"` `"枯渇"` `"すでに"` 等) で切り替えていた。`failure_message` は
「エージェントに読ませる文」として書かれているのに、分類キーとしても二重に使われて
いた。作者は自分の言い回しがシステムの分岐を変えることを知らない。

実測すると当たっても外れても害だった。実 run 43 本の 679 件のうち「時間で回復」は
251 件で、**キーワードに当たるのは 31 件だけ、しかもその 31 件は全部逆の助言**だった
(作者が「風がまた運んでくるのを待つしかない」と書いた上から「別の場所を選べ」を
重ねていた)。同じ壁に 96 回当たっている run がある。

判定した瞬間は条件の種別・対象・要求値を知っているのに、`(False, message)` の文字列
だけ返していた。失敗した条件を例外に載せ、`reactive_bindings` と突き合わせて区分する
形に変えた。

**系統2: 自分たちの表示文に依存していた**

想起の検索語を決めるのに `need_lines` (`"空腹: 危険（68/100）"`) を
`line.startswith("空腹") and ("高い" in line or "危険" in line)` で読み直していた。
`AgentNeed.need_type` と `is_high` がその判定そのものを持っている。`("高い" or "危険")`
は `is_high` (>= 0.6) と完全に等価で、既にある述語を文字列で再実装していた。

**なぜ**: 表示文は変わる。言い回しを整えるリファクタリングで分岐が黙って変わり、
テストは通る。シナリオ作者の自由文なら、作者が結合を知らないまま挙動を変える。

**どう守るか**:

- 判定材料は値のまま運ぶ (`failed_condition` / `need_states`)
- 閾値を写さない。`is_high` のような述語があるならそれに委ねる。写すと片方だけ古くなる
- **配線が抜けても例外が出ない**ことに注意する。材料が届かなくても既定へ倒れるだけ
  なので、実 runtime を通して「材料が実際に載っているか」を見る試験を別に置く
  (#1050 では材料を運ぶのをやめる変異が 39 passed で素通りした)

**関連**: #380 / #1050 / 系統2。判定ではなく**呼び名の所有者**をどこに置くかは別の
論点で、#1054 と判断 #61 を参照。

## 65. enum で分岐するなら表にする。2 分岐は静かに嘘をつく

**何を**: enum の値で表示や挙動を分けるとき、`if x == A else B` の 2 分岐を書かず
`dict[Enum, ...]` の表にして、enum 全件を覆う網羅テストを付ける。

**なぜ**: 2 分岐は「A 以外を全部 B として扱う」。値が 2 つしかない間は偶然正しく、
3 つ目を足した瞬間に静かに嘘をつく。

実例として `AgentNeed.describe` が `"空腹" if need_type == HUNGER else "疲労"` だった。
渇き (THIRST) を足すと **「疲労: 危険」と表示される**。`NeedType` が 2 つだから偶然
正しかっただけである。

同型の問題を `interaction_condition_hint_text` でも直した。そちらは表だったが
`.get(value, value)` で**未知値に生値を返して**いたため、enum が増えるとプロンプトへ
内部識別子が漏れた (判断 #61 の ID 露出方針の裏口)。

**どう守るか**:

- `(enum, 表)` の組を module 定数として公開し、網羅テストがそれを走査する
- **走査リスト自体が縮む形も塞ぐ**。`interaction_condition_hint_text` では走査対象から
  表を 1 つ外す変異が 139 passed で素通りした。モジュール内の `_*_LABELS` を数え上げて
  突き合わせる形にした
- **未知値を静かに倒さない**。生値を返す / 既定値へ倒すのではなく、`KeyError` で落とす。
  `NeedType` が 2 つの間は 2 分岐へ戻す変異が挙動として等価なので、**倒れ方の違い**
  だけが検出できる差になる

**関連**: #1045 / 系統2。判断 #61 (終局結果の世界固有文) と #1043 の「ID を
プロンプトに出さない」方針の裏口を塞ぐ位置にある。判断 #64 と対になる
(あちらは「文字列で判定するな」、こちらは「分岐は表にせよ」)。

## 66. 内部 ID をプロンプトへ出さない。露出は総当たりで見張る

**何を**: LLM に出すツール引数で内部 ID を要求しない。指させるのは**プロンプトに
表示されている名前**だけにする。露出ツール全件を総当たりして、引数名が `_id` /
`_ids` で終わらないこと、説明文に「ID」「識別子」が出ないことを検査する。

**なぜ**: 判断 #3 (揮発ラベルを捨て名前で指す) の帰結だが、**ID 露出は静かな失敗の
入口そのもの**だった。#853 の実例。

`prepare_action` は `action_id` を要求し、説明文は「準備するアクション**ID**（操作
対象に表示される協力アクション名）」と書いていた。**表示されていないものを指定せよ
と言っていた**ので、エージェントは推測するしかない。そして推測は `success=True` で
返り、同期登録は黙って skip されていた。3 つが重なって

    宣言が到達不能 → 推測せざるを得ない → 推測は成功と返る → でも何も起きない

という完全な静かな失敗になっていた。名前で指す形にすると、指せる値は必ず表示されて
いるものになり、**入口が閉じる**。

実測すると、露出中の 16 ツールのうち ID を要求していたのは `prepare_action` だけ
だった。方針は他で守られていて、1 つだけ抜けていた。**だから 1 件直すのではなく、
次に足す人が同じことをできない形にする。**

**どう守るか**: `tests/application/llm/test_tool_schemas_do_not_expose_internal_ids.py`
が `get_spot_graph_specs()` の全件を回す。例外表は空にしてあり、作るときは理由を
書く。休眠文脈 (`quest` / `shop` / `trade`) にも ID 露出があるが、この集合に入らない
ので配線するときに直す。

**関連**: 判断 #3 / #853。ラベル表からの ID 漏れは判断 #65 で塞いだ。

## 67. 想定外例外の発生位置は引数で受け、呼び方を AST で縛る

**何を**: 想定外例外を LLM に伏せて trace に残すヘルパは、発生位置 (`location`) と
段 (`stage`) を引数で受ける。ハードコードしない。そのうえで**全呼び出し箇所を AST で
検査**し、`location` が囲っている関数のどれかの名前と一致することを縛る。

**なぜ**: #846 は `location` を `"_use_item"` でハードコードしていた。use_item だけ
に入れた仕組みなので当時は足りたが、他のハンドラへ広げるとハンドラごとに同じ関数を
複製することになる。

引数にすると**引数化そのものが新しい静かな失敗を作る**。コピー元の `location` を
貼り替え忘れると trace が嘘の場所を指し、**動くしテストも落ちない**。`_use_item` を
調べても該当経路が無い、という形で人間の時間だけが溶ける。

実行時には検証できない。この関数を通るのは例外経路だけで、全経路を通す試験が書ける
なら #847 自体が要らない。だから**ソースの構造**を見る。

**課す制約 5 つ**:

| 制約 | なぜ |
|---|---|
| `location` は文字列リテラル | trace の値から呼び出し箇所へ grep で辿れる |
| `location` は囲っている関数のどれかの名前と一致 | 貼り替え忘れを止める |
| `stage` は文字列リテラル | 同上 |
| 同一 `location` 内で `stage` が重複しない | 2 つそろって場所が一意に決まる |
| ヘルパ名を変数や `partial` に束ねない | 束ねると `location` のリテラルが消え、**上の全部が無効になる** |

最後の 1 つが一番効く。`partial(_unexpected_exception_result, location="_totally_wrong")`
を置くと嘘の location が **13 passed で通った**。C で同じリテラルが 30〜40 個並ぶと
必ず束ねたくなるので、束ねること自体を禁じる。**冗長にリテラルを書き写す形を強制
する**のが方針で、束ねたくなったら試験を消すのではなく見張り方を先に設計し直す。

**location の定義**: 例外を**捕まえた関数の名前**。ツール名でもハンドラ名でもない。
委譲先の helper で捕まえたなら helper の名前を書く。`trace.jsonl` の値をそのまま
grep すればソースの `try` に着く、という対応を保つため。

**関連**: #846 / #847 / `docs/exception_boundary_design.md` §5。

## 68. 宣言したのに効かない形は、読み込み時か corpus 監査で落とす

**何を**: シナリオの宣言が「書いたのに効かない」状態を、実行時に静かに縮退させず
**宣言した時点**で落とす。読み込み時に落とせないもの (既存シナリオを壊す等) は、
corpus 全体を走査する監査テストで落とす。

**なぜ**: 実行時の縮退は誰にも見えない。#383 / #853 / #1045 が同じ形だった。

**warning は構造ではない。** `scripts/run_scenario_experiment.py` の logging は
`format="%(message)s"` で FileHandler も無く、警告は run 冒頭の stderr に**レベル名
なしの 1 行**として流れるだけで `OUT` 配下には残らない。
`docs/trace_observability_review.md` の手順で run 後に確認しても検出できない。

だから #383 では warning を足したうえで、`data/scenarios` と
`tests/fixtures/scenarios` を全走査して落とす監査テストを別に置いた。既存の
`test_interaction_action_name_audit.py` と同じ形である。

**警告の粒度を先に測る。** #383 の issue は「状態更新があるのに narrative が無い」
向きごとに警告する案だった。実装前に数えると **59 件警告し、うち 48 件が主要実験
シナリオから出た**。それらは資源の枯渇で、interact の結果として本人に伝わるため
narrative を書かないのが正しい。**ノイズを出すと人が警告を無視するようになり、
検出器が死ぬ。** 「binding 全体が無音のときだけ」に絞ると 7 件、主要実験シナリオ
から 0 件になった。

**意図的な無音は明示させる。** `narrative_on_true: ""` を書けば通す。空文字は挙動上
無音と同じだが、**書き忘れではないという意思表示**になる。出荷シナリオで警告が
鳴り続ける状態は上のノイズと同じ害があるので放置しない。

**関連**: #843 (前例) / #383 / #853 / #1045。

## 69. 呼び名の所有者は「値の集合を誰が決めるか」で分ける

**何を**: 表示の呼び名をコードが持つか、シナリオが宣言するかは、**その値の集合を誰が
増やせるか**で決める。

| 概念 | 値の集合を決めるのは | 呼び名の所有者 |
|---|---|---|
| 天候 / 明るさ / 気温 | engine の enum | コード (既定) |
| 時刻帯 | **シナリオ** (`DayNightPhaseDef` は自由命名) | **シナリオ** (`display_text`) |

**なぜ**: シナリオが値を増やせるなら、コードの表は必ず追いつかない。実際に腐って
いた。`v3_coop` / `v4_coop` が `predawn`(未明) を宣言しているのに、コードの表は
`morning / noon / afternoon / evening / night` で、**`predawn` が無く `afternoon` は
どのシナリオも宣言していなかった**。両方向にずれていた。`predawn` を条件に書いた
瞬間 `"predawnのみ"` と生値が出る。判断 #61 (終局結果の文はシナリオが宣言する) と
同じ「写しは腐る」である。

**未知値の扱いは選ばずに済ませる。** 表示側で「生値を出す / ヒントを落とす」の
どちらを選んでも悪い (前者は ID 漏れ、後者は実在する制約を隠す)。**未知値がそこへ
来ないようにする**のが正しい。`required_lighting` は既に `LightingEnum` 名を loader
で検証していたのに、**天候と時刻帯だけ素通りしていた**。天候は enum 名、時刻帯は
そのシナリオが宣言したフェーズ名と照合する形へ揃えた。

**残っている論点**: 「engine の enum なのに呼び名はシナリオが持つ」case が判断 #61
にある (`PlayerOutcomeEnum`)。この表と #61 を分ける基準は「**別の舞台で嘘になるか**」
で、#61 の本文にその線が書かれている。独立した判断として明文化するのは #1054 で扱う。

**関連**: 判断 #61 / #1045 / #1054。

## 70. シナリオ述語の trace は実際の根評価を一度だけ記録する

**何を**: scenario event、reactive object / passage binding、player outcome rule が
実際に行った述語の根評価ごとに、`scenario_predicate_evaluated` を 1 件記録する。
成立可否だけでなく、用途と所有者、失敗した条件種別と経路、不足文脈、実際に消費した
確率値を残す。

**なぜ**: 発火した効果だけでは、条件不成立・文脈不足・確率抽選外れのどれで未発火に
なったかを区別できない。一方、trace のために述語を再評価すると、`PROBABILITY` が
乱数を余分に消費し、観測を有効にしただけで世界の進行が変わる。

**どう守るか**:

- 各実行段階は診断つき評価入口を 1 回だけ呼び、同じ `PredicateResult` を分岐と trace に使う
- 確率値は評価したその場で保存する。乱数状態の複製や trace 用の再評価は行わない
- AND / OR の短絡で未評価だった確率条件は記録しない。確率 0 / 1 は従来どおり 1 回引く
- once 発火済み、チェーン待ち、確定済みプレイヤーなど、述語自体を評価しなかった
  方針上のスキップはこの trace に混ぜない
- 記録器は provider から実行時に解決し、`set_trace_recorder` による後付け・差替えへ追従する
- trace の取得・書込み失敗は警告に留め、世界処理を停止させない
- 重複排除や変化時だけの記録は行わない。未発火理由の時系列を失い、再開境界を跨ぐ
  新しい状態管理が必要になるためである

この trace 自体は世界状態を持たない。確率列の再開連続性は判断 #62 の
`scenario_predicate_rng` が担う。

**関連**: #1046 / 判断 #62 / 判断 #63。

## 71. 共通述語は意味が同じ葉から移し、用途固有の出口は残す

**何を**: 条件系を共通化するとき、名前や比較演算が似ているだけで一つの型へまとめない。
複数用途で対象・入力・真理値が同じ葉だけを型付き述語へ昇格し、各用途の失敗文、勝敗、
効果、評価順は用途側に残す。

最初の対象は `FLAG_SET` とする。scenario event系、game end、interaction、通路条件、
発見条件の5経路で、いずれも「完全一致する名前が世界フラグ集合に含まれるか」という意味が同じ
だからである。各経路は既存DTOを共通の `FlagSetPredicate` へ変換し、共通評価核の結果を
既存の戻り値へ戻す。

**なぜ**: 一度に全条件を統合すると、同じ名前に隠れていた対象範囲の違いまで潰してしまう。
たとえば場所条件は、scenarioの世界評価では任意のentity、対象者評価では本人、game end
では明示されたplayer集合のANY/ALLを意味する。単一の `AT_SPOT` へまとめるとどれかが嘘に
なる。探索回数も比較は `>=` だが世界tickではない。

**どう守るか**:

- 共通述語は種類ごとのfrozen dataclassとし、任意項目の集合を新しい名前で作り直さない
- 評価文脈では `None`（未配線）と空集合（正当な状態）を区別する
- 共通評価核は表示文・勝敗・traceを持たず、`PredicateResult`だけを返す
- 通常の不成立だけを用途固有の結果へ戻す。入力不足・評価器未対応は通常不成立へ
  潰さず、構造化結果を返せない用途ではドメイン例外で即時停止する
- 旧入口では失敗述語を元のDTOへ写し戻し、traceの型と経路を変えない
- 合成条件・短絡・確率乱数は既存評価器に残し、決定的な葉だけを委譲する
- 場所条件は対象範囲を別の型で表せるようにしてから移す

**関連**: #1046 / 判断 #63 / 判断 #70。

## 72. tick比較は同じ時間軸と境界を持つ用途だけ共通化する

**何を**: scenario条件の `TICK_AT_LEAST` と game end条件の `TICK_LIMIT` は、
どちらも世界の現在tickが整数閾値以上かを判定するため、`TickAtLeastPredicate` と
`TickPredicateContext` を共通の判定核へ追加する。等号を含む比較、用途固有の勝敗・
理由文、scenario traceの旧条件種別と失敗経路は維持する。

**なぜ**: 比較演算が `>=` というだけで探索回数やobject stateの経過tickまでまとめると、
時間軸や不足値の意味が違う条件を同じ型へ押し込むことになる。共通化の単位は演算子ではなく、
「同じ入力を同じ対象範囲で読む」という意味で決める。

**どう守るか**:

- `TickPredicateContext` は `WorldTick` だけを持ち、flags等の任意項目を増やさない
- `current_tick=None` は通常未成立ではなく文脈不足として返す
- `ScenarioEventCondition.tick=None` と game endの入力欠落は各旧入口の契約を維持する
- loaderが現在受理する非整数・負数の厳格化は、共通化と混ぜず別PRで扱う
- `TICK_BETWEEN`、`TICK_MODULO`、`OBJECT_STATE_TICK_AT_LEAST`、探索回数、会議上限は
  時間軸または意味が異なるため、この移行へ含めない

**関連**: #1046 / 判断 #71。

## 76. SQLiteのシナリオ宣言は全フィールドを同じschemaで往復させる

**何を**: `InteractionCondition` のSQLite用JSON変換は、dataclassの全フィールドを
単一の変換表から符号化・復号する。新しい条件項目を含むSpotInteriorはschema v2として
保存し、復号側は既存のv1とv2を受理する。

**なぜ**: 条件へ項目を追加してもcodecが追従せず、`required_quantity`、時間帯、天候、
対象者条件などが再起動後だけ既定値へ戻っていた。新形式をschema v1のまま保存すると、
旧実装も受理して同じ欠落を再発させる。また、`bool`や文字列を整数IDへ暗黙変換すると、
壊れた保存データが別の正しい条件に見えてしまう。

**どう守るか**:

- dataclassのフィールド集合と変換表のキー集合を構造試験で一致させる
- 符号化と復号で別々の項目一覧を持たない
- v1で存在しない項目だけはdataclassの既定値へ戻して後方互換を保つ
- 新規保存はschema v2とし、未知schemaは即時拒否する
- JSONの型違反、無効enum、無効IDは `SpotGraphStateDecodeError` へ統一する

**関連**: #1046 / 判断 #5 / 判断 #10。

## 77. 通知と効果経路を追加したSQLite宣言は新しいschemaを発行する

**何を**: `InteractionDef` の対象者通知と `InteractionEffect` の可視性・作用先を
SQLite用JSONへ保存する。これらを含むSpotInteriorはschema v3として保存し、復号側は
v1・v2・v3を受理する。

**なぜ**: 復元後に `notify_target` が無効化されるだけでなく、`EffectTarget.TARGET_PLAYER`
が既定の `ACTOR` へ戻ると、対象者へ向けた効果が行為者本人へ適用され得る。schema v2を
再利用すると、v2まで知る旧実装が新項目を黙って捨てるため、意味追加ごとに版を進める。

**どう守るか**:

- v1・v2で項目が無い場合だけ従来の通知・可視性・作用先の既定値へ戻す
- v3では対象者通知、対象者文面、効果可視性、効果対象を完全に往復する
- 不正なJSON型と未知enumは `SpotGraphStateDecodeError` で停止する
- 新しい意味を持つ項目を追加するとき、既存readerが受理するschema番号を再利用しない

**関連**: 判断 #76。

## 73. 場所条件は対象範囲を用途側で選び、共通核では型を分ける

**何を**: 場所条件を単一の `AT_SPOT` と mode の組に畳まず、明示したentity本人を
見る `EntityAtSpotPredicate` と、通常entityの在席数を見る
`EntityCountAtSpotAtLeastPredicate` に分ける。どのentityを対象にするか、ANY / ALLの
どちらで集約するかは、対象範囲を知る用途側に残す。

**なぜ**: 既存の条件名は対象範囲を正確に表していない。scenarioの世界評価における
`PLAYER_AT_SPOT` と `PLAYERS_AT_SPOT` はplayer repositoryと照合せず、graph上の通常
`EntityId`を数える。対象者評価の `PLAYER_AT_SPOT` は指定player本人だけを見る。一方、
game endの `ANY_AT_SPOT` / `ALL_AT_SPOT` は明示された`player_ids`だけを対象にする。
名前だけで一つにすると、非player entityで勝敗が決まる、または既存scenarioが発火しなく
なる。

**どう守るか**:

- `EntityPlacementPredicateContext` は `EntityId` から `SpotId` への防御コピーを持つ
- `None` は文脈不足、空mapping・未配置entity・未知spotは判明済みの通常不成立とする
- world-scope `PLAYER_AT_SPOT` は在席数1、`PLAYERS_AT_SPOT` は明示人数または既定2へ写す
- player-scope `PLAYER_AT_SPOT` は本人の `EntityAtSpotPredicate` へ写す
- game endは明示player全員を本人位置の述語で評価し、ANY / ALLと空集合拒否を用途側で行う
- 未配置playerは通常不一致とし、down / outcomeによる対象補正を新たに加えない
- scenario側の共通結果は旧DTOへ写し戻し、traceの条件種別・失敗経路を維持する
- loader、JSON、snapshot、SQLite、interactionの `PLAYERS_AT_SPOT` はこの移行で変更しない

**関連**: #1046 / 判断 #70 / 判断 #71。
## 74. 同期操作の準備は通常操作の可否と異なる参加者を要求する

(#218 で入口を `interact` に統合した。以下の `prepare_action` は内部の準備経路を指す。)

**何を**: `prepare_action` は現在地に同名 interaction を持つ対象物が一つだけあり、
その interaction の通常の前提条件を満たす場合だけ登録する。同じ同期グループの別の
required action を同じ player が準備済みなら、二つ目は理由つきで拒否する。
resolver も、操作名が揃っていても準備者が重複していれば完成させない。

**なぜ**: 準備だけが対象物・現在地・前提条件を見ないと、別室から操作でき、通常の
`interact` では拒否される者も協力者として数えられる。また action 名だけを数えると、
一人が二つの役割を順に準備して「二人が揃う」作業を一人で完成できる。

前提条件は協力操作用に書き写さず、通常操作と同じ
`SpotInteractionService.evaluate_preconditions_result` を非破壊で呼ぶ。二つ目を記録だけ
して完成に数えない案は、本人に失敗が見えず相方を待ち続けるため採らない。同じ action
の再準備だけは、待ち合わせ窓を更新する既存の用途として許す。

## 75. 数量を持たない所持条件は解決済み品目集合への所属として共通化する

**何を**: scenarioの `HAS_ITEM`、passageの `ITEM_REQUIRED`、discoveryの
`HAS_ITEM`、interactionの `TARGET_HAS_ITEM` / `TARGET_HAS_NO_ITEM` は、上流で解決した
品目集合に `ItemSpecId` が含まれるかを `ItemSpecOwnedPredicate` と
`OwnedItemSpecsPredicateContext` で共通評価する。誰の所持集合を渡すか、否定条件をどう
扱うか、失敗文を何にするかは用途側に残す。

**なぜ**: これらは通常スロットと装備スロットを含む同じ品目集合への所属判定だが、
interactionの行為者側 `HAS_ITEM` / `HAS_ITEMS` は通常スロットにある消費可能instanceの
個数を比較する。名前だけで一つにすると、装備中の鍵が通行条件を満たさなくなる、または
消費用の数量へ装備品を数えるという挙動変更が起きる。

**どう守るか**:

- 共通文脈の `None` は未配線、空集合は配線済みの未所持として区別する
- scenarioの世界評価はplayerごとに判定し、複数人の所持を合算しない
- 対象者の所持集合や参照品目が未解決なら、`TARGET_HAS_NO_ITEM` でも成立へ反転しない
- 共通核の入力不足・未対応は通常不成立へ潰さず、旧DTOへ写すか即時停止する
- inventoryから解決できないitem instanceを黙って除く既存挙動は、この共通化で変更しない
- `consume_item`、数量条件、trapの数量無視、interaction条件のSQLite復元欠損は別課題とする

**関連**: #1046 / 判断 #71。

## 79. state完全一致は対象の選択と分離して共通化する

**何を**: scenarioの `OBJECT_STATE` と、interactionのobject・item instance・
player state条件は、要求mappingの全キーを現在stateの値と比較する
`StateValuesMatchPredicate` / `StateValuesPredicateContext` へ委譲する。

**なぜ**: 判定自体は6経路ですべて `current_state.get(key) == expected` だが、対象は
世界内object、操作object、使う側・使われる側item、使う側・使われる側playerと異なる。
対象範囲まで共通述語へ入れると、巨大な任意文脈へ戻る。用途側が正しいstate snapshotを
選び、共通核は同じ値比較だけを担う。

**どう守るか**:

- 要求mappingと現在stateは入れ子を含めて防御コピーする
- 現在stateの余分なキーは無視し、空の要求mappingは従来どおり成立とする
- 要求値が`None`ならキー欠落とも一致する既存の`dict.get`意味を変更しない
- state未配線は通常不成立でなく文脈不足として返す
- scenario側は元DTOへ写し戻し、traceの条件種別・失敗経路を維持する
- interaction側は対象選択、作者文面、最初の失敗条件を維持する
- 整数下限、経過tick、備蓄再生、loaderの必須値厳格化は別変更とする

**関連**: #1046 / 判断 #71。
## 78. 罠定義と屋外属性をSQLite再開後も保持する

**何を**: `SpotNode.is_outdoor`、`SpotNode.traps`、`SpotObject.trap` をSQLite用JSONへ
保存する。ノード側の意味追加を含むグラフ集約はschema v3、物体罠を含む
`SpotInterior`はschema v4として保存し、それぞれ過去の版も読み込めるようにする。

**なぜ**: 罠はドメインモデルに存在していてもcodecから抜けており、SQLiteへ保存して
再開すると宣言そのものが消えていた。`is_outdoor`も同じ経路で既定の`False`へ戻る。
既存readerが受理する版番号を再利用すると、新しいpayloadを古い実装が正常扱いして
項目を捨てるため、グラフ集約とinteriorの双方で版を進める。

**どう守るか**:

- `TrapDef` のtrigger、効果、解除条件、可視性、反復、発見難易度を完全に往復する
- 効果と解除条件は既存の `InteractionEffect` / `InteractionCondition` codecを再利用する
- `TrapDef` の全フィールドとcodec出力キーを構造試験で一致させる
- 過去版で項目が無い場合だけ、屋外`False`・罠なしの従来既定へ戻す
- 不正な配列、真偽値、整数、未知triggerは `SpotGraphStateDecodeError` で停止する
- この判断は永続化だけを扱い、scenario loader・発火stage・解除数量判定は別変更とする

**関連**: 判断 #76 / 判断 #77。

## 136. 複数陣営では固定人数でなく現在の生存人数を比較する

**何を**: `SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE` は、
`required_state` を満たす生存者数が `comparison_state` を満たす生存者数以下に
なったとき成立する。既存の固定閾値条件
`SURVIVING_PLAYERS_WITH_STATE_AT_MOST` は別用途のため残す。

**なぜ**: インポスターが一人なら「クルーが一人以下」は両陣営が同数という条件と
一致する。しかしインポスターが二人になると、固定値を二人へ変えた条件は、一人が
追放されてもクルー二人で敗北させる。比較すべきなのは初期人数でなく、現在生きている
両陣営の人数である。

**どう守るか**:

- `required_state` が左辺、`comparison_state` が右辺で、左辺が右辺以下なら成立する
- `PlayerOutcomeEnum.is_eliminated` が真の死亡者・追放者はどちらの人数にも含めない
- DEAD の幽霊が作業を続けられても、生存人数には含めない
- 左右に同じ state を指定すると常に成立するため、構築時に拒否する
- 初期人数が零か、将来どう変化するかは静的に断定できないため、一般の達成可能性は
  読み込み時に推測しない
- 条件型は成立した事実だけを表し、WIN / LOSE は置かれた配列から呼び出し側が渡す

## 137. 役職の相互開示はシナリオが宣言し、役職語彙は表示層へ渡さない

**何を**: シナリオの `mutually_known_roles` に書かれた role の人物は、
同じ role の他者を「あなたと同じ側」と表示する。宣言されていない role には
印を作らない。

**なぜ**: 複数人の秘匿陣営では味方を知るかがゲームの規則であり、engine の
全世界共通規則ではない。一方、`role=keeper` のような内部語彙を prompt builder へ
渡すと、役職名の漏洩や crew への誤配信を後段で防ぐ必要が生じる。

**どう守るか**:

- loader は宣言 role に二人以上いることを確かめ、誰にも印が付かない静かな失敗を止める
- runtime が見る側ごとに開示を解決し、prompt builder には確定済みの世界内表示名だけを渡す
- 対人候補には役割値でなく「既知の相方」という真偽だけを渡し、相方へ必ず失敗する襲撃を出さない
- 宣言集合が空の既存シナリオは、従来の名前表示をそのまま保つ
- crew は宣言集合に入れず、crew 同士の印から秘匿陣営を逆算できないようにする

## 80. 数量付き所持条件は解決済み品目別個数の比較として共通化する

**何を**: interactionで使う側の `HAS_ITEM` / `HAS_ITEMS` は、上流で解決した
品目別instance数を `ItemSpecCountAtLeastPredicate` と
`ItemSpecCountsPredicateContext` で共通評価する。`HAS_ITEMS` は宣言順に品目ごとの
述語を評価し、一種でも必要数に届かなければ元の条件を不成立とする。

**なぜ**: この二条件は同じ「品目ごとの個数が必要数以上」という比較を重複して
持っていた。一方、判断 #75 の所持条件は装備を含む品目集合への所属であり、数量条件は
通常スロットのinstance数だけを見る。既存の `ItemSpecOwnedPredicate` に数量を足すと、
装備品を個数へ含める誤った意味になるため、別の型付き述語として分離する。

**どう守るか**:

- 共通文脈の `None` は未配線、空mappingは配線済みの0個として区別する
- 品目別個数は `ItemSpecId` と0以上の整数だけを受け入れ、防御コピーする
- 必要数はboolを除く正整数とし、共通核の評価不能は通常の所持不足へ縮退させない
- `owned_item_spec_counts` が省略された必要数1の条件は、既存どおり品目集合から各1個へ戻す
- `HAS_ITEMS` の重複品目は合算せず、宣言された各要素へ同じ必要数を適用する
- 既存の失敗文、最初の失敗条件、装備除外、stack数量を数えない意味は変更しない
- 予約中品目と `REMOVE_ITEM` の整合、trapの数量判定、消費の原子性は別課題とする
- 判定は決定的で新しい永続状態を持たないため、traceとsnapshot形式は追加しない

**関連**: #1046 / 判断 #71 / 判断 #75。

## 81. 整数state下限は対象解決と分離して共通化する

**何を**: scenarioとinteractionの `OBJECT_STATE_INT_AT_LEAST` は、対象objectを
用途側で解決した後、`StateIntAtLeastPredicate` と既存の
`StateValuesPredicateContext` で同じ整数下限判定を行う。

**なぜ**: 両経路はstateの同じキーを読み、キー欠落または整数以外を0として閾値と
比較していた。一方、scenarioは世界全体からobjectを探し、interactionは操作objectか
明示target objectを選ぶ。対象選択まで共通核へ持ち込むと、用途固有のrepositoryや
任意対象を文脈へ詰め込むことになるため、共通核は解決済みstateの値だけを読む。

**どう守るか**:

- 共通述語の `state_key` は空でない文字列、閾値はboolを除く整数とする
- キー欠落と整数以外の現在値は、従来どおり文脈不足でなく0として比較する
- Pythonでboolが整数である既存意味と、scenarioの0・負閾値はこの変更では直さない
- interactionの必要数は従来どおり最低1へ補正し、数量入り失敗文を用途側に残す
- scenarioのobject不存在は `spot_object` 不足、interactionの対象不足は既存の通常不成立とする
- 共通核の入力不足・未対応は通常不成立へ潰さず、元DTOへ写すか即時停止する
- scenarioの合成条件、失敗経路、確率条件の短絡と乱数消費順、trace payloadを維持する
- typed predicateは評価時の一時値なのでSQLite・snapshot形式を変更しない
- loaderの必須値厳格化、経過tick、備蓄再生、天候条件は別変更とする

**関連**: #1046 / 判断 #71 / 判断 #79。

## 82. 遠隔道具の明示対象は世界全体から解決し、解決不能を成功扱いしない

**何を**: 道具操作の効果が `object_id` を明示した場合は、その物体の所有室を
世界全体から解決する。前提条件は使う側の現在地で評価し、効果と保存だけを対象物の
所有室へ適用する。対象が見つからない場合と、一操作が複数室の物体を指す場合は
`ApplicationException` で停止する。

**なぜ**: run 030 の tick 11 で、連絡通路にいたクゼは集会室の隔壁盤へ
`seal_bulkhead` を実行し、成功文も受け取った。しかし効果処理は使う側の部屋だけを
探索したため `sealed_at_tick` は一度も記録されず、tick 12 にセナとアオイが扉を
通過して会議を開いた。盤を遠隔操作する宣言と、効果の対象探索範囲が食い違い、
何も変えていないのに成功と返す静かな失敗だった。

**どう守るか**:

- 前提条件の `SPOT_*` は使う側の現在地を見続け、遠隔対象の部屋へ意味を変えない
- 明示した物体が一室に収まる場合だけ、その室の `SpotInterior` へ効果を適用して保存する
- 対象物が存在しなければ、成功文や待ち時間を発生させる前に停止する
- 複数室へ物体効果を適用する操作は、原子性と保存先が定義されるまで許可しない
- 解決失敗と複数室指定は、それぞれ例外型と文面を試験で固定する

## 83. scenarioの列挙値は実行時の不成立へ縮退させず読込時に拒否する

**何を**: scenario述語の `WEATHER_IS.weather_type` は、シナリオ読込時に
`WeatherTypeEnum.value` と完全一致する文字列だけを受理する。欠落、`null`、文字列以外、
未知値、大小文字違い、前後空白は、述語の位置と許容値を含む `ScenarioLoadError` で拒否する。

**なぜ**: 従来は値をそのまま `ScenarioEventCondition` へ渡し、実行時に現在天候の文字列と
比較していた。そのため `STROM` のような誤記やfield欠落が通常の条件不成立に見え、
scenario event、reactive binding、player outcome ruleが永久に発火しなくても原因を発見
できなかった。空白除去や大文字化で補正すると誤記を静かに別の意味へ変えるため、補正せず
作者へ修正を求める。

**どう守るか**:

- 共通のscenario条件parserで検査し、合成条件を含む全利用箇所へ同じ契約を適用する
- enumの名前ではなく、評価器が比較する `.value` を正本とする
- loaderを迂回した直接DTO構築とruntimeの防御的な不成立処理は変更しない
- interactionの `required_weather_type`、monster spawn、環境初期値は別スキーマとして扱う
- 正しい列挙値、誤記、型違い、欠落、合成条件と各利用箇所のpathを試験で固定する
- 読込時に停止するため、新しいtraceやsnapshot状態は追加しない

**関連**: #1046 / 判断 #10 / 判断 #65 / 判断 #71。

## 84. 天候条件は正の一致だけを共通化し、否定と失敗文は用途側に残す

**何を**: scenarioの `WEATHER_IS` とinteractionの `WEATHER_IS` / `WEATHER_IS_NOT`
は、`WeatherTypeIsPredicate` と `WeatherTypePredicateContext` で同じ列挙値一致を判定する。
共通核は正条件だけを持ち、現在天候と要求天候が同じ `WeatherTypeEnum` なら成立、異なれば
通常不成立、現在天候が未配線なら文脈不足を返す。

**なぜ**: 正の一致判定は両用途で同じだが、不足時の出口は異なる。scenarioはprovider未配線を
`weather_state` の文脈不足としてtraceへ残し、interactionは既存の作者文面またはprovider不足文を
返す。また `WEATHER_IS_NOT` が共通結果の `is_satisfied=False` をそのまま反転すると、通常不一致
だけでなく文脈不足や評価器未対応まで操作可能へ変わる。

**どう守るか**:

- 共通述語と文脈は文字列でなく `WeatherTypeEnum` を受け取る
- interactionの否定は `require_satisfaction` で正常な真偽へ射影した後だけ反転する
- scenarioは共通結果を元の `ScenarioEventCondition` へ写し戻し、失敗経路とtrace種別を保つ
- providerの呼出し回数、例外処理、既存の失敗文、前提条件の宣言順は用途側で維持する
- loaderを迂回した未知文字列は、このリファクタでは従来の完全一致比較へ戻す
- 天候強度、時間帯、照明、monster spawnの許容天候集合は別の意味なので含めない
- typed predicateは評価時の一時値であり、SQLite・snapshot・trace形式を変更しない

**関連**: #1046 / 判断 #63 / 判断 #71 / 判断 #83。

## 86. 共通述語基盤は決定的な葉と用途表を完成境界とする

**何を**: #1046 の共通述語基盤は、意味が同じ決定的な葉を型付きの評価核へ集約し、
既存用途が対象選択・合成・表示を担う形を完成形とする。共通述語の型一覧、評価器の分岐、
利用用途表を双方向の構造試験で照合し、新しい型が未対応のまま永久不成立へ落ちることを防ぐ。

**なぜ**: 当初案には AND / OR / NOT を含む共通構文木と巨大な評価文脈も含まれていた。
しかし既存の合成条件は短絡順、確率乱数、失敗経路、traceを所有し、interactionやgame end
では合成後の出口も異なる。これらまで一つへ寄せると、同じ名前に隠れた対象範囲や不足時の
意味を再び潰す。共通化によるレバレッジは、同じ入力を同じ真理値で読む葉を一度実装する
ことで得られており、合成構文木の統合は完成条件にしない。

**どう守るか**:

- `ScenarioPredicate` と `PredicateContext` は実行時型一覧と一致させる
- 全述語型を `ScenarioPredicateEvaluator` の分岐と利用用途表へ必ず登録する
- 利用用途表は設計・構造監査の正本とし、用途固有DTOの実行時検証を二重化しない
- monster spawnの必須・禁止フラグと許容天候も既存の共通葉へ委譲する
- 否定は通常の成立・不成立だけを反転し、文脈不足・未対応を成立へ変えない
- 昼夜、探索回数、備蓄再生、経過tick、勝敗集約など、同義でない条件は用途側に残す
- scenario event系の合成・確率・traceと共有乱数snapshotは判断 #62 / #70 のまま維持する
- `TrapEvaluationService` の数量条件と発火配線、monster spawn loaderの文字列強制変換は
  独立した不具合として扱い、共通化の完了に混ぜない

**関連**: #1046 / 判断 #62 / 判断 #70 / 判断 #71〜#84。

## 85. 同時性はフェーズの意味に合わせ、比較 run に必要な量を trace へ残す

**何を**: 自由時間の LLM wave は Phase A を並列にして同 tick の行動を互いに
見せない。会議の逐次化は `LLM_MEETING_SERIAL_TURNS` で明示した比較 run だけにし、
既定は会議も並列にする。逐次化した場合は prompt 構築から一人ずつ実行して先行発言を
後続者へ見せる。実行順を変えるために system prompt や toolset は変更しない。

同時に、マップと会議の変更を実走後に判定できるよう、各 tick の全室在室数、
各人の累積移動 tick、会議区間と累積会議 tick、短期記憶圧縮の前後量を trace
へ残す。圧縮発火は L4 要約の生成結果とは別の事実として記録する。

**なぜ**: 自由時間を逐次化すると wave 内の順番が襲撃や移動の有利不利を作る。
一方、会議を並列にすると全員が同 tick の他者発言を読まずに話し、8 人でも
積み上がる対話が tick 数ぶんしか生まれない。ただし run 029〜033 の実測では、会議の
逐次化は 8 人で約 4 倍の実時間を要する見込みだった。混線は tick を浪費するが議論を
壊してはいなかったため、既定は並列とし、逐次化は比較条件として残す。

9 室化と 80 tick 化では、作業が進まない原因を空間分散、移動負担、会議占有、
記憶圧縮から切り分ける必要がある。最終状態だけでは因果を復元できないため、
分析に必要な量を発火地点で記録する。

**どう守るか**:

- 設定を明示した会議だけ実効 worker 数を1にし、自由時間の worker 数は変えない
- 逐次会議の後続 prompt に同 tick 発言が入り、既定の並列会議と自由時間には
  入らないことを対で試す
- 同一フェーズの system prompt と toolset の sha256 が worker 数で変わらず、
  フェーズ境界の toolset は実物どおり異なることを試す
- 在室数は無人室を含む全室を毎 tick 出し、移動は到着 tick も数える
- 会議は開始と終了を別 event にし、未終了 run でも開始を失わない
- 要約あり・なしの両短期記憶が同じ圧縮 trace 契約を持つ

会議の逐次化 (`LLM_MEETING_SERIAL_TURNS`) は、どの profile も既定の並列 (false) で動かしていたので、記憶ではない設定の片付け (#1631) の #1776 で消した。会議も自由時間も wave 並列だけになる。上の本文と「どう守るか」にある逐次化の記述 (設定を明示した会議だけ worker 数を 1 にする、逐次会議の後続 prompt に同 tick 発言が入る) は、判断の記録として残すが、もう使えない。

## 87. 長走比較では短期記憶だけを要約し、補助 JSON 呼び出しは熟考しない

**何を**: `station_drill_lean` と `station_drill_thinking` は 80 tick の長走に備えて
`SHORT_TERM_MEMORY_KIND=rolling_summary` を使う。エピソード記憶、信念、目標、
意味記憶は無効のまま維持する。`complete_episode_subjective_json` を共有する補助 JSON
呼び出しは、agent turn の `LLM_REASONING_EFFORT` にかかわらず `none` で送る。

**なぜ**: `sliding_window` は畳んだ古いターンを要約せず捨てる。80 tick では圧縮が
複数回起きるため、序盤の殺害や所在を失う。一方、信念・目標なども同時に有効化すると、
run の変化を短期要約へ帰属できない。JSON 抽出は行動選択ではなく、熟考を足す理由がなく、
`json_object` と thinking の組合せは provider 互換性も悪化させる。

**どう守るか**:

- lean の 80 tick、`rolling_summary`、他の記憶機能無効をリテラルで試験する
- thinking は provider・agent turn の reasoning・並列 worker 以外を lean と揃える
- JSON 経路の実送信 kwargs に `reasoning_effort` が無く、reasoning / thinking の
  無効化 block が入ることを試験する
- 補助抽出用の設定項目は増やさず、熟考比較が必要になった時点で別途判断する
- 圧縮発火は `SHORT_TERM_MEMORY_COMPACTED`、要約結果は既存 trace で観測する

`SHORT_TERM_MEMORY_KIND` は、どの profile も `rolling_summary` で動かしていたので、記憶ではない設定の片付け (#1631) の #1785 で消した。短期記憶は常に要約するので、`rolling_summary` をリテラルで見る試験も外した。

## 88. REMOVE_ITEMは予約されていない具体instanceを全量確保してから消費する

**何を**: `REMOVE_ITEM` の消費可能個数には予約中のinstanceを含めない。削除時は
要求された品目の多重集合に対して、通常スロット上の未予約instanceを全量ぶん先に
計画し、すべて確保できた場合だけまとめて削除する。

**なぜ**: 従来は数量判定が予約品を含み、削除は同品目の先頭slotへ `drop_item`
していた。先頭が取引・クエスト用に予約済みなら、後方に未予約品があっても例外になり、
複数個の途中で失敗すれば一部だけ消費された。予約は別の操作が所有する排他的な確保であり、
一般のinteractionが消費可能な所持数として扱ってはならない。

**どう守るか**:

- 消費可能個数は通常slotだけを数え、装備品と予約品を除外する
- 削除計画は具体的な `SlotId` と `ItemInstanceId` を保持し、同じinstanceを二重に選ばない
- 全量を確保できなければinventoryを変更しない
- 適用直前にslot、instance、予約状態を再確認し、計画が古ければ変更せず失敗する
- 効果宣言から削除要求だけを副作用なしで先に解決し、状態変更やloot抽選より前に検証する
- 道具・物体・対人interactionは、行為者・対象の削除全量を確保してから効果を適用する
- scenario eventは全プレイヤーへの最善努力という既存契約を維持し、各inventory内だけ全量消費にする
- リポジトリ保存失敗まで含む複数集約の完全な原子性は、共有Unit of Workの課題として分離する

**関連**: 判断 #75 / 判断 #80。

## 89. 時間制限つき妨害は発動・警報・協力解除・締切を別の宣言で持つ

**何を**: station_drill の燃料凍結は、遠隔操作が開始時刻を物体へ記録し、
scenario event が全員への段階警報・解除告知・9手番後の敗北を担い、同期操作が
別室の二人による解除を担う。同期操作の `on_timeout` は片方が準備した後の
やり直しだけに使い、誰も動かなかった場合を含む全体締切には使わない。

**なぜ**: `on_timeout` は最初の prepare が無ければ始まらない。締切まで同じ機構へ
押し込むと、全員が妨害を無視したときだけ永久に敗北しない静かな失敗になる。
また、フラグ前提は既定では阻害理由つきで操作名を残すため、平常時から解氷操作を
宣伝する。時限ギミックだけが明示的に候補を伏せる属性を持ち、既存の公開条件は
変えない。一度だけの開始警報では作業中に忘れられるため、40分・30分・20分・
10分の四段階で全員を起こす。告げた危機を取り消さない静かな失敗を避けるため、
解除も参加者向けの現場文とは別に全員へ一度だけ告知する。

**どう守るか**:

- 発動は `fuel_frozen` と `frozen_at_tick` を同じ成功操作で記録する
- 段階警報と締切は `fuel_restored` / `fuel_lost` の未成立を要求する一回限りの event にする
- 解除時は `fuel_restored` を見る別 event が、準備に参加しなかった者にも告知する
- 解除は異なる二人・別室・準備時点を1手番目と数える3手番の同期窓を要求する
- 平常時と解除後は弁の操作を隠し、凍結中だけ表示する
- 当番表は平常時から二つの弁と二人で分かれる非常手順を教える
- 燃料圧計は生の手番を伏せ、世界時計と同じ分換算で残り時間を示す
- `fuel_lost` を勝敗条件の真実源とし、放置時の敗北を実 runtime で試す

## 90. 在室数は用途別の範囲を明示し、動的表示はアプリケーション層で解く

**何を**: 区画別の人数集計は `collect_spot_occupancy` に集約し、社会密度の
trace は `meeting_eligible_players`、所内位置表示盤は
`living_players_and_fallen_bodies` を明示する。表示盤は生存者と遺体を同じ
一反応として数え、幽霊を数えず、名前を返さない。

`SHOW_ROOM_OCCUPANCY` は domain 層で静的な文を作らず、動的表示要求だけを結果へ
載せる。application 層が操作時点の graph・生死・遺体を読んで本人向けの文にする。

**なぜ**: trace の人数は社会密度を測るため、遺体を含めると会話可能な人数を
誤る。一方、表示盤から遺体を除くと、未発見の遺体へ向かう手掛かりが消える。
「人数」という語だけで一つの関数へ固定すると、片方の都合で範囲を変えたときに
もう片方も黙って変わる。

また、domain 層には全 player の位置、生死、遺体 registry が無い。そこへ参照を
持ち込むと境界を壊し、シナリオ読み込み時に人数を文へ焼くと実行時の世界とずれる。
要求を越境結果へ載せることで、宣言できるのに表示されない静かな失敗も配線不在の
例外として止められる。

**どう守るか**:

- 集計範囲は enum で選び、遺体範囲には registry の注入を必須にする
- 全区画を宣言順に出し、無人室も 0 として残す
- 表示文は区画名と反応数だけにし、player 名を混ぜない
- 実 runtime でクルーとインポスターの両方が使えることを試す
- 遺体を一人と数え、別位置にいる同じ死者の幽霊を二重に数えないことを試す
- 同席者には表示内容でなく、表示盤を見た行為だけを届ける

## 91. OpenRouter の会話固定 ID は run・世界・player から作り、本文へ混ぜない

**何を**: エージェントの主ターンを OpenRouter へ送るとき、run・世界・player の
組から作った 256 文字以下の `session_id` をトップレベルの送信値へ載せる。同じ
player の評価段・行動段・会議・自由時間では同じ値を使い、player または run が
違えば別の値にする。長すぎる識別子は組全体をハッシュ化する。

**なぜ**: `session_id` が無い場合、毎手番変わる最初の user メッセージによって
別会話と判定され、暗黙のプレフィックスキャッシュが効く配信先へ固定されにくい。
会話 ID を本文へ追記すると、守りたい接頭辞そのものが変わる。フェーズごとに ID を
分けても、会議の入口と出口で配信先の固定が切れてしまう。

**どう守るか**:

- `messages` を加工せず、LiteLLM のトップレベル引数として送る
- OpenRouter 以外には送らず、未対応引数を持ち込まない
- 実験 run は出力先の run 名、通常セッションは衝突しないセッション ID を使う
- 補助 JSON 呼び出しは主ターンと接頭辞が異なり、同時実行で配信先を揺らすため共有しない
- 同一 player の連続呼び出し、別 player、別 run、評価段と行動段を試験する

## 92. 再発動する時限事象は状態を解除し、経過時刻の窓で各周期を識別する

**何を**: 一時的な世界フラグを外す汎用効果 `CLEAR_FLAG` を `SET_FLAG` と対で
用意する。station_drill の燃料凍結は、発動時に前回の復旧・告知フラグを解除し、
復旧時に凍結中フラグを解除する。25手番の待ち時間後は再び発動できる。

段階警報は scenario event の永続的な `once` 記録に依存せず、物体へ上書きした
`frozen_at_tick` からの経過時刻が各段の狭い窓に入ったときだけ発火する。復旧告知は
`fuel_announced` を周期の先頭で解除し、告知と同時に立てることで周期ごとに一度にする。

**なぜ**: 一度きりの札は run 034 で最後まで温存され、妨害として機能しなかった。
単に event の `once` を外すと、成立条件が真である全 tick に同じ警報が繰り返される。
警報ごとの発火済みフラグを増やすと、段数に比例した状態の消し戻しが必要になり、
二度目だけ一段が鳴らない静かな失敗を作りやすい。開始時刻を毎周期上書きし、経過時刻の
窓で識別すれば、周期番号や段別 bookkeeping を持たずに同じ宣言を再利用できる。

**どう守るか**:

- `CLEAR_FLAG` は対象が無くても冪等に成功し、他の世界フラグを変えない
- 同期操作でも `CLEAR_FLAG` を正式対応し、復旧時に `fuel_frozen` を外す
- 初段を含む四段警報は各周期で一度ずつ全員へ届く
- 復旧告知は参加者以外にも各周期で一度だけ届く
- 待ち時間中の再発動は拒否し、25手番の境界で再び許可する
- 二度目を放置した場合も9手番後に同じ敗北条件へ到達する
- 事象を跨ぐ永久状態である `fuel_lost` は解除せず、敗北の真実源を維持する

**関連**: 判断 #89。

## 93. persona の役職知識は世界の事実に限り、立ち回りを代行しない

**何を**: persona に役職固有の能力を説明するときは、能力・世界への帰結・解除条件
までを記し、その情報をどう利用するかという立ち回りは書かない。station_drill の
燃料凍結では、発動できる者、放置時の敗北、二室の弁を二人で同時に開ける復旧要件を
伝える一方、待ち伏せる場所や狙う相手は本人の判断に残す。

**なぜ**: run 035 で燃料凍結が使われなかった直接の原因は、操作名だけが見えて
帰結と復旧要件が persona に無かったことだった。一方、修正案に立ち回りまで書くと、
次の run で使われても「事実から本人が戦術を導いたか」を測れない。停電では暗所と
目撃の関係だけを伝えた結果、クゼ自身が利用法を導けていたため、同じ情報境界に揃える。

**どう守るか**:

- 能力の陽性試験は、所有者と相方が帰結・復旧要件を知ることを確認する
- 所有能力と相方の知識を分け、端末を持たない者へ操作能力を与えない
- 全 player の人物紹介より後ろを検査し、段落内・末尾のどちらへ足した立ち回りも止める
- 禁止語は待機・待ち伏せ・標的指定・移動指示・選択代行を表す語を含める

## 94. 人物固有文と役職共通知識を分離し、固定順で system prompt へ連結する

**何を**: シナリオは `players[].persona_prompt` に人物固有の性格・職掌・動機を、
`role_personas[role]` に陣営の能力・制約・世界知識を宣言する。runtime は人物文を先、
役職文を後ろの固定順で一度だけ連結する。`role_personas` 未宣言の既存シナリオは従来の
人物文だけを使う。

**なぜ**: station_drill では persona の大半が役職ごとの複製で、能力追加時に片方だけ
更新される静かな失敗が起きた。共通知識を一箇所へ束ねれば、同じ役職の全員へ構造的に
届く。一方、現在の所持品から system 文を動的生成すると、譲渡・落下で不変な接頭辞が
変わり、既に得た能力知識まで消える。そのため端末の操作候補は所持品行へ追従させるが、
端末を扱えるという人物固有の知識は所有者の人物文へ残す。

クルーへ燃料凍結の知識を平常時から共通配信はしない。当番表を読んだ者だけが事前に
非常手順を知り、未読の者は最初の警報で初めて知るという差を残すためである。日常から
想定される停電の知識と、初めて起きる燃料凍結の非常手順は同じ事前知識として扱わない。

**どう守るか**:

- `role_personas` の型・空文・player が持たない role を読み込み時に拒否する
- クルー六人とインポスター二人で、人物文の後ろに同一役職文が一度だけ続くことを試す
- 異なる role の共通知識を相互に混ぜない
- runtime の再構築、tick、現在の所持品で八人の system prompt hash を変えない
- 移行前とのバイト同一性は、文面を組み替えていないクルー六人の既知 hash で固定する
- クゼとジンは能力・帰結・復旧要件を保ったうえで、人物文と共通文の順へ意図的に組み替える
- 未宣言のシナリオは空 mapping として既存の `persona_prompt` 経路を保つ

## 95. tools payload は状態不変の常在ブロックを先頭へ固定する

**何を**: `wait`、`speak`、`memo_add`、`memo_list`、`memo_done` を tools
payload の先頭へ固定順で置く。並び順の正本は `ToolExposure` に一つだけ持ち、
スポット・記憶ツールの合成後と死亡フィルタ後に適用する。状態で落ちうる `listen` と
`tend_to_player` は常在ブロックへ入れない。幽霊にも `listen` を残す。

**なぜ**: run 035 では幽霊化した三回だけ、先頭の `listen` が死亡フィルタで消え、
tools JSON 12,039文字の共通接頭辞が31文字まで縮んだ。会議や投票の遷移で接頭辞が
残っていたのは、共通ブロックの意図が構造化されていたからではなく、偶然先頭が一致した
ためだった。観測しかできない幽霊に環境音を聞く手段が無い一方、ほぼ失敗する
`interact` が残る質感の逆転も同時に直す。

**どう守るか**:

- 生存自由時間、生存会議の投票前後、幽霊自由時間、幽霊会議の実 payload を検査する
- 五状態すべてで先頭五ツールの名前と順序が完全一致することを試す
- 幽霊には `listen` を出し、取得・譲渡・遺体報告は引き続き出さない
- 合併集合で全フェーズの定義を固定せず、`vote` など使えない手を別フェーズへ宣伝しない
- user prompt の節順は変えず、追記式の出来事が作る既存の安定接頭辞を保つ

## 96. 熟考と required が両立しない provider は tool_choice を実験条件として切り替える

**何を**: 1段階ターンの `tool_choice` を `required` または `auto` として profile に
宣言できるようにする。既定は従来どおり `required` とし、`auto` では実際の tools
payload から作った名前一覧と「文章だけで答えない」という指示を user prompt 末尾へ置く。
ツールが返らなければ末尾だけを強めて一度だけ再試行し、それでも返らなければ従来の
`NO_TOOL_CALL` として行動履歴へ残す。

**なぜ**: DeepSeek は熟考と `tool_choice="required"` を同時に拒否する一方、同じ
モデルでも provider によってプレフィックスキャッシュの安定性が大きく違う。静かに
`auto` へ降格すると run の実条件が宣言と食い違うため、明示的な比較条件にする必要が
ある。文章指示へツール名を手書きすると、無効化や状態による露出変更後も存在しない
ツールを宣伝する過去の静かな失敗が再発する。

reason-first の第1段は named `tool_choice` を使う。DeepSeek の熟考との両立を実 API で
確認していないため、`auto` profile では実効無効にし、その結果を resolved config に
残す。頻度が低い経路を推測で有効にするより、測定条件を復元できることを優先する。

**どう守るか**:

- 未指定と既存 profile は `required` のままにし、未知値は起動前に拒否する
- `auto` の末尾に載る名前集合を、API へ渡す実 payload と一致させる
- 各ツールを一つずつ無効化し、payload と末尾指示の双方から消えることを試す
- `NO_TOOL_CALL` の再試行は `auto` だけ一回に固定し、`required` は一回のままにする
- 複数 tool call は先頭だけ実行し、捨てた件数と全 tool 名の返却順を
  `LLM_CALL` metrics に残す。引数は実行済みと誤読されるため残さない
- DeepSeek 比較 profile は thinking profile から provider と tool_choice だけを変える
## 97. 待ち時間の共有単位は役職ではなく interaction が宣言する

**何を**: `InteractionDef.cooldown_scope` は `actor` (既定) または `world` を取り、
`actor` は従来どおり行為者ごと、`world` は行為者を問わず同じ行為キーの成功 tick を
一つだけ持つ。engine は役職や陣営を知らず、共有すべき操作をシナリオが選ぶ。

**なぜ**: run 036 では制御端末を持つクゼの追放後、相方のジンから妨害三種がすべて
消え、終盤五手番で点検六件が進んだ。一方、単に端末を二人へ配るだけでは、行為者別の
待ち時間を交互に使って妨害を連射できる。陣営を engine に持ち込まずにこの二つを同時に
解くには、待ち時間の共有単位を宣言側の性質にする必要がある。

**どう守るか**:

- 未指定は `actor` とし、既存シナリオの二人の対人行為を独立したまま保つ
- `world` は実際の候補表示と実行拒否の両方で、別の行為者にも残り時間を適用する
- 未知値は読み込み時に拒否し、`actor` へ黙って縮退させない
- actor/world の記録を world snapshot schema 2 で分け、schema 1 は actor 記録として読む
- SQLite の `InteractionDef` 往復でも `world` を既定値へ戻さない

## 98. 操作名の救済案内は候補表示と同じ露出集合から作る

**何を**: 物体の操作名を誤ったときに返す「利用可能な操作」は、役割・世界状態に加え
`allowed_actor_planes` も候補表示と同じ共通関数で絞る。存在層が合わない実行拒否は
専用例外と `precondition_failure_kind=actor_plane` で区別し、幽霊には生きた体が要る
理由と、続けられる自分の担当・共通点検を伝える。

**なぜ**: run 037 では幽霊の候補から `restore_power` が消えていた一方、誤った操作名の
案内が正解を五回教えた。次の手番で正解を呼ぶと曖昧な文で拒否され、二手番を続けて
失った。候補と救済が別の集合を使うと、伏せた名前をエラー経路から学べる。拒否理由まで
曖昧だと「死後は何もできない」と誤解し、意図して残した点検まで諦めうる。

**どう守るか**:

- 幽霊の候補と誤入力時の案内の双方から、生者専用操作を落とす
- 同じ操作を生者には候補と案内の双方で残し、「常に空」への縮退を止める
- 正しい生者専用操作を幽霊が直接呼んだ実結果で、理由と残る能力を確認する
- `restore_power` は `allowed_actor_planes: [LIVING]` を明示し、既定値へ戻さない
- 幽霊が自分の担当と共通点検を続けられる既存の挙動は変えない

## 99. 進行中の異常はシナリオが宣言し、追記式の出来事より後ろへ表示する

**何を**: シナリオは `ongoing_conditions` に世界フラグ、全員へ見せる事実文を
宣言する。runtime は成立中のフラグだけを
`【進行中の異常】` として、実際のユーザープロンプトの最終指示直前へ毎ターン表示する。
生存者と幽霊で表示経路を分けない。

**なぜ**: run 034 / 037 では停電が全時間の約九割続いたが、機関室に居ない者は
主配電盤の存在も復旧方法も継続して読めなかった。発生時の一度きりの観測だけでは、
長い作業や会議の間に異常と解除方法を見失う。一方、異常一覧を
`【直近の出来事】` より前へ置くと、状態が変わるたびに追記式の長い安定接頭辞まで
プレフィックスキャッシュから外れる。元から変動する末尾へ置けば、世界状態を常時
知らせても既存の安定領域を壊さない。

**どう守るか**:

- エンジンは停電や燃料という固有名詞を知らず、flag と文面の対応をシナリオから読む
- 宣言項目の未知キー、空文字、初期値にも `SET_FLAG` にも無い flag は読み込み時に拒否する
- 成立中の宣言が無ければ見出しごと省略し、空の異常一覧を毎ターン出さない
- 実際に組み上がったユーザープロンプトで、直近の出来事より後かつ最終指示の直前を検査する
- 異常の状態遷移は `resolution` に一度だけ宣言し、会議などの解除経路はそれを参照する

## 100. 会議による異常解除は明示効果で宣言し、遷移成功後だけ適用する

**何を**: `ongoing_conditions[].resolution` に異常を解く flag 効果を一度だけ宣言し、
同期修理と会議は `RESOLVE_ONGOING_CONDITION` で同じ状態遷移を参照する。
`on_meeting_start` の有無を「会議で解ける」の唯一の宣言にする。効果は会議遷移が
成功した直後の `after_apply` で適用し、会議固有の結果文は生存者と幽霊を含む全員へ届ける。

**なぜ**: run 037 では燃料凍結中の遺体報告で会議に入り、移動手段が消えたまま締切を
迎えた。本家と同じく会議で致命的妨害を解く必要がある。一方、同期操作 group を名前で
探索して効果を流用すると、宣言間に見えない結合が生まれる。修理と会議へ同じ flag 効果を
複製すると、片方だけ更新される二重管理になる。一方、観測文まで共通化すると、会議では
誰も触っていないレバーを「噛み合った」と記憶へ流す。状態遷移だけを異常側へ集約し、
経路ごとの語りは各経路に残す。

**どう守るか**:

- `resolution` は flag 効果だけを持ち、自身の flag を `CLEAR_FLAG` することまで読み込み時に確かめる
- `RESOLVE_ONGOING_CONDITION` の参照先に `resolution` が無ければ起動前に拒否する
- 会議で扱えない物体効果などは警告で捨てず、読み込み時に拒否する
- 遺体報告と緊急招集の双方で同じ会議開始境界を通す
- 遷移拒否時は効果も通知も適用せず、停電のように効果を宣言しない異常は残す
- 同期操作と会議解除で妨害 flag は一致させ、観測文は互いの原因を捏造しない別文にする

## 101. 緊急招集を塞ぐ異常は全項目が明示し、遺体報告とは入口を分ける

**何を**: `ongoing_conditions[].blocks_emergency_button` を既定値なしの必須真偽値とし、
成立中の異常に `true` が一つでもあれば緊急招集ボタンを拒否する。停電と燃料凍結は
`true`、時間で自動復帰する隔壁は本家の扉妨害と同じ例外として `false` を宣言する。
遺体報告はこの判定を通さず、異常中でも会議を始められる。

**なぜ**: 本家では扉以外の妨害中に緊急ボタンを押せない一方、遺体報告は常に可能で、
致命的妨害を会議開始時に解く。既定を `true` にすると、異常を追加した人が項目を
書き忘れても一見正しく動き、例外にしたい妨害だけが静かにボタンを塞ぐ。現時点で
`ongoing_conditions` を使うのは station_drill だけなので、全項目の明示を要求しても
互換性の費用は無く、宣言だけ読んで規則を判断できる。

隔壁は `sealed_at_tick` から 4 tick 後に自動で上がる。発動時に
`bulkhead_sealed` を立て、同じ時計の一手番窓でフラグを降ろすことで、通路の実状態と
異常一覧を同じ寿命に揃える。

**どう守るか**:

- 停電・凍結中は実際のボタン操作結果で拒否理由と遺体報告の代替を返し、持ち札を減らさない
- 隔壁中と異常なしではボタンが従来どおり会議を開始する
- 停電中の遺体報告は会議を開始し、停電自体は残す
- 全条件に `blocks_emergency_button` の明示を要求し、文字列などの暗黙変換を拒否する
- 隔壁フラグと二つの通路が同じ 4 tick 境界で復帰することを確かめる

## 102. 道具の妨害間隔は品目内の共有名と世界共有を直交させる

**何を**: 道具 interaction でも `cooldown_group` を受け入れ、待ち時間キーを
`(ItemSpecId, cooldown_key)` にする。station_drill の停電と燃料凍結は同じ group と
25 tick を宣言し、隔壁は group に入れず10 tick の独立した待ち時間を持つ。三操作とも
`cooldown_scope: world` を維持する。

**なぜ**: 本家では扉以外の妨害は一つ使うと他の妨害も待ちに入り、扉だけが独立して短い。
これまでの制御端末は操作名ごとに独立していたため、停電直後に燃料凍結を続けて使えた。
また端末を二人へ配った後は、行為者別の待ち時間なら相方が同じ制約を迂回できる。
`cooldown_group` は行為をまたぐ問い、`cooldown_scope` は行為者をまたぐ問いなので、
どちらかへ統合せず直交させる。25 / 10 は本家の非扉30秒 / 扉17秒の比を、既存の最長値
25 tick を上限として写した第一版である。停電は10から25へ長くなるため、頻度は run で
改めて測る。

**どう守るか**:

- 停電と凍結を両方向に続けて実行し、別の行為者でも実結果が拒否されることを確かめる
- 隔壁の前後では非扉妨害を続けて実行でき、group へ紛れ込まないことを確かめる
- snapshot 復元後も、停電で始まった待ち時間が相方の凍結を拒むことを確かめる
- group 未指定の既存道具操作は action_name ごとに独立したまま保つ
- group 名は ItemSpecId で名前空間を分け、別品目の同名 group を誤共有しない

## 103. 配信先固定は既定を保ったまま実験設定で送信自体を外せるようにする

**何を**: `LLM_SESSION_ID_ENABLED` を解決済み実験設定へ追加し、既定は従来どおり
`true` とする。`false` のときは空文字や `None` を送らず、LiteLLM のリクエストから
`session_id` キー自体を省く。比較 profile は `station_drill_deepseek_auto` からこの
一項目だけを変える。

**なぜ**: run 037 では API タイムアウト 19 件の 90% がアオイとユラへ集中し、二人は
tick 9 以降の呼び出しの 76% が失敗した。OpenRouter の配信先固定が劣化した処理系へ
player を貼り付け続けた可能性と、キャッシュ率への効果を一度に比較するには、会話 ID の
生成方法ではなく送信の有無だけを変える必要がある。空値を送ると値検査で run 開始後に
失敗しうるため、無効化はキーの省略として表現する。

**どう守るか**:

- 未設定は `true`、未知の真偽値は起動前に拒否し、解決済み設定にも実効値を残す
- 実際の LLM 呼び出し境界で、無効時に `session_id` キーワードが存在しないことを確かめる
- prompt dataset の `request.kwargs` でも、有効時だけキーが残ることを確かめる
- 比較 profile 全体を基準 profile から組み立て、差が一項目を超えたら試験で止める

## 104. 売買ツールは商人の宣言でゲートし、負の宣言と対にする

**何を**: `merchants` を宣言したシナリオでだけ `buy_item` / `sell_item` を露出する。
判断は `ToolExposure._ECONOMY_TOOLS` に置き、会議機構 (`_MEETING_TOOLS`) と同じ形にする。
`disabled_tools` は宣言のある世界から個別に落とすためにそのまま効く (売れるが買えない町を
engine を触らずに書ける)。

**なぜ**: 商人の居ない世界に売買が並ぶと、対象候補が永久に空なのに毎ターン選択肢へ載る。
モンスターの居ない世界の `attack` で 3 手を捨てた形と同型で、`disabled_tools` が
「世界の中に無いものを出さない」ための**負の宣言**なら、経済のように「宣言した世界にだけ
現れる」機構には**正の宣言**が要る。両者は排他ではなく、正で出した上で負で個別に落とせる。

判断の置き場所は 1 つに保つ。露出可否がプロンプト本文側にも散ると、宣言が半分しか効かない
状態 (`tend_to_player` で踏んだ形) に戻る。

**どう守るか**:

- 宣言のある世界で両ツールが payload に出て、宣言の無い世界では出ないことを確かめる
- `disabled_tools` で買いだけ落としたとき、売りが残ることを確かめる
- 落としたツール名がプロンプト本文にも出ないことを、全ツール総当たりの既存試験で見張る
- 常在ブロック (`ALWAYS_PRESENT_TOOL_ORDER`) には足さず、条件付きブロックの末尾側へ置く

## 105. 場所の失敗と品の失敗を同じ error_code へ畳まない

**何を**: 売買の失敗を原因ごとに分ける。商人が同席していないのは `MERCHANT_NOT_AT_SPOT`、
その商人が扱っていないのは `BUY_ITEM_NOT_SOLD_HERE` / `SELL_ITEM_NOT_BOUGHT_HERE`。
同席商人が 0 人かどうかを、品名の突き合わせより**先に**判定する。

**なぜ**: 文面はどちらも「この場所では買えない」に見えるが、次の一手は「移動する」と
「品名を読み直す」で違う。同じコードに畳むと、trace の未発火理由を集計したときに
移動の問題と読み違いが混ざり、「エージェントは売買の失敗から学べるか」を測れない。
実装の都合 (解決段階と実行段階で失敗を作る層が違う) を、観測できる分類へ持ち込まない。

**どう守るか**:

- 同席商人ゼロで買うと場所の失敗、商人が居て扱っていない品なら品の失敗になることを固定する
- 失敗文には次の判断に要る値を載せる (不足額・扱う品と価格・所持数)
- 対処文にツール名を書かない。世界ごとに落とせるので、名指しすると嘘になる

## 106. 金銭が動くツールは部分成功を作らない

**何を**: `buy_item` / `sell_item` は数量ぶんすべて成立するか、1 つも成立せずに失敗するかの
どちらかにする。`give_item` の配列バッチ + 部分成功とは挙動が違うので、両ツールの
description にその違いを 1 行ずつ書く。

**なぜ**: 部分成功を許すと、1 回の呼び出しが何 gold 動かしたのかが結果から逆算しないと
決まらず、run 全体の通貨の流入・流出を trace から集計できなくなる。`give_item` に部分成功が
あるのは、複数の相手へ配る操作で 1 件の失敗が他を止める方が不便だからで、**金額が 1 つに
定まることの価値がそれを上回る**のが売買側の事情になる。

支払いより先に持ち物の空きを確かめるのも同じ理由。逆順にすると、入らなかったときに払った
金を戻す処理が要り、途中で壊れる余地を作る。

**どう守るか**:

- 所持金が足りないとき、金も持ち物も動かないことを確かめる
- 空きが足りないとき、支払う前に失敗することを確かめる
- 成立した売買の trace payload に、source と増減と単価を残す

## 107. 曖昧な対象は engine が代わりに選ばない

**何を**: 同じ品を複数の商人が扱うとき、engine は最安 (買い) や最高 (売り) を自動で選ばず、
候補と価格を添えて `MERCHANT_AMBIGUOUS` で返す。行為者は `merchant_label` で相手を指定する。

**なぜ**: どの商人と取引するかは、価格差のある世界では意思決定そのものになる。engine が
勝手に選ぶと「安い方を選んだ」という判断がエージェントの経験から消える。曖昧失敗 →
明示指定の 2 手はコストだが、判断の質感を優先する。失敗文に各商人の価格を載せておけば、
次の 1 手で判断まで終えられるのでコストは 1 手に収まる。

商人は `#N` の ordinal ではなく名前で指す。ordinal は「同名の対象が一覧に並ぶ」表示に
対する道具で、商人節は商人ごとに品を束ねる構造なので前提が違う。

**どう守るか**:

- 同じ品を 2 人が扱うとき、価格つきで選択を促して何も動かないことを確かめる
- `merchant_label` を指定すれば、その商人の価格で成立することを確かめる

## 108. 宣言だけ先に入れる PR は、配線で自動失効する猶予リストで通す

**何を**: `test_loader_config_fields_are_consumed` に `_PENDING_CONSUMERS` を置く。
「読まれなくてよい」`_ALLOWED_UNCONSUMED` とは別の表で、**まだ読んでいないだけ**の
フィールドを、読む予定の PR を理由に書いて一時的に許す。配線が済むと
`test_pending_consumers_are_removed_once_wired` が落ち、表から消さないと緑にならない。

**なぜ**: 宣言 → 表示 → 実行を別々の PR に割ると、宣言だけが入った時点では本番経路が
そのフィールドを読まない。この状態は「シナリオに書いても効かない」guard (#830 / #840) に
必ず引っかかるが、許可リストへ入れると「あとで使う」を理由に無期限で積める抜け道になる。
猶予そのものを許しつつ、**期限を人の記憶ではなく試験に持たせる**。

なお、ありふれた名前 (`spot_id` / `price` など) は guard 自身が認める穴 (同名フィールドの
衝突) で「読まれている」と数えられるため、この表に載せると誤って失効する。載せずに、
読まれない事実をコメントで残す。

**どう守るか**:

- 猶予リストの各項目に、実在するフィールドと空でない理由があることを確かめる
- 配線済みの項目が残っていたら落とす (次のフィールドの漏れが猶予の陰に隠れないように)
- 分割の理由を書けない項目は載せない。「あとで使う」は理由にしない

## 109. 基盤障害は時間を失った事実だけを世界内の記憶へ残す

**何を**: LLM 呼び出し例外、二度目の行動未選択、reason-first の最終失敗、ツール実行例外は、
本人の行動結果へ技術的原因を書かない。本人には「一瞬の空白」「迷い」「行動が形にならず
時間が過ぎた」という世界の中で観測できる結果だけを残す。`error_code`、例外文字列、
ライブラリ名は返却 DTO、trace、prompt dataset に残して運用上の診断に使う。

**なぜ**: run 038 では 182 呼び出し中 118 件の user prompt に `error_code=` または
`litellm` が入り、世界に存在しない API や通信障害が本人の経験として蓄積された。失敗した
turn を隠すと静かな失敗になる一方、「疲労」「寒さ」のような架空の原因を補うと、その原因を
世界の事実として推論してしまう。失った時間は残し、原因の分類だけを観測境界の外へ出す。

通常の `travel_to` や `restore_power` は、次の呼び出しに必要な世界とモデルの契約なので
残す。禁止語の検査はプロンプト全文ではなく、本人の経験になる【直近の出来事】の `[行動]`
行だけを対象にする。

**どう守るか**:

- 実 runtime で API 例外とツール実行例外を起こし、組み上がった user prompt の行動結果に
  技術語彙が無いことを確かめる
- 同じ失敗の返却 DTO と prompt dataset には診断コードと例外詳細が残ることを確かめる
- 既知の旧文面を検出器へ渡して違反行そのものを得ることで、対象抽出が空でも緑になる
  空振りを防ぐ

## 138. 出来事の同一性を、prompt の見た目に依存させない

**何を**: `episode_id` の fingerprint から、描画済みのテキスト (直近の出来事の
箇条書き `observed`、結果の要約文、ツール結果の message) を外す。材料は
「誰が・いつ・何の道具で・成否は」だけにする。付け方の版は id の**接尾辞**
`#e2` で示し、旧 id と機械的に見分けられるようにする。

**なぜ**: 以前は fingerprint に `observed` が入っており、**表示を変えると同じ
出来事の id が変わっていた**。実例は 2 つあり、どちらも表示の改善が目的の
変更だった。

- `c051a47a` (行動履歴に呼び出し形式を併記する): 行が 1 つ増えただけで id が変わる
- `5cf1b9b4` (直近の出来事の時刻表記を固定する): `[昨日]` ラベルが消えて id が変わる

調査時点でこれが壊す経路は無かった。snapshot は id をそのまま書き出して読み
戻し、主観補完は draft の id を持ち回り、開いたチャンクの bucket は snapshot に
含まれないので再エンコードも起きない。**壊れるのは再エンコードを伴う機能
(replay / バックフィル / 版を跨ぐ分析) を足したときで、そのとき気付ける保証が
無い。** 同一性の定義に表示を混ぜているのが根本なので、先に材料を絞る。

版を**接頭辞にしない**のは、afterglow の handle が `episode_id` の先頭 6 文字
から作られるため。先頭を版で潰すと実質 3 文字しか残らず、1 being 数十件の
episode で誕生日衝突が起きて想起が別の出来事を引き当てる (実資産の最大は
64 件/being)。接尾辞なら handle は uuid 部分から作られたままで、`endswith` で
版を判別できる。

旧 id の資産 (58 ファイル・1,777 件) とは断絶する。断絶自体は避けられないので、
**どちらの版か目で分かる**ことを優先した。

**どう守るか**:

- 観測文や結果要約の文言を書き換えても id が変わらないことを確かめる
- 誰が・いつ・何の道具で・成否が変わると id が変わることを確かめる (識別子として機能する)
- 新 id が接尾辞を持ち、旧 id と機械的に区別できることを確かめる
- 版が handle の桁を食っていないこと (新旧混在で handle が一意に引ける) を確かめる
- 材料を減らして衝突が増えていないことを、実 snapshot の全 episode で数える

**その後**: handle を作っていた見出しの欄 (afterglow) は Issue #1631 の段 9 で消した。版を接尾辞で示す決まりはそのまま残し、handle の桁を確かめる試験は消した。

**その後**: エピソードの同一性 (`episode_identity.py`) は、それを使う区切りの書き込みと一緒に記憶の部品の撤去 (#1631) の #1803 で消した。

## 110. 招集の判断材料には集合後の経過だけを末尾で渡す

**何を**: 会議を使う世界の自由時間では、最後の会議終了からの経過を世界の分数で
user prompt の末尾へ出す。会議前の初期区間だけは「ここでの行動が始まってから」と
言い分け、存在しない前回会議を捏造しない。会議中は、いま全員が集まっているため節を
省く。前回会議の終了理由や、招集を勧める文は出さない。

**なぜ**: run 039 までの 4 run で緊急招集ボタンは一度も試されなかった。ボタン自体は
集会室で prompt に出ていた一方、「最後に集合してからどれだけ経ったか」が無く、長い
空白を招集の判断材料にできなかった。押させるのではなく、時計から分かる事実だけを渡し、
使うかどうかは本人に残す。

起点は既存の `GamePhaseStore` にある現在の自由時間区間を使う。初期区間の
`trigger is None` と会議後の区間を区別でき、snapshot に新しい状態を重複して持たずに済む。
表示は毎 tick 変わるため、追記式の【直近の出来事】より前には置かず、
【進行中の異常】とともに最終指示直前の可変部分へ置く。

**どう守るか**:

- 会議終了直後から自由時間を進め、世界の分数が増えることを実 prompt で確かめる
- 会議中は節が無く、会議前は run 開始からの経過だと言い分ける
- 幽霊にも同じ事実が届くことを確かめる
- 実 prompt の文字位置で、【直近の出来事】より後かつ最終指示の直前にあることを確かめる

## 111. CI は固定した依存で振る舞いを試し、リポジトリ検査を別 job にする

**何を**: CI の通常試験と品質検査は、対応下限の Python 3.10 だけで
`uv.lock` を更新せずに同期して実行する。内部ホスト名の漏洩検査は pytest から外し、
checkout 全体を直接走査する `secret-leak` job にする。指数バックオフを確認する試験は
待ち時間を注入し、実時間を 14 秒消費せず呼び出された秒数を検査する。

**なぜ**: 新しい Python だけで通っても対応下限で通る保証にはならず、2 版の同一試験は
runner 消費だけを倍にしていた。無固定の pip 解決は確認時点で既存 `uv.lock` より 20 余りの
間接依存を新しい版へ進めており、CI と手元で別の環境を作る原因になっていた。lock を
真実源にすれば、CI の都度依存が動くこともない。

漏洩走査はロジックの振る舞いではなくリポジトリの状態を検査する gate であり、pytest に
置くと全件時間の 31% を占めたうえ、失敗理由も「テスト失敗」に埋もれる。独立 job なら
通常試験と並列に走り、守りを残したまま job 名で原因を読める。

**どう守るか**:

- workflow を構文として読み、main push と全 pull request に `secret-leak` があることを確かめる
- `secret-leak` が pytest でなく走査スクリプトを直接呼ぶことを確かめる
- 通常試験と品質検査の Python 3.10、setup-uv、locked sync、frozen run を固定する (uv の入れ方は design_decisions D1652 で PyPI からに変えた)
- 注入した 0.05 秒が 0.05 / 0.10 秒の待ちになり、既定値は 2 秒のままかを確かめる

## 112. 商人は世界の外との出入り口で、世界の中に物を溜めない

**何を**: 商人が受け取った品は世界から消え、商人へ払った gold も世界から消える。
商人は在庫を持たない。Phase 1 で商人の gold を無限にしたのと同じ扱いを、品の側にも
そのまま伸ばす。

**なぜ**: gold が無限に湧くのと品が消えるのは、別々の都合ではなく**同じ一本の理由**
から出ている。商人は世界の境界であって、世界の中の主体ではない。片側だけ決めると、
もう片側で「では受け取った品はどこへ行ったのか」が宙に浮く。

在庫を持たせる案は却下した。商人が買った品をエージェントが買い戻せる形になり、
「商人を経由した転売」が最短の稼ぎ方になる。エージェント同士の板で価格が形成される
ところを見たいのに、商人が値の緩衝材になってしまう。

エージェントの側から見ると、**消えたのか商人が持っているのかは区別できない**
(観測に出るのは「グスタフが薬草を 7G で買い取った」だけ)。区別できない以上、engine は
最も単純な形を選び、それを doc とコードのコメントに明示する。暗黙にしないことが要点。

## 113. 板は自動で約定させない。交差は潰さず機会として残す

**何を**: 市場の板に売り 20G と買い 22G が並んでも、engine は約定させない。
どちらも板に残り、誰かが自分の手番で受けたときだけ取引が成立する。

**なぜ**: **線は「手番の外か」ではなく「引き金に人が居るか」**にある。

| 形 | 可否 | なぜ |
|---|---|---|
| 誰かが自分の注文を取ったから動いた | よい | **引き金に人が居る**。通知も届く |
| engine が両者を勝手に選んで約定させた | だめ | **引き金に誰も居ないので、裁定に気づく機会が消える** |

当初は「手番の外で持ち物が変わると、知らないうちに世界が変わったことになる」と
書いていた。**これは広すぎる。** その理由だと、板越しの遠隔約定 (自分が居ない場所で
自分の品が売れる) まで禁じることになるが、それは既に動いていて、通知も届いている。
世界が自分の手番の外で変わってよく、**変えた人が居て、変わったことが観測として
届けばよい**。市場の教科書からは外れるが、ここでは取引が誰かの決定として起きること
の方が優先する。

結果として値の交差した注文が板に残る。これは欠陥ではなく**観測対象**である。
「18G で買えて 20G で売れる」と表示に並んだとき、それに気づいて取れるエージェントが
居るか — 裁定取引を自力で発見できるかという観測点になる。

人間が trace を読むと「約定漏れのバグ」に見えるので、集約の docstring と計画 doc の
両方に意図を書いた。`test_a_crossing_pair_stays_on_the_board` が正の対照で、
自動約定を足した瞬間に落ちる。

## 114. 市場の値は「注文の向き」ではなく「見る人が打てる手」で名づける

**何を**: 板の行が持つ値を `best_sell_price` / `best_buy_price` ではなく
`buy_price_gold` / `sell_price_gold` (見る人が払う単価 / 受け取る単価) にする。
表示も「18G で買える (出品 3件) / 15G で売れる (買い注文 2件)」と、その人が次に
打てる手の言葉で書く。読み出しは必ず見る人を引数に取る (`rows_for(viewer)`)。

**なぜ**: 板に出ている**売り注文は、見る人にとっては「買える」**で、注文の向きと
打てる手は逆になる。名前が注文の向きのままだと読む側が毎回変換することになり、
売り手視点と買い手視点が混線する。実装でも向きの反転は 1 箇所に閉じてコメントを置く。

文面の方は、人間が読んで「買い 1件」を過去の約定か未来の意思表示か取り違えたのが
発端。人間が迷う文面はエージェントも迷う。行動の言葉に寄せると、市場の状態を自分の
行動へ翻訳する一段が要らなくなり、交差も一目で読める。

見る人を引数に取るのは将来のためだけではない。**自分の注文は自分で受けられない**ので、
自分の注文を除いた値でないと「自分には買えない値」を相場として読ませることになる。

## 115. 板に預けたものが返せないときは、消さずに引き取り待ちで残す

**何を**: 市場の注文が期限切れになったとき、預かっていた品を持ち主へ返せない
(所持品が満杯) 場合は、板に「引き取り待ち」として残す。他人には見せず、持ち主には
状態つきで見せる。約定の側は断る相手が居るので、受ける前に空きを確かめて断る。

**なぜ**: `PlayerInventoryAggregate.acquire_item` は満杯だと**黙って品を捨てる**
(溢れイベントを出して return する)。市場でそのまま使うと「代金だけ払って品が消える」
という最悪の形の静かな失敗になる。

返却の側は断る相手が居ないので、同じ手が使えない。消すと預けた品が黙って消え、
溢れさせると所持品の不変条件が壊れる。板に残すのが唯一、何も失わない形になる。

持ち主には見せる理由は、見えないと**期限切れの通知を 1 回見落とした時点で取り戻す
手がかりが消える**から。他人に見せない理由は、買えないものを見せないため。

## 116. 板の注文は「同じ品目・同じ向きで 1 件まで」を状態の側で守る

**何を**: 同じ品目・同じ向きの自分の注文を、板に 1 件までしか置けないようにする。
引き取り待ちの注文もこの 1 件に数える。制限はツールではなくサービス (状態を持つ層)
に置く。

**なぜ**: 2 件あると取り下げ・値の付け直しが「品目 + 向き」でどちらを指すのか決まらず、
板の状態そのものが壊れる。番号 (#N) で指す形は「表示に出ている名前をそのまま渡す」
規約から外れるので採らない。

ツール側だけで禁じると、ツール以外の呼び出し元 (テスト・将来のコード・別の入口) が
曖昧な状態を作れてしまう。**不変条件はツールの都合ではない**ので、状態を持つ層で守る。

断り文は「既に出ている (取り下げるか値を変える)」と「先に預けたままのものを引き取る」
で分ける。次の一手が違うものを同じエラーコードに畳まない (#105 と同じ判断)。

## 117. 外部の変化には適応し、自分の誤りには従わない

**何を**: 板から買うとき、**出ている数が足りなければ買えるだけ買う**が、
**所持金が足りなければ 1 つも買わない**。同じ「求めたとおりにできない」でも、
構えを揃えない。

**なぜ**: 何が変わったのかが違う。板の中身は**他人の手番で変わる外の世界**で、
「3 つあると思ったら 2 つだった」は自分の誤りではない。あるだけ買うのが自然で、
断ると「もう一度読んで、数を直して、また呼ぶ」で 2 手番を失う。

所持金は**自分で見えている自分の状態**なので、足りないのは自分の計算違いである。
黙って数を減らして成立させると、意図と違う買い物が成立する。「3 つ買う」と決めた
判断は「2 つでもよい」を含んでいない。

どちらの場合も、結果には**求めた数と買えた数の両方**を残す。買えた数だけだと、
読む側は自分の意図が満たされたかを判断できない。

この線引きは市場に限らない。**外の世界の変化には黙って適応してよいが、本人の
指定が本人の持っている情報と矛盾しているときは、勝手に解釈して実行しない。**

## 118. 同じ量が動くなら、どのツールから動いても同じ形で記録する
**何を**: 所持金の変化 (`gold_delta` / `gold_after` / `gold_change_source`) は、
ツールごとに書かない。**dispatch でツール呼び出しを包み、前後の所持金を測って
残す。** 動いていなければ何も足さない。

**なぜ**: この 3 項目を出していたのは商人ツール (`buy_item` / `sell_item`) だけ
だった。板を通した売買は 7G 増えても記録が 1 行も出ず、実 run
(`market_town_v3_first`) の分析で所持金の台帳が組めなかった。同席取引
(`trade_accept`) も `gold_after` だけ落ちていた。**商人ツールだけが出していたのは、
先に作ったからで設計判断ではない。**

ツールの側に書いて回ると 2 つ壊れる。

1. **書き忘れが静かに漏れる。** 例外は出ない。run が終わって「所持金の推移が
   引けない」で初めて気づく
2. **「どのツールが gold を動かすか」という知識が、分析器の側へ漏れる。**
   分析器はツールの一覧を持つことになり、ツールを 1 つ足すたびに壊れる

包む側で測れば、将来クエスト報酬や戦利品で gold が動いても、同じ経路を通る限り
自動で残る。**足す人は何も知らなくてよい。**

ここで効いているのは**規則を人に守らせるのではなく、構造で守る**という形である。
「全ツールが記録する」と規則で書くと、各ツールに責務が残り、選び忘れの余地が
消えない。包む側に置いた時点で、守るべき人がいなくなる。

出どころの名前だけは handler の申告を使う (`merchant_buy` のような意味のある名前を
ツール名で潰さない)。**数字は必ず測った側を使う** — 申告は書いた時点の想定で、
実際は世界で起きたこと。台帳を組むのは後者でなければならない。

読めなかったことを 0 と書かない。**動かなかったのと区別がつかなくなる。**

同じ形は品の移動にもあった (`item_name` を結果に入れているのは市場ツールだけで、
対面の品名が分析側から取れない)。**「同じものが動くなら同じ形で記録する」は
gold に限った話ではない。**

## 119. 食料腐敗の進行ルールは Item 集約に置く

**何を**: 腐敗の進行ルール (`acquired_at_tick` 遅延初期化、閾値判定、`spoiled=True`)
は `ItemAggregate.advance_spoilage` に置く。`FoodSpoilageStageService` は走査と
永続化だけを担当し、初回腐敗の観測材料は集約が`ItemSpoiledEvent`として積む。

**なぜ**: いつ腐るかはアイテム個体のライフサイクルである。application の stage に
置くと、別の境界づけられた文脈や別経路が同じルールを再実装しやすい。

**どうしないと壊れるか**: `use_item` / 表示 / 取引が `state['spoiled']` を読む一方、
進行だけ stage に残ると「いつ腐るか」の真実源が分裂する。

## 120. 腐敗食の消費数値は Item ドメインで計算する

**何を**: 腐敗食を食べたときの HP ダメージ (10) と空腹回復の半分 (`int` 切り捨て)
は `spoiled_consumption_outcome` が計算する。`PlayerStatus` への適用と LLM 向け
メッセージは executor が行う。

**なぜ**: 「腐って食べると何が起きるか」はアイテムのルールなのに、LLM executor
が定数と HUNGER 抽出を持っていた。計算と適用を分けると、将来の handler やデモが
同じ数値を参照できる。

**どうしないと壊れるか**: 別経路が同じ定数を再実装し、10 と 0.5 が分裂する。
新鮮パスの `ConsumableUsedEvent` 経路と腐敗パスの数値がずれても気付きにくい。

## 121. 世界の厳しさは宣言で決める。既定は据え置く

**何を**: 空腹と疲労の進み方を `needs.hunger_per_tick` / `needs.fatigue_per_tick`
としてシナリオから宣言できるようにした。**宣言しない世界は 1 ミリも変わらない**
(空腹 +1 / 疲労は自然増加なし)。

**なぜ**: 宣言できないと、シナリオ側で希少性を作れない。市場の v3 run では
**80 手番 × +1 = 最大 80 で、上限 100 に届く経路が存在しなかった**。つまり
パンの必要量は 0 個で、全員が**必要がないのに食べていた**。

このとき run 分析は「空腹が弱かった」と読んでいたが、正しくは「**空腹という力が
最初から働いていない**」である。**分子だけを見て「弱かった」と読み、上限に届く
経路があるかを確かめていなかった。** 分母を見ずに分子を読む形の一例である。

既定を据え置くのは比較のため。既定が動くと**過去の run と比べられなくなる**。

**空腹だけ 0 を弾く。** 0 を通すと「空腹の無い世界」が黙って出来上がる。空腹が
要らない世界は `needs` 節ごと書かなければよい (既定は据え置き) ので、**0 は
書き間違いの形しか持たない**。疲労は既定がそもそも 0 なので、0 を弾くと既定値を
宣言で表現できなくなる。**同じ節でも、既定が違えば許す範囲も違う。**

宣言を読めることと、宣言が効くことは別である。設定に値が入っていても、世界を
組むところで渡し忘れれば既定のまま進み、**変えたつもりで変わっていない run** に
なる。例外は出ないので、run が終わってからでないと気づけない。だから試験は
**実際に手番を進めて、宣言どおりに増えること**まで見る。

## 122. 疲労の行為コストと限界時ブロックはドメイン政策に置く

**何を**: 行為種別ごとの疲労増減量と、疲労 100 で止める行為種別は
`FatigueExertionPolicy` (値オブジェクト) に集約する。LLM ツール名から
`ExertionKind` への写像だけ `SpotGraphToolExecutor` (application) に残す。

**なぜ**: 同じルールが LLM executor のクラス定数にしか無いと、別経路
(将来の非 LLM 入口・テスト・別 executor) がコスト無し実行や block 忘れを
起こしやすい。疲労の「どの行為で何点」「限界で何を止める」は個体の状態
(`PlayerStatusAggregate`) ではなく世界の政策である。

**どうしないと壊れるか**: prefix cache のために tool list は不変のまま、
実行時だけ止める判断 (#1 / #2) の数値が executor に埋もれ、wait 回復 20 と
attack +5 の関係が読めなくなる。連続待機の回帰ガードも executor 定数参照
から外れると、弱い値への逆戻りを検知しにくくなる。

## 123. 欲求 tick の増加と限界ダメージは PlayerStatus が持つ

**何を**: 欲求の自然増加と、飢餓・疲労限界の毎 tick HP ダメージ判定は
``PlayerStatusAggregate.apply_needs_decay_tick`` が持つ。
``SpotGraphNeedsDecayStageService`` は走査・保存・イベント配信・
evidence 配線だけを担当する。

**なぜ**: 「空腹が限界なら毎 tick HP が減る」は個体の状態ルールなのに、
application stage に閾値判定まで埋もれていた。別経路が同じ判定を再実装すると、
95 (疲労限界ダメージ) と max (飢餓) と 0=無効 (既存シナリオ) が分裂する。

**どうしないと壊れるか**: ダウン中スキップ、``increase_need`` 後即 starvation
判定、``starvation_damage_per_tick=0`` で既存シナリオ不変、という条件が
stage に散在すると読み取れなくなる。

## 139. 読めなかった値を、既定値として黙って返さない

**何を**: 現在の世界時刻が読めなかったとき、0 を返す前に必ず警告を残す。時刻の
提供者を呼ぶ経路は、まず提供者、次に runtime の順に試し、**どちらも駄目なら
そう言う**。

**なぜ**: 実 run で、持ちかけた取引の提案が**次の手番で流れた**。3 回連続で
流れ、4 回目でようやく成立している。エージェント側は正しく動いていて
(「こっちが返事をする前に流れちまった」)、機構が壊れていた。

原因は、時刻の提供者のメソッド名が `get_current_tick` なのに `current_tick` を
呼んでいたこと。**`AttributeError` を握り潰して 0 を返していた**ので、板の注文も
取引の提案も期限が「世界の開始から N 手番後」になっていた。

**0 は、時刻としては正当な値である。** だから「読めなかった 0」と「本当に 0」が
区別できない。区別できない既定値を黙って返すのは、**失敗を成功の形に変換して
いる**のと同じ。

集約の計算式 (`created_tick + expires_in_ticks`) は正しく、**集約の単体試験は
全部通っていた**。壊れていたのは「何を渡すか」の側で、そこには試験が無かった。
**部分が全部正しくても、繋いだ全体は違いうる。**

## 140. 期限を宣言したら、期限が来る経路まで繋ぐ

**何を**: 板の注文の期限切れを片付ける tick stage を、取引の提案の片付けと
並べて置く。

**なぜ**: 片付ける処理 (`MarketService.expire_orders`) は書いてあったが、
**どこからも呼ばれていなかった**。期限は宣言されているのに注文が永久に板へ
残り、v3 の実 run では t33 に出した注文が t80 まで生きて値の付け直しまで
受けていた。

**「期限がある」と宣言した世界で期限が来ないのは、世界が嘘をついている**状態
である。出した人は「置いておけばいつか流れる」と思って板を離れる。

書いただけで呼ばれていないコードは、**動いていないのに存在する**ので、探しても
「実装済み」に見える。同じ形は他にもありうるので、**期限まわりは 1 か所に
まとめて置く** — 次に足す人が、隣に並んでいるものを見て気づけるように。

## 124. プロンプトのテンプレートに、特定の世界の固有名詞を書かない

**何を**: 全シナリオで共有されるプロンプトのテンプレートには、その世界に属する
固有名詞を書かない。書くなら、世界の側から渡す。

**なぜ**: 長期記憶 (L5) を作らせるテンプレートに、漂流島シナリオ時代の文言が
残っていた。

```
"world_view": "この島について 2-3 文で (narrative voice)"
```

市場町の run で **long summary 9 件すべてに「島」が出現**し、その出力は
【自己像と世界観】として**毎ターンのプロンプトに注入**されていた。エージェントは
市場町にいながら「ここは島だ」と読まされ続けた。

**シナリオにも system prompt にも「島」は 1 件も無い。** 世界を汚染していたのは
テンプレートだけで、**世界の側をいくら調べても原因が出てこない**形になる。

見つけにくさが本質的である。テンプレートは全 run で共有されるので、**間違った
世界の run でだけ症状が出る**。しかも long summary は長い run でしか発火しない
ので、短い run では現れない。

検査は置いたが、**網羅ではない**。既知の語の一覧を見るだけで、新しいシナリオの
固有名詞は自動では増えない。**規則そのものは機械で証明できない**ので、一度混入した
語が戻ってこないことだけを保証する仕掛けとして置いてある。

**その後**: 長期記憶 (L5) と【自己像と世界観】は、#1824 で消した (#1828)。ここで直したテンプレートも一緒に無くなった。テンプレートに世界の固有名詞を書かない決まりは、残る要約の指示にも当てはまる。

## 125. 発話ぼかしの発火は is_severely_fatigued が決める

**何を**: 発話ぼかしの発火は ``PlayerStatusAggregate.is_severely_fatigued()`` が
決める。語を伏字化する確率と正規表現は ``speech_executor`` の演出として残す。

**なぜ**: 疲労 85 以上で呂律が回らないのは個体の身体状態なのに、
``speech_executor`` が閾値 85 を再定義していた。severe の意味が executor と
集約で分裂すると、プロンプトの「severe で朦朧」と実発話がずれる。

**どうしないと壊れるか**: 集約側だけ 85 を動かしても発話は古いまま。身体状態の
ルールを直したつもりが、他者が聞く発話だけ変わらない。
## 141. できないことは、できない理由の粒度で見せる

**何を**: 職能や世界の状態で操作がすべて落ちた物体には、操作一覧の代わりに
「いまのあなたに扱える操作はない」と注記する。**存在層 (幽霊など) が理由のときは
注記しない。**

**なぜ**: 実 run の `INTERACTION_ACTION_NOT_FOUND` 5 件 (失敗の半分) は全件が同じ
形だった。職能が合わないと操作の一覧が**角括弧ごと消える**。ところが system prompt
は「表示された操作の中から選べ」と指示している。**表示が 1 つも無いのに選べと
言われた**エージェントは、`examine` のような動詞を発明する。

決定的なのは、**時間で戻らないことは既に注記されていた**こと
(「今は採れない・時間を置けば戻る」)。**時間ゲートは注記され、職能ゲートは
注記されない。この非対称だけが原因**だった。

### 理由を断定しない

注記に「あなたの仕事では扱えない」と書くと、**理由が職能でないときに嘘になる**。
同じ経路で世界の状態でも落ちる。書くのは「扱えない」という事実だけにする。

### 理由によって、見せてよいものが違う

存在層が理由のときは注記自体を出さない。出すと**「生者にだけ見える操作がある」
ことを漏らす**。そのため builder では「役割・世界状態だけで判定した集合」と
「存在層まで含めた集合」を別々に持つ。**一緒くたにすると、見せない理由まで
見せてしまう。**

### 拒否の文は、2 つの誤読を両方塞ぐ

送った名前に触れないと「実在するが権限が無い」と読んで同じ名前で再試行する。
名前の話だけで終えると「名前を直せば通る」と読む。**その名前が無いことと、名前を
変えても通らないことを、両方言う。**

## 126. 言葉が自然に書ける形を、世界の側が受け取れるようにする

**何を**: `give_item` の各要素に `quantity` を足し、頼まれた数だけ渡す。手元が
足りなければ**渡せるだけ渡し、頼んだ数と渡した数の両方を返す**。

**なぜ**: 実 run で、焼き手が `quantity: 2` を指定し「ふたつとも持ってけ」と
言ったのに **1 個しか動かなかった**。しかも部分失敗としても記録されず、
**合計 2 個のパンが、両者に気づかれないまま移動しなかった**。

原因は、`gives` の要素に `quantity` が**存在しなかった**こと。engine は知らない
引数を黙って捨て、1 要素 = 1 個の設計どおり 1 個動かして成功を返した。
**丸めていたのではなく、最初から見ていなかった。**

ここで効いているのは、**schema が「2 個渡す」を表現できないのに、エージェントは
自然にそう書いた**という食い違いである。言葉の側が正しく、世界の側が追いついて
いなかった。「2 要素に分けて書け」と教える道もあったが、それは**世界の都合に
言語を合わせさせる**形になる。

### 未知の引数を黙って捨てる問題は、これに限らない

今回は `quantity` だったが、**エージェントが発明した引数はすべて黙殺される**。
成功が返るので、独白と結果の食い違いは trace を精読しないと見えない。**別の
問題として残っている** (学習可能な形で無視する = 結果に「受け取れなかった引数」を
出すのが正しい)。

## 127. 申告は真実ではなく期待として使い、実測と照合する

**何を**: ツールは「この人たちの所持金が動くはず」を申告する
(`gold_affected_player_ids`)。**数字の真実は測った結果**で、申告は照合にだけ使う。
食い違えば警告を出す。

**なぜ**: 所持金を「呼び出した人の財布」だけ測っていたので、二者間の取引で
**受け取った側の行が 1 件も出なかった**。台帳は差額から逆算するしかなく、
**逆算が要る時点で「どのツールが誰の gold を動かすか」の知識が分析器へ戻って
いる**。

素直な直し方は「ツールが影響を受けた人を申告し、その人を測る」だが、これだと
**申告漏れが静かな失敗になる**。申告に無い人の gold が動いても、誰も測らないので
誰も気づかない。

そこで**測るのは全員**にして、申告は**期待**として残した。申告と実測が食い違えば
警告が出るので、**申告漏れそのものが検出できる**。申告が負債から検査に変わる。

「申告に無い人の gold が動いた」は、どこかで意図しない移動が起きているという
ことなので、**まさに検出したい事故**である。

### 全員測るのは、いまの人数だから

人数が増えたら「申告された人だけ測る」形へ移す判断が要る。ただし**この理由が
消えていると、後の人が「非効率だ」と思って申告ベースへ変え、申告漏れが静かな
失敗として復活する**。移すなら、申告漏れを別の方法で検出できるようにしてから。

## 128. 相手が居ないことを、自分が動けないことと書かない

**何を**: 板の表示で「売れない (買い注文なし)」「買えない (出品なし)」をやめ、
「買い注文なし (出品して待てる)」「出品なし (買い注文を出して待てる)」にする。

**なぜ**: 実 run で、焼き手がパンを持ち空腹 88 の状態でこう書いている。

> 掲示板にはパンの買い注文がないから、手持ちのパンを売っても買い手がつかない
> ——となると、自分で薬草を摘めるようになるのが一番確実な道だ。

**彼女は板で売る可能性を検討したうえで棄却している。** 棄却の根拠は「買い注文が
ない」。しかし**出品は買い注文の有無と関係ない** — 出品は買い手を待つ行為である。

「自分が何をできるかで書く」という原則自体は正しかったが、**「売れない」が売り側の
口を塞がれたと読ませた**。実際には「いま即座に売れる買い注文は無い」だけ。買い注文が
尽きた手番以降、この行は **66 手番にわたり全員に「パンは売れない」と表示し続けた**。
板の前でパンを 2 つ以上持っていた手番が 16 回あり、**出品は起こりえた**。

**打てる手を塞いで見せる方が、冗長よりはるかに悪い。**

買い側も同じ形をしていたので同時に直した (`market_bid` は 2 つの run で 0 回)。
**片側で見つけた誤読は、鏡像側も必ず確かめる。**

### 統計だけでは、この原因に辿り着かない

出品 0 回という数字からは「希少だから手放さない」まで読めるが、**なぜ起きなかった
かは独白にしか書いていない**。0 だった軸については、その行動を検討した独白を探す。

## 129. 失敗文は「何が駄目か」だけでなく「次にどこへ行けばよいか」を言う

**何を**: 助言に**道具の名前を書かない**。識別子だけでなく、その道具を指す日常語も
書かない。書くなら露出判断を通す。

**なぜ**: 「相手が別アイテムを **drop** するのを待つか」という助言が 4 か所にあった。
`drop_item` を落とした世界では**打てない手を勧める**ことになる。

**無効化のラチェットは全件緑だった。** `test_disabled_tools_vanish_from_the_prompt`
は助言文も見ているが、**識別子 (`drop_item`) しか照合していない**。実際の文は
**動詞だけ** (`drop`) で書かれていて素通りした。

**ラチェットが守備範囲を偽っていた**とも言える。名前は「プロンプトから消える」なので、
読む人は日常語も含むと思う。実際は含まない。**名前に実装を合わせる**方向で広げた。

### 限界を書いておく

日常語の一覧は手で書く。「拾う」「置く」のような日本語の言い換えは捕まらない。
**これは網羅ではなく、一度踏んだ形が戻らないための仕掛け**である。

### 併せて: 止めるだけでなく、行き先を言う

`disabled_tools` に memo を書くと、fail-fast は「指定できるのは: attack, ...」と
**できないこと**を言うが、「memo は実験設定で落とす」とは言わない。止めてくれたのは
正しいが、**次にどこへ行けばよいかが無い**。

`INVALID_DESTINATION_LABEL` が「有効な destination_label: "市場の広場"」と**正解を
列挙している**のが最良の形で、他の失敗文もここへ寄せる価値がある。**行き先の無い
拒否は、拒否された側に推測を強いる。**

## 130. 遠さの段階は、それぞれ違うものを届ける

**何を**: 隣から漏れ聞こえる言葉 (MUFFLED) は、全文ではなく**断片** (先頭 20 文字 +
「…」) にする。

**なぜ**: 聞こえ方は 3 段階あるのに、真ん中が近いほうと同じだった。

| | 直す前 | 妥当か |
|---|---|---|
| CLEAR (同じ場所) | 全文 | ○ |
| **MUFFLED (隣の部屋)** | **全文** | **×** |
| FAINT (さらに遠い) | 内容を伏せる | ○ |

**「遠くの声が聞こえる」と言いながら、完全な書き起こしを渡していた。** 段階が
3 つあるのに、実質 2 つしか機能していない。

**隣の部屋の会話を一言一句知っている世界では、移動して話を聞きに行く理由が薄く
なる。** これは節約の話ではなく、世界の壊れ方の話である。

断片の長さは、**誰が何の話をしているかは分かり、中身までは分からない**量にする。
全部伏せると FAINT と区別がつかなくなり、また段階が減る。

### prose と構造化側を食い違わせない

prose だけ切って構造化側に全文を残すと、**記憶や分析にだけ完全な書き起こしが残る**。
どちらが本当に聞こえたのか分からなくなるので、両方を同じ断片にする。

**節約はおまけである。** 実測では 1 手番あたり 890 文字ぶん減るが、金額で正当化
すると、後の人が「効果が小さいから戻そう」と考える。**質感のための変更が、たまたま
節約にもなった**が正しい順序。

## 131. 同じ身体に付く Being の一意性は、取り出した列に対する判定である

**なぜ**: ``BeingAttachmentResolver`` が ``BeingRepository`` をコンストラクタで持ち、
``find_all_attached_to`` / ``find_by_id`` していた。ドメインサービスがリポジトリの
ラッパーになっていた。同一 (world, player) に attach 中の Being が 0..1 かという
横断ルールは世界のルールだが、永続化からの取り出しは application の仕事である。

**何を**:

- 永続化からの取得は application 層の ``BeingAttachmentResolver`` に置く
- 0 / 1 / 2件以上の判定は ``unique_attached_being``（domain、リポジトリ無しの純関数）
- ``Being.attach`` は「1 Being の attachment 高々 1」を守る。横断の一意性は取り出した
  列に対する判定
- 公開メソッド名（``resolve_attached_being`` / ``resolve_being_id`` /
  ``resolve_player_id``）は変えない。想起ツール等 40 ファイル超の呼び出し入口を壊さない

**設計判断**: 集約単体では「同じ身体に複数 Being が付いていないか」を試せない。
Repository が返した列を domain の純関数で判定し、application が両者を組み立てる。
## 142. 観戦用の所持品一覧は application 照会が公開走査を使う

**何を**: 観戦 HTTP `GET /sessions/{id}/inventory/{character_id}` の所持品一覧は、
`PlayerInventoryQueryService.list_held_items` が `iter_occupied_slots()` で読み、
同じ `item_spec_id` の個数をまとめる。

**なぜ**: この経路だけ presentation が所持品集約の `_max_slots` を直接読み、
`SlotId` ループでスロット走査まで HTTP 層でやっていた。LLM 向け所持品表示を
application 照会へ寄せたあとも、観戦 API だけ内部表現に依存したまま残っていた。
スロット表現を変えると観戦だけ壊れる。

**presentation に残すもの**: セッション解決、player の数値 ID 変換、
`id_mapper` による `item_spec_id` の文字列化。集約内部フィールドは読まない。

**プロンプト用 `_build_inventory` とは揃えない**: そちらは
`(spec_id, is_spoiled)` で行を分ける。観戦 HTTP は spec_id だけでまとめる。
腐敗と新鮮を分ける必要が観戦側には無い。

**装備スロットは出さない**: 走査は所持スロットの `iter_occupied_slots()` のみ。
inventory 集約が無い、または空のときは空一覧を返す（セッション無しだけ 404）。

## 132. 記憶ツールの BeingId は手番入口で一度だけ決める

**何を**: memo / recall / explore / semantic search の aux ツール executor は
``ActingBeing``（``player_id`` + ``being_id`` の対）を受け取る。
``BeingAttachmentResolver`` は executor が持たない。

**なぜ**: 変換は ``PlayerId → BeingId`` の一種類なのに、各 executor が
``BeingAttachmentResolver`` を注入され、付着の一意性まで葉が知っていた。
PR #1209 で判定を domain へ移したあとも、変換そのものは 40 ファイル超に
複製されていた。

**入口**: ``WorldRuntime.run_llm_auxiliary_tool`` が ``ensure_attached`` の
直後に ``resolve_being_id`` し、``ActingBeing`` として handler に渡す。
未付着は入口の ``being_id is None`` だけが ``INVALID_STATE`` を返す。

**まだ残る Resolver 利用**: prompt_builder / chunk / 信念 / hint service は
今回触らない。次切片で prompt の記憶節へ ``BeingId`` を渡す。

**置かないもの**: スレッド局所の「いまの Being」状態。入口で決めた対を
引数で渡すだけにする。

## 133. プロンプト組み立ての BeingId は手番入口で一度だけ決める

**何を**: `IPromptBuilder.build` は `ActingBeing` を受け取る。
`DefaultPromptBuilder` は `BeingAttachmentResolver` を持たない。

**なぜ**: 手番は `PlayerId`、経験は `BeingId`。builder が葉で付着を引くと、
aux ツール (#132) と同じ変換が本編ターンにも複製される。

**入口**: `WorldRuntime.build_full_prompt` が `_acting_being_for` で一度決める。
`run_llm_auxiliary_tool` も同じ helper を使う。

**まだ残る Resolver 利用**: 受動想起 retrieve / chunk / 信念 / hint は
エピソードが持つ being_id、または呼び出し側から BeingId を渡す次切片。

## 134. 受動想起と chunk は呼び出し側の BeingId を使う

**何を**: `retrieve` と `after_action_recorded` / scheduler `submit` は
`BeingId` を引数で受け取る。これらのサービスは `BeingAttachmentResolver` を持たない。

**なぜ**: プロンプト入口 (#133) で既に `ActingBeing` があるのに、想起と
chunk が葉で付着を引き直していた。エピソード VO はまだ `player_id` しか
持たないので、今は引数で渡す（VO への being_id 追加は別切片）。

**入口**: prompt 節は build 済みの being_id。chunk は
`WorldRuntime._record_action_result` の `_acting_being_for`。

**その後**: 受動想起 (`EpisodicPassiveRecallRetrievalService` の `retrieve`) は記憶の部品の撤去 (#1631) の #1796 で消した。chunk の書き込みは残る。

区切りの書き込み (`EpisodicChunkCoordinator`) と主観補完の scheduler も、#1803 で消した。

## 135. 応答として書かれた文を、常時出る注記に流用しない

**判断**: シナリオが条件ごとに書く `failure_message` は、**その操作を呼んだ人
ひとりへの応答**である。一覧に常時出る注記へ流用しない。注記は engine が型を
持ち、**作者が書いた語 (値の呼び名) だけ**を差し込んで組む。

**なぜ**: 実際に描画して分かった。市場町の文面は

> 窯の火加減も捏ね方も分からない。パンを焼けるのは**あの人**だけだ。

呼び出しへの応答としては完結している。ところが常時表示の注記に置くと、

- 「あの人」が誰か分からない。**注記は「では誰なら」に答える位置にいる**のに、
  その問いに答えていない
- 焼き手は 2 人 (トム・ノラ) いるのに単数で書かれている。**シナリオの事実と
  食い違う**
- 刈り手の行にも同じ文が出る

書かれた場所と使う場所がずれた文面の流用で、`tend_to_player` / `give_item` で
踏んだ形 (プロンプト本文がツールを宣伝し続ける) の親戚である。

**engine が決め打ちしてよいのは型だけ**: 出すのは `<値の呼び名>だけが扱える`。
一度 `<呼び名>の仕事` にしかけて差し戻した。生業なら通るが、`race` を同じ経路に
通すと **「エルフの仕事」** になる。属性の種類を engine が決め打ちすると嘘になる。

呼び名が宣言されていなければ `いまのあなたには扱えない` に落とす。ここで
「あなたの生業では」と書くと、生業以外の属性で同じ嘘をつく。**世界が名前を
持っていないものを、engine が代わりに名付けない。**

**伏せた属性が混ざっても、公開されたぶんはそのまま出す**: 「伏せた属性が
混ざっていたら全部伏せる」にすると、**公開側の出力が伏せた属性の有無で変わり、
そこから伏せた属性の存在が読める**。伏せ方が伏せていることを漏らす形で、これは
伏せる仕組み全般に効く。

**関連**: #1197 (注記は理由を断定しない) は撤回していない。engine が理由を
**推測しない**規律であって、**作者が宣言した呼び名を伝えない**という意味では
なかった。

**残る穴**: 注記は物体単位なので、使える操作が 1 つでも残ると、落ちた操作の
存在自体が見えない。摘み手は石窯に「パンを焼く」があることを知る道が無い。
`docs/agents_reaching_past_the_world.md` の「教わることができない」と同じ根で、
今回は解いていない。

## 143. 値の呼び名は、全部に付けるか 1 つも付けないか

**判断**: `player_attributes[].values` の呼び名は、**全部に付けるか、1 つも
付けないか**の二択にする。一部の値にだけ付ける形は用意しない。

```json
"values": {"picker": "摘み手", "baker": "焼き手", "reaper": "刈り手"}  // 全部
"values": ["picker", "baker", "reaper"]                              // 1 つも無し
"values": {"picker": null, "baker": "焼き手"}                         // 書けない
```

**なぜ**: PR 4 (`values` の検証) で列挙が実質的に義務になったので、この制約が
初めて効くようになった。「呼び名を付けたい値が 1 つあると、実際に使う値すべてに
呼び名を付けなければならない」。

書けるようにしなかった理由は、**同じ属性の中で行の形が変わる**こと。呼び名の
ある値では `[焼き手だけが扱える]`、無い値では `[いまのあなたには扱えない]` に
なり、読み手には**その違いに意味があるように見える**。実際には作者が書いたか
書かなかったかでしかない。

#1220 で型を選んだとき「書いたか書かなかったかが、文の形として漏れない」ことを
利点として採った。属性の単位でその性質を保つ。

**この判断を見直す条件**: 値が多く、そのうち 1 つだけが行を制御する属性が実際に
出てきたとき。いま同梱シナリオで `values` を宣言しているのは市場町の生業だけで、
3 つとも呼び名が要る。**困っている実例が出るまで形を増やさない。**

## 144. memo 完了 hint は呼び出し側の BeingId を使う

**何を**: `MemoCompletionHintService.detect` / `augment_result_summary` は
`BeingId` を引数で受け取る。このサービスは `BeingAttachmentResolver` を持たない。

**なぜ**: 手番入口 (#133) と行動記録 (#134) で既に対があるのに、hint だけが
葉で付着を引き直していた。

**入口**: `run_phase_b` が `WorldRuntime._acting_being_for` で一度決めて渡す。
未付着なら hint だけ skip し、行動結果は残す。

## 145. 信念固着と再解釈は呼び出し側の BeingId を使う

**何を**: `BeliefConsolidationCoordinator` と
`EpisodicReinterpretationCoordinator` の `after_turn_completed` /
`flush_player` は `PlayerId` と `BeingId` を両方受け取る。これらの
サービスは `BeingAttachmentResolver` を持たない。手番カウンタは
`player_id`、evidence / recall / journal は `being_id`。

**なぜ**: 手番入口 (#133) と行動記録 (#134) で既に対があるのに、
ターン完了 sidecar だけが葉で付着を引き直していた。

**入口**: `WorldLlmTurnTrigger` が `_acting_being_for` で一度決めて渡す。
未付着なら sidecar だけ skip し、手番は止めない。

**その後**: 再解釈の coordinator (`EpisodicReinterpretationCoordinator`、`LLM_EPISODIC_REINTERPRETATION_ENABLED`) は Issue #1631 で消した。

固着の coordinator (`BeliefConsolidationCoordinator`) と、その帰属の節 (`BELIEF_ATTRIBUTION_ENABLED`) は、記憶の部品の撤去 (#1631) の #1790 で消した。

## 146. 記憶リンクとクラスタ昇格は呼び出し側の BeingId を使う

**何を**: `EpisodicMemoryLinkApplicationService` と
`EpisodicSemanticClusterPromotionService` は `BeingId` を引数で受け取る。
これらのサービスは `BeingAttachmentResolver` を持たない。昇格フロンティアは
まだ `player_id` keyed。

**なぜ**: chunk (#134) と prompt (#133) と探索ツール (#132) で既に対があるのに、
link / promotion だけが葉で付着を引き直していた。

**入口**: chunk の `on_episode_committed`、prompt の受動想起候補、
`ActionResultRecorder` の `on_after_tool_turn`、explore の `ActingBeing`。

**その後**: クラスタ昇格 (`EpisodicSemanticClusterPromotionService`) は、記憶の部品の撤去 (#1631) の #1792 で消した。記憶リンクは受動想起と一緒に続く PR で消す。

記憶リンク (`EpisodicMemoryLinkApplicationService` と store) も、読み手の受動想起を #1796 で消したあと、#1799 で消した。

## 147. Unit of Workは永続化に絞り、CommandScopeがcommand完了を統括する

**何を**: 1回のアプリケーションコマンドは1つの `CommandScope` で実行する。
`UnitOfWork` はtransaction開始、同じtransaction資源の提供、commit、rollbackだけを担う。
イベント収集、同期ハンドラの収束処理、commit後配送は、それぞれ操作単位collector、
dispatcher、handoffへ分離し、`CommandScope`が順序を統括する。

**なぜ**: 現行はUoW、`TransactionalScope`、repository、`EventPublisher`がそれぞれ
確定処理の一部を持ち、インメモリとSQLiteでも保存時期が異なる。repositoryの生成方法に
よって独自commitの有無が変わるため、同じcommandでも部分更新やrollback後配送を
構造的に防げなかった。

**どう守るか**:

- scope参加repositoryは同じtransaction資源から生成し、独自commit / rollbackを禁止する
- 同期ハンドラは現在のscopeへ参加し、外部配送や新しいtransactionを開始しない
- rollback時は操作単位collectorを破棄し、commit後配送を開始しない
- commit後配送失敗でcommit済み状態をrollbackしたことにしない
- 再試行が必要な配送はdomain状態と同じtransactionでoutboxへ保存する
- 暗黙の入れ子scopeを拒否し、commit後ハンドラだけが新しいscopeを開始できる
- インメモリとSQLiteへ同じ原子性契約試験を適用する
- 詳細な状態遷移、失敗時契約、移行表は
  `docs/refactor_plans/command_scope_contract.md` を正本とする

**関連**: #1094 / #1095 / 判断 #88。

## 148. 新CommandScopeはtransaction状態機械だけを本番配線の外で先に固める

**何を**: 新しい `CommandScope` は、イベントAPIを持たない `TransactionPort` だけに依存し、
begin、commit、rollback、暗黙の入れ子拒否を一方向の状態機械として実装する。最初のPRでは
既存の `TransactionalScope`やapplication serviceへ接続せず、transactionの失敗契約をfakeで固定する。

**なぜ**: transaction状態とイベント収束を一度に入れると、commit失敗の問題と配送順序の問題を
同じ差分で調べることになる。既存UoWへ直接新しい完了処理を接続した場合も、repository参加方法の
差まで同時に変わり、原子性基盤の不具合を用途回帰から切り分けられない。

**どう守るか**:

- `TransactionPort`へイベント収集・配送APIを追加しない
- command本体とcommitの失敗だけがrollbackを開始する
- rollback失敗時は主例外とrollback例外を一つのapplication例外に保持する
- 暗黙の入れ子scopeは`ContextVar`でtransaction開始前に拒否する
- collector、同期dispatcher、commit後handoffは次の積み上げPRで追加する
- 既存UoW adapterと共通永続化試験はその後の積み上げPRで追加する
- 本番traceは最初の縦断移行時にobserver portから追加し、状態機械単体では状態を増やさない

**関連**: #1094 / #1097 / 判断 #147。

## 149. 同期イベントはCommandContextへ戻し、commit後handoffは元scopeの外で開始する

**何を**: `CommandContext`は既存の`DomainEventCollector`を操作単位で所有し、同期dispatcherが
生成した追加イベントも同じ入口へ戻す。`CommandScope`はqueueが空になるまで同期処理した後に
commitし、commit成功後だけ確定済みイベント列を`AfterCommitHandoffPort`へ渡す。

**なぜ**: Unit of Workがイベント処理件数やcommit済みイベントを持つと、永続化方式と配送方式が
再び結合する。一方、handoff中まで元scopeを有効扱いすると、commit後処理が開く正当な独立commandも
暗黙の入れ子として拒否される。

**どう守るか**:

- event idの重複排除は1回のcommand全体で維持する
- 同期dispatcher例外と処理件数上限超過はcommitせずrollbackする
- commit失敗時はhandoffを一度も呼ばない
- commit成功直後に元の`CommandContext`と入れ子ガードを閉じてからhandoffする
- handoff失敗はcommit済みを表す専用例外で観測可能にし、commit済みtransactionをrollbackしない
- この段階のhandoffは差替え点であり、outbox recordの同時永続化は後続PRで追加する

**関連**: #1094 / #1097 / 判断 #147 / 判断 #148。

## 150. 既存Unit of Workの自動rollbackをtransaction専用commitから分離する

**何を**: `InMemoryUnitOfWork`と`SqliteUnitOfWork`へ、同期イベント配送と自動rollbackを行わない
`commit_transaction`を追加する。`CommandScope`用adapterはこの入口だけを使い、commit失敗後の
rollback判断を`CommandScope`へ一元化する。

**なぜ**: 既存`commit`は内部で同期dispatcherとrollbackまで実行する。これをそのまま
`TransactionPort`へ渡すと、rollback失敗が主例外を隠し、`CommandScope`が確定順序を統括できない。
また、snapshot元のないインメモリ実装は保留操作の途中失敗を戻せず、SQLiteと同じ原子性を名乗れない。

**どう守るか**:

- 既存`commit`の互換動作は維持し、内部から`commit_transaction`を呼ぶ
- `commit_transaction`失敗時はtransactionをactiveのまま残す
- begin途中失敗はactive状態と排他を残さず、rollback失敗後のUoW・接続・共有storeは使用不能にする
- SQLiteのcommit成功後にconnection解放だけが失敗した場合は、commit済み後処理失敗としてrollbackしない
- インメモリsnapshotは共有storeの全業務状態を構造的に網羅し、同じstore上の同時transactionを拒否する
- adapterは旧`sync_event_dispatcher`が設定されたUnit of Workを拒否する
- インメモリadapterはrollback用`data_store`がない構成を拒否する
- 旧Unit of Work側に未回収イベントが残る場合は、保留operation実行後も再検査してcommitせず、`CommandContext`への移行を要求する
- インメモリとSQLiteへ同じ複数書込み・rollback・transaction外書込み拒否試験を適用する
- scope専用repositoryの生成とread-your-writesの横断試験は次の積み上げPRで追加する

**関連**: #1094 / #1097 / 判断 #147 / 判断 #148 / 判断 #149。

## 151. scope専用repositoryはtransaction開始後にproviderから一度だけ生成する

**何を**: `CommandScope`はtransaction開始後、用途別の`RepositoryProvider`を一度だけ生成して
`CommandContext`へ結び付ける。SQLite取引commandでは、取引、inventory、status、profile、itemの
書込みrepositoryを同じconnectionの共有UoWモードで生成する。providerと取得済みrepositoryは、
scope終了後の読取り・書込みをともに拒否する。

**なぜ**: constructor注入されたrepositoryと、各所で任意に呼ばれる
`for_shared_unit_of_work(connection)`を併用すると、同じcommand内に独自commit版や別connectionが
混ざってもapplication serviceから判別できない。また書込みだけをscope外で拒否しても、終了後の
repository読取りを許すと閉じた接続や次commandの状態へ静かに依存する。

**どう守るか**:

- provider生成に失敗した場合はcommand本体を開始せずtransactionをrollbackする
- provider factoryへ`CommandScope`が実際に開始した`TransactionPort`を渡し、factory自身には
  別のUnit of Workを保持させない。SQLite用途ではadapterから同一`SqliteUnitOfWork`を取得し、
  異なるtransaction実装との組合せはprovider生成時に拒否する
- providerは接続をapplication serviceへ公開せず、用途に必要なdomain repositoryだけを返す
- repository呼出しのたびにscopeとtransactionの有効性を検査し、取得済みメソッドの後利用も拒否する
- scope内ではsave直後のfindで同じ未commit変更を読めるようにする
- 別connectionにはcommit成功まで変更を見せず、例外終了では複数repositoryの変更をまとめて破棄する
- repositoryが回収した集約イベントは、対応するSQL書込みが成功した後に限って、旧Unit of Workへ
  残さず`CommandContext`へ移す。保存失敗をcommand側が処理しても、未保存集約のイベントを
  同期処理やcommit後handoffへ流さない
- 単独書込み版はfixture、migration、管理用commandの明示的な入口として分離したまま残す
- 最初は取引書込みrepository群だけを縦に通し、用途ごとの移行PRでproviderを追加する

**関連**: #1094 / #1102 / 判断 #147〜#150。

## 152. application commandはscope factoryだけを保持してrepositoryを操作中に取得する

**何を**: `TradeCommandService`を最初の縦断移行対象とし、5つの書込みrepositoryと旧
`UnitOfWork`のconstructor注入を廃止する。serviceは`CommandScopeFactoryPort`だけを保持し、
offer、accept、cancel、declineの各呼出しで新しいscopeを1つ生成して、
`CommandContext.repositories`から取引用途のrepository束を取得する。

**なぜ**: providerが同一transactionのrepositoryを生成できても、application serviceが古い
repositoryをフィールドに保持したままでは、操作中にscope外のrepositoryを混ぜられる。逆に
`CommandScope`自体をserviceへ使い回し注入すると、一方向状態機械の終了済みscopeを次commandで
再利用してしまう。commandごとのfactoryを唯一の入口にすれば、transactionとrepositoryの寿命を
同時に揃えられる。

**どう守るか**:

- `CommandScopeFactory`は呼出しごとに新しい`TransactionPort`とNEW状態のscopeを生成する
- 取引serviceは旧`UnitOfWork`と個別repositoryを属性に持たない
- インメモリproviderは永続化操作を元UoWへ委譲し、集約イベントだけを`CommandContext`へ移す
- SQLite providerは前判断どおり、scopeが開始した同じUoWのconnectionだけを使う
- インメモリとSQLiteへ同じ取引コマンド試験を適用し、正常結果と用途固有例外を維持する
- 同期処理失敗は取引・採番・予約をrollbackし、commit後handoff失敗は
  `CommandPostCommitException`のまま上位へ伝えて再実行可能な業務失敗と区別する
- 現時点で本番composition rootに存在しない取引command配線は新設せず、契約と両永続化実装の
  縦断試験までをこの移行単位とする

**関連**: #1094 / #1105 / 判断 #148〜#151。

## 153. CommandScopeのイベント処理はcommit前必須処理とcommit後配送の二相に限定する

**何を**: 新しいcommand確定境界では、従来の`is_synchronous: bool`や用途別に増えた5相を使わず、
handlerを`register_required_before_commit`または`register_after_commit`のどちらかへ登録する。
commit後配送は実行時期とは別に、用途を`DeliveryChannel`、必要な保証を`DeliveryGuarantee`で表す。

**なぜ**: transaction内で実行する正当な理由は、その処理の失敗時にcommand全体を戻す必要があること
だけである。失敗してもcommandを続ける補助処理や観測をcommit前に置くと、未確定状態の外部露出、
rollback後の偽の成功観測、handler順序への依存を招く。過去の同期観測がcommit前の集約状態を必要と
する場合は、その事実をdomain eventへ載せてcommit後に処理できる契約へ直すべきであり、専用の
transaction相を恒久化しない。一方、commit後処理の「何のためか」と「失敗時に再試行するか」は
独立した判断なので、相の名前へ混ぜず二つの軸で表す。

**どう守るか**:

- commit前には、失敗を伝播して`CommandScope`にrollbackさせる必須handlerだけを実行する
- 観測、read model、別コンテキスト連携、補助処理は、確定状態へ追随するcommit後配送に置く
- `DeliveryChannel`は`OBSERVATION`、`READ_MODEL`、`INTEGRATION`、`AUXILIARY`を区別する
- `DeliveryGuarantee.DURABLE_RETRY`の失敗は`CommandPostCommitException`として業務失敗と区別する。
  現段階では再試行可能な失敗として顕在化し、永続化と自動再送は後続outbox PRで完成させる
- `DeliveryGuarantee.BEST_EFFORT`の失敗はwarningと失敗observerへ残し、後続配送を続ける
- 同じイベント・同じ側のhandlerは登録順で実行する
- 既存`EventPublisher`入口は段階移行中の互換面として残し、新しい`CommandScope`配線からは使用しない
- 取引read model更新を最初の`READ_MODEL + DURABLE_RETRY`登録とし、旧publisher向けの非同期指定は
  移行完了まで互換面として維持する

**関連**: #1094 / #1107 / 判断 #147〜#152。

## 154. scope参加repositoryの集約イベントはCommandContextだけへ移す

**何を**: `CommandScope`へ移行した取引commandでは、インメモリとSQLiteのrepositoryが保存後に
回収する集約イベントを、共通の`CommandContextAggregateEventSink`から`CommandContext`へ移す。
旧`UnitOfWork`のpending event列は永続化操作の都合で残っていても、この経路のイベント正本には
使わない。

**なぜ**: 永続化方式ごとにイベント回収を実装すると、片方だけclear時期、重複排除、終了後利用の
扱いが変わり得る。またインメモリproviderが`__getattr__`で旧`UnitOfWork`を全面透過すると、
repository変更時に`add_events`へ逆流しても構造的に止められない。outboxへ保存する前に、1 commandの
確定イベント列を一つへ固定する必要がある。

**どう守るか**:

- 共通sinkはscopeとtransactionが有効な間だけ収集を許可する
- 全イベントを`CommandContext`へ渡せた後だけaggregateのevent queueを空にする
- 同じ`event_id`の重複排除と宣言順維持は`CommandContext`を正本にする
- SQLite repositoryはSQL成功後にだけ共通sinkを呼び、保存失敗時の幽霊イベントを作らない
- インメモリ用facadeは永続化に必要なUoW操作だけを明示委譲し、`__getattr__`や`add_events`を公開しない
- 両永続化方式で旧UoWのpending event列が空のまま、同期処理とcommit後handoffへ一度だけ届くことを
  試験する
- 今回は取引commandだけを縦に通し、他用途は対応する`CommandScope`移行PRで同じsinkへ接続する

**関連**: #1094 / #1112 / 判断 #149〜#153。

## 155. 再送必須イベントは業務状態と同じtransactionでoutboxへ保存する

**何を**: `CommandScope`は同期必須handlerが収束した後、commit後登録のうち
`DeliveryGuarantee.DURABLE_RETRY`を持つイベントをtransactional outboxへ登録してから
業務状態をcommitする。SQLiteでは`command_event_outbox`をgame write schemaに置き、取引イベント
4種をschema version付きJSONとして保存する。

**なぜ**: commit後handoffの失敗を専用例外で区別できても、再試行元がプロセス内のイベント参照
だけでは再起動時に失われる。一方、業務状態のcommit後にoutbox行を別保存すると、その間の停止で
「取引は確定したが配送予定がない」状態になる。同期処理収束後、同じtransactionへ先に登録すれば、
業務状態と配送予定を同時にcommitまたはrollbackできる。

**どう守るか**:

- outbox対象はイベント型の固定表ではなく、`CommandEventDispatcher`の登録済み配送保証から導出する
- `BEST_EFFORT`だけのイベントはoutboxへ保存しない
- 現段階では既存のcommit後即時handoffを維持し、成功後だけ対応行を`delivered`へ更新する
- handoff失敗時は業務状態を戻さずoutbox行を`pending`のまま残し、`CommandPostCommitException`を返す
- 配達済み記録の失敗はhandoff失敗と混同せず、同例外の`outbox_error`へ保持する
- outboxの単位はevent idとし、同じevent idを重複保存しない。再配送は少なくとも一回になり得るため、
  durable handlerはevent idに対して冪等であることを前提にする
- payloadは対象bounded contextの明示codecで型付き値へ復元し、未知version・不正JSON・暗黙型変換を
  読込み時に拒否する
- v32以前の取引日時はタイムゾーンを保持していないため、migrationで壁時計値を変えず
  UTC付きへ正規化する。解釈できない日時は推測せずmigrationを失敗させる
- 今回は取引commandの縦断経路までとし、未配送行を取得するworker、試行回数、間隔、dead letterは
  次のPRで追加する

**関連**: #1094 / #1114 / 判断 #153 / 判断 #154。

## 156. outbox workerは登録順に1件ずつ再配送する

**何を**: `OutboxWorker.run_once` は`pending`行を単調増加の`outbox_id`順で
一定件数取得し、明示codec registryで型付きイベントへ復元して
`DURABLE_RETRY` handlerだけへ渡す。handler成功後にその1行を`delivered`へ更新する。

**なぜ**: 複数行をまとめて配達済みにすると、中間のhandler失敗で成功済み行まで再送される範囲が
不必要に広がる。一方、一時失敗後も後続行を先に配送すると、同じ投影先の古いイベントが
後から適用され得る。1件ずつ確定し、一時失敗でその実行を停止することで順序を保つ。

**どう守るか**:

- event typeはDB値から動的importせず、起動時に登録した型とcodecだけを許可する
- 対象となる`DURABLE_RETRY` handlerが0件なら成功扱いにせず、`pending`を維持して構成漏れを顕在化する
- 未知event type・未対応schema・不正payloadは`rejected`へ隔離し、同じ入力を無限再試行しない
- handler例外は一時失敗として`pending`を維持し、試行回数・時刻・理由を残して後続配送を停める
- handler成功後・配達済み更新前に停止する可能性は残るため、配送保証は少なくとも1回であり、
  handlerはevent idに対して冪等である必要がある
- 今回は単一workerの`run_once`を契約とし、複数worker間のlease、指数backoff、最大試行回数、
  rejected行の再投入運用は後続PRに分ける

**関連**: #1094 / #1114 / #1118 / 判断 #155。

## 157. read model投影はconsumer inboxと同じtransactionで確定する

**何を**: 取引read modelのdurable handlerは、安定した`consumer_id`と`event_id`の組を
`event_consumer_inbox`へ記録し、その行の新規取得に成功した場合だけ投影を実行する。
SQLiteではinbox行とread model更新を同じtransactionで確定し、インメモリでも失敗時に
read modelを投影前へ戻す。

**なぜ**: outbox workerの配送は少なくとも1回であり、handler成功後・outboxの配達済み更新前に
停止すると同じeventが再配送される。read modelだけを再更新すると、将来の加算投影や通知投影で
二重反映が起きる。一方、投影後に別transactionで処理済みを記録すると、その間の停止を防げない。

**どう守るか**:

- 一意性は`(consumer_id, event_id)`で持ち、同じeventを別consumerが処理することは許す
- `consumer_id`はhandler実装ごとの版付き固定値とし、名前変更で意図せず再投影しない
- handlerはrepositoryやtransactionを保持せず、`TradeProjectionExecutorPort`へ投影関数を渡す
- SQLite executorが毎回新しいtransactionと、そのconnectionに参加するrepositoryを組み立てる
- 投影失敗時はinbox行もread model更新も残さず、同じeventを再試行可能にする
- 成功ログはexecutorが正常終了し、commitが完了した後だけ出す
- 遅延した`Offered`は既存モデルを上書きせず、終端状態から`ACTIVE`へ巻き戻さない
- read model不在のcancel/declineは前提投影不足としてrollbackし、後続の再配送で自己修復可能にする
- 外部API呼出しなどtransactionで戻せない副作用はprojection内へ追加しない

**関連**: #1094 / #1118 / #1120 / 判断 #155 / 判断 #156。

## 158. outbox再配送はprocessの生存期間に属する有界loopで駆動する

**何を**: `GAME_DB_PATH`を持つFastAPI processは起動時に取引outbox workerを組み立て、
起動直後と一定間隔ごとに最大件数を制限して再配送する。同期SQLite処理はasyncioのevent loopから
executorへ逃がし、1回の配送失敗はwarningへ残して次の周期で再試行する。

**なぜ**: `OutboxWorker.run_once`を手動でしか呼べない状態では、再起動後に残った`pending`行が
永続化されていても自動回復しない。一方、1回の失敗をサーバ停止へ波及させると、一時的な投影障害が
ゲーム全体の可用性を奪う。processの起動・停止と同じ境界で単一loopを所有すれば、通常の即時配送を
維持しながら未配送分だけを継続的に回復できる。

**どう守るか**:

- 1回の実行は`batch_limit`件までとし、空になるまで占有し続けない
- 同一loop内では前回の`run_once`終了後にだけ次を始め、重複実行しない
- start/stopは冪等とし、shutdown時は実行中の1回に終了猶予を与える
- `GAME_DB_PATH`未設定のインメモリ構成ではloopを作らない
- 配送失敗は握り潰さずwarningに例外情報を残すが、次回再試行とゲームserverは止めない
- 現段階の排他は1process内だけである。複数process・複数hostで動かす前に、outbox行を
  原子的にclaimするowner・lease期限をSQLite store契約へ追加する
- 指数backoff、最大試行回数、dead letter運用は配送頻度と障害方針を決める別PRへ分ける

**関連**: #1094 / #1118 / #1120 / #1124 / 判断 #155 / 判断 #156 / 判断 #157。

## 159. outbox一時失敗は順序を保ったまま間隔を広げ、上限で隔離する

**何を**: 一時失敗した`pending`行は、失敗回数に応じて1秒から最大5分まで
指数的に次回試行を遅らせる。既定で12回失敗した行は`dead_letter`へ隔離し、
後続イベントの配送を再開する。試行回数、次回試行時刻、最終理由、隔離時刻は
SQLiteへ保存する。

**なぜ**: handlerや投影DBの障害中に毎秒同じ行を再配送すると、復旧を促すどころか
DB・外部依存・ログへ追加負荷をかける。また、回復不能な一時失敗が先頭に残り続けると、
登録順を守るために全後続イベントが永久に止まる。待機で負荷を抑え、有限回で隔離すれば、
失敗したpayloadと理由を失わずに通常配送を回復できる。

**どう守るか**:

- 待機中の最古`pending`行がある場合は、期限到来済みの後続行も取得しない
- 待機時間は永続化し、process再起動で即時再試行へ戻さない
- 最大試行回数に達した場合だけ`dead_letter`とし、同じworker実行で後続へ進む
- 復元不能なpayloadを表す`rejected`と、配送試行を使い切った`dead_letter`を区別する
- 隔離件数は定期loopの完了ログに残し、最終理由と時刻はDBから調査できるようにする
- 手動再投入と管理画面、複数process間のclaim/leaseは別の運用PRで追加する

**関連**: #1094 / #1126 / 判断 #156 / 判断 #158。

## 160. 更新commandの横展開は実利用される複数集約操作を一つずつ移す

**何を**: 取引で確立した `CommandScope` を他用途へ広げる最初の対象は、
`SpotGraphItemTransferService.give_item` とする。送り手・受け手の所持品、品目、
プレイヤー状態、位置をcommand専用providerから取得し、2つの所持品保存を同じ
transactionで確定する。`PlayerGaveItemEvent` は同じscopeへ収集し、commit成功後だけ
観測パイプラインへ最善努力で渡す。

**なぜ**: `give_item` は実際のLLMツール経路で使われ、送り手保存後に受け手保存が失敗すると
アイテムが片側だけから消える。影響が現実的でありながら、書込み対象は共有
`InMemoryDataStore`または同じSQLite接続上の2つのinventoryに限定できる。一方、
`drop_item`と`pickup_item`は`SpotInterior`と`SpotGraph`のインメモリ永続化境界も同時に
設計し直す必要があるため、同じPRへ混ぜない。

**どう守るか**:

- command内の書込みrepositoryは開始済みtransactionから生成し、長寿命repositoryを使わない
- SQLite providerは全repositoryで同じ接続を共有し、独自commitを無効にする
- インメモリproviderは共有storeのsnapshot transactionへ両inventoryを参加させる
- 受け手側保存が失敗した場合は、先に行った送り手側更新もrollbackする
- 成功観測はcommit前に配信せず、rollback時には一件も配信しない
- scope終了後のrepository再利用を拒否する
- 観測は `OBSERVATION + BEST_EFFORT` とし、read model用outboxへ保存しない
- 公開`give_item`は`CommandScopeFactory`を必須とし、未配線ならrepository参照前に拒否する
- 長寿命のinventory・item・status repositoryと直接publisherはserviceに保持しない
- 次段階で`drop_item` / `pickup_item`のインメモリ永続化資源をscope参加可能にして移行する

**関連**: #1094 / #1131 / 判断 #147 / 判断 #151〜#159。

## 161. drop/pickupは所持品とSpotInteriorを同じtransactionで確定する

**何を**: `SpotGraphItemTransferService.drop_item`と`pickup_item`を、`give_item`と同じ
`CommandScope`へ移す。更新対象の`PlayerInventory`と`SpotInterior`はcommand専用providerから取得し、
どちらか一方の保存に失敗した場合は両方をrollbackする。`SpotGraph`はプレイヤー位置と`graph_id`の
参照にしか使わないため、providerでは読み取り専用契約として公開する。

**なぜ**: dropで所持品だけが消えて地面へ置かれない場合はアイテムが消失し、pickupで地面だけから
消えて所持品へ入らない場合も同じく消失する。逆順の部分確定や再試行は複製にもつながる。
`give_item`で確立したcommand境界を使えば、所持品と地面を同じ成功・失敗単位にできる。一方、
`SpotGraph`まで書込み可能なrepositoryとして公開すると、将来の変更が意図せずこのtransactionへ
混入するため、現在必要な読み取り能力だけに狭める。

**どう守るか**:

- インメモリの`SpotInterior`を共有`InMemoryDataStore`のsnapshot対象へ移す
- SQLiteの`SpotInterior`は開始済みUoWと同じconnectionから生成し、独自commitを無効にする
- drop/pickupはscope内のrepository集合だけを使い、長寿命repositoryへ書き込まない
- 公開drop/pickupは`CommandScopeFactory`未配線時にrepository参照前で拒否する
- `PlayerDroppedItemEvent`と`PlayerPickedUpItemEvent`はscopeへ収集し、commit後だけ観測として配送する
- 地面保存の失敗時に、先行したinventory変更・地面変更・成功観測がすべて残らないことを
  インメモリとSQLiteの両方で試験する
- `SpotGraph`は`find_graph`だけを持つ読み取り専用portとしてproviderから公開する
- 経路探索や地面一覧取得などのqueryは従来どおりtransaction外で実行する

**関連**: #1094 / #1133 / 判断 #160。

## 162. repository外の世界内可変状態も同じcommandのrollbackへ参加させる

**何を**: interactionのようにrepositoryと世界内の可変storeを同時更新するcommandでは、
repository外の資源を `RollbackParticipantPort` として基底transactionへ合成する。
参加資源はsnapshot前からcommand完了まで資源単位の所有権を保持し、基底transactionまたは
commandが失敗した場合は登録と逆順で開始前へ戻す。

**なぜ**: `SpotInteractionApplicationService` はinventoryや`SpotInterior`だけでなく、
world flag、spot graph、待ち時間、退場者位置なども直接変更する。repositoryだけを
`CommandScope`へ移すと、永続化はrollbackしたのに外側の状態だけが残る新しい部分反映を作る。
一方、tick全体を一つのtransactionに広げると排他時間と巻戻し範囲が大きすぎるため、
一つの業務commandが実際に変更する資源だけを明示的に参加させる。

**どう守るか**:

- 参加資源は資源同一性の固定順で占有し、snapshotからcommit/rollback完了まで別commandを待たせる
- 参加資源を占有してから基底transactionを開始し、全commandで同じ取得順を守る
- 合成transactionの多段化は認めず、一つのadapterが全参加資源の重複検査と取得順を所有する
- 同じ実資源を複数adapter経由で二重登録しない
- command失敗とcommit失敗では、基底transactionの後に参加資源を逆順で復元する
- 基底transactionのbegin途中失敗では、まだsnapshotを取っていない参加資源へ触れない
- durable commit後のcleanup失敗では、確定した参加資源を復元しない
- repository providerとoutboxは合成transactionを共通入口で剥がし、実際に開始した基底資源へ参加する
- 一つの資源の復元失敗後も残りを試し、失敗した資源を使用不能にする
- transaction rollback失敗と全参加資源の復元失敗を同じ例外から診断できるよう保持する
- この基盤だけではinteractionを移行済みとせず、具体資源adapterと用途別差分試験を後続PRで追加する

**関連**: #1094 / #1137 / 判断 #147〜#161。

## 163. interactionの外部状態と通知を同じ確定境界へ参加させる

**何を**: 通常の物体interactionが直接変更する `MutableWorldFlagState`、
`InteractionCooldownStore`、`DepartedPositionStore`、インメモリspot graphを、
一組のrollback参加資源として構築する。各資源はcommand開始時のdeep snapshotを持ち、
失敗時は状態と集約event queueを含めて開始前へ戻す。

world flagの変更通知は状態変更時に即時配信せず、参加資源がcommand中だけ保留する。
commit後は元の順序で通知し、rollback後は捨てる。これにより、状態が戻ったのに
`WORLD_FLAG_CHANGED` traceだけが残る偽の成功観測を作らない。

**なぜ**: repositoryのrollbackだけでは、graph上の移動・接続、世界flag、待ち時間、
退場者位置が部分的に残る。さらにworld flag callbackはtraceへ直結しているため、状態だけ
snapshotへ戻しても観測上の嘘が残る。更新と観測を同じ確定境界へ揃える必要がある。

**どう守るか**:

- 4資源を一つのbuilderから固定して組み立て、同じparticipant群を全commandで再利用する
- rollbackではflag・actor/world待ち時間・退場者位置・graph本体とevent queueを復元する
- flag callbackはtransaction内で呼ばず、基底commit後だけ宣言順に渡す
- callbackを含む復元・解放失敗では参加資源をpoisonし、後続commandで再利用しない
- `CALL_MEETING`は別command呼出しなのでsnapshot資源へ偽装せず、後続の用途配線で扱う
- このPRではinteraction本体をまだ接続せず、次のPRでrepository providerとイベント収集を移す

**関連**: #1094 / #1137 / 判断 #162。

## 164. 通常の物体interactionはrepositoryと外部状態を一つのcommandで確定する

**何を**: `CALL_MEETING` を含まない通常の物体interactionは、操作ごとに新しい
`CommandScope`を開く。spot graph、`SpotInterior`、player inventory、player status、
item、item specのrepositoryは、scopeが開始した同じUnit of Workから生成する。
world flag、待ち時間、退場者位置、インメモリspot graphは判断#163のrollback参加資源として
同じcommandへ加える。

成功eventは操作中に外へ配信せず`CommandContext`へ集め、全状態のcommit後だけ既存の
観測pipelineへ渡す。前提条件による拒否は成功eventではないため、rollback完了後に確定状態を
読み直して失敗観測を一度だけ発行する。

**なぜ**: 従来の物体interactionは複数repositoryとrepository外の世界状態を順番に保存し、
途中失敗時に一部だけ残り得た。さらに成功eventがcommitより先に配信されると、同期処理や
永続化が失敗してrollbackした操作を観測者だけが成功として記憶する。更新対象と成功観測を
同じ確定境界へ揃える必要がある。

`CALL_MEETING`は会議開始という別commandを呼び出すため、この段階では既存経路へ残す。
外側interactionのtransaction中に内側commandを始める形へ押し込まず、会議開始を独立した
commandとして分離してから移行する。

**どう守るか**:

- providerは実際に開始した基底transactionからだけ生成し、別Unit of Workの誤配線を許さない
- scope終了後のrepository再利用を拒否する
- repository保存失敗とcommit前必須処理失敗では、repositoryと4つの参加資源を開始前へ戻す
- world flag callbackと成功eventはcommit後だけ外へ出し、rollback時は破棄する
- 前提条件失敗の観測はrollback後の確定状態から作り、成功eventと混ぜない
- インメモリとSQLiteのproviderは同じ用途portを実装し、SQLite writerの独自commitを無効にする
- `CALL_MEETING`を含む操作はscopeへ入れず、後続PRで会議command境界を明示してから移行する

**関連**: #1094 / #1137 / 判断 #151 / 判断 #153 / 判断 #162 / 判断 #163。

## 165. 道具に宣言したinteractionも物体操作と同じcommandで確定する

**何を**: `CALL_MEETING`を含まない道具interactionは、通常の物体interactionと同じ
`CommandScope`、repository provider、rollback参加資源を使う。所持道具の解決、遠隔物体を
含む`SpotInterior`、inventory、item、player status、spot graph、world flag、待ち時間、
退場者位置を一つのcommandとして確定し、成功eventはcommit後だけ既存pipelineへ渡す。

**なぜ**: 制御端末のような道具操作は、手元のitemだけでなく別室の物体状態や全室の照明、
接続、所持品、player状態を同時に変えられる。従来の長寿命repositoryを順番に保存する経路では、
遠隔物体を保存した後のgraph保存失敗などで一部だけが残り、観測だけが成功する可能性もあった。
通常の物体操作用に確立した境界を再利用し、同じ失敗規則に揃える。

**どう守るか**:

- command内の全repositoryは、scopeが開始した同じUnit of Workから取得する
- world flag、待ち時間、退場者位置、インメモリspot graphは同じrollback参加資源を再利用する
- 遠隔`SpotInterior`を保存した後のgraph保存失敗でも、物体状態と待ち時間を開始前へ戻す
- commit前必須処理の失敗ではgraph変更・待ち時間・成功eventを残さない
- commit後handlerが読む時点では、repositoryと外部状態の両方が確定済みである
- `CALL_MEETING`は別commandを起動するため既存経路に残し、入れ子transactionへ押し込まない

**関連**: #1094 / #1137 / 判断 #162〜#164。

## 166. 対人interactionは二者の状態と観測を一つのcommandで確定する

**何を**: `CALL_MEETING`を含まない対人interactionは、通常の物体・道具interactionと
同じ`CommandScope`、repository provider、rollback参加資源を使う。使う側と使われる側の
inventory・player status、item、spot graph、world flag、待ち時間を一つのcommandとして
確定し、`PlayerDownedEvent`と成功観測はcommit後だけ既存pipelineへ渡す。

**なぜ**: 対人操作は、使われる側から品物を削除した後に使う側への保存が失敗するなど、
二つの集約を跨いだ途中失敗が起きる。従来の長寿命repositoryを順番に保存する経路では、
品物が消失・複製したり、rollbackした攻撃を観測者だけが成功として記憶したりする可能性が
あった。二者の更新と成功観測を同じ確定境界へ揃える必要がある。

**どう守るか**:

- command内の全repositoryはscopeが開始した同じUnit of Workから取得する
- 更新対象となるplayer statusはscope内から読み、二者の保存を同じtransactionへ参加させる
- 身体として扱うかは既存の`PlayerLifeQuery`へ集約し、用途ごとの生死規則を増やさない
- 対象inventory保存後に使う側inventory保存が失敗しても、両方を開始前へ戻す
- commit前必須処理が失敗した場合は、HP・昏倒・待ち時間・成功eventを残さない
- `PlayerDownedEvent`と`PlayerInteractedWithPlayerEvent`はcommit後だけ配送する
- world flag、待ち時間、退場者位置、インメモリspot graphは既存のrollback参加資源を再利用する
- `CALL_MEETING`は別commandを起動するため既存経路に残し、入れ子transactionへ押し込まない

**関連**: #1094 / #1137 / 判断 #162〜#165。

## 167. 会議開始は通常interactionから独立したcommandとして扱う

**何を**: `CALL_MEETING`は一つの`InteractionDef`で唯一の効果としてだけ許可する。
loaderと`InteractionDef`の両方で、通常効果との混在を構築時に拒否する。緊急招集と
遺体報告の処理は`MeetingCommandService`へ移し、`WorldRuntime`の公開入口は同serviceへ
委譲する。会議中の投票進行とフェーズ遷移の正本は、今回も`WorldRuntime`に残す。

**なぜ**: `CALL_MEETING`は物体状態の変更の一種ではない。招集回数の消費、全playerの
移動終了と集合、遺体記録、ゲームフェーズ遷移を伴う別のcommandである。通常interactionの
効果列へ混ぜると、外側のtransaction中に内側の会議commandを開始する入れ子構造になり、
どこまでを一緒にrollbackするかが曖昧になる。悪い過去挙動を互換性として残さず、宣言時点で
一つのcommandへ分ける。

**どう守るか**:

- loaderは`CALL_MEETING`と別効果を含むシナリオをpath付き`ScenarioLoadError`で拒否する
- 直接構築も`InteractionEffectValidationException`で拒否し、loader迂回の抜け道を残さない
- `WorldRuntime.call_emergency_meeting`と`report_body`は専用serviceへの薄い委譲にする
- 既存の戻り値、エラーコード、集合、遺体記録、フェーズ遷移の順序は変更しない
- この段階では`begin_meeting`をruntime callbackとして渡し、次段階で会議command全体を
  `CommandScope`へ接続する

**関連**: #1094 / #1137 / 判断 #162〜#166。

## 168. 会議開始の状態と観測を一つのcommandで確定する

**何を**: 緊急招集と死体報告は専用`CommandScope`を開き、`GamePhaseStore`、
spot graph、player statusを一つのcommandとして確定する。会議開始の
`GamePhaseChangedEvent`は操作中に直接配信せず`CommandContext`へ集め、commit後だけ
既存の観測pipelineへ渡す。

**なぜ**: 会議開始は、緊急ボタン消費または死体の報告済み記録、全生存者の集合、
移動状態の終了、フェーズ遷移を順に変更する。途中のstatus保存や必須イベント処理が失敗した
とき、一部だけ残ると「会議は始まらないのに持ち札だけ失う」「graphでは集合済みなのに
古い移動経路が再開する」「自由時間のまま会議開始観測だけ届く」という矛盾になる。

**どう守るか**:

- graphとplayer statusはscopeが開始した同じUnit of Work由来のproviderからだけ取得する
- `GamePhaseStore`は現在フェーズ、履歴、使用済みボタン、報告済み身体、投票をまとめて復元する
- spot graphはrollback参加資源とし、status保存失敗では全playerの位置も開始前へ戻す
- 集合中のrepository保存失敗は警告へ潰さずcommand全体を失敗させる
- 会議開始eventはcommit前必須処理を通し、成功時だけ確定後配送する
- trace記録はscope正常終了後に行い、失敗しても確定済み会議を業務失敗として返さない
- `CALL_MEETING`は前提条件の評価後に専用scopeだけで完結し、会議確定後に外側interactionの
  保存・成功観測・待ち時間処理を続けない
- ボタン操作の成功観測は`GamePhaseChangedEvent`へ一本化し、入れ子transactionと二重確定を避ける

会議終了と投票は別commandであり、この判断では開始二入口だけを移行する。

**関連**: #1094 / #1137 / 判断 #162〜#167。

## 169. 投票・追放・会議終了を一つのcommandで確定する

**何を**: 一票の記録と進捗通知を`MeetingCommandService`の`CommandScope`へ移す。
最後の一票または時間切れでは、票の集計、追放outcome、spot graphからの退場、
倒れた身体の消去、自由時間への遷移までを同じcommandとして確定する。
`MeetingVoteCastEvent`、`MeetingVoteResolvedEvent`、`GamePhaseChangedEvent`は
`CommandContext`へ集め、commit後だけ既存の観測pipelineへ渡す。

**なぜ**: 従来は票を先に記録し、進捗を即時配信した後で追放と会議終了を順に実行していた。
graph保存や同期処理が失敗すると「最後の票だけ残る」「追放outcomeだけ確定する」
「会議中なのに終了観測だけ届く」という部分適用が起こり得た。さらにoutcome callbackは
即時発火するため、状態だけをsnapshot復元してもrollbackした追放観測が外へ漏れる。

**どう守るか**:

- `GamePhaseStore`は票・フェーズ・報告済み身体をまとめて開始前へ戻す
- `PlayerOutcomeRegistry`はoutcomeを参加資源にし、command中はcallbackを発火させない
- 追放callbackは`MeetingVoteResolvedEvent`の確定後handlerから通知し、
  最後の投票 → 集計 → 追放outcome → 会議終了の観測順を守る
- spot graph保存失敗を警告へ潰さず、追放を含むcommand全体をrollbackする
- `FallenBodyRegistry`を参加資源にし、会議終了処理の失敗で身体を消さない
- 最後の一票では進捗、集計結果、フェーズ遷移を宣言順に集め、確定後だけ配送する
- 沈黙・tick上限でも現在票を同じ経路で集計し、手動終了は集計せず終了だけを確定する
- 会議時間の累積と終了traceはscope正常終了後に更新し、trace失敗をcommand失敗へ変えない

**関連**: #1094 / #1241 / 判断 #168。

## 170. SpotGraph移動は1 player・1操作ごとに確定する

**何を**: 移動開始、1 world tick分の進行、同一spot内のsub-location変更、
移動中断・復元をそれぞれ`CommandScope`で囲む。`PlayerStatus`は同じ
Unit of Work由来のrepositoryから保存し、spot graphと退場者位置はrollback参加資源とする。
これら5つの公開更新入口は`CommandScopeFactory`未配線時にrepositoryへ触れる前に拒否し、
規則試験もrepositoryを明示した試験用scopeを通す。

**なぜ**: `travel_ticks=0`の区間が連続すると1 tickで複数の接続を渡る。
従来は渡るたびにgraphまたは退場者位置を書き換え、最後にnavigation stateを
保存していた。2区間目の通行判定やstatus保存が失敗すると、位置だけ進み
移動予約が古いままという矛盾が残る。

**どう守るか**:

- 複数crossingはすべての通行条件再検査と状態更新が通ったときだけ一括確定する
- graphが生成した移動eventは`CommandContext`へ移し、commit後だけ宣言順に配送する
- 到着callbackは各playerの移動command終了直後に呼び、後続playerの失敗で失わない
- spot遭遇記録は確定後の`EntityEnteredSpotEvent`だけから行い、callbackと二重計上しない
- ダウン・追放時の予約破棄と、別toolによる中断も同じ移動serviceのcommandを使う
- 公開更新入口から長寿命repositoryへ直接保存する退避経路を残さない
- world tick全体は一つのtransactionにせず、playerごとの移動を独立に確定する
- passageの`consume_item`は副作用設計が別に必要なため、この移行では実装しない

**関連**: #1094 / #1242 / 判断 #168〜#169。

## 171. world tickは順序だけを所有し、確定はstageまたはcommandへ分ける

**何を**: `SpotGraphSimulationApplicationService`からtick全体を囲む旧`UnitOfWork`を
外す。世界時刻を一度進めた後、stageを宣言順に呼ぶcoordinatorとし、更新の確定と
event収集は各stageまたはその内側のcommandが所有する。最初の代表移行として
`StatusEffectsTickStageService`を一つの`CommandScope`へ移す。

**なぜ**: 本番で渡していた旧`InMemoryUnitOfWork`は共有data storeを持たず、stageが
直接変更するrepositoryやstoreをrollbackできなかった。一方、移動は既にplayerごとの
独立commandとして内側でcommitする。外側にtick全体のtransactionがあるように見せると、
実際には戻らない状態を戻るものと誤認させ、独立commit済みの前段まで同じtickで再実行する
危険がある。

**どう守るか**:

- tick開始時に時刻を一度進め、後段失敗でも戻さず同じtickを自動再試行しない
- 失敗時も`WorldRuntime`のtickミラーを時刻源へ同期し、残り時間と終了判定を分裂させない
- 完了済みの前段は残し、失敗commandだけが自分の状態と成功eventをrollbackする
- 累積移動tickはplayerごとの移動command確定直後に記録し、後段失敗でも失わない
- stage失敗では依存する後段とpost-tick hookを実行せず、呼出し側へ例外を返す
- `StatusEffectsTickStageService`は全player statusを一括保存し、保存失敗では全員分を戻す
- `PlayerDownedEvent`等は`CommandContext`へ集め、player status確定後だけ配送する
- 公開stageは`CommandScopeFactory`を必須とし、長寿命repositoryと直接publisherへ戻る
  旧経路を残さない
- 未移行stageは `docs/refactor_plans/world_tick_commit_boundaries.md` の表で危険と移行単位を明示する
- tick全体を一つのSQLite transactionにする変更は行わない

**関連**: #1094 / #1243 / 判断 #147〜#170。

## 172. needs decayはplayer status確定後にevidenceへ転記する

**何を**: `SpotGraphNeedsDecayStageService`を、状態異常stageと共有する
player status用`CommandScope`へ移す。全playerの空腹・疲労・飢餓ダメージを一括保存し、
`PlayerDownedEvent`等は確定後だけ配送する。空腹限界のevidenceはscope正常終了後に転記する。

**なぜ**: 従来は空腹限界evidenceをplayer status保存より先に書いていた。後続の一括保存が
失敗すると、実際の空腹はrollbackされたのに記憶だけ「空腹が限界に達した」と残り得た。
また旧publisherへの直接配送は、保存と成功観測の確定境界をコード上で保証できなかった。

**どう守るか**:

- 空腹・疲労・飢餓ダメージは全player分を一つのplayer status transactionで保存する
- 一括保存失敗では全playerのneeds・HP・集約eventを開始前へ戻す
- 集約eventは`CommandContext`へ集め、player status確定後だけ既存pipelineへ渡す
- evidence転記はscope正常終了後に行い、rollback時には呼ばない
- commit後cleanup失敗ではstatusは確定済みなのでevidenceを追随させてから元例外を返す
- evidence転記自体の失敗は従来どおり警告に留め、確定済みplayer statusを戻さない
- 公開stageは`CommandScopeFactory`を必須とし、長寿命repositoryと直接publisherへ戻る
  旧経路を残さない。更新規則の単体試験はrepositoryを明示してprivate helperを検証する

**関連**: #1094 / #1243 / 判断 #171。

## 173. scenario eventはevent定義1件ごとに世界状態と進捗を確定する

**何を**: `SpotGraphScenarioEventStageService`の発火単位を、一つの
`ScenarioEventDef`を処理する`CommandScope`へ移す。flag、interior、graph、item、
inventoryと、once・chainのprogressを同じ確定境界へ入れる。graphの集約eventは
`CommandContext`へ収集し、message callbackはscope終了後に呼ぶ。

**なぜ**: 従来はflag、interior、graph、inventoryを順に直接保存した後でonce記録と
chain予約を更新していた。後段のitem付与や進捗更新が失敗すると、世界の一部だけが
変わったままeventは未発火扱いとなり、次tickで同じ効果を再適用する危険があった。
messageも保存途中で呼ばれ得る構造では、rollback済みの出来事を観測として残してしまう。

**どう守るか**:

- 条件評価は現在の確定状態をscope外で行い、成立したeventだけcommandを開始する
- eventの効果、once記録、chain予約・解除を一つのscope内で更新する
- 途中失敗ではflag、interior、graph、item、inventory、progressを開始前へ戻す
- 同じtickの複数eventは別commandとし、先行eventの確定結果を後続失敗で戻さない
- graphの集約eventは確定後だけ既存pipelineへ宣言順に配送する
- message callbackはcommit後の最善努力とし、失敗しても確定済み世界を戻さない
- commit後cleanup失敗でもmessageを確定状態へ追随させてから元例外を返す
- item overflowはscope内repositoryとevent収集口へ束縛し、地面だけの部分確定を防ぐ
- event定義がある公開stageは`CommandScopeFactory`を必須とし、未配線なら進捗・graph・
  条件評価へ触れる前に拒否する。直接repositoryを更新する旧経路は残さない

**関連**: #1094 / #1243 / 判断 #171〜#172。
## 174. 主観エピソードに経験の主体 BeingId を載せる

**何を**: `SubjectiveEpisode` に必須フィールド `being_id: BeingId` を追加する。
`player_id` は手番の身体として残す。store の一次キーと VO の `being_id` が
食い違う書き込みは `put_by_being` で失敗する。

**なぜ**: store は既に Being 単位のキーなのに、葉の記録は `player_id` だけを
持ち、経験の主体が永続化の面から消えていた。chunk / action draft builder は
呼び出し側の `BeingId` を VO に刻む。`ChunkEncodingInput` には載せない
(世界の手番ウィンドウであり、経験の主体ではない)。

**旧データ**: snapshot / SQLite payload に `being_id` キーが無い行は、ファイル
または行の Being から復元する。payload と fallback の両方があり不一致なら
失敗する (黙って片方を採用しない)。

**この PR で触らない**: `EpisodicPromotionFrontier` のキー変更、retrieve /
`on_episode_committed` 等の `being_id` 引数削除、他 VO の `player_id` 置換。

**その後**: runtime は主観エピソード (`SubjectiveEpisode`) を書かなくなった (記憶の部品の撤去 (#1631) の #1801)。区切りの書き起こし・主観補完・store は続く PR で消す。 snapshot のキー `episodic_episodes` もそこで消す。それまでは空で書き出し、古い snapshot に入っているエピソードは読んでも空の store に戻るだけで、次に保存するときに無くなる。

区切りの書き起こし・主観補完のサービスと scheduler は #1803 で消した。`SubjectiveEpisode` と store は段 12 の 3 本目で消す。

`SubjectiveEpisode` と store (in-memory / SQLite)、Being の snapshot のキー `episodic_episodes` も #1805 で消した。消す前の snapshot も読める。

## 175. 昇格フロンティアは BeingId で分ける

**何を**: `EpisodicPromotionFrontier` のキーを `player_id: int` から `BeingId`
に変更する。`add` / `add_many` / `drain` はすべて呼び出し側が決めた
`BeingId` を使う。`MemoryLink.player_id` や `acting.player_id.value` を
フロンティアのキーに使わない。

**なぜ**: link / promotion サービスは #146 で呼び出し側の `BeingId` を使う
ようになったが、昇格フロンティアだけが手番の数字 keyed のまま残っていた。
`on_after_tool_turn` はグラフを `being_id` で組み立てる一方 `drain(player_id)`
しており、`_hebbian_strengthen_existing` は `MemoryLink.player_id` を
フロンティアに入れていた。経験の主体は `BeingId` なので seed バッファも
同じ軸に揃える。

**snapshot には載せない**: フロンティアはランタイムの一時バッファのまま。
長走実験の再開で seed を復元する必要はない。

**この PR で触らない**: `MemoryLink.player_id` / `SemanticMemoryEntry.player_id`
の型変更、retrieve / `on_episode_committed` 等の `being_id` 引数削除、
`SubjectiveEpisode` の再設計。

**その後**: 昇格フロンティアは、クラスタ昇格と一緒に記憶の部品の撤去 (#1631) の #1792 で消した。

## 176. エピソードがある経路では BeingId を VO から読む

**何を**: `SubjectiveEpisode` を既に受け取る公開入口
(`on_episode_committed`、主観補完 scheduler の `submit`、chunk coordinator
の `_put_episode` 以降の sidecar) から、呼び出し側の `being_id` 引数を
削除する。store キーと sidecar は `episode.being_id` / `draft.being_id` を
一次にする。

**なぜ**: #174 で VO に `being_id` が必須になったあとも、同じ Being を
引数でもう一度渡しており、引数と VO が食い違う余地が残っていた。エピソード
が刻済みなら経験の主体は記録から読む。

**残す**: エピソードがまだ無い入口 (`after_action_recorded`、retrieve、
`MemoCompletionHintService.detect`、`on_passive_recall_candidates` 等) の
`being_id`。`put_by_being(being_id, episode)` の store 契約もそのまま。

**その後**: `SubjectiveEpisode` は記憶の部品の撤去 (#1631) の #1805 で消した。

## 177. 記憶リンクに経験の主体 BeingId を載せる

**何を**: `MemoryLink` に必須フィールド `being_id: BeingId` を追加する。
`player_id` は手番の身体として残す。store の一次キーと VO の `being_id` が
食い違う書き込みは `upsert_link_by_being` / `replace_all_by_being` で失敗
する。

**なぜ**: store は既に Being 単位のキーなのに、葉の記録は `player_id` だけを
持ち、経験の主体が永続化の面から消えていた。#174 の主観エピソードと同じ型を
`MemoryLink` に載せる。`EpisodicMemoryLinkApplicationService._put_fresh_link`
は呼び出し側の `being_id` を VO に刻む。

**旧データ**: snapshot payload に `being_id` キーが無い行は、restore 時の
snapshot Being から復元する。payload と fallback の両方があり不一致なら
失敗する (黙って片方を採用しない)。SQLite 行は既存の `being_id_value` 列から
VO に復元する (スキーマ変更は不要)。

**この PR で触らない**: `SemanticMemoryEntry.player_id` 他の記憶 VO、
`SubjectiveEpisode.player_id` の削除、`on_passive_recall_candidates` の
`being_id` 引数削除、未使用 `player_id` 引数の掃除。

**その後**: 記憶リンク (`MemoryLink`、store、Being の snapshot のキー `memory_links`) は記憶の部品の撤去 (#1631) の #1799 で消した。消す前の snapshot も読める (restore は足りないキーだけを拒む。リンクの欄は tick を持たないので replay でも止まらない)。SQLite のリンクの表は、表を作る版ごと使われなくなった。古い DB ファイルに表は残るが、どこも開かない。

## 178. monster spawnはslot 1件ごとに確定する

**何を**: `SpotGraphMonsterSpawnStageService`の条件付き配置を、一つの
`MonsterSpawnSlot`を処理する`CommandScope`へ移す。monster、skill loadout、graph、
slot対応と内部採番を同じ確定境界へ入れ、graphのspawn / despawn eventは確定後だけ
既存pipelineへ渡す。

**なぜ**: 従来はloadout、monster、graph、slot対応を順に直接更新していた。後段の
graph保存などが失敗すると、使われないloadoutやmonsterだけが残り、slotは未配置のため
次tickで別IDの実体を重ねて作る危険があった。またskill loadoutだけが共有data store外に
あり、既存のインメモリtransactionではrollbackできなかった。

**どう守るか**:

- 条件評価は確定状態を読むだけなのでscope外で行い、spawn / despawnが必要なslotだけcommandを開始する
- skill loadout repositoryもmonster等と同じ`InMemoryDataStore`から生成する
- graphとstageのslot対応・内部採番をrollback参加資源にし、保存失敗時は開始前へ戻す
- IDはscopeで戻せる内部counterだけを使い、外部factoryとの併用は構築時に拒否する
- graph eventはrepository保存成功後に`CommandContext`へ収集し、commit後だけ配送する
- 複数slotは別commandとし、先行slotの確定結果を後続slotの失敗で戻さない
- 既に別経路でgraphから除去されたmonsterだけはslotを空へ同期し、その他のdespawn例外は隠さない
- slotsがある公開stageは`CommandScopeFactory`を必須とし、長寿命repositoryへ
  直接書き込む旧経路を残さない。slotsが空のときだけ副作用なしで終了する

monster behaviorは攻撃、移動、採食などで更新資源が異なるため、このslot境界へ混ぜず、
monster 1体の行動単位として次段で移行する。

**関連**: #1094 / #1243 / 判断 #171〜#173。

## 179. monster behaviorはmonster 1体ごとに確定する

**何を**: `SpotMonsterBehaviorTickService`の攻撃、移動、採食などを、monster
1体を処理する`CommandScope`へ移す。monster、player status、interior、graphを
同じ確定境界へ入れ、行動が生んだeventは確定後だけ既存pipelineへ渡す。

**なぜ**: 従来は1回のstageで全monsterを順番に直接更新していた。後続のgraph保存
などが失敗すると、空腹やHP、地面itemだけが変わる部分適用が起こり得た。また後続
monsterの失敗が、先に完了したmonsterの行動まで失敗に見せる構造だった。

**どう守るか**:

- tick開始時に対象monster IDを確定し、ID昇順で1体ずつcommandを開始する
- monster、player status、interiorはscopeから得たrepositoryだけで更新する
- graphと行動乱数状態をrollback参加資源にし、攻撃状態異常の抽選も同じ乱数へ
  束縛して、途中失敗では開始前へ戻す
- `SpotAttackOrchestrator`もcommandごとに複製し、同じscopeのrepositoryとevent収集口へ束縛する
- graph eventはcommand開始前の列を保持し、そのmonsterが追加したsuffixだけを収集する
- 複数monsterは別commandとし、先行monsterの確定結果を後続monsterの失敗で戻さない
- 群れ行動のtick内cacheは従来どおり共有し、同じtick内の判断順序を変えない
- 公開`tick` APIは`CommandScopeFactory`を必須とし、未配線時はgraphや
  repositoryへ触れる前に拒否する。直接更新の旧経路は残さない

**関連**: #1094 / #1243 / 判断 #178。

## 180. reactive objectはbindingごと、passageはstage全体で確定する

**何を**: reactive objectはbinding 1件を一つの`CommandScope`、reactive
passageは全bindingを一つの`CommandScope`として処理する。両stageは同じscope
factoryを共有し、interior、graph、確率条件の乱数列、成功eventを確定境界へ入れる。

**なぜ**: objectはbindingごとに別のobject stateを更新するため、後続bindingの失敗で
先行bindingを戻す必要がない。一方passageは正逆接続を一つの論理接続として扱い、
stage内で重複観測を抑制するため、全bindingをまとめて確定する必要がある。従来は
objectのinterior保存後にgraph eventが未確定のまま残り、passageも複数接続を変更した
後の保存失敗でgraph参照へ部分状態が漏れ得た。

**どう守るか**:

- objectはbinding 1件ごとにscope由来interior / graph repositoryを使う
- passageは全bindingの接続変更と重複通知抑制を一つのscopeへ入れる
- graphと共有`ScenarioConditionEvaluator`の乱数列を同じrollback参加資源にする
- 各commandが追加したgraph eventだけを収集し、以前のstageが残したeventを横取りしない
- 成功eventはinterior / graphの確定後だけ既存pipelineへ配送する
- 後続object bindingの失敗は先行bindingの確定状態と観測を戻さない
- object bindingsがある公開stageは`CommandScopeFactory`を必須とし、長寿命repositoryを
  constructorへ保持せずscope由来repositoryだけを使う。bindingsが空のときだけ副作用なしで終了する
- passage bindingsがある公開stageは`CommandScopeFactory`を必須とし、長寿命repositoryへ
  直接書き込む旧経路を残さない。bindingsが空のときだけ副作用なしで終了する

**関連**: #1094 / #1243 / 判断 #179。

## 181. synchronized actionはgroupごとに確定する

**何を**: `SynchronizedActionResolverStageService`は、一つの同期行動groupを一つの
`CommandScope`として処理する。準備状態を表すworld flag、同期効果のworld flag、
graph上の通路変更と成功eventを同じ確定境界へ入れる。

**なぜ**: 従来は全groupを一つのgraph参照へ順番に適用し、最後に一度だけ保存して
いた。また成功messageはgraph保存より先に通知していた。このため、後続groupや最後の
保存が失敗すると、先行groupの成功まで失敗に見えたり、実際には戻った通路変更を成功と
通知したりする余地があった。

**どう守るか**:

- group 1件ごとにscope由来graph repositoryを使い、world flagとgraphを同時に戻せるようにする
- 完了・期限切れで準備flagを消す処理も同じscopeへ入れ、効果だけ確定する状態を作らない
- groupが追加したgraph eventだけを収集し、前段stageが残したeventはそのまま保持する
- 成功messageは専用eventとして同じ`CommandContext`へ収集し、command確定後にだけ通知する
- 後続groupの失敗は、先に確定したgroupの状態・event・messageを戻さない
- groupsがある公開stageは`CommandScopeFactory`を必須とし、長寿命repositoryと直接callbackを持たない
- groupsが空のときだけscope・registry・world flagへ触れず副作用なしで終了する

**関連**: #1094 / #1243 / 判断 #180。

## 182. 天候と昼夜は遷移ごとに独立して確定する

**何を**: `SpotGraphEnvironmentStageService`の天候更新と
`SpotGraphDayNightStageService`の昼夜更新を、それぞれ一つの`CommandScope`へ
移す。天候は現状態と専用乱数位置、昼夜は現在の`TimeOfDay`をrollback参加資源にする。

**なぜ**: 従来は状態を先に書き換えてからcallbackを直接呼んでいた。後続処理が
失敗したときの確定単位がなく、天候抽選で消費した乱数も戻せなかった。また天候は
モジュール全体の乱数を使っており、snapshot再開後の抽選列を継続できなかった。

**どう守るか**:

- 天候更新間隔に到達したtickだけcommandを開始し、現天候と専用`random.Random`を一緒に戻す
- 昼夜は毎tickの`TimeOfDay`更新を一つのcommandとし、commit失敗では開始前へ戻す
- 天候・昼夜の変更は`CommandContext`へeventとして収集し、専用dispatcherがscope終了後だけ通知する
- commit済み後処理失敗でも確定済みeventを通知してから元の`CommandPostCommitException`を維持する
- `WeatherSubsystemCodec`をschema v2へ上げ、天候専用乱数位置も保存・復元する
- 旧schema v1は現天候だけを復元し、起動済みruntimeの乱数位置は変更しない
- `WeatherSimulationService`の直接利用は従来のモジュール乱数を維持し、stageだけ専用乱数を渡す

天候と昼夜は順序上連続していても別の世界状態であり、片方の観測失敗や後段失敗で
もう片方を戻す理由はないため、scopeは共有しない。

**関連**: #1094 / #1243 / 判断 #181。

## 183. 食料劣化は全対象itemをstage単位で確定する

**何を**: `FoodSpoilageStageService`の1回の`run`を一つの`CommandScope`へ
移し、そのtickで進行する全`ItemAggregate`を同じtransactionで保存する。
`ItemSpoiledEvent`はscope終了後に専用dispatcherが日次観測バッファへ渡す。

**なぜ**: 従来はitemを一件ずつ保存し、その場で個別callbackを呼んでいた。後続itemの
保存に失敗すると、先行itemだけが腐り、stage全体は失敗を返す部分適用になり得た。
また最終保存前に「腐った」という観測が出るため、rollback後の状態と観測が矛盾する
余地があった。同tickの腐敗は一括観測へ集約されるため、確定単位もstage全体が自然で
ある。

**どう守るか**:

- 本番runtimeはscope由来の`ItemRepository`だけで全対象itemを走査・保存する
- 一件でも保存や同期処理に失敗したら、同tickで変更した全itemを開始前へ戻す
- 腐敗eventは全item保存後にだけ配送し、通知失敗で確定済みitemを戻さない
- commit済みcleanup失敗でもeventを配送してから`CommandPostCommitException`を維持する
- 腐敗の進行規則は従来どおり`ItemAggregate.advance_spoilage`を唯一の正本にする
- 腐敗対象がある公開`run()`はscopeを必須とし、旧repository・callbackを保持しない

**関連**: #1094 / #1243 / 判断 #119 / 判断 #182。

## 184. 期限切れ取引提案はoffer一件単位で予約解除と一緒に確定する

**何を**: `TradeOfferExpiryStage`が検出した期限切れ提案を、一件ごとに独立した
`CommandScope`へ移す。pending offer storeをrollback参加資源、offererのinventoryと
itemをscope内repositoryとして扱い、提案削除とitem予約解除を同時に確定する。

**なぜ**: 従来は予約解除を先に行う順序により、途中失敗を次tickで自己修復できる
形にしていた。しかし予約解除後に提案削除が失敗すると、そのtick中は「生きている
提案なのに品を使える」という中間状態が残る。順序による回復可能性は安全網として
有用だが、同じ操作の二状態を一緒に確定できるなら中間状態自体を作らない方がよい。

**どう守るか**:

- 期限判定と処理順は従来どおりoffer ID順にし、期限内の提案には触れない
- offer一件の予約解除・inventory保存・pending store削除を一つのscopeへ入れる
- 後続offerが失敗しても、先に確定したofferの期限切れは戻さない
- 期限切れ観測は各offerのcommit後に観測pipelineへ直接、最善努力で通知する。
  tick末のgraph event flushへ預けると、後続offer失敗時に先行offerの観測まで
  滞留するため、offer単位の確定境界と配送境界を揃える
- commit済みcleanup失敗では観測後に元の`CommandPostCommitException`を維持する
- pending storeのsnapshotは提案集合と次IDを厳密に保持する
- 候補取得もscope由来のpending storeだけで行い、各offerのscope内で現在も期限切れか再確認する
- 公開`run()`はscopeを必須とし、長寿命pending store・凍結service・直接callbackを保持しない
- `TradeOfferExpiredEvent`をcommand contextへ収集し、専用dispatcherがcommit後に観測pipelineへ渡す

**関連**: #1094 / #1243 / 判断 #87 / 判断 #183。

## 185. 期限切れ市場注文はorder一件単位で預り資産と一緒に確定する

**何を**: `MarketOrderExpiryStage`が検出した期限切れ注文を、一件ごとに独立した
`CommandScope`へ移す。market board storeをrollback参加資源、返却先のinventory・
player status・itemをscope内repositoryとして扱い、板の削除または引き取り待ち化と
預り品・預りgoldの返却を同時に確定する。

**なぜ**: 従来の`MarketService.expire_orders`は複数注文の預り資産を順に返し、
最後に板全体を一度だけ保存していた。途中注文で失敗すると、先行注文は資産だけ
返却済みなのに板へ残り、次tickで同じ資産を二重返却し得る。stageが例外を警告へ
変えるため、世界はその不整合を抱えたまま進行していた。

**どう守るか**:

- 期限判定は板のsnapshotからorder ID順に行い、各order内で現在も期限切れか再確認する
- 売り注文はitem生成・inventory返却・板更新、買い注文はgold返却・板更新を同じscopeへ入れる
- 所持品が満杯なら品を失わず、従来どおり引き取り待ちへの遷移だけを確定する
- 通常失敗したorderは開始前へ戻して次tickで再試行し、独立した後続orderは処理を続ける
- 先行orderの確定は後続orderの失敗で戻さない
- 期限切れ観測と市場traceは各orderのcommit後だけ最善努力で通知する
- commit済みcleanup失敗では観測後に`CommandPostCommitException`を維持し、資源を再利用させない
- market board snapshotは板と次order IDを厳密に保持する
- 公開stageと`MarketService.expire_orders` / `expire_order`は`CommandScopeFactory`を
  必須とし、未配線なら板を読む前に拒否する
- 公開一括入口も注文ごとに独立したscopeを作り、実更新はscope由来repositoryを
  受け取るprivate処理だけへ集約する

**関連**: #1094 / #1243 / 判断 #115 / 判断 #140 / 判断 #184。

## 186. プレイヤー結果規則は発火rule単位で全対象と進捗を確定する

**何を**: `PlayerOutcomeRuleStageService`の条件評価、適格な未確定player全員の
outcome遷移、一度限りの発火進捗を、rule一件ごとの`CommandScope`へ移す。
`PlayerOutcomeRegistry`、`InMemorySpotGraphScenarioEventProgressStore`、
`ScenarioConditionEvaluator`の確率乱数をrollback参加資源にする。

**なぜ**: 従来は適格playerを順に`set_outcome`し、全員の処理後に進捗を記録して
いた。途中のplayer評価や最後の進捗記録で失敗すると、先行playerだけ結果と通知が
確定した一方でruleは未消費になり、次tickに同じ機会を再評価する部分確定が残った。

当初の監査表では「playerとruleの一組」を確定単位としていたが、once ruleは対象者が
ゼロでも機会を消費し、同じ発火機会に複数playerが適格になり得る。playerごとに進捗を
確定すると、先行playerの成功後に後続playerが失敗した場合、その後続playerだけが機会を
永久に失う。したがって、発火時点の適格player集合とrule進捗を一つの業務不変条件として
扱う。

**どう守るか**:

- 発火済みのonce ruleはscope開始前にskipし、資源所有権の取得後にも再確認して
  待機中に確定した同じruleを二重評価しない
- triggerとplayer条件の評価もscope内で行い、失敗時は消費した確率乱数を戻す
- ruleで許可するoutcomeは、この境界だけで世界状態を完結できる`RESCUED`と
  `STRANDED`に限る。退場位置やgraph更新を要する`DEAD` / `EJECTED`は読込時に拒否する
- outcome更新ではcallbackを抑止し、全outcomeとprogressのcommit後に元のplayer順で通知する
- 対象者がゼロでも、triggerが成立したonce ruleは従来どおり発火済みにする
- 通常失敗はrule全体を開始前へ戻す。先行ruleの確定は後続ruleの失敗で戻さない
- commit済みcleanup失敗では確定outcomeを通知してから`CommandPostCommitException`を維持する
- 条件traceは成功観測ではなく評価試行の診断なので、従来どおり評価時点で記録する
- 規則がある公開stageは`CommandScopeFactory`を必須とし、未配線なら進捗を読む前に
  拒否する。outcomeとonce進捗を直接更新する旧callback経路は残さない

**関連**: #1094 / #1243 / 判断 #70 / 判断 #114 / 判断 #169 / 判断 #185。

## 187. 死亡猶予の期限到達はplayer単位で結果・timer・退場位置を確定する

**何を**: `PlayerDeathGraceTickStage`が検出した期限超過playerを、一人ごとの
`CommandScope`へ移す。`PlayerOutcomeRegistry`、`PlayerDeathGraceTimer`、
`FallenBodyRegistry`、`DepartedPositionStore`をrollback参加資源にし、`DEAD`遷移、
pending削除、身体位置を起点にした退場位置を一緒に確定する。

**なぜ**: 従来は`set_outcome(DEAD)`がcallbackを即時実行し、そのcallbackが退場位置と
観測を更新した後にgrace timerを掃除していた。timer掃除や後続playerで失敗すると、
死亡結果・退場位置・観測だけが残り、pendingも次tickの再試行対象も不整合になり得た。
また、期限超過一覧の取得後に蘇生されても、古い候補を再確認せず死亡確定できた。

**どう守るか**:

- 期限超過一覧の順序を維持しつつ、player一人ごとに独立scopeを作る
- scope取得後にtimerのpending・期限と正本`PlayerStatus.is_down`を再確認する。蘇生済みなら
  `DEAD`にせず、個別handler失敗で残ったpendingと身体記録だけを同じscopeで掃除する
- outcome callbackを抑止して`DEAD`・pending削除・退場位置をcommit前に揃える
- outcome registryのcallbackから退場位置変更を除き、commit後の観測だけを残す
- 身体記録が無い場合は従来どおり`DEAD`とpending削除を確定し、退場位置未設定を
  commit後に警告する
- 通常失敗はそのplayerだけ開始前へ戻す。先行playerの死亡確定は後続playerの失敗で戻さない
- commit済みcleanup失敗では確定済みoutcomeを通知してから
  `CommandPostCommitException`を維持する
- 公開stageは`CommandScopeFactory`を必須とし、未配線ならtimerを読む前に拒否する。
  直接構築から死亡結果だけを更新できる旧callback経路は残さない
- `PlayerOutcomeRegistry.set_outcome(DEAD)`の直接呼出しは結果だけを変える低水準操作とし、
  退場位置を暗黙に補完しない。世界状態を伴う死亡確定はdeath grace commandが所有する

**関連**: #1094 / #1243 / 判断 #114 / 判断 #169 / 判断 #186。

## 188. 探索は発見回数・室内・付与品・観測を一度に確定する

**何を**: 本番の`SpotExplorationApplicationService.explore_once`を
`CommandScope`へ移し、探索回数、発見済み状態、生成品、所持品、満杯時に足元へ
落とす品を同じ失敗境界へ入れる。`SpotExploredEvent`と溢れ観測はcommit後だけ配送する。

**なぜ**: 従来は探索回数を先に増やし、室内保存、品物生成、所持保存を順に行っていた。
後段が失敗すると探索回数や発見済み状態だけが残り、再試行しても報酬を得られない、
または状態に存在しない発見を観測する部分確定が起こり得た。

**どう守るか**:

- 探索回数storeをrollback参加資源にし、共有`InMemoryDataStore`のrepository更新と揃える
- `GroundOverflowSink`はscope由来repositoryと`CommandContext`へ束縛し直す
- 成功観測は発見状態と品物付与のcommit後にだけ配送する
- 公開`explore_once`はscope factory未配線ならrepositoryへ触れる前に停止し、
  探索規則の単体試験だけが`_explore_with_repositories`を直接使う
- world flagは探索条件の読取専用であり、このcommandの変更資源には含めない

**関連**: #1094 / #1244 / 判断 #87 / 判断 #114 / 判断 #187。

## 189. 同席取引は提案・承諾・辞退をそれぞれ一度に確定する

**何を**: 現行`WorldRuntime`が使う`PlayerTradeService`の`offer`、`accept`、
`decline`を、一操作ごとの`CommandScope`へ移す。pending offer storeをrollback参加資源、
二者のinventory・status・itemをscope内repositoryとし、取引観測はcommit後に配送する。

**なぜ**: 提案はstore登録後に品物を予約し、承諾は予約解除後に二者の品物と所持金を
順に動かし、辞退は予約解除後にstoreから提案を消していた。途中失敗すると、提案の
無い予約、品物だけ動いた決済、辞退済みなのに予約中といった部分確定が残り得た。

**どう守るか**:

- 提案ではID払い出し・store登録・差し出す品の予約を同時に確定する
- 承諾では予約解除・二者の品物・所持金・提案削除を同時に確定する
- 辞退では予約解除と提案削除を同時に確定する
- `TradeFreezeService`もcommand内のinventory・status・itemを使い、長寿命repositoryを迂回しない
- 成功観測は同じ`CommandContext`へ収集し、commit前には外へ出さない
- 公開更新入口はscope未配線なら依存へ触れる前に停止し、規則実行はscope用の内部複製だけに許す

**関連**: #1094 / #1244 / 判断 #87 / 判断 #114 / 判断 #184 / 判断 #188。

## 190. NPC商人との売買は支払・品物・観測を一度に確定する

**何を**: `SpotGraphMerchantTradeService.buy`と`sell`を、一回の売買ごとの
`CommandScope`へ移す。playerのstatus・inventory・itemをscope内repositoryから取得し、
取引中の凍結額・予約品を読む`TradeFreezeService`も同じrepositoryへ束縛する。

**なぜ**: 購入は所持金を保存してから品物を生成・付与し、売却は品物を所持から外して
から所持金を保存していた。後半が失敗すると、支払ったのに品物が無い、品物を失ったのに
代金が増えない部分確定が残り得た。成功観測も確定前に直接配送されていた。

**どう守るか**:

- 購入では支払・品物生成・所持保存を同時に確定する
- 売却では所持からの除去・所持金加算を同時に確定する
- pending offer storeも読取中の凍結状態を安定させるため同じ資源所有権へ参加させる
- `PlayerTradedWithMerchantEvent`は`CommandContext`へ収集してcommit後にだけ配送する
- 商人の在庫と所持金は従来どおり無限かつ状態を持たないため、変更資源に加えない
- 公開更新入口はscope未配線なら依存へ触れる前に停止し、規則実行はscope用の内部複製だけに許す

**関連**: #1094 / #1244 / 判断 #114 / 判断 #189。

## 191. 市場注文の預託・値付け・返却は操作ごとに確定する

**何を**: playerによる売り注文・買い注文の掲載、値付け直し、取り下げを、
一回の公開操作ごとの`CommandScope`へ移す。板と採番をrollback参加資源とし、
inventory・status・itemはscope内repositoryだけで更新する。

**なぜ**: 板は品またはgoldを先に預かる。掲載後半の板保存、買い注文の値上げ、
取り下げ後半の板保存が失敗すると、預けた資産と板の注文が食い違い得た。
成功観測と価格traceも確定前に出るため、失敗した注文が価格履歴へ残る余地があった。

**どう守るか**:

- 板、次の注文ID、品、goldを同じrollback境界へ載せる
- pending trade offerも同じ資源所有権へ載せ、対人取引へ提示中のgoldを
  `TradeFreezeService.available_gold`で差し引いて二重利用を拒否する
- `MarketBoardActivityEvent`は`CommandContext`へ収集してcommit後にだけ配送する
- 市場traceは操作中に保留し、commit後またはcommit済み後処理失敗時にだけ転記する
- 複数注文を受ける`buy_best` / `sell_best`と直接の`take_order`は、複数約定を
  一括確定する次の段階で移す
- 商人名義の初期注文はworld構築中に置かれ、player資産を動かさないため対象外とする
- player資産を動かす公開更新入口はscope未配線なら依存へ触れる前に停止する

**関連**: #1094 / #1244 / 判断 #114 / 判断 #190。

## 192. 一回の市場操作が生む複数約定はまとめて確定する

**何を**: `take_order`、`buy_best`、`sell_best`を市場更新用`CommandScope`へ
接続する。`buy_best` / `sell_best`が複数注文を順に受けても、外側の公開操作が
一つのscopeを所有し、内側の各`take_order`は同じrepositoryと板を使う。

**なぜ**: 価格順に複数注文を受ける途中で後半が失敗すると、先頭の約定だけが
成立し、呼び出しは失敗を返す部分確定が起こり得た。満杯の遠隔買い手へ品を
渡す経路は板の足元へ品を置くため、地面とその観測も同じ問題を持っていた。

**どう守るか**:

- 一回の`buy_best` / `sell_best`が動かす全注文、全playerのgold・inventory、
  item実体、板と採番を一つのrollback境界へ載せる
- `take_order`を直接呼ぶ場合も一約定を同じ境界へ載せる
- `GroundOverflowSink.bind_to_command`で板の足元への配送をscope内の
  graph・interior・itemと`CommandContext`へ束縛する
- 全約定の観測はcommit後に宣言順で配送し、価格traceもcommit後に転記する
- 対人取引へ提示中のgoldは判断#191と同じ`TradeFreezeService`で差し引く

**関連**: #1094 / #1244 / 判断 #114 / 判断 #191。

## 193. アイテム消費と消費効果は同じ確定区間で適用する

**何を**: 本番`spot_graph_use_item`を専用`CommandScope`へ接続し、itemの数量、
inventory slot、PlayerStatusへの消費効果と疲労回復を一操作として確定する。
`ConsumableUsedEvent`はcommit前必須処理で状態効果を適用した後、commit後の観測へ
同じeventを引き渡す。

**なぜ**: 旧経路は品物を先に保存・削除してから`ConsumableUsedEvent`をpipelineへ
直接配送し、pipeline side handlerが別の更新としてPlayerStatusへ効果を適用していた。
効果保存が失敗すると品物だけが減り、逆に確定前の観測や後段の疲労回復失敗も
一操作の成否へ追随しなかった。

**どう守るか**:

- item・inventory・PlayerStatusは同じscope由来repositoryだけで更新する
- 通常の消費効果は`ConsumableUsedEvent`のcommit前必須handlerとして適用する
- 腐敗品の直接ダメージと疲労回復も失敗を握らず、操作全体をrollbackする
- pipelineから状態変更handlerを外し、確定後は観測だけを配送する
- LLMの短発話はscope終了後に行い、失敗した消費を発話しない
- `SpotGraphToolExecutor._use_item`はscope factory未配線なら`NOT_WIRED`で拒否し、
  scope外でitem・inventory・statusを更新する旧入口を#1244で撤去する

**関連**: #1094 / #1244 / #1279 / 判断 #114 / 判断 #192。

## 194. 介抱による復活と復活イベントは同じ確定区間へ載せる

**何を**: 本番`spot_graph_tend_to_player`を`CommandScope`へ接続し、対象の
`PlayerStatusAggregate.revive`、status保存、`PlayerRevivedEvent`収集を一操作として
確定する。短発話とeventの外部配送はscope正常終了後にだけ行う。

**なぜ**: 旧経路はstatusを長寿命repositoryへ保存してからeventをpipelineへ直接
配送していた。保存失敗をDTOへ変換すると、repository実装によっては復活だけが漏れ、
逆に確定前の復活観測が出る余地もあった。前提条件違反も通常returnなので、scopeを
正常commitさせず明示的にrollbackへ写す必要がある。

**どう守るか**:

- actorとtargetはscope由来のPlayerStatus repositoryから読み直す
- 成功時だけstatusと`PlayerRevivedEvent`をcommitし、失敗DTOは内部例外でrollbackする
- `PlayerRevivedEvent`は確定後に既存pipelineへ渡し、復活済みstatusを観測できる
- `say_inline`はscope終了後に行い、~~失敗した介抱を発話しない~~ (design_decisions D1601 で取り消し。失敗した介抱の発言も scope 終了後に出す。発言を出さない理由は確定区間の順序だけで、失敗には当てはまらなかった)
- FallenBodyとdeath grace timerは判断#196で同じscopeのrollback参加資源となり、
  status遷移と一緒に確定する
- `SpotGraphToolExecutor._tend_to_player`はscope factory未配線なら`NOT_WIRED`で
  拒否し、復活statusだけを部分確定できる旧入口を#1244で撤去する

**関連**: #1094 / #1244 / #1279 / 判断 #114 / 判断 #193。

## 195. 協力行動の二種類の準備記録は一緒に確定する

(#218 で入口を `interact` に統合した。準備経路自体はここに書いたとおり。)

**何を**: 本番`spot_graph_prepare_action`を`CommandScope`へ接続し、互換用の
`prepared:{action}:{player}` flagと、猶予窓判定用の
`sync_prep:{action}:{player}:{tick}` flagを一操作として確定する。準備観測は
両方のflagがcommitした後にだけ配送する。

**なぜ**: 旧経路は二種類のflagを順番に直接更新していた。後半のtick付き登録が
失敗すると、操作は失敗を返す一方で互換flagだけが残り、別のinteraction条件が
準備済みと誤認できた。`SpotPlayerPreparedActionEvent`も更新中にpipelineへ直接
渡され、観測が確定状態より先行し得た。

**どう守るか**:

- world flagをrollback参加資源として占有し、二種類の準備記録をまとめて戻す
- graph参照はscope由来の読取口を使い、準備eventは`CommandContext`へ収集する
- 失敗DTOは内部例外へ写してscopeをrollbackし、部分的なflagを残さない
- 準備観測のhandlerから両flagの確定状態を読めることを試験で固定する
- `SpotGraphToolExecutor._prepare_action`はscope factory未配線なら`NOT_WIRED`で
  拒否し、実処理はscope内部の`_execute_prepare_action_in_scope`だけが呼ぶ

**関連**: #1094 / #1244 / 判断 #114 / 判断 #194。

## 196. ダウン・蘇生は身体と死亡猶予まで一度に確定する

**何を**: `PlayerDownedEvent`と`PlayerRevivedEvent`に伴うFallenBodyと
`PlayerDeathGraceTimer`の更新を、イベントを生んだ`CommandScope`のcommit前必須処理へ
移す。PlayerStatus、身体、猶予タイマーを同じ失敗境界で確定し、外部観測はcommit後に
だけ配送する。

**なぜ**: 旧経路はPlayerStatusを確定した後、`PipelineEventPublisher`の最善努力
side handlerで身体と猶予を別々に変更していた。登録・取消の片方が失敗すると、倒れて
いるのに死亡期限が無い、蘇生済みなのに期限到達で死亡する、といった回復不能な状態が
残った。確定後に同じ状態handlerを再実行する経路も、古いeventが新しいepisodeを
上書きする原因になる。

**どう守るか**:

- interaction、道具使用、needs・状態異常tick、scenario event、monster行動の各scopeで
  同じ身体・猶予参加資源を共有する
- 身体記録・猶予登録・身体削除・猶予取消の失敗はPlayerStatusを含む操作全体を戻す
- 本番のpipelineから身体・猶予の正本更新を外す。#1244で互換アダプタも撤去し、
  `PipelineEventPublisher`は身体・猶予を補正しない観測専用の出口にする
- commit前の猶予取消で失神時間を失わないよう、取消時の起点tickを復活event_idへ
  一度だけ引き渡し、commit後のpost hoc観測が消費する
- テストがダウン状態を直接準備する場合はPlayerStatus・身体・猶予を明示して作り、
  `publish_all`を状態更新コマンドの代わりに使わない

**関連**: #1094 / #1244 / #1279 / 判断 #114 / 判断 #187 / 判断 #194。

## 197. 旧確定経路は許可表を縮めながら撤去する

**何を**: #1244の最終撤去では、`CommandScopeFactory`を保持するapplication serviceを
「scope必須」と「未配線時に旧更新へ戻る残存経路」へ機械的に分類する。旧
`domain.common.unit_of_work.UnitOfWork`を直接使うmoduleと、`UnitOfWorkFactory`経由で
生成するmoduleも別の許可表へ固定し、現行のruntime・LLM・presentationから再接続しない。

**なぜ**: 本番composition rootへfactoryを注入しただけでは、直接構築や将来の配線漏れで
長寿命repository・直接publisherへ静かに戻れる。反対に、未接続の旧bounded contextを
spot-graph runtimeの撤去と一括で消すと、現在の機能境界を越えた大きな変更になる。
「通常は新経路を通る」と「旧経路が存在しない」を区別し、残件を数えられる正本が必要である。

**どう守るか**:

- `docs/refactor_plans/uow_legacy_command_path_inventory.md`を人間向け正本とする
- 構造試験でscope所有serviceの分類、旧UnitOfWork・factory import一覧、本番composition
  rootの再exportを含むimport graphと旧client classの構築禁止を双方向に検査する
- 移行PRごとに残存許可表から対象を除き、未配線拒否をrepository接触前に試験する
- query、純粋な観測生成、fixture・移行・管理用書込みを更新commandと混同しない
- 残存許可表が空になってから全scenario構築と全体試験を行い、#1244を閉じる

**関連**: #1094 / #1244 / 判断 #147〜#196。

## 198. player statusのtick stageはscope未配線を拒否する

**何を**: `SpotGraphNeedsDecayStageService`と`StatusEffectsTickStageService`から、
長寿命`PlayerStatusRepository`と直接publisherを撤去する。公開`run()`は
`CommandScopeFactory`を必須とし、未配線なら状態へ触れる前に拒否する。

**なぜ**: 本番runtimeがfactoryを注入していても、直接構築時に旧repositoryへ戻れる限り、
将来の配線漏れが非原子的な更新として静かに動く。旧publisherはPlayerStatus確定前のevent
配送を再導入でき、判断#171・#172で作った身体・死亡猶予を含む確定境界を迂回する。

**どう守るか**:

- constructorは更新規則とevidence依存だけを受け、repository・publisherを保持しない
- 公開`run()`はscope由来repositoryだけで全playerを一括更新する
- aggregate eventはrepositoryのevent sinkから`CommandContext`へ集め、確定後だけ配送する
- 未配線拒否、全員rollback、確定後event、commit済みcleanup時のevidence追随を試験する
- 純粋なneeds・状態異常規則はprivate helperへrepositoryを明示して検証する

**関連**: #1094 / #1244 / 判断 #171 / 判断 #172 / 判断 #197。

## 199. 食料劣化の公開入口はscopeと集約eventだけを使う

**何を**: `FoodSpoilageStageService`から長寿命`ItemRepository`、個別callback、
一括callbackを撤去する。腐敗対象がある公開`run()`は`CommandScopeFactory`を必須とし、
`ItemAggregate`が積む`ItemSpoiledEvent`を専用dispatcherで確定後に日次観測へ渡す。

**なぜ**: 本番配線がscopeを使っていても旧repository入口が残れば、直接構築や将来の
配線漏れで全item一括rollbackを迂回できる。callbackは保存処理と通知処理を同じserviceへ
再結合し、確定前観測や`CommandPostCommitException`時の通知漏れを再導入しやすい。

**どう守るか**:

- 腐敗対象が空なら依存へ触れず終了し、対象があればrepository接触前に未配線を拒否する
- 腐敗規則とevent生成を`ItemAggregate.advance_spoilage`へ置き、stageは走査・保存だけを行う
- 専用dispatcherは全itemのcommit後にeventを日次観測バッファへ渡す
- 保存失敗では全itemとevent配送を戻し、確定後handler失敗では状態を戻さない
- 構造棚卸しではfood spoilageを残存許可表からscope必須表へ移す

**関連**: #1094 / #1244 / 判断 #119 / 判断 #183 / 判断 #197。

## 200. 取引提案期限切れの公開入口はscope由来storeだけを使う

**何を**: `TradeOfferExpiryStage`から長寿命pending store、`TradeFreezeService`、
直接observerを撤去する。候補取得とofferごとの再確認・予約解除・削除をscope由来の
依存だけで行い、`TradeOfferExpiredEvent`を確定後に専用dispatcherへ渡す。

**なぜ**: 候補取得だけを確定区間の外へ残すと、別commandが先に承諾・辞退した提案を
古いsnapshotから期限切れにできる。直接callbackも、commit済みcleanup失敗や後続offerの
失敗時に通知漏れ・二重通知を作りやすい。更新と通知の所有者をoffer単位のcommandへ
揃えれば、先行offerの確定を維持したまま後続offerだけを戻せる。

**どう守るか**:

- 公開`run()`はscope未配線を状態参照前に拒否する
- 最初のscopeで候補IDだけを取得し、offerごとのscopeで現在状態と期限を再確認する
- providerが公開するpending storeは、同じrollback participantの資源であることを検証する
- 予約解除、pending store削除、`TradeOfferExpiredEvent`収集を同じscopeへ入れる
- 観測失敗で確定済みofferを戻さず、後続offer失敗でも先行offerの通知を失わない
- 構造棚卸しではtrade offer expiryを残存許可表からscope必須表へ移す

**関連**: #1094 / #1244 / 判断 #87 / 判断 #184 / 判断 #197。

## 201. 天候・昼夜の公開入口はscopeと確定後eventだけを使う

**何を**: `SpotGraphEnvironmentStageService`と`SpotGraphDayNightStageService`から
直接callbackと未配線時の更新経路を撤去する。更新対象tickの公開`run()`は
`CommandScopeFactory`を必須とし、天候・昼夜の変更を専用eventとして収集する。

**なぜ**: 本番がscopeを注入していても、未配線時に状態を直接更新できれば、将来の
配線漏れで天候状態・乱数位置・昼夜位置のrollbackを静かに迂回できる。callbackをstageへ
残すと、状態更新と観測配送が再び結合し、確定前通知や確定後例外時の通知漏れを作りやすい。

**どう守るか**:

- 天候は更新間隔外のtickだけ副作用なしで終了し、更新対象tickではstate参照前に未配線を拒否する
- 昼夜は毎tickの更新前に未配線を拒否する
- stageは`SpotGraphWeatherChangedEvent`または`SpotGraphDayNightPhaseChangedEvent`を収集するだけにする
- 本番composition rootの専用dispatcherが、設定された場合だけ確定後観測へ変換する
- callback handlerの失敗は最善努力として警告化し、確定済み世界状態を戻さない
- 構造棚卸しではweather・day-nightを残存許可表からscope必須表へ移す

天候のprovider / setterと昼夜の現在値はrollback・snapshotの対象となるstage自身の状態境界であり、
観測用の長寿命依存ではないため残す。

**関連**: #1094 / #1244 / 判断 #182 / 判断 #197。

## 202. reactive objectと同期行動の公開入口はscopeだけを使う

**何を**: `ReactiveObjectStateBindingStageService`と
`SynchronizedActionResolverStageService`から、未配線時の長寿命repository更新を撤去する。
同期行動の`SHOW_MESSAGE`も直接callbackではなく専用eventとして確定区間へ収集する。

**なぜ**: 本番配線が正しくても直接更新入口が残ると、将来の配線漏れや直接構築で
interior・graph・world flag・prepare消去のrollbackを静かに迂回できる。message callbackを
stageが所有すると、状態確定と観測配送が別の成功条件になり、確定前通知を再導入しやすい。

**どう守るか**:

- bindings / groupsが空のときだけscope不要の副作用なし終了を許す
- 更新対象がある場合はrepository・条件評価・registryへ触れる前に未配線を拒否する
- reactive objectはconstructorへgraph / interior repositoryを受け取らず、bindingごとにscope由来repositoryを使う
- synchronized actionはconstructorへgraph / interior repositoryとmessage callbackを受け取らない
- `SynchronizedActionMessageEvent`をgraph eventの後に収集し、専用dispatcherが確定後に参加者観測へ変換する
- 構造棚卸しでは両stageを残存許可表からscope必須表へ移す

**関連**: #1094 / #1244 / 判断 #180 / 判断 #181 / 判断 #197。

## 203. monster behaviorの公開tickはscopeを必須とする

**何を**: `SpotMonsterBehaviorTickService.tick`から、`CommandScopeFactory`未配線時に
長寿命repositoryを直接更新する旧経路を撤去する。未配線ならgraphを読む前に
明示例外で停止する。

**なぜ**: 本番runtimeがfactoryを注入していても、直接構築で旧経路へ戻れる限り、
将来の配線漏れが攻撃・移動・採食の部分適用と確定前観測を静かに復活させる。
monster単位で作った確定境界を公開入口の唯一の更新経路にする必要がある。

**どう守るか**:

- 公開`tick`は最初にfactoryを検査し、未配線ならrepositoryとorchestratorへ触れない
- tick開始時のID一覧も読取り専用scopeのgraphから取得し、各monsterの
  更新は必ず別のscope由来repositoryで行う
- 攻撃・採食・移動の規則試験はprivateなロード済み規則入口に寄せ、
  公開入口の配線契約と混同しない
- 構造棚卸しでmonster behaviorを残存許可表からscope必須表へ移す

**関連**: #1094 / #1244 / 判断 #179 / 判断 #197。

## 204. 取引系の公開更新入口はscope未配線を拒否する

**何を**: `PlayerTradeService`、`SpotGraphMerchantTradeService`、`MarketService`から、
`CommandScopeFactory`未配線時に長寿命repositoryで更新する旧経路を撤去する。公開更新は
scopeを必須とし、scope用の内部複製だけが束縛済みrepositoryで取引規則を実行する。

**なぜ**: 本番runtimeがfactoryを注入していても、直接構築時の更新fallbackが残れば、
将来の配線漏れで提案の予約、二者決済、商人売買、市場の預託・約定を部分確定へ戻せる。
さらにplayer tradeとmerchant tradeの長寿命publisherはscope経路では使われず、確定前配送を
再導入できる不要な接続口になっていた。

**どう守るか**:

- player tradeの提案・承諾・辞退、merchant tradeの購入・売却、市場のplayer資産を動かす
  公開更新は、factory未配線ならrepository・store・publisherへ触れる前に停止する
- scope用内部複製を明示し、その複製だけが既存の規則本体を実行する
- player tradeとmerchant tradeの長寿命publisher setterをcomposition rootから撤去し、
  成功eventは`CommandContextEventPublisher`だけへ収集する
- market order expiryの確定後観測口と、world構築時の商人初期注文は更新fallbackではないため維持する
- 構造棚卸しで3サービスを残存許可表からscope必須表へ移す

**関連**: #1094 / #1244 / 判断 #184 / 判断 #189 / 判断 #190 / 判断 #191 / 判断 #192 / 判断 #197。

## 205. interactionの公開更新入口はscope未配線を拒否する

**何を**: `SpotInteractionApplicationService`の物体・道具操作と
`PlayerInteractionApplicationService`の対人操作から、factory未配線時に長寿命repositoryと
直接publisherで実行する旧経路を撤去する。

**なぜ**: 本番配線が正しくても直接更新fallbackが残れば、将来の配線漏れでinterior、graph、
inventory、status、world flag、cooldownの一括rollbackと確定後観測を静かに迂回できる。
とくにinteractionは現在のシナリオの中心なので、公開入口を唯一の確定経路へ固定する必要がある。

**どう守るか**:

- 物体・道具・対人の公開更新は、factory未配線ならrepository・publisherへ触れる前に停止する
- 成功eventはscope内の`CommandContextEventPublisher`だけへ収集する
- 物体操作の前提条件拒否だけは、rollback後の確定状態を伝える観測として専用publisherへ渡す
- `CALL_MEETING`はfactory配線を確認した後、通常interaction scopeを開始せず
  `MeetingCommandService`の専用scopeだけで完結する
- 対人interactionでは意味を持たなかった`CALL_MEETING`特例を削除し、通常のscope経路へ統一する
- 構造棚卸しの残存許可表を空にし、両serviceをscope必須表へ移す

**関連**: #1094 / #1244 / 判断 #117 / 判断 #166 / 判断 #167 / 判断 #197。

## 206. #1244完了後は任意の確定区間fallbackを認めない

**何を**: 本番commandの旧確定経路を撤去した最終状態を、全出荷シナリオの実構築試験と
ASTによる構造棚卸しの二層で固定する。

**なぜ**: 個別serviceの試験だけでは、シナリオ条件によって生成されるstageの配線漏れや、
新しい更新serviceを許可表へ分類し忘れる静かな失敗を検出できない。一方、実構築だけでは
未使用の旧clientや直接構築fallbackの再導入を検出できないため、両方が必要である。

**どう守るか**:

- `data/scenarios/*.json`を列挙し、各runtimeに存在する更新service・stageのfactory接続を検査する
- `use_item`、`tend_to_player`、`prepare_action`のruntime所有factoryも同じ試験で検査する
- application全体のscope factory所有moduleを必須経路表と双方向比較する
- 任意fallback許可表は空集合を明示的な契約とし、再導入には設計判断の更新を要求する
- 旧`UnitOfWork` client 39ファイルは未接続library面として固定し、本番compositionからの
  構築をAST import graphで禁止する

**関連**: #1094 / #1244 / 判断 #153 / 判断 #197 / 判断 #205。

## 207. gold を減らす効果は、前提条件とのペアを読み込みで強制する

**何を**: `DEPOSIT_GOLD_TO_OBJECT` (行為者の gold を object.state の累積値へ
移す効果) を持つ interaction は、同じ操作に `PLAYER_GOLD_AT_LEAST` の
`gold_threshold` が納める総額以上で書かれていないと `ScenarioLoadError` に
なる。

**なぜ**: 支払いは application 層が効果の適用後に行う。前提条件で額を受け
止めないと「カウンタは保存されたのに払えない」という部分成功 (= 金銭が動く
ツールは部分成功なし、の違反) が宣言だけで作れてしまう。宣言だけで成立する
規則は run ではなく読み込みで止める (#1225 / #1227 と同じ向き)。

**なぜ item (DEPOSIT_ITEM_TO_OBJECT) には同じ強制が無いか**: 品物の減算は
効果内で予約数と加算数を同じ値から作るうえ、実際の除去可否は永続化前の
runtime ガード (`_require_removable_items`) が全量を検査する。gold には
「予約」に相当する中間状態が無いので、静的なペアで先に受け止める。

**支払いの適用位置**: カウンタの保存 (interior save) の直後、ダメージ等の
後段より前。かつ**後段も保存する同じ集約インスタンスに対して**行う — repo は
clone を返すので、別インスタンスで払うと後段の保存が支払いを打ち消す。

**凍結との関係**: `PLAYER_GOLD_AT_LEAST` は生の所持金を見る。同席取引に
出して凍結中の gold は素通りするため、永続化の前に `available_gold`
(凍結差し引き、TradeFreezeService の規約) の第二ガードを通す。板 (#1265)・
商人と同じ形。

## 208. 意味記憶エントリに経験の主体 BeingId を載せる

**何を**: `SemanticMemoryEntry` に必須フィールド `being_id: BeingId` を追加する。
`player_id` は手番の身体として残す。store の一次キーと VO の `being_id` が
食い違う書き込みは `add_by_being` / `replace_all_by_being` /
`supersede_by_being` で失敗する。

**なぜ**: semantic store は既に Being 単位のキーなのに、葉の記録は
`player_id` だけを持ち、経験の主体が永続化の面から消えていた。#174 の
主観エピソード / #177 の記憶リンクと同じ型を `SemanticMemoryEntry` に載せる。
`EpisodicSemanticClusterPromotionService` と
`BeliefConsolidationCoordinator` は呼び出し側の `being_id` を VO に刻む。

**旧データ**: snapshot payload に `being_id` キーが無い行は、restore 時の
snapshot Being から復元する。payload と fallback の両方があり不一致なら
失敗する (黙って片方を採用しない)。SQLite 行は既存の `being_id_value` 列から
VO に復元する (スキーマ変更は不要)。

**この PR で触らない**: `MemoryLink` / `SubjectiveEpisode.player_id` の削除、
再解釈 / 想起観測 / Goal / L4 / L5 の `player_id`、`on_after_tool_turn` 等の
`being_id` 引数削除、SQLite スキーマ変更。

**その後**: `BeliefConsolidationCoordinator` は記憶の部品の撤去 (#1631) の #1790 で消した。いまの profile では、意味記憶エントリを書く部品は動かない。

クラスタ昇格と gist (`SEMANTIC_LLM_GIST_ENABLED`) も #1792 で消したので、意味記憶エントリを書く部品は無くなった。意味記憶の store は続く PR で消す。

意味記憶エントリ (`SemanticMemoryEntry`) と、その store・Being の snapshot のキー `semantic_entries` / `semantic_cluster_signatures` は #1794 で消した。消す前の snapshot も読める。

## 209. 再解釈エントリに経験の主体 BeingId を載せる

**何を**: `EpisodicReinterpretationEntry` に必須フィールド `being_id: BeingId`
を追加する。`player_id` は手番の身体として残す。store の一次キーと VO の
`being_id` が食い違う書き込みは `put_active_by_being` / `replace_all_by_being`
で失敗する。

**なぜ**: journal store は既に Being 単位のキーなのに、葉の記録は
`player_id` だけを持ち、経験の主体が永続化の面から消えていた。#174 の
主観エピソード / #177 の記憶リンクと同じ型を載せる。
`EpisodicReinterpretationCoordinator._apply_updates` は呼び出し側の
`being_id` を VO に刻む。

**旧データ**: snapshot payload に `being_id` キーが無い行は、restore 時の
snapshot Being から復元する。payload と fallback の両方があり不一致なら
失敗する (黙って片方を採用しない)。SQLite の `payload_json` も同契約で、
キー無しは store 行の `being_id_value` から fallback する (スキーマ変更は不要)。

**この PR で触らない**: `EpisodicRecallObservation` への being_id 載せ、
`SubjectiveEpisode.player_id` 削除、Goal / L4 / L5。

**その後**: 再解釈の coordinator (`EpisodicReinterpretationCoordinator`、`LLM_EPISODIC_REINTERPRETATION_ENABLED`) は Issue #1631 で消した。想起の記録と再解釈エントリの保存先、値の型、Being の snapshot のキー `recall_buffer_pending` / `reinterpretation_journal` も、続く PR で消した。消す前の snapshot も読める。

## 210. 履歴には、次に真似しても通る形だけを残す

**何を**: resolver が崩れた表記 (quote つきラベル、表示行の丸ごとコピー) を
救って成功させたとき、行動履歴 (`identifier_arguments`) には**生の入力ではなく
解決に使った正規値**を残す。resolver は `canonical_identifiers()` で「生値と
違う識別値」だけを集め、`_with_inner_thought(canonical=...)` で出力に載せる。
dispatch が回収して履歴の射影に反映し、**generic 経路 (do_* を通らない tool)
にも同じ射影を届ける**。

**なぜ**: 救済と履歴は対で設計しないと崩れが増える。供物競争 run では、quote
つきの `destination_label` が resolver に救われて成功し、その生値が履歴に
積まれ、以降ずっと同じ崩れた形で送られ続けた。**成功例として見えるものが、
次のターンの手本になる。**

**救済の範囲**: 表示を写したときの表記の崩れだけ。表示に無い名前の発明 (65 run で 111 件の
主因) は救わない — 対象の `available_interactions` に一致した候補だけを採り、
外れたら従来どおり「その操作はありません + 利用可能な一覧」で失敗させる。
救うと「適当に書いても通る」を教えることになる。

**raw args は変更しない**。入力 dict は fingerprint と行動要約のフォールバック
表示にも使われるので、内部キーを混ぜると別の場所へ漏れる。

## 211. wall-time cap は呼び出し元を実際に解放しないと意味がない

**何を**: `_call_with_wall_cap` の `ThreadPoolExecutor` を `with` で囲まない。
`finally` で `shutdown(wait=False)` する。

**なぜ**: `with` の退出は `shutdown(wait=True)` なので、cap で例外を投げても
下位 call の完了までブロックする。「hard cap」と名乗りながら待ち時間を 1 秒も
縮めていなかった (実測: cap 0.5s / call 3s で、例外は 0.5s・退出は 3.0s)。
供物競争 run では 13 件がこれで待ち切り、run 時間の 16% を占めていた。

**テストの教訓**: 既存テストは「cap で例外が出るか」しか見ておらず、この欠陥を
素通りさせていた。**時間で守る性質は、時間を測って固定する。**

## 212. 交換比率が判定に効く世界でないと、値段の話は始まらない

**何を**: 敵対する 2 組に**非対称な供物**を課す。供物競争 v2 は東が薬草 4 + 45G、
西が麦束 3 + 60G で、必要量も gold も揃えない。産物は組で分かれていて、自組の
産物は自分の祭壇に納められない。

**なぜ**: v2 の初版は両組に同じ供物を課していた。この形だと**1:1 交換が判定に
中立**で、交換しても勝敗が動かない。エージェントは交換の必要を認めるが、比率を
考える理由がどこにも無いので、永遠に引き分けに向かう。

非対称にしたあとの run (`offering_race_v2_second`) の t78、セラ (西) の発話。

> 交換レートは 1 対 1……いや、麦束 1 本につき薬草 1 本＋10G でどうだ？ お前たちは
> 薬草が 4 本と 45G 必要だ。こっちは麦束 3 本と 60G が必要だ。計算が合うだろ

**両組の必要量を突き合わせて 1:1 が不利だと判断し、gold を上乗せしている。**

**根拠の限界**: 対称版 v2 の run は無い (欠陥は run 前のレビューで見つけたので、
回さずに直した)。対称なのは v1 (`offering_race_first`) だけで、こちらは供物構成も
gold の必要額も違い、**自組の産物を自分の祭壇に納められる**。「対称性だけが違う
2 本」の比較ではない。言えるのは、v1 の speak 全 7 件に比率・価格の対案が 0 件で、
非対称版で初めて出たこと。さらに非対称版でも v2 初回 run にはこの型の発話が無く、
**観測は 1 件**である。

**教訓**: 「取引が要る」だけでは値付けは生まれない。**取引の条件が結果を変える**
ことまで作らないと、交渉は「交換しよう」で止まる。仮説として扱い、次の run で
同じ型が出るかを見る。

## 213. 世界の刻限はシナリオが持つ。`max_world_ticks` はループの上限でしかない

**何を**: run 長を変えるときは、**シナリオの `game_end_conditions.lose.TICK_LIMIT`**
と、それに紐づく `scenario_events` の `TICK_AT_LEAST` (判定発火) を動かす。profile の
`max_world_ticks` は同じ値に揃える。

**なぜ**: `run_scenario_experiment.py` は毎 tick `check_game_end()` を見て break する。
`max_world_ticks` は**ループが回れる上限**で、世界を延ばす手ではない。エージェント
に見える「残り行動可能 tick」も `TICK_LIMIT` から作られる。

供物競争 v2 の run 長を 80 → 140 にしようとして、**profile だけ書き換えた**。run は
t80 で終わり、プロンプトの残り時間も 80 のままになる。**値を書いたのに何も起きない**
形の静かな失敗で、レビューで指摘されるまで気づかなかった。

**揃っていないと 2 方向に壊れる**。profile が短いと判定 tick に届かず勝敗が付かない。
profile が長いと余りが空回りする。

**構造で守る**:

1. `test_the_loop_cap_matches_the_scenario_deadline` — profile の `max_world_ticks` と
   シナリオの `TICK_LIMIT` の一致を固定する
2. `test_the_judgment_compares_enemy_produce_then_gold` — 判定 tick を `TICK_LIMIT - 1`
   から導く。刻限だけ動かすと落ちる
3. `test_the_metadata_names_the_real_deadline` — `metadata.description` と
   `estimated_ticks` が名乗る刻限を `TICK_LIMIT` に固定する。**エージェントはこの
   数字を読まない** (`description` はネタバレを含むので LLM へ渡さず、`llm_public_intro`
   / `llm_objective_text` は「刻限までに」と書いて数字を持たない)。守るのは人間側の
   読み物で、run の条件を誤って読まないため。実際に刻限を 140 にした変更で両方
   80 のまま置いていかれた

**窮乏は run 長に依らない**: 供物競争の窮乏は gold 側 (総量 80G 固定に対し必要 105G)
に寄せてある。材料は再生するので run を伸ばせば収穫は増えるが、**gold の総量は動か
ない**ので取引の必然性は緩まない。伸ばすときにここを再設計する必要はない。

**天候の通知が増える**: `update_interval_ticks: 30` は run 長に対する比率が変わるので、
天候変化は約 2 回から約 4 回になる。通知は `schedules_turn=True` で全員の手番を起こす
ので、**全体で 2 回ぶん手番が天候に食われる**。行動密度を数えるときの分母に入る。

**ただし空腹は run 長に依る**: このシナリオは `needs` を宣言しておらず、既定の
`hunger_per_tick=1` / `starvation_damage_per_tick=0` で走る。t100 前後で空腹が上限に
達し、**食料アイテムが世界に無い**ので最後の 40 tick は全員が空腹限界の身体状態を
読み続ける。HP は減らないが、身体状態が観察に出続けることの影響は分かっていない。
run 長を伸ばすときの既知の副作用として残す。

## 214. 恒久的な LLM 障害は「サーバが名乗る理由」ではなく「治らなさ」で判定する

**何を**: LLM 呼び出しの失敗に対して、**retry は例外の種類で決め、run を止めるかは
連続失敗の回数で決める**。2 つを混ぜない。

| 問い | 答える場所 | 判断材料 |
|---|---|---|
| この呼び出しを再試行するか | `litellm_client._is_retryable_transient_error` | 例外の種類 (429 / 5xx) |
| この run を止めるか | `LlmFailureStreakMonitor` | **retry を尽くした後**の連続失敗数 |

**なぜ**: 供物競争 140 tick run は t47 で OpenRouter のクレジットが尽きた。失敗
74 件のうち **クレジット由来の 68 件はすべて `in_flight_budget_exhausted` を名乗って
いた** (残り 6 件は wall-time cap の Timeout) — OpenRouter の文言では「in-flight が
捌ければ直る」= 一時エラーである。実際は残高 0 で、待っても永久に直らなかった。
**サーバが名乗る理由と、本当に回復するかは一致しない。**

理由で分類して retry を足すのは逆効果でもある。この 68 件を 3 回ずつ retry すると
2+4+8 秒 × 68 = **約 16 分の空回りが増えるだけで、1 件も回復しない**。

**閾値 8 の校正**: `var/runs/` の 68 run で最長連続失敗を数えた。

| | 最長連続失敗 |
|---|---|
| 健全な 65 run | 0〜4 |
| DigitalOcean 速度崩壊 (成功率 12%) | 35 |
| 認証ミス (成功率 0%) | 45 |
| クレジット切れ (成功率 51%) | 64 |

8 は下側に 2 倍 (8 = 2×4)、上側に 4.4 倍 (35/8) の余裕を持って分離する。**過去
68 run に対して誤検知 0・見逃し 0。** `LLM_FAILURE_STREAK_ABORT` で変更でき、0 で無効。

**件数だけでは足りない**。8 エージェント run は 1 tick に最大 9 件呼ぶので、
「全員が同時に 1 回落ちる」だけで閾値に届く。しかも履歴の失敗の主因は wall-time cap
の Timeout (343 件中 168 件) で、**これは retry 対象外なので provider が数十秒遅く
なった瞬間のバーストはそのまま監視に届く**。そこで**連続が 2 つ以上の tick に
またがること**を条件に足した。壊れた 3 本の最初の 8 連続はそれぞれ 4 / 2 / 2 tick に
またがるので、検出は 1 本も失わない。

**1 体だけが恒久的に落ちる場合は守っていない** (context length 超過など)。ただし
他の 7 体が動いていれば成功が挟まって streak が切れるので、連続が伸びる時点で
run 全体が既に止まっている。「2 人以上にまたがること」を足すと 1 人世界で永久に
止まらなくなるので、入れなかった。

**止めた理由は trip した瞬間に凍結する**。並列 Phase A では停止を決めたあとに
遅れて成功が着地し、生のカウンタは 0 に戻る。凍結しないと**止まるのに「0 件連続で
失敗した ()」が report と trace に載る**。

**既存の砦では足りなかった**: `_classify_llm_run_health` は **成功が 0 件**のとき
だけ働く。壊れた 3 本のうち捕まえるのは認証ミス (成功率 0%) の 1 本だけで、
**途中で死んだ run は前半の成功に隠れて通過する**。

**outcome を分ける**: 自ら打ち切った run は `LLM_ABORTED`。`LLM_FAILURE` は
「1 件も成功しなかった」の意味で既に使っているので、混ぜると過去 run の読みが
変わる。どちらも成果物は残し (実験データを守る)、終了コードは 1 を返す。

## 215. 呼び出しの健全さは report の冒頭に出す

**何を**: `report.md` の冒頭の箇条書きに `llm calls: 150 (成功 76 / 51%)` を必ず出す。
失敗があるときだけ error_code の内訳を節にする。

**なぜ**: 140 tick run の report はこう書いていた。

```
- outcome: **LOSE**
- last tick: 140 / max world ticks: 140
| player_id | actions | successes | failures |
| 1         | 20      | 20        | 0        |
```

**呼び出しの半分が落ちたことが 1 文字も出ていない。** しかも `failures` 列は tool の
失敗なので、**呼び出しが届かなかったぶんは行動として数えられず、失敗率が高いほど
report がきれいになる**という逆転があった。`llm_call_count` / `llm_success_count` は
計算されて `RUN_END` trace には載っていたが、**人が最初に開く report.md には
出していなかった**。

`make experiment` の `[done]` 行にも出す。**閾値未満の「じわ荒れ」(319 件中 57 件
落ちて最長連続 2、など) は層 2 では永久に捕まらない**ので、そこはこの 2 か所だけが
砦になる。

**停止 (#214) と両方要る**。停止だけだと閾値未満の run が黙る。可視化だけだと次も
82 tick 空回りする。

## 216. LLM境界ではcommit済み後処理失敗を成功として伝える

**何を**: `CommandPostCommitException`をLLMツール結果へ写すときは、
`success=True`と専用の`COMMAND_COMMITTED_POST_PROCESSING_FAILED`を返す。
messageには「世界へ反映済み」「同じ操作を繰り返さない」を明記し、
`should_reschedule=False`を維持する。

**なぜ**: この例外が示すのは業務失敗ではなく、commit後のcleanup・handoff・outbox
処理の異常である。`SYSTEM_ERROR`へ縮退すると「再度お試しください」という対処が付き、
アイテム消費、準備、介抱、取引、市場注文のような非冪等操作を二重実行させる。
また、Phase Bが失敗と解釈すると、新しい行動のために中断していた移動まで復元し、
確定済み世界状態と行動履歴を食い違わせる。

**どう守るか**:

- `exception_result`が`CommandPostCommitException`を最初に識別し、通常例外の
  sanitizer・`SYSTEM_ERROR`対処へ流さない
- use item、prepare action、tend、対人取引、市場、旧取引画面の各入口で
  成功・業務拒否・commit前例外・commit後例外を分けて試験する
- Phase Bにも最終防御を置き、個別executorが例外を上位へ通しても成功を維持する
- traceにはcleanup・handoff・outboxのどこで失敗したかを例外型だけで残し、
  内部messageはLLMへ渡さない

**関連**: #1094 / #1245 / 判断 #149 / 判断 #153 / 判断 #155。

## 217. 他者の発言で起こすかは、判断の前に規則で守ってから判断に問う

**何を**: 1 人の発言が、その場で聞いた全員を次の tick に起こしていた。会議では
8 人が毎 tick 全員喋る形になる。聞いた一人ひとりについて「この発言に自分が
返答する必要があるか」を型付き判断 (Noul) に問い、確率が閾値
(`TYPED_JUDGMENT_REPLY_GATE_SKIP_BELOW`、既定 0.15) 未満のときだけ起こさない。
`ObservationTurnScheduler` に `IWakeGate` を挟み、`schedules_turn` を「起床候補」
と読み替える。formatter は触らない。

**なぜこの形か**:

- 落とすのは低確率側だけ。取りこぼし (返答すべき人を起こさない) は静かな失敗
  になるので、閾値は小さく置き、run の会話を読んでから動かす。
- 判断に委ねると壊れるものは、判断の前に規則で守る。囁き、本文に自分の名前が
  ある発言、一定 tick 発言していない聞き手 (`..._SILENCE_TICKS`、既定 3) は
  判断を引かずに起こす。実データでは宛先つき質問の 64% で、宛先が同じ tick
  に喋っていた。ここを判断に任せると「呼ばれても答えない」が trace から
  見えない形で起きる。
- `player_spoke` 以外の観測は起動判定の対象外。投票の要求など返答が要る観測は別の
  型で届くので、構造的に抑制されない。
- 起こさなくても観測は buffer に残る。appender が scheduler より先に走る
  (#29 と同じく、観測を捨てて状態を軽くしない)。
- 判断が得られなければ起こす側へ倒し、`unavailable_reason` を残す。

**trace**: `TYPED_JUDGMENT` の `question=speech_reply_needed` に、聞き手ごとに
1 件。判定で起こした分も、起こさなかった分も残す。`reason` (`whispered_to_me` /
`named_in_speech` / `silence_limit` / `judged_needed` / `judged_unneeded` /
`judgment_unavailable`)、`probability`、`skip_below`、`woke`、`latency_ms`、
`source` を持つ。残さないと、起動判定の無い run と全件起こした run が見分けられない。

**閾値の経緯**: 0.05 で始めた。Gemma と deepseek (StreamLake) の 2 run、約 650 件
で Jev の最小値は 0.10 で 1 件も落ちなかった。0.15 未満の 87 件を全部読むと、
「気象記録、転記しておく」のような作業の宣言と、通路の向こうから聞こえる他人
宛ての指示だけだった。低確率で次 tick に喋った聞き手は全員、別の観測 (燃料凍結
の警報) に反応していた。取りこぼしが読み取れなかったので 0.15 へ上げた。答えを
求める発言は 0.6〜0.9 に付いている。

**その後 (run 005)**: 会議を含む run で読むと、判断の中身は妥当だったが
**会議の LLM 呼び出しは 1 件も減らなかった**。1 tick に 7 件の発言が届く場では、
7 件すべてが閾値未満でないと起動を止められない。発言単位の起動判定は会議に効かないので、
tick 単位の起動判定 (#219) に置き換えた。判断の付き方 (作業の宣言と他人宛ての指示は
0.1 前後、答えを求める発言は 0.6〜0.9) はそのまま #219 の閾値の根拠になる。
いまは常時有効で、`TYPED_JUDGMENT_REPLY_GATE_ENABLED=0` で判断ポートを残した
まま起動判定だけ外せる。

**どこで出てきたか**: Jev (#1319) の 3 つ目の用途。観察 profile は
`station_drill_reply_gate`。

観察 profile の `station_drill_reply_gate` と `station_drill_gemma_reply_gate` は、観察する仕組みが無くなったので #1693 で退役させた (#1631)。

## 218. 二人で合わせる操作の入口は interact に統合する

**何を**: 同期グループ (`synchronized_action_groups`) の required action を
`interact` に渡すと、その操作の効果を起こさず「自分の側を受け持った」と登録する。
専用ツール `prepare_action` は消す。登録層 (`prepared:` / `sync_prep:` の 2 フラグを
CommandScope で確定し、同室者に観測を出す) と tick 終わりの窓判定は変えない
(#74 / #195)。準備対象の interaction に `effects` を書くと読み込みで落とす。

**なぜこの形か**:

- 実データで別の動詞は選ばれなかった。station_drill の 13 run で `prepare_action`
  は 0 回。run 003 で弁を触った 5 回は全部 `interact` だった。世界は「レバーに
  手をかけた」と返しながら何も登録しておらず、tick 11 に両方の弁が揃っていたのに
  燃料が失われた。
- 勘違いの原因はツール名ではなく**操作名の出所**にあった。準備対象の操作は
  対象行に `[解氷弁を開く準備をする → "open_thaw_valve"]` と他の操作と同じ書式で
  出る。`interact` は「対象行の名前は私に渡せ」と言い、`prepare_action` の
  action_name の説明は `interact` と一字一句同じだった。2 つの動詞が同じ名前を
  取り合い、毎ターン使う側が勝つ。
- 準備は「効果が遅延し、相方が揃うことを条件にした interact」で、エージェントが
  区別して得るものがない。区別は世界の側の都合なので、世界の側で吸収する。
- 判断 #74 が「準備は現在地に同名の interaction を持つ対象物が無いと登録しない」
  と決めた時点で、interaction 定義は名前と前提条件の土台として必須になった。
  土台を `interact` から実行可能に残すと、今回の飾りの成功が生まれる。だから
  土台には `effects` を書けなくし、`interact` は名前を見て登録層へ回す。

**どうしないと壊れるか**: 別ツールのまま「使わせる工夫」(表示の区別、interact
の拒否、説明文の書き直し) をしても、interact を拒否する形は期限つきの場面で
1 tick を失い、拒否しない形は結局この統合になる。

**関連**: #74 / #195 / #66 (表示されていない名前を指定させない) / #126 (言葉が
自然に書ける形を世界が受け取る)。run 003 (`station_drill_reply_gate_003`)。


## 219. 起こすかは観測 1 件ごとでなく、tick の終わりに本人の未読をまとめて問う

**何を**: `run_scheduled_turns` が pending の各人を回す直前に、その人の buffer に
溜まった未読の観測をまとめて渡し、「いま自分が動く (発言を含む) 必要があるか」を
Noul で 1 回問う (`TurnGate`、trace は `TYPED_JUDGMENT` の `question=turn_needed`)。
確率が `TYPED_JUDGMENT_TURN_GATE_SKIP_BELOW` (既定 0.15) 未満なら回さない。観測は
buffer に残り、次に起きたときに読める。発言単位の起動判定 (#217) は外した。

**なぜこの形か**:

- 会議では 1 tick に 7 件の発言が届く。観測 1 件ごとに問う形では 7 件すべてが
  不要と判定されないと寝られず、run 005 では 1 件も減らなかった。本人の状況を
  まとめて 1 回問えば、Jev の呼び出しも 1 tick 最大 8 回 (49 回から) に減る。
- 「この発言に返答するか」は聞き手の側の話で、「いま動くか」は本人の意思の話。
  keeper が「今は黙って様子を見る」のも正しい答えになる。エージェントの注意は
  観測型ごとの真偽 (`schedules_turn`) より、この問いに近い。
- 判断の前の規則は既存の `observation_category` で書ける。`self_only` (被ダメージ、
  所持品、行動失敗) と `environment` (警報、フェーズ変化、投票の要求) が 1 件でも
  あれば判断を引かずに回す。対象は `social` だけが溜まった人。囁き、名指し、
  沈黙の上限 (`..._SILENCE_TICKS`、既定 3)、未読なし (自己 reschedule) も回す。
- **会議中は候補の中で少なくとも 1 人を回す** (`meeting_floor`)。会議は沈黙が
  続くと「話し合いは流れた」で終わる。起動判定のせいで流れた会議は、議論が尽きて
  流れた会議と trace 上で見分けられない。

**どうしないと壊れるか**: 発言単位のまま閾値を上げても、会議では別の発言で
起こされるので効かない。会議中の 1 人保証を忘れると、起動判定が会議を静かに終わらせる。

**結果 (run `station_drill_turn_gate_001`)**: 27 tick、会議 2 回で、起動判定の決定 197 件の
うち起動しなかった人は 0。内訳は名指し 100、本人・世界の観測あり 42、Jev に問った 42
(確率は最小 0.18、中央値 0.42)、その他 13。会議中に名指しで届いた発言 170 件の
83% は疑問符付きの本人宛ての質問だった。

**station_drill では、この判定で LLM 呼び出しは減らない。** 会議は「返答の要らない
人まで起きている」場ではなく、全員が名指しで質問され答える義務を負っている場で、
会議の外も 8 人全員が毎 tick 点検や移動をしている。発言単位 (#217) は分解能が
細かすぎて効かず、tick 単位は正しく「全員起きるべき」と言っている。当初の仮説
「会議は起床の無駄が大きい」は、このシナリオには当てはまらなかった。

起動判定は残す。判定の前に守る条件、trace、会議の 1 人保証は壊れておらず、「全員起こすべき
だった」と trace で読めることに価値がある。費用を削る手段としては station_drill
では追わない。名指しでない雑談や独り言が多い世界 (survival_island、market_town)
で効くかは別の観察課題として残す。Gemma の run では 0.15 未満が 44 件あった。

**関連**: #217 / #404 (schedules_turn の網羅性監査)。


## 220. 起動判定は規則で素通しさせず、pending の全員を Jev に問う

**何を**: tick 単位の起動判定 (#219) から、判断の前に置いていた規則 (self_only /
environment の観測があれば回す、囁き、名指し、沈黙の上限、会議中の 1 人保証) を
すべて外す。pending の全員について未読の観測をまとめて Jev に問い、「本当に不要」
と判定できた人だけ回さない。囁き・名指し・警報は判断を飛ばす規則ではなく、state に
分類の見出し付きで渡す材料にする。唯一の例外は未読の観測が無い人で、判断の材料が
無いのでそのまま回す。設定キー `TYPED_JUDGMENT_TURN_GATE_SILENCE_TICKS` は消す。
成功した自分の行動のあとに回した人も、判定にかけずに通す (2026-10-12 追記、
design_decisions D1597)。自分の行動の結果は判定の材料に入らないため。

**なぜこの形か**:

- 目的は「普通は毎回起動するところに Jev を挟み、本当に不要な場合だけ行動しない」
  こと。起こす経路は 1 つも足さず、起動判定は pending を減らすだけにする。
- 規則が判断の出番を奪うと、フィルタとしての Jev を評価できない。run
  `station_drill_turn_gate_001` では 197 件中 155 件が Jev に届く前に規則で通り、
  会議で起動判定が効かない原因は名指しの規則だった。名指しの質問に答えるべきかどうかも
  Jev の判断に含める。
- 引き継ぎの「自分宛ては必ず起こす」「沈黙の上限」は取りこぼしを防ぐ保険だった。
  保険を規則で置く代わりに、閾値を低く置き (0.15)、取りこぼしが起きるかを run で
  読む。起きたら閾値を下げる。
- 会議の 1 人保証も外す。起動判定のせいで会議が流れるなら、それは trace の
  `turn_needed` (全員 `judged_unneeded`) で読める。

**関連**: #217 / #219。


## 221. 起動判定の候補は pending の人ではなく、未読の観測がある人全員

**何を**: tick 単位の起動判定 (#219 / #220) の候補を、「その tick に `schedules_turn` の
観測を受けて pending に入った人」から「未読の観測が 1 件でもある LLM プレイヤー
全員」に広げる。pending の人はそのまま候補に残り、順序は pending が先。前の tick に
寝た人は、新しい観測が届かなくても溜まった未読を見て毎 tick 判断し直される。
trace の `turn_needed` に `scheduled` (pending に居たか) を足す。

**なぜこの形か**:

- 目的は「普通は毎回起動するところに Jev を挟む」こと。候補を pending に限ると、
  formatter が観測型ごとに付けた `schedules_turn` の真偽が候補の入口を決め、その
  後で Jev がふるう二段構えになる。未読があれば毎 tick 判断する形なら、Jev が
  観測の中身を見て決める一段になる。
- `schedules_turn` の網羅性を作者が守り続ける必要 (#404 の監査) が薄くなる。
  付け忘れた観測型でも、未読として Jev の目に入る。
- 溜まった未読が増えるほど確率は上がりやすく、「そろそろ動くべき」の自然な圧力に
  なる。heartbeat も未読の 1 件として同じ経路で扱われる。
- 蓄積と drain は変えない。観測は届いた時点で buffer に積まれ、ターンが回ると
  prompt 構築が drain して LLM に渡す。回らなければ残る。

**代償**: Jev の呼び出しは pending の人数から未読のある人数に増える (station_drill
では tick あたり 7.2 → 8 回程度)。

**関連**: #219 / #220 / #404。


## 222. 起動判定は既定で外し、観察するときだけ入れる

**何を**: `TYPED_JUDGMENT_TURN_GATE_ENABLED` の既定を off にする。
`TYPED_JUDGMENT_PROVIDER=jev` にしても起動判定は入らず、行動名の読み替えと memo の判定
だけが動く。起動判定のコード (#219〜#221) は残し、観察するときだけ明示的に true にする。

**なぜこの形か**: station_drill の 4 run (`turn_gate_001`〜`004`) で分かったこと。

- Jev の判定は正確だった。名指しの質問や囁きを起動しなかった誤りは、trace に残した
  本文で確かめた範囲で 0 件。会議は全員起こし、通路越しの他人の作業報告だけの人は
  起動しない。
- 問題は問いの形にある。「届いた観測を受けて動く必要があるか」は反応の問いで、
  本人のやるべき仕事の残りを見ない。run 004 では crew の大半が tick 9〜38 の 30 tick
  を寝て過ごし、点検は 50 tick で 10 件 (勝利条件 12 件) にとどまった。本人の目的を
  材料に足せば直る可能性はあるが、足していくと起動判定が LLM のターンを先取りする
  2 つ目の小さなエージェントになる。
- 費用の非対称が大きい。余計に起きる代償は数円で、起きるべき時に寝る代償は物語が
  止まることで、後者は run が終わるまで気づきにくい。

**この用途で Jev が向く方向**: 「起こさない」ではなく「起こす」側の補助。
`schedules_turn=False` の観測から「これは起こすべき」を拾うなら、外しても現状維持で、
当たれば得しかない。

**関連**: #217 / #219 / #220 / #221。

起動判定 (`TurnGate`、`TYPED_JUDGMENT_TURN_GATE_ENABLED` / `_SKIP_BELOW`) は、どの profile も入れていなかったので、記憶ではない設定の片付け (#1631) の #1692 で消した。219〜222 は判断の記録として残す。

## 223. 行動名の意味による救済を semantic-resolver へ委譲する

**何を**: `ActionNameRescue` から `SemanticResolver.resolve` を呼び、対象ごとの
操作名と意味ラベル、元の入力、対象名、直前の思考を渡す。候補の検査と解決結果の
組み立てをライブラリへ委譲し、ゲーム側で呼ぶタイミングと trace への変換を担う。
ツールスキーマは変更せず、動的候補は判断時にだけ渡す。判断 #1 の
プレフィックスキャッシュと、判断 #37 の候補集合を維持する。

**なぜこの接続か**: 既存の `ITypedJudgmentPort` をライブラリの `Backend` 契約へ
適合させる。Jev の通信・再試行・設定・stub は引き続き既存ポートを使う。
ライブラリ付属の `JevPolicy` は確信度を必須とするが、既存の行動名救済は
確信度が省略された回答を確率だけで評価する。そのためゲーム側に専用の
`Policy` を置き、確率と、省略されていない確信度が閾値以上なら採用する。
閾値と等しい場合も採用する。新しい採用モードは今回追加しない。

**保つこと**: 完全一致・表示の正規化で解決した名前や候補のない対象は判断しない。
`__no_match__` は常に選択肢に含める。採用・確信不足・該当なしの証拠と通信障害の
理由を既存の trace に残す。置換の通知と履歴上の正式名も従来どおりにする。

**入口で明確化すること**: 空の入力は判断せず元の失敗経路へ返す。説明がない候補は
操作名を説明に使う。候補外の回答や該当なしの予約値との衝突は `invalid_response`
として記録し、該当なしと区別する。回答欠落は従来の `ANSWER_MISSING` を維持する。

**依存の再現性**: まだ PyPI 公開前なので、`tool.uv.sources` と `uv.lock` で
公開 GitHub のマージ済みコミット `f164e0973c0cb6aa59aaa75837107f2a962b4d08` に
固定する。ローカルの隣接ディレクトリや未マージのデモ用ブランチには依存しない。

**どう守るか**: 救済・通知・trace・設定・セッションへの接続・通信アダプタ・履歴・
snapshot の回帰試験を実行する。候補の入れ替わり、閾値境界、確信度や確率の欠落、
該当なしの証拠、候補外の回答、予約値の衝突、空の入力を追加で確認する。

## 224. 効かない引数は残さず消し、並び順は契約として試験で固定する

**何を**: `PostRepository.find_by_user_ids` の `sort_by` を、インタフェースと
2 つの実装から消す。並び順は「作成日時の降順、同じならば `post_id` の降順」に
固定し、インタフェースのドックストリングへ書く。

**なぜ消すのか**: `sort_by: str = "created_at"` はどの値を渡しても同じ順序を
返していた。指定できるように見えて効かない引数は、無いより悪い。既定値以外で
渡している呼び出し元は無く、どのキーが要るかも決まっていない。要件が無いまま
他のソートキーを実装すると、使われない分岐と試験が増える。必要になった時点で、
そのときの要件に合わせて足す。その際は受け付けるキーを列挙型で閉じ、文字列を
そのまま `ORDER BY` へ渡さない。

**並び順のずれ**: SQLite 実装は `post_id DESC` で同時刻を解決していたが、
インメモリ実装は `created_at` だけで安定ソートしていたため、同時刻では挿入順
(実質 `post_id` の昇順) になっていた。同じ入力に対して 2 実装が違う順序を返す
のは静かな失敗になる。インメモリ側を `(created_at, post_id)` の降順へ揃える。

**どう守るか**: 2 実装が共有する契約試験へ、作成日時の降順と、同時刻を
`post_id` の降順で返すことを確かめる試験を足す。後者はインメモリ実装だけが
落ちることを確認してから直した。

## 225. リポジトリの取得系はドメインの型を返し、実装ごとに変えない

**何を**: `ItemSpecRepository` の取得系は、全実装で `ItemSpec` を返す。読み取り用の
`ItemSpecReadModel` は返さない。インメモリ実装も内部で `ItemSpec` を保持する。

**なぜこの形か**: インタフェースは `ReadRepository[ItemSpec, ItemSpecId]` を継承して
`ItemSpec` を返すと宣言していたのに、インメモリ実装だけが読み取り用の型を返していた。
呼び出し側は読み取り用の型にしか無い `to_item_spec()` を前提にしていたため、SQLite
配線では `AttributeError` になる。テストがインメモリ実装しか使っていなかったので、
この不整合は mypy を入れるまで見えていなかった (Issue #1364)。

契約の側を曲げてインタフェースを `ItemSpecReadModel` にする案もあった。採らなかった
理由は 2 つ。`ItemSpecRepository` は `domain/item/repository` にあり、ドメインの型を
返すのが層の役割に合う。そして調査の結果、`to_item_spec()` を呼ぶ 7 箇所すべてが
受け取った直後に `ItemSpec` へ変換しており、読み取り用の型に固有の値を使っている
呼び出し側は 1 つも無かった。読み取り用の型を返す形を恒久化する根拠が無い。

**副作用として受け入れたこと**: `ItemSpec` は frozen で `__post_init__` が不変条件を
検証する。読み取り用の型は素の dataclass で検証が無かったため、これまで無検証で
spec を投入していた経路 (scenario 投入、テストデータ) にも検証が効くようになる。
これは望ましい方向なので、この変更で受け止めた。

**どう守るか**: 2 実装に同じ ID と条件を与えて、取得系 7 メソッドすべてが `ItemSpec`
を返すことを確かめる契約試験を置く (`tests/infrastructure/repository/`
`test_item_spec_repository_contract.py`)。この試験が無かったことが、不整合が長く
残った直接の原因にあたる。

**同じ形を作らないために**: mypy の対象は `src` だけで、テストは見ていない。実装の
戻り値を直しても、テストが古い型を投入し続ければ契約は実際には効かず、緑のまま
空振りになる。リポジトリの契約を変えたら、投入側のテストも合わせて変える。

## 226. 値オブジェクトの定義はコードベースに 1 つだけ置く

**何を**: `item_template_id.py` に残っていた 2 つめの `ItemSpecId` を消し、定義を
`item_spec_id.py` の 1 つに畳む。両者は同じコミットで追加され、例外メッセージの
文言以外は同一だった。「テンプレート ID」という別概念のための型ではない。

**なぜ消すか**: frozen dataclass の等価比較はクラスが一致しないと `False` を返す。
同名で中身も同じ値オブジェクトが 2 つあると、`ItemSpecId(1) == ItemSpecId(1)` が
黙って偽になる。dict のキーや集合の要素として混ざっても例外は出ず、一致しないまま
処理が進む。静かな失敗であり、import 元を見なければ気付けない。

**どう見つかったか**: mypy strict の導入まで見えていなかった。#1332 で
`spot_interaction_application_service` に `TYPE_CHECKING` import を足したとき、
ファイル名 `item_template_id.py` とクラス名 `ItemSpecId` のずれが選び間違いを誘い、
型検査が食い違いを報告した。import は直したが、同名クラスが 2 つある状態は残っていた。

**保つこと**: `ItemSpecId` の定義はコードベースに 1 つだけ。ファイル名とクラス名を
ずらさない。ずれていると、import 補完の候補に 2 つ並んだとき正しい方を選ぶ根拠が
読み手に無くなる。


## 227. 対象の名前も、候補に当たらなければ意味で選び直す

**何を**: `interact` の `target_label` が候補 (この場所の物・人・手持ちの品) に
当たらなかったとき、行動名の救済 (#1321、semantic-resolver) と同じ口で Jev に
問い、確信があれば置き換える。`TargetLabelRescue`、trace は `TYPED_JUDGMENT` の
`question=target_label_rescue`、置き換えたときは結果文の先頭で「「East Shrine」は
「東の祭壇」と解釈した。」と当人に見せる。閾値は行動名より高い 0.85
(`TYPED_JUDGMENT_TARGET_LABEL_MIN_CONFIDENCE`)。

**なぜこの形か**: 過去 65 run の `INVALID_TARGET_LABEL` 212 件を
`scripts/jev_target_label_rescue_demo.py` で測った。暗くて見えない 32 件と候補が
無い 109 件は対象外。候補があった 70 件を Jev に問うと:

- 正しく置き換えた 5 件: 「East Shrine」「东の祭壇」→ 東の祭壇、「漂着物」→ 波が運んだ
  漂着物、「貝」→ 貝の岩棚 (2 件)。いずれも確率 0.93 以上、確信 0.89 以上
- 正しく「該当なし」と言った 58 件: 「大型カニ」に「貝の岩棚」、「発電機」に
  「当番表 / 隔壁盤」、人の名前に流木や船倉。0.95 以上で断っている
- 誤って置き換えた 4 件: 「古い手記 (前半)」→ 岩肌の刻み跡 / 朽ちた机。手持ちの品を
  対象物の一覧から選ばせた型で、確率 0.83〜0.99。これは当時 `interact` が手持ちの
  品を対象に取れなかったことによる。いまは `inventory_item` も候補に入り、名前が
  そのまま当たるので Jev は呼ばれない
- 入れ替え対照 70 件で何かを選んだのは 2 件で、どちらも上の 2 つの型

救える件数は 5 / 212 と少ないが、費用は失敗したときだけの Jev 1 回で、置き換える
べきでない場面を置き換えた例は対照で確かめた範囲で無い。1 tick の損が数件消えるなら
得しかない。

**問わない場面**: 名前が候補に当たった、候補が空、種別違い (`INVALID_TARGET_KIND`)、
曖昧 (`AMBIGUOUS_TARGET_LABEL`)。名前の問題でないものは問わない。

**関連**: #1321 / #66 / #218。

---

## 228. 在るのに種類が違う名前は「無い」と言わず、種類と使うツールを添えて返す

**何を**: 対象の名前を引く resolver を、表示名で 1 回だけ索引を作る
`TargetIndex` (`_argument_resolvers/target_lookup.py`) に載せ替えた。名前 1 つに
つき参照 1 回で「当たり / 曖昧 / 種類違い / 無い」の 4 つが同時に出る。別の種別に
在る名前は `INVALID_TARGET_KIND` で失敗させ、文面は「「大型カニ」はこの場所の敵で、
対象の名前には使えません。戦うなら attack を使う。有効な対象の名前: 貝の岩棚 / リン」
の形にする。interact / travel_to の専用の失敗組み立て (tool_dispatch) は、この
文面を「見つかりません」で上書きしない。

**なぜこの形か**: 過去 83 run の interact の `INVALID_TARGET_LABEL` 194 件のうち
約 70 件が、敵 (大型カニ・大蛇)、隣の場所 (川の上流・連絡通路)、手持ちの品の
名前を対象に書いたものだった。従来の `resolve_target` は受け付ける種別しか探さず
「候補にありません」と返していたので、当人は「大型カニはいない」と誤解し、同じ
名前を attack や travel_to で試す手を取れなかった。「在るが種類が違う」は規則で
確定できることで、意味で選び直す (#227) 前に弾くべき最大の群でもある。

**「では何が書けるのか」は失わない**: 以前は KIND の文面に候補一覧が付かないことを
理由に、別種別の表示名でも LABEL を返していた (test_resolve_target_unified の旧
docstring)。いまは KIND の文面にも受け付ける種別の候補一覧を必ず添えるので、
その理由は消えた。

**勧めるツール名は露出判断を通す**: 失敗文に載せるツール名は、シナリオが
`disabled_tools` で落としたものを宣伝しない (CLAUDE.md「プロンプト本文にツール名を
書くときは、必ず露出判断を通すこと」)。`SpotGraphArgumentResolver(tool_is_exposed=)`
に `runtime.tool_exposure.is_exposed` を注入し、無効なツールは文面から落として
種別だけを伝える。露出判断を持たない最小配線では全ツールを在るものとして扱う。

**内部ラベル (O1 / P2) は最後の逃げ道としてだけ引く**: プロンプトは名前直書きで、
内部ラベルを出していない (#3)。直近 15 run の引数約 1000 件に内部ラベル形式は
0 件だった。表示名で当たらなかったときだけ辞書のキーでも引く。物とプレイヤーが
同じ表示名を持つときは名前では指せず、`AMBIGUOUS_TARGET_LABEL` の文面で内部
ラベルを案内するのが唯一の出口になるため。辞書のキーそのものは収集・記憶の下書き・
他のツール族の resolver が識別子として使っているので残す。

**同名は最初の 1 件を黙って採らない**: 同じ種別に同名が複数あるときも `AMBIGUOUS_TARGET_LABEL`
で失敗させる。以前の行き先解決は最初の 1 件を黙って採っていたが、行き先を取り違えて
成功として返る方が痛い。プロンプト側は同名を `#N` で区別しているので、通常は起きない。

**関連**: #3 / #227 / #66。

---

## 229. 名前で対象を引く全ツールが、同じ 3 段の入口を通る

**何を**: 対象名の救済 (#227、`TargetLabelRescue`) を `interact` だけでなく、名前で
対象を引く全ツール (use_item / drop_item / pickup_item / give_item の品と相手 /
travel_to) に配線した。resolver 側の入口は `SpotGraphArgumentResolver._resolve_named`
の 1 つで、段は上から順に決まる。

1. 表示名で当たる、別の種別に在る、同名が複数: 規則で確定する (#228)
2. どこにも無く候補が空: 問わずに失敗する
3. どこにも無く候補がある: Jev に「該当なし」を含めて問う

**なぜこの形か**: ミスの型を過去 83 run で分類すると、規則で確定できるのは「種類が
違う」(約 70 件) と「候補が空」だけで、残り (翻訳・異体字・言い換え・発明) は
パターンで網羅しきれない。正規化を頑張り続けるより、規則で確定できるものを先に
弾き、残りを Jev に「該当なし」込みで判断させる方が保守できる。4 ツールの
過去データで救える件は 0〜1 件だが、SLM に切り替えると表記崩れは増え、費用は
「候補があるのに当たらなかった」ときの Jev 1 回だけ。

**判断は列で運ぶ**: `TARGET_LABEL_JUDGMENTS_KEY` は dict の list。give_item は
entry ごとに品と相手の 2 つの名前を引くので、1 回の呼び出しで複数の判断が出る。
entry が該当なしで失敗しても (部分成功)、その判断は列に残って trace に届く。
結果文の注釈は採った判断ぶんを最初のものから順に並べる。

**trace で引き分ける**: payload に `tool` と `argument` (「渡す相手の名前」など)
を足した。1 ツールなら不要だったが、5 ツールになると `question=target_label_rescue`
だけでは何を選び直したか分からない。Jev の state にも同じ 2 つを入れる。

**travel_to の注意**: 隣接していない既知の部屋 (機関室) を書いた失敗が travel_to の
主因で、Jev はこれに「該当なし」と言う。途中の部屋に置き換える誤りは 0.85 の閾値と
「該当なし」の選択肢で抑えるが、本来は「隣接していない」と失敗理由を直すのが筋。
`dark_hidden_object_names` と同じ流儀で既知の部屋名を context に載せるのは別 PR。

**関連**: #227 / #228 / #1321。

---

## 230. 隣接していない既知の場所を行き先に書いたら、「見つからない」ではなく「隣接していない」と返す

**何を**: 現在地でも隣でもない世界の場所の名前を `distant_spot_names` として
snapshot → `ToolRuntimeContextDto` に運び (`dark_hidden_object_names` と同じ流儀で、
プロンプト本文には出さず失敗理由の照合にだけ使う)、travel_to にその名前が書かれたら
`DESTINATION_NOT_ADJACENT`「「機関室」はここと隣接していません。有効な接続先: 通信室 /
連絡通路」で失敗させる。意味で選び直す口 (#229) より先に決め、Jev には問わない。

**なぜこの形か**: travel_to の失敗 51 件 (83 run) のほぼ全部が、目的文や記憶にある
部屋を隣の場所として書いたものだった。「見つかりません」と返すと当人はその部屋が
無いと誤解する。Jev に渡すと「機関室へ行きたいなら途中の連絡通路」と置き換える余地が
あり、当人は注釈を読み飛ばして着いたと思い込みかねない。規則で確定できることは
規則で確定する。

**経路は教えない**: 「行ける場所」を並べるだけで、機関室への経路は返さない。地図は
歩いて知るもので、失敗文が案内板になると探索の質感が消える。書かれた名前の存在を
確かめることになるが、当人が既に書いた名前なので新しい情報は増えない。

**関連**: #228 / #229 / 3 (名前直書き)。

---

## 231. 存在しない tool 名への提案は、そのターンに送った tool から意味で選び、実行はしない

**何を**: `UNSUPPORTED_TOOL` の失敗文にある「もしかして 'X' ですか?」と「現在使える
tool」の一覧を、Phase A で実際に送った `tools_payload` から作る。型付き判断が使える
run では `ToolNameRescue` が「送った tool のどれを意図したか」を `ChoiceQuestion` で
問い、確信が閾値 (`TYPED_JUDGMENT_TOOL_NAME_MIN_CONFIDENCE`、既定 0.7) 以上なら提案を
差し替える。該当なし・閾値未満・判断が得られないときは文字の類似度による提案に戻し、
理由を `TYPED_JUDGMENT` (`question=tool_name_rescue`) に残す。

**なぜ送った一覧からか**: 以前は handler 表の全キーから作っていた。会議中に送った
7 個に対し、`interact` や `attack`、この世界で出していない `memory_*` まで 33 個を
失敗文に並べていた。勧めた名前を呼ぶと、今度は `TOOL_NOT_OFFERED_NOW` で落ちる。
存在しない tool を勧めるのは、無効化しないより悪い (「LLM に出すツールを増やす /
出し分けるとき」と同じ形)。

**なぜ意味で選ぶか**: 過去 89 run の 24 件は typo より発明された名前に寄っていた。
`say` は `speak` の `channel`、`gather` は `interact` に操作名を渡すこと。先頭の単語が
共通しないので類似度では候補が出ない。選択肢の意味には送った説明の 1 行目を使う
(#38)。`inner_thought` を tool 名として送った崩れ (10 件) のために「該当なし」を必ず
入れる。

**なぜ実行しないか**: 別の tool として実行するには引数の写し替えが要り、足りない
引数の扱いが難しい。失敗は失敗のまま返し、提案の中身だけを変える。`suggested` と
同じ player の次の `action` の `tool` を突き合わせれば、提案どおりに呼んだかを数えられる。

**その後**: 閾値と `TYPED_JUDGMENT_TOOL_NAME_MIN_CONFIDENCE` は外した。「該当なし」以外を
選べば、確率によらずその tool を提案する。理由は #234。

**関連**: #1318 / #1413 / #223 (semantic-resolver 経由) / #234。

## 232. ループ警告の文面は、繰り返しの理由の見立てで選ぶ。見立てで警告は消さない

**何を**: ループ警告が発火したとき、警告の出し口 (`LoopWarningEmitter`) が Jev に
`ChoiceQuestion` で繰り返しの理由を 1 回問う (`question=loop_diagnosis`)。選択肢は
達成済み / 状態の取り違え / 前提の欠けた再試行 / 待機 / 返事待ちの再依頼 / 手段の固着 /
該当なし。採れた理由ごとに、本人が読み落としていそうな世界の事実を並べた文面にする
(居場所、前の成功、直近の失敗文、届いている観測の件数、同じ内容を伝えた回数)。
`TYPED_JUDGMENT_LOOP_DIAGNOSIS_ENABLED` の既定は off。

**なぜこの形か**: 今の文面は理由にかかわらず「別の行動を選べ」と命じる。居場所を
取り違えている人に要るのは「もう土手に居る」という事実で、命令ではない。繰り返しを
見つけることはコードで確定できるが、なぜ繰り返しているかは確定できない。Jev に向く
のは後者だけで、件数と tick 差は問わない。

**警告は消さない**: どの理由を選んでも警告は出す。「該当なし」、確信が閾値未満、判断が
得られない、の 3 つは今の順繰りの文面で出し、`fallback_reason` で分ける。「待機」の
見立てで警告を消すと、見立てが外れたときに詰まった人に誰も気づかない (#222 と同じ
非対称)。

**文面に対処のヒントを載せない**: `get_remediation` の文には「別の行動を選んでください」
のような指示が入っている。理由の文面は事実だけで組む。

**材料**: 繰り返した行動、直近 5 件の行動と結果の文 (発言は内容も)、現在地、いま届いて
いる観測。本人の目的は入れない (#222)。渡した state は trace にそのまま残す (判断が
見たものは判断の trace に残す)。

**実 Jev の見立て**: 既存 trace の 4 場面を組み直して問うた
(`scripts/jev_loop_diagnosis_demo.py`)。閾値 0.7 で 2 場面を採り、どちらも当たった
(前提の欠けた再試行 0.99、返事待ちの再依頼 0.79)。残る 2 場面は最上位の理由が事実に
合っていたが閾値未満で縮退した (達成済み 0.64、待機 0.54)。発言内容を材料に入れる
前は、申し出の言い直しを「達成済み」と外していた。同じ state でも確率は呼ぶたびに
揺れる (場面 1 で 0.40 と 0.64)。

**その後**: 閾値と `TYPED_JUDGMENT_LOOP_DIAGNOSIS_MIN_CONFIDENCE` は外した。縮退は
「該当なし」と判断が得られないときの 2 つになり、`below_threshold` は無くなった。
理由は #234。

**関連**: #222 / #1411 / #1412 (意味上の繰り返しの検出器はこの出し口を使う) / #234。

## 233. 完全一致で数えられない繰り返しは、直近の行動の窓を Jev に問って足す。件数はコードが持つ

**何を**: ループ警告の 3 つ目の検出器として `SemanticRepeatDetector` を置く。player ごとに
直近 K 件 (既定 4) の行動の要約と結果の文を持ち、K 件そろったターンに `NoulQuestion` で
「手段を変えずに同じことを試し続けているか」を 1 回問う (`question=semantic_repeat`)。
確率が閾値 (既定 0.8) 以上なら `SemanticRepeat` を返し、#232 の出し口と見立てを通る。
`TYPED_JUDGMENT_SEMANTIC_REPEAT_ENABLED` の既定は off。

**なぜこの形か**: 完全一致の検出は `(tool 名, fingerprint)` が揃わないと数えない。言い直した
同じ依頼、操作名や呼び名を変えた同じ失敗、2 つの行動の往復は、どれも連続が切れる。意味が
同じかをルールで決めるのは難しい。逆に件数と「何件並んだか」はコードで確定できるので、
Jev には数えさせず、窓の中身が同じ試みかだけを問う。

**重ねて出さない**: 同じ行動で複数の検出器が発火したら、出し口 (`emit_all`) は 1 件だけ
出す。優先は離れた tick の失敗 (失敗の理由を持つ)、連続の同一行動、意味上の繰り返しの順。
同じ繰り返しに警告が 2 件届くと待機へ押す力が強くなりすぎ、見立ても 2 回問うことになる。
`CrossTickFailureTrigger` は、離れた tick の失敗を出したときに返し続ける。捨てた側の判断も
`TYPED_JUDGMENT` に `exact_match_fired=True` で残す。重なりを後から数えるため。

`CrossTickFailureTrigger` は、繰り返した失敗を信念の証拠に書き起こす部品だけが読んでいた。
その部品と一緒に、記憶の部品の撤去 (#1631) の #1646 で消した。警告と見立ては、検知器の
`CrossTickFailureRepeat` を出し口の中で受けるので変わらない。

完全一致の検出が発火したら、その行動を最後に意味上の窓も空にする。完全一致は閾値の倍数で、
意味上の検出は窓がそろった時点で発火するので、空にしないと隣り合うターンに同じ繰り返しへ
2 件届く (K=4 で wait を 9 回続けると 3, 4, 6, 8, 9 回目に警告が出た)。

**発火は控えめに**: signal を出したら窓を空にし、新しい行動が K 件溜まるまで問わない。
閾値未満なら窓は空にせず、次のターンに 1 件ずれた窓をまた問う。既定の文面は、完全一致の
警告の命令調を引き継がず、事実だけを書く。

**材料**: 行為者の名前と、直近 K 件の行動の要約・成否・結果の文だけ。要約は fingerprint から
`format_action_summary_for_display` で作るので、発言は内容つきで入り、内心は入らない。本人の
目的は入れない (#222)。目的の同乗フィールド (`goal_update` / `goal_outcome`) は fingerprint に
残り、要約の表に無い tool では JSON のまま出るので、要約の前に落とす。結果の文は 200 字で切り、
trace の窓と渡した窓を同じにする。見立て用の直近 5 件 (`RecentAction`) とは別に持つ。評価に使った要約と
同じ形に保つため。

**呼ぶ回数**: 検出の問いは 1 ターンに最大 1 回。発火したターンだけ、#232 の見立てがもう 1 回
問う。見立ては居場所と届いている観測も材料にするので、同じ state にまとめていない。

**実 Jev の確率**: 既存 trace から 20 窓を組み直した (`scripts/jev_semantic_repeat_demo.py`)。
繰り返しでない窓 8 件の最大は 0.51 (同じ相手へ段階的に進む囁き、椰子の実を拾って食べる往復)。
完全一致で拾えなかった繰り返し 10 件は、6 件が 0.86〜0.91 (申し出の言い直し、言い換えた
無い操作、拾い尽くした漂着物、往復 3 種)、4 件が 0.55〜0.71 (操作名を毎回変えた同じ失敗 2 件、
対象名が要約に出ない古い trace、部屋の往復)。質問の真の側に「同じ理由で拒否され続けている
場合」を足すと、繰り返しでない窓の最大が 0.62 から 0.51 に下がり、繰り返しの側は変わらな
かった。閾値 0.8 は繰り返しでない窓の最大から離して置いた値で、trace を読んでから下げる。
この 20 窓は質問文の調整にも使っており、取り分けた検証用の窓は無い。本番では閾値未満の窓を
毎ターン 1 件ずらして問うので、問う窓のほとんどは繰り返しでない。繰り返しでない 8 件で誤検出
0 件という結果では、本番の警告の件数はまだ見積もれない。観察 run の trace で数え直す。

**関連**: #222 / #232 / #1411 / #1412。

目的の同乗フィールド (`goal_update` / `goal_outcome`) は、目的の見直し (`GOAL_REVISION_ENABLED`) と一緒に、記憶の部品の撤去 (#1631) の #1664 で消した。要約の前に落とす処理も一緒に消えた。

## 234. Jev の閾値は、誤ったときに行動が実行される問いにだけ残す

**何を**: tool 名の提案 (#231) と繰り返しの理由の判定 (#232) から閾値を外す。
いちばん確率の高い選択肢をそのまま採り、「該当なし」を選べば採らない。判断が得られない
とき (例外、答えが無い、選択肢に無い答え) の縮退と trace は残す。確率と確信は trace に
残し続ける。profile の `TYPED_JUDGMENT_TOOL_NAME_MIN_CONFIDENCE` と
`TYPED_JUDGMENT_LOOP_DIAGNOSIS_MIN_CONFIDENCE` は消し、書くと未知のキーとして起動前に落ちる。

**基準は、誤ったときの損**: 閾値は、判断を誤ったときに行動が実行されてしまう問いを守る
ためにある。誤っても行動が実行されない問いでは、閾値で採らなかった分だけ、当たっていた
答えも捨てることになる。

- tool 名の提案: 別の tool として実行はせず、失敗文の「もしかして 'X' ですか?」が
  変わるだけ。外れても、使える tool の一覧は並べてある
- 繰り返しの理由の判定: どの理由を選んでも警告は出る。変わるのは警告の文面だけ

**外すと変わる件数**:

- tool 名の提案: 過去 run の 24 件のうち 2 件。`inner_thought` → `travel_to` (0.64) は
  誤りで、`look_around` → `explore` (0.53) は正しい。誤りの側も、提案が外れるだけで
  失敗は失敗のまま返る
- 繰り返しの理由: 観察 run `station_drill_gemma31_loop_jev_001` の 4 件のうち 1 件。
  会議の告発の言い直しが「同じ手段へのこだわり」(0.65) の文面になる

**残す閾値**: 行動名の置き換え (#223、0.7) と対象名の置き換え (#227、0.85) は、置き換えた
名前でそのまま行動が実行される。値も 1 つにまとめない。0.85 にまとめると、行動名の救済が
実際の失敗 99 件で救えていた 71 件が 58 件に減る。0.7 にまとめると、対象名で手持ちの品を
その場の物に置き換える誤りが 4 件増える。

**はい / いいえの問い**: memo の達成判定と意味上の繰り返し (#233) は、選択肢ではなく確率
1 つを閾値と比べる形なので、ここでは触らない。後続の PR で選択肢の形に変える予定。

**新しい使い道にも閾値を足さない**: 「待機」と判定した警告を軽くする件 (#1425) は、
「待機」がいちばん高い選択肢なら軽くする。軽くしても事実は届くので、誤っても文面が
変わるだけの側に入る。

**関連**: #223 / #227 / #231 / #232 / #233 / #1427。

## 235. 動的引数候補の実験は、モデルへ見せる前から同じ真実源を保存する

**何を**: prompt dataset の各 LLM 呼び出しに、`tool_runtime_context` から作った
ツール・引数別候補 snapshot と、そのまま介入に使える表示文を保存する。基準条件では
表示文を prompt へ入れない。後段で同じ request を介入なし / 候補表ありの両方へ再生する。

**なぜ**: 既存 dataset は prompt 本文と tool schema を持つが、runtime context を持たない。
本文から候補名だけを拾っても、対象ごとの `action_name`、非公開候補、配列内の引数との対応を
完全には復元できない。現在の resolver へ過去出力を流す案も、過去run後の仕様変更を混ぜる。
呼び出し時点の候補へ文字列照合すれば、当時なら動的引数で拒否されたかを、現在の世界コードを
実行せずに再集計できる。

**保存する理由**: 集計値だけを残すと、候補表の文面や判定規則を変えたときに分析をやり直せない。
構造化候補、表示文、request、response、token・費用・待ち時間を生データとして残す。

**候補表へ該当なしは足さない**: 本番案に無い選択肢を実験だけへ足すと別の介入になる。候補外の
意図に対して別ツールを選ぶか、候補を無理に選ぶかも候補表の実用上の性質として測る。

**関連**: #1429 / #37 / #98 / #210 / #223 / #227。

## 236. 動的引数候補は世界説明を置き換えず、行動指示の直前で正規化して再提示する

**何を**: 実際に LLM API へ渡すツール集合と同じ `tool_runtime_context` から、
対象解決を行う `tool.argument` ごとの候補表を作る。世界の説明やツール定義は残したまま、通常の
行動選択プロンプトの末尾、行動指示の直前へ表を置く。二段階推論では評価段階へ
入れず、行動選択段階だけへ入れる。候補が無いときは見出しごと出さない。

**なぜ**: 現在地の説明にも、接続先や物体の操作は既に書かれている。しかし、
それらは世界の説明として複数箇所へ分散しており、`destination_label` や
`action_name` に完全一致で何を書けるかは集約されていない。Issue #1429 の保存済み
失敗5件へ候補表だけを足した小規模介入では、候補外入力が5件から0件になった。
4件は候補内の行動へ再計画し、1件は別行動へ退いた。正常5件にも候補外入力は
生じなかったが、1件は別行動へ変わった。ただし各条件1回の小規模確認であり、
効果量を確定するものではない。そのため候補表は意味理解の代替ではなく
「現在指定できる文字列」の正規化として扱う。

**どうしないと壊れるか**: ツール定義へ動的 enum を埋めると tick ごとに定義が変わり、
プレフィックスキャッシュを壊す。世界説明を候補表で置き換えると、物体の意味や
前提条件が消える。APIへ出さないツールの候補まで載せると、存在しない行動を宣伝する。
評価段階へ載せると、評価専用ツールしか呼べない局面で行動候補を見せることになる。

**候補の範囲**: 見出しは「現在選べる対象引数」とし、自由文、数量、価格、検索語などは
含めない。表示名を受ける `TargetIndex` 系と、`P1` / `G1` などのラベルを直接受ける
`require_target_type` 系を区別し、各 resolver が実際に受理する値を載せる。会議、発話、
個人間取引、ギルド、ショップ、任務、スキルを含む対象解決ツールを同じ対応表で管理する。

**再分析時の判定**: 「表に表示した値との完全一致」と「当時の resolver なら受理したか」
を別々に保存する。後者は `label_forms` と `normalize_action_name_candidates` と同じ規則で
照合し、内部ラベル、引用符、表示行の丸写しを入力ミスとして水増ししない。

**関連**: #1429 / #1 / #210 / #234。

## 237. 信念を作る直前に、形と同じ意味の既存の信念を Jev に 1 回で問う。候補は文だけで絞る

**何を**: 信念を固める LLM が `create` を選んだとき、適用の直前に `BeliefCreateGate` が
Jev に 2 つの `ChoiceQuestion` を同じ state で 1 回で問う (`question=belief_create_gate`)。
形が「いまの状況」なら作らない (skip 理由 `create_current_situation`)。同じ意味の既存の
信念が選ばれたら、`create` の証拠をその信念に積む `strengthen` に置き換える。
`BELIEF_CREATE_GATE_ENABLED` の既定は off。

**候補は文だけで絞る**: 同じ意味の選択肢は、既存の有効な信念を `ITextCandidateNarrower` で
上位 K 件 (既定 5) に絞って並べる。最初の実装は文字の 2 字組の BM25
(`char_bigram_bm25`)。tags と cue は使わない。tags には tool 名や spot 番号が混ざっていて、
環境を取り換えると前の環境の語彙で絞ることになる (#1436)。手法は
`BELIEF_CANDIDATE_NARROWER` で選び、埋め込みは同じインタフェースの実装として足す。2 字組を
1 つも共有しない候補は並べない。

**閾値を残す**: #234 の基準では、誤ったときに取り返しがつかない問いにだけ閾値を置く。
この問いは誤ると記憶への書き込みになり、戻せない。「いまの状況」の誤りは学びを捨て、
同じ意味の誤りは別の主張の信念に証拠を混ぜる。そこで確信度が
`BELIEF_CREATE_GATE_MIN_CONFIDENCE` (既定 0.4) に届かない答えでは `create` を通す。
決定論 stub は迷った答えを返し、「該当なし」と「世界の決まり」を先頭に置いているので、
stub の run は現行のまま作る。

**K と閾値の根拠**: 過去の snapshot の似た組 96 組 (`difflib` の ratio ≥ 0.6) で測った
(`scripts/jev_belief_create_gate_measure.py`)。相方が BM25 の上位 K 件に入った割合は
K=1 で 74%、K=3 で 96%、K=5 で 100%。96 組を人が「同じ主張 72 組 / 違う主張 24 組」に
分け、K=5 で Jev に問うた。違う主張の信念へ置き換えた例は確信度によらず 0 件で、同じ主張の
組を置き換えた割合は閾値 0.4 で 90%、0.6 で 61% だった。30 組を K=3 / 10 でも問い、K を
増やしても選び間違いは増えなかった。この 96 組は文字が似ている組だけなので、言い換えで
文字が重ならない重複は測れていない。
「いまの状況」で作らない側の誤り (残すべき信念を捨てた率) は測っていない。96 組の新しい方
77 文のうち閾値 0.4 以上で「いまの状況」とされた 10 文を目視しただけで、採り尽くした・
持っている・提案した、の類だった。有効にした run の trace で skip された文を読んで決め直す。

**判断が得られないとき**: 例外 (候補の絞り込みの例外を含む)・答えの欠け・選択肢に無い
答えは `create` を通し、縮退の理由を `TYPED_JUDGMENT` の `unavailable_reason` と decision の
`create_gate_unavailable_reason` に残す。置き換えた decision は
`BELIEF_CONSOLIDATION` の `decisions` に `create_gate_outcome` と
`strengthened_belief_id` を足して残す。create のままだと、作られたと誤読する。

**関連**: #1436 / #1453 / #1414 / #1463 / #234。

作る前の判定 (`BELIEF_CREATE_GATE_*`、`belief_create_gate.py`) と候補の絞り込み (`BELIEF_CANDIDATE_*`) は、記憶の部品の撤去 (#1631) の #1787 で消した。どの profile でも無効だった。測った記録の `scripts/jev_belief_create_gate_measure.py` も一緒に消した。

## 238. 目的の達成 hint は、判断が得られないとき規則へ縮退しない。清算できない目的は問わない

**何を**: 行動の結果が返ったあと、未達成の目的が達成されたかを Jev に問い、確率が閾値以上なら
結果の文に「目的「〜」は達成したかもしれない。達成したなら goal_outcome で記録する」と添える
(Issue #1448)。目的の状態は変えない。有効化は `TYPED_JUDGMENT_GOAL_HINT_ENABLED`、閾値は
`TYPED_JUDGMENT_GOAL_HINT_MIN_PROBABILITY` (既定 0.5)。

**memo の hint と違えたところ**:

- **判断が得られなければ hint を出さない**: memo の hint は文字の重なりへ縮退するが、目的では
  しない。目的の達成を規則で推す案は、誤った材料が信念に流れるので P8 で捨てた
  (`docs/memory_system/unified_memory_phase2_implementation_plan.md`)。縮退すると、捨てた規則を
  本人に勧めることになる。縮退の理由は TYPED_JUDGMENT に残す (#5)
- **閾値以上の目的ごとに hint を出す**: memo は最も確率の高い 1 件だけだが、目的は清算の単位
  なので、達成したかもしれない目的はどれも知らせる

**問わない場面**:

- **失敗した行動**: 目的を進めないので、問うと費用と誤った hint の機会だけが増える
- **locked の目的**: `goal_outcome` が拒否されるので、問えば拒否される申告を勧めることになる
- **提示した定義に `goal_outcome` が無い tool**: memo の操作など。tool 名の規則
  (`is_subjective_action_tool`) では memo tool も含まれるので、実際に提示した定義を見る
- **同じ行動で `goal_outcome` か `goal_update` を書いた**: 本人がもう決めている
- **目的の改訂が無効な run**: `goal_outcome` が tool に出ていない。hint を有効にした profile で
  判断ポート・goal store・目的の改訂のどれかが欠けていたら、session を作る時点で落とす。黙って
  無効にすると、run 後に「hint が 0 件」が閾値のせいか配線のせいか見分けられない

**判断に渡す結果の文**: memo の hint を付ける前の文を渡す。付けたあとの文を渡すと、行動の結果で
なく別の hint を材料に達成を判断する。

**「問わなかった」は trace に出さない**: 上の条件はどれも、同じ tick の `action` (tool 名と引数) と
`action_result` (成否) から再構成できる。毎ターン記録すると、判断の記録が埋もれる。判断が得られ
なかったとき (例外、答えの欠落、確率として読めない答え、想定外の例外) は理由を 1 件残す。

**閾値 0.5 の根拠**: 過去 run には、本人の目的を達成して申告しなかった場面が無い。goal store を
有効にした run はシナリオ目的が locked で、本人の `goal_update` は全件棄却されていた。そこで
棄却された文を目的とみなし、その後の行動と結果に当てて 23 件を組み直した
(`scripts/jev_goal_completion_hint_demo.py`)。未達 14 件の最大は 0.18、達成 9 件は
0.9 / 0.9 / 0.82 / 0.68 と 0.35 以下に割れた。0.35 以下は「A してから B」のような複合目的で、
ラベル自体が割れうる。0.7 では明らかな達成 (渡す目的で 2 件とも渡せた、0.68) を落とす。

#234 の基準では、hint は誤っても行動が実行されないので閾値の要らない側に入る。それでも閾値を
置くのは、誤った hint が続くと本人が未達成の目的を達成扱いにし、嘘の支持 evidence が信念に
流れるため。

**関連**: #5 / #234 / P8。

目的の達成 hint (`TYPED_JUDGMENT_GOAL_HINT_ENABLED` / `_MIN_PROBABILITY`) は、記憶の部品の撤去 (#1631) の #1657 で消した。
hint が勧めていた `goal_outcome` も、目的の見直し (`GOAL_REVISION_ENABLED`) と一緒に #1664 で消した。

## D1439. 予期の状態の変化と、その出来事を、同じ保存の単位で残す

**何を**: 予期の保存先 (`ExpectationRepository`) は、予期の状態と、その変化で集約が返した出来事を
1 回の `save` で受け取り、出来事を未配信として積む (アウトボックス)。配信できたら印を付ける。
未配信の出来事と記憶のターン数も、予期と一緒に snapshot へ載せる (Issue #1439)。

**なぜ**:

- 確定は取り消せず、信念を直す処理につながる。予期だけ保存されて確定の出来事が失われると、
  信念は直らないまま、確定した状態だけが run を跨いで持ち越される。逆に出来事だけ残ると、
  清算待ちの予期にもう一度判定が入り、同じ確定が二度届く
- 予期は状態をそのまま保存して戻す。照合の記録を流し直す形では、形の判定と期限の確認の
  ターンが記録に残らず、終わった予期が清算待ちに戻る (#1468 のセルフレビュー)

**決まり**:

- **出来事の ID は「予期の ID@ターン」**: 集約の規則上、1 つの予期は 1 ターンに出来事を
  1 つまでしか返さない。配り直しても同じ ID になるので、受け取る側が重複を見分けられる。
  保存先が連番を振る形は、連番そのものを snapshot に持つ必要があり、配信済みの印で消した
  番号と再開後の番号が重なりうるので採らなかった
- **終わらせた保存には、終わったターンの出来事を必須にする**: 清算待ちだった予期を
  終わった状態で保存するのに、終わったターンの出来事が無ければ何も保存せずに拒む。
  `save` の出来事は省略できない引数にし、出来事を返さなかった変化でも空で渡させる
- **保存先は予期を保存用の値で持つ**: 取り出した予期を書き換えても、`save` を通るまで
  保存先は変わらない。状態だけが先に書き換わる経路を作らない
- **復元の整合は書く前に確かめる**: 予期・未配信の出来事・記憶のターン数の組は
  `require_restorable` で確かめる。snapshot の復元は複数の保存先を順に書くので、
  どの保存先にも書く前に呼ぶ。持ち主の違い、重複、予期の無い出来事、予期や出来事より
  前のターン数を拒む

**どうしないと壊れるか**: 予期の状態と出来事を別々に保存すると、どちらかの保存の失敗や
呼び出し側の渡し忘れで、確定が信念に届かないまま静かに消える。

**関連**: design_decisions 27 (per-Being store の snapshot 配線) / Issue #1436 / #1440 (配信と配り直し)。

**その後**: 記憶のターン数は、予期の保存先から Being 側の時計 (`MemoryTurnClock`、
`being/domain/memory_turn_clock.py`) に移した (Issue #1631、PR #1643)。古い記憶の部品を消すと予期も消える
が、ターン数は新しい記憶 (エピソードの書き起こし、目次、メモ帳、知り合いの記録) も読むため。
snapshot のキー `memory_turn` は変えていない。予期の保存先は、復元のときに一緒に戻すターン数を
`require_restorable` で確かめるためだけに受け取り、持たない。

予期のドメイン (`domain/memory/expectation`) と保存先も Issue #1631 で消した。`require_restorable` も一緒に消えたので、
snapshot の `memory_turn` は予期と突き合わせずに時計へ戻す。snapshot から
`expectations` と `expectation_undelivered_events` のキーを外した。消す前に保存した snapshot は、
復元が足りないキーだけを拒むので、そのまま読める (2 つのキーは読み飛ばす)。`memory_turn` は残した。
`snapshot_save` / `snapshot_load` の trace の `expectation_counts` は、記憶のターン数だけを載せる
`memory_turns` (`[{being_id, memory_turn}]`) に変えた。

## D1463. 環境とエージェントの契約は、欄の段と経路ごとの必須欄を型で表し、本文に無い名前を写さない

**何を**: `ai_rpg_world.being.contract` に観測 (`Observation`)・エージェントの 1 手
(`AgentMove`)・環境に入るときの取り決め (`EnvironmentEntry`) を置く。観測の欄の段は
注釈と既定値の有無で表す。必須は `T`、分かるなら書くは既定値の無い `T | Unknown`、
任意の助言は `T | None = None`。経路は 5 つの型の和で、呼び出しの ID と成否は
`OwnActionResult` だけが持つ。ゲームからの変換は `application/observation/being_contract/`
に置く。

**なぜ**: 「分かるなら書く」を任意にすると、空が「当てはまらない」のか「書かなかった」
のかが区別できない (#1436 のコメント)。省けない欄にして「不明」を明示させ、空文字は拒む。
経路ごとの必須欄を検証コードで書くと、新しい経路を足したときに検証の書き忘れが起きる。
型にすれば作る時点で欠けられない。

**本文に無い名前を写さない**: ゲームの `structured` には、本文で伏せた名前も入っている。
雰囲気の変化 (`spot_public_effect_observed`) の `actor_name` は妨害の行為者で、本文は
「集会室の雰囲気が変わった」としか言わない。主体の名前と場所は、本文に現れる値だけを写す。
本人が観測から知り得ないことを契約に載せると、記憶が秘匿を破る。照合は部分一致なので、
伏せた名前が本文の別の語の一部と重なると写る。日本語の本文に語の境界が無いため、いまは
この限界を受け入れる。

**主体が本人かは確かめたときだけ真にする**: `role: "self"`、話者の ID、行為者の名前が本人と
一致したとき、または本文が一人称で本人の状態を述べる種類 (入手・所持金・装備など) だけを
本人とする。`self_only` には取引の提案や拒否のように主体が他人の観測もあるので、分類からは
推さない。本人が行為者かは本文が伏せていても本人には分かるので、構造化データで決める。

**情報源と体の状態**: 「見た・聞いた」「自分の体の状態」「自分の行動の結果」の情報源は本人
(自分で知った)、「言われた・書かれていた」は話し手や書き手、「環境からの知らせ」は「不明」。
標的が本人でも経路を「自分の体の状態」にするのは害を受けたとき (モンスターの攻撃) だけで、
追跡の開始のように見て知る出来事は「見た・聞いた」のまま自分宛てにする。

**写せない観測は選択肢を足さずに拒む**: 目的の振り返り・改訂 (`goal_reflect` /
`goal_revision`) とループ警告は、Being 自身の判断を書き戻したもので、環境から届く観測では
ない。目撃文との重複を避けて本文を空にした `player_downed` と、時刻ラベルの無い観測も拒む。
どれも `ObservationNotRepresentable` の理由で区別する。

目的の改訂 (`goal_revision`) は #1664 で、目的の振り返り (`goal_reflect`、`GOAL_REFLECT_ENABLED`) は #1679 で、記憶の部品の撤去 (#1631) として消した。拒む記録はループ警告だけになった。

**trace での数え方**: アダプタはまだ run の中で動いていない。trace の `observation` に変換の
入力がそのまま残るので、`scripts/being_contract_unknown_report.py` が run を回さずに欄ごとの
「不明」を数える。

**関連**: #1463 / #1436 / #1469 / design_decisions 51 / design_decisions 57。

## D1440. 予期の清算は、ターンの終わりに 1 回だけ問い、保存してから配り、受け取る側に重複を見分けさせる

**何を**: Being の 1 手を受け取ったターンの終わりに、`ExpectationSettlementService` が Jev を
1 回だけ呼ぶ。このターンに書いた予期には形の問い、清算待ちの予期には清算の問い、加えて場面が
変わったかを、同じ state で問う。判定は予期の集約に渡し、返った出来事を予期と一緒に未配信と
して保存したあとで、`ExpectationEventDispatcher` が受け取る側へ配る (Issue #1440)。

**なぜ**:

- 形と当否を 1 問に混ぜると、材料がまだ無い時点ではすべて「まだ分からない」に倒れる (#1436 の
  試し)。2 問に分けても state は同じなので、呼び出しは 1 回にまとめる
- 保存の前に配ると、配った直後に保存が失敗したとき、受け取る側だけが確定を知っている状態が
  残る。保存してから配れば、配る途中で失敗しても出来事は未配信のまま残り、次のターンに配り直せる

**決まり**:

- **ターン数は手の処理より先に進める**: `run_phase_b` の入口で `advance_memory_turn` を呼ぶ。
  手の中で作る予期 (#1441) がその手のターン数を持ち、同じターンの終わりに形の問いを受ける。
  失敗した手や迷った手でも進める。既存のターンの数え手 (信念を固める周期など) も同じ単位で
  数えているので、#1464 で置き換えるときに数え方が変わらない
- **期限と件数の上限は問う前に閉じる**: 期限はターン数で決まり、判断ではない。Jev が答えない
  ターンにも閉じる。上限を超えたら、期日の無い古い予期から `Expectation.expire_early` で期限を
  前のターンに繰り上げて閉じる。閉じ方は期限を過ぎたときと同じで、暫定の当否があればそれで
  確定する。上限で外す専用の閉じ方を持つと、保存して戻すときに閉じた理由を導けない
- **判断が得られないターンは、どの予期にも判定を渡さない**: 例外、欠けた答え、選択肢に無い
  答えはどれも縮退として扱い、理由を trace に残す (design_decisions 5)
- **形の問いは、書いたターンではなく形の判定を待っているかで出す**: 予期を書いたターンに
  判定が得られなかった予期にも、次のターンに形を問う (`Expectation.awaits_shape`)。書いた
  ターンで分けると、形を一度も問われない予期が清算に回り、「どう転んでも当たる」予期が
  当たりで確定する
- **清算の途中で想定外の例外が出たら、閉じた予期を trace に残してから投げ直す**: 期限と件数
  で閉じた予期は問う前に保存しているので、残さないと閉じたことが trace から見えない。保存済み
  の出来事も配ってから投げ直す。ゲームのターンは止めない
- **state に ID も整数も入れない**: 質問の名前は連番、ターンは「ターン3」の文にする
- **受け取る側は同じ ID を二度受け取っても結果を変えない**: 配り手は、受け取る側の 1 つでも
  例外を投げたら出来事を未配信のまま残し、次に全員へ配り直す。先に受け取れた側にも同じ出来事
  がもう一度届く。受け取り済みの ID は、受け取った結果と同じ保存の単位で記録する (#1479)
- **配り直しの上限に届いた出来事は、捨てずに配り直しから外す**: 未配信のまま保存先に残り、
  `undeliverable` と trace の `gave_up` で一覧できる。再開した run では数え直してもう一度配る。
  `report.md` には出さない。受け取る側がまだ無く、上限に届く経路が run に無いため
- **受け取る側が無ければ、配信済みの印だけ付ける**: 受け取る側 (#1442、#1443) がまだ無い。
  trace の outcome は `delivered` ではなく `no_receivers` にし、誰かが受け取ったとは読めない
  値で残す

**持ち越さないもの**: 清算に見せる時系列と、配ろうとした回数は run の中だけで持ち、snapshot
に入れない。再開した直後の数ターンは時系列が短く、清算の問いは「まだ分からない」に寄りうる。
時系列は直近の数ターン分だけを見せる材料で、失っても予期の状態は壊れない。

**問いの説明で決めたこと** (`scripts/jev_expectation_settlement_demo.py` で過去 run を組み直して
確かめた):

- 形の問いの「本人の行動」は「これから何をするかだけを述べ、その結果を述べていない」とする。
  行動の結果 (見つかる、できる、失敗する) は清算できる予期に入れる。入れないと、行動に添えた
  予期の多くが外される
- 清算の問いで「主語の無い予期は本人のこととして読む」と書く。書かないと、「流木を拾えて」を
  他の人が流木を拾った出来事で当たりと読んだ

**どうしないと壊れるか**: 配ってから保存すると、確定した予期の出来事が信念に届いたかどうかが
保存の成否に左右される。受け取る側が重複を見分けないと、配り直しのたびに同じ確定が信念へ
二重に積まれる。

**関連**: design_decisions D1439 / design_decisions 5 / Issue #1436 / #1441 / #1442 / #1443 / #1464 / #1479。

**その後**: 予期の清算 (`ExpectationSettlementService`、`EXPECTATION_SETTLEMENT_*`)、配り手 (`ExpectationEventDispatcher`、`EXPECTATION_EVENT_MAX_DELIVERY_ATTEMPTS`)、再開時の配り直しは Issue #1631 で消した。予期の保存先と snapshot のキーも、続く PR で消した (D1439 の「その後」)。

## D1452. 信念と証拠は観測のターン数だけを持ち、状態の変わり方は観測の食い違いから学ぶ

**何を**: 証拠 (`BeliefEvidence.observed_turn`) に、観測したときの記憶のターン数を必須で持たせる。
信念 (`SemanticMemoryEntry.last_observed_turn`) には、支える観測のうち最も新しいターンを持たせる。
信念を固める LLM には、証拠の `observed_turn`、候補の信念の `last_observed_turn`、いまの
`current_turn` を並べて渡す。選択肢に `explain_change` (状態の変わり方を説明する信念を作る) を
足し、反証された状態の信念を新しい信念に置き換える (`supersedes`) (Issue #1452)。

**なぜ**:

- 信念に有効期限を持たせない。Being は見た時点で、それがいつまで続くかを知らない。
  「浜の枯れ葉は採り尽くされている」が変わる状態だということは、前に見たときと今の
  観測の食い違いからしか学べない
- 食い違いを「前の学びが誤っていた」(`revise` / `contradict`) と「状態が変わった」
  (`explain_change`) に分けて選ばせる。どちらなのかは文の中身で決まるので、LLM に
  2 つのターン数を並べて読ませる

**決まり**:

- **時計は記憶のターン数**: 世界の tick は使わない (#1436)。ターン数は Being 側の時計
  (`MemoryTurnClock`、Issue #1631 で予期の保存先から移した) から、読むだけの口
  `MemoryTurnReader` で受け取る。
  証拠を作る部品と信念を固める処理は、runtime が持つ 1 つの数え手を共有する
- **証拠は作る時点でターン数を必須にする**: 証拠を作る 6 か所 (転記器 4 つ、クラスタ昇格、
  目的の停滞) は口を省けない引数で受ける。証拠の時点は「転記した時点」で、chunk の中の
  個々の出来事の時点ではない。エピソードがターン数を持つようになったら (#1464)、そちらに
  寄せるかを決め直す
- **信念の時点は支える観測の最新**: 作る・強めるで前に進め、戻さない。改める・否定するは
  動かさない。否定は信念を支えないので、反する観測のターン数は証拠の側で渡す。観測から
  作られていない信念 (クラスタ昇格の要約) は `None` (不明)
- **変わり方の信念は別の系譜**: 状態の言い直しではないので新しい `belief_id` を持つ。
  前の状態を支えた観測と、食い違った今の観測の両方を支持に持つ。食い違った証拠の指定が
  無ければ batch 全件には倒さず見送る。何と食い違って変わったのかを残せないため
- **作る前の判断 (#1453) を通す**: 置き換える状態の信念は同じ意味の候補から外す。同じ意味の
  変わり方の信念がすでにあればそれを強め、状態の信念は superseded にする (`supersedes` の
  指し先は残らない)。強めるときに足すのは今回食い違った証拠だけで、前の状態を支えた
  観測は引き継がない。「いまの状況」と判断されたら作らず、状態の信念も置き換えない
- **状態の変化か前の学びの誤りかは指示文で分ける**: 見落としていた所での発見は前の学びの
  誤りとして `revise` / `contradict` に回す。機械の試験では守れないので、
  `scripts/belief_state_change_probe.py` の対照の場面で読む (#1452 の確認で 3/5 → 1/5)。
  この script は固着と一緒に #1631 の #1790 で消した
- **snapshot の互換は保たない**: 証拠の payload に `observed_turn` が無ければ読み込まずに
  止める。いつ見たかを捏造しない。信念の `last_observed_turn` は、キーが無ければ不明として
  戻す。不明は値として表せるので、止めるほどではない

**どうしないと壊れるか**: 有効期限で状態の信念を消すと、Being は「変わる」ことを学ばない
まま、期限が来るたびに同じ状態を学び直す。ターン数を任意にすると、配線の漏れた部品の
証拠だけが時点を持たず、固める LLM が並べて比べられないまま静かに判断する。

**関連**: design_decisions D1439 (記憶のターン数の保存先) / Issue #1436 / #1440 (ターン数を進める配線) /
#1443 (予期の外れを証拠につなぐ) / #1453 (作る前の判断)。

**その後**: 証拠のバッファ (`BeliefEvidence`、`BELIEF_EVIDENCE_ENABLED`) は、読み手の固着を #1790 で消したあと、記憶の部品の撤去 (#1631) の #1792 で消した。Being の snapshot のキー `belief_evidence_buffer` / `belief_evidence_received_event_ids` も外した。消す前の snapshot も読める。信念の `last_observed_turn` は、意味記憶の store と一緒に続く PR で消す。

信念の `last_observed_turn` も、意味記憶エントリと一緒に #1794 で消した。

## D1441. 予期は環境の tool の引数として一律に書かせ、その手のターンの予期として積む

**何を**: profile の `EXPECTATION_ARGUMENT_ENABLED` を有効にすると、環境の tool (spot graph の
tool) すべてに必須の引数 `expectations` (1 件ごとに what / when / likelihood) を付ける。
行動ルールには書き方の 1 行を足す。`run_phase_b` は tool を実行する前に引数から予期を読み、
Being のターン数を作ったターンとして清算待ちの予期を積む (Issue #1441)。

**なぜ**:

- `expected_result` を 4 tool だけに付けていた理由 (共通の記録経路が主観の引数を運べなかった)
  は解消している。tool の一覧で分けると、発話のように他の人の反応を予期する行動に予期が残らない
- 予期は「この行動をしたら、こうなるはず」なので、行動を選んだあとに書く。2 段階ターンの
  `assess_situation` は考えてから tool を選ぶための tool で、予期を書く場所ではない

**決まり**:

- **付けるのは環境の tool だけ**: 記憶の tool と `assess_situation` には付けない。積むときも、
  送った定義に `expectations` がある tool の呼び出しだけを読む。付けていない tool の引数に
  紛れた予期は積まない
- **定義は run の中で変えない**: 有効化は run 全体で決まり、ターンごとに出し分けない
  (design_decisions 1)
- **作ったターンは Being のターン数**: ターン数は手の処理より先に進めてある
  (design_decisions D1440) ので、積んだ予期は同じターンの終わりに形の問いを受ける
- **頭にあった信念と想起は、そのターンのプロンプトから取る**: `PredictionContextLedger` が
  プロンプトを組んだときに載った信念と、想起したエピソードを持っている。行動の記録が台帳を
  消費するので、tool を実行する前に `peek` で読む。台帳から引けなければ信念と想起を空にして
  積み、trace の `context_found` を False にする。「0 件だった」と「分からない」を分けるため
- **行動の成否を待たずに積む**: 行動が失敗しても、本人がそう予期した事実は残る。失敗した結果は
  清算の材料になる
- **崩れた予期は 1 件ずつ外す**: 確からしさが 4 段の日本語の値以外、`what` が空、`when` が文字列
  でない予期は積まず、理由と元の値を trace `expectation_formed` に残す。ほかの予期は積む
- **期限は期日の有無で分ける**: 期日の無い予期は `EXPECTATION_UNDATED_TERM_TURNS` (既定 5)、
  期日のある予期は `EXPECTATION_DATED_TERM_TURNS` (既定 30) で期限を切る。期日は環境の時間で
  書かれ、届いた出来事の時刻で清算されるので、ターン数は長めにする
- **ID は「Being の ID:t ターン:書いた順」**: 保存先の状態に頼らず決まる (#1479)。同じターンに
  2 回積もうとしたら、上書きせずに止める
- **組めない組み合わせは起動前に止める**: 清算 (`EXPECTATION_SETTLEMENT_ENABLED`) が off だと、
  期限で閉じる処理も動かないので予期が増え続ける。信念と想起の台帳
  (`PREDICTION_CONTEXT_ID_ENABLED`) が off だと、頭にあった信念が常に空になる。
  `LLM_EXPECTED_RESULT_POLICY` が off でないと、予測を書く欄が 2 つ並ぶ。どれも `ValueError`
  (この検査は予期の引数と一緒に Issue #1631 で消した)
- **`expected_result` は消さずに残す**: 予期の引数が無効な run の tool の定義と行動ルールを
  変えないため。いまの profile の多くは `expected_result` を必須にしている。「前回の予測と
  実際」の欄 (#1442) と、区切り・主観補完の読み手が予期に移ったら消す

**どうしないと壊れるか**: 頭にあった信念を tool の実行後に読むと、行動の記録が台帳を消費した
あとなので、成功した行動の予期だけ信念が空になる。清算が off のまま積むと、予期は閉じられずに
増え続け、清算の trace が 0 件の run を「予期が無かった」と読み違える。

**関連**: design_decisions 1 / D1439 / D1440 / Issue #1436 / #1442 / #1443 / #1479。

**その後**: 行動ごとの結果の予想 (`LLM_EXPECTED_RESULT_POLICY`、tool の `expected_result` 引数、行動ルールの予測の行、【前回の予測と実際】) は Issue #1631 で消した。予期の引数と同時に有効にさせない検査も一緒に消えた。行動の記録に残る `expected_result` の欄と、古いエピソードの下書きが予想を読む処理も、続く PR で消した。主観補完の LLM に `prediction_error` を書かせる指示は、古いエピソードを消す段で消す。world snapshot の `action_result_store` は `expected_result` を書かなくなった。版は 5 のままで、キーのある古い snapshot も読める。

予期の引数そのもの (`EXPECTATION_ARGUMENT_ENABLED`、期限のターン数 `EXPECTATION_UNDATED_TERM_TURNS` / `EXPECTATION_DATED_TERM_TURNS`、tool の `expectations` 引数、行動ルールの予期の行、書かれた予期を積む `ExpectationFormingService`) も Issue #1631 で消した。予期の清算・配り手・保存先も、続く PR で消した (D1439 / D1440 の「その後」)。

信念と想起の台帳 (`PredictionContextLedger`、`PREDICTION_CONTEXT_ID_ENABLED`) も Issue #1631 で消した。台帳を読む予期が無くなり、プロンプトにも出ない ID を行動の記録と想起に書くだけになっていた。行動の記録の `prediction_context_id` / `in_context_belief_ids`、想起の記録の `prediction_context_id`、trace の `prediction_outcome` も一緒に消えた。world snapshot と Being の snapshot はこれらのキーを書かなくなった。版は据え置きで、キーのある古い snapshot も読める。

## D1443. 予測の当否の材料は確定した予期だけから積み、受け取る側は受け取り済みの ID を材料と同じ store に持つ

**何を**: 予期の配り手 (D1440) に 3 つの受け取る側を登録する。確定した予期の当否を、頭に
あった信念への支持・反証の材料 (`ExpectationBeliefMaterialReceiver`)、思い出していた
エピソードの役に立った回数とずれの書き添え (`ExpectationRecallCreditReceiver`)、次に閉じる
chunk の主観補完への外れの受け渡し (`ExpectationChunkNoteReceiver`) にする。chunk の
`prediction_error` から信念と想起を動かしていた経路 (U4 の PREDICTION_ERROR / CONFIRMATION、
U9a / U9b) は外す (Issue #1443)。

**なぜ**:

- chunk の `prediction_error` は、LLM が空を返しても失敗した行動があると既定の文で上書き
  され、予期どおりの失敗が反証になっていた。外れたかどうかを 1 回の判断で決めていたので、
  ぶれもそのまま信念に届いた。予期の清算は 2 回続いた当否で確定する (D1440)
- 両方の経路を残すと、同じ外れを chunk と予期の両方から二重に数える

**決まり**:

- **材料にするのは確定だけ**: 暫定の外れ、期限切れ、形の判定で外した予期、予期になって
  いない予期は材料にしない。期限を過ぎて暫定の当否で確定したものは確定として扱う (D1440)
- **強さは本人の確からしさで決める**: ほぼ確実の外れだけを salience=high にし、次の固着を
  待たせない。それ以外の外れと、すべての当たりは low。確からしさは材料の文にも残し、固着の
  LLM にどれだけ動かすかを読ませる。当たりを high にしないのは、的中は繰り返してはじめて
  意味を持つという既存の扱い (U4) に合わせるため
- **頭に信念が無い当たりは積まない。外れは積む**: 支える相手の無い的中は、何もしなかった
  だけの当たりで水増しになる。外れは新しく学ぶ材料になる (design_decisions D1484 で
  「頭に」を「根拠の」に読み替えた)
- ~~**関連度で絞らない**: 頭にあった信念は、そのターンのプロンプトに載った信念すべてで、予期と
  関係の無い信念も含む。chunk 側にあった関連度のゲート (P3) は外した。#1414 までは、
  無関係な信念にも支持が積まれうる既知の弱点として残す~~ design_decisions D1484 で、
  頭にあったもののうち根拠と判断したものだけに返すようにした
- **受け取り済みの ID は材料と同じ store に、同じ呼び出しで書く** (#1479): 証拠バッファ、
  役に立った回数の記録、想起の記録が、それぞれ受け取り済みの ID を持ち、snapshot に入れる。
  固着が証拠を取り除いたあとも配り直しは届くので、証拠の有無では二度目を見分けられない
- **材料の ID は出来事の ID から決める**: `belief-evidence-{予期の ID}@{ターン}`。材料は
  エピソードに結びつかないので、`episode_ids` には予期の ID を置く (目的の清算と同じ扱い)
- **外れのずれは、思い出していたエピソードの、まだ書き添えの無い想起すべてに書く**
  (design_decisions D1484 で根拠のエピソードに絞った): 予期は
  持ったときの想起の ID を持たない。同じエピソードを別の場面で思い出した想起にも書かれうる
- **主観補完 LLM は外れたかどうかを判断しない**: 外れたで確定した予期が渡された chunk でだけ、
  何が違ったかを書かせる。渡されていない chunk では、LLM が書いても `prediction_error` は
  None にする。渡したのに LLM が失敗したか空を返したときは、外れたこと自体を予期の文から
  書く。外れは確定しているので、既定の文で外れを作っていた旧来の上書きとは違う
- **外れの受け渡しは run の中だけで持つ**: 開いている chunk と同じ寿命にする。chunk を閉じる
  前に run が終わると、その外れは chunk に渡らない。信念と想起の材料は別の受け取る側が
  store に書くので、失うのはエピソードの記述だけ。どの chunk に渡したかは
  `episodic_chunk_written` の `settled_miss_event_ids` で読める (この欄は外れの受け渡しと一緒に
  Issue #1631 で消した)
- **当たりの回数は、想起の記録が残っていなくても足す**: 役に立った回数はエピソードごとの
  数で、想起の記録を経由しない。旧経路は想起の記録に残ったエピソードにだけ足していた。
  外れのずれは想起の記録にしか書けないので、想起が再解釈で処理済みなら書き添えは 0 件になる。
  その件数は trace の `stamped_recalls` に残す (ずれの書き添えは Issue #1631 で消した)
- **SQLite の store は 1 本の接続を 1 つのスレッドから使う前提**: 受け取り済みの ID と材料を
  複数文で書くので、別スレッドが同じ接続で commit すると途中の状態が確定しうる。実験の run は
  メモリ上の store を使う。DB に移すとき (#1479) に接続とトランザクションの扱いを決める
- **受け取る側は、その記憶の機能が有効なときだけ登録する**: 証拠バッファは
  `BELIEF_EVIDENCE_ENABLED`、ずれの書き添えは `ERROR_DRIVEN_REINTERPRETATION_ENABLED` と想起の
  記録 (再解釈の LLM があるとき)、役に立った回数は `RECALL_HIT_BOOST_ENABLED`。配り手は
  episodic stack を組んだあとで作る。機能が有効なのに store が無くて登録できないときは起動時に
  warning を出し、配信の trace には登録された受け取る側の名前を残す (配り手と受け取る側、
  `ERROR_DRIVEN_REINTERPRETATION_ENABLED` は Issue #1631 で消した)

**比べた結果**: `docs/experiments/issue_1443_expectation_material/` に、過去 run の同じ 64 手で
材料の件数を前後で並べた。反証は 16 → 16 件で数は同じだが、予期どおりの失敗や「分からない」
を反証にしていた文が消えた。支持は 0 → 9 件。

**どうしないと壊れるか**: 受け取り済みの ID を別の store に持つと、片方だけ書けた状態が残り、
配り直しで材料が二重に積まれるか、積まれずに受け取り済みになる。chunk の経路を残すと、
同じ外れが二重に信念へ届く。

**関連**: design_decisions D1439 / D1440 / D1441 / D1452 / Issue #1414 / #1436 / #1442 / #1479。

**その後**: 確定した予期を信念の材料・想起の手柄・区切りのメモに返す受け取る側は Issue #1631 で消した。古いエピソードの区切りの `prediction_error` は、外れを決める清算が無くなったので、いつも空になる。

誤差駆動の再解釈 (`ERROR_DRIVEN_REINTERPRETATION_ENABLED`)、ずれを想起の記録に書き添える `stamp_prediction_outcome_for_episodes_by_being`、想起の記録の `prediction_outcome_error` と受け取り済みの出来事の ID も Issue #1631 で消した。Being の snapshot は `recall_buffer_received_event_ids` を書かなくなった。消す前の snapshot も読める。

役に立った回数 (`RECALL_HIT_BOOST_ENABLED` と的中の store) は、書き手を消したあと常に 0 で効いていなかったので、Issue #1631 の段 9 で消した。

## D1484. 予期の根拠は形と同じ呼び出しで 1 件ずつ問い、確定した当否は根拠にだけ返す

**何を**: 予期を書いたターンの清算の呼び出し (design_decisions D1440) に、頭にあった信念と
エピソードごとの Noul を同乗させる。「この予期は、この信念から出てきたか」「この出来事を
材料にしたか」。確率が閾値を超えたものだけを予期の根拠 (`ExpectationGrounds`) とし、形の
判定と一緒に集約へ渡す。確定の出来事は頭にあったものではなく根拠を運び、信念の材料・
役に立った回数・ずれの書き添えは根拠にだけ返る (Issue #1484)。

**なぜ**:

- 頭に載る信念は見えているものの名前で選ばれ、予期と関係が無くても載る。すべてに当否を
  返すと、いつも載る信念に支持が積まれて確信度が上がり、さらに載りやすくなる。エピソード
  も、役に立った回数が想起の順位を底上げするので、信念より速く同じ循環が回る
- #1483 で cue の語の一致による絞り込みを外した。判断は文だけで行い、ゲームの ID を使わない

**決まり**:

- **根拠は形と一緒に渡す**: `judge_shape` は根拠を省けない引数で受ける。形が判定済みなら
  根拠も判定済みで、確定の出来事が「根拠を判断していない」と「根拠が無い」を区別せずに
  済む。形の判定を経ずに照合だけで確定した予期 (集約の単体の経路) は、空の根拠を運ぶ
- **判断が得られないターンは根拠も形も渡さない**: 答えが 1 つでも使えなければ、どの予期にも
  渡さない (design_decisions D1440 と同じ)。形の判定を待つ予期は次のターンに根拠と一緒に問い
  直す。trace の `grounds` には `judged: false` と空の根拠を残す。頭にあったものすべてを根拠と
  みなす縮退はしない。それが悪循環そのものなので
- **閾値ちょうどは採らない**: 確率が閾値 (既定 0.5) を超えたものだけを採る。決定論の stub の
  迷った答えは 0.5 で、ちょうどを採ると smoke run で頭にあったものすべてが根拠になる
- **閾値は取りこぼしより誤って選ばないことを優先する**: 過去 run を組み直した実 Jev の試し
  (`docs/experiments/issue_1484_expectation_grounds/`) の清算できる予期では、人の当否で 0.5 で選んだ
  19 件のうち根拠でないものは 2 件で、根拠である 22 件のうち 6 件を取りこぼした。0.4 では根拠でないものが 11 件になる。
  取りこぼしはその予期の当否が返らないだけで済むが、誤って選ぶと関係の無い信念に材料が積まれる。
  ただしエピソードは 120 字で切った抜粋で問うたので、全文で問う本番では確率が動く。閾値は暫定で、
  全文で確かめ直す
- **根拠を絞っても、形の判定が甘いと水増しは残る**: 同じ試しで「清算できる」と判定された
  45 件のうち 15 件は、何が分かるかを述べない「確認できる」だけの予期などで、ほぼ必ず当たる。
  そこに選ばれた根拠が、清算できる予期の根拠 19 件のうち 8 件あった。形の問いの見直しは #1489
- **問いの数に上限を置く** (既定 12): 上限は 1 回の呼び出し全体で数え、先に書いた予期から、
  信念、エピソードの順に埋める。外したものは問わず、根拠にもせず、trace の `omitted` に
  `over_limit` で残す
- **本文は形を問うターンに記憶の store から引く**: 予期は頭にあったものを ID でしか持たない。
  プロンプトの想起と同じ store (信念、エピソード、有効な再解釈) を読む。見つからないもの、
  読む途中で例外が出たものは問わずに外し、理由を trace に残す。1 件の読み失敗で形の判定まで
  止めない。信念は状態を見ずに ID で引くので、置き換えられた信念も前の本文で問う。台帳 (`PredictionContextLedger`) に本文を載せて予期に持たせる案は、snapshot に
  本文が重複して載るので採らなかった。そのため、プロンプトに載せてから形を問うまでに再解釈で
  書き換わったエピソードは、書き換わったあとの本文で問う
- **根拠が無い当たりはどこにも返さない。外れはいまの扱いを保つ**: 外れは根拠が空でも新しく
  学ぶ材料として信念の証拠に積み、指す信念は空になる
- **snapshot の互換は保たない**: #1484 より前に保存した、形を判定済みの予期と確定の出来事には
  根拠が無い。空と捏造せずに読み込みを止める。閉じた予期も形を判定済みなので、予期の引数を
  有効にした #1484 より前の snapshot は、ほぼ再開できない。形の判定を待つ予期だけなら読める
- **問わなかったものは根拠にならず、問い直さない**: 上限を超えたもの、本文が無いもの、読み
  失敗、store の未配線 (`text_read_failed: InMindStoreUnwired`) は、その予期の根拠から外れた
  まま決まる。確定の出来事と受け取る側の trace からは「選ばれなかった」と区別できないので、
  清算の trace の `omitted` と集計スクリプトの「問わずに外したもの」で数える
- **閾値は stub の迷った答えより下げない**: 閾値を 0.5 未満にすると、stub の run で頭にあった
  ものすべてが根拠になる

**trace での数え方**: `expectation_settlement` の `grounds` に、予期ごとの頭にあったもの、
問うたものと確率、外したもの、選んだ根拠が残る。`scripts/expectation_grounds_report.py` が、
信念とエピソードごとに「頭に載った回数」「根拠に選ばれた回数」「返った材料の数」を並べる。
載った回数に比例して材料が増えていれば、悪循環が残っている。

**どうしないと壊れるか**: 頭にあったものすべてに当否を返すと、関係の無い予期の当たりで
いつも載る信念が強まり、外れのたびに関係の無い信念が反証され、関係の無いエピソードが
解釈し直される。判断が得られないときに頭にあったものすべてへ倒すと、Jev が落ちている
あいだだけ悪循環が戻り、trace の上では区別できない。

**関連**: design_decisions D1439 / D1440 / D1443 / Issue #1436 / #1414 / #1454 / #1467
(つながりの強化も根拠にだけ返す決まりを渡す)。

**その後**: 根拠の選択 (`grounds.py`、`EXPECTATION_GROUNDS_*`) は、予期の清算と一緒に Issue #1631 で消した。台帳 (`PredictionContextLedger`) も、続く PR で消した (D1441 の「その後」)。

## D1414. ~~想起は状況の 6 つの欄から、残す欄を選んだマスクごとに引き、結果を混ぜずに持つ~~

**取り消し (design_decisions D1414-8)**: 6 つの項目で表すことは残す。残す項目を Jev に選ばせること、場所を残した組と捨てた組の 2 本で引くことはやめた。全部の項目をつなげて 1 本で引く。

**何を**: 想起のきっかけを、場所 / 相手 / 自分の状態 / やろうとしていること / いま起きたこと /
未解決のこと の 6 つの欄 (`Situation`) で表す。欄の値は名前や文だけで持つ。場所以外の 5 つの欄は、
残すか捨てるかを Jev に欄ごとに問う (`field_selection_questions`)。残した欄から、場所を残した
マスクと捨てたマスクの 2 本を作り、マスクごとに信念を引いて別々の一覧で持つ
(`SituationBeliefRecall`)。部品は `application/being/recall/` に置き、まだゲームには繋いでいない
(Issue #1414)。

**なぜ**:

- いまの cue は、見えているものの名前と場所の ID に偏り、ゲームの ID に依存する。
  Issue #1414 の集計では、頭に載った信念の 88% が、そのどちらかの一致で選ばれていた。いくつもの観点の文を 1 本につなげて問い
  合わせると、平均に寄ってどの観点にも中途半端になる
- 残すか捨てるかは規則で書くとゲームの都合が入り込む。Jev は文を生成せずに選ぶだけなので、
  問い合わせを書かせるより向いている。規則は問いの説明に例として渡す

**決まり**:

- **場所は Jev に問わない**: 場所を捨てると別の場所での似た経験が、残すとこの場所についての
  知識が取れる。危機のときもどちらかに決め打ちしないので、2 本を必ず引く。選んだ欄に場所を
  入れると `FieldSelection` が拒む
- **判断が得られなければ全部の欄に縮退する**: Jev が答えなかったか、答えが欠けたか、選択肢に
  無い答えが返ったら、場所以外の 5 つの欄をすべて残す。一部の答えだけを採ることはしない。
  理由は trace で数えられるように 3 つの分類 (`judgment_unavailable` / `answer_missing` /
  `answer_invalid`) で `degraded_reason` に持ち、中身は `degraded_detail` に置く。`judge` が
  投げた例外は `FieldSelection.unavailable` で縮退に変える。縮退しても場所の有無の 2 本の検索は
  走る
- **閾値を持たない**: 欄ごとに「残す / 捨てる」の選択肢で問い、確率の高い方を採る。誤っても
  行動は実行されず、頭に載る信念が変わるだけ (design_decisions 234)。その代わり、欄ごとの
  答え・確率・出所 (Jev か stub か) を trace に残し、どの程度の確信で残した欄かを後から読める
  ようにする
- **点は 1 段目の手法の点だけ**: 作った時刻による新しさと重要度は入れない。どのマスクにも
  一致しない信念は載らない。いまの経路では 6% の信念が新しさと重要度だけで選ばれていた。
  手法は #1453 と同じ `ITextCandidateNarrower` で、最初は 2 字組の BM25
- **一覧の重複は先の一覧に残し、除いてから件数を切る**: 後の一覧からは外し、外したことを
  `duplicates` に残す。後の一覧は先の一覧と重なった数だけ余分に引き、重複を除いたあとで
  `top_k` 件に切る。2 本は場所の文しか違わないので、重なったまま切ると場所を捨てた一覧が
  空になり、別の場所での似た経験が取れない
- **枠は一覧から順番に 1 件ずつ取る**: 場所を残した一覧の 1 位、捨てた一覧の 1 位、場所を
  残した一覧の 2 位、の順。一覧どうしの点は問い合わせ文が違うので比べない。2 段目の並べ直し
  と枠の割り当ては、確かめ方 (#1414 の PR 4) の結果で決め直す
- **値の無い欄だけを残したマスクは引かない**: 問い合わせ文が空のマスクは手法に渡さず、
  空の一覧として残す。埋め込みの手法は空の文にも何かを返しうる
- **trace に残すのは、取れた記憶より、どの欄を残したか**: 残した欄、欄ごとの答え、縮退の理由、
  手法の名前、候補の数、マスクごとの欄と問い合わせ文と引けた信念と重複を `to_trace_payload`
  に載せる。候補の数があれば、何も載らなかったときに、信念が無かったのか一致しなかったのかを
  分けられる

**これからの PR**: ゲームの観測と持ち物から欄を組み立てて【関連する学び】を切り替える PR、
清算の Jev の呼び出し (design_decisions D1440) に欄の問いを同乗させる PR (#1484 のあと)、
確かめ方の PR に分ける。分け方は Issue #1414 のコメントにある。

**どうしないと壊れるか**: 欄をつなげて 1 本で引くと、きっかけの偏りが平均に紛れて見えなく
なる。縮退を空のマスクにすると、判断が得られないターンに何も思い出さず、それが判断の結果
なのか失敗なのかを trace から区別できない。

**関連**: design_decisions D1440 / D1443 / D1463 / 5 / 234 / Issue #1414 / #1436 / #1453 / #1454 / #1484。

## D1414-2. 状況の項目は観測の契約に変換してから組み、profile で有効にしたときだけ【関連する学び】を切り替える

**何を**: `SITUATION_BELIEF_RECALL_ENABLED` を有効にすると、【関連する学び】を状況の項目から引く
(design_decisions D1414-8)。ゲームの観測と行動結果は観測の契約 (design_decisions D1463) に変換し、
`assemble_situation` が契約とエージェントの持ち物 (目的、直前の内心、清算待ちの予期) だけから
項目を組む。結果は trace `situation_belief_recall` に、`semantic_passive_recall` の代わりに残す。
既定は無効で、無効の run は変わらない (Issue #1414)。

**決まり**:

- **項目は観測の契約から取る**: 場所は場所が分かっている最も新しい観測の場所、相手は自分以外の
  主体の名前と、自分以外が言った・書いた観測の情報源。自分の状態は経路が「自分の体の状態」の
  観測の本文、いま起きたことはそれ以外の観測の本文 (自分の行動の結果を含む)、未解決のことは
  清算待ちの予期。どれも新しい順に数件だけ取る。古い出来事まで入れると、いまの状況が問い合わせ
  文の中で薄まる
- **予期は未解決の項目にだけ入れる**: Issue では「やろうとしていること」の材料にも挙げたが、
  2 つの項目に同じ文が入ると、1 本の問い合わせ文の中でその文が 2 回数えられ、点が偏る。やろうと
  していることは目的と直前の内心にする
- **目的は読み取りだけの口から取る**: 【現在の目的】を描く口は、目的がまだ無いと書き込む。
  想起が先に呼ぶと書き込みの順が変わるので、書き込まない `_reflect_objective_provider` を使う
- **契約に写せない観測は 1 件ずつ飛ばして数える**: ループ警告、目的の振り返り、時刻の無い
  観測、契約の検査に通らない観測は項目に入れず、理由ごとの件数を trace の
  `skipped_observations` に残す。1 件のためにそのターンの想起全体を落とさず、項目の材料が
  減ったことを見えるようにする
- ~~**欄の選択はまだ無い**: 清算の呼び出しに欄の問いを同乗させるまで (#1484 のあと)、選択が
  無いこと (`no_selection`) を縮退の理由にして全部の欄で引く~~ 項目を選ぶ仕組みはやめ、いつも全部の
  項目で引く (design_decisions D1414-8)
- **件数と出す条件は受動想起と共有する**: 件数は `SEMANTIC_PASSIVE_TOP_K`。0 のまま有効にすると
  何も引かずに有効に見えるので、設定の時点で止める。episodic の stack や信念の store が無いまま
  有効にしたときも、プロンプトを組む前に止める
- **失敗しても組み立ては止めない**: 引く途中の例外は ERROR で記録し、trace に `failed` を残して、
  【関連する学び】を出さない。成功したときは `failed` を None で残し、何も引けなかった結果と
  失敗を見分けられるようにする。trace の記録が失敗しても、引けた信念は捨てない
- **表示は信念の ID の順に固定する**: 枠は一覧から順番に埋めるが、本文は ID の順に並べる。
  同じ信念の組なら同じ文字列にし、並びの揺れでプロンプトのキャッシュを壊さない
  (design_decisions 1、受動想起の `format_semantic_recall_section` と同じ扱い)。予測の台帳へ
  渡す ID も、本文に出した信念と同じ組にする

**限界**: 場所は観測の契約の場所から取る。契約への変換 (design_decisions D1463) は、
構造化データに場所の無い観測と自分の行動の結果に、受け取った時点のいまいる場所を入れる。
そのため、移動する前の古い観測にも、いまの場所が付きうる。観測も行動結果も無いターンは
場所の項目が空になる。

**関連**: design_decisions D1414 / D1463 / Issue #1414 / #1484。

状況の項目から引く想起 (`SITUATION_BELIEF_RECALL_ENABLED` / `_NARROWER`) は、記憶の部品の撤去 (#1631) の #1656 で消した。【関連する学び】は受動想起 (`SEMANTIC_PASSIVE_TOP_K`) が出す。

【関連する学び】 (`SEMANTIC_PASSIVE_TOP_K` と `SemanticPassiveRecallService`) は、記憶の部品の撤去 (#1631) の #1786 で消した。

## D1414-3. ~~次のターンの想起で残す欄は、ターンの終わりの清算の呼び出しで毎ターン問い、予期の判定とは分けて読む~~

**取り消し (design_decisions D1414-8)**: 残す項目を選ばなくなったので、清算で問うのをやめた。予期が 1 件も無いターンには、清算は Jev を呼ばない形に戻した。

**何を**: 状況の欄から引く run (design_decisions D1414-2) では、ターンの終わりの清算
(design_decisions D1440) の Jev の呼び出しに、場所以外の 5 つの欄を残すかの問いを足す。予期が
1 件も無いターンにも、欄の問いだけで呼ぶ。選んだ欄は `NextTurnFieldSelections` に清算したターンの
番号と一緒に入れ、次の手のプロンプトを組むときに使う。清算の trace `expectation_settlement` の
`field_selection` と、想起の trace `situation_belief_recall` の両方に残る (Issue #1414)。

**なぜ**:

- 想起はプロンプトを組むとき (行動の前)、清算はターンの終わり (行動の後) に行う。材料 (直近の
  出来事と清算待ちの予期) が同じなので、呼び出しを増やさずにまとめられる
- 予期が無いターンだけ前のターンの選択を使い回す案は採らない。場面が変わっても古い選択で
  引くことになり、呼ぶかどうかを決まりで分けること自体が規則による判断になる。1 ターンあたりの
  時間と費用は最初の実 run で測る (#1414 のコメント)

**決まり**:

- **欄の答えは予期の判定とは分けて読む**: 欄の答えを先に読み、そのあとで予期の判定を読む。
  予期の答えが欠けても欄の選択は採り、欄の答えが欠けても予期は判定する。どちらかの崩れで
  もう片方を縮退させない。Jev が答えなかったときは両方が縮退する
- **選択は清算したターンの番号と一緒に持つ**: プロンプトは次の手を受け取ってターン番号を
  進める前 (Phase A) に組むので、清算したターンと同じ番号のときだけ使う。番号が違えば
  `stale_selection`、一度も清算していなければ `no_selection` を理由に全部の欄で引く。清算が
  呼ばれなかったターンに、前の場面の選択を使い回さない
- **清算が途中で失敗したら、欄の選択も縮退させてから投げ直す**: 古い選択を残さない。ただし
  同じターンを 2 回清算しようとした配線の誤りでは、1 回目に選んだ欄を
  上書きしない
- **欄だけを問うターンも清算の trace に残す**: 予期が無いターンの `skipped_reason` は
  `nothing_to_judge` のまま、欄の問いの生の答えと、答えが得られなかったときの理由
  (`unavailable_reason`) を残す。Jev の失敗を数えるときに、このターンを取りこぼさない
- **清算を切った run では欄を問わない**: 想起の側は `settlement_disabled` を理由に全部の欄で
  引く。最初のターンや再開した直後の `no_selection` と分けて数えられるようにする。状況の欄から
  引かない run では、清算は欄を問わず、予期が無いターンに Jev を呼ばない (いままでどおり)

**snapshot に入れない (design_decisions 27 の例外)**: 次のターンの選択は、1 ターンで作り
直せる一時的な状態なので、run の中だけで持つ。27 が防ぐのは、失うと連続性が静かに壊れる
状態で、これは失っても次の清算で戻る。再開した直後の 1 ターンは `no_selection` を理由に
全部の欄で引き、trace にそう残るので、失ったことは見える。清算の時系列 (design_decisions
D1440) と同じ扱い。

**範囲外**: 自分の状態の「平常 / 注意 / 危機」への丸めは、同じ呼び出しで問う予定で、
別の PR にする。

**関連**: design_decisions 27 / D1414 / D1414-2 / D1440 / D1484 / Issue #1414。

## D1414-4. ~~自分の体の状態は、清算の呼び出しで「平常 / 注意 / 危機」の帯に丸め、帯の文を生の本文に足す~~

**取り消し (design_decisions D1414-8)**: 体の具合を 3 段階に判定させる処理はやめた。判定した文の使い道が問い合わせ文に 1 行足すことしかなく、引ける信念を変える証拠が無かった。

**何を**: 状況の欄から引く run では、ターンの終わりの清算の呼び出しに、欄の問い
(design_decisions D1414-3) と並べて、自分の体の状態を「平常 / 注意 / 危機」のどれかに丸める問いを
足す。読んだ帯は欄の選択と同じ保存先に、清算したターンの番号と一緒に持ち、次の手のプロンプトで
「体の状態は危機」のような文として自分の状態の欄の先頭に足す。生の本文 (体の状態の観測) も残す
(Issue #1414)。

**なぜ**:

- 帯を入れる狙いは、エピソードの書き込み時のキー (#1454) と語を揃えること。キーの例は
  「囲まれた・危機・入口へ走って離脱・逃げ切れた」で、帯の語が入っている。問い合わせの側にも
  帯の文があれば、環境ごとの言い回し (HP の数字、空腹の段階の表示) が違っても、キーと一致する
- 生の本文を残すのは、いまの信念の文にはまだ帯の語が無いから。帯の文だけにすると、いまの
  信念とは一致しなくなる
- 丸めは規則で書かない。HP や空腹の段階の表し方は環境ごとに違い、規則に環境の都合が入る

**決まり**:

- **材料は清算の時系列**: 時系列の「行動」には体の状態の観測の本文も入っているので、清算の
  state は変えない
- **体のことが書かれていなければ「分からない」**: 選択肢に「分からない」を足し、そのときは
  帯を付けない (理由は `body_not_mentioned`)。平常に丸めると、空腹や怪我が続いていても観測が
  時系列から流れたあとに「体の状態は平常」が付き、いまの体と食い違う。書き込み時のキーの
  平常に当たるぶん、帯が無いより悪い (セルフレビューの指摘)
- **帯は欄とは分けて読む**: 帯の答えが欠けても欄の選択は採り、帯だけを付けない。Jev が
  答えなければ両方が縮退する。帯が無いときは帯の文を作らず、生の本文だけで引く。理由は
  想起の trace の `body_band` と、清算の trace の `field_selection.body_band` に残る
- **欄の選択と同じ決まりで渡す**: 清算したターンと同じ番号のときだけ使い、古い帯や、清算を
  切った run の帯は付けない

**関連**: design_decisions D1414 / D1414-2 / D1414-3 / Issue #1414 / #1454。

## D1414-5. ~~残す欄は、欄を選択肢にした 1 問の確率の上位を固定の件数だけ採り、欄の値を Jev に見せる~~

**取り消し (design_decisions D1414-8)**: 残す項目を選ぶこと自体をやめたので、この問いの形も使わない。

**何を**: 次のターンの想起で残す欄 (design_decisions D1414-3) を、欄ごとに「残す / 捨てる」を問う 5 問から、
「次の判断にいちばん効く欄はどれか」を問う 1 問に置き換える。選択肢は場所以外の 5 つの欄で、Jev が
返す選択肢ごとの確率の上位 `SITUATION_FIELDS_TO_KEEP` 個 (既定 2) を残す。清算の state には、
そのターンの終わりの状況の欄の値を「いまの状況」として足す (Issue #1414)。

**なぜ**:

- 過去 run の 40 場面を実 Jev で確かめたところ (`docs/experiments/issue_1414_situation_recall/`)、
  5 問の形では残す確率がほとんど 0.5 を超え、捨てたのは「相手」の 5 場面だけだった。欄を選ぶ
  仕組みが「全部の欄で引く」とほぼ同じになっていた。1 問にすると欄どうしを比べさせられる
- 清算の state には出来事の時系列しか無く、Jev は組み立てた欄の値を知らずに答えていた。値が空の
  「未解決のこと」も残していた
- 形はユーザーと決めた (#1414 のコメント)

**決まり**:

- **閾値は持たない**: 上位何個と決めるだけで、確率の大きさは問わない (design_decisions 234)。同じ
  確率の欄は、欄の決まった順で先のものを採る
- **確率が全部の選択肢にそろわなければ縮退する**: 答えが欠けたか、確率の欠けた欄や数でない (NaN を
  含む) 欄があれば、全部の欄で引き、理由を持つ。一部の確率だけで並べない
- **欄の値は欄を問う清算にだけ見せる**: 状況の欄から引かない run の清算の state は変えない
- **見せる値には帯を入れない**: 体の帯はこの清算で決めるので、ターンの終わりに組む状況には入らない。
  いまいる場所の名前も渡さず、場所の欄は観測から分かる範囲にする。場所は Jev に問わない欄で、
  判断の文脈として見せるだけ
- **状況を組めなくても清算は止めない**: 例外は記録し、欄の値を見せずに問う。清算の trace の
  `field_selection` に、値を見せたか (`situation_shown`) と、組めなかった理由または飛ばした観測の件数
  (`situation_note`) を残す。値を見ずに選んだ選択を、ふつうの選択と見分けられるようにする
- **trace の欄ごとの答え**: 欄ごとの確率、残したか、出所を `judgments` に、残す数を `keep` に残す

**ターンの終わりの状況と、次のプロンプトの状況はずれる**: 欄の値はターンの終わり (清算の前) に組み、
選んだ欄は次の手のプロンプトで組み直した状況に使う。次の 3 つのずれは受け入れる。

- 自分の状態の欄には、まだ体の帯が入らない。帯はこの清算で決まるため。体の観測が無いターンは空に
  見えて選ばれにくくなるので、問いの説明に「体が危ないかは出来事の時系列から読み、危ないなら自分の
  状態を選ぶ」と書く
- 未解決のことの欄には、この清算で当たり外れが決まる予期も入る。清算の前に組むため
- 上位に入った欄が、次のプロンプトで空のこともある。値の空かどうかでは選び直さない。上の 2 つの
  ずれがあり、ターンの終わりの空は次のプロンプトの空と一致しない

**関連**: design_decisions 234 / D1414 / D1414-3 / D1414-4 / Issue #1414 / #1493。

## D1414-6. メモ・記憶・状況評価の道具の結果は、環境の観測として写さない

**何を**: ゲームの観測を契約に変換する入口 (design_decisions D1463) で、`memo_` / `memory_` で始まる道具と
`assess_situation` の結果を、「自分の行動の結果」として写さずに拒む。理由は目的の振り返りやループ警告と
同じ `being_inner_record` (Being 自身の記録)。状況の項目の「いま起きたこと」には入らず、飛ばした観測の
件数として trace に残る (Issue #1414)。

**なぜ**:

- 過去 run の 40 場面を確かめたところ (#1493)、14 場面で「いま起きたこと」に「メモを追加しました（ID: …）」
  のような道具の応答が入っていた。Being が自分の記録を読み書きした結果で、環境で起きたことではない。
  ID のような文字列も含む
- 項目の中身が環境固有になっていないか、というユーザーの懸念に応える。項目の組み方は契約だけを見ているが、
  変換の入口がこれらを通していた

**決まり**:

- **見分けるのは道具の名前**: 記憶の道具は接頭辞 `memo_` / `memory_` で名付けられている
  (`tool_constants.py`)。2 段階ターンの `assess_situation` も、考えてから道具を選ぶための道具で、環境に
  働きかけない
- **選択肢を足さずに拒む**: 契約の経路を増やさず、写せない観測として拒む (design_decisions D1463 の
  「写せない観測は選択肢を足さずに拒む」と同じ)
- **道具のカタログの分類と一致させる**: カタログでは、環境に働きかける道具が `world_action`、メモが
  `auxiliary`、記憶と状況評価が `meta_cognitive` に分類されている。`world_action` 以外を拒むことと、道具の
  名前の定数がすべてカタログにあることを、カタログ全体の総当たりの試験で確かめる。道具を足せば自動で
  検査の対象になる。変換の入口からカタログの分類を引かないのは、契約の入口を LLM の道具の定義に依存
  させないため
- **飛ばした観測は理由と種類で数える**: 状況の項目の trace の `skipped_observations` は、
  「being_inner_record: memo_add」のように、理由に観測の種類か道具の名前を添える。拒んだもの・漏れた
  ものを trace で読めるようにする
- **道具の名前が無い結果は写す**: 古い snapshot から戻した結果など、道具の名前が無いものは見分けられ
  ないので、これまでどおり自分の行動の結果として写す

**取り違えていたこと**: 確かめ方の README では、「【心の声】」も「いま起きたこと」に混ざると書いた。これは
素材の run (2026-07-26 のコード) だけの書き方で、2026-07-27 のコミット 4a1e69be3 で、内心を道具の結果の
文に付け足すのはやめている。いまのコードでは起きないので、この PR では扱わない。

**関連**: design_decisions D1463 / D1414-2 / Issue #1414 / #1493。

## D1414-7. 文字の 2 字組は、改行・句読点・空白・記号の区切りをまたいで作らない

**何を**: 候補を絞る文字の 2 字組の BM25 (`text_candidate_narrowing.py`) で、文字列を改行・句読点・空白・
記号で区切り、区切りの中だけで 2 字組を作る。区切りで 1 文字だけ残った断片は、ほかに 2 字組が無いときだけ、
その文字で比べる (Issue #1414)。

**なぜ**: これまでは区切りを消してから 1 本につないで切っていた。想起の問い合わせ文は状況の項目の値を改行で
つなぐので、「観測拠点跡 (廃屋)」と「ノア」の境目に「屋ノ」のような無い言葉が生まれていた。ユーザーの指摘で
直す。最初の PR のセルフレビューで同じ点が LOW として挙がっていたが、「埋め込みを足すときに決め直す」として
直さなかった。その判断は誤りだった。

**影響**: 信念を作る前の判定 (#1453) も同じ部品を使う。過去の snapshot の似た組 96 組で、相方が上位 K 件に
入る割合を直す前と後で測ったところ、K=1 で 74%、K=3 で 96%、K=5 で 100% と変わらなかった
(`scripts/jev_belief_create_gate_measure.py --port stub`)。

**限界**: 区切りで 1 文字だけになった語は、2 字組のある文では比べない。「食料:3 水:2」では「水」が検索から
落ちる。直す前も「3水」「水2」のような無い並びになっていただけで、「水」では当たっていなかった。小数も
「3.5」が「3」と「5」に割れ、数だけが違う信念の差は見えにくい。どちらも 2 字組の手法の限界で、語に分ける
手法に替えるときに直る。

**採らなかったこと**: 「った」「ている」のような語尾の 2 字組を決まりで外すこと (ひらがなだけの 2 字組を外す
など)。決まりでは語尾と、ひらがなで書いた中身のある語を見分けられない。語に分けたいなら、形態素解析や埋め込みに
手法を差し替えて比べる (`ITextCandidateNarrower`)。形態素解析では、辞書に無い固有名詞の扱いを確かめる。

**関連**: design_decisions D1414 / Issue #1414 / #1453。

文字の 2 字組の BM25 (`text_candidate_narrowing.py`) は、使い手だった作る前の判定と一緒に、記憶の部品の撤去 (#1631) の #1787 で消した。

## D1414-8. 想起は状況の全部の項目をつなげた 1 本の問い合わせで引き、上位 3 件を載せる

**何を**: 状況の 6 つの項目 (`Situation`) の値を、項目の決まった順に改行でつないだ 1 本の文 (`Situation.query`) で
信念を引き、点の高い順に `top_k` 件 (既定 3) を【関連する学び】に載せる。残す項目を Jev に選ばせること
(design_decisions D1414 / D1414-3 / D1414-5)、場所を残した組と捨てた組の 2 本で引くこと、体の具合を判定させる
こと (design_decisions D1414-4) はやめ、`selection_store.py` / `body_band.py` と設定
`SITUATION_FIELDS_TO_KEEP` を消した。清算 (design_decisions D1440) は予期が 1 件も無いターンには Jev を呼ばない
形に戻した (Issue #1414)。

**なぜ**:

- 残す項目を選ばせても、載る 3 件はほとんど変わらなかった。保存した 40 場面を実 Jev で回したところ、
  全部の項目で引いた 3 件と違ったのは、項目ごとに問う 5 問の形で 1/40 場面、1 問の形で 6/40 場面だった。
  その差のために毎ターン Jev を呼ぶ費用は見合わない (`docs/experiments/issue_1414_situation_recall/`)
- 場所を入れた検索と抜いた検索の 2 本は、40 場面中 30 場面で上位 3 件がまったく同じだった (2 字組を直した design_decisions D1414-7 のあと、`results_plain.json` の `same_three_without_place`。この集計は Issue #1498 でスクリプトから外したので、再現は PR 1497 のマージ時点のスクリプトで行う)。長い問い合わせ文の
  中で場所の名前は数文字で、入れても抜いても点がほとんど動かない
- Issue #1414 より前の想起で同じ 3 件が続けて並んだこと (16/36) が減ったのは、状況の項目で引く方式全体の効果で、項目の
  選び方の効果ではなかった。どの項目を 1 つ抜いて引いても 4/36 以下に収まった
- 単純な形なら、想起の部品は観測の契約と文だけで動き、ゲームの都合を持ち込まない。ほかの環境でも同じ部品を使える

**どうしないと壊れるか**: 選ぶ仕組みを残したまま使わないと、清算が毎ターン Jev を呼び続け、費用だけがかかる。
2 本の検索を残すと、trace で何が効いたかを読む手間が増える。

**限界**: 1 本の問い合わせでは、値の多い項目 (いま起きたこと) の言葉が点を左右しやすい。体の危険の語がある 32 場面では、体に関わる信念が載った枠が Issue #1414 より前の想起の 26/96 から 16/96 に減った。手法は
`ITextCandidateNarrower` で差し替えられるので、形態素解析や埋め込みと比べるときにあわせて確かめる。

**関連**: design_decisions D1414 / D1414-3 / D1414-4 / D1414-5 / D1414-6 / D1414-7 / Issue #1414。

状況の項目から引く想起 (`SITUATION_BELIEF_RECALL_ENABLED` / `_NARROWER`) は、記憶の部品の撤去 (#1631) の #1656 で消した。【関連する学び】は受動想起 (`SEMANTIC_PASSIVE_TOP_K`) が出す。

## D1498. 信念の絞り込みは文字の 2 字組のままにし、形態素解析の手法は比べた記録だけ残して外す

**何を**: 状況の想起と信念を作る前の判定で候補を絞る手法 (`ITextCandidateNarrower`) は、文字の 2 字組の BM25
(`char_bigram_bm25`) のままにする。形態素解析で語に分けてから BM25 にかける手法を Janome と SudachiPy で作り、
保存した 40 場面で比べたうえで、実装と依存 (janome / sudachipy / sudachidict-core) は外した。比べた記録は
`docs/experiments/issue_1498_narrower_comparison/` に残す。外す前の実装はコミット `ef0c3a06` にあり、README の
「再現」の手順で動かせる (Issue #1498)。

**なぜ**:

- 体が危ない場面で体に関わる信念が載る枠が減った件 (design_decisions D1414-8 の限界) は、語に分けても戻らなかった。
  96 枠のうち 2 字組 16、Janome 14、Sudachi 12。問い合わせ文が長く (この 32 場面の平均で 440 字)、体の語がその中の数語に
  すぎないことが原因で、語の切り方を替えても解けない
- 同じ 3 件が続けて並ぶ割合は 2 字組が同じか少なく、信念を作る前の判定の相方と人の名前の当たりは 2 字組が同じか多かった。
  語に分けたほうが当たったのは場所の名前だけ
- 辞書に無い名前で、解析器によっては名前がまったく当たらなくなる。ひらがなの人名「ことは」は Janome では語が何も残らず、
  地名「狼煙台」は Sudachi では文によって「狼 / 煙台」と「狼煙 / 台」に切れ方が変わる。2 字組には、名前がまったく当たらない
  場合は無い。環境を取り換える前提 (#1436) では、この失敗のほうが重い
- 使わない手法のために、約 90 MB の依存を CI と実行環境に載せ続けない

**どうしないと壊れるか**: 形態素解析を既定にすると、環境ごとの名前の切られ方を確かめないまま、名前で引けない信念が
静かに生まれる。もう一度試すときは、その環境の名前で `ef0c3a06` の `scripts/narrower_unknown_name_probe.py` と同じ確かめをする。

**体に関わる信念が減った件は、いまは手を打たない**:

- 前の想起の 26 件が、その場面に合った信念だったかは読んでいない。減ったことが悪くなったことかは、まだ分からない
- 長い問い合わせ文に強い手法として、埋め込みを #1454 (エピソードの側の引き方) の比較に入れる。信念の検索も、同じ
  `ITextCandidateNarrower` の差し替えで埋め込みを試す

**限界**: 品詞の残し方は 1 通りしか試していない。素材は 1 本の run の 4 人で、辞書に無い名前の確かめは 18 個 (作った名前 15 個、
この run の地名 3 個)。

**関連**: design_decisions D1414-7 / D1414-8 / Issue #1498 / Issue #1454 / Issue #1414。

絞り込みの差し替えの部品 (`text_candidate_narrowing.py`) は、記憶の部品の撤去 (#1631) の #1787 で消した。

## D1454. 埋め込みの手法は絞り込みの差し替えとして足し、作る部品・ベクトルの索引・縮退を分けて差し替える

**何を**: `ITextCandidateNarrower` の実装として、文の埋め込みで候補を絞る手法を足した。profile の
`SITUATION_BELIEF_RECALL_NARROWER` / `BELIEF_CANDIDATE_NARROWER` に名前を書くと選べる。既定は `char_bigram_bm25` のまま変えない (Issue #1454)。

- `qwen3_embedding_8b_openrouter`: OpenRouter の `qwen/qwen3-embedding-8b`。キーは環境変数 `OPENROUTER_API_KEY` から読み、`.env` は読まない。
  無ければ `OPENAI_API_KEY` を使うが、OpenRouter のキー (`sk-or-` で始まる) のときだけにする。本物の OpenAI のキーを第三者のホストに送らない
- `ruri_v3_30m` / `ruri_v3_70m` / `ruri_v3_130m` / `ruri_v3_310m`: 手元の Ruri v3 (Apache-2.0)。任意の依存 `embedding-local` (sentence-transformers と PyTorch) が要る

部品は 3 つに分け、それぞれ差し替える。

| 部品 | 役目 | いまの実装 |
|---|---|---|
| `ITextEmbedder` | 文をベクトルにする。問い合わせ文と検索される文を別の役割で渡す | `OpenRouterEmbedder` (問い合わせ文にだけ英語の指示文を付ける)、`RuriEmbedder` (「検索クエリ: 」「検索文書: 」を付ける) |
| `IVectorIndex` | ベクトルを持ち、候補の中から近い順に引く | `InMemoryExactVectorIndex` (手元のメモリで全件を行列積で比べる) |
| `FallbackNarrower` | 埋め込みを得られないとき 2 字組で絞り直し、理由を返す | API の手法だけを包む |

**なぜ**:

- 体が危ない場面で体に関わる信念が載らない件 (design_decisions D1414-8、D1498) は、問い合わせ文の長さが原因で、語の切り方では解けなかった。
  長い文の意味を 1 本のベクトルにする埋め込みを比べる (結果は `docs/experiments/issue_1454_embedding_comparison/`)
- ベクトルの比べ方は自前のループで書かず、numpy の行列積にする。信念は 1 人数十件で、30 件を比べるのに 0.06 ms、1 万件でも 10 ms ほど。
  近似検索の索引 (sqlite-vec、faiss など) は 10 万件を超える規模で効くもので、いまは要らない。エピソードを引くとき (Issue #1454 の後の PR) に
  件数を見て、`IVectorIndex` の実装として足す
- 1 回の想起の時間は、ほぼ全部が文をベクトルにする時間になる。API は provider の待ち時間で、1 回 0.8 秒 (中央値) から 20 秒の時間切れまで揺れた

**決まり**:

- **API の失敗は 2 字組へ縮退し、縮退を trace に残す**。通信・状態コード・応答の形・次元の食い違いを `EmbeddingUnavailableError` にそろえ、
  `FallbackNarrower` が 2 字組で絞り直す。縮退先を cue の完全一致にしない。trace `situation_belief_recall` と信念を作る前の判定の trace に、
  選んだ手法 (`requested_narrower`)、実際に使った手法 (`narrower`)、縮退の理由 (`fallback_reason` / `narrower_fallback_reason`) が残る。
  実装の誤り (それ以外の例外) は縮退させずに上げる。信念を作る前の判定では、絞り込みの失敗を判断の失敗と分けて
  `unavailable_reason=NARROWER_FAILED` で残し、作るを通す
- **手元の Ruri v3 は縮退で包まない**。手元のモデルの失敗は、通信の揺れではなく設定か実装の誤りなので、2 字組の結果で隠さない。
  状況の想起は `failed` の trace (選んだ手法の名前つき) に残り、その回は何も載らない
- **組めない設定は最初の想起を待たずに止める**。キーが無い (空、または置き値の `EMPTY`)、sentence-transformers が入っていない、モデルを読めない、
  のどれも手法を組む時点で落とす。最初の想起まで遅らせると、毎ターン縮退か失敗をしたまま run が最後まで走る
- **検索される側のベクトルは、文をキーに索引へ持ち、想起のたびに作り直さない**。持てる数 (既定 4096) を超えたら、長く使っていない文から捨てる。
  捨てるのは比べたあとにする。比べる前に捨てると、その想起の候補が欠ける。1 回の候補が持てる数を超えたら警告を残す
- **並列の想起は索引の操作にだけ鍵をかける**。1 ターンの中で複数の人の想起が並列に走り、同じ索引を使う。API を呼ぶ間は鍵を持たず、
  その間に別の想起が候補のベクトルを捨てたら、捨てられた分だけ作り直す (3 回まで)。次元の合わないベクトルは索引に入れない
- **ベクトルは Being ごとに分けず、snapshot にも載せない**。値は文だけで決まり、Being ごとの状態ではないので、design_decisions 27 の
  Being ごとの store に当たらない。読み込み直後の最初の想起で作り直す費用は、信念が 1 人 30 件ほどなら API で数百〜千トークン
  ($0.00001 ほど)、手元の Ruri で 0.1 秒ほど。エピソードは run をまたいで溜まり続けるので、エピソードを埋め込みで引く PR で、
  保存して持ち越すかを件数と費用で決め直す
- **numpy の行列積の警告は止め、値が有限かを自分で確かめる**。macOS の Accelerate では、値は正しいまま行列積が divide by zero や overflow の
  警告を出す。run のログに誤った警告を残さない

**どうしないと壊れるか**:

- 縮退を trace に残さないと、API が落ちていた区間の想起が 2 字組の結果なのに、埋め込みの結果として読まれる
- 比べる前にベクトルを捨てると、候補が持てる数より多い想起で KeyError になる (テストで再現した)
- ベクトルを Being ごとの store にすると、design_decisions 27 の配線と snapshot の互換の扱いが要るのに、値は文から作り直せる。費用に見合わない

**限界**:

- Qwen3 の指示文は 1 通りしか試していない。Ruri v3 は Mac の手元で測った時間で、GPU の無い Linux では遅くなりうる
- 起動時に確かめるのはキーがあるかだけで、キーが無効 (401) や残高切れ (402) でも、run は毎回 2 字組へ縮退しながら最後まで走る。
  縮退の理由は毎回 trace に残るが、run が止まるわけではない。時間切れ (20 秒) も毎回待つ。既定を埋め込みに替えるときに、
  起動時に 1 回試すか、認証の失敗を縮退と分けて止めるかを決める

**関連**: design_decisions 27 / D1414-8 / D1498 / Issue #1454 / Issue #1436。

埋め込みの絞り込み (`embedding_narrowing.py`、OpenRouter と Ruri v3 の埋め込み) と任意の依存 `embedding-local` は、記憶の部品の撤去 (#1631) の #1787 で消した。比べた記録 (`scripts/situation_recall_review.py` の出力) は残る。

## D1461. SNSの対象には作成時の不変識別子を保存し、表示参照と分ける

**なぜ**: 一時的な画面番号や再利用可能な整数だけでは、履歴に残った指定が別の対象へ
結び直されうる。表示名は読みやすさに使い、投稿・返信・アカウントの同一性とは分ける。

**決まり**: 各対象に作成時の UUID4 を保存し、復元時には保存した値を検査してそのまま
使う。保存領域にも UUID4 を一つ保存する。SQLite の旧行への補完は移行時の一回だけで、
読取時に欠損を再発行しない。同じ保存領域を複製しても既存の対象は同一、分岐後に新しく
作った対象は整数採番が重なっても別の UUID になる。名前変更・削除・再描画は識別子を変えない。

**限界**: これは同一性の保存基盤で、IDを知ることは閲覧・操作の権限ではない。公開SNSの
入口では作者・親・通知の参照先も作成時の対象へ束縛し、現在の公開範囲とブロックを別に
検査する。旧画面の一時参照をこの変更だけで置き換えず、世界全体のJSON再開へのSNS接続も
別の変更で扱う。実モデルの使い分け・有効性は未検証。

**関連**: Issue #1455 / #1459 / #1460 / #1461。既存の衝突防止 Draft #1457 は旧経路の安全策として残す。

## D1460. SNSの作者・親・通知先を、整数だけでなく作成時の対象へ束縛する

**なぜ**: 投稿自身の不変IDだけでは、作者や親の整数が再利用されたときに、古い投稿が
別の人物・別のスレッドへ結び直される。通知の整数参照と保存済み本文にも同じ問題がある。

**決まり**: 投稿と返信は作者、返信は親、通知は発信者・受信者・対象の不変識別子を
保存する。現在の対象の識別子と一致しなければ公開SNSの新しい入口では表示しない。
SQLiteの旧作者・親は移行時に一度だけ束縛する。過去の通知は安全に宛先を確定し直せない
ため、未束縛のまま保存し、新入口では隠す。既存の通知や履歴は削除しない。

**配送の保存情報**: 通知には元イベントと配送済み状態を保持し、再配送の重複排除と
確定後の再試行に使う。実際の要求由来を保存できる欄を用意するが、実行していない
要求・データセット記録のIDは補わない。確定境界と実配送の実装は後続へ分ける。

**限界**: 保存だけでは権限を保証しない。現在の公開範囲・削除・全祖先・双方のブロックを
検査する読取入口が必要である。旧SNSの全操作経路を修正したものではない。

**関連**: Issue #1455 / #1459 / #1460 / #1461、design_decisions D1461。

## D1460-2. 初期のSNS読取は公開だけを、全祖先の権限を確かめて有限件ずつ返す

**決まり**: 投稿一覧・通知一覧・選択した投稿／返信を共通の公開読取から取得する。
作者本人にも非公開の投稿は返さない。作者・親の不変識別子、削除、全祖先の公開範囲、
双方のブロックを確認し、不在と不可視は同じ応答にする。IDを知るだけで権限を得られない。

**上限**: 1ページは最大20件、内部候補は一回101件まで取得し100件まで検査する。
見えない対象が先頭を埋めても、残候補があれば空ページと継続位置を返す。整数採番の
降順キーを使い、新規投稿は更新後の先頭から見る。継続位置は保存領域と閲覧者の
不変ID、画面種別と選択対象へ束縛する。全いいね・全関係・全返信を復元しない薄い
読取模型を用い、ブロックは対象の組だけを照会する。

**本文と通知**: 選択した本文は末尾まで返す。画面側は選択本文を優先して親・返信を
上限内へ投影する。通知の保存本文を信用せず、参照先の不変IDと現在の権限から本文を
引き直す。実行経路への接続やSNS専用の起動ループはこの変更に含めない。

**限界**: 最大64対象で根に到達しない返信の鎖は、循環と同様に表示しない。取得できる
ことと、実モデルがそれを適切に使うことは別の検証である。旧SNS画面の全機能を
この入口へ移したわけではなく、非公開機能とフォロー／いいね操作の露出は後の課題に残す。

**関連**: Issue #1455 / #1460 / #1461、design_decisions D1460 / D1461。

## D1459. 公開SNSの投稿・親更新・通知を一つのCommandScopeで確定する

**なぜ**: 隔離した旧SNSのUnitOfWorkをそのまま再接続すると、保存と通知の順序や
巻き戻しの契約が崩れる。公開SNSは既存の確定境界へ適合する小さい入口から接続する。

**決まり**: 新しい公開専用コマンドは、投稿／返信、直接の親の返信集合、永続通知を
同じCommandScopeで確定する。現在の公開条件と全祖先を操作前と通知保存前に検査する。
未確定の本文は配送しない。同期ハンドラは通知を保存するだけで、確定後に配送する。

**再送**: 通知は元イベント・受信者の不変ID・通知種別で重複排除する。配送失敗は
投稿の失敗と偽らず、確定済み結果を保つ専用例外にする。保存された未配送通知から
再試行し、受信側は通知の不変IDで冪等に扱う。配信済みと既読は別の状態である。
配送直前にも発信者・宛先・対象と現在の権限を確認する。

**宛先ごとの失敗分離**: 初回配送と再送は、一件の例外で後続を止めない。取得した通知を
それぞれ試し、失敗分と元の例外をまとめて報告する。初回配送では従来どおり
`CommandPostCommitException` へつなぎ、成功した宛先の配送済み記録と投稿確定を保つ。
再送は一回100件以下とし、最後に選んだ通知IDの次から取得する。失敗が100件以上続いても
後ろの正常な宛先へ到達でき、末尾へ達したら先頭の未配送通知へ循環する。
走査位置はサービスだけが一時保持し、サービス再作成では先頭へ戻る。通知と配送済み状態は
保存先に残るため、この位置が失われても通知の欠落にはならない。永続スキーマは増やさず、
受信側の不変IDによる冪等性も従来どおり必要とする。

**受信の範囲**: フォロー・いいねの道具は追加しない。既存ドメインが発生させる
フォロー・いいねイベントに発生時の不変識別子を添え、安全な受信変換から通知へ渡す。
識別子のない旧イベントを現在の整数から推測で再束縛しない。メンションは重複可能な
表示名ではなく、一意なアカウント名を使う。同じ相手への返信とメンションは一通知にまとめる。

**出典**: 実行境界にある要求ID・本人の手番・実際のツール呼出しIDを受け渡す欄を用意する。
データセット記録が無い呼出しには、その記録が存在するようなIDを補わない。通常の
行動・観測へ渡す表示や起動条件は次の接続変更で扱う。

**限界**: インメモリの書込みは既存の全状態を戻せる確定境界を使うため、読取ページの
候補上限と同じ計算量にはならない。確定後の外部受信側の冪等性は受信側にも必要である。
実モデル評価は未実施。関連: Issue #1459 / #1460 / #1461、design_decisions D1460 / D1461。

## D1459-2. 公開SNSは二つの道具と通常観測に接続し、専用の起動ループを作らない

**入口**: シナリオの `public_sns_enabled` を明示した世界だけに `sns_read` と
`sns_publish` を出す。既定は無効。読む操作は受信箱・公開投稿一覧・スレッド・閉じる、
発信は新規投稿・返信だけ。フォローといいねは受信通知のみで、操作を公開しない。
既存の一起動一行動を維持し、読取成功から専用の追加判断や再起動を作らない。
全SNS通知は `schedules_turn=False` とし、既存の通常起動判定を変更しない。

**通知**: 相手と操作対象の不変ID、できるだけ全文を自動提示し、先に読む操作を
要求しない。描画の合計は `public_sns_push_budget_chars`（既定6000 Unicode文字、
512〜24000）以内。返信・メンションを優先し、足りなければ本文だけを部分表示する。
省略した通知は保存済み受信箱に残り、本文が直近履歴から抜けても未表示件数を示す。
単なる描画やモデル呼出し失敗では表示済みにしない。サービス上の既読とも分ける。

**画面**: 一人に一つ、最大12000 Unicode文字の取得済み画面を保持する。共通見出しに
本人アカウント、表示条件、取得時点、範囲、続きの入口／終端を置く。新着通知では
切り替えない。選択本文は全文、親文脈は近い3件までを表示し、省略と親のIDを残す。
次の成功取得かcloseまで再取得せず、失敗要求の出典と以前の成功画面を区別する。

**実行由来**: 実際の行動を実行する境界で要求IDと本人の手番を一度確定し、実providerの
ツール呼出しIDがある場合だけ対応付ける。既存dataset用IDを偽造しない。短い結果記録と
現在画面へ出典を残し、更新・保持・失敗して旧画面保持を最終プロンプトで区別する。
本文は画面と通知履歴で重複させず、描画時だけ短い通知事実へ投影する。記憶は削除しない。

**保存**: SNS内容・関係・名前空間・通知・画面・最後の要求・表示状態・実行手番を世界の
JSONへまとめる。SNS有効の再開でこの状態やworld.jsonが無ければ停止し、古いIDを新しい
空の世界へ移さない。無効な旧世界の互換は保つ。配送未完了は再開後の最初の表示前にも
最大100件ずつ再送し、通知IDで二重観測を防ぐ。

**限界**: 配送重複の台帳と未表示IDは通知件数に比例して増える。保存期間短縮は別の設計。
成功した読取・発信は他の通常行動同様、移動中なら移動を中断する。決定的な実行経路と
保存の試験は行うが、実モデルの理解・自発的利用・協調の質はまだ証明しない。

**関連**: Issue #1455 / #1459 / #1460 / #1461、design_decisions D1459 / D1460 / D1461。

## D1509. 外れた予期の材料には、清算に見せた時系列のうち書いてから確定するまでを付け、関係の無い出来事の除き方は信念をまとめる LLM に任せる

**何を**: 清算の service が外れで確定した予期の出来事 (`ExpectationSettled.what_happened`) に、清算に見せた時系列のうち、予期を書いたターンから確定したターンまでの行動と発言の文を載せる。信念の材料を積む受け取る側は、外れのときだけそれを材料 (`BeliefEvidence.what_happened`) に付け、信念をまとめる LLM の入力に `what_happened` として渡す。予期の清算が有効な run では、システムプロンプトの【入力の意味】に説明を、末尾に【外れた予期から学ぶ】の指示を足す (Issue #1509)。

**なぜ**: 外れの材料が「ほぼ確実と思っていた予期『…』は外れた。」だけだと、信念は「〜とは限らない」ばかりになり、次の行動に使えない。実 run の外れ 30 件で、理由や次の行動が分かる信念は 0 件だった。清算のときに Jev は時系列を見て外れを判定しているので、その中身を渡せば 8〜9 件になる (`docs/experiments/issue_1509_miss_material_timeline/`、当否は Claude が付け、人は確かめていない)。

**決まり**:

- **新しく観測を集め直さない**: 付けるのは清算の service が持つ時系列の範囲だけ。時系列は直近 `timeline_turns` ターン分しか持たず snapshot にも載らない (design_decisions D1440) ので、長く清算待ちだった予期や、再開した直後に確定した予期は、残っている分だけになる。空の行は載せない
- **付けるのは外れだけ**: 当たりは根拠の信念があるときだけ材料になる (design_decisions D1484)。当たりに付けるかは、外れの結果を見てから決める。出来事にも当たりでは載せない
- **確定の出来事と一緒に保存する**: 時系列は出来事が運ぶので、未配信のまま snapshot に保存され、restore で戻る (design_decisions D1439、design_decisions 27)。材料にも載るので、証拠バッファの snapshot と SQLite にも保存する。#1509 より前の payload にはキーが無いので、拒まずに空として読む。時系列が無くても材料が理由を持たないだけで、状態は壊れない
- **上限は受け取る側で、先頭から**: 先頭から 1500 字に収まる行までを残す。予期を書いたターンの行動の結果が先頭に来るので、後ろを切る。外れを決めた出来事は確定に近い後ろの行にあることもあるが、30 件の最長は 1193 字で、いまは切る場面が無い。切る場面が run に出たら、どちらを残すかを決め直す。先頭の 1 行だけで超えるときは、その行を上限で切る (空白だけになれば残さない)。trace の `expectation_material` に、付けた行数 (`what_happened_lines`)、元の行数 (`what_happened_total_lines`)、切り詰めたか (`what_happened_truncated`) を残す
- **時系列が欠けた外れは、清算の trace で見分ける**: 清算の `transitions` の外れの確定に、付けた行数、予期を書いたターン、時系列の最初のターンを残す。書いたターンより時系列の最初のターンが新しければ欠けている。再開直後は時系列が空になる
- **空の行は出来事の時点で拒む**: 材料は空の行を受け付けない。出来事が通すと、壊れた snapshot から戻った出来事を受け取る側が配り直しのたびに失敗し、外れの材料が配信の上限で落ちる。SQLite の行も、キーが無ければ空として読み、list[str] でない値は拒む
- **tool の名前と ID は、ゲームから写すところで外す**: 清算の時系列を作る `turn_material` が、行動と観測の文の小文字で始まる語を「操作」に置き換え、数字と a〜f だけでできた 6 文字以上の語 (メモの ID) を消す。シナリオの操作名 (`gather`、`search_wreck_hold`) は tool の一覧に無く、シナリオごとに増えるので、語の形で拾う。小文字で始まらない語 (SOS、CLEAR) と、数と単位 (1.5kg) は残す。発言は本人たちの言葉なので触らない。行動と観測の文に小文字で始まる世界の言葉 (英語の地名など) があれば、それも「操作」になる。いまのシナリオには無い。Jev が見る清算の時系列からも外れる。清算の state に ID を入れない決まり (design_decisions D1440) に合わせる
- **節は、材料に時系列が付く run でだけ出す**: 予期の清算と信念の証拠 (`BELIEF_EVIDENCE_ENABLED`) の両方が有効なときだけ、システムプロンプトに節を足す。どちらかが無効なら時系列の付いた材料は作られない。時系列の付いた材料が残った snapshot を、清算を無効にして再開すると、入力には `what_happened` が載るが節は出ない
- **期限や件数の上限で確定した外れは、期限より後の出来事も含む**: 範囲は確定したターンまでで、予期の期限では切らない。関係の無い出来事は信念をまとめる LLM への指示で除く
- **関係の無い出来事を除くのは、信念をまとめる LLM への指示で扱う**: 時系列にはその期間の別の出来事も混ざる。規則では絞らない。Jev に行ごとに問う案は、30 件の時系列が 6〜22 行あり、清算の呼び出しが外れ 1 件あたり最大 22 問増える。指示の案で、関係の無い学びは 4 件から 1 件になり、呼び出しは増えなかった。Jev に問う案は試していない。run で関係の無い学びが目立ったら比べる
- **言い切りの抑えは、既存の確信度の指示だけでは効かなかった**: 支持の数に合わせる指示は、既存の信念を強めるときの指示で、外れから新しく作るときには効いていなかった (#1491 の比較で「大樫の樹には手がかりは無い」)。指示に、理由が書かれていないときは 1 回の観測で言い切らないことを足した。それでも言い切りは 4 件のまま減らなかった。他の人の「浜はもう打ち止めだ」を理由として読んだ言い切りが残る
- **操作の案内を世界の出来事として読ませない代わりに、案内に含まれる世界の事実も学べない**: 「大樫の樹は隣の場所。そこへ行くなら操作を使う」から「大樫の樹は移動先の場所である」を学べなくなった。tool の名前を信念に入れないことを優先した

**どうしないと壊れるか**: 外れの理由を渡さないと、外れから学ぶ信念は予期を打ち消すだけになり、仮説を確かめる流れ (#1491) で確かめたいことも立たない。時系列を出来事に載せずに清算の service の中だけで持つと、未配信のまま run を跨いだ外れの材料は理由を失う。tool の名前を残すと、信念にゲームの用語が入る。

**揺れについて**: 同じ時系列で問い直しても、temperature 0 で 22 件のうち 6 件で作るか捨てるかが変わった。上の件数の差は、この揺れと同じくらいの大きさにある。

**関連**: design_decisions D1439 / D1440 / D1443 / D1484 / design_decisions 27 / Issue #1436 / #1491。

**その後**: 外れた予期の時系列を信念の材料に付ける受け取る側と、信念をまとめる LLM に時系列の読み方を足す節 (`expectation_what_happened_enabled`) は Issue #1631 で消した。材料の `what_happened` の欄は信念の部品と一緒に消す。

---

## D1568. 予期の当否は、決め手が他の人の発言の中身しかないかも同じ呼び出しで問い、そうなら当たりを「まだ分からない」に下げる

**何を**: 予期の清算 (design_decisions D1440) で、清算待ちの予期ごとに当否の問い (`check_N`) と並べて Noul の問い (`hearsay_N`) を足す。「この予期が当たったと言える決め手は、誰かの発言の中身しかないか」。当否が当たりで、この確率が閾値 0.5 (`HEARSAY_ONLY_THRESHOLD`) を超えたら、集約には「まだ分からない」を渡す。当否の問いの説明にも、発言はその人がそう言ったという事実で、中身が起きたことの確かめにはならないと書く。時系列の欄の名前は `行動` から `出来事` に変える (Issue #1568)。

**なぜ**: `mine_v1_003` の T9 で、ハルの予期「水門が開き、下層の近道が水に浸かって通れなくなる」が hit 0.97 で確定した。時系列でこれを裏づけていたのは、ミオの「下層の近道は水浸しだ」という発言だけだった。反する物音「遠くで南の坑道と南の横坑の奥の道が動く音がした」も時系列に入っていた。発言の欄は分かれていたが、問いには発言の扱いが書かれていなかった。ゲン T22 も同じ形で、帳面をめくった結果に缶のありかしか無いのに、ミオの「帳面のとおり」で「帳面に弁の目盛りの意味が書いてある」が当たりになった。

**決まり**:

- **問いの文だけで済ませない**: 文で伝えるだけでは、Jev が従わなかったことを清算の結果からも trace からも見分けられない。問いを足せば、下げたことが trace に残り、件数を数えられる
- **下げるのは当たりだけ**: 外れとまだ分からないはそのまま渡す。外れは、反する出来事か、起きなかったことで決まる。発言に引きずられた外れは、この問いでは見ない
- **閾値ちょうどは採らない**: 根拠の閾値 (design_decisions D1484) と同じ。stub の迷った答えは 0.5 で、ちょうどを採ると smoke run のすべての当たりが下がる
- **人の言動そのものについての予期は下げない**: 「ミオが何か言う」のように言動が起きたこと自体が決め手になる予期は、問いの「偽」の側に入れて説明している。Jev がこれを取り違えると当たりを取りこぼす。取りこぼしても予期は清算待ちに残り、期限で閉じるだけで、材料は積まれない。誤った当たりは根拠の信念を強めてしまう (design_decisions D1484)。取りこぼしのほうが害が小さい
- **trace での数え方**: 下げた予期の移りに、Jev の判定 (`judged_verdict`) と発言だけの確率 (`hearsay_only`) を足す。`verdict` には集約に渡した判定 (`undetermined`) が入る。下げなかったときの確率は `answers` の `hearsay_N` にある
- **閾値は設定に出さない**: 根拠の閾値と違い、まだ実 Jev の答えを集めていない。次の run で、下げた件数と、そのうち人の言動の予期だった件数を数えてから決め直す

**採らなかった案**:

- 発言を時系列から外す: 人の言動についての予期が清算できなくなる
- 問いの文だけを直す: 上のとおり、効いたかを確かめられない

**限界**: 直るのは清算の当否だけ。T16 にハルが作った信念「北の坑道の水門は開けると下層の近道が水浸しになる」は、この清算からではなく、伝聞を信念の材料にする経路 (`source_kind: hearsay`) から作られていた。T9 の当たりは根拠の信念もエピソードも無く、どこにも返っていない。伝聞 1 件から信念が作られる経路は、この判断では直らない。

**どうしないと壊れるか**: 他の人の憶測が予期の当たりになり、根拠の信念があればその信念を強める。外れから世界の決まりを学ぶ仕組みの前提である、当否が世界で起きたことから決まるという性質が崩れる。

**関連**: design_decisions D1440 / D1484 / D1509 / Issue #1436 / #1568。

**その後**: この判定を含む予期の清算は Issue #1631 で消した。


---

## D1513. 出来事の条件・操作の前提条件・効果に、種類ごとの許可キーの表を置き、表に無いキーは読み込み時に止める

**何を**: 出来事の条件は `SCENARIO_EVENT_CONDITION_KEYS` (`parse_scenario_events.py`)、操作の前提条件は `INTERACTION_CONDITION_KEYS` (`parse_interaction_conditions.py`)、効果の `parameters` は `EFFECT_PARAMETER_KEYS` (`parse_interaction_effects.py`) に、種類ごとに書けるキーを列挙する。表に無いキーがあれば `ScenarioLoadError` で読み込みを止める。効果の直下も `effect_type` / `parameters` / `visibility` / `target` だけを許す。ファイルから読むときは、エラーの先頭にファイルのパスを付ける (Issue #1513)。

**なぜ**: ローダは知らないキーを読まずに捨てていた。島のシナリオの `PLAYER_AT_SPOT` は場所を `spot_id` に書いていて、ローダが読む `target_spot` が空のまま読み込まれ、`outpost_discovered` と `lone_hut_discovered` は一度も発火していなかった。同じ形で、`SET_FLAG` の `"value": false` はフラグを下ろさずに立てており、`APPLY_STATUS_EFFECT` の種類を `effect_type` に書いた出血は一度も付いていなかった。どれも例外も警告も出ない。記憶を測るシナリオ (#1508) で決まりを足すたびに、効かない決まりが紛れ込む。

**決まり**:

- **表に載せるのは、評価器や handler がその種類で実際に読むキーだけ**: 全種類で 1 つの集合にすると、他の種類のキー (`TICK_AT_LEAST` に `flag_name`) が通る。読み込みで名前を変えるキー (`target_object` → `object_id`) は、JSON に書く側の名前で載せる
- **種類を足したら表にも足す**: 表のキーの集合が `SUPPORTED_CONDITION_TYPES` / `InteractionConditionTypeEnum` / `InteractionEffectTypeEnum` と一致することを `test_unknown_scenario_keys_fail_fast.py` が見る。読まれるキーを handler に足したときに表へ足し忘れても、そのキーを書いたシナリオが読み込みで止まるので気づける
- **知らない effect_type も読み込みエラーにする**: 表を引く前に種類を確かめる。以前は生の `KeyError` が読み込みの入口を素通りしていた

**どうしないと壊れるか**: 書いた決まりが黙って効かなくなる。効いていない決まりの上で記憶を測ると、測っているものが変わる。

**関連**: design_decisions 3 / Issue #1508。

---

## D1514. 記憶だけを持ち越す回は、実験設定の `snapshot_load_mode: "replay"` で選び、前の回の世界の tick は記憶から外す

**何を**: 実験設定の最上位に `snapshot_load_mode` を置く。`"continue"` (既定) はいままでどおり Being と世界の両方を戻す。`"replay"` は Being の snapshot だけを読み、`world.json` があっても読まずに、世界を初期状態の tick 0 から始める。回の番号は、snapshot ディレクトリの親にある前の回の `experiment.config.resolved.json` の `replay.round` に 1 を足して決め、resolved と trace の `run_start` に `replay` として残す。読み込むときは、記憶に残る世界の tick の欄を 0 に置き換え、保留中の予測を捨てる (`world_clock_restart.py`、Issue #1514)。

**なぜ**: 同じシナリオを繰り返し遊び、前の回に学んだことが次の回に効くかで記憶を測る (#1508)。以前は `make experiment-resume` が `world.json` を見つけると世界も戻し、「続きから」になった。記憶だけを持ち越すには `being_*.json` を手で別の場所へ写すしかなく、写し忘れると黙って続きから始まった。

**決まり**:

- **違いは実験設定にだけ置く**: 1 つの profile で全部の回を回す。`SNAPSHOT_LOAD_DIR` の無い run が 1 回目になる。make の入口は増やさない。環境変数で切り替えない
- **回の番号が分からない run は始めない**: 前の回の run に resolved が無ければ起動前に止める。手で写した snapshot から 2 回目を始めると、番号を推測することになる
- **世界の tick の欄は 0 に置き換える**: Being のターン数 (`memory_turn`、予期、信念の観測ターン、知り合いの記録 (design_decisions D1520)) は回をまたいで続くので書き換えない。memo・目的・信念の材料・想起の枠・冷却期間・余韻・慣れはまだ世界の tick の絶対値を持つ。そのまま戻すと、前の回の tick 90 の記録が新しい回の tick 5 より新しく見え、想起の枠や余韻が tick 90 を過ぎるまで残る。0 にすると、前の回の記録はどれも新しい回の記録より前か同時になる。冷却期間の値は「この tick まで戻さない」という期限なので、0 にすると冷却は解ける。慣れは前の回に思い出したものすべてが「tick 0 に思い出した」ことになり、新しい回の序盤に最も強くかかる
- **保留中の予測は捨てる**: 窓が前の回の世界の時計を指していて、初期状態に戻った世界では判定できない。捨てた件数は `snapshot_load` の `world_clock_restarts` に残る
- **表の漏れは 2 か所で止める**: codec が書く欄のうち名前に tick を含むものが `WORLD_TICK_FIELDS_BY_CODEC` と一致することを `test_world_clock_restart.py` が見る。読み込みの時点でも、書き換えたあとに 0 でない tick の欄が残っていれば、store に書き戻す前に止める

**採らなかった案**:

- 前の回の最後の tick を引いて負にする: 前後関係は保てるが、`GoalEntry` と `PendingPrediction` が負の tick を拒む。不変条件をゆるめることになる
- 世界の tick を前の回の続きから始める: 時間帯と tick で決まる出来事がずれ、世界が初期状態にならない
- 記憶が世界の tick を持たなくなる #1464 を待つ: そのあいだ繰り返しが測れない

**失うもの**: 前の回の記録どうしの tick の前後が消える (どれも 0)。memo の「経過 M tick」は新しい回の始まりから数えるので、実際より短く出る。#1464 が入れば、この書き換えは要らなくなる。

**どうしないと壊れるか**: 世界を戻したまま「2 回目」と呼ぶと、学習ではなく続きを測ることになる。tick を書き換えずに戻すと、前の回の想起と余韻が新しい回の始まりに居座り、新しい回の記録より新しいものとして並ぶ。

**関連**: design_decisions 15〜18 (snapshot) / Issue #1508 / #1464 / #1520。

**その後**: 世界の tick を 0 に置き換える欄のうち、目的 (goal journal の `created_tick`) は、目的の保存先と一緒に記憶の部品の撤去 (#1631) の #1686 で消した。

保留中の予測 (約束、`PENDING_PREDICTION_ENABLED`) は Issue #1631 で消した。Being の snapshot も `pending_predictions` を書かなくなった。消す前に保存した snapshot に残る約束は前の回の tick を持つので、replay では読み込む前に捨てる処理を残した。捨てた件数はいまも `world_clock_restarts` に残る。

世界の tick を 0 に置き換える仕組み (`world_clock_restart.py`) は、記憶の部品の撤去 (#1631) の段 13 で消した (#1810)。
- 置き換える欄は、上の 2 つが消えた時点で無くなっていた。
- 残っていたのは、名前に tick を含む欄が 0 でなければ止める番人だけだった。今の codec は Being のターン数 (`*_turn`) しか書かないので、番人は発火しなかった。
- `snapshot_load` の `world_clock_restarts` 欄も無くなった。
- replay で世界を tick 0 から始め、記憶だけを持ち越す仕組みはそのまま残る。

記憶に世界の tick を書く欄を足すと、前の回の tick が新しい回の記録より新しく見える問題がまた起きる。記憶の欄は Being のターン数で持つ。

**その後**: replay (`snapshot_load_mode: "replay"`) は外した (#1832)。
- 使う profile も run も無かった。
- 同じ Being が新しい環境に入る形は、#1771 の環境への出入りで扱う。
- 短期記憶を Being の側へ移すと、replay では前の回の出来事が次の回の直近の出来事に残る。続きからの再開では、残るのが正しい。
- 外したのは、実験設定の `snapshot_load_mode`、回の番号を前の回の resolved から数える処理、resolved と `run_start` の `replay` 欄、`snapshot_load` の `load_mode` / `world_snapshot_ignored` 欄。実験設定に `snapshot_load_mode` が書かれていたら、黙って無視せず起動前に止める。
- #1508 で記憶の持ち越しの効果を測るときは、環境への出入りの形で作り直す。

---

## D1514-2. 回ごとの役と初期配置は、シナリオの `round_assignment` に枠として書き、シードと回の番号で並べ替える

**何を**: シナリオの最上位に `round_assignment.groups` を書く。group は `players` (player id の配列) と、同じ数の `slots` (`spawn_spot` と `initial_state` の枠) を持つ。読み込みの最初に、group ごとに枠を並べ替えて、player の `spawn_spot` を上書きし、`initial_state` に枠のキーを足す。並べ替えの乱数は `SCENARIO_RANDOM_SEED` と回の番号 (design_decisions D1514) から作る。割り当ての結果は trace の `round_assignment` に残す (`parse_round_assignment.py`、Issue #1514)。

**なぜ**: 繰り返し遊ぶシナリオ (#1508) では、回ごとにチームの組み分けと入口を入れ替え、前の回の相手が今回の味方になる形を測る。回ごとに別のシナリオファイルを用意すると、別のシナリオとして扱われ、回どうしを比べにくい。

**決まり**:

- **player の id と名前は動かさない**: Being は人物に結び付いたまま、枠だけが動く
- **割り当ては生の JSON に書き込む**: その後の読み込みと検証 (`mutually_known_roles`、`role_personas`、場所の id) は、割り当て後の player に対して今のまま走る。割り当て専用の検証を別に持たない
- **シードが無ければ止める**: 割り当てを再現できない run を作らない。`round_assignment` の無いシナリオはシードが無くても読める
- **同じシードと同じ回なら同じ割り当て**: 回の番号を変えれば割り当ても変わりうる。毎回必ず変わるとは限らない (並べ替えなので同じ並びも出る)
- **知らないキーは止める**: `round_assignment`、group、枠のどれも、書けるキー以外があれば読み込みで止める (design_decisions D1513 と同じ理由)
- **枠の値も枠の場所で確かめる**: 枠の `initial_state` の値の型は、割り当てる前に枠の場所を指して止める。player に書き込んでから確かめると、どの枠が当たったかで止まる回と止まらない回が分かれる
- **trace には割り当てたあとの値を残す**: 枠に `spawn_spot` が無ければ宣言どおりの場所、`initial_state` は player の宣言に枠のキーを足した値を残す
- **回の番号が分かるのは replay の run だけ**: 続きからの run と、API サーバのセッションは回 1 として割り当てる。API サーバはシードを持たないので、`round_assignment` のあるシナリオはセッションの作成で止まる

**どうしないと壊れるか**: 枠を player の外に書かずに回ごとのファイルで変えると、`scenario_sha256` が回ごとに変わり、同じ世界を遊んだのかを記録から確かめられない。シード無しで並べ替えると、どの回がどの割り当てだったかを再現できない。

**関連**: design_decisions D1514 / D1513 / Issue #1508。

**その後**: replay を外したので (#1832)、実験の入口は回の番号を数えず、いつも 1 回目として割り当てる。割り当てはシードだけで決まり、同じシードなら同じになる。`round_assignment` と、シナリオの読み込み (`ScenarioLoader`)・`create_world_runtime`・`world_random` の `round_number` の引数は残した。実験の入口 (`GameRuntimeManager`) は回の番号を持たず、渡さない。#1508 で回を重ねる形を作り直すとき、同じ世界から回ごとに違う割り当てを作る仕組みとして使える。`round_assignment` の trace の `round` は 1 になる。

---

## D1514-3. 世界の側の乱数は、用途ごとに、シードと回の番号から作る

**何を**: `world_random(seed, round_number, purpose)` (`application/world_runtime/world_random.py`) で、条件判定 (`scenario`)、天候 (`weather`)、抽選表の効果 (`loot`)、runtime が持つ攻撃の判定器 (`attack`)、モンスターの行動 (`monster_behavior`) の乱数を別々に作る。1 回目の `scenario` と `weather` は以前と同じ種 (`seed` と `weather:{seed}`) にする。2 回目以降は `{purpose}:{seed}:round{n}` にする。シードが無ければ非決定的な乱数を返す (Issue #1514)。

**なぜ**: `SCENARIO_RANDOM_SEED` が効くのは条件判定と天候だけで、抽選表 (`LootTableAggregate.roll`) はモジュール全体の乱数、攻撃とモンスターの行動はシードの無い乱数を使っていた。同じシードで回しても、世界の側の結果がそろわなかった。回を重ねる実験 (#1508) では、同じ profile で回しても確率の出来事が回ごとに変わる必要がある。

**決まり**:

- **用途ごとに分ける**: ある用途で引く回数が変わっても、ほかの用途の並びがずれない。天候を条件判定と分けた既存の判断と同じ
- **1 回目は以前と同じ種**: 回の番号を入れる前の run と、条件判定と天候の結果がそろう
- **モンスターの行動の中の攻撃は、行動の乱数で引く**: モンスターの行動は command ごとに乱数の状態を控え、失敗したら戻す。その巻き戻しに攻撃の判定も含めるため、`_for_command` が行動の乱数を攻撃の判定器に渡す (以前からの形)。`attack` の乱数を引くのは、プレイヤーの攻撃と、command を通らない経路
- **`combat_logic_service.py` は触らない**: タイル地図の世界の戦闘で、実験に使う spot graph の世界からは呼ばれない。タイル地図の世界の死亡報酬 (`monster_death_reward_handler.py`)、採集 (`harvest_command_service.py`)、移住 (`monster_lifecycle_survival_coordinator.py`) も同じ理由で触らない
- **続きからの再開では、新しい乱数は先頭から引き直す**: world snapshot が乱数の状態を持つのは条件判定と天候だけで、`loot`・`attack`・`monster_behavior` は持たない。続きから再開した run は、通しで回した run と、この 3 つの結果がずれる。以前はシードの無い乱数だったので、悪くはなっていない。続きからの再開をまたいでそろえる必要が出たら codec を足す

**どうしないと壊れるか**: 世界の側の乱数がそろわないと、同じシードの 2 本の run の差が、記憶の差か乱数の差かを分けられない。回の番号を混ぜないと、毎回同じ確率の出来事が起き、前兆から学んだのか並びを覚えたのかを分けられない。

**関連**: design_decisions D1514 / D1514-2 / Issue #1508。

**その後**: replay を外したので (#1832)、実験の入口からは 1 回目の種だけを使う。1 回目は回の番号を入れる前と同じ種なので、続きからの再開を含めて結果は変わらない。`world_random` の `round_number` の引数は、D1514-2 の「その後」と同じ理由で残した。

---

## D1520. 会った相手の記録は Being が持ち、環境の encounter には「この観測はもう出した」の判定だけを残す

**何を**: 会った相手の記録を、環境の encounter (`InMemoryEncounterMemory`、世界の snapshot に入る) から、Being の知り合いの記録 (`AcquaintanceRepository`、`being/domain/acquaintance.py`) に移した。鍵は BeingId と、環境の名前と相手の名前の文の組。初めて会ったターン、最後に会ったターン、会った回数を持つ。時計は Being の記憶のターン数。Being の snapshot に入る。環境の encounter には、場所・出来事・初めて見たモンスター・倒れている人を残し、人は書かない (Issue #1520 段 1)。

**なぜ**: encounter は、環境の「この観測はもう出した」の判定と、Being の「会った人」の両方を持っていた。環境が Being の記憶を兼ねていると、Being を別の環境へ持ち出したとき会った人が付いてこない。誰を知っているかでプロンプトを変える段 (#1508 の、互いを知らずに始まる 2 チーム) の前提になる。

**決まり**:

- **会うのは、人が入ってきたときと、初期配置で同じ場所にいたとき**: 人が入ってきた観測から、受け手と入ってきた人の双方に記録する。入ってきた本人には自分の到着の観測が届かないので、受け手への観測から両方を残す。名前の伏せられた観測 (暗がりなど) では、どちらも記録しない。人が入ってきた観測は配置のあとにしか出ないので、初期配置の同席は `create_world_runtime` の最後にターン 0 で記録する
- **起動時に全員の Being を用意する**: 初期配置の同席を最初の手番より前に Being へ記録するため、capture も episodic 記憶も無効な構成でも、補助 Being を起動時に配線する (design_decisions 52 を改めた)
- **プレイヤー番号と Being、名前とプレイヤー番号の対応は `PlayerAcquaintances` だけが持つ**: 記録そのものにはゲームの ID を入れない
- **知り合いにするのはシナリオの参加者だけ**: 入ってきた者の名前が参加者に無ければ (モンスター、名前を引けなかったときの代わりの名前「不明なプレイヤー」) 記録しない。代わりの名前を記録すると、別々の相手が 1 人の知り合いにまとまる。同じ名前の参加者が 2 人いるシナリオは、名前から相手を決められないので起動時に止める
- **環境の名前はシナリオの title**: 入るときの取り決め (`EnvironmentEntry.environment_name`) と同じ文を使う。title を書き換えると、保存した知り合いは別の環境の相手として扱われる
- **知り合いの無い古い snapshot は読めない**: Being の snapshot の互換は保たない (#1436)。保存済みの snapshot を読むには、その run の `experiment.config.resolved.json` の `git.commit` にチェックアウトする。知り合いの欄が無い snapshot は #1525 のマージ (001ced21) より前のコミットで、知り方の欄が無い #1525 の形式の snapshot は #1525 のマージから段 1 の PR 2 のマージより前のコミットで読める
- **「(初めて会った)」は会った回数が 1 の間だけ付く**: 以前の encounter と同じ意味。初期配置で同席した相手には、1 ターン目から付く
- **想起の手がかりの「直近に会った相手」は Being のターン数で数える**: 窓の幅は 5 ターン。以前は世界の tick で 5 tick だった
- **snapshot では空で代用しない**: `ExperimentSnapshotSession` は知り合いの store を必須にする。空の代用品で再開すると、会った相手を全員忘れたまま、配線漏れと見分けられない

**入るときの紹介と【知っている人】 (段 1 の PR 2)**:

- **紹介は入るときの取り決めで渡す**: `EnvironmentEntry.introductions` に、名前と関係の注記 (`Introduction`) を並べる。紹介は Being の知り合いの記録に「紹介された」として入り、会った回数は 0 のまま。紹介された相手に会うと、知り方は「紹介された」のまま会った回数が増える
- **シナリオは `players[].knows_at_start` で紹介する相手を宣言する**: 書かなければ自分以外の全員を紹介する。既存のシナリオは、いままで system prompt に全員を並べていたので、これで変わらない。空の配列なら誰も紹介しない。互いを知る役 (`mutually_known_roles`) が同じ相手には「あなたと同じ側」の注記を付ける
- **【知っている人】は毎ターンのメッセージの【現在の目的】の直後に置き、system prompt に置かない**: system prompt に置くと知り合いが増えるたびに書き換わり、キャッシュがそこから全部切れる。目的の直後は、いちばん変わりにくい側。新しい人を知ったときだけ、この節から後ろが変わる
- **【知っている人】に描くのは名前と関係の注記だけ**: 会った回数のように会うたびに変わるものを描くと、会うたびに節が書き換わる。描くのは Being の側の `render_known_people` で、いまの環境で知った相手だけを並べる。別の環境で知った相手は並べない
- **起動時の検査より前に Being を用意する**: 起動時の検査は画面を組み、知り合いの記録を読む。Being を用意する前に読むと「Being が無い」の警告を誤報で出し、player ごとに 1 回だけの警告の枠を使い切る。あとで本当に Being が引けなくなっても警告が出なくなる
- **Being を用意できなければ起動を止める**: 用意できない player は紹介を受け取れず、【知っている人】が消える。「誰も知らない」と見分けがつかないまま実験の条件が変わるので、player を示して止める。PR 1 では止めずに続けていた
- **再開した Being には、シナリオの紹介を足し直さない**: snapshot を読み込むと知り合いの記録は全部置き換わり、起動時に受け取った紹介は残らない。誰を知っているかは Being の記憶で、あとからシナリオの `knows_at_start` を書き換えても、再開した Being の記憶は変えない
- **関係の注記は紹介でだけ付く**: `knows_at_start` で紹介しなかった相手とは、互いを知る役が同じでも、会ったあとの記録に「あなたと同じ側」は付かない。同じ側だと最初から知っているなら、紹介する相手に入れる

**話し手を知らない受け手の話し声 (段 1 の PR 3)**:

- **観測は両方の版を持ち、受け手の Being が選ぶ**: 話し声の観測 (`ObservationOutput`) は、話し手の名前と組で、名前を「誰か」に伏せた本文と structured (`SubjectUnknownView`) を持つ。受け手の記録に入れる入口 (`ObservationAppender` の `recipient_view`) で、受け手の Being が知り合いの記録を引き、知らなければ伏せた版を記録する。環境は Being の記憶を読まない。契約の `Observation` では `body_if_subject_unknown` に当たる
- **伏せた版では structured からも話し手を外す**: structured の `speaker` は episode の `who` と想起の手がかりに入り、記憶を通してプロンプトに出るため
- **同じ場所の声も同じ扱いにする**: 暗がりで入ってきた人のように、同じ場所にいても会っていない相手がいる
- **記録したあとで相手を知っても、記録した行は書き換えない**: 聞いたときには誰か分からなかった、という経験のまま残す
- **引けないとき、選ぶ口が無い入口、選ぶ口が例外を出したときは、伏せる側へ倒す**: 名前は、記録に入ったあとでは消せない。入口の配線を 1 つ忘れただけで、名前が全員に静かに届かないようにする
- **trace には伏せた話し手の名前を残す**: OBSERVATION の `subject_hidden` と `hidden_subject_name`。trace は人が読む記録で、エージェントには届かない
- **話し手が自分の名前を口にした言葉は、伏せた版でもそのまま残す**: 声がそう言ったのは聞こえている
- **話し声以外の漏れ方は #1531 で扱う**: 話した本人に返る人数、救助・取り残しの告知、遠くの復帰の気配、会っていない相手が倒れているのを見つけた観測

**どうしないと壊れるか**: 環境の encounter に人を残すと、知っている人を Being の記憶で決める段で、環境と Being の 2 か所に会った記録ができてずれる。歩いて入った側に記録しないと、相手のところへ行った側だけが相手を知らないままになる。紹介をシナリオで止められないと、互いを知らずに始まる班 (#1508) が作れない。

**関連**: design_decisions 27 / 52 / Issue #1436 / #1465 / #1508。

**その後**: 想起の手がかりの「直近に会った相手」(`PlayerAcquaintances.recently_met_names`) を読んでいた受動想起は、記憶の部品の撤去 (#1631) の #1796 で消した。手がかりを作る側の引数 (`recently_met_names` と encounter の 5 つ) と、読み手のいなくなった `recently_met_names` も一緒に消した。

---

## D1516. チームの勝敗は `teams[].win` で決め、個人の勝敗は所属チームの勝敗にそろえる。個人結果 (RESCUED など) とは別の軸で残す

**何を**: シナリオの最上位に `teams` を書けるようにした。チームは `id`、`name`、`member_state`、`win` を持つ。`initial_state` が `member_state` に一致する player がそのチームに入る。`win` には終了条件を書き、新しい型 `ALL_MEMBERS_HAVE_OUTCOME` (そのチームの全員が `outcome` の個人結果になった) を `teams[].win` の中でだけ使える。ゲームが終わると、チームごとの勝敗 (`GameEndResult.team_results`) が決まり、trace の `team_result` に、チームごとの勝敗と、人ごとの所属・個人結果・勝敗を 1 件残す (`parse_teams.py`、`scenario_team.py`、Issue #1516)。

**なぜ**: 廃坑の山村 (#1508、`docs/mine_village_scenario_design.md`) は 2 チームが敵対し、「チームの 2 人とも脱出したチームの勝ち。寝返って 1 人だけ脱出しても、その人のチームは負け」。いままでの勝敗は全体で 1 つの WIN / LOSE で、どちらのチームの勝ちかは書いた人の視点で読み替えるしかなかった。回を重ねる実験では、回ごとに誰がどちらのチームで、どのチームが勝ったかを記録できないと、「前の回は負けた」を次の回へ持ち越す場面が作れない。

**決まり**:

- **所属は名簿でなく `member_state` で書く**: `round_assignment` (design_decisions D1514-2) の枠が書き換えるのは `initial_state` なので、枠に `"team": "north"` を書けば回ごとの組み分けがそのまま効く。所属は回の開始時の `initial_state` で決め、回の途中で state が変わっても動かない
- **全員がちょうど 1 チームに入る**: どのチームにも入らない人、2 チームに入る人がいれば読み込みで止める。勝敗の決まらない人を作らない。真偽値の `true` と数の `1` は別の値として比べる
- **チームは 2 つ以上**: 1 つだけなら全体の `win` と変わらない
- **`teams` を書いたら `game_end_conditions.win` / `lose` を置けない**: 誰から見た勝ちかが二重になる。どのチームも勝たずに終わる条件は `game_end_conditions.end` に書き、1 つ以上を必須にする。無いと、どのチームも勝たないまま run が打ち切られ、勝敗が決まらない。`teams` のあるシナリオの `end` には、`FLAG_SET` や `TICK_LIMIT` など世界を見る条件を置ける (`teams` の無いシナリオの `end` は、これまでどおり `ALL_PLAYER_OUTCOMES_RESOLVED` だけ)
- **既存の条件型は、チームの中でも世界全体を見る**: `teams[].win` に `SURVIVING_PLAYERS_WITH_STATE_AT_MOST` を書いても、数えるのは全員のうち `required_state` を満たす人。チームの人だけを見るのは `ALL_MEMBERS_HAVE_OUTCOME` だけ。既存の型の意味を、置き場所で変えない
- **`ALL_AT_SPOT` / `ANY_AT_SPOT` は `teams[].win` に置けない**: 「全員が」「誰かが」を「チームの全員が」と読み違える。実際は相手チームの人まで数えるので、`ANY_AT_SPOT` なら相手が着いただけで勝つ。チームの人が場所にいることを勝ちにしたいなら、`player_outcome_rules` で場所にいる人に個人結果を付け、`ALL_MEMBERS_HAVE_OUTCOME` で待つ
- **待つ個人結果を付ける規則が無ければ止める**: `ALL_MEMBERS_HAVE_OUTCOME` が RESCUED か STRANDED を待つのに、それを付ける `player_outcome_rules` が無ければ読み込みで止める。DEAD と EJECTED は死と会議の投票が付けるので、規則が無くてよい
- **チームの `win` を `end` より先に見る**: 昇降機が出た tick に「北の 2 人が RESCUED」と「`lift_departed` が立った」が同時に起きても北の勝ちにする
- **勝つのは高々 1 チーム**: 成立したのが 1 チームならそのチームが WIN、他は LOSE。2 チーム以上が同時に成立したら、成立したチームは DRAW、他は LOSE。どれも成立せず `end` で終わったら全チーム LOSE。`END_ON_ALL_DOWN` の外的停止でも同じ表を作る
- **個人の勝敗は所属チームの勝敗と同じ**: 個人だけが勝つ・負けることは無い。`PlayerOutcomeEnum` に WON / LOST を足さない。身に何が起きたか (RESCUED / DEAD / STRANDED) と、チームが勝ったかは別の軸で、1 つの値に混ぜると「寝返って脱出したが負け」の片方しか残らない。trace の `team_result` では `outcome` と `result` を並べて残す
- **全体の勝敗は無い**: `teams` のシナリオでは `GameEndResult.result` は None で、`run_end` の outcome は ENDED になる
- **チームの名前と、相手チームの所属はプロンプトに出さない**: チームの名前 (`teams[].name`) は trace にだけ出す。所属を書いた `initial_state` のキーは、他の state と同じく本人の「自分の状態」にだけ出て、相手には出ない。本人にも見せたくないときは `player_attributes` でそのキーを `"visibility": "hidden"` と宣言する (D1546)。相手の存在を伏せる設定 (`knows_at_start`、design_decisions D1520) と矛盾させない。全体告知にもチームを差し込まない
- **`team_result` は check_game_end で終わったときだけ出す**: `max_world_ticks` に達した、LLM の障害で打ち切った、中断した run では出ない。勝敗は決まっておらず、`run_end` の outcome (TIMEOUT / LLM_ABORTED / INTERRUPTED) で分かる。決まっていない勝敗を LOSE として残さない
- **チームごとの理由を残す**: `team_result` の `teams[].reason` に、成立した条件の理由か、成立しなかったチームの最後の条件の理由 (「チームの RESCUED は 1/2人」) を入れる。全体の `reason` は終わらせた判定の理由で、同時に成立したら成立したチームの理由を並べる
- **結果を本人に届けて記憶へ持ち越す経路は、まだ無い**: ゲームが終わると手番の無いまま snapshot を取るので、終了時の観測が記憶に入る経路が無い。別の Issue で扱う

**どうしないと壊れるか**: 個人結果に WON / LOST を混ぜると、寝返った人が脱出したことと、その人のチームが負けたことの片方が消える。所属を名簿で書くと、回ごとの組み分けにシナリオファイルの書き換えが要り、回どうしを同じ世界として比べられない。同時に成立したチームを両方 WIN にすると、「両方のチームが勝つ結果は無い」シナリオで、両方が勝った記録が次の回へ持ち越される。

**関連**: design_decisions D1514-2 / D1520 / Issue #1508 / #1516。

---

## D1546. 本人にも見せない属性は `player_attributes` で `hidden` と宣言する。`teams[].member_state` のキーを自動では伏せない

**何を**: `player_attributes[].visibility` に `hidden` (本人も他人も知らない) を足した。`hidden` と宣言した属性のキーは、本人の「自分の状態」に出ない。手番を記録する効果が書くキー (#892) と合わせて `hidden_player_state_keys` に渡す。物体の注記では `secret` と同じく呼び名を出さない。廃坑の山村は `player_attributes.team` を `hidden` と宣言した (Issue #1546)。

**なぜ**: 互いを知らずに始まる 2 チーム (#1508) で、本人の「自分の状態」に `team=north` が出ていた。チームという区切りがあり、north の対になる側がいそうだと本人に分かる。

**決まり**:

- **伏せるかどうかは作者が宣言する**: `teams[].member_state` のキーを自動で伏せる案は採らない。所属のキーが勝敗を集計するための記録か、本人が知るべき立場かは作者にしか分からない。人狼型のシナリオに `teams` を書けば `member_state` は `{"role": "impostor"}` が自然で、自動で伏せると人狼が自分の役を知らないまま動く。どこも失敗しないので気づけない
- **呼び名に置き換えない**: `所属: 北の組` と出しても、「所属」という区切りがあることが伝わる
- **宣言しなければ、これまでどおり本人にだけ出る**: 既存シナリオのプロンプトは変わらない。`player_attributes` の呼び名を「自分の状態」全般に効かせる変更は、市場町などのプロンプトを変えるので別に扱う

**関連**: design_decisions D1516 / D1520 / #892 / Issue #1508 / #1546。

---

## D1531. 名前を伏せても誰かがいると分かる観測は、主体を知らない受け手には届けない

**何を**: 観測が主体を知らない受け手向けに持つ版に、名前を伏せた版 (`SubjectUnknownView`) のほかに、届けない印 (`WithheldFromStrangers`) を足した。受け手の記録に入れる入口 (`ObservationAppender`) で、受け手の Being が主体を知らなければ、バッファに入れず、ターンも積まず、移動も止めない。契約の `Observation` では `withheld_if_subject_unknown` に当たる。倒れた・復帰した観測と、倒れている人を見つけた観測をこの形にした (Issue #1531)。

**なぜ**: 遠くの倒れた気配・動けるようになった気配は、本文で名前を伏せても、知らない誰かがどこかにいることを知らせる。互いの存在を知らずに始まる 2 チーム (#1508) では、存在を知らせること自体が漏れになる。structured の `actor` に名前も入っていて、episode の `who` と想起の手がかりを通してプロンプトに出ていた。

**決まり**:

| 観測 | 主体を知らない受け手 |
|---|---|
| 遠くで倒れた気配、遠くで動けるようになった気配 | 届けない |
| 同じ場所で倒れた・復帰した観測 | 「誰か」に伏せ、structured の `actor` を外す |
| 倒れている人を見つけた観測 | 「誰か」に伏せ、structured の `actor` を外す |

- **同じ場所の観測は届ける**: 姿は見えているので、存在は知ってよい。名前は分からない。加害者が見えているときは、加害者の名前はそのまま残す。加害者が見えるのは同じ場所が明るいときだけで、明るい場所に居合わせた相手とは、入ってきたときか初期配置で会った記録が残っている
- **選ぶ口を渡していない入口で伏せたら、1 回だけ警告する**: runtime の入口のほかに、心拍・行動の失敗・チャットの観測を運ぶ入口があり、選ぶ口を渡していない。いまは主体の名前を持つ観測が通らないが、通ると紹介済みの相手の観測まで黙って伏せる・落とすことになる
- **自分が主体の観測は、知っている側として扱う**: 自分を知り合いとして記録していなくても届く
- **届けないときは trace にだけ残す**: OBSERVATION に `subject_withheld: true` と `hidden_subject_name` が付き、本文は名前付きの版を残す。エージェントには届かない
- **選ぶ口が無い入口、選ぶ口が例外を出したときは届けない**: D1520 の「伏せる側へ倒す」と同じ理由
- **契約では、本文が名前を伏せて主体が不明でも印を持てる**: 契約の観測は本文に現れる名前しか写さないので、遠くの気配の主体は不明になる。受け手は主体を知っているか決められないので、届けない側へ倒す。段 3 で Being が契約の観測を選ぶとき、知っている相手の遠くの気配まで落ちるので、そのときに主体の渡し方を決め直す
- **その場にいる人の行は、まだ倒れている相手の名前を出す**: 会っていない相手が倒れている場所に入ると、行には名前が出る。行の描き方を Being に移す段 3 で扱う

**結果の告知と、声が届いた人数 (PR 2)**:

- **救助・取り残し・死亡の全体告知は、主体を知らない受け手には届けない**: 遠くの気配と同じで、名前を伏せても誰かがいることが分かる。シナリオの文型 (`player_outcome_messages`) で名前を消しても、告知そのものが届いていた。死を全体に知らせない世界 (`announce_globally: false`) では、これまでどおり誰にも届かない
- **追放の告知は伏せず、全員へ届ける**: 追放は会議の場で全員が見て決めたことで、隠す理由が無い。会議で呼び集められた参加者どうしには、会った記録が残っていないことがある
- **話した本人に返る人数は、本人の知っている聞き手だけを数える**: 1 人で叫んで「2 名に届いた」と返れば、知らない誰かが近くにいると分かる。数えるのは Being の知り合いの記録で、聞き手を決めるのは環境 (`SpeechAudienceResolver`) のまま
- **知らない聞き手だけに届いたときは、誰にも届かなかったときと同じ文を返す**: 文が違えば存在が分かる。「聞こえる範囲には他のプレイヤーがいませんでした」は事実と食い違うが、話した本人から見れば、知っている人には届いていない。文を変えると、全員を紹介する島の golden が変わる
- **知り合いの記録を持たない runtime では、全員を数える**: 誰を知っているかの概念が無いので、これまでどおりにする
- **`SpeechToolExecutor` の人数は直さない**: 聞き手の解決 (`audience_resolver`) を渡して作る箇所が src に無く、いまは人数を返さない

**どうしないと壊れるか**: 伏せた版だけで済ませると、遠くの気配のたびに、会っていない相手の存在がエージェントに届く。届けない観測でもターンを積むと、何も新しくない手番が回り、気配があったことが手番の数から分かる。

**関連**: D1520 / Issue #1508 / #1520。

## D1557. でたらめに行動するスタブは、エージェントに見えている候補だけから選び、実シナリオの総当たりは CI に入れない

**何を**: `RandomLlmClient` は、毎ターン、渡された tool 定義と、ユーザープロンプトの
【現在選べる対象引数】の表だけから行動を作る。表は `parse_dynamic_argument_candidate_table`
で読み戻す。名前を指す引数 (`*_label` / `action_name` / `*_id(s)`) に候補が無いツールは選ばない。
回す入口は `scripts/fuzz_scenario_with_random_agents.py` (`make fuzz-scenario`) で、例外・
握られた例外・ERROR ログ・内部番号やシナリオ ID の漏れを、シード・tick・行動の並びと一緒に出す。
漏れは、メッセージの本文とツール定義の説明文の両方で探す。シナリオの操作名 (`action_name`) は
候補の行と `呼び出し:` の続き行に渡すための値として出るので、【直近の出来事】の `[行動]` 行の要約
(`→` より前) に出たときだけ漏れにする (#1564)。Issue にしてまだ直っていない穴は
`KNOWN_HOLES` に Issue 番号と形を書き、見つけても run を失敗にしない。書かないと、すべての
シナリオで毎回同じ既知の漏れが出て、新しい穴が埋もれ、終了コードも使えなくなる。
CI では、わざと穴を入れた小さなシナリオで検出器そのものを試し、廃坑の山村は 2 シード 10 tick
だけ回して「回せる」ことを見る。多数のシードでの総当たりは手で回す。

**なぜ**: 候補をエンジンの内部 (`ToolRuntimeContextDto`) から直接もらうと、プロンプトに出して
いない値を選べてしまい、「エージェントが実際にできる行動」の組み合わせからずれる。表を読み戻す
形なら、エージェントに見えているものと選べるものが一致する。ただし表示が壊れると、名前を指す
ツールが黙って選ばれなくなる。そこで、表にあるのに読み戻せなかった行を `unreadable_candidates`
として出す。

総当たりを CI に入れないのは、行動の並びがプロンプトの中身で決まるからである。関係のない PR が
候補の並びや文面を変えるだけで、どのシードがどの穴を踏むかが入れ替わる。その PR が作っていない
穴で CI が落ちると、原因の持ち主を取り違える。

**どうしないと壊れるか**: 検出器は空振りしやすい。ERROR ログの検出は、入口で root の level を
CRITICAL に絞っていたため一度も拾えていなかった (正の対照の試験で分かった)。検出器を足すときは、
わざと穴を入れた試験を先に書き、検出の部分を外すとその試験が落ちることを確かめる。

#1558 のあとは、世界の tick で 1 体ぶんの例外が既定で取りやめになり、run が止まらない。止まる
ことだけを見ていると見逃すので、trace の `world_tick_unit_failed` も例外として数える。

**関連**: #1557 / #1508 / #1558 / design_decisions 66 / design_decisions 109。

---

## D1559. 移動の途中で区間が閉じたら、例外にせず、その手前で移動を取りやめる

**何を**: 予約した経路の区間を渡る直前に、通れるかを確かめ直す。通れなければ、その区間の出発側で移動を取りやめる (`PlayerSpotNavigationState.at_rest`)。移動サービスは止まった区間を `SpotTravelTickAdvanceDto.blocked` で返し、travel stage は到着の観察者ではなく止まった観察者 (`add_blocked_observer`) へ知らせる。runtime は次の 3 つを残す。

- trace の `travel_blocked`: エージェント、通路の id・名前・種類・状態、理由 (`passage_closed` / `passage_condition`)、区間の両端と最終の行き先
- 本人への観測: 閉じた通路の手がかりと「その先へは行けない。」。手番を積む (`schedules_turn=True`)
- 行動履歴: 移動を取りやめた失敗の行 (`error_code="TRAVEL_BLOCKED"`)

**なぜ**:

- 区間が閉じるのは世界の正常な出来事で、エンジンの異常ではない。扉の施錠、浸水、隔壁の閉鎖、通行条件のフラグを消すこと、どれも予約の後に起こりうる。例外のままだと、廃坑の山村 (`var/runs/mine_v1_002`) のように run 全体が止まる
- 予約は横断が成功したあとにしか保存されない。上で例外を握るだけでは、次の tick に同じ区間を踏んで同じ例外が出続ける。止まったことを結果として扱い、予約を消す必要がある
- 本人は区間を渡り切る tick までグラフ上は出発側にいる。手前で止めれば、出発した場所に戻したのと同じになる。通路の途中を表す状態を新しく作らずに済む
- 1 tick に複数の区間を渡る経路では、通れた区間までは渡る。渡ったことは世界で確定した出来事なので、巻き戻さない
- 到着の観察者を呼ぶと「◯◯に着いた」と履歴に残り、事実と食い違う。呼ばずにおくと、出発の行だけが残って本人が移動中だと思い込み、手番も来ない。だから止まった観察者を別に持つ

**手がかりの文**: 通路の種類と状態だけから作る (`travel_blocked_cue`)。扉は「〈名前〉は閉ざされていて、開かない。」、障壁は「〈名前〉は塞がっていて、通れない。」、壁は「〈名前〉は壁に阻まれている。」。通行条件で落ちたときは、シナリオの `failure_message` を使う。誰が閉じたかは出さない。現地でその人を見ていない本人には分からないことで、出すと会っていない相手の存在が漏れる (design_decisions D1520、D1531)。内部の番号も出さない (#1553)。

**通知の失敗**: 本人への観測を最初に出し、trace の記録の失敗は個別に握る。trace が落ちたせいで観測と手番まで失うと、本人は止まったことを知らず、手番も来ない。確定の後処理が失敗して結果が返らない経路 (`CommandPostCommitException`) では、移動中でなくなったことだけでなく、予約の行き先にいるかを見て到着を決める。そうしないと、取りやめた本人に「着いた」が残る。

**どうしないと壊れるか**: 渡る直前の確かめ直しを外すと、閉じた区間で `move_entity` が例外を投げて run が止まる。止まった結果で予約を消さないと、同じ区間を毎 tick 踏み続ける。止まったときに到着の観察者を呼ぶと、着いていない場所に着いたと履歴に残る。

**今は直さないもの**: `DESTROY_CONNECTION` で区間の接続そのものが消える場合 (`UnknownConnectionException`) と、消した接続の id が作り直しで再利用される場合。どちらも今のシナリオでは使っておらず、#1559 に記録した。通路ごとの手がかりの文 (水没なら水の音など) をシナリオに書けるようにするかは、共通の文で足りるかを次の run で見て決める。

**関連**: Issue #1559 / #1508 / #1558。

---

## D1558. 世界の tick の 1 体ぶんの例外は、CommandScope の単位で取りやめ、必ず trace と報告に出す

**何を**: 世界の tick の各段で、1 体 (プレイヤー、モンスター、出来事、取引など) の処理が例外を出したら、その 1 体の処理だけを取りやめて tick を続ける。取りやめるたびに trace に `world_tick_unit_failed` を 1 件残し (段・対象・例外の型と文・発生箇所・commit 済みか)、run_end の `world_tick_failure_counts` と report.md の冒頭に段ごとの件数を出す。実験設定の `WORLD_TICK_FAILURE_POLICY` で `isolate` (取りやめて続ける) と `fail_fast` (trace に残してから止める) を選ぶ。判断は `WorldTickFailureIsolator` の 1 か所に置く (Issue #1558)。

**なぜ**: 廃坑の 2 本目の実 run (`mine_v1_002`) は、1 人の移動の続きで出た `ConnectionNotPassableException` が `_execute_with_error_handling` で包み直されて run ごと止まった。費用のかかる run を 1 体の失敗で捨てたくない。一方で、例外を捕まえてログに出すだけで続ける箇所もあり、BeingId の NameError で状態崩壊の証拠が 1 件も作られていなかった不具合 (#1507) はこの形だった。止めすぎる箇所と黙りすぎる箇所の両方を、止めないが隠さない形にそろえる。

**決まり**:

| 段 | 取りやめる単位 |
|---|---|
| travel / death_grace / llm_turn | プレイヤー 1 人 |
| monster_behavior | モンスター 1 体 |
| monster_spawn | 出現の枠 1 つ |
| scenario_event | 出来事 1 件 (条件の評価を含む) |
| reactive_object_state | 物の状態の結び付け 1 件 |
| sync_action_resolver | 同期操作の組 1 つ |
| trade_offer_expiry / market_order_expiry | 提案 1 件 / 注文 1 件 |
| player_outcome_rule | 規則 1 件 |
| 上以外の段 (needs_decay / status_effects / food_spoilage / environment / day_night / reactive_binding) | 段そのもの |
| 確定後フック | フック 1 つ (`post_tick.<名前>`) |

- **取りやめる単位は CommandScope 1 回にそろえる**: scope の中で出た例外は rollback されるので、取りやめても状態が中途半端に残らない。全員を 1 つの scope で処理している段は、段そのものが単位になる。1 体ずつにするには scope を分ける必要があり、それは段ごとの変更として別に扱う
- **段の単位は受け皿として常に置く**: 1 体ずつ包んでいない例外も、段の単位で取りやめて残る。段の中の配線を忘れても、粒度が粗くなるだけで黙らない
- **commit 後の後始末に失敗した例外 (`CommandPostCommitException`) は、isolate でも止める**: trace には `committed: true` で残す。後始末できなかった transaction 資源を持ったまま次の 1 体の scope を開くと、資源を再利用してしまう。1 体の失敗ではなく世界の側の失敗なので、取りやめの対象にしない。これまでも各段はこの例外で止まっていた
- **CommandScope 1 回でない単位では `committed` を `null` で残す**: LLM のターンと確定後フックは、取りやめる前に何が確定したか分からない。`false` と書くと、rollback されたと読まれる
- **trace に残せないなら止める**: isolate でも、記録先が無いとき、記録そのものが失敗したとき、閉じた記録先が黙って捨てたとき (`seq` が負) は元の例外を投げる。記録先を持たない試験や API サーバーは例外で止まる。ログに出して続けていた出現条件の評価の失敗と注文の期限切れの失敗も、この構成では止まるようになった
- **`create_world_runtime` 以外で組み立てた段は fail_fast**: 段の既定は止める側で、`spot_graph_world_services.py` などで組み立てた段は部品を渡されず、これまでどおり止まる
- **fail_fast でも trace に残してから止める**: どこで止まったかを trace から読める。内側の単位が記録して投げ直した例外は、外側の段の単位で記録し直さない
- **既定は isolate**: `make experiment` はその場で書いた実験設定 (`mine_v1_002` もそう) でも回す。既定を fail_fast にすると、キーを書き忘れた run がまた止まる。でたらめに行動するスタブでシナリオの穴を探す試験 (#1557) のように、例外で止めたい試験は `"WORLD_TICK_FAILURE_POLICY": "fail_fast"` と書く
- **取りやめた 1 体は次の tick にまた試される**: 隔離して二度と試さない形にはしない。毎 tick 失敗するなら毎 tick 残るので、件数は独立した失敗の数ではなく、のべの数になる。続けて失敗したら run を止めるしきい値はまだ無い
- **件数が 0 でない run は、効果の測定に使う前に原因を切り分ける**: report.md の冒頭にその旨を出す

**ターンは CommandScope 1 回ではない**: LLM のターンを取りやめても、プロンプトを組むときに読み出した観測は戻らない。ツールの実行は中で例外を捕まえて `action_result` に残すので、取りやめに来るのはプロンプトの組み立てなど、ツールの外の例外になる。ツールの実行後に例外が出ると、ターン後の処理 (自分で次の手番を積む判断、予期の清算、短期記憶のターンの区切り) も飛び、その人は新しい観測が来るまで手番を待つ。

**どうしないと壊れるか**: 例外で run が止まると、費用をかけた run が途中で捨てられ、同じ穴に次の run でも当たる。ログだけに出して続けると、trace と報告からは何も起きていない run に見え、効果の測定に混ざる。

**関連**: design_decisions 5 / 10 / 67、`docs/agent_design_principles.md` の 6、Issue #1507 / #1508 / #1557 / #1558。

---

## D1558-2. 確定済みの処理に続く後処理の失敗は、取りやめずに trace に残して続ける

**何を**: commit 済みの処理に続く後処理 (通知、観測の配信、証拠の書き起こし、履歴の記録など) や、本体の前後の判断 (ゲーム終了の判定、ターンを回せるかの判定など) が例外を出したら、`WorldTickFailureIsolator.record_continued_failure` で trace の `world_tick_unit_failed` に `continued: true` で残し、処理は続ける。本体が確定済みなら `committed: true`、本体の前の判断や CommandScope 1 回でない本体 (ターン、心拍) なら `committed: null` にする。段の名前は `<段>.<後処理>` (`needs_decay.state_collapse_evidence`、`after_commit.observation` など) にする。件数は D1558 の件数に入り、report.md の冒頭の「世界の tick で例外を出した処理 (のべ)」に出る (Issue #1558)。

**なぜ**: ログに出して続けるだけの後処理は、trace と報告からは何も起きていない run に見える。#1507 では状態崩壊の証拠の書き起こしが毎回例外を出していたのに、証拠が 1 件も無いことに誰も気づかなかった。`CommandEventDispatcher` は失敗の受け口 (`failure_observer`) を持っていたが、どこにも配線されておらず、commit 後の best-effort ハンドラの失敗は warning だけだった。

**決まり**:

- **取りやめるものが無いので続ける**: 状態は確定済みで、後処理を止めても戻らない。1 体の処理の取りやめ (D1558) とは別の入口にする
- **isolate で記録先が無い構成ではログに残して続ける**: D1558 の「trace に残せないなら止める」は取りやめについての決まりで、後処理には当てはめない。止めても確定済みの状態は戻らず、記録先を持たない API サーバーを倒すだけになる。これまでと同じ動き
- **記録先があるのに記録できなかったときは止める**: 記録が例外を出したとき、閉じた記録先が黙って捨てたとき (`seq` が負) は、黙って続けない
- **fail_fast では trace に残してから止める**: 記録先が無ければログに残してから止める。続ける側に倒していた判断 (ターンを回せるかの判定、移動中かの判定、ゲーム終了の判定) も、fail_fast では倒さずに止める
- **fail_fast でも止まらない経路がある**: 投げ直した例外を外側が握る経路では、trace に残るだけで止まらない。`CommandEventDispatcher` の best-effort ハンドラ (受け口の例外をディスパッチャが握る) と、移動の段の到着の観察者 (到着の履歴など。観察者の例外を段が握って `travel.arrival_observer` として残すが、記録済みなので数え直さない) がこれに当たる。行動のあとの疲労の保存 (`action.fatigue`) もこれに当たる。ツールの中から投げ直しても phase_b が失敗の結果に変えて続けるだけで、確定済みの行動を LLM が繰り返すので、投げ直しは実行器が握って行動を成功のまま返し、ERROR のログに残す
- **fail_fast で確定後の失敗と通知の失敗が重なると、残るのは通知の失敗だけ**: `except CommandPostCommitException:` の中で通知が投げ直すと、元の例外は `__context__` に退き、`committed: true` の取りやめの行は残らない。isolate では起きない
- **部品を渡されていない段や観測の部品は fail_fast**: 単体で組み立てた試験で後処理の失敗が黙らないようにする。続ける動きを試すときは、isolate の部品と記録先を渡す

**揃えなかった後処理**: 盤に居ない人を飛ばす経路 (`world_runtime.py` の遠景の配信先、期限切れの提案の観測、到着の履歴で場所の名前が取れない人) は、例外を制御の流れとして使う正常な経路なので残した。例外の型を絞るのは別に扱う。trace の記録そのものの失敗も、残す先が無いので残した。

**どうしないと壊れるか**: 後処理の失敗がログにしか出ないと、証拠・観測・履歴が欠けた run が効果の測定に混ざる。欠けたものは「作られなかった」ことしか残らないので、後から探しても見つからない。

**関連**: design_decisions D1558、Issue #1507 / #1558。

状態崩壊の証拠の書き起こし (`needs_decay.state_collapse_evidence`) は、記憶の部品の撤去 (#1631) の #1642 で消した。段の名前の付け方の例としてだけ残す。

---

## D1569. 効果や出来事で持ち物から外れた品は、捨てたと言わず品名で伝える。出来事で消えたときの文は品の定義に書く

**何を**: `REMOVE_ITEM` などの効果、出来事、売買、取引の成立で持ち物から品を外すときは、`PlayerInventoryAggregate.remove_item` (取引の予約品は `remove_reserved_item`) を使い、`ItemRemovedFromInventoryEvent` を出す。本人が捨てたときの `drop_item` (`ItemDroppedFromInventoryEvent`) とは分ける。観測は持ち主にだけ届き、「〈品名〉が手もとからなくなった。」になる。シナリオの出来事で外れたとき (`by_world_event=True`) に限り、品の定義に `event_removal_message` があればその文にする。観測の整形 (`ObservationFormatter`) には、ランタイムが品の repository を渡す。

**なぜ**:

- 廃坑の山村の 3 本目の実 run (`var/runs/mine_v1_003`) で、灯の燃え尽きも、灯すときに使った油も「何かのアイテムを捨てました。」と届いた。燃え尽きの決まり (R7) を学ぶ手がかりにならず、自分が捨てたという誤った経験が記憶に残る
- 品名が出なかったのは、観測の整形にだけ品の repository が渡っていなかったため。入手も同じく「何かのアイテムを入手しました。」だった
- 燃え尽きや腐り落ちのように、世界の側で品が消える消え方は品ごとに違う。エンジンが文を持つと、シナリオの世界の言葉で書けないので、品の定義に書く
- 品の文を、外れた原因を問わず使う形にはしなかった。灯は奪うことも渡すこともでき、奪われた人に「燃え尽きた」と届くと事実と食い違う。人の操作で外れたときは、操作した本人にも、奪われた人にも、ほかの観測 (奪われた手がかり、操作の結果の文) が届くので、既定の文で足りる
- 効果の側に文を持たせる案は採らなかった。外す品の一覧は、効果から呼び出し元 (物体の操作、持ち物の操作、出来事) まで品の ID だけで運ばれていて、文を通すには 3 つの経路を変える必要がある。出来事かどうかの 1 ビットなら、出来事の経路で渡すだけで済む
- 品の定義 (`ItemSpec`) そのものに持たせる案も採らなかった。SQLite の表まで変わる。文は観測にだけ要るので、シナリオの品の定義から作った対応表を整形に渡す

**どうしないと壊れるか**: 効果で外す処理を `drop_item` に戻すと、使った・燃え尽きた品が「捨てました」と届く。整形に品の repository を渡し忘れると、持ち物の観測がすべて「何かのアイテム」になる。出来事の経路で `by_world_event=True` を渡し忘れると燃え尽きの文が届かず、整形で `by_world_event` を見ないと奪われた灯が「燃え尽きた」と届く (廃坑の山村の試験 `test_holder_hears_the_flame_burned_out_by_name` と `test_a_stolen_flame_is_not_said_to_have_burned_out` が落ちる)。

**今は直さないもの**: 同じ場所の人に届く、持ち物を使った観測 (`item_use_formatter`) にも品名が出るようになった。使った人の名前と品名を同じ文で出すが、暗い場所で名前を伏せる仕組み (design_decisions D1531) は持ち物の使用の観測を対象にしていない。暗い坑道で井戸の水や保存食を使うと、使った品の名前が同じ場所の人に届く。暗がりで伏せるべきかは、この PR では決めない。

**関連**: Issue #1569 / #1508。

---

## D1569-2. 前提条件で断られた操作の行も、成功の行と同じく操作の表示名で書く

**何を**: `interact` の resolver が、解決した操作の表示名 (`display_label`) から、対象名の後ろに続く句を作り、内部キー `ACTION_DISPLAY_PHRASE_KEY` で運ぶ。句は成功の行 (runtime の `do_interact` 系) と同じ助詞にそろえ、物と持ち物は「で〈表示名〉」、人は「に対して〈表示名〉」。dispatch が行動の引数に写し、行動の行の整形 (`_format_interact`) は句があれば「「対象」〈句〉」と書き、`action_name` を出さない。表示名は、その対象にいま出している操作にだけ付いている (`interaction_labels`)。出していない操作 (人の行で「いまできない」に回した操作、対象や操作が見つからなかったとき) は表示名が引けず、従来どおり「「対象」に 〈action_name〉 した」に戻る。

**なぜ**: 成功した操作は runtime が表示名で記録していたが、前提条件で断られた操作は phase_b の汎用の経路で生の引数から作られ、「「昇降機」に start_lift した → [失敗]」と出ていた (廃坑の山村の 3 本目の実 run)。`action_name` は呼び出しの値で、世界の言葉ではない。断られた行は呼び出しの手本 (`呼び出し:` の行) も残さないので (design_decisions 57)、内部の名前だけが経験として記憶に残る。

**どうしないと壊れるか**: dispatch で内部キーを行動の引数に写さないと、resolver が表示名を引いても行動の行に届かず、静かに元の形へ戻る (`tests/demos/test_action_result_records_the_canonical_action_name.py` の `test_failed_interaction_line_names_the_action_by_its_display_label` が落ちる)。

**今は直さないもの**: 失敗した行の `error_code=` と `tool=`。全シナリオに効き、design_decisions 57 の形を覆すので別の Issue で決める。

**関連**: Issue #1569 / #1508。

---

## D1569-3. 「行動の総量には限りがある」の行は、シナリオが外せるようにする。既定は従来どおり出す

**何を**: シナリオの `metadata.limits_actions` を false にすると、system prompt の「- 行動の制限: …総量には限りがある…」の行を出さない。既定は true で、文字列は従来と 1 文字も変わらない。廃坑の山村が false にした。

**なぜ**:

- 廃坑の山村は締め切りを置かず、時間で圧をかけない設計にしている。無い制限を system prompt で信じさせると、設計と食い違う
- 勝敗条件から自動で決める案は採らなかった。島のシナリオは締め切りを `TICK_LIMIT` ではなく出来事と個人結果の規則で書いていて、`TICK_LIMIT` の有無で決めると、本命の実験 profile (`belief_goal_full` の島) のプロンプトまで変わり、前の run と比べられなくなる
- 既定を変えないので、既存のシナリオのプレフィックスキャッシュ (design_decisions 1) も質感 golden も変わらない

**どうしないと壊れるか**: 既定を false にすると、締め切りのある世界で行動の制限が伝わらなくなる。真偽値以外を受け付けると、`"false"` と書いた人の意図と逆に常に出る (読み込み時に止める)。

**関連**: Issue #1569 / #1508。

---

## D1581. 名前を知らない相手は見た目で出し、名乗りか、同じ場所で名前を呼ばれるのを聞いたときに名前に切り替える

**何を**: シナリオの `players[].appearance` に見た目の短い説明を書く。知り合いの記録 (`Acquaintance`) に名前を知ったターン (`name_learned_turn`) を足し、会うことと名前を知ることを分けた。受け手が相手をどう呼ぶか (`PlayerAcquaintances.call_name`: 名前を知っていれば名前、知らなければ見た目) を 1 か所で決め、受け手ごとの画面と、記録に入る観測の 2 か所で使う (Issue #1581)。

**なぜ**: 廃坑の山村の実 run (`var/runs/mine_v1_004`) で、初めて会った 4 人が名前で呼び合った。同じ場所の人の一覧、到着の観測、【知っている人】、行動の対象の候補が、会った瞬間から名前を出していた。「誰だ？」と問う余地が無いと、出会いが平らになり、相手を知らないことから生まれる警戒や駆け引きも起きない。Being が知らない名前を環境が渡すのは、design_decisions D1520 の方針とも食い違う。

**決まり**:

- **見た目は `players[].appearance` に書く**: 誰かが最初から知らない人 (`knows_at_start` から外れる人) には必須。空、2 人で同じ、誰かの名前を含む見た目は読み込み時に止める。ある人の名前が別の人の名前の一部になっているシナリオも止める。persona と目的に、その人が最初から知らない相手の名前を書いたシナリオも止める。`knows_at_start` を書かないシナリオは全員を紹介するので、見た目は要らず、プロンプトも変わらない。番号つきの呼び方 (「見知らぬ人 1」) は世界の言葉ではないので採らない
- **紹介された相手は名前を知っている。会っただけの相手は名前を知らない**: 見た目の説明が無い人と会ったときは名前を知る。読み込み時の検査で、見た目の無い人は全員に紹介されているので、これは既存のシナリオを変えないためだけの形
- **名前を知るのは 2 つの場合**: (a) 名乗り: 話し手が分かる声 (「誰か」に伏せた版でない) の中に、話し手自身の名前がある。(b) 呼びかけ: 聞いた声の中に、受け手と同じ場所にいる人の名前がある。囁きは呼ばれた人に聞こえないので数えない。どちらも、受け手が会ったことのある相手に限る。遠くの声で名前を聞いただけでは、会っていない人の名前を知ったことにしない
- **(b) は、同じ場所に名前を知らない人が何人いても、呼ばれた人の名前を知ったことにする (限界)**: エンジンは誰が呼ばれたかを知っているので、取り違えは起きない。人なら呼ばれた人の返事などの文脈で見分ける、という単純化で、実際には聞き分けられない場面でも名前が決まる。名前を知らない人が 1 人のときだけ数える案は厳密だが、2 対 2 で出会う廃坑ではほとんど働かない。誰に向けた発言かを Jev に問う案は、毎回の呼び出しが要るので採らない
- **名前を知るのは、その声の観測の次から**: 名乗った声そのものは見た目で記録される。記録した行は書き換えない (D1520 と同じ)
- **画面では、同じ場所の人の一覧の名前を呼び方にする**: 一覧の名前 (`SpotGraphCurrentStateBuilder._name_seen_by`) は、【現在選べる対象引数】の値、名前から相手を引く解決、失敗文の候補、`co_present` の共通の鍵なので、エージェントは見た目をそのまま行動の対象に渡せる。名前を知った次のターンから、値が名前に変わる。取引の申し出の節も同じ呼び方にする。「(初めて会った)」は一覧の名前ではなくプレイヤー番号で知り合いの記録を引く
- **記録に入る観測では、structured に参加者として出ている人の名前だけを置き換える**: 受け手の版を選ぶ入口 (`PlayerAcquaintances.view_for`) で、structured の値または鍵が参加者の名前と一致する人を集め、本文と structured の文字列で見た目に置き換える。文の中から全員の名前を探すと、名前を含む別の語まで巻き込むので探さない。structured に出ていない名前は置き換わらないので、新しい観測は参加者を structured に書く。漏れたときは下の総当たりの見張りが落ちる。フォーマッタごとに 2 つの版を作る形 (D1520 の話し声) は、2 人目の名前 (受け渡しの相手、投票の内訳) を扱えず、新しいフォーマッタが忘れるので採らない
- **聞いた言葉は変えない**: 「」『』の中と、話し声の `content` は置き換えない。話し手が口にした名前は、そのまま聞こえる
- **届けない・「誰か」に伏せるの判定は「その人を知っているか」(紹介されたか会ったか) のまま**: 名前の置き換えはその後に別に行う。会ったが名前を知らない相手の遠くの声は「〈西の坂道〉の向こうから、髭の濃い大柄な人の遠くの声が聞こえる」のように届く
- **引けないときは見た目へ倒す**: 知り合いの記録を引けないとき、呼び方は見た目になる。名前は記録に入ったら消せない
- **名前を知ったことは trace に残す**: `name_learned` に、受け手、知った名前、それまでの見た目、知り方 (「名乗り」「呼びかけ」) を 1 件残す
- **snapshot では、名前を知ったターンの無い知り合いは読めない**: 知っている側へ補うと、名前を知らない相手の名前がプロンプトに出る。互換は保たない (#1436)
- **総当たりで見張る**: `tests/demos/test_unknown_names_vanish_from_the_prompt.py` が、互いを紹介しない人たちを同じ場所から始めてでたらめに行動させ (design_decisions D1557)、手番ごとに実際に送る本文とツールの定義から、手番の人が名前を知らない相手の名前を探す。見た目が出ていることと、一覧または観測の置き換えを外すと落ちることも確かめる

**残っている穴**: 取引・市場の結果の文と、看板の書き手の名前は、名前表から実名を引いていて置き換えを通らない (#1585)。総当たりの見張りのシナリオには取引・市場・看板が無い。

**どうしないと壊れるか**: 会うことと名前を知ることを分けないと、出会った瞬間に名前で呼び合う。画面と記録の片方だけを置き換えると、一覧の見た目と観測の名前が結び付き、名前が漏れる。全員の名前を文から探して置き換えると、名前を含む地名や品名まで書き換わる。

**関連**: design_decisions D1520 / D1531 / D1557 / Issue #1508 / #1520 / #1585 / #1605 (モンスターの攻撃と追跡の観測が標的の名前を structured に書いておらず、置き換わらなかった) / #1609 (倒された観測と取引を断られた観測が、倒した人と断った人の名前を structured に書いておらず、置き換わらなかった)。

---

## D1582. 有効な reasoning effort も、OpenRouter の統一の形で `extra_body` に載せる

**何を**: `LiteLLMClient` は、有効な effort (`minimal`〜`xhigh`) を `extra_body` の `reasoning: {"effort": <値>}` だけで送る。LiteLLM の top-level 引数 `reasoning_effort` は使わない。`none` は従来どおり `reasoning: {"effort": "none", "exclude": true}` と `thinking: {"type": "disabled"}` を送り、空文字は reasoning の欄を何も送らない。構築時の既定と、`invoke` / `completion_base_kwargs` の呼び出しごとの上書きは、同じ `_build_reasoning_block` を通る。

**なぜ**:

- LiteLLM は top-level の `reasoning_effort` を、モデル表で reasoning 対応と載っているモデルにしか通さない。載っていない `openrouter/deepseek/deepseek-v4.1-flash` では、送る前に `UnsupportedParamsError` で落ち、thinking ありの run を回せなかった。`extra_body` は LiteLLM が中身を見ずに本文へ合流させるので、モデル表に左右されない
- 無効化はもともと `extra_body` で送っていた。有効化も同じ形にすると、OpenRouter に届く欄が effort の値だけで切り替わる
- `drop_params=True` は採らない。LiteLLM が黙って `reasoning_effort` を落とすと、thinking が効いていない run を thinking ありとして比べてしまう

**どうしないと壊れるか**: top-level の `reasoning_effort` に戻すと、モデル表に無いモデルで全呼び出しが `LLM_FAILURE` になる。`tests/infrastructure/llm/test_litellm_client.py` の `test_enabled_effort_passes_litellm_param_check_for_unlisted_model` が、組んだ引数を LiteLLM の送信前の引数検査 (`get_optional_params`) に通して見張る。

**対象は OpenRouter 経由だけ**: `extra_body` の `reasoning` は OpenRouter の形で、OpenAI 直など他の provider に送ったときに effort が効くかは確かめていない。thinking を有効にしている実験設定は、すべて `openrouter/` のモデルを使う。他の provider で thinking を使うときは、その provider の渡し方を別に決める。

**今は決めないもの**: thinking と `tool_choice=required` が実 API で両立するか (docs/llm_provider_selection.md、#96)。両立しないと分かったときの扱いは、実 API で確かめてから決める。

**関連**: Issue #1582 / #1508。

---

## D1591. 操作が parameters から読むキーは、前提条件のものも効果のものも「が要る」で出す。キーが無いときは番号違いの文を使わず、キーを名指す

**何を**:

- `required_parameter_hints` は、前提条件 `PUZZLE_INPUT_MATCH` の `puzzle_input_key` と、効果 `WRITE_PLAYER_TEXT` の `text_param_key` (既定は `text`) を、どちらも物体の行の操作の候補に `"code" が要る` の形で出す。同じキーは 1 度だけ出す
- `PUZZLE_INPUT_MATCH` は、キーが無いか空のとき、シナリオの `failure_message` を使わず、`何を入れるか、parameters の "code" で指定してください。` を返す。キーがあって値が違うときは、これまでどおり `failure_message` を返す
- `interact` の説明は、表示の形を `『"キー名" が要る』` と書き、特定のキーを例に挙げない。`parameters` の例は「`"text" が要る` と出ていれば」と表示に結び付ける

**なぜ**:

- `var/runs/mine_v1_005` で、金庫の行に番号を渡すキーが出ず、4 人とも説明の例にあった `text` で番号を渡した。返った文は番号違いと同じ「ダイヤルを合わせて把手を引いたが、扉はびくともしない。」で、全員が番号を疑って坑道へ戻った。廃坑の山村の勝ち筋はこの金庫の鍵が要る
- キーが無いのは世界で起きた出来事ではなく、道具の呼び方の誤り。番号違いの文は「入力して試した」場面を書いているので、起きていないことを伝えてしまう。直すのに要るのはキーの名前で、それを書けるのはエンジンの固定の文だけ。`WRITE_PLAYER_TEXT` が `text` を渡されなかったときと同じ扱いにした
- 採らなかった案は Issue #1591 のコメントに残した。条件に `missing_input_message` を足す案は、作者が書き忘れると今と同じになり、世界の言葉ではキーの名前を書きにくい。道具の実行側で先に確かめる案は、判定がドメインと二重になり、ドメインを直接呼ぶ経路が区別されないまま残る

**どうしないと壊れるか**: 表示を足さずに試験だけ `{"code": "1907"}` を直書きすると、今回と同じく緑のまま表示の抜けを見逃す。`tests/demos/test_mine_village_safe_code.py` は、プロンプトの金庫の行から「が要る」のキーを読み取って引数を組む。`tests/infrastructure/scenario/test_required_interaction_parameters_are_visible.py` は、全シナリオの `PUZZLE_INPUT_MATCH` と `WRITE_PLAYER_TEXT` の宣言から要るキーを数え、候補の表示に出ているかを見張る。parameters を読む前提条件や効果を足したら、`required_parameter_hints` とこの監査の両方に足す。

**残っている穴**: 対人の操作 (`player_interactions`) は、奪う品の名前を `parameters["item"]` から読む (`TARGET_HAS_ITEM` の `item_spec_id_parameter_key` と、`GIVE_ITEM` / `REMOVE_ITEM` の `item_spec_id_parameter`)。同席者の行には「が要る」を出す経路が無く、廃坑の山村は表示名に「(奪う品の名前を item に書く)」と手で書いている。`station_drill` と `survival_island_v4_coop` の `loot_from_downed` は表示名が「持ち物を奪う」だけで、`item` がどこにも出ない。

**関連**: Issue #1591 / #1508、design_decisions 49。

---

## D1594. 同じ行動かを比べるとき、行動に添えた発言と、識別値の書き方の揺れを外す

**何を**: ループ警告が同じ行動かを比べる `build_argument_fingerprint` で、次の 3 つを比べない。

- `say_inline`。`ACCOMPANYING_SPEECH_FIELDS` に置く。周りに届くので主観ではなく、`NARRATIVE_ARG_FIELDS` には入れない
- 識別値 (分類表で `IDENTIFIER_STRING` の引数) の書き方の揺れ。dispatch が `__action_history_projection` に解決済みの値を載せていればその値で比べる。どちらの値からも両端の引用符は剥がす。解決済みの値を報告しない resolver では生値のまま載り、解決前に断られた呼び出しでは何も載らないため
- 運搬用の内部キー `__action_history_projection` そのもの。自由文の引数名の並びを持つので、`say_inline` の有無だけで別の行動になる

`__action_display_phrase` は残す。対象と操作が決まれば決まる値で、言い直しの検出 (design_decisions 233) が行動の要約に使う。

**なぜ**: `var/runs/mine_v1_004` と `mine_v1_005` で、ループ警告が 0 件だった。5 本目のハルは同じ金庫を同じ番号で T20、T24、T30 に試して同じ理由で断られており、離れた tick の失敗の閾値 (20 tick 以内に 3 回) に届いていた。発言が毎回違い、T20 は `"\"金庫\""` と引用符つきで渡していたので、数えられなかった。警告が出ないので、繰り返しの理由を問う判断 (design_decisions 232) も呼ばれていなかった。

**外さないもの**: `speak` の `content` は発言そのものが行動なので外さない。同じ言葉の繰り返しは完全一致の検出が、言い直しは意味上の検出が数える分担のままにする。自由文の両端の引用符も中身として比べる。

**言い直しの検出との関係**: 意味上の検出の要約は、表示名と識別値から作る。`say_inline` を持つ tool はどれも要約の表にあり、`say_inline` は前から要約に出ていない。発言だけを変えた同じ操作は、これからは完全一致の側が数え、意味上の検出は `exact_match_fired=True` で窓を空にする。警告は 1 件にまとまる。見立ての材料の `said` は `speak` の `content` だけで、`say_inline` は入れていない。

**どうしないと壊れるか**: loop guard を直接呼ぶ試験では、dispatch が足す内部キーを通らない。`tests/demos/test_mine_village_safe_retry_raises_loop_warning.py` は、本番と同じ session でプロンプトの対象表から `run_phase_b` を回し、発言を変えた金庫の 3 回の失敗で警告と見立てが 1 件ずつ出ることを見る。`say_inline` のような同乗の引数を足したら `ACCOMPANYING_SPEECH_FIELDS` に足す。

**関連**: Issue #1594 / #1508、design_decisions 232 / 233。

---

## D1596. 「(初めて訪れた)」は、着いてから最初の手番を実行するまでの間だけ付ける

**何を**: `SpotGraphUiContextBuilder` に、その player が実行し終えた手番の数を返す `executed_turn_provider` を渡す。初めて訪れた場所 (訪れた回数 1) で注記を出すとき、そのときの手番の数を (player, 場所) ごとに覚え、手番の数が同じ間だけ「(初めて訪れた)」を付ける。手番の数は `run_phase_b` が手番の実行を始めるときに数える `WorldRuntime._execution_turns` を使う。

**なぜ**: 訪れた回数は着いたときにしか増えない。`var/runs/mine_v1_004` と `mine_v1_005` では、事務所に留まった数ターンのあいだ「現在地: 鉱山会社の事務所 (初めて訪れた)」が出続け、エージェントはずっと新しい場所にいると受け取っていた。

**手番で数え、tick では数えない**: 着いた tick と最初の手番の tick は一致するとは限らない (エージェントごとの待ち時間がある)。同じ tick の中の順序も trace の tick 番号からは分からない。手番を実行する前なら、プロンプトを何度組み直しても同じ注記を出す (reason-first の 2 段や起動時の検査で組み直す)。

**訪れた記録は足さない**: 手番のあとに訪れた記録を足すと、留まっただけで訪れた回数が 2 になり、再訪と見分けられなくなる。最後に訪れた tick も変わり、これは想起の手がかりの時間窓に使われている。

**変えていないもの**: 「(初めて会った)」は、design_decisions D1520 のとおり会った回数が 1 の間ずっと付く。同じ場所に留まる相手にも付き続けるので、場所と同じ扱いにするかは別に決める。snapshot から再開した直後は、手番の数は戻るが、覚えた値は空から始まるので、初めて訪れた場所に留まっていれば再開後の最初のターンにもう一度付く。LLM の呼び出しが例外で終わった手番も `run_phase_b` は数えるので、着いた直後の手番が例外で終わると、本人が注記を読まないまま次のターンから消える。

**どうしないと壊れるか**: `executed_turn_provider` を渡さないと、これまでどおり留まっている間ずっと付く。`tests/integration/test_encounter_memory_prompt_integration.py` は、実 runtime で `run_phase_b` から 1 手を実行し、次のターンに注記が消えることを見る。

**関連**: Issue #1596 / #1508、design_decisions D1520。

---

## D1595. 呼び出しが失敗した人は次の tick に回し、同じ人の 3 回連続で打ち切る。thinking は出力の上限トークン数で抑える

**何を**:

- 主ターンの呼び出しが例外で落ちた手番 (`LLM_API_FAILED`。時間切れを含む) のあと、`WorldLlmTurnTrigger` はその人を次の tick の pending に戻す。同じ人が 3 回続けて失敗したら戻さず、観測か待ち時間のタイマーに任せる。成功か、ほかの結果を挟むと連続は切れる。打ち切ったあとの失敗は 1 から数え直す
- reason-first の状況評価の段で、呼び出しが 2 回とも例外で落ちた手番も同じ扱いにする。行動の段の例外はもともと `LLM_API_FAILED` を返していた
- 失敗のたびに trace の `llm_failure_retry` を 1 件残す。payload は `consecutive_failures` / `max_consecutive_failures` / `rescheduled` / `error_code`。打ち切った失敗は `rescheduled=False` で見分ける
- runtime_config の `LLM_MAX_OUTPUT_TOKENS` を、主ターンの呼び出しに top-level の `max_tokens` として送る。書かなければ送らない。送った値は prompt dataset の `request.kwargs` に残る

**なぜ**:

- `var/runs/mine_v1_005` で、95 秒の上限で止まった `litellm.Timeout` が 4 件あった。ミオは T32 の失敗のあと T38 まで動かなかった。失敗した手番は `should_reschedule=False` で返り、しかも手番の直後に待ち時間のタイマーがリセットされるので、起こす観測が届くか 6 tick 経つまで眠っていた
- 上限を 3 にしたのは、mine_v1_005 の失敗率 4/118 では偶然 3 回続く確率が 1/25,000 程度だから。続くなら一時的な遅れではなく、毎 tick 最大 90 秒ずつ run を止め続ける。run 全体を止める判断は `LlmFailureStreakMonitor` (design_decisions 214) が別に持つ。こちらは 1 人ぶんの手番を戻すかだけを決め、run を止めない
- 既存の自己 reschedule の連続 (`max_self_reschedule_streak`) には載せない。あちらは `was_no_op=True` で連続が切れる設計で、失敗した手番は `was_no_op=True` なので数えられない
- `LLM_REASONING_EFFORT=minimal` は「出力の上限の約 1 割を考えに回す」という指定で、上限を送っていないと抑えが効かない。#1590 の試しで、minimal・low・medium のトークン数が段階の順に並ばなかったのと合う
- OpenRouter の `reasoning.max_tokens` は採らなかった。effort と同時に送れず、直接効くのは Gemini・Anthropic・一部の Qwen で、DeepSeek についてはドキュメントに記載が無い (2026-10-11 に確認)。top-level の `max_tokens` は thinking と出力の合計の上限で、provider を問わず効く

**どうしないと壊れるか**:

- 失敗した人を戻さないと、thinking ありの run で長く考えた人ほど手番を失う。`tests/application/llm/services/world_llm_turn/test_failed_llm_call_retries_next_tick.py` が、実シナリオの runtime で時間切れを起こし、次の wave で呼び出しが起きることと、3 回目で止まることを見張る
- 上限トークン数の値が prompt dataset に残らないと、上限ありの run となしの run を後から見分けられない。`tests/infrastructure/llm/test_litellm_client_max_output_tokens.py` が本物の記録係で `calls.jsonl` の request を読む
- 上限で切れた呼び出しは、考えの途中で切れればツールを返さず「迷い」(`NO_TOOL_CALL`) になり、ツールの引数の途中で切れれば引数が空のまま実行される。どちらになるかは実 API で確かめていない。`memory_jev_mine_v1_v41_thinking_capped` の 4096 は、mine_v1_005 の成功した呼び出し 114 件で最も遅かった毎秒 49 トークンでも 84 秒で収まり、超えていたのは 4 件だった

**起動判定との関係**: 起動判定 (design_decisions 222) を入れた run でも、戻した人は落とされない。Phase A は呼び出しの前にプロンプトを組んで観測を取り出すので、失敗した人の未読は空になり、起動判定は「未読なし」で通す。失敗のあとに新しい観測が届いていたときだけ判定に問われ、その判定は trace の起動判定の行に残る。

**対象外**: 行動が成功したのに本人を起こす観測が出ず、6 tick 眠る件 (記憶を思い出すツール、結果の出ない探索など) は、原因が別なので Issue #1597 に切り出した。こちらは本人が手を決める前に手番を失う件で、あちらは手を決めて結果を受け取ったあとに起こされない件。

**関連**: Issue #1595 / #1597 / #1508、design_decisions 7 / 214 / D1582。

---

## D1600. 試して学ぶ決まりは、外れ方を足りないものごとに分け、満ちた瞬間を音で知らせる。答えは書かない

**何を**: 廃坑の山村の R4 (発電機を温めないと昇降機が動かない) で、次の 3 つにした。

- 昇降機の断りの文を、発電機が回っていない・温まっていない・燃料が 2 未満の 3 つに分ける。前提条件を `generator_running` → `generator_warm` → `generator_fuel_2` の順に並べ、それぞれに別の文を持たせる
- 温まった tick に、機械室とその隣の 3 か所と昇降機の乗り場にいる人へ、それぞれの場所の音の知らせを 1 回届け、番を回す。届け先は `players_at_spot` の出来事を場所ごとに置き、その後ろに「聞いた」のフラグ `generator_warm_heard` を立てる出来事を置く。フラグは発電機が止まると消える
- 日誌と給油の帳面には、温まりの手がかりを足さない

**なぜ**: `var/runs/mine_v1_006` で、鍵・温まり・燃料 2・席がそろった T36〜T38 に誰も把手を引き直さず、時間切れになった。T35 に把手を引いたときの断りの文は燃料不足のときと同じで、温まった T36 には知らせが無かった。外れ方が区別できなければ、試して外れても学べない。

**乗り場にも届ける**: T36 の時点で 4 人とも乗り場にいて、機械室には誰もいなかった。機械室とその隣だけでは、この run の誰にも届かない。昇降機は発電機の電気で動くので、操作盤の奥で音がするのは世界として自然に書ける。全員には届けない。起動と停止の唸りは坑道じゅうに響くが、唸りの質が変わったことは遠くでは聞き分けられない。

**3 つに分ける**: 2 つに分けると、発電機が止まっているときも「温まっていない」に入る。温まり前の文に「手応えはある」と書くと、止まっているときに嘘になる。回っていないときは、ポンプの断りと同じ「ぴくりとも動かない」にした。

**答えを書かない**: どの文も、温まり・燃料・発電機・準備を名指ししない。温まり前の文は「唸りがまだ荒く波打っている」と様子だけを書き、待てばよいとも何 tick とも書かない。起動の文を「荒い唸り」にし、温まりの知らせを「荒い唸りが、低く落ち着いた」にして、荒い→落ち着いたの対で学べるようにした。全員に届く起動の唸りからは「低い」を外し、落ち着いたあとの響きと重ならないようにした。

**帳面に足さない**: 外れ方と温まった瞬間が区別できれば、R4 は試して学べる。給油の帳面は缶のありかだけを書き、量やポンプの燃料を書かないと決めている。温まりを書くと手順書に近づく。覆る条件は、次の run で、温まり前に断られたあと落ち着いた知らせを受けても、誰も把手を引き直さないこと。

**どうしないと壊れるか**: 「聞いた」のフラグを立てる出来事は、知らせの出来事より後ろに並べる。前に置くと、同じ tick のうちにフラグが立って知らせが出ない。止まったときにフラグを消さないと、動かし直して温まっても知らせが届かない。`tests/demos/test_mine_village_noise_and_lift.py` の `TestGeneratorWarmthIsHeard` と `TestLiftRefusalTellsWhatIsMissing` が、届く場所・届かない場所・回数・文の違いを見張る。

**関連**: Issue #1600 / #1508、`docs/mine_village_scenario_design.md` の R4 と「温まりの学び方」。

---

## D1602. 伝聞から来た信念は、支持の内訳から【関連する学び】に印を付ける。推測の言い方を残すことは指示で頼み、作る前の判定は変えない

**何を**:

- 【関連する学び】の行に、信念の支持のうち伝聞の件数から印を付ける。支持がすべて伝聞なら「(人から聞いた話)」、一部なら「(根拠 6 件のうち 5 件は人から聞いた話)」、伝聞が無ければ何も付けない。行は `belief_recall_line` が組み、状況から引く経路 (`situation_recall.py`) と従来の経路 (`format_semantic_recall_section`) の両方が使う
- 信念をまとめる指示の絶対のルールに「材料が推測の言い方なら、確信度によらず命題も推測の言い方で書く。推測をいくつまとめても言い切りにしない」を足す
- 伝聞の節に「材料が伝聞だけなら命題に話し手を残す」と「ヘッジを外すかを決める支持から伝聞を除く」を足し、shortlist の各信念に `hearsay_support_count` を載せる。伝聞が無効な run では載せない (Issue #1602)

**なぜ**: `var/runs/mine_v1_006` の T34 に、サヨはミオの推測 4 件 (はず・と思う・かもしれない・依頼) から「切り替え弁の目盛りが正しくないと昇降機に動力が来ない」を言い切りで作った。弁は昇降機と関係なく、誤りだった。T36 に発電機が温まり、把手を引けば脱出できたのに、サヨはこの学びを reasoning で引いて昇降機を試さなかった。指示は確信度に応じた言い方を求めるだけで、材料の推測を残せとは書いていなかった。表示は文だけで、信念が持つ伝聞の件数を使っていなかった。

**決まり**:

- **出どころは文ではなく支持の内訳で示す**: LLM が文を言い切りで書いても、伝聞から来たことは必ず見える。指示が守られたかは確かめられないので、確かめられる部分をコードに置く
- **伝聞の件数は数で出し、閾値を置かない**: 「大半が伝聞」のような線を引くと、その線のすぐ下の信念に印が付かない。run の終わりのサヨの信念は、支持 6 件のうち 5 件が伝聞で、残りの 1 件は反証だった約束の破れが支持に入ったものだった
- **自分の体験の信念には印を付けない**: 毎ターンすべての行に印を付けると【関連する学び】が長くなる。印の無いことが「聞いた話ではない」を表す
- **推測かどうかは保存しない**: 推測は文の言い方に残すことに頼る。言い方から規則で読むと、「らしい」「ようだ」などの言い換えを取りこぼす

**採らなかった案**:

- 作る前の判定 (design_decisions 237) に「材料は推測や伝聞だけか」を問う: 判定に渡す state は信念の文だけで、材料を見ていない。材料を渡して問うても、Jev は選ぶだけで文を直せないので、当たったときの行き先が「作らない」しか無い。他の人から教わること自体は止めない (#1574)。文を書き換える部品を足すことになり、記憶の部品を減らす検討 (#1587) と逆を向く。判定が無効な run では効かないことも理由
- 既存の snapshot の言い切りの信念を推測に直す、または持ち越さない: 直すには文を書き換える呼び出しか語の規則が要る。持ち越さないと、正しかった伝聞 (「金庫の番号は1907」) も消える。印は保存済みの `hearsay_support_count` から作るので、snapshot に残った伝聞の信念にも読み込んだ時点から印が付く。snapshot の形は変えない

**限界**: 本人の予期の外れから作った言い切りすぎの信念 (同じ run のミオの「機械室の発電機は燃料や鍵だけでは動かない」) は、伝聞を含まないので印が付かない。外れの経路は design_decisions D1509 で扱う。能動想起の `memory_search_semantic` が返す要約には印を付けていない。mine_v1_006 では無効だった。

**どうしないと壊れるか**: 印を外すと、他の人の推測が自分で確かめた決まりと同じ形で頭に載り、直近の出来事より優先される。shortlist に伝聞の件数を載せないと、伝聞が 3 件積まれただけでヘッジを外す言い直しが選ばれうる。

**関連**: Issue #1602 / #1574 / #1587、design_decisions 237 / D1509 / D1568。

伝聞を抜き出す部品と固める側の伝聞節 (`HEARSAY_ENABLED`) は、記憶の部品の撤去 (#1631) の #1649 で消した。「推測の言い方を残す」決まりは残る。【関連する学び】の印の処理と伝聞の件数 `hearsay_support_count` は、信念の残りを消すまで残る。伝聞の証拠が作られなくなったので、新しく作る信念に印は付かない。

【関連する学び】 (`SEMANTIC_PASSIVE_TOP_K` と `SemanticPassiveRecallService`) は、記憶の部品の撤去 (#1631) の #1786 で消した。印を付ける行 (`belief_recall_line`) も一緒に消えた。

---

## D1601. 行動に添えた発言は、行動の結果を問わず dispatch で 1 回出す

**何を**:

- `say_inline` を各ツールの handler から外し、dispatch (`wire_missing_spot_graph_tools` の配線) で handler を包む `wrap_with_say_inline` から出す。handler が返った後に `SpotGraphToolExecutor.speak_say_inline` を 1 回呼ぶ。成功、前提条件の失敗、名前の解決の失敗、疲労による拒否のどれでも出す。handler が例外を投げたときも出し、届いたかを例外に載せて外へ出す。例外から失敗の結果を作る `phase_b` が、それを結果文と trace に書き足す
- 包むのは、ツール定義に `say_inline` を持つツールすべて。名前の一覧はツール定義から作り、手で並べない
- 包みは resolver の外側に置く。対象の名前を解決できず executor が呼ばれない場合も、発言は届く
- 発話そのものが断られたとき (speech service が未配線、倒れていて声が出せない、居場所が無い) は、結果文の末尾に「（添えた発言は届かなかった）」と足す。trace の `tool_trace_payload` に `say_inline_spoken` (`true` / `false`) を残す。`say_inline` が無い行動には何も足さない
- 介抱 (design_decisions 194) も失敗で届ける。scope が閉じてから発言を出す順序は保つ

**なぜ**:

- `var/runs/mine_v1_006` の T17〜T20 で、籠の前の駆け引きの宣言 (ゲンの「サヨ、鍵を差せ」、ミオの「俺もハルと二人で外へ出る約束なんだ」など 5 件) が、前提条件で断られた interact に添えられていて相手に届いていなかった。本人は聞こえた前提で次の行動を選んでいた
- 原因は 194 ではなく、`say_inline` を入れたときからの形だった。各 handler が成功の経路の最後でだけ発言を出しており、後から足したツールも同じ形を写した。194 の「失敗した介抱を発話しない」もこの形を介抱で保ったものだった
- 口にしたことと、行動が通ったかは別のことである。籠が動かなくても「鍵を差せ」と言った声は乗り場に響く。意図の表明や交渉の言葉は、行動が断られる場面でこそ要る
- 各 handler に発言を置き直す案は採らなかった。22 ツールの失敗の `return` すべてに置く必要があり、ツールを足すたびに同じ漏れが起きる

**届き方**: 発言は `speak` と同じ経路 (`SpeechChannel.SAY`) で出すので、届く範囲は成功した行動の発言と変わらない。同じ場所の人には全文、隣の場所の人には断片 (design_decisions 130) が届き、話し手の名前の伏せ方も同じになる。`say_inline` は囁きにならないので、囁きの規則はかからない。

**届けないもの**: `say_inline` を持つツールで選り分けて届けないものは無い。届けないのは次の 2 つで、どちらも本人の結果文に「（添えた発言は届かなかった）」と出る。

- handler まで届かない行動: 世界に無いツール名 (`UNSUPPORTED_TOOL`)、いまのフェーズで出していないツール (`TOOL_NOT_OFFERED_NOW` など。会議中の `interact` が典型)。行動そのものが世界で起きていないので、それに添えた発言も起きていない扱いにする。会議中の発言には会議の規則があり、出していないツールの引数から抜け道を作らない
- 発話そのものが断られたとき: speech service が未配線、または `speak` が例外を投げたとき。世界の規則による拒否 (`SpeechCommandException`。倒れていて声が出せない、居場所が決まっていない) は warning、それ以外は不具合として `logger.exception` に残す

**どうしないと壊れるか**:

- handler の中で発言を出すと、dispatch の包みと二重に出る。`tests/application/llm/services/executors/test_spot_graph_say_inline.py` が、handler 単体では発言が出ないことを見る
- `tests/demos/test_words_said_with_a_refused_action_are_heard.py` が、本番と同じ session で `run_phase_b` から、前提条件・名前の解決・疲労・介抱の 4 通りの失敗で発言が届くこと、断られた行動と成功した行動で聞き手の観測が同じになること、世界に無いツールの発言は出さずに本人へ伝えること、handler が例外で終わったときの扱い、`say_inline` を持つツールがすべて包みを通ることを見る
- 包む対象は `get_spot_graph_specs` のツール定義から作る。別のカタログに `say_inline` を持つツールを足すと包まれず、上の試験でも見えない。足すときはこの一覧の作り方を広げる

**対象外**: 発言が行動の結果を先取りする問題 (拾えていないのに「見つけました」と言う) は扱わない。発言が届くようになったので、先取りした発言も届く。Issue #1612 に切り出した。

**関連**: Issue #1601 / #1508、design_decisions 130 / 194。

---

## D1607. 引数が渡されずに断られた操作は、同じ場所の他の人に失敗として見せない

**何を**: 物体への操作で、parameters から読むキーが無くて断られたとき、ドメインは `InteractionNotAllowedException` の子の `InteractionParameterMissingException` を投げる。いまは前提条件 `PUZZLE_INPUT_MATCH` のキーが無いか空のときと、効果 `WRITE_PLAYER_TEXT` の文字列が無いとき。application 層は、この例外のときだけ `SpotObjectInteractionFailedEvent` を出さない。シナリオの `on_failure_observation` があっても出さない。本人には、これまでどおりツールの結果でキーの案内が返る。

**なぜ**: 目撃者向けの失敗の文は、断られた理由の文をそのまま使って「{actor}が{object}の「{label}」を試みたが、{reason}」と組む。廃坑の山村で、ハルが金庫を `"code"` 無しで開けようとすると、ミオの観測に「…を試みたが、何を入れるか、parameters の "code" で指定してください。」が出ていた。キーが無いのは道具の呼び方の誤りで、世界では何も起きていない (design_decisions D1591)。目撃者はツールの引数名を世界の出来事として読み、記憶に入れる。操作の案内を世界の出来事として読ませないのは design_decisions D1509 と同じ方針。

**見せないことにした理由**: 案内の部分だけを伏せて「…を試みたが、うまくいかなかった」と見せる案は採らなかった。ハルは番号を入れておらず、金庫は動いていない。「試みた」も起きていないことになる。`on_failure_observation` を出さないのも同じ理由で、作者の文は試して失敗した場面を書いている。

**型で分ける**: 理由の文から引数の案内かを見分けると、文面を変えただけで目撃者に漏れる。作者の文を分類のキーにしない方針は Issue #380 (`precondition_failure_kind.py`) と同じ。前提条件の失敗は `failed_condition` を運ぶので、キーが無い失敗かは、条件と parameters から `_lacks_puzzle_input` で判定する。判定は前提条件の評価と同じ関数を使い、二重にしない。子の例外にしたので、`InteractionNotAllowedException` で受けている道具の実行側とループ検出は変わらない。

**どうしないと壊れるか**: parameters からキーを読む前提条件や効果を足したら、キーが無いときに `InteractionParameterMissingException` を投げる。親の例外のままだと、目撃者に案内が漏れる。`tests/demos/test_mine_village_safe_witness_sees_no_parameter_guidance.py` は、実 session でハルが `"code"` 無しで金庫を試すとミオの観測に失敗の文が出ず、番号違いなら出ることを見る。`tests/application/world_graph/test_missing_parameter_failure_is_not_witnessed.py` は、看板の `text` 無しで失敗の観測が出ないことを見る。`tests/domain/world_graph/test_missing_puzzle_input_is_a_distinct_refusal.py` は、キーが無い・空・空白だけのときに子の例外を、番号違いのときに親の例外を投げることを、物体の経路と道具に宿る操作の経路の両方で見る。

**残っている穴**: 対人の操作 (`player_interactions`) で `parameters["item"]` が無いときは、「相手がそれを持っていない」と同じ前提条件の不成立として扱う。対人の操作は目撃者に失敗の観測を出さないので、いまは漏れない。でたらめに行動するスタブ (design_decisions D1557) は、目撃者の観測に出た引数名を漏れとして数えていない。

**関連**: Issue #1607 / #1591 / #380、design_decisions D1591 / D1509 / D1557。

---

## D1613. 体の届く範囲の前提条件は、試して学ぶ決まりの前提条件より先に確かめる

**何を**: 廃坑の山村の昇降機で、次の 2 つにした。

- 昇降機を動かす操作 (`start_lift`) の前提条件を、籠がもう上がったか → 籠の中の場所 (`HAS_ITEM lift_berth`) → 鍵 → 発電機が回っている → 温まっている → 燃料 2 以上、の順に並べる。籠に乗り込んでいない人には、鍵・温まり・燃料の状態によらず「操作盤は籠の中にある。乗り込まないと、把手に手が届かない。」が返る
- 昇降機の説明を「籠の中の奥の壁に操作盤があり、鍵穴と始動の把手が付いている。乗り込まなければ手が届かない。」にする

**なぜ**: `var/runs/mine_v1_006_r2` で、説明の「脇に操作盤があり」から、ミオが T17 に「籠の脇の操作盤なら外から引ける」と推論し、T28〜T33 に 4 人全員へ広がった。籠の中の場所の確認は前提条件の最後にあり、籠の外で把手を引いたゲンには鍵の文が返った。外から引けないという文は、この run で一度も返らなかった。ゲンは外に残って引く役を申し出て籠を降り、籠の中のサヨが把手を引いて取り残された。

**並べ方の決まり**: 本人の体がその操作に届くかを、先に確かめる。届かない人に鍵や温まりの文を返すと、「届いてはいるが、ほかの何かが足りない」と読める。籠の外からの試行は、温まりや燃料の手がかりとして読まれ、操作盤の位置の思い違いを強める。籠がもう上がったかの確認だけは籠の中の場所より前に置く。上がったあとは、乗り込もうにも籠が無い。籠の外の人には、鍵を持っているかも分からなくなる。鍵の文は乗り込んでから返るので、乗り込むことと鍵を探すことの順は、試して学ぶことになる。これは受け入れる。外から鍵を確かめられても、外からは動かせない。

**説明に書いてよい理由**: design_decisions D1600 は、試して学ぶ決まり (R4) の答えを文に書かないと決めた。操作盤の位置は試して学ぶ決まりではなく、見れば分かる物の配置である。見れば分かることを伏せると、学ぶ対象ではない思い違いが勝敗を決める。

**どうしないと壊れるか**: 物の位置を前提条件にする操作を足すときは、その前提条件をほかの不成立より先に置く。後ろに置くと、断られた人は位置を正されないまま、ほかの理由で断られ続ける。`tests/demos/test_mine_village_noise_and_lift.py` の `TestLiftControlsAreInsideTheCage` が、鍵が無い・発電機が止まっている・温まっていない・燃料が足りないの各状態で籠の外の人に操作盤の文が返ること、説明の操作盤の文が籠の中と書くこと、断りの文がすべて違って trace の行動の結果から理由を区別できることを見る。籠に乗り込んだ人に D1600 の文が返ることは `TestLiftRefusalTellsWhatIsMissing` が見る。

**扱わないこと**: すでに snapshot に残った「操作盤は籠の外」の信念は直さない。記憶の側の検討 (Issue #1587) で扱う。

**関連**: Issue #1613 / #1600 / #1587 / #1508、design_decisions D1600、`docs/mine_village_scenario_design.md` の「昇降機の籠」。

---

## D1618. 個人結果の規則は、世界の段の中と全員の手番のあとの 2 回判定する

**何を**: `SpotGraphSimulationApplicationService` は、`player_outcome_rule` の段を世界の段の中 (`death_grace` の前) で走らせたうえで、`_run_post_tick_hooks` の `llm_turn_trigger` のあとにもう一度走らせる。手番の中の操作で立ったフラグ (廃坑の山村の `lift_departed`) は、その tick のうちに、そのときの位置で判定される。2 回目は hook として並べ、手番が失敗しても、それまでの手番で立ったフラグを判定する。

**なぜ**: 1 tick の中では、世界の段 (移動 → 出来事 → … → 個人結果の判定) が先に走り、エージェントの手番はそのあとで回る。手番で立ったフラグは次の tick の判定で読まれ、そのときには次の tick の移動がもう反映されている。`var/runs/mine_v1_007_memo` では、T36 の手番でゲンが昇降機を動かし、乗り場へ向かう途中だったサヨが T37 の移動の段で着いてから判定されて脱出し、チーム南が勝った。籠の中の場所の説明「籠が上がるときに乗り場にいれば、一緒に地上へ出られる」と食い違う。正しくは、サヨは取り残され、両チームとも負けだった。

**ほかの案**: 判定を手番のあとへ移して 1 回だけ走らせる案は採らなかった。島のシナリオで、移動で山頂に着いた人が救助の前に 1 回手番を持つようになる。死亡の猶予の段が判定より先に走るので、猶予が切れた tick に救助の機会が来た人が `DEAD` になり、同じ tick なら救助が死亡に勝つという約束 (Issue #621) が逆になる。手番の中で操作のたびに判定する案は、手番を回す `turn_trigger` が個人結果の段を知ることになる。昇降機を動かした人より後に手番が来た人は籠が出たあとの世界で 1 回動けるが、乗り込む操作も降りる操作も `lift_departed` の前提条件で断られ、移動は次の tick まで反映されないので、判定は変わらない。比べた内容は Issue #1618 のコメントにある。

**2 回走らせても壊れない理由**: `once: true` の規則は 1 回目で発火済みになり、2 回目では読み飛ばされる。結果が決まった人は `set_outcome` が何もしないので、結果の知らせは 1 人 1 回のまま。島のシナリオの救助の規則は時刻が発火の条件で、世界の段の中で発火済みになるので、振る舞いは変わらない。手番のあとの判定で `RESCUED` になった人は、次の tick の猶予の段で `DEAD` に上書きされない。同じ tick の世界の段で猶予が切れて `DEAD` になった人は、その tick の手番で昇降機が出ても `DEAD` のまま (籠が出る前に死んでいた)。

**trace で区別する**: 個人結果の規則の評価の trace (`scenario_predicate_evaluated` の `purpose` が `player_outcome_trigger` / `player_outcome_eligibility`) は、`evaluation_point` に `world_stage` か `after_turns` を持つ。同じ tick に同じ規則の評価が 2 件並ぶので、どちらの判定で発火したかを並び順から復元させない。2 回目は `PlayerOutcomeRuleStageService.run_after_turns` で、段の型 `_PlayerOutcomeRuleTickStage` がこれを求める。

**どうしないと壊れるか**: 手番の中の操作でフラグを立て、それを個人結果の規則の発火の条件にするシナリオは、この 2 回目の判定に頼っている。2 回目を外すと、籠が上がったあとに着いた人が脱出する。`tests/integration/test_player_outcome_judged_in_the_tick_of_the_turn.py` は、廃坑の山村で、手番で昇降機が出た tick のうちに全員の結果が決まり、移動中のサヨが次の tick に着いても取り残されることと、島の 3 本で、救助の tick に移動で山頂に着いた人が手番より前に救助されることを見る。島の 3 本は直す前から通り、世界の段の判定を外すと落ちる。結果の知らせが 1 人 1 回の試験は、`once` の読み飛ばしと `set_outcome` の冪等の両方が崩れたときだけ落ちる。`tests/application/world_graph/test_spot_graph_simulation_stage_order.py` は段の順番と、手番が失敗しても 2 回目が走ることを、同じ統合試験の `TestOutcomeJudgementTraceTellsWhenItWasJudged` は `evaluation_point` を、`tests/application/world_graph/test_player_outcome_rule_after_turns_and_death_grace.py` は猶予の段との順番の約束を見る。

**残っている穴**: tick の外から手番を回す入口が 1 つ残っている。`presentation/spot_graph_game/runtime_manager.py` の `run_scheduled_llm_turns` (`POST /api/sessions/{session_id}/llm-turns`) は `turn_trigger.run_scheduled_turns()` を直接呼ぶので、そこで立ったフラグは手番のあとの判定を通らず、次の tick の世界の段で、移動のあとに判定される。セッションは `data/scenarios` のどのシナリオでも作れるので、廃坑の山村でこの入口を呼べば Issue #1618 と同じことが起きる。ただし、この入口を呼ぶものはリポジトリに無く、入口を足したとき (2026-04-25) から削除済みの `frontend/` まで含めて一度も無い。実験は `make experiment` から tick を回し、`spot_graph_game` のサーバも `tick_loop` が `advance_tick` を呼んで tick の中で手番を回すので、どちらも手番のあとの判定を通る。呼ぶものが無いので配線は足していない。呼ぶものを足すときは、手番のあとに `run_after_turns` を呼ぶ配線を足すか、入口を消す。

**関連**: Issue #1618 / #621 / #1508、design_decisions 43、`docs/mine_village_scenario_design.md` の「温める時間 (R4) と昇降機」。

---

## D1616. システムプロンプトの記憶の指示は、組み上がった runtime が実際に出す欄とツールから書き分ける

**何を**:

- `build_world_system_prompt` は `relevant_memories_shown` と `active_recall_offered` を既定値なしで受け取る。【関連する記憶】と能動想起のそれぞれの有無で、「確かな記憶」の文と【文脈と履歴の限界】の文を 4 通りに書き分ける。両方ある設定の文は、これまでとバイト単位で同じ
- 2 つの値は `create_world_runtime` の末尾で、組み上がった runtime から決める (`WorldRuntime._memory_parts_named_in_system_prompt`)。【関連する記憶】は episodic stack に受動想起があるか。能動想起は `get_tool_definitions(for_every_player=True)` に `ACTIVE_RECALL_TOOL_NAMES` のどれかが入っているか。そのためシステムプロンプトの組み立ても関数の末尾へ移した
- `memory_recall_by_handle` の説明は、`memory_recall_episodes` も出す設定でだけ「自由文での検索は `memory_recall_episodes` を使う」と書く

**なぜ**: `var/runs/mine_v1_007_memo` (profile `memory_jev_mine_v1_v41_thinking_capped_memo_only`、エピソードと想起を止めた設定) のシステムプロンプトが、「【関連する記憶】または能動想起で取り出した内容だけが確かな記憶」「【関連する記憶】が空のときは能動想起の手段を試す」を指示し続けた。この run では欄もツールも出ていない。サヨ T20 は「The instructions mention 能動想起 but no tool」と探し、ゲン T20・T23、サヨ T26 も同じように探した。記憶を比べる run で、記憶なしの条件が無い手段を探すことに手番を使うと、比較が濁る。CLAUDE.md の「プロンプト本文にツール名を書くときは、必ず露出判断を通す」と同じ穴で、欄の名前にも同じ扱いが要る。

**設定値ではなくツールの一覧から決める理由**: 能動想起のツールは、設定と実行器の有無の両方がそろったときに出る。`memory_recall_by_handle` には設定が無く、見出しと想起スロットの store がそろったときだけ出る。`LLM_TOOL_MODE` の純スポットグラフでは、記憶のツールが丸ごと隠れる (この設定は #1631 の #1762 で消した。いまは `include_todo_tools=False` で組んだときに隠れる)。設定から推すと、これらの経路で本文と一覧がずれる。一覧は design_decisions 44 の入口が決めたものなので、本文もそれを読む。

**既定値を置かない理由**: 置くと、渡し忘れた呼び出しが「両方ある」文へ黙って戻り、無い欄とツールをまた探させる。

**プレフィックスキャッシュ**: どちらの値も設定と起動時の配線だけで決まり、run 中は変わらない。design_decisions 1 は保たれる。

**どうしないと壊れるか**: 記憶の欄やツールの名前をシステムプロンプトやツールの説明に書くときは、その欄やツールが出ているかを見て書き分ける。`tests/demos/test_disabled_memory_parts_vanish_from_the_prompt.py` が、全部入りの設定から記憶の部品を 1 つずつ止め、1 ターン目のシステムプロンプト・user 文面・ツール定義のどこにも名前が出ないことを見る。正の対照として、全部入りでどの名前が出るかも固定している。`tests/demos/test_disabled_tools_vanish_from_the_prompt.py` と違って、名前の表はツールの一覧から自動では作らない。記憶の欄やツールを足したら、`_ALL_NAMES` と `_DISABLED_PARTS` に足す。

**関連**: Issue #1616 / #1587 / #1621、design_decisions 1 / 44。

**その後**: 全部入りの profile (`memory_jev_mine_v1_v41_thinking_capped`) とメモだけの profile は Issue #1631 で退役させた。試験は、新しい記憶の profile に全部入りの run が入れていた古い部品を戻して全部入りの設定を作る。退役前の profile と、止める部品ごとの 1 ターン目のプロンプトが一致することを確かめてから置き換えた。

能動想起の道具は Issue #1631 の #1767 で消した。`active_recall_offered` と `ACTIVE_RECALL_TOOL_NAMES` も消え、書き分けは【関連する記憶】の有無の 2 通りになった。【関連する記憶】だけがある設定と、どちらも無い設定の文は、消す前とバイト単位で同じ。試験の名前の表には能動想起の名前を残し、どの設定でもプロンプトに戻ってこないことを見張る。

受動想起【関連する記憶】も記憶の部品の撤去 (#1631) の #1796 で消したので、`relevant_memories_shown` と `WorldRuntime._relevant_memories_named_in_system_prompt` も消え、記憶の指示は記憶を止めた設定の文だけになった。station_drill のシステムプロンプトも、この文に変わった。

---

## D1623. 目次つきのエピソードは、ゲームから切り離した別の型で持ち、呼び名は重なったときに新しい側だけを伸ばす

**何を**:

- `being/domain/episode.py` に `Episode` (1 件で集約の根) と `EpisodeIndex` (目次の値)、`IndexRevision` (直す前の目次と直したターン) を置く。今の `SubjectiveEpisode` とは別の型で、場所・人・物の番号も、持ち主の `BeingId` も持たない。持ち主は保存の側 (`EpisodeRepository`) が Being ごとに分ける
- 本文は 400 字まで、目次の 2 つの文は 40 字まで、どれも空や空白だけは不可。超えた文はドメイン層が受け付けず `EpisodeValidationException` を投げる。切り詰めはアプリケーション層の仕事にする (Issue #1623 の決めたこと)
- 本文は作ったあと変えない (`frozen`)。目次を直すと、前の版を直したターンと一緒に `index_history` に足す。呼び出すと回数が 1 増え、最後に呼び出したターンが記録される。ターンはどれも Being の記憶のターン数で、戻ることは許さない
- 目次に載せる分の選び方は `EpisodeIndexSelection` (一覧と N を受け取り、表示する順に返す)。実装は 2 つ。書いた時の新しい順 (`NewestFirst`) と、書いた時と最後に呼び出した時のうち新しいほうの順 (`RecalledRisesToTop`、Issue #1623 の追記で最初に使うと決めた並べ方)。どちらも同じターンなら後から足した方を先に出す。どちらを使うかと N は profile から組み立ての段で選ぶ (PR 4)
- 呼び出しは `recall_episodes` (`being/domain/episode_recall.py`) で、呼び名をまとめて受け取り、渡した順に呼び名ごとの結果を返す。知らない呼び名は `episode=None` を返し、記録を増やさない。1 回の呼び出しで同じ呼び名を 2 回渡しても 1 度だけ数える。どれか 1 件でもターンが決まりに合わなければ、どれも書き戻さない。途中まで書き戻すと、ツールが失敗を返したのに回数だけ増えた記憶が残る。件数の上限 M は profile の値なので、ツールの側で確かめる (PR 4)
- `InMemoryEpisodeRepository` を足し、`BeingMemorySnapshotService` の `being_episodes` に配線した (design_decisions 27 の 4 手順)。`WorldRuntime._being_episode_store` が常に持ち、`ExperimentSnapshotSession` では必須の store にした。SQLite の実装は作っていない。手本の知り合いの記録も in-memory だけで、Being の記憶は snapshot で持ち越すため

**呼び名を ID だけから毎回作らない理由**: 呼び名は `ep_` と ID (区切りの `-` を除いた 16 進) の先頭 6 文字で、同じ Being の中で重なったら 1 文字ずつ伸ばす。伸ばすのは後から足した側だけにした。前からある側も伸ばすと、プロンプトの履歴に残った `ep_3f2a7b` が指す先が変わる (design_decisions 3 のラベルが変わって混乱した問題と同じ形)。どちらが後かは足した順で決まり、ID だけでは決まらない。そこで呼び名をエピソードに持たせ、snapshot にもそのまま入れる。読み込むときは ID から作り直さず、呼び名の無い payload は拒む。作り直すと、伸ばした呼び名が 6 文字に戻り、前からある呼び名と重なる。エピソードの側では「呼び名は `ep_` + ID の先頭 6 文字以上」だけを不変条件として確かめる。Issue #1623 は「今の `afterglow_store.py` と同じ作り方」と書いているが、今の `make_afterglow_handle` は常に 6 文字で伸ばさない。重なりは引くときに新しい方を選んで済ませている

**ID を UUID に限る理由**: 呼び名を作る文字を 16 進に揃えるため。大文字の UUID も拒む。同じ ID から大文字と小文字の 2 通りの呼び名ができないようにするため

**例外の合わせ方**: 手本の `acquaintance.py` は `AcquaintanceInvalid(ValueError)` を投げているが、CLAUDE.md の「ドメイン層では組み込み例外ではなくドメイン例外を投げる」に合わない。エピソードは `domain/being/exception/being_exceptions.py` に `EpisodeValidationException` / `EpisodeConflictException` / `EpisodeNotFoundException` を足し、`BeingDomainException` とカテゴリ例外の多重継承にした。snapshot の codec では、予期の codec と同じく `DomainException` を `ValueError` に包み、`BeingMemoryPayloadFormatError` として見せる。`acquaintance.py` はこの PR では直していない

**書き戻しを保存の側で確かめる理由**: `frozen` は代入を防ぐだけで、本文を変えた別のインスタンスや、目次の履歴を消した版も作れる。`save` は `Episode.follows` で、記録の版から呼び出しと目次の直しだけで行き着ける版か (本文・書いた時・環境の名前・呼び名が同じ、回数も最後に呼び出した時も戻らない、前の履歴を先頭に含む、目次を替えたなら記録の目次を前の版として履歴に足している) を確かめ、違えば `EpisodeConflictException` で止める

**この PR より前の snapshot は読めない**: `being_episodes` の欄が無い payload は、知り合いの記録を足したときと同じく形式エラーで拒む。空として補うと、欄を書き忘れた payload と見分けられない。design_decisions 6 (後方互換を過度に守らない) に従う。前の snapshot から再開したい run は、この PR を含む main で 1 回目から回し直す

**どうしないと壊れるか**: 呼び名の長さを ID から計算し直す処理を足すと、読み込み直したあとに呼び名が別の記録を指す。呼び名を扱う処理は、エピソードが持つ `handle` を使う。エピソードを足すときは、その Being がもう使っている呼び名を `Episode.write(taken_handles=...)` に渡す。渡し忘れると `add` が `EpisodeConflictException` で止める

**関連**: Issue #1623 / #1621、design_decisions 3 / 27、design_decisions D1520 (知り合いの記録)。

## D1626. エピソードは短期記憶を畳むときと環境を離れるときに、要約とは別の呼び出しで本人が書き起こす

**何を**:

- 書き起こしの部品は `being/application/episode_writing.py` の `EpisodeWriter`。本人の名前・人物像・範囲の出来事 (【直近の出来事】と同じ書き方で古い順に並べた文) を受け取り、要約とは別の LLM の呼び出しで 0〜3 件のエピソードを作って `EpisodeRepository` に足す。ゲームのパッケージを import しないので、出来事は描いたあとの文で受け取る。環境の名前は保存にだけ使い、LLM には渡さない。直前の要約も渡さない (要約の誤りを持ち込まないため)。thinking は使わない (`complete_episode_writing_json` は要約と同じく熟考を止めて送る。design_decisions 87)
- 呼ぶ側は 2 か所だけ。`SummarizingShortTermMemory` が古いターンを畳むとき (`on_compacted` に畳んだ範囲を渡す) と、run の終わり (`WorldRuntime.write_episodes_on_leaving`。まだ畳まれていない分を渡す)。区切り方を差し替える仕組みは作らない。Jev などで区切るときは呼ぶ側を足す
- run の終わりの呼び出しは `scripts/run_scenario_experiment.py` の 1 か所だけにある。ほかの入口 (観戦用のサーバなど) で有効にしても、離れるときの書き起こしは走らない。そこで使うときは、その入口の終わりに足す
- LLM が使えずに終わった run (`LLM_FAILURE` / `LLM_ABORTED`) では、離れるときに書かず、`skip_reason: llm_unusable` をプレイヤーごとに残す。呼んでも同じ障害で失敗が並ぶだけで、終わるのが遅れる。Ctrl+C で止めた run (`INTERRUPTED`) では書く。snapshot も保存して続きに使うので、最後の場面を残す
- `application/being/player_episode_writing.py` の `PlayerEpisodeWriting` が、プレイヤーから Being・記憶のターン数・環境の名前 (`EnvironmentEntry.environment_name`)・人物像を引いて部品を呼び、`episode_writing` の trace を 1 回に 1 件残す
- profile の `BEING_EPISODE_WRITING_ENABLED` (既定 off) で有効にする。古いエピソード (`LLM_EPISODIC_ENABLED` / `LLM_EPISODIC_SUBJECTIVE_ENABLED`) とは別のスイッチ。呼ぶ口が `rolling_summary` にしか無いので、ほかの短期記憶と組み合わせたら起動前に止める (design_decisions 10)。`LLM_CLIENT=stub` の run では、範囲の最初の出来事を本文にしたスタブが書くので、配線と trace を実 LLM なしで確かめられる

**応答が崩れていたら 1 件も作らない理由**: 項目のどれかに目次や本文が欠けていたら、正しい項目があっても全部を捨てて失敗として残す。全項目を確かめてから保存に入るので、応答の崩れで一部だけ残ることはない (保存そのものが途中で失敗したときは、それまでの分が残る)。形を守れなかった応答は、残りの項目の中身も当てにならない。生の記録を詰めて代わりにすることもしない (中身の薄い記憶を混ぜないため。Issue #1626)。呼び出しの失敗、応答の崩れ、Being を引く処理の例外のどれでも、run は止めず、`outcome: failed` と例外の型を trace に残す

**上限を超えたもの**: 文は上限 (目次 40 字、本文 400 字) まで切り詰めて保存し、項目ごとに切り詰める前の長さを trace の `truncated` に残す。ドメイン層は上限超えを受け付けないので (design_decisions D1623)、切り詰めはこの部品の仕事。4 件目より後の項目は捨て、捨てた件数を `dropped_count` に残す。捨てた項目の形は確かめない

**畳むときは要約の scheduler に乗せず、その場で呼ぶ理由**: 要約は thread pool で動くことがあるが、書き起こしを同じ worker に載せると、run の終わりの書き起こしと同じ Being の記録を別々の thread が触り、呼び名の重なりの確かめ (`taken_handles`) が競合する。畳むのは 1 人あたり run ごとに 2 回前後なので、その場で待っても tick の遅れは小さい。聞き手が例外を投げても要約は止めない。逆に要約の送信が例外を投げても、聞き手には渡す。畳んだ範囲はもう短期記憶から消えていて、離れるときにも拾えないため

**どうしないと壊れるか**: 離れるときの書き起こしを snapshot の保存より後ろに置くと、最後の場面のエピソードが次の回へ持ち越されない。`scripts/run_scenario_experiment.py` で保存の手前に置いてあり、スタブの run の試験が、書いた件数と snapshot に入った件数が一致することを見ている

**まだ扱っていないこと**: `snapshot_load_mode` が replay でない再開 (同じ世界の続き) では、1 回目の終わりに書いた範囲が短期記憶に残ったまま戻るので、2 回目に畳むとき同じ出来事からもう一度書く。いまの計画 (Issue #1621) は replay で回すので、続きの再開で使うときに、書いた範囲を覚えるかを決める

**関連**: Issue #1626 / #1621 / #1623、design_decisions 10 / 54 / 55 / 87 / D1623。

**その後**: `BEING_EPISODE_WRITING_ENABLED` は Issue #1631 で消し、書き起こしは常に入る形にした。短期記憶の既定を `rolling_summary` にし、`sliding_window` は起動時に拒む (design_decisions D1631)。

---

## D1623-2. エピソードの目次は空でも【思い出せる出来事】として毎ターン出し、呼び名で本文を呼び出す

**何を**:

- profile の `BEING_EPISODE_INDEX_ORDER` で並べ方を選ぶ。`recalled_rises_to_top` (`RecalledRisesToTop`) か `newest_first` (`NewestFirst`)。既定の `off` では欄もツールも出さず、既存の profile のプロンプトとツール定義は変わらない。載せる件数 N は `BEING_EPISODE_INDEX_LIMIT` (既定 10)、1 回に呼び出せる件数 M は `BEING_EPISODE_RECALL_MAX_HANDLES` (既定 3)
- 欄は `being/application/episode_index_text.py` が 1 件 1 行で書く (`[ep_3f2a7b] 金庫の番号を探した — 思い出すとき: 金庫や鍵の話が出たとき (呼び出し 2 回)`)。前にいた環境で書いたものは、メモ (design_decisions D1628) と同じく環境ごとの見出しでまとめる
- 呼び出しは `episode_recall` (`BeingEpisodeRecallToolExecutor`)。呼び名の配列を受け取り、`recall_episodes` で呼び名ごとに本文を返す。知らない呼び名は「そのような記憶は思い出せない。」で、ほかは通常どおり返す。本文の前には、その記憶の「どんな記憶か」を添える。呼び出した本文と目次がずれているかを本人が比べられるようにするため
- 目次を出したことは `episode_index_shown` (並べ方・N・記録の件数・出した呼び名)、呼び出しは `episode_recall` (渡した呼び名・呼び名ごとの見つかったか・回数、断った理由、失敗した例外の型) として trace に残す。目次はプロンプトを組むたびに 1 件残す。呼び出しを選んだ手番が、どの呼び名を見ていたかを後から引けるようにするため
- システムプロンプトの【文脈と履歴の限界】に、【思い出せる出来事】は目次で、本文は `episode_recall` で読むことを 1 行足す。ツールの名前は実際に出すツールの一覧から決める (design_decisions D1616 と同じ)。純スポットグラフの経路で記憶のツールが隠れたときは、欄の説明だけになる

**空の目次も出す理由**: 書き起こしは短期記憶を畳むときに走るので、run の最初の 20 ターンほどは目次が空になる。そのあいだも呼び出しのツールは出ている。欄を消すと、システムプロンプトが指す欄が無く、ツールだけがある状態になり、呼び名を作って呼ばせることになる。「(まだ無い)」と出せば、まだ思い出せる出来事が無いことが本人に分かる。メモ帳が空の分類の見出しも出すのと同じ考え方

**欄の置き場所**: 【直近の出来事】の後ろ、【関連する記憶】と【進行中のメモ】の間に置く。目次は書き起こしと呼び出しのときだけ変わり、毎ターン変わる欄よりは長く同じ文が続く。それでも直近の出来事の前に置くと、目次が変わるたびに直近の出来事の先頭からキャッシュが外れる (design_decisions 1)

**上限 M をツールで確かめる理由**: スキーマの `maxItems` にも M を書くが、provider は配列の長さを守らせない。M を超えた呼び出しは、どれも呼び出さずに上限を添えて失敗を返す。一部だけ呼び出すと、どれを落としたかを本人が知らないまま手番が終わる。同じ呼び名を重ねて渡したときは 1 件と数える (`recall_episodes` が 1 度しか数えないのと揃える)

**書き起こしが無い組み合わせを止める理由**: `BEING_EPISODE_WRITING_ENABLED` が無いと、目次はいつまでも空のまま、ツールだけが出続ける。起動前に `ValueError` で止める (design_decisions 10)。前の回の snapshot から読み込んだエピソードだけで回す実験が要るようになったら、この検査を外す

**呼び出しの文字列に配列以外を受け付けない理由**: 呼び名を 1 つの文字列で渡されても配列として読み替えず、書き方を添えて断る。読み替えは静かにうまくいくので、スキーマとずれた呼び方が trace から見えなくなる。断った回数は `episode_recall` の `reject_reason: malformed` で数えられる

**目次を直すツールとメモとのつながり**: design_decisions D1623-3 に分けて書いた

**どうしないと壊れるか**: 記憶の欄やツールを足したら、`tests/demos/test_disabled_memory_parts_vanish_from_the_prompt.py` の `_ALL_NAMES` と `_DISABLED_PARTS` に足す (design_decisions D1616)。この PR で【思い出せる出来事】と `episode_recall` を足した。呼び出しの結果は環境で起きたことではないので、観測への変換では Being 自身の記録として拒む。拒む道具は `memo_` / `memory_` の頭で見分けていて、`episode_recall` はその頭を持たないため、`observation_translation.py` の `_AGENT_SIDE_TOOLS` に名前を足した。頭を持たない記憶のツールを足すときは、ここにも足す。`tests/application/observation/being_contract/test_observation_translation.py` がカタログの全道具を見張るが、関数で作る定義は手で足す必要がある。名前は `memory_recall_episodes` の部分文字列にならない形にした。部分文字列だと、片方を止めても他方の名前で緑になる

**関連**: Issue #1623 / #1621 / #1626、design_decisions 1 / 10 / D1616 / D1623 / D1626 / D1628。

**その後**: `BEING_EPISODE_INDEX_ORDER` は Issue #1631 で消し、目次は常に出す。並べ方は `RecalledRisesToTop` に固定した。並べ方を差し替える作り (`EpisodeIndexSelection` と `NewestFirst`) はドメイン層に残し、profile で選ぶことだけをやめた。trace の `episode_index_shown.order` は過去の run と並べて読めるよう `recalled_rises_to_top` のまま残す。 記憶のツールを隠す純スポットグラフ (#1762 で設定を消し、いまは `include_todo_tools=False`。`LLM_TOOL_MODE=pure_spot_graph`) では、呼び出せない目次を出さない。

---

## D1623-3. 目次は本人が専用のツールで直し、目次を出す設定ではメモの出どころにエピソードを選ばせる

**何を**:

- `episode_revise_index` (`BeingEpisodeIndexRevisionToolExecutor`) は、呼び名と新しい `about` (どんな記憶か)・`recall_when` (どんな時に思い出すか) を受け取り、`Episode.revise_index` で目次を替える (D1621 で、値を返す形から集約の操作に作り直した)。前の目次は、直したターンと一緒に `index_history` に残る。本文は変えない
- 40 字を超えた文は、書き起こし (design_decisions D1626) と同じくアプリケーション層で 40 字に切り詰めて保存し、切り詰める前の長さを trace の `truncated` に残す。ドメインは上限を超えた文を受け付けない (design_decisions D1623)
- 知らない呼び名、空や文字列でない引数では、何も変えずに失敗を返す
- 目次の直しは `episode_index_revision` として trace に残す (前と後の目次、ターン数、切り詰め、断った理由)
- ツールは目次を出す設定 (`BEING_EPISODE_INDEX_ORDER` が off 以外) で、呼び出しのツールと一緒に出す。別のスイッチは置かない。目次を見られるのに直せない、という組み合わせを実験で使う予定が無いため
- `WorldRuntime.memo_episode_source_offered` は目次の有無を返す。目次を出す設定では、引数 `memo` の出どころの選択肢に `episode` が入り、`from` に呼び名を書ける

**専用のツールにした理由**: Issue #1623 で決めた。呼び出しのツールに直す引数を添える案は、本文を読む前に呼ぶツールなので、読んだあとに直す流れに合わない。メモの共通の引数で直す案は、メモとは別の操作で、引数がさらに難しくなる。欠点は、直すのに手番を 1 回使うこと。最初は本人が自由に直し、仕組みからは知らせない

**メモの出どころに受け付ける呼び名**: その Being のエピソードの全件にした。目次に載っていない (沈んだ) エピソードの呼び名も通る。本人がその呼び名を知るのは、前に目次で見たか、呼び出したときなので、いまの目次に無くても本人が知っていた呼び名である。いまの目次に載っている分だけに絞ると、少し前に呼び出して書き留めようとした記憶が、並びが変わっただけで外される

**どうしないと壊れるか**: 目次を直すツールの結果も、呼び出しと同じく `_AGENT_SIDE_TOOLS` に名前を足して、観測に写さない (design_decisions D1623-2)。目次を直すツールを止める設定を足すときは、`tests/demos/test_disabled_memory_parts_vanish_from_the_prompt.py` に行を足す。メモの出どころの「エピソードから」は、メモ帳と目次の両方を出すときだけ出る。総当たりの試験は、メモ帳に置き換えた正の対照でこの説明が出ることと、目次を止めると消えることを見ている

**関連**: Issue #1623 / #1628 / #1621、design_decisions D1616 / D1623 / D1623-2 / D1626 / D1628 / D1628-2。

**その後**: 目次は Issue #1631 で常に出す形になったので、メモ帳を出す設定では、出どころにエピソードを常に選べる。

---

## D1628. メモは Being ごとのメモ帳を集約の根にし、分類ごとの件数の上限をメモ帳が守る

**何を**:

- `being/domain/memo_book.py` に `MemoBook` (集約の根) と `Memo` (その中のエンティティ)、`MemoProvenance` (出どころと確かさの値)、`MemoKind` / `MemoSource` / `MemoCertainty` の Enum を置く。今の `MemoEntry` とは別の型で、ゲームの番号も持ち主の `BeingId` も持たない
- 分類は「やること」「分かったこと」「人について」。件数の上限はそれぞれ 5 件・10 件・5 件 (`KIND_LIMITS`)。上限を超えて足そうとすると `MemoLimitReachedException`。上限は複数のメモにまたがる決まりなので、メモ帳が自分で守る。並べたメモ帳を直接作る経路 (snapshot から戻すとき) でも、`MemoBook.__post_init__` が上限・ID と呼び名の重なりを確かめる
- 出どころと確かさは「分かったこと」にだけ持たせ、ほかの分類で持たせると `MemoValidationException`。人から聞いたなら誰から、エピソードからなら `ep_` で始まる呼び名が要る。エピソードの呼び名は、`add` / `edit` に渡した `known_episode_handles` の中にあるものに限る。エピソードは別の集約なので、メモ帳は保存を引かず、呼ぶ側が知っている呼び名を渡す (`Episode.write` の `taken_handles` と同じ形)
- 文は空不可、60 字まで。超えた文はドメイン層が受け付けない
- 書き換えは文と、分かったことなら出どころを置き換える。出どころを渡さなければ前のまま。書き換えた時を記録し、書いた時と前に書き換えた時より前には戻せない。消すと記録からも消え、消したメモを返す (trace に何を消したかを残すため)
- 呼び名は `m_` と ID の先頭 6 文字。重なったら後から足した側だけを伸ばす (design_decisions D1623 と同じ理由)
- `InMemoryMemoBookRepository` を足し、`BeingMemorySnapshotService` の `being_memo_book` に配線した (design_decisions 27 の 4 手順)。`WorldRuntime._being_memo_store` が常に持ち、`ExperimentSnapshotSession` では必須の store にした。SQLite は作らない (#1625 で保存の形を決める)

**誰についてかを別の値にしない理由**: 「人について」に相手の名前を別に持たせると、名前を知らない相手 (見た目で呼ぶ相手、design_decisions D1581) や複数人についてのメモが書けなくなる。文の中に書かせる

**出どころと確かさを分ける理由**: 「人から聞いた推測」と「自分の推測」を区別するため

**この PR より前の snapshot は読めない**: `being_memo_book` の欄が無い payload は形式エラーで拒む (design_decisions D1623 と同じ。design_decisions 6)

**どうしないと壊れるか**: メモを足す処理で、件数の上限を呼ぶ側で数え直さない。数え直すと、メモ帳を経由しない書き方 (snapshot から戻す、試験で並べる) で上限が守られなくなる。エピソードの呼び名を出どころに書かせるときは、本人が目次で見られる呼び名を `known_episode_handles` に渡す

**関連**: Issue #1628 / #1621 / #1625、design_decisions 6 / 27 / D1623。

## D1628-2. メモは環境の tool の省略できる引数 `memo` で書き、崩れた操作だけを外して本人に理由を返す

**何を**:

- profile の `BEING_MEMO_ENABLED` で有効にする。既定は off で、既存の profile の tool 定義とプロンプトはバイト単位で変わらない
- 有効にすると、環境の tool すべてに省略できる引数 `memo` を付ける (`tool_catalog/memo_argument.py`)。付ける範囲は予期の引数 (design_decisions D1441) と同じで、記憶の tool と `assess_situation` には付けない。書いても手番を使わない
- 受け取った側で操作ごとに形を確かめる (`memo_arguments.py`)。崩れた操作 (分かったことに出どころが無い、61 字以上、知らない `do` など) と、メモ帳が受け付けなかった操作 (上限、無い呼び名) だけを外し、ほかの操作と行動そのものは通す。1 回の行動の操作は書いた順にメモ帳へ当て、保存は 1 回にする (`being/application/memo_writing.py`)
- 外した操作は、何件目か・直し方の分かる理由の文 (「やることが上限 (5 件) です。消すか書き換えてください。」など) を結果の文の末尾に添えて本人に返す。trace の `being_memo` に、当てた操作 (消した操作は消したメモ)・外した操作の理由と元の値を残す。引数を書かなかった呼び出しでは出さない
- 【メモ】は【進行中のメモ】と同じ位置に、毎ターン、分類ごとに全部出す。空の分類も見出しを出す。今と違う環境で書いたメモは、分類の中で環境ごとの見出しでまとめる。システムプロンプトには【メモの書き方】で、分類の意味と書き方だけを書く。件数の上限と引数の形は tool の説明に書く
- 済んだかの知らせ (#1322、`MemoCompletionHintService`) を、メモ帳のやることにも使う。消し方は `memo` の remove と案内する。自動では消さない。食い違いの知らせは作っていない (#1628 の「最初の run では入れない」)
- 読み取りやメモ帳への書き込みが途中で失敗しても、行動は止めない。本人には「メモ帳に書けませんでした」と結果の文で返し、trace の `skipped_reason` と `error` に理由を残す。返さないと、本人は書けたと思い込んだまま進む
- 同じ行動に添えて足したやることは、その行動で済んだのではと問わない。足した行動の文と重なるのは当然で、済んだ印ではない

**今のメモの道具と並べない理由と、止め方**: 両方を出すと、メモを書く口と欄が 2 つずつ並ぶ。`BEING_MEMO_ENABLED=1` で `MEMO_TOOLS_ENABLED` が true のままなら、起動前に `ValueError` で止める。メモ帳の側で今の道具を自動で隠さないのは、露出の判断を今の `memo_tools_enabled` の 1 か所に残すため。2 か所で決めると、profile を読んでも何が出ているかが分からなくなる (CLAUDE.md の「露出の判断は 1 か所」)

**長すぎる文を切り詰めない理由**: エピソードの書き起こし (design_decisions D1623) と違い、メモは本人がその手で書いた短い文で、外したことを次の手で本人に返せる。切り詰めると意味が変わったまま残り、本人は気づけない

**出どころにエピソードを目次を出す設定でだけ選ばせる理由**: ドメインは「エピソードから」を持てるが、本人がエピソードの呼び名を知るのは、目次か呼び出しの結果から。どちらも目次を出す設定でだけ出るので、目次を出さない設定で選ばせると、知らない呼び名を書いて外されるだけになる。`WorldRuntime.memo_episode_source_offered` が目次の有無を返し、目次が無ければ引数の選択肢と説明から `episode` と `ep_` を消す (design_decisions D1623-3)

**崩れた操作の理由を本人に返す場所**: 結果の文の末尾。済んだかの知らせと目的の判断は、理由を足す前の文で行う。足したあとの文で判断すると、メモの理由の文を行動の結果と取り違える

**プレフィックスキャッシュ**: 引数の定義も【メモの書き方】も、設定だけで決まり run 中は変わらない (design_decisions 1)

**どうしないと壊れるか**: メモの名前・分類・引数をプロンプトの本文や tool の説明に書くときは、メモ帳が有効な設定でだけ書く。`tests/demos/test_disabled_memory_parts_vanish_from_the_prompt.py` が、全部入り (今のメモ) にメモ帳の名前が出ないことと、メモ帳に置き換えたときにメモ帳の名前だけが出て今のメモの名前が消えることを見張る。メモ帳と今のメモは並べられないので、全部入りの 1 つの土台から 1 つずつ止める形 (`_DISABLED_PARTS`) では、メモ帳を止めた場合を空振りせずに書けない。そのため置き換えの正の対照を別の試験にした

**関連**: Issue #1628 / #1621 / #1322 / #1616、design_decisions 1 / D1441 / D1616 / D1623 / D1628。

**その後**: 古いメモの道具と【進行中のメモ】は #1631 の段 11-2a で消した (design_decisions D1631-4)。`MEMO_TOOLS_ENABLED` と、メモ帳と並べたときに止める検査も一緒に消えた。メモ帳はほかのメモと並ばないので、`tests/demos/test_disabled_memory_parts_vanish_from_the_prompt.py` はメモ帳を全部入りに入れ、`_DISABLED_PARTS` で止める形に戻した。

**その後 (2)**: #1631 の段 11-3 (#1806) で `BEING_MEMO_ENABLED` を消し、メモ帳を `create_world_runtime` で組んだ runtime にいつも入れる形にした。上の「既定は off で、既存の profile の tool 定義とプロンプトはバイト単位で変わらない」はもう成り立たない。それまで off だった profile では、環境の tool の 1 つ 1 つに引数 `memo` の定義が付き、システムプロンプトに【メモの書き方】が足され、tool 定義とプロンプトが大きく増える (smoke_stub の 1 ターン目で 16,837 → 34,288 バイト)。済んだかの知らせのサービスも、いつも組む。そのため、型付き判断の port がある profile では、残りのやることが 1 件以上あると、行動の結果を返すたびに型付き判断を 1 回呼ぶ。純スポットグラフ (`include_todo_tools=False`) でもメモ帳は出る。目次は止めているので扱いが食い違うが、どちらに寄せるかは `include_todo_tools` を整理するときに決める。その後、#1807 で `include_todo_tools` と純スポットグラフのモードごと消したので、この食い違いは無くなった (呼ぶ経路は #1762 で `LLM_TOOL_MODE` を消したときから無かった)。

---

## D1597. 成功した自分の行動のあとは次の tick に手番を回す。休むのは wait を選んだときと移動中だけ

**何を**:

- 自分の行動の結果も、本人への観測として扱う。成功した手番のあと、`WorldLlmTurnTrigger` はその人を次の tick の pending に戻す。記憶の呼び出し (`episode_recall` など world_action 以外のツール)、何も見つからなかった探索、物を読むだけの interact、発言も含む
- 回さないのは 2 つだけ。`wait` を選んだときは、結果 DTO の `rests_until_woken=True` を見て、起こされるまで休む。時間のかかる移動の途中は、着いたときの知らせで起きる (#404)
- 成功した手番ごとに trace の `own_action_follow_up` を 1 件残す。payload は `rescheduled` と `reason` (`succeeded` / `rest_chosen` / `traveling` / `cannot_act`)。`cannot_act` は、行動の結果で倒れた・去った人。回しても手番の入口で落ちるので、回したと残さない。失敗と「迷い」の手番には残さない。失敗は `llm_failure_retry` と失敗の観測が受け持つ
- 起動判定 (design_decisions 220 / 222) を入れた run でも、自分の行動のあとに回した人は判定にかけない。判定を入れた run では、回した人が同じ tick の実行順の先頭に並ぶ
- 失敗の扱いは変えない。`_RESCHEDULE_ERROR_CODES` による回し直しと、呼び出しの失敗の回し直し (design_decisions D1595) がそのまま受け持つ

**なぜ**:

- `var/runs/mine_v1_005` で、記憶の呼び出し、結果の出ない探索、紙切れを読むだけの interact が成功したあと、本人を起こす観測が出ず、待ち時間のタイマーが切れるまでちょうど 6 tick 手番が回らなかった。記憶を思い出すツールは、思い出した内容で次の手を決めるためにある。そのあと 6 tick 動けないと、使う意味が薄れる
- ツールごとに起こすかを決める案は採らなかった。ツールを足すたびに決め直すことになり、決め忘れたツールでまた静かに止まる。既定を「回す」にして、休む側の `wait` だけが印を立てる形にすると、印を立て忘れたツールは回る側に倒れる
- 自己 reschedule の連続上限 (`max_self_reschedule_streak`) には載せない。上限で止めると、一人で動き続ける人が 5 手ごとに 6 tick 眠る。同じ行動の繰り返しは、今ある繰り返しの警告 (`tool_call_loop_guard`) が受け持つ
- 起動判定は「未読の観測で、いま動く必要があるか」を問う。自分の行動の結果は判定の材料に入っていないので、判定にかけると、手を決めた直後の人を材料なしで眠らせることになる

**design_decisions 7 (待ち時間のタイマー) との関係**: タイマーは「N tick 何も起きなかったら 1 回だけ起こす」最大沈黙時間の上限で、手番が走るたびに数え直す。この判断で手番が増えても、タイマーの意味は変わらない。`wait` を選んだ人には、今までどおりタイマーか起こす観測で手番が来る。

**agent_design_principles 2 (観測が来ないあいだは休眠する) との関係**: 休眠は、何も起きていないのに LLM を呼ぶ無駄を避けるためにある。自分が行動した直後は、何も起きていない状態ではない。自分の行動の結果は、本人に届いた観測として扱う。休むかどうかは本人が `wait` で選ぶ。

**費用**: 一人の場面では手番が増えるぶん呼び出しが増える。互いの発言で毎 tick 起こし合う run (mine_v1_004 など) では、もともと毎 tick 回っていたので増えない。でたらめに行動するスタブ (`make fuzz-scenario`) の廃坑の山村 10 シード × 40 tick では、行動の数は直す前と同じだった。スタブ同士が毎 tick 起こし合うため。

**どうしないと壊れるか**:

- `wait` の結果を作り直す経路が `rests_until_woken` を落とすと、`wait` を選んでも毎 tick 起こされる。`with_inner_thought_empty_warning` は DTO を項目を並べて作り直していて、心の声が空の `wait` でこの印を落としていた。`dataclasses.replace` で作り直す
- `tests/application/llm/services/world_llm_turn/test_own_action_result_gets_the_next_tick.py` が、本番と同じ組み立ての世界で world tick を進め、mine_v1_005 の形 (結果の出ない探索・紙切れの interact・メモのツール・`episode_recall`) のあと次の手番が 1 tick 後に来ること、`wait` のあとはタイマーまで来ないこと、2 tick の移動では着いた tick に来ること、探索を 5 回続けるとループ警告が出ること、起動判定にかけないことを見張る
- 移動中に手番を回さない守りは、手番の入口 (`_can_player_act`) と、この判断の `traveling` の 2 か所にある。入口だけでも行動は止まるので、`traveling` を外したときに落ちるのは trace の試験だけになる

**関連**: Issue #1597 / #1595 / #1508、design_decisions 7 / 222 / D1595、agent_design_principles 2。

自分の行動のあとに回した人を起動判定にかけない扱いは、起動判定と一緒に #1692 で消した (#1631)。手番を次の tick に回す決まりはそのまま残る。

---

## D1617. 記憶の部品と Jev の LLM 呼び出しは、行動の `llm_call` と分けて `aux_llm_call` に部品名つきで残す

**何を**:

- 記憶の部品の LLM 呼び出しは、すべて `LiteLLMClient` の JSON 補完 (`_complete_aux_json`) を通る。入口の 7 つのメソッドが部品名 (`AuxLlmComponent`) を付け、1 回ごとに部品名・モデル・トークン・費用・待ち時間・成否を `AuxLlmCallSink` へ渡す。失敗した呼び出し (API の例外、JSON でない応答) も残す
- Jev (`JevTypedJudgmentAdapter`) は Decisions endpoint への 1 回ごとに、部品名 `typed_judgment`・待ち時間・成否・問いの名前を残す。429 の再試行は 1 回に数える
- `AuxLlmCallTraceSink` が trace の `aux_llm_call` に書く。recorder と tick は呼ばれた時点で引く。記憶の部品は runtime より先に組まれ、主観の書き込みは別スレッドで tick を跨いで終わるため
- `create_world_runtime` が sink を 1 つ作り、`WorldRuntime._aux_llm_call_sink` に持たせる。記憶の部品を組む箇所と、runtime_manager が組む Jev は、すべてこの sink を `create_llm_client_from_config` / `create_typed_judgment_port_from_config` の `aux_call_sink` に渡す
- report.md の冒頭に費用の合計と内訳を 1 行で出し、「LLM 呼び出しの回数と費用」の表で行動と部品ごとの行を分ける

**`llm_call` に混ぜない理由**: 混ぜると、行動の費用と記憶の費用が分けられない。さらに `llm_call` は連続失敗で run を止める監視 (`LlmMetricsTraceSink._notify_failure_monitor`) と progress の呼び出し数に数えられている。記憶の部品の失敗で run が止まるのは、この Issue の「記録の失敗で run を止めない」に反する

**応答に無い値を None にする理由**: Jev の Decisions endpoint は課金額もトークン数も返さない (`docs/experiments/issue_1429_candidate_table_comparison.md`)。0 で埋めると、report で「無料だった」と読める。LiteLLM の記憶の部品も、`usage.cost` が無ければ費用を None に、`usage` そのものが無ければトークン数も None にする (OpenAI 直結や vLLM)。report は取れた分だけを足し、取れなかった回数を添える。ただし応答が届かず失敗した回は、値が無くて当然なので「取れない」に数えない。課金されていない回と、課金額が分からない回を混ぜないため。行動の `llm_call` は今の決まりのまま 0.0 で残すので、表の説明文にそう書いた

**記録の失敗**: sink の例外は呼び出し側 (`LiteLLMClient` / Jev アダプタ) が握り、記憶の部品の結果は変えない。trace への書き込みが失敗したら、部品名と例外の型だけの `aux_llm_call_record_failed` を書く。report はその回数を「記録できなかった呼び出し」として表の外に出す。recorder が差し込まれる前の呼び出しは、どちらも残らない。今は run の開始前に記憶の部品を呼ぶ経路は無い

**trace viewer**: `aux_llm_call` は `llm_call` と同じく性能計測なので、イベントログからは隠す。`aux_llm_call_record_failed` は隠さない

**player_id を残さない理由**: 記憶の部品の入口 (completion port) は誰のための呼び出しかを受け取らない。部品ごとの費用を比べる目的には部品名で足りる。誰の呼び出しかが要るときは、同じ tick の `short_term_summary_generated` や `episode_writing` などの部品側の trace と突き合わせる

**prompt dataset に残さない理由**: `prompt_dataset/calls.jsonl` は行動の呼び出しの入力と出力を残すもので、費用の集計の一次情報は trace にした。記憶の部品の入力を残す必要が出たら別に足す

**どうしないと壊れるか**: 記憶の部品のために LLM クライアントや Jev を組むときは、`aux_call_sink` を必ず渡す。`tests/application/world_runtime/test_memory_llm_calls_reach_the_trace.py` が、src の中の全呼び出しが `aux_call_sink=` を渡しているかを ast で見張る。新しい部品を足すときは `AuxLlmComponent` に値を足し、report の `_AUX_COMPONENT_LABELS` に日本語の名前を足す (足さなければ部品名がそのまま出る)

**関連**: Issue #1617 / #1587 / #1627 / #1429 / #1631、design_decisions 5 / D1626。

**その後**: 主観補完 (`episode_subjective`) の呼び出しは記憶の部品の撤去 (#1631) の #1801 で消し、`AuxLlmComponent.EPISODE_SUBJECTIVE` も外した。消す前の run の report を読めるよう、表記の対応 (`主観の書き込み`) は文字列のまま残す。

---

## D1612. 行動に添える一言には、結果ではなくこれから何をするかを書くよう、書き方の案内で頼む

**何を**: システムプロンプトの【独白と一言の書き方】の `say_inline` の項に、「一言には、行動の結果ではなく、これから何をするかを言う。行動は断られることがあり、結果は次の観測で分かる。」と書く。

**なぜ**: 一言は行動を選ぶのと同じ呼び出しで書かれ、その時点で結果はまだ出ていない。`mine_v1_005` T35 で、断られた取得に「燃料の缶、見つけました」と添えた。#1601 以降は断られた行動の一言も聞き手に届くので、聞いた人は起きていないことを起きたこととして受け取る。理由を添えるのは、禁止だけを書くと何を書けばよいかが分からないため。

**世界の側で直す案をとらない理由**: 発言のあとに行動が断られたことを聞き手に見せる案もある。ただ、先取りは `mine_v1_003`〜`006` で 1 件だけで、先に文で頼んで効くかを見る。文では完全には防げないので、次の run で残るならこの案を考える。

**プレフィックスキャッシュ**: 足した文は定数で、システムプロンプトは runtime を作るときに 1 回組み立てる。run 中は変わらない (design_decisions 1)

**どうしないと壊れるか**: この文を消すと、先取りの一言がまた聞き手の観測と記憶に入る。`tests/application/llm/services/test_world_system_prompt_say_inline_intent.py` が、`say_inline` の項にこの文と理由があることを見張る。

**関連**: Issue #1612 / #1601 / #1508、design_decisions 1。

---

## D1641. 人を対象にした操作の品名は、完全一致・部分一致・意味の判断の順で相手の持ち物に当て、当てられないときは「持っていない」と言い切らない

**何を**:

- 懐を探る操作などの引数 `item` を、相手の所持品の正式な名前へ当てる。手順は `application/world_graph/target_item_name_resolution.py` にあり、次の順に試す
  1. 完全一致 (全角・半角と空白の違いは無視する)
  2. 書かれた名前が、相手の持たない別の品の正式な名前なら、そこで「持っていない」とする。「カンテラ」と書いて「カンテラの油」だけを持つ相手から油を奪わない
  3. 部分一致 (書かれた名前が正式な名前に含まれるか、その逆)。「起動鍵」は「昇降機の起動鍵」に当たる
  4. 意味の判断 (`application/llm/services/_argument_resolvers/target_item_name_rescue.py` の `TargetItemNameRescue`)。名前の重なりが無い「鉄の鍵」のような書き方だけを問う。候補は相手の所持品の名前と説明で、「該当なし」を必ず入れる
- 当てはまりそうな物が 2 つ以上あるときは選ばない。完全一致・部分一致・判断のどれで複数になっても同じ
- 結果は 4 つ。当たった (`resolved`) / 曖昧 (`ambiguous`) / 持っていない (`absent`) / 見分けられない (`unrecognized`)
- 「持っていない」と言うのは、相手が何も持っていない、名前の重なりが無く判断が配線されていない、判断が確率と確信の両方で下限を超えて「該当なし」と答えた、のどれかのときだけ。判断が確信を持てなかった、判断器に届かなかったときは「見分けられなかった。持っていないとは限らない。品の名前が違うのかもしれない」と返す
- 読み替えて奪えたときは、結果文の先頭に「「起動鍵」は「昇降機の起動鍵」と解釈した。」と足す
- 正式な名前どおりでなかった試みは、結果によらず trace の `item_name_resolution` に 1 件残す。判断を問うたときは、採らなかった判断もその中に入れる。「持っていない」と言い切ったときは、その理由を `method` に入れる (`official_name_of_other_item` / `nothing_held` / `no_judge` / `judgment`)
- 名前を当てるのは再使用間隔を確かめた後にする。間を置く必要がある試行のたびに判断を問わないため。ほかの前提条件 (籠の中の相手など) は当てた品を使って評価するので、その前に当てる。断られる行動でも判断を 1 回問うことがあり、その費用は許容する
- 1 文字の書き方 (「鍵」「油」) も、持ち物の 1 つにだけ含まれていれば部分一致で当てる。短いだけで断ると「鍵を奪う」が通らない。誤って当てた品は結果文の注記で本人に分かる
- 閾値は対象名の救済と同じ `typed_judgment_target_label_min_confidence` (既定 0.85) を使う。判断が配線されるのは、対象名の救済が配線されるとき (`typed_judgment_provider` が `off` 以外) と同じ

**なぜ**: `mine_v1_008_r2` で、鍵の正式な名前「昇降機の起動鍵」に対し「起動鍵」と書いた懐探りが 4 人で 14 回「相手はそれを持っていない」と断られた。聞いた側は持ち主が嘘をついていると受け取り、疑いが広がった。世界が誤った手がかりを返していたので、繰り返しの警告も行動前の状況評価も止められなかった。記憶を持ち越すと「ミオは鍵を持っていない」という誤りが次の回にも残る。

**断りを前提条件の番に出す理由**: 名前を当てる処理は前提条件の評価より先に走る。そこで断ると、籠の中の相手に「手が届かない」より先に名前の断りが出て、手が届かない相手の持ち物について手がかりを返す。だから当てられなかった理由だけを `interaction_parameters` の `item_name_unresolved` に置き、`TARGET_HAS_ITEM` が自分の番で文を返す (`domain/world_graph/value_object/unresolved_item_name.py`)。この文はシナリオの `failure_message` より優先する。`failure_message` は「持っていない」と言い切る文だからである。以前は同名の別品があるときに前提条件より先に例外で止めていたので、これも同じ経路に移した

**相手の持ち物をどこまで漏らすか**:

- 見分けられなかったときの文に、相手の持ち物の名前は出さない。文は相手が何を持っているかによらず同じである。漏れるのは「相手が何か 1 つは持っている」ことだけで、何も持たない相手には「持っていない」が返る
- 曖昧のときは「当てはまりそうな物が複数ある」と返す。懐を探って手で触れた結果として、似た物が複数あることは伝わってよいと判断した。名前は出さない
- 解釈の注記は奪えたときだけ足す。奪えた時点で品は自分の手にあるので、名前を伝えても漏れない。読み替えた後にほかの理由で断られたときは足さない

**判断が無いとき (`typed_judgment_provider=off`) と stub のとき**: 判断が無ければ名前の重なりだけで当て、重ならなければ今までどおり「持っていない」と返す。「鉄の鍵」→「昇降機の起動鍵」のような読み替えはできない。stub (`DeterministicTypedJudgmentPort`) は選択肢に均等な確率を返すので下限に届かず、名前が重ならない書き方はすべて「見分けられなかった」になる。stub の run は配線と trace を確かめるためのもので、意味のある読み替えを期待しない

**シナリオの文のずれ**: 金庫を開けた文は「中に鉄の鍵が 1 本入っていた」で、鍵の正式な名前を出していなかった。木箱の文は「燃料が少し残った缶」を渡すのに、別の品の名前「燃料の缶」を出していた。どちらも正式な名前を入れる文に直した。全シナリオを見る検査は入れていない。「渡す品の名前が文に無い」は 7 シナリオで 70 件を超え、「冷たい水を汲んだ」(井戸の水) のように正当な書き方が大半を占める。「渡す品と別の品の名前を文が出す」も 15 件ほどで、使った道具 (「骨のナイフで蔓を切った」) や一緒に出た物の言及がほとんどだった。構造で直すなら、品を渡す効果そのものが結果文に正式な名前を添える形になる。全シナリオの文面が変わるので別の Issue で扱う

**どうしないと壊れるか**:

- 部分一致を外すと、`mine_v1_008_r2` の「起動鍵」がまた断られる。`tests/demos/test_items_named_differently_are_still_found.py` が見張る
- 判断が「確信を持てない」ときに「持っていない」を返すと、持っている相手が嘘つきになる。`tests/application/world_graph/test_target_item_name_resolution.py` が見張る
- 断りを前提条件より先に出すと、籠の中の相手の持ち物の手がかりが漏れる。同じ demo の `test_an_earlier_precondition_still_speaks_first` が見張る
- 判断の配線を忘れると、profile が判断を求めても読み替えが効かない。`tests/presentation/spot_graph_game/test_typed_judgment_reaches_the_session.py` が見張る

**関連**: Issue #1641 / #1321。

---

## D1631. 短期記憶の既定は rolling_summary にする

**何を**: `SHORT_TERM_MEMORY_KIND` を書かない設定は `rolling_summary` になる (これまでは `sliding_window`)。stub の 3 profile (`smoke_stub`、`station_drill_stub`、`issue_1429_candidate_capture_smoke`) も `rolling_summary` にした。`sliding_window` は明示すれば選べる。

**なぜ**: 新しい記憶のエピソードの書き起こし (design_decisions D1623、#1626) は、短期記憶が出来事を畳むときと環境を出るときに呼ばれる。`sliding_window` には畳む瞬間が無く、書き起こしを呼べる場所が無い。新しい記憶をスイッチの無い標準にする (Issue #1631) 前に、既定のまま書き起こしまで動く形にしておく。実 LLM を使う profile はすでにすべて `rolling_summary` なので、実験の挙動と費用は変わらない。stub の LLM では要約が LLM を呼ばずにテンプレートで畳まれるので、試験も実 API を呼ばない。

**採らなかった案**:

- 短期記憶の種類で新しい記憶の有無を分ける: 「書き起こしが入るか」が短期記憶の種類に隠れて決まり、`sliding_window` の run では目次が黙って空のまま走る
- `sliding_window` をここで消す: Issue #1631 の段 13 (値を固定する設定) の仕事で、試験とコードの片付けが一度に広がる

**どうしないと壊れるか**: 既定が `sliding_window` のまま新しい記憶を標準にすると、短期記憶の種類を書かない設定 (多くの試験) が、起動時の検査で止まるか、書き起こしの無いまま走る。

**関連**: Issue #1631 / #1626 / #1621、design_decisions D1623。

**その後**: 書き起こしと目次をスイッチの無い標準にしたとき (Issue #1631)、`sliding_window` は設定の検証で拒むようにした。`resolve_short_term_memory_kind` はまだ値として受け付け、`DefaultSlidingWindowMemory` を組む分岐も残る。どちらも設定からは届かず、短期記憶の種類を固定する段 (#1631 の段 13) で消す。キー、解決、`DefaultSlidingWindowMemory` を組む分岐は #1785 で消した。`DefaultSlidingWindowMemory` は試験の代役として残る。#1631 の段 11-4 (#1811) で `DefaultSlidingWindowMemory` を消し、試験の代役は `SummarizingShortTermMemory` (要約の LLM を渡さず、テンプレートで畳む) に付け替えた。snapshot の codec からは、短期記憶が固定容量のときに保存・復元する経路と、要約された snapshot を固定容量の短期記憶へ書き戻す経路を消した。保存は常に `mode: "rolling_summary"` になる。保存形式の subsystem のキー `"sliding_window"` は要約する短期記憶でも使っているので名前を変えず、固定容量の短期記憶で保存した古い snapshot (v1 の mode 無しと v2 の `mode: "sliding_window"`) を要約する短期記憶へ読む経路は残した。これを消すと、過去の snapshot から再開できなくなる。

---

## D1631-2. OpenRouter の provider を固定したら、送る引数をすべて受け付ける provider にだけ送る

**何を**: `OPENROUTER_PROVIDER` か `OPENROUTER_QUANTIZATION` を書いた run は、routing の塊にいつも `require_parameters=true` を入れる。`OPENROUTER_REQUIRE_PARAMS` のキーは #1788 で消した。どちらも書かない呼び出しは、今までどおり routing の塊を作らない。

**なぜ**: このリポジトリでは、行動のターンに `tool_choice="required"` を送るのがほぼ前提になっている (#1053)。`require_parameters` が無いと、OpenRouter はその引数を受け付けない provider にも送ることがあり、引数は無視される。そのため `required` が効かないまま run が進む。true にすると、受け付けない provider には送らず、送る前にエラーで止まる。静かな失敗を、起動直後に見える失敗に変える。

**どうしないと壊れるか**: provider の対応状況は予告なく変わる (`docs/llm_provider_selection.md`)。provider が `required` の対応をやめたとき、false のままだとツールを呼ばない応答が混ざる。それでも run は成功として終わる。 `require_parameters` は `tool_choice` だけでなく、送る引数 (`max_tokens`、`reasoning` など) をすべて見る。どれか 1 つを受け付けない provider に固定した run も、送る前に止まる。

**将来の方針**: `tool_choice="required"` を受け付ける適したモデルが無くなったら、`required` を外す。代わりにプロンプトの末尾に、必ずツールを 1 つ選ぶ指示を足して選ばせる。これは #1053 でやめた形と同じで、その部品 (`force_tool_call_instruction`) は #1677 で消した。戻すときは、#1053 が退けた理由 (行動しない応答を許すこと、比べる run のプロンプトの byte が変わること) を受け入れたうえで判断する。

**関連**: Issue #1631、PR #1053 (熟考の有無にかかわらず `required` を使う)、PR #1677 (末尾の指示の部品を消した)、`docs/llm_provider_selection.md`。

---

## D1631-3. 推論の段階を書かない run は minimal で送る

**何を**: `LLM_REASONING_EFFORT` を書かない設定は `minimal` になる (これまでは `none`)。キーは残し、`none` と書けば熟考なしのまま送る。#1798 で変えた。`LiteLLMClient` を直に組むときの引数の既定 (`none`) は変えていない。プローブ (`scripts/openrouter_ping.py`) と試験が使う。

**なぜ**: 本命の profile をはじめ、実 LLM の run の多くは `minimal` を明示している。`none` で動かす profile も値を明示している。既定の `none` に頼っていたのは、stub の profile と、profile を通らない recall probe だけだった。書き忘れた run だけが熟考なしで走ると、比べたつもりの run と条件がずれる。

**どうしないと壊れるか**: 既定が `none` のままだと、新しい profile で `LLM_REASONING_EFFORT` を書き忘れた run が、本命と違う条件で走る。その違いは、run_start の設定の記録を読まないと気づけない。

**関連**: Issue #1631、design_decisions 87 (補助 JSON 呼び出しは agent turn の値にかかわらず `none`)。

---

## D1631-4. 古いメモのうち LLM から見える部分を消し、保存先と過去の trace を読む側は残す

**何を**: Issue #1631 の段 11-2a。古いメモの道具 (`memo_add` / `memo_list` / `memo_done`)、その実行器、【進行中のメモ】の節、システムプロンプトの案内、設定のキー `MEMO_TOOLS_ENABLED`、古いメモに対する済んだかの知らせの配線を消した。`MEMO_TOOLS_ENABLED` を profile に書くと、未知のキーとして起動前に止まる。済んだかの知らせはメモ帳のやることにだけ出る。

**残したもの**: 保存先 (`_todo_store`、`MemoRepository`)、Being の snapshot の `memo` キー、知らせのサービスにある古いメモの分岐は段 11-2b / 11-3 で扱う。trace の `memo_add` / `memo_done` の種別は、出す側は無いが、viewer と trace 分析が過去の trace を読むので残す。 `memo_id_display.py` の `memo_handle` と `resolve_memo_id_prefix` は、実行器と【進行中のメモ】が消えて使い手が無くなった。知らせのサービスの古いメモの分岐と一緒に、次の段で消す。

**道具の並び**: 常に出す道具の並び (`ALWAYS_PRESENT_TOOL_ORDER`) は `wait`、`speak` だけになった。memo の道具を出していた profile では、後ろの道具が 3 つ前へ詰まる。1 本の run の中では並びが変わらないのでプレフィックスキャッシュ (design_decisions 1) は壊れないが、memo の道具を出していた過去の run とは、プレフィックスを比べられない。

**なぜ一度に消すか**: 道具だけ消して【進行中のメモ】やシステムプロンプトの案内を残すと、エージェントは無い道具を呼ぶ (CLAUDE.md の「プロンプト本文にツール名を書くときは、必ず露出判断を通す」)。設定のキーだけ残すと、有効にしたつもりの run が古いメモなしで走る。

**どうしないと壊れるか**: 保存先に古いメモが残った snapshot を読み込んでも、プロンプトには出ない。`tests/integration/test_world_runtime_current_runtime_contract.py` の `test_old_memo_left_in_the_store_does_not_reach_the_prompt` が見張る。

**関連**: Issue #1631、design_decisions D1628 / D1628-2。

**その後**: 保存先、snapshot の `memo` キー、知らせのサービスの古いメモの分岐、trace の `memo_add` / `memo_done` の種別は、段 11-2b で消した (design_decisions D1631-5)。上の `test_old_memo_left_in_the_store_does_not_reach_the_prompt` は、保存先が無くなったので消した。

## D1631-5. 消した部品の snapshot のキーは、拒まずに捨てて件数を trace に残す

**何を**: Issue #1631 の段 11-2b。古いメモの保存先 (`_todo_store`、`InMemoryMemoStore`、`MemoRepository`、`MemoEntry`、`MemoFulfillmentContext`)、Being の snapshot の `memo` キーと codec、知らせのサービスの古いメモの分岐、`memo_id_display.py`、trace の `memo_add` / `memo_done` の種別と viewer・trace 分析での扱いを消した。済んだかの知らせは、メモ帳のやることだけを見る。

**消したキーの表**: Being の snapshot の memory payload から消したキーは、`src/ai_rpg_world/application/being/removed_memory_payload_keys.py` の `REMOVED_MEMORY_PAYLOAD_KEYS` に 1 か所で並べる。いまは想起の階層と証拠のバッファの 6 キー、`pending_predictions`、`memo`。読み込み (`RestoreBeingSnapshotFromFileUseCase.execute`) は、replay かどうかに関わらず、まず `drop_removed_memory_payload_keys` で表のキーを取り除き、そのあとで replay なら世界の時計を巻き戻す。取り除いたキーごとの件数 (値が list なら要素数) は `snapshot_load` の trace の `removed_memory_keys` に、Being ごとに残る。取り除くキーが無かった Being は載せない。

**なぜ拒まないか**: 消した部品の欄を持つ古い snapshot から、replay も続きからの再開もできるようにするため。黙って捨てると、古い snapshot を読んだことが run の記録から分からなくなるので、件数を残す。それまでは `world_clock_restart.py` が replay のときだけ欄を捨て、続きからの読み込みでは restore が知らないキーを読み飛ばしていた。どちらの読み込みでも同じ表を通す形にそろえた。trace を持たない `BeingPersistenceService.load` も同じ表を通し、件数はログに残す。空の欄は捨てても失うものが無いので、件数に載せない。

**次に消すとき**: 古いエピソードの store を消す段 12 は、`EXPECTED_PAYLOAD_KEYS` から `episodic_episodes` を外し、表に 1 行足す。あわせて、`BeingMemorySnapshotService` の `episodic_episode_store` 引数、`capture` / `restore` の `episodic_episodes` の処理、`ExperimentSnapshotSession` の `_empty_episode_store` を消す。表のキーが `EXPECTED_PAYLOAD_KEYS` に残っていると、表が捨てたあとで restore が欠けとして拒むので、`tests/application/being/test_removed_memory_payload_keys.py` が重なりを見張る。

**trace の欄の変化**: `snapshot_load` の `world_clock_restarts` の要素から `dropped_pending_predictions` が無くなり、`{being_id, reset_tick_fields}` になった。捨てた約束の件数は、新しい欄 `removed_memory_keys` の `counts` に `pending_predictions` として出る。いまの記憶の欄は世界の tick を持たないので、`reset_tick_fields` は 0 になる。

**snapshot session の空の代用**: `ExperimentSnapshotSession` が未配線の store を空で代用してログに残す仕組みは、対象が古いメモの保存先だけだったので一緒に消した。いまの Being の記憶の store は、古いエピソードの store を除き、渡らなければ起動時に止まる。古いエピソードの store は `_empty_episode_store` で空に代用するが、段 12 で store ごと消す。design_decisions 27 の「`fallback_used` ログ対象に新 store の属性名を追加する」は、新しい store を必須の一覧に足すことに読み替える。

**関連**: Issue #1631、design_decisions D1631-4、design_decisions 27。

**その後**: 段 12 で `episodic_episodes` を表に足し、`EXPECTED_PAYLOAD_KEYS` と `BeingMemorySnapshotService` の古いエピソードの処理、`ExperimentSnapshotSession` の空の代用を消した (#1805)。

段 13 で `world_clock_restart.py` を消した (#1810)。読み込みは表のキーを捨てたあと、replay かどうかで分かれない。`snapshot_load` の `world_clock_restarts` 欄も無くなった。

上で「同じ表を通す」と書いた `BeingPersistenceService` は、本番から呼ばれず試験だけが使っていたので、段 13 で消した (#1813)。表を通る読み込みは、`RestoreBeingSnapshotFromFileUseCase` だけになった。

---

## D1824. 短期記憶は要約の要約 (L5) を作らず、3 世代を超えた要約は捨てる

**何を**: 短期記憶の要約 (L4) が 3 世代を超えたとき、あふれた分を L5 にまとめて【自己像と世界観】として出す仕組みを消した (#1828)。3 世代を超えた要約は捨てる。world snapshot の `long_summaries` / `long_gen_indices` は書かなくなり、古い snapshot のこのキーは読み飛ばす (版は据え置き)。

**なぜ**: run 009 で一度も動いていなかった。長い期間の流れは、エピソードの目次 (design_decisions D1623) が受け持つ。部品を減らすと、何が効いたかを run から読み分けやすくなる。

**どうしないと壊れるか**: 長い期間の流れを持たせたくなったら、短期記憶に層を足すのではなく、エピソードの目次の側で考える。要約に層を足すと、エピソードと同じものを 2 か所で持つことになり、食い違ったときにどちらを信じるか決められない。非同期で要約を作る部品 (`ThreadPoolShortTermMemoryScheduler` など) は、#1756 で使うので残した。

**関連**: Issue #1824、design_decisions 124、D1623。

---

## D1824-2. 短期記憶の要約は【ここまでのいきさつ】として流れと気分だけを持ち、言われた予定と実際にしたことを分けて書かせる

**何を**: 短期記憶の要約 (L4) の見出しを【最近の流れ】から【ここまでのいきさつ】に替え、持たせる欄を流れ (`compressed_activity`) と気分 (`emotional_summary`) の 2 つにした (#1829)。片付いていないこと (`unresolved`) は値・指示・プロンプト・trace・world snapshot から外した。要約を作る指示には、「誰が何をすると言ったか」と「誰が何をしたか」を分けて書き、言われただけの予定を決まったことや済んだことに書き換えない、と書いた。一覧にしないのは片付いていないことだけで、言われた約束や予定は「言った」として流れの中に書かせる。

**なぜ**: 出来事そのものはエピソードが、やることはメモ帳が持つ。片付いていないことを要約にも持たせると、メモ帳の「やること」と食い違ったときに、どちらを信じるか決められない。要約は 20 ターンごとにしか作り直されないので、言われた予定を済んだことに書き換えると、その誤りが長く残る (#1584)。

**どうしないと壊れるか**: 要約に項目を足したくなったら、エピソードとメモ帳と重ならないかを先に見る。予定と実際を分ける文を指示から消すと、#1584 の書き換えが戻る。`tests/application/llm/services/test_short_term_memory_backstory.py` が、指示の文と、`unresolved` がプロンプトに出ないことを見張る。値のクラス名 (`L4MidSummary`) と置き場所は変えていない。Being の側へ移す作業 (design_decisions D1824-5 から) で、Being の `Backstory` (`flow` / `mood`) に移る。

**関連**: Issue #1824、#1584、design_decisions D1824、D1628。

---

## D1824-5. 短期記憶の出来事には、それを見る 1 手の番号を付ける

**何を**: Being 側の短期記憶 (`being/domain/short_term_memory.py`) の出来事は、Being の時計 (`MemoryTurnClock`) の番号を持つ。番号は短期記憶の集約 (`ShortTermMemory`) が決める。観測は `perceive`、自分の行動の結果は `receive_result` で受け取る (design_decisions D1824-9)。

| 経路 | 届く時点 | 付ける番号 |
|---|---|---|
| 自分の行動の結果 (`OwnActionResult`) | 時計がその 1 手の番号まで進んだあと (`phase_b.py` の `advance_memory_turn` のあと) | 時計の値のまま |
| 見た・聞いた、言われた・書かれていた、自分の体の状態、環境からの知らせ | 次の 1 手のプロンプトを組むとき (`prompt_builder.py` の観測の取り出し。時計を進める前) | 時計の値 + 1 |

時計が 0 のまま 1 手、その結果、1 手を出せなかったことが届いたら拒む。最初の 1 手で時計は 1 に進むので、0 の番号を持つ 1 手は無い。

**なぜ**: 1 手の番号で区切ると、1 回の手番で見たものと、した結果が同じ番号にまとまる。いまの世界の短期記憶は、プロンプトを組むときに取り出した観測と、その手番の行動の結果を 1 つの区切りに入れ、手番を終えたときに閉じる (`turn_trigger.py` の `complete_turn`)。表の規則は、この区切りと同じ境目になる。行動のあとで届く自分の観測 (移動の到着など) は、次の手番で取り出されるので、次の番号になる。

**退けた案**:
- 届いた時点の時計の値をそのまま付ける: 観測は時計を進める前、行動の結果は進めたあとに届くので、1 回の手番の出来事が 2 つの番号に割れる
- 時計をプロンプトを組むときに進める: 知り合い・エピソード・メモ帳は、時計の番号をすでに記録に書いている。進める位置を変えると、それらが書く番号も変わる。短期記憶を足すために、ほかの記憶の振る舞いを変えることになる
- いまの世界の短期記憶のように、区切りごとの件数の列を別に持つ: 時計と同じことを 2 か所で数えることになり、食い違ったときにどちらが正しいか決められない

**どうしないと壊れるか**: `tests/being/domain/test_short_term_memory.py` の `TestPerceive` と `TestActAndReceiveResult` が、表の行を試験にしている。

**関連**: Issue #1824 (移す作業の 1 本目)、#1465、design_decisions D1824-6。

## D1824-6. Being の snapshot に後から足したキーは、無ければ空として読む

**何を**: `BeingMemorySnapshotService.ADDED_PAYLOAD_KEYS` に、後から足したキーを並べる。restore は、payload にそのキーが無ければ空の list として読む。いまは短期記憶の `being_short_term_memory` だけ。

**なぜ**: キーを足す前に保存した snapshot から、replay も続きからの再開もできるようにするため。`EXPECTED_PAYLOAD_KEYS` は全部のキーを必須にしているので、足したキーが無い古い snapshot は欠けとして拒まれていた。

**消したキーとの違い**: 消したキー (design_decisions D1631-5 の `REMOVED_MEMORY_PAYLOAD_KEYS`) は、読み込みで取り除いて件数を trace に残す。後から足したキーは、無いことが「まだ何も覚えていない」と同じなので、件数を残さない。

**関連**: Issue #1824、design_decisions D1824-5、design_decisions D1631-5、design_decisions 27。

## D1824-7. 行動の結果は環境が文にして観測の本文に入れ、構造の欄は契約に足さない

**何を**: 本番で、観測と自分の行動の結果を契約の型に写し、今の短期記憶と並べて Being 側の短期記憶にも書く (#1824 の移す作業の 2 本目)。今の保存先 (`UnifiedRecentEventStore`) に追記を知らせる口を足し、写す側 (`PlayerShortTermMemoryCopy`) がそれを受ける。プロンプトの出力は変えない。

今の行動の結果 (`ActionResultEntry`) の欄の扱い:

| 欄 | 扱い |
|---|---|
| `action_summary`、`result_summary`、`error_code`、`should_reschedule` の文、`identifier_arguments` と `free_text_argument_names` (「呼び出し:」の行)、`omit_result_in_prompt`、発話の特別扱い | 環境が今と同じ規則で 1 つの文にし、観測の本文 (`body`) に入れる (`format_action_result_body`)。時刻の前置きと心の声は入れない |
| `game_time_label` | 観測の時刻 (`ObservedTime.display`) |
| `occurred_tick` | 観測の時刻の秒 (`ObservedTime.seconds`)。下の「時刻の秒」 |
| `should_reschedule` | 起こしてほしいかの助言 (`wants_wake`) |
| `success` | `OwnActionResult.succeeded` |
| `tool_name`、引数、心の声 | 1 手 (`AgentMove`) |
| `argument_fingerprint` | 写さない。同じ失敗の繰り返しを止める判定 (`phase_a.py`) は環境の規則で、今の保存先から読み続ける |
| `execution_provenance` | 写さない。`execution_request_id` を、結果と 1 手を結ぶ `call_id` に使う |

観測 (`ObservationEntry`) の構造の情報 (`output.structured`) も写さない。公開 SNS の投影は、環境の画面として今の保存先から読み続ける。

**なぜ**: 「呼び出し:」の行や失敗の行の組み方は、道具ごとの知識 (どの引数が識別子か、発話は本文を伏せる) と、環境ごとの言葉に依る。欄のまま契約に足すと、Being がゲームの道具の作りを知ることになる。環境が部品を文として描き、Being の知識で変わる部品だけを構造で渡す (#1520)。文で持てば、Being の側からも今と同じ行を組める (時刻の前置き + 本文 + 心の声)。

**退けた案**:
- `error_code`、`action_summary` などを `OwnActionResult` の欄として足す: Being が使い道を持たない欄が契約に増える。今の Being に、失敗の種類で振る舞いを変える部品は無い。要るようになったら、そのときに文ではなく意味の欄 (失敗の種類など) として足す
- 本文を `result_summary` だけにする (今の変換のまま): 「[行動] … → [結果] …」の形と「呼び出し:」の行が失われ、Being の側から今と同じ行を組めない

**写さないもの** (`being_short_term_memory_not_copied` の trace に、理由 `reason` と種類 `event_kind` を残す):

| 理由 | 何か |
|---|---|
| `being_inner_record` | 同じ行動の繰り返しへの警告 (種類は `loop_guard`) と、1 手を持たない記憶の道具の結果。Being の内側の記録で、環境で起きたことではない。1 手と組になる記憶の道具の結果は写す (design_decisions D1824-9) |
| `empty_body` | 本文が空 |
| `missing_time_label` | 時刻が無い。いまは死から戻った知らせ (`player_revived_post_hoc`) だけが時刻を渡していない |
| `unpaired_result` | 結果を待っている 1 手が無いか、呼び出しの ID が違う自分の行動の結果。環境と Being の取り決めが崩れたしるし (design_decisions D1824-9) |
| `memory_rule` | 短期記憶の決まり (自分の行動の結果を観測として渡した、など) を満たさない |
| `contract_violation` | 契約の型の決まりを満たさない値が来た (引数に JSON でない値がある、など) |
| `unexpected_error` | 上のどれでもない例外。run は止めず、例外の型を残す |

**3 本目への引き継ぎ**: 【直近の出来事】を Being の側から組むと、上の表の写さないものは出なくなる。同じ行動の繰り返しへの警告は、今のプロンプトには出ている。3 本目で、これを出し続けるか、Being の内側の記録として別に持つかを決める。

**時刻の秒**: 観測 (`ObservationEntry`) は起きた tick を持たない。取り出した時点の tick で秒を埋めると、時刻の表示 (起きた時点のラベル) とずれるので、観測の秒は分からない (`None`) とする。行動の結果は記録した tick (`occurred_tick`) を持つので秒を入れる。

**1 手を出さない結果**: 移動の到着と、移動が止められた知らせは、1 手と同じ手番には届かない (`execution_provenance` が無い)。契約の決まり (呼び出しの ID を持たない他の経路で届く) どおり、経路を「見た・聞いた」にして写す。D1824-5 の規則で、次の 1 手の番号になる。今の短期記憶でも、手番の間に届くので次の区切りに入る。

**関連**: Issue #1824、design_decisions D1824-5、#1520、#1771。

## D1824-8. 観測は、環境の中で起きた順を持つ。順は同じ環境の中でだけ比べられる

**何を**: 契約の観測 (`Observation`) に、起きた順 (`order: OccurrenceOrder | None`) を足す。`OccurrenceOrder` は環境の名前と値を持つ。別の環境の値と大小を比べると `ContractViolation` を投げる。

写す側 (`PlayerShortTermMemoryCopy`) は、環境の名前 (`WorldRuntime.environment_name_for`) と、今の出来事の `occurred_at.timestamp()` を起きた順にする。snapshot は観測の `order` を残す。起きた順を足す前に保存した観測は、起きた順を持たない (`None`) として読む。

この PR では、起きた順で並べる処理はまだ無い。並べるのは、短期記憶の集約に作り直すときの `recent()` (#1824 の設計)。

**なぜ**: 今の保存先は、時系列を `occurred_at` で並べ直して【直近の出来事】を組む (`unified_recent_event_store.py` の `get_timeline`)。Being の側は届いた順 (1 手の番号の順) に持つ。自分の 1 手より前に他人の行動が起き、その観測が次の手番で取り出されると、2 つの並びが食い違う。Being の側で【直近の出来事】を組んで今の文と突き合わせたところ (mine_village_v1、3 シード × 40 tick、でたらめに行動するスタブ)、食い違いは 366 件あり、すべて並び順だけの違いだった。起きた順で並べれば、今と同じ文になり、「探索していた相手から奪おうとして失敗した」のような因果も世界で起きた順に読める。

同じ環境の中でだけ比べるのは、環境ごとに時計が違うため。値は秒として使わず、順だけを表す。時刻の差は `ObservedTime.seconds` が持つ。

**退けた案**:
- Being の側は届いた順 (自分が見た順) で出す: 契約は変えずに済むが、切り替えるとプロンプトの並び順が変わる。今と同じ文になることで切り替えを確かめられなくなる
- 起きた順を `ObservedTime` の欄にする: 時刻の表示と秒は環境の時計の値で、起きた順は並べるためだけの値。比べ方の決まり (同じ環境の中だけ) を持つので、別の型にした

**関連**: Issue #1824、design_decisions D1824-5、design_decisions D1824-6、design_decisions D1824-7。

## D1824-9. 短期記憶は、出来事の種類ごとの型と、規則を持つ集約で持つ

**何を**: Being の短期記憶 (`being/domain/short_term_memory.py`) を、値を持つだけの型から、規則を持つ集約 (`ShortTermMemory`) に作り直す。集約は持ち主の `BeingId` を持つ実体で、操作は自分の中身を書き換え、値を返さない。決まりに反する操作は例外を投げ、中身もためたイベントも変えない。出来事、`MemoryOperationResult`、`Backstory`、`OccurrenceOrder` は値のまま (中身の変わらない frozen dataclass)。

出来事 (`Experience`) は種類ごとに型を分ける。

| 型 | 中身 |
|---|---|
| `Perception` | 自分の行動の結果以外の経路で届いた観測 1 つ |
| `Attempt` | Being が選んだ 1 手と、その結果。結果は、ゲームの行動なら自分の行動の結果の観測、記憶の道具なら記憶の結果 (`MemoryOperationResult`)、どちらも無ければ結果の分からない試み |
| `Lapse` | 1 手を出せなかったこと (迷った、LLM の呼び出しが失敗した、道具を選ばず文章を返した) |

規則は集約の振る舞いに置く。

| 振る舞い | すること |
|---|---|
| `act(1 手, 今のターン)` | 結果を待つ 1 手 (`awaiting`) として持つ。前の 1 手の結果が来ていなければ、前の 1 手を結果の分からない試みとして残す |
| `perceive(観測, 今のターン)` | 次のターンの番号で足す |
| `receive_result(結果, 今のターン)` | 待っている 1 手と組にして今のターンの番号で足し、待っている 1 手を無くす。待っている 1 手が無い、呼び出しの ID が違うときは `ShortTermMemoryUnpairedResultException` |
| `lapse(本文, 時刻, 今のターン)` | 今のターンの番号で足す |
| `recent()` | ターンの順に並べ、同じ環境が続く間は起きた順 (design_decisions D1824-8) に並べ直す。起きた順を持たない出来事は動かさない |
| `fold(今のターン)` | 直近の範囲 (`recent_from` から今のターンまで。出来事の無いターンも数える) が `RECENT_TURNS` (20) に届いていれば、古い `FOLD_TURNS` (10) ターン分を外し、範囲の始まりを 10 進め、「出来事を外した」イベント (`ExperiencesFolded`。外した出来事と、そのときのいきさつ) をためる。外すターンに選んだまま結果の来ない 1 手も、結果の分からない試みとして一緒に外す。外す出来事が無ければイベントはためない |
| `add_backstory` | 足して新しい `BACKSTORY_GENERATIONS` (3) 世代だけ残す |

ためたイベントは、ゲームの集約 (`AggregateRoot`) と同じ `get_events()` / `clear_events()` で渡す。`being/` はゲームのパッケージを import できないので、`AggregateRoot` は継承せず、同じ名前のメソッドを自前で持つ。イベントを取り出して受け手 (いきさつを作る、エピソードを書き起こす) に渡すのは、イベント基盤の作り直し (#1837) のあと。

保存先 (`InMemoryShortTermMemoryRepository`) は、出し入れのたびに写しを渡し、ためたイベントは保存しない。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。写しを渡すのは SQLite の保存先 (`sqlite_shop_repository.py` の `copy.deepcopy`) と同じ考え方だが、出来事といきさつは中身の変わらない値なので、deepcopy せず、同じ値を持つ集約を作り直して写しにする (出来事が 2000 件の集約で、deepcopy 1 回に 25ms ほどかかった)。snapshot は取った時点で JSON にするので、あとで集約を書き換えても変わらない。

イベントの型 (`ExperiencesFolded`) は、ゲームの `BaseDomainEvent` を継がない素の値にする。`being/` が `domain.common` を import できないため。イベント基盤の作り直し (#1837) の共通の基底に乗せ替えるとき型の形を変えずに済むよう、`event_id` (`uuid4().int`) と `occurred_at` (UTC) を同じ名前で持ち、Being の ID とターンを自分で持つ。ゲームの集約にある `add_event` と `warn_if_pending_events` は、取り出す側ができるまで持たない。

出来事を種類ごとに読む側 (文を作る側、snapshot の保存) は、`Experience.show_to(reader)` で種類ごとのメソッドを呼ばれる (`ExperienceReader`)。型を見分けずに済む。

結果を待つ 1 手と範囲の始まりのターンは、集約に持ち、snapshot に入れる。集約に作り直す前の snapshot (観測と 1 手の組の並び) は、1 手の無い出来事を `Perception`、1 手のある出来事を結果つきの `Attempt` として読む。

写す側 (`PlayerShortTermMemoryCopy`) は、Being を引き、ゲームの型を契約の型に変え、集約に頼んで保存し、失敗を trace に残すだけにする。今の時計の番号から出来事の番号を決める自由関数 (`turn_for_event`) と、書き留めた 1 手の dict は消した。

**なぜ**: 規則が型の外にあったため (経路の型を `isinstance` で見分ける自由関数、application のサービスの dict にある 1 手、設定と application にある 20 / 10 / 3)、同じ規則を何か所でも守る必要があり、結果を待つ 1 手は snapshot に入っていなかった (#1824、CLAUDE.md の「ドメインモデルは振る舞いで設計する」)。

種類ごとに型を分けたのは、性質が違うものを 1 つの型にすると、その型の不変条件を作るときの検査で守ることになり、種類による分岐が外に広がるため。

**1 手と結果は 1 対 1**: 1 手に結果は 1 つだけ付く。結果を受け取ったら、待っている 1 手は無くなる。同じ 1 手への 2 件目の結果は、組にする 1 手の無い結果として `unpaired_result` の trace に残り、fuzz が穴として数える。2026-10-24 に fuzz (mine_village_v1 と station_drill を各 10 シード × 40 tick、でたらめに行動するスタブ) で数えたとき、結果の付いた 4049 件の要求のうち 2 件以上の結果が付いたものは無かった。成功した explore / interact / travel_to は do_* だけが記録し、phase_b の汎用の記録は飛ばす (`phase_b.py` の `skip_duplicate_action_log`)。

**退けた案**:
- 1 手に結果の並び (1 件以上) を持たせる: 2 件付く経路が無いのに、読む側すべてが並びを扱うことになる
- 待っている 1 手を出来事に先に入れ、結果が来たら差し替える: 出来事が後から書き換わり、`recent()` の結果が結果の届く前後で変わる
- 集約も中身の変わらない値 (frozen dataclass) にし、操作が新しい集約を返す: ID を持ち時間とともに変わる実体に値の作り方を当てることになり、イベントを出すには操作が「新しい集約とイベントの組」を返す不自然な形になる。最初はこの形で作り、誤りとして作り直した (#1841 を閉じた)

**記憶の道具の結果と、1 手を出せなかったことを写す**: 環境の側 (`result_from_action_result`) が、記憶の道具 (メモ、エピソード、状況の評価) の結果を `MemoryOperationResult` に、それ以外を自分の行動の結果の観測に変え、写す側が `receive_result` に渡す。記憶の道具は手書きの一覧 (`observation_translation.py` の `_AGENT_SIDE_TOOLS` とメモの接頭辞) で見分け、道具のカタログで環境に働きかける道具 (world_action) でないものと一致することは試験 (`test_observation_translation.py` の `TestResultFromActionResult`) が見張る。1 手を出せなかったときに phase_b が残す行は、実行の要求の ID より先に道具の名前 (`迷い`、`一瞬の空白`) で見分け、`lapse` に渡す。1 手を持たない記憶の道具の結果は、組にする 1 手が無いので写さない (`being_inner_record`)。

**定数と設定のキー**: 直近として持つターン数 (`RECENT_TURNS`、20)、一度に外すターン数 (`FOLD_TURNS`、10)、いきさつの世代数 (`BACKSTORY_GENERATIONS`、3) は、全員共通の決まりとしてドメインの定数にした。どの profile も値を変えていなかった。今の短期記憶 (`SummarizingShortTermMemory`) も同じ定数を使う。実験の設定のキー `SHORT_TERM_MEMORY_TURN_CAP` / `SHORT_TERM_MEMORY_TURN_COMPACT_COUNT` は消し、書かれていたら知らないキーとしてではなく、消したキーとして理由を添えて起動前に止める (`resolved_runtime_config.py` の `_REMOVED_RUNTIME_CONFIG_KEYS`)。行動の結果を 1 人 100 件までに削る処理 (`DefaultActionResultStore`) もなくした。直近の範囲が 20 ターンで外れるので、100 件には届かない。

**まだしないこと**: `fold` はまだ誰も呼ばず、ためたイベントもまだ誰も取り出さない。そのため出来事は run の間ずっと増える (#1830 からある振る舞い)。集約を書き換えるたびに出来事の件数に比例する確かめが走るので、長い run では 1 件ごとの追記が少しずつ遅くなる。`fold` を呼ぶ PR で解消する。

**関連**: Issue #1824、design_decisions D1824-5、D1824-7、D1824-8。

---

## D1652. CI の uv は、配布元からではなく PyPI から固定版を入れる

**何を**: CI で uv を使う job は、`actions/setup-python` のあと `python -m pip install uv==<固定版>` で uv を入れる。`astral-sh/setup-uv` は使わない。版は全 job で同じにする。そのあとの `uv sync --locked` と `uv run --frozen` は変えない (design_decisions 111 の、uv.lock のとおりに入れる守りはそのまま)。依存のキャッシュは置かない。

**なぜ**: setup-uv は、uv の版の一覧を `raw.githubusercontent.com` から、uv 本体を `releases.astral.sh` から取りに行く。ここで時間切れが 2 回起きた。

- #1710 の CI (run 39278879113 の 1 回目) では、版の一覧の取得が 5 秒で時間切れになり、test job が落ちた
- main の run 39289145404 では、uv 本体の取得が 180 秒で時間切れになって再試行し、test (3/3) の job が 355 秒になった

#1652 で test job を 3 台に分けたので、1 回の CI で uv を取りに行く回数も増えた。PyPI は依存を入れるときにすでに頼っている取得先なので、取得先が 1 つ減る。

キャッシュを置かないのは、無くても遅くならなかったため。setup-uv のキャッシュがあったころの main では、uv の準備が 2〜6 秒、依存を入れる手順が 1〜3 秒だった。キャッシュ無しで PyPI から入れると、uv を入れるのが 1〜5 秒、依存を入れるのが 2〜4 秒だった (#1826 の CI 3 回)。数秒のために `actions/cache` を足すと、キャッシュの置き場所という取得先がもう 1 つ増える。

**どう守るか**:

- `tests/architecture/test_ci_workflow.py` が、uv を使う job がどれも、uv を使う前に PyPI から同じ固定版の uv を入れること、setup-uv を使わないことを見る
- 同じ試験が、どの job の `uv sync` も `--locked`、`uv run` も `--frozen` であることを見る

## D1837. ゲームと Being のイベント基盤を一つにする

**何を**: [Issue #1837](https://github.com/Motifman/llm-rpg/issues/1837) の決めたこと 1〜6。
次の設計を複数の PR で実装する。PR 1 では共通の基底と依存の境界だけを用意し、配送と Being の接続は後続に分ける。

1. 最上位の `eventing/` に、イベントの基底・受け手の登録・同期と非同期の配送・失敗の知らせ先を置く。`ai_rpg_world` 内では自分以外を import しない。同じプロセスの中だけを扱い、外部ライブラリは使わない。`CommandScope` と取引の outbox はゲーム側に残す。既存の確定前の連鎖は維持するが、確定前の受け手は新設せず、まず集約の規則にできるかを検討する。
2. 共通の `DomainEvent` は `event_id` と `occurred_at` だけを持つ。ゲームの `BaseDomainEvent` がそれを継ぎ、`aggregate_id`・`aggregate_type`・`occurred_tick` を加える。ゲーム側の別名 `DomainEvent` も共通型を指す。ゲームの時刻と Being のターンを一つの項目には入れない。
3. ID を持つ集約は自身の状態を書き換え、共通の基底の `add_event` / `get_events` / `clear_events` でイベントをためる。値の変わらない形は値オブジェクト・イベント・snapshot の中身に使う。ゲームの `warn_if_pending_events` はゲーム側に残す。`EventProducingAggregatePort` は維持し、取り出しと消去を行う場所を集める。
4. 非同期の受け手は確定後に `ThreadPoolExecutor` で走らせる。同じ Being は到着順、異なる Being は並行に処理し、スレッド数は実験設定に置く。裏のスレッドは結果を待ち行列に置くだけにし、集約への反映はその Being のターン開始時に行う。必須の知らせ先へ、受け手の例外・未完了件数の上限超過・終了中の受付拒否を通知する。終了時は受付停止、期限付きの待機、完了結果の反映、snapshot 保存の順とし、期限超過で捨てた結果も trace に残す。
5. 休眠している文脈の登録は文脈ごとに新しい確定前後の登録へ置き換え、試験を移してから古い経路と `is_synchronous` を消す。受け手のクラスとイベントとの対応は残す。既存の確定前登録は意味を保って移し、本番へ戻すときに必要性を見直す。再送必須の受け手の失敗で後続の配送が飛ぶ問題も配送の移行で直す。
6. Being は保存を確定の区切りとし、リポジトリが保存時にイベントを取り出して消去し、組み立て時に渡された配り手へ渡す。`PipelineEventPublisher` 内の四つの受け手も共通基盤の確定後の受け手に移し、失敗は既存の `SIDE_HANDLER_FAILED` へつなぐ。直接発行する経路と `EventPublisher` の口の整理は #1340 に分ける。

**なぜ**: ゲームの `domain/common` に基盤を置いたままでは Being がゲームに依存する。Being 専用の配送を増やすと、失敗の記録や終了処理が二重になる。共通基盤にゲーム固有の項目を持たせず、集約への書き込みをターンを進める側に絞れば、依存の逆転と並行更新による消失を避けられる。集約を値の変わらない形のまま新しい値とイベントの組を返す案は、主体の同一性と状態変更を値として扱ってしまうため採らない。

**どうしないと壊れるか**: 共通基盤からゲームを import すると Being の独立性が崩れるので、依存の境界を試験で見張る。取り出しと消去を呼び出す側へ分散するとイベントが残って重複配送される。裏のスレッドから集約へ直接書くと、ターン処理との競合で変更が消える。失敗の知らせ先を省略可能にすると trace に残らない。休眠中の登録を移す前に古い経路を消すと、受け手の対応まで失われる。

## D1621. エピソードは、自分の目次を持つ集約にする。目次の並びは問い合わせで作る

**何を**: エピソード (`being/domain/episode.py` の `Episode`) を、1 件ずつ ID を持つ集約にする。集約は、書いた Being の ID と、自分の目次 (`EpisodeIndex`) と、直した履歴 (`IndexRevision` の並び) を持つ。呼び出し (`recall`) と目次の直し (`revise_index`) は中身を書き換え、値を返さず、`EpisodeRecalled` / `EpisodeIndexRevised` をためる。決まりに反する操作は例外を投げ、中身もためたイベントも変えない。本文・呼び名・書いた時・書いた環境は変わらない。`EpisodeIndex` と `IndexRevision` は値のまま。

目次として見せる並び (どれを何件、どの順で) は、状態として持たず、これまでどおり `EpisodeIndexSelection` が保存先の一覧から毎回作る。呼び名が同じ Being の中で重ならない決まりは、集約ではなく保存先 (`EpisodeRepository.add` と `replace_all_by_being` の `EpisodeConflictException`) に残す。

持ち主の `BeingId` は集約が持つ (短期記憶・メモ帳と同じ)。保存先は集約の `being_id` で分けて持ち、別の Being のエピソードを混ぜて戻そうとすると断る。イベントを受け取る側は、誰のエピソードかを集約のイベントから知れる。snapshot の payload は Being ごとに 1 本なので、エピソードの欄に持ち主は書かず、戻す先の Being の ID で組み立てる。

保存先は出し入れのたびに写しを渡し、ためたイベントは保存しない (D1824-9 の短期記憶と同じ)。後の版でない書き戻しを断る検査 (`Episode.follows`) は残す。写しを持つ手が 2 つあると、古い写しを後から書き戻せるため。

**なぜ**: CLAUDE.md の「ドメインモデルは振る舞いで設計する」(#1843) に合わせる。目次をどこが持つかは 2 案を比べた。

| 案 | 持つもの | 採ったか |
|---|---|---|
| A. エピソードの集約が自分の目次を持つ | エピソード 1 件の中に、目次・直した履歴・呼び出しの記録 | 採った |
| B. Being ごとの目次の集約を別に置く | 目次の集約が全件の目次と呼び出しの記録を持ち、エピソードは本文だけを持つ | 採らない |

呼び出しと目次の直しは、どちらも 1 件の中で閉じる。1 件の中の決まり (直した履歴の順、呼び出しのターンが戻らない) は、その 1 件の集約に収まる。エピソードをまたぐ決まりは、いま呼び名が重ならないことだけで、それは書くときの 1 回で決まる。案 B にすると、書くたびに 2 つの集約を一緒に変える必要があり、片方だけ保存される隙ができる。snapshot のキーも変わる。

**案 B が要るようになる条件**: 目次そのものに決まりができたとき。たとえば、目次に載せる件数や顔ぶれを本人が選んで固定する、目次から外す、目次の並びを本人が決める。どれも、エピソードの一覧から毎回作れない状態を目次が持つことになり、Being ごとの目次の集約が要る。

**どうしないと壊れるか**: 保存先が同じ集約を指し続けると、save し忘れた呼び出しや目次の直しも保存されたように見える。呼び名の決まりを保存先から外すと、重なった呼び名で引いたときにどちらのエピソードかが決まらない。
