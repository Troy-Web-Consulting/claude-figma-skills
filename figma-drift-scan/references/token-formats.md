# Token Format Parsing Rules

How to parse each supported token format for the write path (code → Figma).

---

## CSS Custom Properties

**Detection:** File contains `:root {` with `--` prefixed properties.

**Parsing:**
```css
:root {
  --color-brand-primary: #2563EB;
  --color-text-default: var(--color-brand-dark);
  --spacing-sm: 0.5rem;
  --font-size-body: 1rem;
  --font-family-heading: "Cabinet Grotesk", sans-serif;
}
```

**Rules:**
- Strip `--` prefix for Figma name generation
- `var(--name)` references → create as Figma alias (VARIABLE_ALIAS)
- `#hex` values → COLOR type
- `rem`/`em`/`px` values → FLOAT type (convert to px: rem * 16)
- Quoted strings → STRING type
- `rgb()`/`rgba()`/`hsl()` → COLOR type (convert to hex)
- Comments (`/* ... */`) → variable description in Figma

**Media query handling:**
```css
@media (max-width: 768px) {
  :root {
    --font-size-h1: 2.5rem;
  }
}
```
→ Create a Figma mode named after the breakpoint (e.g., "Mobile") and set the value there.

---

## Tailwind Config

**Detection:** File exports `theme` or `theme.extend` object.

**Parsing:**
```js
module.exports = {
  theme: {
    extend: {
      colors: {
        brand: {
          primary: '#2563EB',
          dark: '#1E40AF',
          DEFAULT: '#2563EB',  // maps to just "brand"
        }
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
      fontSize: {
        'display': ['4rem', { lineHeight: '1.1' }],
      }
    }
  }
}
```

**Rules:**
- Nested objects → slash-separated Figma names: `colors.brand.primary` → `color/brand/primary`
- `DEFAULT` key → parent name without suffix: `colors.brand.DEFAULT` → `color/brand`
- Array values (fontSize) → first element is size, second is config object
- String values with rem/px → FLOAT type
- Hex values → COLOR type
- Tailwind's `screens` config → Figma modes

---

## Style Dictionary JSON

**Detection:** Objects have `{ value, type }` or `{ $value, $type }` structure.

**Parsing:**
```json
{
  "color": {
    "brand": {
      "primary": {
        "value": "#2563EB",
        "type": "color",
        "description": "Primary brand color"
      },
      "dark": {
        "value": "{color.brand.primary}",
        "type": "color"
      }
    }
  }
}
```

**Rules:**
- Object path → Figma name: `color.brand.primary` → `color/brand/primary`
- `{reference.path}` syntax → Figma VARIABLE_ALIAS
- `type` field maps directly: `color` → COLOR, `dimension` → FLOAT, `fontFamily` → STRING
- `description` field → Figma variable description
- `$value`/`$type` (DTCG format) treated identically to `value`/`type`

---

## Tokens Studio JSON

**Detection:** Objects have `{ value, type, description }` with Tokens Studio conventions.

**Parsing:**
```json
{
  "colors": {
    "brand-primary": {
      "value": "#2563EB",
      "type": "color",
      "description": "Primary brand"
    },
    "text-heading": {
      "value": "{colors.brand-primary}",
      "type": "color"
    }
  },
  "spacing": {
    "sm": {
      "value": "8",
      "type": "spacing"
    }
  }
}
```

**Rules:**
- Same as Style Dictionary with these additions:
- `{group.name}` curly brace syntax → alias reference
- `spacing` type → FLOAT
- `borderRadius` type → FLOAT
- `fontFamilies` type → STRING
- `fontWeights` type → FLOAT (map named weights: Regular=400, Medium=500, SemiBold=600, Bold=700)
- Token sets → Figma variable collections
- Token set groups → Figma modes within a collection

---

## Common Gotchas

- **rem to px conversion:** Always use base 16px unless the project specifies otherwise. `1rem = 16px`
- **Alias chains:** A token may reference another token that references another. Resolve the full chain before deciding if it's an alias or a concrete value in Figma
- **Naming collisions:** CSS `--color-brand` and Tailwind `colors.brand.DEFAULT` may map to the same Figma name. Detect and flag duplicates before writing
- **Mode mismatches:** CSS has media queries, Tailwind has screens, Figma has modes. These are conceptually equivalent but the mapping isn't always 1:1
- **String vs number:** `"16"` (string) vs `16` (number) — Figma variables are type-strict. Parse appropriately
