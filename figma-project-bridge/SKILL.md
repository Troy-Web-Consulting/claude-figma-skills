---
name: figma-project-bridge
description: >
  Bridge non-Figma inputs into Figma. Two modes: (1) Spec Cross-Reference —
  analyze a technical spec against existing Figma components, producing
  REUSE/EXTEND/CREATE verdicts. (2) Token Sync — bidirectional sync between
  code tokens (CSS, Tailwind, JSON) and Figma variables. Triggers on:
  "what does this spec mean for Figma," "do we already have components for this,"
  "sync tokens," "push CSS vars to Figma," "pull tokens from Figma," or
  starting design work from a spec/requirements doc.
---

# Figma Project Bridge

Bridges non-Figma inputs (specs, code tokens, CSS) into Figma — either as analysis (cross-referencing a spec against existing components) or as writes (pushing tokens into Figma variables).

**Prerequisite:** Run `figma-workspace` first to gather context about the target Figma file.

**Project context:** Both modes pull project context from the directory specified in `.claude/figma-config.json` > `contextDir` — fileKeys, design decisions, prior specs, token formats. See `figma-workspace` Step 4 for config details.

---

## Mode 1: Spec Cross-Reference

Augments a spec analysis with live Figma cross-references. Answers the question: "what can we reuse vs. what needs new design work?"

### When to use

- User shares a technical spec and asks what it means for Figma
- Starting design work from requirements and wanting to know what exists
- After `design-brief` or `spec-design-interpreter` produces a design companion

### Workflow

#### Step 1: Produce design companion

Follow the `spec-design-interpreter` workflow:
1. Identify the key decision that most affects design scope
2. Summarize technical changes (before/after)
3. Identify confirmed screens and screens implied
4. Surface open questions (blocking vs. important)
5. List next steps

If a design companion already exists (from a prior `spec-design-interpreter` or `design-brief` run), use it as input instead of re-analyzing.

#### Step 2: Extract queryable terms

From the companion doc, pull:
- **Component types** mentioned or implied (drawer, form, modal, table, card, sidebar)
- **Interaction patterns** (progressive disclosure, multi-step wizard, inline edit, drag-and-drop)
- **Data types** implied (user list, role selector, org picker, date range)

Map these to search queries for Figma.

#### Step 3: Run figma-workspace context gathering

Use `search_design_system` with each queryable term. Pull visual specs (`get_design_context`) for matches.

#### Step 4: Produce cross-reference

For each screen/component the spec implies, assign a verdict:

| Verdict | Meaning | Action |
|---|---|---|
| **REUSE** | Existing component handles this | Name the component, key, and which variant to use |
| **EXTEND** | Existing component needs a new variant or property | Describe what needs adding |
| **CREATE** | Nothing exists — new component needed | Flag for human design decision |
| **UNCLEAR** | Spec is ambiguous about what's needed | Surface as blocking question |

#### Step 5: Append to companion doc

Add a `## Figma Cross-Reference` section:

```markdown
## Figma Cross-Reference

| Spec Implies | Verdict | Component | Action Needed |
|---|---|---|---|
| User create form | REUSE | Drawer v2 + Drawer Form Field | Configure for user fields |
| Role selector | EXTEND | Drawer Form Field | Add Radio Card variant |
| Primary org picker | CREATE | — | New component, needs design |
| Notification preferences | UNCLEAR | — | Spec doesn't define interaction model |
```

Optionally include: list of Figma component keys ready for instantiation.

### Escalation rules

- **REUSE / EXTEND** = high confidence → can proceed to building
- **CREATE** = flag for human design decision before building. Do not invent components.
- **UNCLEAR** = surface as blocking question in the companion doc. Do not assume.

---

## Mode 2: Token Sync

Bidirectional sync between code tokens and Figma variables. Read path (Figma → code) follows `design-token-bridge` patterns. Write path (code → Figma) is the new capability.

### When to use

- "Sync tokens" / "push CSS vars to Figma" / "pull tokens from Figma"
- Setting up a new Figma file with tokens from an existing codebase
- Auditing drift between code tokens and Figma variables
- After a rebrand or token update in code that needs to flow to Figma

### Read Path: Figma → Code

Follows `design-token-bridge` workflow:

1. **Ingest** — read Figma variables via `get_variable_defs` or `search_design_system`
2. **Resolve alias chains** — follow `VARIABLE_ALIAS` references to concrete values. Present full chain: `semantic → intermediate → primitive`
3. **Handle modes** — map Figma modes to breakpoints or themes. Present values for all modes side-by-side
4. **Convert units** — px → rem (base 16px). Show both values. Round rem to 4 decimal places
5. **Generate output** — CSS custom properties, Tailwind config, or reference docs

**CSS output structure:**
```css
/* Primitives */
:root { --color-brand-primary: #HEXVAL; }

/* Semantic (referencing primitives) */
:root { --color-heading-dark: var(--color-brand-primary); }

/* Responsive overrides */
@media (max-width: 768px) { :root { --font-size-heading-1: 3rem; } }
```

6. **Document alias map** — table or tree showing how semantic tokens resolve to primitives

### Write Path: Code → Figma

1. **Parse input** — supported formats:

| Format | Detection | Key parsing notes |
|---|---|---|
| CSS custom properties | `:root { --name: value; }` | Handle `var()` references as aliases |
| Tailwind config | `theme.extend.*` objects | Handle nested objects, `DEFAULT` keys |
| JSON (Style Dictionary) | `{ value, type }` structure | Handle `$value` references |
| JSON (Tokens Studio) | `{ value, type, description }` | Handle `{reference}` syntax |

See `references/token-formats.md` for detailed parsing rules.

2. **Map naming conventions:**

| CSS pattern | Figma variable type | Figma name |
|---|---|---|
| `--color-*` | COLOR | `color/[rest as slash-separated]` |
| `--spacing-*`, `--size-*` | FLOAT | `spacing/[rest]` or `size/[rest]` |
| `--font-family-*` | STRING | `font/family/[rest]` |
| `--font-size-*`, `--font-weight-*` | FLOAT | `font/size/[rest]` or `font/weight/[rest]` |
| `--radius-*`, `--border-radius-*` | FLOAT | `radius/[rest]` |
| `--shadow-*` | STRING | `shadow/[rest]` |

CSS kebab-case → Figma slash-separated: `--color-brand-primary` → `color/brand/primary`

See `references/mapping-rules.md` for the complete mapping table.

3. **Diff before writing:**

| Status | Meaning | Action |
|---|---|---|
| **MATCH** | Values identical | Skip — no action needed |
| **DRIFT** | Values differ | Flag for user decision: overwrite Figma / keep Figma / keep code |
| **NEW** | Token in code, not in Figma | Create in Figma |
| **ORPHAN** | Token in Figma, not in code | Flag for user decision: delete from Figma / keep / add to code |

4. **Preview** — always show the diff and get explicit approval before writing. Never silently overwrite.

5. **Write:**
   - Small sets (<100 tokens) → single `use_figma` call with batched `figma.variables.createVariable()` calls
   - Large sets → multiple `use_figma` calls following `figma-builder` batch patterns
   - Map CSS media queries or Tailwind screens to Figma variable modes

### Audit Mode (read-only)

Compare code tokens against Figma tokens without making changes:

```
Token Sync Audit — [Project Name]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

In sync:     47 tokens
Drifted:      3 tokens
  --color-brand-primary: code=#2563EB, figma=#3B82F6
  --spacing-lg: code=2rem, figma=1.5rem
  --font-size-h1: code=3rem, figma=2.5rem
Missing in Figma:  5 tokens
  --color-status-warning, --spacing-2xl, ...
Missing in code:   2 tokens
  color/brand/accent, spacing/inset/card
```

Also check for:
- Unused aliases (tokens that reference but are never referenced)
- Circular aliases
- Duplicate resolved values under different names
- Missing semantic tokens (primitives without semantic wrappers)
- Inconsistent naming patterns

---

## Project Context Integration

Both modes pull project context automatically from `contextDir`.

**Read `.claude/figma-config.json` to get `contextDir`:**

```json
{
  "contextDir": "docs/design-context"
}
```

Then load from that directory:
```
{contextDir}/
  → fileKeys (if not already in figma-config.json), design decisions,
    component conventions, prior specs, design companions, open questions
```

For universal Figma patterns (token architecture, MCP rules, agentic conventions):
```
figma-workspace/references/figma-mcp-patterns.md
```

If `contextDir` is not set, skip context loading and proceed from the registry and live Figma reads. `contextDir` can point to any directory — a project docs folder, a notes vault, a shared drive path.

---

## Relationship to claude.ai Skills

| Capability | claude.ai skill | This skill |
|---|---|---|
| Spec → companion doc | `spec-design-interpreter` | Mode 1 Step 1 (same workflow) |
| Figma cross-reference | — | Mode 1 Steps 2-5 (new) |
| Figma JSON → CSS/docs | `design-token-bridge` | Mode 2 read path (same workflow) |
| CSS/code → Figma variables | — | Mode 2 write path (new) |
| Token audit | `design-token-bridge` (partial) | Mode 2 audit mode (expanded) |

The claude.ai skills continue to work independently. This skill composes their workflows with live Figma MCP access.
