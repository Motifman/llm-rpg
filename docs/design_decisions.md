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
を解決できない構成は起動時に止める。capture が無効で episodic 記憶も無効なら、従来どおり
この配線は遅延したままとし、公開 tool の集合や世界の振る舞いは変えない。

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

追放者は `is_down=False` なので、世界観測の門だけを見れば受信可能である。実際に観測が
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
- 通常試験と品質検査の Python 3.10、setup-uv、locked sync、frozen run を固定する
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
は `ItemAggregate.advance_spoilage` に置く。`FoodSpoilageStageService` は走査・
永続化・観測 callback だけを担当する。

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

## 146. 記憶リンクとクラスタ昇格は呼び出し側の BeingId を使う

**何を**: `EpisodicMemoryLinkApplicationService` と
`EpisodicSemanticClusterPromotionService` は `BeingId` を引数で受け取る。
これらのサービスは `BeingAttachmentResolver` を持たない。昇格フロンティアは
まだ `player_id` keyed。

**なぜ**: chunk (#134) と prompt (#133) と探索ツール (#132) で既に対があるのに、
link / promotion だけが葉で付着を引き直していた。

**入口**: chunk の `on_episode_committed`、prompt の受動想起候補、
`ActionResultRecorder` の `on_after_tool_turn`、explore の `ActingBeing`。
