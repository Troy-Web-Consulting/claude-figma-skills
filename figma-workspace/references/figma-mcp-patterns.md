# Figma MCP Patterns

Accumulated patterns from building, maintaining, and automating design systems. Covers the Figma-to-code pipeline, drift detection architecture, token strategy, CSS conventions, and agentic implementation workflows.

---

## Figma MCP

- **Two servers, different roles** — Figma exposes two MCP connection modes. The remote server (hosted endpoint, any seat/plan) handles API reads: design context, variables, screenshots, metadata. The desktop server (requires Figma app running locally) enables Dev Mode integration and write-adjacent features. For headless/CI pipelines, remote is the only option

- **Read tools are the foundation** — Four tools cover most implementation needs:
  - `get_design_context` — structured layout, component tree, token usage for a frame
  - `get_variable_defs` — variable/token definitions from the file
  - `get_screenshot` — visual snapshot for fidelity checks (ground truth)
  - `get_metadata` — file/node metadata and outline

- **Code Connect is plan-gated** — Code Connect (mapping Figma components to repo components with import paths and prop mappings) requires Organization or Enterprise plan. Professional plan gets all read tools but no Code Connect enrichment. This is the single biggest capability gap between plan tiers for agentic workflows

- **Rate limits are real constraints** — Figma enforces per-day and per-minute call limits that vary by plan and seat type (check current Figma developer docs for exact numbers). In practice, a design-heavy session can exhaust the daily limit in surprisingly few calls. Workaround: use design briefs and documentation as the source of truth for prompt writing rather than inspecting Figma files directly

- **Code-to-Figma requires desktop app** — Writing back to Figma (capturing rendered HTML into Figma frames) requires the desktop app running and a Dev or Full seat. This enables review loops: generate code from Figma, render in browser, capture back into Figma for comparison

- **Unrendered tokens are invisible** — Figma's visual-first pipeline means tokens that are defined but not applied to visible elements won't appear in MCP responses. The MCP server reports what's used in the design, not everything that exists in the file. Token auditing requires the Variables API or Tokens Studio export, not MCP reads

- **Token write options** — Token sync from code → Figma can be done via: `use_figma` with `figma.variables.createVariable()` (Plugin API, all plans), the Variables REST API (Enterprise only), or Tokens Studio plugin with GitHub sync (any plan). The `figma-project-bridge` skill covers the Plugin API write path.

- **Skills encode implementation discipline** — Figma's "Skills" are reusable instruction sets that sequence MCP tool calls. They don't add capabilities but encode repeatable workflows (implement design, create rules, map components). Use them to ensure agents follow the same process every time rather than improvising

- **Webhooks for event-driven sync** — Figma's REST API supports HTTP webhooks triggered by events like `LIBRARY_PUBLISH`. A design system team can treat every library publish as a "design contract change" and automatically trigger token generation, drift checks, or documentation regeneration on the code side. Highest-leverage automation pattern available without Enterprise

---

## Figma MCP Write Operations

Writing to the Figma canvas via `use_figma` (remote MCP, runs Plugin API JavaScript).

### Tool Selection

- **`use_figma` is the default write tool** — Figma's remote MCP server for all canvas creation and modification. Runs Plugin API JS without requiring the desktop app. Best for 1–4 high-level operations where context loading cost is acceptable
- **`figma-console:figma_execute` (Desktop Bridge) for granular or bulk writes** — Preferred when: (1) 5+ discrete write operations in a session — `use_figma` loads file context per call, figma-console's granular tools are significantly cheaper per-operation; (2) slot manipulation on pre-existing instances (ghost node problem); (3) post-write screenshot verification where cloud cache lag is unacceptable; (4) `use_figma` silently fails. Both tools execute the same Plugin API. Requires the Figma Desktop plugin to be running

### Before Building Anything

1. `search_design_system` — find existing components before creating new ones. Import matches via `importComponentByKeyAsync`/`importComponentSetByKeyAsync` instead of recreating
2. `get_variable_defs` — get token values from a relevant node
3. `get_design_context` — get visual specs + screenshot for reference
4. `get_metadata` — understand section and page structure

Never recreate a component that already exists in the library.

### Canvas Placement

- **Children use parent-relative coordinates** — Nodes inside sections, frames, and component sets position from (0,0) at the parent's origin. Never add the parent's absolute canvas x/y to child positions
- **Placement discipline for generated nodes** — LLM-generated nodes default to arbitrary coordinates, causing off-canvas placement or parent clipping. When adding children to a container, calculate position relative to existing siblings. Prefer appending to auto-layout parents over manual coordinate math
- **After `combineAsVariants`** — Resize the component set to wrap tightly, then audit child positions for overlap or clipping

### Component Property Binding

- `setProperties()` updates the stored value but text nodes won't visually respond unless `componentPropertyReferences` is bound on the component definition
- Always verify with `node.componentPropertyReferences` before assuming a property will take effect

### Slot API

- Clear component slot defaults BEFORE creating instances
- Ghost nodes from defaults persist on pre-existing instances and cannot be removed via the API
- Build content nodes before creating the instance that will contain them

### Auto-layout

- Set `layoutSizingHorizontal = "FILL"` AFTER appending to an auto-layout parent, not before
- Load required font variants via `figma.loadFontAsync()` before any text manipulation — missing fonts silently fail
- Set `primaryAxisSizingMode = "AUTO"` after children exist, not before

### Cross-file vs Cross-page

- **Cross-file copy** always creates an instance, never a component definition. There is no API or manual method to move a component definition between files
- **Cross-page reparenting within the same file** is supported via the Plugin API (`targetPage.appendChild(node)`)
- **Within-page moves** work via direct reparenting: `targetFrame.appendChild(node)`

---

## Figma Plugin Architecture

- **Two-thread sandbox** — Main thread: Figma document API (no DOM). UI thread: renders HTML/CSS/JS (no Figma API). Communication via `postMessage` only
- **UI must be async-first** — Every interaction: emit request → wait for main thread response → update UI
- **ClientStorage is async and local-only** — Scoped to the plugin and user's machine, not the file or team
- **Variable alias chains must be fully resolved** — The API returns the immediate value, which may be an alias. Drift comparison requires walking the full chain
- **No network access from main thread** — External API calls must happen from the UI thread and be serialized before crossing to main

---

## Drift Detection Philosophy

- **Decision capture over detection** — Detecting drift is easy. Capturing what the team decided to do about it (and why) is what prevents tools from being abandoned
- **Four decision states** — Ignore / Pin / Flag for fix / Restore. Each with rationale and author
- **Status-first UI** — Organize by decision status (Needs Review, Flagged, Ignored/Pinned, Healthy), not by data structure
- **Two-actor loop** — Agent scans and writes findings to a registry. Human reviews and decides. Neither owns the registry exclusively
- **Drift is not always a bug** — Intentional, temporary, or negligible deviations exist. Without recording distinctions, all deviation is treated as failure

---

## Token Architecture

- **Three-tier hierarchy** — Primitive (raw values) → Semantic (purpose-named aliases) → Component (scoped overrides, rarely needed)
- **Naming convention: category-property-variant-state** — e.g., `color-background-primary`, `color-text-disabled`, `space-inset-lg`. Avoid names that embed literal values
- **Namespace CSS tokens with a project prefix** — `--{project}-category-name` prevents collisions
- **The token pipeline** — Define (Figma Variables / Tokens Studio) → Export (JSON) → Transform (Style Dictionary) → Consume (code imports generated output)
- **Common failure modes** — Tokens defined but unused; primitives in semantic positions; flat structure with no semantic layer; no pipeline (manual copy-paste)

---

## CSS Design System Conventions

- **Colors as CSS variables only** — No hex values in code; everything maps to a token variable
- **Typography as class-based tokens** — Font weight, size, line height, and letter spacing defined together. Prevents typographic drift by making selective overrides impossible
- **Standardized REM spacing stops** — Use clean, predictable values (0.25, 0.5, 0.75, 1.0 rem base). No "nudge" values
- **ds-theme-inverse class pattern** — Single CSS class that swaps all variable values for dark mode or inverted contexts. No separate dark token set required
- **Dual approval gate** — Nothing merges without code review AND designer visual review (via Chromatic or equivalent)
- **Chromatic for visual regression** — Screenshot testing at the component level, tied to Storybook. Developer does first-pass review, designer must approve before PR merges
- **Tokenize spacing for AI** — AI coding agents look for named spacing tokens. Inline REM values degrade AI output quality

---

## Agentic Design Workflow

- **Screenshot-to-API heuristic** — Before analyzing a UI via screenshot, always check if there's an API returning structured data. Screenshots exhaust context windows; use as last resort
- **AI behavior as diagnostic data** — When an agent consistently misapplies a component, that's a signal the design system needs better documentation, not just a model failure
- **Higher-order compositions outperform naked primitives** — Define named patterns (a "card" block, a "form section"). AI composes coherently from named patterns; it struggles from individual atoms
- **Tacit knowledge must be made explicit** — What teams "just know" must be written as explicit rules. Documentation shifts from "nice to have" to "critical input" when AI is a consumer
