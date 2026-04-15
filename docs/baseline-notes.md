# Phase 0 Baseline — Pre-Refactor State

Captured 2026-04-15 via static analysis + mye-ui artifact inspection. Proving ground: `~/Code/mye-ui`.

This doc is the measurement surface for the refactor — the post-refactor state will be compared against it to validate the ~60% token-reduction target and to confirm the three-file contract works.

---

## Skill surface today

### Repo skills (5)

| Skill | SKILL.md lines | References (lines) | Est. prompt tokens* | Script helpers |
|---|---|---|---|---|
| `figma-workspace` | 345 | 574 (5 files) | ~23k | none |
| `figma-builder` | 216 | 535 (2 files) | ~19k | none |
| `figma-project-bridge` | 245 | 284 (2 files) | ~13k | `figma-token-parse.py` (516 lines) |
| `figma-bind-variables` | 520 | 0 | ~10k | `figma-bind-prep.sh` (416 lines) |
| `figma-swap-library-to-local` | 210 | 0 | ~4k | `figma-idmap-inject.sh` (174 lines) |
| **Total** | **1536** | **1393** | **~69k** | 3 scripts, 1106 lines |

*Rough estimate at ~4 chars/token, assuming references loaded per skill's instructions.

### mye-ui project-local skills (9)

Located in `~/Code/mye-ui/.claude/skills/`. Four are repo symlinks, five are project-native prototypes that heavily overlap with the refactor plan.

| Skill | Lines | Prototype of | Overlap with refactor |
|---|---|---|---|
| `figma-workspace` (symlink) | 345 | — | direct |
| `figma-builder` (symlink) | 216 | — | direct |
| `figma-project-bridge` (symlink) | 245 | — | direct |
| `figma-bind-variables` (symlink) | 520 | — | direct |
| `figma-swap-library-to-local` (symlink) | 210 | — | direct |
| **`design-audit`** | 343 | `figma-design-audit` (Phase 5) | High — 9 grep-based passes, dispatches subagent, writes structured report. Reference rules = `PRINCIPLES.md` + `TACIT_RULES.md`. |
| **`design-system-sync`** | 300 | `figma-design-sync` (Phase 6) + part of `figma-drift-scan` (Phase 3) | High — bidirectional Figma↔code token sync with 4 operation modes. Parity report pattern matches planned drift-manifest. |
| **`figma-page-audit`** | 1075 | Not in plan — but implements the triad pattern informally | Very high — four-phase artifact pipeline (Collect→Enrich→Analyze→Report), Fast Path/Fallback, `bindIgnoreRules`, variable cache. The richest prototype by far. |
| `component-build` | 900 | Not mapped (orthogonal) | Low — bidirectional Vue↔Figma component sync. Keep as-is; not part of the triad refactor. |

**The big signal:** `design-audit`, `design-system-sync`, and `figma-page-audit` are already doing what the refactor plans to build — just in 100% LLM prose with heavy mechanical work (regex, diffing, alias resolution) in the main thread.

---

## The rules layer already exists (unofficially)

mye-ui has a rules file, split across two docs — neither of which is referenced by the repo skills today:

| File | Lines | Role |
|---|---|---|
| `mye-ui/PRINCIPLES.md` | 259 | Architecture/why: token tiers, anti-patterns, component layers |
| `mye-ui/TACIT_RULES.md` | 195 | Conventions/how: font assignment, spacing scale, interaction states |

**Total: ~23KB, 454 lines.** The plan targets 200–800 words for `design.md`. These are larger — either they need trimming (the core rules are smaller than the prose around them), or the contract accepts two documents (architecture + tacit).

Referenced by: `design-audit/SKILL.md`, `design-system-sync/SKILL.md`, `component-build/SKILL.md`. **Not referenced by** any repo skill — the repo defaults to `figma-workspace/references/conventions.md` (80 lines, minimal).

### Migration implication

Phase 1 of the plan says "move `conventions.md` to `templates/design.md`." But mye-ui's effective design.md is `PRINCIPLES.md` + `TACIT_RULES.md`. The migration for mye-ui is:
- Option A: leave them split; point `designDocPath` at a wrapper `docs/design.md` that references both.
- Option B: merge + trim to one `design.md`; keep PRINCIPLES/TACIT_RULES as deeper refs.
- **Recommended: Option A initially** — zero churn on the existing docs. Revisit consolidation after the refactor stabilizes.

---

## The registry is richer than documented

Current `docs/figma-registry.json` in mye-ui (68KB, scanned 2026-04-01):

```
meta            {fileKey, branchKey, scanDate, page, note}
sections        [5 items — page sections on Components page]
components      [103 items — {id, key, name, section, type}]
variables       {collections, color, corners, spacing, _note}
versionMap      {5 deprecation→current mappings with migration notes}
bindIgnoreRules [triage exceptions — consumed by figma-page-audit]
```

The repo README documents only `meta` + per-component entries. In practice, the registry has evolved to hold:
- **`versionMap`** — component deprecation history (critical for `figma-swap-library-to-local`)
- **`bindIgnoreRules`** — persistent audit triage (consumed by `figma-page-audit`)
- **`sections`** — page layout metadata
- **`variables.collections`** — variable collection IDs (saves rediscovery)

### Migration implication

The refactor's JSON Schema for `figma-registry.json` should include all six top-level keys, not the stripped-down version in the current README. Derive the schema from mye-ui's actual shape.

---

## Deterministic work currently in the LLM main thread

From inspection of the 5 repo skills + 3 prototype local skills. Each item is a candidate for demotion per the four-question rubric (idempotent / structured I/O / no taste / single-pass).

| Operation | Where it lives today | Primitive candidate | Est. token cost per run |
|---|---|---|---|
| Token format parse (CSS/Tailwind/JSON/YAML) | `figma-token-parse.py` already exists | `parse_tokens.py` — port | already ~0 LLM tokens ✓ |
| Alias chain resolution | `figma-project-bridge` prose + inline per-reference | `resolve_aliases.py` | ~2–3k |
| Token diff (Figma vs code) | `design-system-sync` prose | `diff_tokens.py` | ~3–4k |
| Hex matching to variables (Phase 4b of bind) | `figma-bind-variables` prose + shell | `match_colors.py` | ~1–2k |
| Unbound property scan | `figma-page-audit` Phase 1 Mode 2 (JS-in-`figma_execute`) | `scan_unbound.py` + reusable JS | mostly offloaded ✓ |
| Grep-based rule checks (9 passes of `design-audit`) | `design-audit` prose — pure regex | `audit.py` with a rules registry | ~5–8k |
| CSS variable generation from registry | `design-system-sync` Figma→Code mode | `generate_css.py` (Jinja template) | ~1–2k |
| Variable ID injection into bind scripts | `figma-bind-prep.sh` | `prep_bind.py` — port | already ~0 ✓ |
| Swap script generation | `figma-idmap-inject.sh` | `prep_idmap.py` — port | already ~0 ✓ |

**Estimated total deterministic-in-LLM work per full run: ~12–19k tokens.** This is the primary savings target.

---

## Artifact conventions (mye-ui as reference)

Already-established artifact paths — useful input for defining the config schema.

| Artifact | Path | Producer | Consumer |
|---|---|---|---|
| Registry | `docs/figma-registry.json` | `figma-workspace` (manual) | all skills |
| Audit reports | `docs/audits/{name}-{raw\|analysis\|report}.{json\|md}` | `figma-page-audit` | humans; historical comparison |
| Audit tracker | `docs/audits/AUDIT_TRACKER.md` | `figma-page-audit` | humans |
| Variable cache | `docs/audits/variable-cache.json` | `figma-page-audit` | `figma_execute` scripts |
| Audit report (rule audit) | `docs/audit-report.md` | `design-audit` | humans |
| Parity report | `docs/parity-report.md` | `design-system-sync` | humans |
| Production coverage | `docs/production-coverage.md` | `design-system-sync` | humans |
| Component doc template | `docs/COMPONENT_DOC_TEMPLATE.md` | `component-build` | component docs |
| Screen schema | `docs/screen-schema.json` | external | screen work |
| Token CSS | `src/styles/tokens/{colors,typography,spacing,components}.css` | `design-system-sync` Figma→Code | app |
| Tailwind theme | `src/styles/tailwind-theme.css` | `design-system-sync` | app |

### Migration implication

The new `figma-config.json` schema should codify these paths (with sensible defaults). Add fields: `auditsDir`, `driftManifestPath`, `auditReportPath`, `parityReportPath`, `tokensDir`, `tailwindThemePath`. The prototype skills already expect them — the refactor just formalizes the contract.

---

## Estimated token footprint (pre-refactor, per operation)

Rough estimates. Real measurement requires live sessions — these are the numbers to beat.

### Full design-token pull (`design-system-sync` Figma → Code)

| Step | Tokens |
|---|---|
| Load `figma-workspace` + `figma-project-bridge` | ~25k |
| `get_variable_defs` + `search_design_system` responses | ~25k |
| Read 5 token CSS files | ~3k |
| Diff + alias resolution in-thread | ~5k |
| CSS generation (prose) | ~2k |
| Write parity report | ~3k |
| **Total** | **~63k** |

### Variable binding pass (`figma-bind-variables` Phases 1–4)

| Step | Tokens |
|---|---|
| Load `figma-workspace` + `figma-bind-variables` | ~30k |
| Phase 1 + 2 `use_figma` responses | ~15k |
| Phase 3 scan responses | ~10k |
| Phase 4 binding prose + script injection | ~8k |
| **Total** | **~63k** |

### Page audit (`figma-page-audit` — Desktop Bridge fast path)

| Step | Tokens |
|---|---|
| Load `figma-workspace` + `figma-page-audit` | ~30k |
| `figma_lint_design` + `figma_execute` (already clustered) | ~5k |
| Phase 2 enrichment (local) | ~2k |
| Phase 3 analysis + report | ~4k |
| **Total** | **~41k** |

Note: `figma-page-audit` is already the lean one because it offloads work to scripts via `figma_execute`. This is the direction the refactor should push all skills.

### Design audit (`design-audit` — 9 grep passes)

| Step | Tokens |
|---|---|
| Load `figma-workspace` (not strictly needed, often loaded anyway) + `design-audit` | ~30k |
| 9 grep passes across `src/components/**/*.vue` | ~15k |
| Finding classification + report generation | ~8k |
| **Total** | **~53k** |

---

## Friction points observable from artifacts

Not actively broken, but visible in how the skills have been used:

1. **Repeated registry regeneration.** Scan date on mye-ui registry is 2026-04-01 — two weeks stale at time of this baseline. No automation nudges a refresh; regeneration is manual and expensive.
2. **`bindIgnoreRules` invented in the registry** by `figma-page-audit` but not documented in the repo schema. Prototype features leak into production registries without a formal home.
3. **Audit reports have two formats** — markdown (for humans) + JSON (for machine re-reading). This is the structured-output pattern at the artifact layer. Good — keep it.
4. **`design-audit` and `design-system-sync` both dispatch subagents** via `Agent(mode="bypassPermissions")` to isolate context. This is a workaround for the "loading a fat skill burns context" problem. The thin-SKILL + primitive-scripts refactor addresses the root cause.
5. **`figma-page-audit` references `figma_execute` scripts** as a custom Plugin API runtime. This is essentially an ad-hoc primitive layer — formal primitives would replace most of it.

---

## Proto-to-plan mapping

How the mye-ui prototypes inform each refactor phase.

| Refactor target | Prototype to lift from | Lift strategy |
|---|---|---|
| `figma-drift-scan` (Phase 3) | `design-system-sync` Full Parity Check mode | Extract parity logic → `diff_tokens.py` primitive + thin skill |
| `figma-design-audit` (Phase 5) | `design-audit` (all 9 passes) | 9 passes → rules registry in `audit.py`; skill becomes dispatcher |
| `figma-design-sync` (Phase 6) | `design-system-sync` Figma→Code + Code→Figma modes | Reuse token CSS generators + Figma variable writers, wrapped in thin skill |
| `figma-spec-crossref` (Phase 4) | `figma-project-bridge` Mode 1 | Lift prose verbatim into new skill |
| Registry schema | mye-ui's actual registry | Derive JSON Schema from real shape, not README |
| `design.md` template | `PRINCIPLES.md` + `TACIT_RULES.md` | Write an example template pointing to both; don't force consolidation |
| `scan_unbound.py` primitive | `figma-page-audit` Phase 1 Mode 2 `figma_execute` JS | Extract the JS as a reusable Plugin API snippet; Python wraps it |
| Artifact pipeline pattern | `figma-page-audit`'s four-phase Collect→Enrich→Analyze→Report | Adopt as the pattern for every audit-like skill |

### What this means for the phasing

- **Phase 3 (drift-scan)** gets a big head start: `design-system-sync`'s parity logic + the existing `figma-token-parse.py` get us ~70% of the way.
- **Phase 5 (design-audit)** lifts 9 working grep-based rule passes directly. The refactor is mostly mechanical.
- **Phase 6 (design-sync)** is the most at-risk for scope creep — `design-system-sync` has 4 modes. Decide early which modes make v1.
- **`figma-page-audit` is not in the plan, but should be.** Add a Phase 4.5 to fold it into the triad (likely as `figma-unbound-scan` + reused primitives).

---

## Measurement plan

To validate the refactor's ~60% reduction target, re-run these scenarios post-refactor:

1. Full token pull: Figma → Code sync of mye-ui's ~5 token files.
2. Variable binding: bind 10–20 unbound fills/strokes on a Figma page.
3. Page audit: audit one non-trivial page (e.g., the user-details flow).
4. Design-system audit: run against current mye-ui source.

For each, capture:
- Total tokens consumed (prompt + completion)
- Time to completion
- Number of LLM round-trips

Target (per plan): ≥60% reduction. Stretch: 70% on full token-sync and page audit (the ops with most demotable work).

---

## Out-of-scope callouts

- **`component-build`** is orthogonal to this refactor and stays in mye-ui. If the triad contract proves useful, revisit later.
- **`figma-page-audit`** should be added to the refactor scope as a formal repo skill (currently only in mye-ui). Will flag as an addendum PR after the main triad lands.
- **Subagent-dispatch pattern** (`design-audit`, `design-system-sync`, `component-build` all use it) is a valid context-isolation strategy, but complicates the thin-SKILL pattern. Decide per-skill whether to preserve it or collapse into main-thread orchestration.
