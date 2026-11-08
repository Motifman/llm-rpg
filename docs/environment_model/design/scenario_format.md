# シナリオの形式 (YAML)

シナリオの作者 (人と LLM) が書く形式。読み込む側 (infrastructure) が、ここから名詞と動詞の宣言 ([world_design.md](world_design.md)) を作り、`WorldDesign.compose` に渡す。決めた経緯は #2052。

## 決まり

- 1 つのシナリオは 1 つの YAML ファイル。共通の部品は `includes:` で取り込む
- 名前で指すものは、欄の値ではなく、地図 (mapping) の鍵に書く (`spots: { lift_landing: { ... } }`)。鍵が `SpotId` などの宣言の名前になる。同じ鍵を 2 回書くと、YAML を読む時点で `DesignFlaw` にする
- 作者は、名詞の中に、その名詞に付く動詞を書いてよい (物の中に操作、区画の中に出入り)。読み込む側が名詞と動詞に分ける (#1990)
- 宣言の型は既定値を持たない。書かなかった欄は、読み込む側が共通の部品 (データ) の既定で埋める (#2029 の E2)。埋めたものは `DesignWarning` にしない。作者が書くべきなのに書かなかったもの (知覚の文など) だけを `DesignWarning` にする
- 誤りの場所 (`DesignLocation`) は、宣言の種類・名前・欄と、どのファイルに書いたか (シナリオか、取り込んだどの共通の部品か) で表す。誤りの文の先頭にもファイルの名前が出る。`defaults:` で埋めた欄の誤りは、埋めた宣言ではなく `defaults:` を書いた場所を指す。書き忘れた欄は、いちばん近い書かれた親を書いたファイルを指し、どこにも無ければシナリオのファイルを指す。YAML の道筋 (`spots.lift_landing.objects.lift_panel.interactions.start_lift.precondition`) は、`DesignLocation("object", "lift_panel", "interactions.start_lift.precondition")` に写す
- 文の中の人は、`{actor}` `{target}` `{chosen_by_group}` `{each_person}` だけ。物や場所の名前は、作者が文に直接書く

## 一番上の欄

```yaml
includes: [common/ja_default.yaml]    # 共通の部品。断りの文の表、組み込みの行為の知覚の文、知覚の既定の文、行為の長さなど
introduction:                         # WorldIntroduction
  text: ...                           # 導入
  objective: ...                      # 目的
rules: { ... }                        # WorldRules。includes の既定を、書いた欄だけ上書きする
time: { day_night: ..., weather: ... }
flags: { ... }
groupings: { ... }                    # 分け方と、その中の集まり
spots: { ... }                        # 場所。中に区画・物・見つかる物を書く
passages: { ... }
item_specs: { ... }
characters: { ... }
world_stages: { ... }
initial_stage: ...                    # 最初の段階の名前。world_stages を書いたら必須、書かなければ NoWorldStages
group_decisions: { ... }
outcomes: { ... }
happenings: { ... }
reactions: { ... }
joint_actions: { ... }
person_interactions: { ... }          # 殴る、盗むなど、人への操作
ending: { ends_when: ... }
refusal_texts: { ... }                # RefusalTexts。ふつうは includes から取り込み、行を書き換える
built_in_action_perceptions: { ... }  # 組み込みの行為ごとの知覚 (行為は travel、hand_over などの snake_case)
defaults: { ... }                     # 書かなかった欄の既定。下の「書かなかった欄」
perception_defaults: { ... }          # 書かなかった知覚の文の既定。下の「書かなかった欄」
```

宣言に無い欄を書くと `DesignFlaw` にする (綴り違いを見逃さない)。

## 条件と効果の書き方

木の 1 つの節は地図で、種類を表す鍵をちょうど 1 つ持つ。鍵が種類 (条件や効果の型の名前を snake_case にし、`Condition` / `Effect` を外したもの)、値がその欄。欄が 1 つだけの種類は、値に直接書いてよい。条件の節だけは、種類の鍵と並べて `failure_text` を書ける。種類の鍵が 0 個か 2 個以上の節は `DesignFlaw`。

```yaml
precondition:
  all_of:
    - flag_is_raised: generator_running        # 欄が 1 つなら直接
    - has_item: { who: actor, item_spec: lift_key, count: 1 }
  failure_text: 操作盤の鍵穴に合う鍵を持っていないか、機械が動いていない。
```

- `failure_text` は、その節の欄と並べて書く。条件を置いた場所の根には必ず書く (#2029 の B1)
- 主語は `actor` `target` `chosen_by_group` `each_person` と、名指しの人 (`{ named: haru }`)

## 宣言ごとの欄

欄の名前は、宣言の型の欄の名前と同じ。名詞の中に書く動詞の欄 (物の `interactions`、区画の `access`、通路の `condition`、品物の `use` と `interactions`、段階の `when_entered` と `when_left`、集団の決定の `voters` から `when_undecided`) は、読み込む側が動詞の宣言に分ける。

| 書く場所 | 欄 |
|---|---|
| `flags.<名前>` | `meaning`, `initially_raised` |
| `spots.<名前>` | `name`, `description`, `atmosphere` (`lighting`, `outdoor`, `temperature`, `ambient_sound`, `smell`), `sections`, `objects`, `discoverables` |
| `spots.<場所>.sections.<名前>` | `name`, `capacity` (`null` は定員なし), `reachable_objects`, `access` (`enter_label`, `leave_label`, `enter_text`, `leave_text`, `exertion`, `duration`, `entry_condition`, `perceived_as`) |
| `spots.<場所>.objects.<名前>` | `name`, `description`, `appearance` (`seen_in_dark`, `hidden_until_revealed`), `state_keys`, `interactions` |
| `spots.<場所>.discoverables.<名前>` | `found_text`, `condition`, `when_found`, `finding` (`once_in_world` / `once_per_person`) |
| 操作 (`interactions.<名前>`、`person_interactions.<名前>`) | `display_label`, `precondition`, `effect`, `success_text`, `shows_on_success`, `exertion`, `actor_requirement`, `perceived_as`, `reaches_unseen`, `duration`, `allows_stealth`, `arguments` |
| `passages.<名前>` | `ends` (2 つ), `two_way`, `travel_ticks`, `states` (`<状態>: { display_name, traversable, sound_loss }`), `initial_state`, `hidden_until_revealed`, `condition` (書けば `PassageTraversalDeclaration`) |
| `item_specs.<名前>` | `name`, `description`, `state_keys`, `lights_up` (`null` か `{ key, value }`), `hands_needed`, `interactions`, `use` (書けば `ItemUseDeclaration`) |
| `groupings.<名前>` | `name`, `visibility`, `changes`, `groups` (`<集まり>: { name, members_know_each_other, shared_description }`) |
| `characters.<名前>` | `appearance`, `spawn_spot`, `initial_items`, `initial_held`, `initial_groups`, `knows_at_start`, `max_hp`, `pack_capacity`, `being` |
| `world_stages.<名前>` | `name`, `description`, `allowed_actions` (`all` か一覧), `when_entered`, `when_left` |
| `group_decisions.<名前>` | `name`, `abstain_allowed`, `reveals_ballots`, `voters`, `choices`, `when_decided`, `when_undecided` |
| `outcomes.<名前>` | `name`, `announcement` |
| `happenings.<名前>` | `condition`, `effect`, `once`, `notice` |
| `reactions.<名前>` | `condition`, `when_becomes_true`, `when_becomes_false` |
| `joint_actions.<名前>` | `required` (`{ object, interaction }` の一覧), `window`, `distinct_people`, `on_complete`, `on_timeout`, `complete_notice`, `timeout_notice` |
| `time` (必須) | `day_night` (`null` か `{ ticks_per_day, starts_at, phases: { <段階>: { begins_at, dark, announcement } } }`), `weather` (`null` か `{ initial, changes, announce_changes, obscuring }`。`changes` は `null` か `{ ticks, transitions }`、`transitions` は `default` か `{ <今>: { <次>: 重み } }`)。天候と昼夜の無い世界でも `null` と書き、欄そのものが無ければ `DesignFlaw`。書き忘れを「無い」として通さないため、`defaults:` でも埋めない |
| `rules` | `tend` (`null` か `{ revive_hp_rate }`), `fatigue`, `hunger`, `death`, `departed_persons_act`, `name_tags`, `hearing`, `stealth`, `action_durations`, `person_max_hp`, `pack_capacity` |

値の書き方:

- 列挙 (`lighting`、`loudness`、`ActionKind` など) は名前を小文字の snake_case で書く (`very_dark`、`hand_over`)
- 「無い」を表す型 (`NoSmell`、`NoCapacity`、`Silent`、`NoFailureWitness`、`NoNotice`、`NotSeenInDim` など) は `null`
- 雰囲気を変える効果 (`change_atmosphere`) で書かなかった欄は変えない (`Unchanged`)。`null` は「無くす」
- 状態の鍵は `<名前>: { kind, initial }`。`kind` は `flag` / `count` / `written_text` / `{ choice: [...] }` / `{ stock: { capacity, refills_every } }` (`refills_every: null` は補充しない)。`initial` は種類に合わせて真偽・数・選択肢の名前で、書いた文の鍵は `null`
- 状態の鍵を指すときは `<物か品物>.<鍵>` (`lift_panel.power`、`lamp.lit`)
- 行為は組み込みの行為の名前か `{ interaction: <名前> }`。人の結末は結末の名前か `died`
- `exertion` は `uses_body` / `does_not_use_body`、`actor_requirement` は `living_only` / `living_or_departed`、`salience` は `notable` / `background`、`duration` は tick の数か `default`、操作の引数は `<名前>: text` / `<名前>: item`
- 知らせ (`notice`) は `sight_at: { spot, texts, salience }` / `sound_from: { spot, sound, salience }` / `announcement_to: { audience, text, salience }`
- 体力 `max_hp` と荷 `pack_capacity` を書かない登場人物は、`rules` の `person_max_hp` と `pack_capacity` で始まる (#2055)

## 書かなかった欄

宣言の型は既定値を持たない。書かなかった欄は、読み込む側が `defaults:` の、その宣言の種類の欄で埋める。`defaults:` は共通の部品に書き、シナリオでも `includes:` と同じく鍵ごとに上書きできる。埋めるのは欄の 1 段だけで、地図の中までは重ねない (`passage.states` の既定は、`states` を書かなかった通路だけに入る)。

```yaml
defaults:
  flag: { initially_raised: false }
  atmosphere: { outdoor: false, temperature: normal, ambient_sound: null, smell: null }
  passage:
    two_way: true
    states: { open: { display_name: 開いている, traversable: true, sound_loss: 0 } }
    initial_state: open
    hidden_until_revealed: false
```

`includes:` の重ね方は地図を全階層で重ねるので、シナリオで `defaults.passage.states` を書くと、共通の部品の状態に足される。状態を置き換えたいときは、通路の `states` に直接書く。

種類は `flag` `spot` `atmosphere` `section` `section_access` `object` `appearance` `state_key` `discoverable` `interaction` `passage` `passage_state` `item_spec` `grouping` `group` `character` `world_stage` `group_decision` `outcome` `happening` `reaction` `joint_action` `perception` `sight_texts` `sound` `sight_at` `sound_from` `announcement_to` `day_phase` `weather`。知らない種類は `DesignFlaw`。

知覚 (`perceived_as`) の目撃の文 `witness`、音の文 `sound`、された人の文 `target` (人への操作だけ) を書かなかったときは、`perception_defaults:` の文で埋めて `DesignWarning` を残す。`sound: null` と書けば音の無い操作 (`Silent`) で、警告しない。

```yaml
perception_defaults:
  witness: { clear: "{actor}が何かをした。" }
  target: { clear: "{actor}があなたに何かをした。" }
  sound: { loudness: normal, clear: 物音がした。, muffled: かすかな物音がした。 }
```

## 例: 廃坑の山村の昇降機

今の形式では、籠に乗ることを人の属性 (`aboard`)、籠の在庫 (3)、乗った印の品物 (`lift_berth`) の 3 つで表している。新しい形式では、乗り場の中の籠を区画 (定員 3) にし、操作盤を籠の中からしか届かない物にする。

```yaml
spots:
  lift_landing:
    name: 昇降機の乗り場
    description: 坑道の最も深い所にある昇降機の乗り場。鉄の籠が地上へ続く縦穴に吊られている。
    atmosphere: { lighting: dark, outdoor: false, temperature: cold, ambient_sound: 縦穴を吹き上がる風の音 }

    sections:
      cage:
        name: 昇降機の籠
        capacity: 3
        reachable_objects: [lift_panel]          # 操作盤は籠の中からしか届かない
        access:                                   # SectionAccessDeclaration
          enter_label: 籠に乗り込む
          leave_label: 籠から降りる
          enter_text: 鉄の籠に乗り込んだ。籠が足もとで小さく揺れた。
          leave_text: 籠から降りた。
          entry_condition:
            not: { flag_is_raised: lift_departed }
            failure_text: 籠はもう上がってしまった。
          perceived_as:
            witness: { clear: "{actor}が昇降機の籠に乗り込んだ。" }

    objects:
      lift_panel:
        name: 籠の操作盤
        description: 籠の奥の壁にある操作盤。鍵穴と始動の把手が付いている。
        interactions:
          start_lift:
            display_label: 鍵を差して昇降機を動かす
            precondition:
              all_of:
                - not: { flag_is_raised: lift_departed }
                  failure_text: 籠はもう上がってしまった。昇降機は二度と動かない。
                - has_item: { who: actor, item_spec: lift_key, count: 1 }
                  failure_text: 鍵穴に合う鍵を持っていない。
                - flag_is_raised: generator_running
                  failure_text: 把手を引いても、籠はぴくりとも動かない。
              failure_text: 昇降機は動かない。
            effect:
              raise_flag: lift_departed
            success_text: 籠が大きく揺れ、ゆっくりと縦穴を上がりはじめた。
            perceived_as:
              witness: { clear: "{actor}が昇降機の操作盤に鍵を差し、把手を引いた。" }
              sound: { loudness: very_loud, clear: 鉄の籠が軋みながら上がっていく音がした。, muffled: 遠くで重い鉄の軋む音がした。 }

outcomes:
  rescued: { name: 救出, announcement: "{each_person}は昇降機で外へ出た。" }
  stranded: { name: 取り残された, announcement: "{each_person}は坑道に取り残された。" }

happenings:
  lift_leaves:                                    # 籠が上がったとき、籠の中の人は救出、ほかは取り残される
    condition: { flag_is_raised: lift_departed, failure_text: 籠はまだ上がっていない。 }
    once: true
    effect:
      sequence:
        - for_everyone:
            people: { where: { is_in_section: { who: each_person, section: cage } } }
            effect: { set_outcome: { who: each_person, outcome: rescued } }
        - for_everyone:
            people: { where: { not: { is_in_section: { who: each_person, section: cage } } } }
            effect: { set_outcome: { who: each_person, outcome: stranded } }
```

## 例: 獣を出来事に置き換える

今の廃坑の山村では、北の坑道で物音が積もると「坑道の獣」が現れる (モンスター)。モンスターは #1971 で設計するので、ここでは出来事に置き換える。

```yaml
happenings:
  beast_north_attacks:
    condition:
      all_of:
        - flag_is_raised: beast_north_awake
        - people_count_at_least:
            people: { where: { is_at_spot: { who: each_person, spot: north_tunnel } } }
            count: 1
      failure_text: 北の坑道は静かだ。
    once: false
    effect:
      for_everyone:
        people: { where: { is_at_spot: { who: each_person, spot: north_tunnel } } }
        effect: { damage: { who: each_person, amount: 8 } }
    notice:
      sound_from: { spot: north_tunnel, sound: { loudness: very_loud, clear: 暗がりから何かが唸り、飛びかかってきた。, muffled: 坑道の奥で獣のような唸り声がした。 } }
```

## 例: 登場人物

世界に渡す部分と、Being に渡す人柄 (`being:`) を分けて書く。読み込む側は `being:` を世界の宣言に入れず、Being の入口 (ステージ 8) に渡す。

```yaml
characters:
  haru:
    appearance: 測量具を背負った年かさの男
    spawn_spot: north_shaft_head
    initial_items: [lamp, fuel_can, lamp_oil, lamp_oil]
    initial_held: [lamp]
    initial_groups: [team_north]
    knows_at_start: [mio]
    being:
      name: ハル
      first_person: 私
      persona: あなたはハル、山の測量を請け負う調査隊の隊長で、落ち着いた男。……
      objective: ミオと二人そろって、坑道の奥の昇降機で外へ出る。
```

## 決めたこと (#2052)

1. 条件と効果の節は、種類を鍵にした地図で書く (`kind:` の欄は使わない)。短く書けて、人と LLM が読みやすいため
2. 1 つのシナリオは 1 ファイル。共通の部品だけを `includes:` で取り込む
3. 名前は地図の鍵に書く (`id:` の欄は使わない)
4. `includes:` は、地図を鍵ごとに重ね、シナリオに書いた鍵だけを置き換える
5. Being に渡す人柄は、登場人物の `being:` の中に書く

## 決めたこと (#2057)

1. 書かなかった欄の既定は、共通の部品の `defaults:` に宣言の種類ごとに書く。「無い」を表す型は `null`
2. `PassageDeclaration` の `states` と `ItemSpecDeclaration` の `hands_needed` は型の既定を外し、`defaults:` で埋める
3. 出来事を読む条件は `HappeningId` を、集団の決定を始める効果は決定と `voters` / `choices` を持つ。自分を読む出来事 (5 tick ごとに襲う) と、決まらなければもう一度投票する決定を書けるようにするため
4. 登場人物の `being:` は世界の宣言に入れず、地図のまま `LoadedScenario.beings` に返す。地図でなければ `DesignFlaw`
5. 誤りの場所に、どのファイルに書いたかを持たせ、誤りの文にもファイルの名前を出す。シナリオを作る LLM が、どこを直せばよいかを分かるようにするため
6. `time` の `day_night` と `weather` は、「無い」ことも `null` で書かせる。欄が無ければ `DesignFlaw`
