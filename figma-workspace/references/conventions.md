# Figma Design System Conventions

Default conventions for component naming, variable naming, layer structure, and token scales. These apply when no project-specific overrides are configured.

**Override mechanism:** Set `conventionsPath` in `.claude/figma-config.json` to point to a project-specific conventions doc. When present, that file takes precedence over this one for all conventions. Operational skills defer to whichever source is active — they do not hardcode conventions.

---

## Component Naming

| Element | Convention | Example |
|---|---|---|
| Component sets | PascalCase, space-separated words | `Drawer Form Field` |
| Sub-components | Slash namespacing | `Drawer/ProgressBar` |
| Variants | `Property=Value` pairs, comma-separated | `Type=Text, State=Default` |
| Layers | Semantic names describing role or content | `Body Content`, `Role Cards`, `ButtonRow` |

**Avoid:** `Container`, `Frame 1`, `Group 2`, `Rectangle 4`, or any auto-generated Figma name.

---

## Variable Naming

Variables use slash-separated paths: `category/subcategory/name`

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

Default scale used by `figma-bind-variables` when matching numeric values to variables:

| Variable key | Value | Variable name (default) |
|---|---|---|
| `cornerXS` | 4px | `radius/xs` |
| `cornerSmall` | 8px | `radius/small` |
| `cornerBase` | 12px | `radius/base` |
| `cornerLarge` | 20px | `radius/large` |
| `cornerFull` | 100px / 16777200 | `radius/full` |

> Figma stores "full" corner radius internally as 16777200. Any value > 10000 is treated as `cornerFull`.

**Project override:** If your project uses different radius values or variable names, define the `getCornerVar` mapping in your conventions doc and reference it when running Phase 4d of `figma-bind-variables`.

---

## Page Structure

Default page name for component definitions: `Components`

Override with `componentsPage` in `.claude/figma-config.json`. Skills that scan or bind components read this config field rather than assuming the page name.

---

## Token Architecture (Three-Tier)

1. **Primitive** — raw values (`color/palette/blue-600: #2563EB`)
2. **Semantic** — purpose-named aliases (`color/brand/primary: → color/palette/blue-600`)
3. **Component** — scoped overrides, used sparingly (`button/background: → color/brand/primary`)

Semantic tokens should always reference primitives, never literal values. Primitives should never appear directly in component definitions.

---

## Layer Conventions

- Auto-layout containers: name by their role (`Header`, `Body`, `Footer`, `ButtonRow`)
- Slot containers: name by their content type (`Icon Slot`, `Label`, `Supporting Text`)
- Bounding boxes (invisible sizing vectors): name `_bbox` or `_bounds` — prefix with underscore to signal infrastructure
- Decorative elements: name by what they are (`Divider`, `Background`, `Shadow Layer`)
