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
| 11. 設定 DTO 集約 + ctor 注入 | 2026-06-09 | PR #446-#451 (リファクタ 6 PR) |
| 12. Future work は xfail-strict で可視化 | 2026-06-09 | PR #451 (慣習化) |
| 13. memory caller の未解決時挙動は役割で分岐 | 2026-06-14 | PR #491 / #492 |
| 14. promotion_frontier は Phase 3 Step 3c scope 外 | 2026-06-14 | PR #495 |
| 15. BeingSnapshot v2 は memory payload をオペーク JSON で持つ | 2026-06-14 | Phase 4 Step 4-1 |
| 16. run 途中再開 CLI は 4 DB + in-memory memo で動く | 2026-06-14 | Phase 5 |
