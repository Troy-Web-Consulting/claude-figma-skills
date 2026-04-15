# CSS to Figma Variable Mapping Rules

How to translate code token names and values into Figma variable names and types.

---

## Name Mapping

CSS kebab-case → Figma slash-separated. Strip the `--` prefix.

| CSS Property | Figma Name | Example |
|---|---|---|
| `--color-brand-primary` | `color/brand/primary` | |
| `--color-text-heading-dark` | `color/text/heading-dark` | |
| `--spacing-sm` | `spacing/sm` | |
| `--spacing-inset-card` | `spacing/inset/card` | |
| `--size-icon-lg` | `size/icon/lg` | |
| `--font-family-heading` | `font/family/heading` | |
| `--font-size-body` | `font/size/body` | |
| `--font-weight-bold` | `font/weight/bold` | |
| `--font-line-height-tight` | `font/line-height/tight` | |
| `--radius-sm` | `radius/sm` | |
| `--border-radius-card` | `radius/card` | Note: `border-radius` prefix normalizes to `radius` |
| `--shadow-sm` | `shadow/sm` | |
| `--elevation-modal` | `elevation/modal` | |
| `--z-index-modal` | `z-index/modal` | |
| `--opacity-disabled` | `opacity/disabled` | |
| `--duration-fast` | `duration/fast` | |
| `--easing-ease-out` | `easing/ease-out` | |

### Prefix → Figma Variable Collection

Group variables into collections by their top-level prefix:

| Prefix | Collection Name |
|---|---|
| `color` | Colors |
| `spacing`, `size` | Sizing |
| `font` | Typography |
| `radius` | Border |
| `shadow`, `elevation` | Effects |
| `z-index` | Z-Index |
| `opacity` | Opacity |
| `duration`, `easing` | Motion |

---

## Type Inference

| CSS Value Pattern | Figma Type | Conversion |
|---|---|---|
| `#hex` (3, 4, 6, or 8 digits) | COLOR | Parse to {r, g, b, a} |
| `rgb(r, g, b)` / `rgba(r, g, b, a)` | COLOR | Parse to {r, g, b, a} |
| `hsl(h, s%, l%)` / `hsla(h, s%, l%, a)` | COLOR | Convert to {r, g, b, a} |
| `Npx` | FLOAT | Use value directly |
| `Nrem` | FLOAT | Multiply by 16 (or project base) |
| `Nem` | FLOAT | Multiply by parent size or 16 |
| `N%` | FLOAT | Divide by 100 |
| `N` (bare number) | FLOAT | Use value directly |
| `"string"` or `'string'` | STRING | Strip quotes |
| `font-family, fallback` | STRING | Keep full stack |
| `var(--name)` | VARIABLE_ALIAS | Resolve to target variable ID |
| `Ns` / `Nms` | FLOAT | Convert to ms if in seconds |

---

## Alias Handling

When a CSS value uses `var()`, create a Figma alias instead of a concrete value:

```css
:root {
  --color-brand-primary: #2563EB;        /* → concrete COLOR value */
  --color-action-default: var(--color-brand-primary);  /* → VARIABLE_ALIAS to color/brand/primary */
}
```

**Resolution order:**
1. Parse all concrete values first
2. Then resolve `var()` references — the target must exist before you can alias to it
3. For chained aliases (`var(--a)` where `--a` is also `var(--b)`), Figma handles the chain automatically — just alias to the immediate target

---

## Mode Mapping

| Code Concept | Figma Equivalent |
|---|---|
| CSS `@media (max-width: 768px)` | Mode: "Mobile" |
| CSS `@media (prefers-color-scheme: dark)` | Mode: "Dark" |
| CSS `.dark` / `[data-theme="dark"]` | Mode: "Dark" |
| Tailwind `screens.sm` / `screens.md` / `screens.lg` | Modes by breakpoint name |
| Style Dictionary `$themes` | Modes by theme name |
| Tokens Studio token sets | Modes by set name |

**Default mode:** The `:root` or base values map to the first (default) mode.

---

## Semantic vs Primitive Layer

When writing to Figma, maintain the three-tier hierarchy:

| Tier | CSS Pattern | Figma Collection |
|---|---|---|
| Primitive | `--color-blue-500: #3B82F6` | Primitives |
| Semantic | `--color-action-primary: var(--color-blue-500)` | Semantic |
| Component | `--button-bg: var(--color-action-primary)` | Component (optional) |

**Rules:**
- If the codebase has a clear primitive/semantic split, preserve it in separate collections
- If the codebase is flat (all tokens at one level), create as a single collection
- Never guess at semantic relationships — only create aliases where the code explicitly uses `var()`

---

## Project-Specific Overrides

Some projects use non-standard patterns. Check the project context directory (`contextDir` from `.claude/figma-config.json`) for:

- **Custom prefix:** e.g., `--twc-color-*` instead of `--color-*` → strip project prefix before mapping
- **Custom base font size:** e.g., 14px instead of 16px → adjust rem conversion
- **Collection naming:** project may have its own collection names
- **Naming convention:** project may use different separator (e.g., dots instead of hyphens in CSS)

The project context directory is authoritative for per-project conventions.
