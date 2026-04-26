# Design System Strategy: The Elegance of Decay

## 1. Overview & Creative North Star

The Creative North Star for this design system is **"The Fractured Aristocrat."**

This system is built upon the tension between two opposing worlds: the timeless, suffocating elegance of a Meiji-era mansion and the violent, entropic collapse of a digital simulation. We move beyond "standard" horror tropes by rejecting clutter. Instead, we use aggressive negative space, intentional asymmetry, and high-end editorial layouts to create a sense of "Beautiful Prison." The UI should feel like a terminal being projected onto a silk-lined wall—refined, yet fundamentally broken.

### Breaking the Template

- **Asymmetric Gravity:** Layouts should never be perfectly centered. Weight should shift heavily to one side, leaving "dead zones" that suggest something is missing or corrupted.
- **Layered Temporal Friction:** We overlay clean, high-contrast serif typography (the past) with monospaced terminal data (the failing present).

---

## 2. Colors & Atmospheric Depth

Our palette is rooted in the `surface_container_lowest` (#0A0E14) to ground the experience in a void-like navy.

### The "No-Line" Rule

**Prohibit 1px solid borders for sectioning.** Boundaries must be defined solely through background color shifts. To separate a navigation rail from a main content area, transition from `surface` to `surface_container_low`. Lines are a "digital construct" that we only use when the system is "glitching." Otherwise, the UI should feel like seamless, physical layers of darkness.

### Surface Hierarchy & Nesting

Treat the UI as a series of stacked materials.

- **Base:** `surface_dim` for the primary environment.
- **Nesting:** Place a `surface_container_low` card inside a `surface_container_high` area to create "recessed" depth. This mimics the architectural molding of a mansion.
- **The Glass Rule:** For floating menus or "HUD" elements, use `surface_container_highest` at 60% opacity with a heavy `backdrop-filter: blur(12px)`. This creates a "frosted glass" effect that feels premium and ethereal.

### Signature Textures

Use a subtle linear gradient on primary CTAs transitioning from `primary` (#f4bd67) to `on_primary_container` (#a07323). This provides a metallic, gold-leaf sheen that flat colors cannot achieve, evocative of Kintsugi (repairing broken pottery with gold).

---

## 3. Typography: The Dual Narrative

The typography system is a dialogue between the "Mansion" (Noto Serif) and the "Machine" (Space Grotesk).

- **Display & Headlines (Noto Serif):** These are your "Editorial" voices. Use `display-lg` for chapter titles and key narrative moments. These should feel heavy, authoritative, and beautiful. Apply a 1px "chromatic aberration" shadow using `secondary` (#ffb4ac) and `primary` to suggest the text is vibrating or unstable.
- **UI & Data (Space Grotesk):** All interactive elements, menus, and system readouts use the monospace scale. This represents the "Collapsing Digital." It should be clean, cold, and spaced with a slightly wider `letter-spacing` (0.05rem) to mimic old terminal readouts.

---

## 4. Elevation & Tonal Layering

In this design system, shadows are not "lighting"; they are "voids."

- **The Layering Principle:** Depth is achieved by "stacking" the surface-container tiers. Never use a drop shadow on a standard card. Instead, use a `surface_container_highest` element on top of a `surface_dim` background to create a natural, "soft lift."
- **Ambient Shadows:** When a floating dialogue box is required, use an extra-diffused shadow: `box-shadow: 0px 20px 50px rgba(0, 0, 0, 0.6)`. The shadow color must be a tinted version of the background navy, never a neutral grey.
- **The "Ghost Border" Fallback:** If a container requires a boundary for legibility, use a "Ghost Border." Apply the `outline_variant` token at **15% opacity**. This creates a whisper of a container without breaking the "No-Line" rule.

---

## 5. Components

### Corner radius（リポジトリ標準）

初版ストラテジーでは「完全な角のないシャープさ」を志向していたが、タイトル画面の実装（Stitch 由来レイアウトとの折り合い・タッチ操作性）を経て、**シェル UI の正規値は `border-radius: 6px`** とする。ボタン、モーダル、プロローグのテキストパネル、話者チップなどに共通の `--ts-btn-radius: 6px` を使う。鋭さは **左縁 4px のアクセント**やフラットな面の重ねで表現し、大きなピル型（16px 超）の「安全な Web 2.0 感」だけは避ける。

### Buttons

- **Primary:** **6px** corner radius（上記）。Background: `primary` (#f4bd67). Text: `on_primary` (#432c00). On hover, the button should "glitch"—a 2px horizontal shift and a brief flash of `secondary` (#ffb4ac).
- **Tertiary:** No background. Text: `primary`. Underlined with a 1px dash that mimics a command-line cursor (`_`).

### Input Fields

- **The Terminal Style:** No box. Only a bottom-aligned `outline_variant` (20% opacity). The cursor should be a solid block of `primary` that blinks at a steady 500ms interval. Label text uses `label-sm` in `primary` above the input.

### Cards & Lists

- **Anti-Divider Rule:** Explicitly forbid 1px horizontal dividers. Use vertical white space from the spacing scale (e.g., 24px or 32px) to separate list items. For high-density lists, alternate background colors between `surface_container_low` and `surface_container_highest`.

### Status Chips

- **Warning/Error:** Use `secondary_container` with `on_secondary_container` text. The chip should have a "scanline" pattern overlay (a 1px repeating linear gradient) to denote it is a system alert.

---

## 6. Do's and Don'ts

### Do

- **Use Intentional Asymmetry:** If a title is top-left, place the navigation bottom-right. Create "tension" in the layout.
- **Embrace the Glitch:** Use `error` (#ffb4ab) as a rare, violent highlight color for critical failures or narrative horror spikes.
- **Leverage Negative Space:** Let the `surface_container_lowest` breathe. High-end design is defined by what you *don't* fill.

### Don't

- **Avoid "friendly" roundness:** Do not use large pill radii or superellipse shells that read as generic product UI. **Canonical shell radius is 6px** in this codebase—not 0px (too harsh for compositing) and not 16px+ (too soft).
- **No "Web 2.0" Gradients:** Avoid generic vibrant gradients. Only use the "Kintsugi" gold gradient or tonal navy-to-navy shifts.
- **No Standard Icons:** Avoid generic filled icons. Use thin-stroke (1px or 1.5px) "technical" icons that look like blueprint symbols.

### Accessibility Note

While we lean into horror aesthetics, the `on_surface` (Cold White) must maintain a 7:1 contrast ratio against `surface` containers for all primary narrative text. The "Collapsing Digital" must remain legible to the prisoner.

---

## 実装メモ（リポジトリ）

- **トークン:** `frontend/src/title/TitleScreen.css` の `--ts-*`（`--ts-btn-radius: 6px` を含む）。
- **タイトル:** 同ファイル（Stitch 由来ヒーロー＋`.ts-btn` ナビ）。
- **プロローグ:** `frontend/src/prologue/PrologueScreen.css` — テキストパネルはガラス（背景のみ透過、`blur(12px)`）、本文は長文可読性のため **Segoe UI / system-ui 系サンセリフ**（`on_surface` 相当・不透明度 1）。ヒント・操作は Space Grotesk。上部はタイトルと同型の `.prologue-ts-btn`。
- **共通ゲームUI:** `frontend/src/ui/GameUi.tsx` / `GameUi.css` — 新規画面はまず `GameScreenBackground`, `GameChrome`, `GameButton`, `GameFrameButton`, `GamePanel`, `GameWorldBadge` を使い、背景レイヤ、戻るボタン、テレメトリ、金CTA、ガラスパネル、選択中ワールド表示を画面間で揃える。個別画面CSSは配置と固有演出だけを持つ。

本ファイル（`DESIGN.md`）がデザインストラテジーの正本。索引は [README.md](./README.md)。
