---
name: figma-builder
description: >
  Build or modify Figma components and component sets using the Plugin API.
  Covers variant schemas, property binding, combineAsVariants, naming
  conventions, slot operations, SVG import, instance rules, and batch
  operations. Triggers on: "create a component," "add a variant," "build this
  in Figma," "update all," "bulk," or any component set modification.
---

# Figma Builder

Codified rules and patterns for creating, extending, and bulk-modifying Figma components via the Plugin API (`use_figma`).

**Prerequisites:**
1. Run `figma-workspace` first to gather context about the target file
2. The official `figma-use` skill handles all generic Plugin API rules (color ranges, fills/strokes, font loading, page context, auto-layout ordering, coordinate placement, incremental workflow, error recovery). **Do not duplicate that guidance here.** This skill covers only what goes beyond `figma-use`.

---

## Capture + Canvas Sequencing Rule

**When doing multi-page web captures (code→Figma):** never interleave `use_figma` canvas writes with capture polling. The Figma plugin processes one operation at a time — `use_figma` calls preempt the capture queue and cause silent failures.

**Correct order:**
1. Generate all capture IDs upfront (parallel `generate_figma_design` calls)
2. Fire all captures (navigate + `captureForDesign`)
3. Poll all to `completed` — no `use_figma` calls in between
4. Do all renames, moves, and layout in one `use_figma` call at the end

**Also:** Always call `await figma.setCurrentPageAsync(page)` before reading `page.children`. Figma lazy-loads page node trees — without this, `children.length` returns 0 even when frames exist.

---

## Pre-flight Checklist

Before creating anything:

1. Confirm `figma-workspace` context exists in conversation (fileKey, components found, canvas position)
2. Verify no existing component already does what you're about to build (check workspace component inventory)
3. Review `figma-use` pre-flight checklist for generic API checks

---

## Property Binding

`componentPropertyReferences` is what wires a text node or visibility toggle to a component property. Without it, `setProperties` updates the stored value but nothing changes visually.

**How to check:**
```js
// If this returns {}, the property isn't bound — setProperties won't have visual effect
console.log(node.componentPropertyReferences);
```

**Property key format:** Keys have `#nodeId` suffixes (e.g., `Label#12:34`). Always search by prefix at runtime, never hardcode the full key:
```js
const typeKey = Object.keys(node.componentProperties).find(k => k.startsWith('Type'));
node.setProperties({ [typeKey]: 'NewValue' });
```

**Binding types:**
- `characters` binding — drives text content
- `visible` binding — drives show/hide

**Nested instances:** Properties often live on a child instance, not the top-level node:
```js
const target = parentInstance.findOne(n =>
  n.type === 'INSTANCE' && 'Type' in (n.componentProperties || {})
);
target.setProperties({ 'Type': 'NewValue' });
```

---

## Variant Schema Rules

- All variants in a component set must share the **same property dimensions**
- Adding a variant with fewer properties results in "invalid variants" warning
- Fix: add default values for missing properties before combining (e.g., `State=Default`)
- Verify all variants match before calling `combineAsVariants`

---

## combineAsVariants Checklist

This is a destructive operation. Follow every step:

1. Put **existing variants FIRST** in the array — this preserves the naming convention
2. Call `figma.combineAsVariants([...existingSet.children, ...newComponents], parent)`
3. Check for **duplicate variant names** (Figma allows them silently — "same property values" warning)
4. Verify **`clipsContent` matches** across all variants
5. **Re-fetch the component set** — it has a new node ID after combine
6. **Resize to wrap contents** with appropriate padding

```js
// Post-merge pattern
const existingSet = await figma.getNodeByIdAsync('EXISTING_SET_ID');
const setX = existingSet.x, setY = existingSet.y, setName = existingSet.name;
const parent = existingSet.parent;

const merged = figma.combineAsVariants([...existingSet.children, ...newComponents], parent);
merged.name = setName;
merged.x = setX;
merged.y = setY;
return { newId: merged.id, variantCount: merged.children.length };
```

**New component defaults that differ from existing:**

| Property | New default | Usually should match |
|---|---|---|
| `clipsContent` | `false` | `true` |
| `fills` | none | Check existing variant |

---

## Slot Operations

Slots on instances are NOT regular frames. Special rules apply:

1. **Clear component slot defaults BEFORE creating instances.** Ghost nodes from defaults persist on pre-existing instances and cannot be removed via the API
2. **Build slot content BEFORE creating the instance.** Park content nodes on the page, then `appendChild` into the instance's slot
3. **Ghost node workaround:** If stuck with ghost nodes on pre-existing instances, escalate to `figma_execute` (Desktop Bridge) — observed to handle this more reliably

---

## Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Component sets | PascalCase | `Drawer Form Field` |
| Sub-components | Slash namespacing | `Drawer/ProgressBar` |
| Variants | Property=Value pairs | `Type=Text, State=Default` |
| Layers | Semantic names | `Body Content`, `Role Cards`, `ButtonRow` |

**Never:** `Container`, `Frame 1`, `Group 2`, `Rectangle 4`

---

## SVG Import

**Always use `figma.createNodeFromSvg(svgString)` for SVG import.** It handles all path types, preserves viewBox scaling, and maintains correct relative positions.

```js
// CORRECT — handles all path types
const svgNode = figma.createNodeFromSvg(`<svg viewBox="0 0 256 256">...</svg>`);

// WRONG — fails silently on any arc command
vector.vectorPaths = [{ windingRule: "NONZERO", data: "M 0 0 A 32 32..." }]
```

**`vectorPaths` does NOT support arc commands (`A`).** Only: `M L H V C Q Z`. Spaces between values, no commas: `"M 0 0 L 48 0 L 48 48 Z"`.

**After `createNodeFromSvg`:**
- Returns a FRAME with children at their natural positions
- Do NOT resize individual children
- Scale by moving children into a component and applying a single scale factor: `const scale = targetSize / viewBoxSize`

---

## Instance Rules

- **Cannot reparent** nodes inside instances — "Cannot move node. New parent is an instance"
- **Cannot edit sublayer content directly** — use `setProperties` on exposed props
- After `detachInstance()`: all sublayer IDs become stale — re-fetch via `findOne`/`findAll`
- `setProperties` fails when the variant value doesn't exist in the set yet
- Always verify the variant exists before calling `setProperties`

---

## Cross-File vs Cross-Page

- **Cross-file copy** always creates an instance, never a component definition. No API or manual method moves definitions between files
- **Cross-page reparenting** within the same file is supported: `targetPage.appendChild(node)`
- **Within-page moves** via direct reparenting: `targetFrame.appendChild(node)`

---

## Batch Operations

### When batching is needed

- Operations targeting >10 nodes
- Code exceeding 50k character limit for `use_figma`
- Data payloads (SVGs, property maps) too large to inline
- Multi-step operations where partial failure is likely

### use_figma batching

- 50k character limit per call
- Break into logical batches (e.g., 10 variants per call)
- Each call must be self-contained — no shared state between calls
- Return created nodeIds from each batch for stitching later

### Error tracking

Each batch should return:
```js
{ success: [...nodeIds], failed: [...{id, error}] }
```

Accumulate across batches. After all batches, report summary.

### Retry rules

1. On failure: clean up orphaned nodes with `node.remove()`
2. Re-fetch target state before retrying (IDs may shift after writes)
3. **Never retry without cleanup** — partial artifacts compound
4. Never cache nodeIds across batches — they shift after writes

See `references/batch-patterns.md` for complete patterns.

---

## References

- `references/snippets.md` — copy-paste code blocks for common build operations
- `references/batch-patterns.md` — batching strategies, progress tracking, error recovery
- `figma-workspace/references/snippets.md` — read/audit snippets (shared)
- Official `figma-use` skill references — Plugin API typings, gotchas, common patterns, variable/component/text-style patterns
