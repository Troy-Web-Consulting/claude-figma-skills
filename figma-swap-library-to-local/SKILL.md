---
name: figma-swap-library-to-local
description: Use when a Figma section or frame contains instances sourced from a published library that need to be replaced with local equivalents in the current file.
allowed-tools: Bash(python3 *) Bash(cat *) Bash(ls *)
---

# Figma: Swap Library Components to Local

## Overview

Scans a target node for remote (library) instances and replaces them with local equivalents using a parent-down traversal to avoid mid-loop invalidation. Requires `figma-use` skill before any `use_figma` call.

## Workflow

Four phases, always in order. Never skip phases.

```
Scan → Collect local IDs → Parent-down swap → Verify → Repeat until only known gaps remain
```

**Stop and confirm with the user before swapping when:**
- A remote component has no obvious local equivalent by name (e.g., `Drawer Input` → needs mapping to `Text Input`)
- `skipped` list is non-empty after a swap pass

---

## Phase 1 — Scan (remote-only, deduped)

Run first. Shows scope before touching anything.

```js
// Replace NODE_ID with target node ID (convert URL 1234-5678 → "1234:5678")
let targetNode = null;
for (const page of figma.root.children) {
  await figma.setCurrentPageAsync(page);
  targetNode = await figma.getNodeByIdAsync("NODE_ID");
  if (targetNode) break;
}
if (!targetNode) return { error: "Node not found" };

const instances = targetNode.findAll(n => n.type === "INSTANCE");
const remoteMap = {};
let localCount = 0, unresolvable = 0;

for (const inst of instances) {
  let mc;
  try { mc = await inst.getMainComponentAsync(); } catch (e) { unresolvable++; continue; }
  if (!mc) { unresolvable++; continue; }
  if (mc.remote) {
    const key = mc.key;
    if (!remoteMap[key]) remoteMap[key] = {
      componentKey: key,
      componentName: mc.name,
      componentSetName: (mc.parent?.type === "COMPONENT_SET") ? mc.parent.name : null,
      count: 0,
    };
    remoteMap[key].count++;
  } else { localCount++; }
}

return {
  targetNodeName: targetNode.name,
  totalInstances: instances.length,
  localCount, unresolvable,
  remoteCount: instances.length - localCount - unresolvable,
  distinctRemoteComponents: Object.keys(remoteMap).length,
  remoteComponents: Object.values(remoteMap).sort((a, b) => b.count - a.count),
};
```

Review the result. For each remote component set, verify a local equivalent exists. Confirm any non-obvious mappings with the user before proceeding.

---

## Phase 2 — Collect local component IDs

**Separate `use_figma` call from the swap.** Returns ID strings, not node references — references go stale across `setCurrentPageAsync`.

```js
// Fill in set names and standalone names from Phase 1 results
const COMPONENTS_PAGE = "Components"; // from figma-config.json > componentsPage
const targetSetNames = new Set(["Icons", "Buttons" /* etc */]);
const targetStandalones = new Set(["Drawer header" /* etc */]);
const idMap = {};

for (const page of figma.root.children) {
  if (page.name !== COMPONENTS_PAGE) continue;
  await figma.setCurrentPageAsync(page);
  const allNodes = page.findAll(n => n.type === "COMPONENT_SET" || n.type === "COMPONENT");
  for (const node of allNodes) {
    if (node.type === "COMPONENT_SET" && targetSetNames.has(node.name)) {
      for (const variant of node.children) {
        if (variant.type === "COMPONENT") idMap[`${node.name}::${variant.name}`] = variant.id;
      }
    } else if (node.type === "COMPONENT" && targetStandalones.has(node.name)) {
      idMap[`__standalone::${node.name}`] = node.id;
    }
  }
  break;
}

return { count: Object.keys(idMap).length, idMap };
```

If a needed component is missing from `idMap`, stop and resolve the gap before swapping.

---

## Phase 3 — Parent-down swap

**Use the inject script** to generate Phase 3 automatically from Phase 2 output — no manual idMap copy-paste:

```bash
# Resolve scriptsPath from config first:
SCRIPTS_PATH=$(python3 -c "
import json, sys
cfg = json.load(open('.claude/figma-config.json'))
p = cfg.get('scriptsPath')
if not p: sys.exit('ERROR: scriptsPath not set in .claude/figma-config.json')
print(p)
")

# Save Phase 2 output from Figma console to a JSON file, then:
PYTHONPATH="$SCRIPTS_PATH" python3 -m figma_primitives prep-idmap \
  --input /tmp/phase2-output.json \
  --node-id <target-node-id> \
  --output-dir /tmp/figma-swap
# → writes /tmp/figma-swap/phase3-swap.js  (paste into Figma console)
# → writes /tmp/figma-swap/SUMMARY.md      (lists all mapped components)
```

Node ID format: convert URL `1234-5678` → `1234:5678` (the script handles this automatically).

Alternatively, paste the `idMap` literal from Phase 2 manually into this script:

**Why parent-down:** `findAll` returns nodes depth-first. Swapping a parent mid-loop invalidates its children's IDs — they were children of the old remote node, not the new local one. Filtering to outermost-only avoids this entirely.

```js
const idMap = { /* paste Phase 2 result here */ };

let targetNode = null;
for (const page of figma.root.children) {
  await figma.setCurrentPageAsync(page);
  targetNode = await figma.getNodeByIdAsync("NODE_ID");
  if (targetNode) break;
}
if (!targetNode) return { error: "Node not found" };

const instances = targetNode.findAll(n => n.type === "INSTANCE");

// Identify all remote instances
const remoteInstances = [], remoteInstanceIds = new Set();
for (const inst of instances) {
  let mc;
  try { mc = await inst.getMainComponentAsync(); } catch (e) { continue; }
  if (mc?.remote) { remoteInstances.push({ inst, mc }); remoteInstanceIds.add(inst.id); }
}

// Filter: outermost only — skip children whose ancestor is also being swapped
function hasRemoteAncestor(node) {
  let cur = node.parent;
  while (cur && cur.type !== "PAGE" && cur.type !== "SECTION") {
    if (remoteInstanceIds.has(cur.id)) return true;
    cur = cur.parent;
  }
  return false;
}
const topLevel = remoteInstances.filter(({ inst }) => !hasRemoteAncestor(inst));

// Swap
const swapped = [], skipped = [], errors = [], mutatedNodeIds = [];
for (const { inst, mc } of topLevel) {
  const setName = (mc.parent?.type === "COMPONENT_SET") ? mc.parent.name : null;
  const lookupKey = setName ? `${setName}::${mc.name}` : `__standalone::${mc.name}`;
  const localId = idMap[lookupKey];
  if (!localId) { skipped.push({ componentName: mc.name, setName }); continue; }

  const localComponent = await figma.getNodeByIdAsync(localId);
  if (!localComponent) { errors.push({ componentName: mc.name, error: "not found" }); continue; }

  try {
    inst.swapComponent(localComponent);
    swapped.push({ componentName: mc.name, setName });
    mutatedNodeIds.push(inst.id);
  } catch (e) { errors.push({ componentName: mc.name, error: e.message }); }
}

return { swappedCount: swapped.length, skippedCount: skipped.length, errorCount: errors.length, skipped, errors, mutatedNodeIds };
```

---

## Phase 4 — Verify

Re-run Phase 1 script unchanged. Compare `remoteCount` before and after.

- **`remoteCount` dropped to 0 (or only known gaps):** Done.
- **`remoteCount` still has swappable components:** Local component definitions themselves reference library components. Run Phase 3 again — the tree has settled and children that were invalidated mid-pass are now addressable.
- **New components in `remoteComponents`:** Previously hidden inside a remote parent, now exposed. Add them to `idMap` and run Phase 3 again.

Stop when the only remaining remote instances are confirmed gaps (no local equivalent exists).

---

## Known Pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Node references go stale across page switches | Phase 3 returns no output or swaps 0 | Always collect IDs (strings) in a separate call; resolve with `getNodeByIdAsync` in the swap call |
| `getMainComponentAsync` throws on compound IDs | Script aborts mid-loop | Always wrap in `try/catch`; skip and continue |
| Children invalidated mid-loop | High unresolvable count; known-swappable components appear in second verify scan | Use parent-down filter; re-run Phase 3 after tree settles |
| Local component definitions still reference library | Remote count doesn't reach 0 even after multiple passes | Fix the component definition on the Components page; instances update automatically |

## Non-obvious mappings

When a remote component has no same-name local equivalent, confirm the mapping with the user before swapping. Document confirmed mappings in the `idMap` using the remote set name as the key:

```js
// Remote "Drawer Input::State=Default" maps to local "Text Input::State=Default"
"Drawer Input::State=Default": "3004:33766",
"Drawer Input::State=Locked": "3004:33763",
```
