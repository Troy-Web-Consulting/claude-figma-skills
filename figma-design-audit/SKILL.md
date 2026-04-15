---
name: figma-design-audit
description: >
  Audit a Figma project's registry and source components against the project's
  design rules. Runs structural checks via the audit primitive (naming, tier
  violations, orphans, alias issues) then applies prose rules from design.md
  for taste-level findings. Emits audit-report.yaml. Triggers on: "audit the
  design system," "check for naming violations," "are there any orphaned
  components," "review the Figma registry," or as a pre-step before a
  design-system cleanup sprint.
allowed-tools: Bash(python3 *) Bash(cat *) Bash(ls *) Bash(grep *)
---

# Figma: Design Audit

Audits the project's Figma registry and component structure against its design rules. Structural checks are demoted to the `figma_primitives` package; the only LLM work is applying `design.md` prose rules to ambiguous findings and writing actionable remediation notes.

**Prerequisite:** Run `figma-workspace` first to load registry and design doc context.

---

## Step 1: Resolve Paths from Config

```bash
python3 - << 'PYEOF'
import json, os, sys

cfg = json.load(open(".claude/figma-config.json"))
registry = cfg.get("registryPath", "docs/figma-registry.json")
design_doc = cfg.get("designDocPath") or cfg.get("conventionsPath")
audit_out = cfg.get("auditReportPath", "docs/audit-report.yaml")
scripts = cfg.get("scriptsPath") or "scripts"

print(f"registry={registry}")
print(f"design_doc={design_doc or 'unset'}")
print(f"audit_out={audit_out}")
print(f"scripts={scripts}")
print(f"registry_exists={'yes' if os.path.exists(registry) else 'no'}")
print(f"design_doc_exists={'yes' if (design_doc and os.path.exists(design_doc)) else 'no'}")
PYEOF
```

If `registry_exists=no`: run `figma-workspace` first to generate the registry.
If `design_doc_exists=no`: the structural checks still run, but prose-rule findings will be skipped. Tell the user.

---

## Step 2: Run Structural Audit Primitive

`figma_primitives` lives in `~/Code/claude-figma-skills/scripts/`. It is not installed as a package — invoke it by setting `PYTHONPATH` or running from that directory:

```bash
PYTHONPATH="$HOME/Code/claude-figma-skills/scripts" \
  python3 -m figma_primitives audit \
  --registry "$REGISTRY_PATH" \
  --output "$AUDIT_OUT"
```

Read the summary output:

```bash
python3 - << 'PYEOF'
import yaml
data = yaml.safe_load(open("$AUDIT_OUT"))
s = data["summary"]
print(f"Components: {s['totalComponents']}  Variables: {s['totalVariables']}")
print(f"Naming violations: {s['namingViolations']}")
print(f"Tier violations:   {s['tierViolations']}")
print(f"Orphans:           {s['orphans']}")
print(f"Alias issues:      {s['aliasIssues']}")
print(f"Duplicate values:  {s['duplicateValues']}")
PYEOF
```

---

## Step 3: Read design.md Rules (LLM)

Read the project's `design.md` (path from `designDocPath`). Extract:
- Naming conventions declared in the doc
- Token tier architecture (what counts as primitive vs. semantic)
- Any explicit "do not do X" rules

These inform the finding classification in Step 4.

---

## Step 4: Classify Findings (LLM)

For each category with non-zero counts, read the items from `audit-report.yaml` and classify:

### Naming violations
- Cross-check against `design.md` naming conventions.
- Mark as **Critical** if the violation breaks a convention explicitly stated in `design.md`.
- Mark as **Advisory** if it's a pattern inconsistency not covered by the doc.

### Tier violations
- Confirm against `design.md`'s token tier rules (if present).
- Mark as **Critical** if a primitive is used where a semantic token is required by the rules.
- Mark as **Advisory** if the rules don't explicitly address this case.

### Orphans
- Check whether the orphaned component appears in the deprecated section of `versionMap`.
- Mark as **Safe to remove** if it's deprecated and has a migration path.
- Mark as **Investigate** if it has no clear deprecation record.

### Alias issues
- Broken chains → **Critical** (will cause rendering failures when variables are used in code).
- Unused primitives → **Advisory** (possible dead token, but may be intentional).

### Duplicate values
- Exact same hex used under different names → surface to user. Likely candidates for aliasing.

---

## Step 5: Write Remediation Notes

Append a `remediation` section to `audit-report.yaml`:

```yaml
remediation:
  critical:
    - finding: "<description>"
      action: "<specific action>"
      file: "<registry path or component name>"
  advisory:
    - finding: "<description>"
      action: "<suggested action>"
  deferred:
    - finding: "<description>"
      reason: "<why deferred>"
```

Surface **critical** items to the user immediately. Present **advisory** items as a grouped list for review. **Do not make any writes to Figma or source files** — this skill is read-only.

---

## Step 6: Report to User

Present a summary:

```
Design Audit — <project name> — <date>
─────────────────────────────────────────
Registry: <n> components, <n> variables
Audit report: <audit_out path>

Critical (requires action):
  • <finding 1>
  • <finding 2>

Advisory (review recommended):
  • <finding 3>
  • <finding 4>

All findings written to: <audit_out>
```

If all counts are zero: confirm "No structural violations found" and note that prose-rule checks (from `design.md`) were applied. The clean result is also a data point worth recording.

---

## Output Contract

Emits `audit-report.yaml` at `auditReportPath` from config (default: `docs/audit-report.yaml`).

This file is reusable input for `figma-design-sync` when cleanup writes are needed.
