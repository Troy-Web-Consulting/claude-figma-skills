# Batch Operation Patterns

Patterns for large-scale Figma operations that exceed single-call limits.

---

## When Batching is Needed

- Operations targeting >10 nodes
- Code exceeding 50k character limit for `use_figma`
- Data payloads (SVGs, property maps) too large to inline
- Multi-step operations where partial failure is likely

---

## use_figma Batching Strategy

50k character code limit per call. Each call is a fresh execution context — no shared state.

### Pattern: Logical Batches with ID Stitching

```
Batch 1: Create variants 1-10 → return [{id, name}, ...]
Batch 2: Create variants 11-20 → return [{id, name}, ...]
Batch 3: Combine all variants into set → use IDs from batches 1-2
```

**Rules:**
- Each batch must be self-contained (define all helpers inline)
- Return created nodeIds from each batch — you'll need them later
- Never assume nodeIds persist across batches for nodes you didn't create
- Park newly created nodes off-canvas (`x = -99999`) until final placement

### Estimating Batch Sizes

| Operation | Approximate chars per node |
|---|---|
| Simple frame creation | ~200-400 |
| Component with auto-layout + text | ~600-1000 |
| SVG import + scaling | ~500-800 (plus SVG string length) |
| Property setting on existing node | ~150-300 |
| Variable creation | ~200-400 |

Rule of thumb: 50k chars / chars-per-node = max nodes per batch. Leave 20% headroom for error handling and return statements.

---

## figma_execute Batching Strategy

Default 5s timeout — set `timeout: 15000-30000` for bulk ops.

### Pattern: HTTP Data Serving

For large datasets, serve via localhost HTTP instead of embedding inline:

```bash
# Step 1: Prepare data (bash_tool)
mkdir -p /tmp/serve
cat > /tmp/serve/data.json << 'EOF'
{
  "Icon1": "<svg viewBox='0 0 256 256'>...</svg>",
  "Icon2": "<svg viewBox='0 0 256 256'>...</svg>"
}
EOF
python3 -m http.server 8765 --directory /tmp/serve &
SERVER_PID=$!
echo "Server PID: $SERVER_PID"
```

```js
// Step 2: Fetch in figma_execute
const resp = await fetch('http://localhost:8765/data.json');
const data = await resp.json();

const results = [];
for (const [name, svg] of Object.entries(data)) {
  try {
    const node = figma.createNodeFromSvg(svg);
    node.name = name;
    results.push({ name, ok: true, id: node.id });
  } catch (e) {
    results.push({ name, ok: false, error: e.message?.slice(0, 80) });
  }
}
return results;
```

```bash
# Step 3: Clean up (bash_tool)
kill $SERVER_PID 2>/dev/null
rm -rf /tmp/serve
```

---

## Progress and Error Tracking

### Operation Log Pattern

Accumulate results across batches:

```js
// In each batch, return structured results
return {
  batch: 1,
  success: [
    { id: "123:456", name: "Variant1" },
    { id: "123:457", name: "Variant2" }
  ],
  failed: [
    { name: "Variant3", error: "Font not loaded: Inter Bold" }
  ]
};
```

After all batches, aggregate:
```
Total: 20 operations across 3 batches
Succeeded: 18
Failed: 2
  - Variant3: Font not loaded: Inter Bold
  - Variant15: Cannot reparent inside instance
```

### Retry Strategy

1. **Clean up orphaned nodes** from the failed batch:
   ```js
   // Remove all nodes created in the failed batch
   for (const id of failedBatchNodeIds) {
     const node = await figma.getNodeByIdAsync(id);
     if (node) node.remove();
   }
   ```

2. **Re-fetch target state** — IDs may have shifted:
   ```js
   // Don't trust cached IDs — re-scan
   const currentChildren = targetFrame.children.map(c => ({ id: c.id, name: c.name }));
   ```

3. **Retry the batch** with fresh state

4. **Never retry without cleanup** — partial artifacts compound into increasingly broken state

---

## Common Batch Recipes

### Bulk Variant Property Update

Update a property across all instances of a component in a frame:

```js
const frame = await figma.getNodeByIdAsync('FRAME_ID');
const instances = frame.findAll(n => n.type === 'INSTANCE');
const results = [];

for (const inst of instances) {
  try {
    const propKey = Object.keys(inst.componentProperties || {}).find(k => k.startsWith('State'));
    if (propKey) {
      inst.setProperties({ [propKey]: 'Active' });
      results.push({ id: inst.id, ok: true });
    } else {
      results.push({ id: inst.id, ok: false, reason: 'no State prop' });
    }
  } catch (e) {
    results.push({ id: inst.id, ok: false, reason: e.message?.slice(0, 80) });
  }
}
return { total: instances.length, succeeded: results.filter(r => r.ok).length, failed: results.filter(r => !r.ok) };
```

### Component Description Update Across Library

```js
const page = figma.currentPage;
const components = page.findAll(n => n.type === 'COMPONENT' || n.type === 'COMPONENT_SET');
const updates = [];

for (const comp of components) {
  if (!comp.description || comp.description.trim() === '') {
    comp.description = `[Auto] ${comp.name} — needs description`;
    updates.push({ id: comp.id, name: comp.name });
  }
}
return { updated: updates.length, components: updates };
```

---

## Instance Sibling Modification Pattern

When you need to modify multiple siblings inside a component instance (e.g., table
cells in a column, form fields in a slot, radio cards in a group), **each sibling
needs its own `use_figma` call.** This is because the Figma Plugin API re-renders
the entire instance subtree after any `setProperties`, `.characters`, or `.visible`
change, invalidating all sibling node IDs.

### Pattern: Sequential Sibling Updates

```
// Pseudocode — each block is a separate use_figma call

// Call 1: Update cell 0
const shell = figma.getNodeById('SHELL_ID');  // stable anchor
const table = shell.findAll(n => n.name === 'Users Table')[0];
const col = table.children[0].children[0]; // first column
const cell = col.children[1].children[0];  // first cell in cells slot
cell.setProperties({ 'Content#3065:4': 'Maria Rodriguez' });

// Call 2: Update cell 1 (re-traverse from shell — IDs changed!)
const shell = figma.getNodeById('SHELL_ID');
const table = shell.findAll(n => n.name === 'Users Table')[0];
const col = table.children[0].children[0];
const cell = col.children[1].children[1];
cell.setProperties({ 'Content#3065:4': 'James Park' });

// ...repeat for each cell
```

### Pattern: Hiding Extra Siblings (may work in single call)

Simple `.visible = false` changes sometimes survive in a single call if you
collect all refs first via spread. Try this first; fall back to per-call if it fails:

```js
const container = shell.findAll(n => n.name === 'Properties')[0];
const children = [...container.children]; // spread captures refs
for (const child of children) {
  child.visible = false;
}
```

### Pattern: Adding Content to Slots

Create instances on the page, then move into the slot. Children get new IDs
after the move but structure is preserved:

```js
// Call 1: Create and configure the instance
const comp = figma.getNodeById('COMPONENT_ID');
const instance = comp.createInstance();
// Set properties while it's still a page-level node
instance.setProperties({ ... });

// Move into slot
const slot = shell.findAll(n => n.name === 'Body')[0];
slot.appendChild(instance);
instance.layoutSizingHorizontal = 'FILL';
return { createdNodeIds: [instance.id] }; // ID will change after move
```

### Call Count Estimation

Before starting a sibling batch, calculate and report:

| Content type | Items | Calls needed |
|---|---|---|
| Table column headers | 4 | 4 (one per header) |
| Table cell data (6 rows × 4 cols) | 24 | 24 |
| Hide extra rows (4 × 4 cols) | 16 | 4 (one per column, spread pattern) |
| Drawer form fields | 8 | 8 |
| Radio cards | 9 | 9 |
| **Total** | | **~49 calls (~3 min)** |

Present this estimate to the user before executing.

### Desktop Bridge Alternative

When `figma_get_status` shows the Desktop Bridge is connected, use individual tools
instead. These target specific nodes by ID without triggering instance re-renders:

- `figma_set_instance_properties({ nodeId, properties })` — any instance
- `figma_set_text({ nodeId, text })` — any text node
- `figma_instantiate_component({ componentKey, parentId })` — create in place

This eliminates the one-call-per-sibling limitation entirely.

---

## Anti-Patterns

- **Caching nodeIds across batches** — they shift after writes. Always re-fetch.
- **Setting FILL sizing before parent auto-layout exists** — throws silently or errors.
- **Skipping cleanup on partial failures** — orphaned nodes accumulate and break subsequent operations.
- **Inlining large SVG strings** — use HTTP serving instead. 50k limit is reached fast with SVGs.
- **Running all batches without checking intermediate results** — a batch 1 failure may invalidate the assumptions of batch 3.
- **Modifying multiple siblings in one `use_figma` call** — the Figma Plugin API re-renders the entire instance subtree after any mutation, invalidating sibling IDs. Use one call per sibling, re-traversing from a stable ancestor each time.
