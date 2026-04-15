# Design System Rules — [Project Name]

This file is the **rules layer** of the Figma-skills three-file contract. Skills read it every invocation to understand naming, token scales, and architecture. Keep it short (target: 200–800 words) and opinionated — this is where "why" and taste live.

**Contract note:** Skills locate this file via `designDocPath` in `.claude/figma-config.json`. If this project's rules are split across multiple documents (e.g., `PRINCIPLES.md` + `TACIT_RULES.md`), this file can be a thin wrapper that references them — skills read whichever path is declared.

---

## Token Architecture

Describe the project's token tier structure. The default is a **two-layer model**:

- **Primitives** — raw values from the design system (palette, raw scale numbers). Components never reference these directly.
- **Semantic tokens** — the public API. Components reference these. Semantic tokens reference primitives.

If you use a three-tier model (primitive → semantic → component-scoped), document it here. State the *rule* that keeps the architecture coherent (e.g., "semantic tokens must reference primitives, never literal values").

---

## Component Naming

| Element | Convention | Example |
|---|---|---|
| Component sets | PascalCase, space-separated | `Drawer Form Field` |
| Sub-components | Slash namespacing | `Drawer/ProgressBar` |
| Variants | `Property=Value` pairs, comma-separated | `Type=Text, State=Default` |
| Layers | Semantic names describing role or content | `Body Content`, `Role Cards`, `ButtonRow` |

**Avoid:** `Container`, `Frame 1`, `Group 2`, `Rectangle 4`, or any auto-generated Figma name.

---

## Variable Naming

Variables use slash-separated paths: `category/subcategory/name`.

| Token type | CSS pattern | Figma variable name |
|---|---|---|
| Colors | `--color-brand-primary` | `color/brand/primary` |
| Spacing | `--spacing-lg` | `spacing/lg` |
| Font size | `--font-size-h1` | `font/size/h1` |
| Font weight | `--font-weight-bold` | `font/weight/bold` |
| Corner radius | `--radius-base` | `radius/base` |
| Shadow | `--shadow-card` | `shadow/card` |

CSS kebab-case maps to Figma slash-separated: `--color-brand-primary` → `color/brand/primary`.

---

## Corner Radius Scale

Declare the numeric values for the project's corner-radius scale. `figma-bind-variables` reads this when matching unbound numeric values to variables.

| Variable key | Value (px) | Variable name |
|---|---|---|
| `cornerXS` | 4 | `radius/xs` |
| `cornerSmall` | 8 | `radius/small` |
| `cornerBase` | 12 | `radius/base` |
| `cornerLarge` | 20 | `radius/large` |
| `cornerFull` | 100 (or any value > 10000) | `radius/full` |

> Figma stores "full" corner radius internally as 16777200. Any value > 10000 is treated as `cornerFull`.

---

## Spacing Scale (optional)

If the project has a named spacing scale, declare it here. Skills will match raw spacing values to tokens.

| Key | Value (px) | Variable |
|---|---|---|
| `tight` | 4 | `spacing/tight` |
| `small` | 8 | `spacing/small` |
| `base` | 16 | `spacing/base` |
| `large` | 24 | `spacing/large` |
| `xl` | 32 | `spacing/xl` |

---

## Page Structure

| Role | Default page name |
|---|---|
| Components | `Components` |
| Design system home | `Design System` |
| Flows / screens | `Flows` |

If your project uses different page names, declare them in `.claude/figma-config.json` under `componentsPage` and `knownPages`. Skills read the config, not this doc, for page routing.

---

## Layer Conventions

- Auto-layout containers: name by their role (`Header`, `Body`, `Footer`, `ButtonRow`).
- Slot containers: name by their content type (`Icon Slot`, `Label`, `Supporting Text`).
- Bounding boxes (invisible sizing vectors): prefix with underscore to signal infrastructure (`_bbox`, `_bounds`).
- Decorative elements: name by what they are (`Divider`, `Background`, `Shadow Layer`).

---

## Project-Specific Rules

Add any rules that are specific to this project and don't fit the categories above. Examples:

- **Forbidden imports** — e.g., primitives tier cannot import from patterns tier.
- **Required composition** — e.g., status components must use matched bg/text token pairs.
- **Responsive conventions** — e.g., components do not contain responsive breakpoints; consumers handle responsive layout.
- **Icon library** — e.g., lucide only; no `@heroicons`, `@mdi`, `font-awesome`.

The shorter this section, the better. If it grows past ~20 bullet points, split into a dedicated rules file and reference it.
