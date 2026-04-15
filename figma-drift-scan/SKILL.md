---
name: figma-drift-scan
description: >
  Detect drift between code tokens and Figma variables. Reads the project's
  token files and Figma registry, runs parse_tokens + diff_tokens primitives,
  and emits a drift-manifest.yaml. LLM-side work is bounded: judge whether
  each drift item is intentional, then write a prose report. Triggers on:
  "check token drift," "are tokens in sync," "what's drifted in Figma,"
  "sync audit," or as a pre-step before figma-design-sync.
allowed-tools: Bash(python3 *) Bash(cat *) Bash(ls *) Bash(jq *)
---

# Figma: Drift Scan

Detects drift between code design tokens and Figma variables. Demotes all diffing to the `figma_primitives` package — the only LLM work is judging intentionality and writing a human-readable report.

**Prerequisite:** Run `figma-workspace` first to load registry context.

---

## Step 1: Resolve Paths from Config

```bash
python3 - << 'PYEOF'
import json, os, sys

cfg = json.load(open(".claude/figma-config.json"))
print(f"registry={cfg.get('registryPath', 'docs/figma-registry.json')}")
print(f"drift_out={cfg.get('driftManifestPath', 'docs/drift-manifest.yaml')}")
print(f"tokens_dir={cfg.get('tokensDir', 'src/styles/tokens')}")
scripts = cfg.get("scriptsPath") or "scripts"
print(f"scripts={scripts}")
PYEOF
```

Set variables from output. If `tokensDir` does not exist, ask the user where the token files live before proceeding.

---

## Step 2: Locate Token Files

```bash
ls "$TOKENS_DIR"/*.css "$TOKENS_DIR"/*.json "$TOKENS_DIR"/*.yaml 2>/dev/null
```

List token files found. If none found, check `tailwindThemePath` as a fallback:

```bash
cat ".claude/figma-config.json" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tailwindThemePath',''))"
```

Ask the user to confirm which files to diff against Figma before proceeding.

---

## Step 3: Parse Tokens

Run `parse_tokens` on each token file. Merges into a single normalized-tokens.json:

```bash
python3 -m figma_primitives parse-tokens \
  --input "$TOKENS_FILE" \
  --output /tmp/figma-drift/normalized-tokens.json
```

Repeat for each file, or pass comma-separated paths if supported. Check output:

```bash
cat /tmp/figma-drift/normalized-tokens.json | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(f'Parsed {len(d)} tokens')
"
```

If parse fails, report the error verbatim — do not guess at the format.

---

## Step 4: Diff Against Registry

```bash
python3 -m figma_primitives diff-tokens \
  --tokens /tmp/figma-drift/normalized-tokens.json \
  --registry "$REGISTRY_PATH" \
  --output "$DRIFT_OUT"
```

Read the manifest back:

```bash
python3 - << 'PYEOF'
import yaml, sys, collections

data = yaml.safe_load(open("$DRIFT_OUT"))
items = data.get("items", [])
counts = collections.Counter(i["status"] for i in items)
print(f"MATCH={counts.get('MATCH',0)}")
print(f"DRIFT={counts.get('DRIFT',0)}")
print(f"NEW={counts.get('NEW',0)}")
print(f"ORPHAN={counts.get('ORPHAN',0)}")
PYEOF
```

---

## Step 5: Intentionality Judgment (LLM)

For each item with status `DRIFT`, `NEW`, or `ORPHAN`:

1. Read the token name, code value, and Figma value side-by-side.
2. Apply these heuristics:
   - **Intentional drift:** rebrand in progress, token renamed, Figma not yet updated
   - **Unintentional drift:** small value difference (1–2px, slight hex shift), likely copy-paste error
   - **Intentional NEW:** new token added in code but not yet pushed to Figma
   - **Orphaned:** token removed from code but still lives in Figma — flag for cleanup

Do not guess — if the name gives no signal, mark as `UNKNOWN` and surface to the user.

---

## Step 6: Write Prose Report

Append a `## Drift Scan Report` section to the drift-manifest.yaml (or a companion `.md`):

```yaml
report:
  scanned_at: <ISO date>
  token_files: [<list>]
  summary:
    match: <n>
    drift: <n>
    new: <n>
    orphan: <n>
  intentional_drift: [<list of names>]
  unintentional_drift: [<list of names>]
  new_tokens: [<list of names>]
  orphans: [<list of names>]
  unknown: [<list of names>]
  recommended_actions:
    - "<action>"
```

Surface to the user:
- Unintentional drift (needs a fix — either update code or update Figma)
- Orphaned tokens (likely safe to delete from Figma — confirm first)
- Unknown items (need human judgment)

Do **not** make writes to Figma or to token files. This skill is read-only.

---

## Output Contract

Emits `drift-manifest.yaml` at `driftManifestPath` from config (default: `docs/drift-manifest.yaml`).

This file is the input for `figma-design-sync` when it is built (Phase 6). Keep it at the declared path so downstream skills can find it.
