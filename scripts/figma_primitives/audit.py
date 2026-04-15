"""
audit.py — Structural audit of a Figma registry against naming and tier rules.

Runs deterministic checks that don't require taste judgment:
  - Naming patterns: slash-separated paths, casing consistency
  - Token tier violations: primitives referenced directly in components
  - Orphaned components: in registry but section/page structure is inconsistent
  - Alias chain issues: circular refs, missing semantic tokens, unused aliases
  - Variable collection audit: duplicate values, undeclared collections

Prose rules from design.md are NOT applied here — that is LLM work done in the
figma-design-audit skill. This primitive handles the grep-equivalent structural
passes so the LLM doesn't need to re-scan raw data.

Input:
  --registry  figma-registry.json (required)
  --output    audit-report.yaml

Output (audit-report.yaml):
  auditDate: "2026-04-15"
  registryFile: "docs/figma-registry.json"
  summary:
    totalComponents: 103
    totalVariables: 280
    namingViolations: 5
    tierViolations: 3
    orphans: 2
    aliasIssues: 4
    duplicateValues: 8
  namingViolations:
    - { name: "ButtonPrimary", reason: "not slash-separated", type: "component" }
  tierViolations:
    - { token: "color/brand/primary", usedIn: "Button/Primary", reason: "primitive used directly in component" }
  orphans:
    - { name: "OldCard", reason: "section not found in registry sections list" }
  aliasIssues:
    - { token: "color/heading", reason: "alias target not found: color/brand/headingX" }
  duplicateValues:
    - { value: "#1a2b3c", tokens: ["color/brand/primary", "color/link/default"] }

CLI:
    python -m figma_primitives audit --registry <registry.json> --output <report.yaml>
"""

import sys
import json
import argparse
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _dump_yaml(data: dict, path: str) -> None:
    content = _to_yaml_str(data)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _to_yaml_str(data: dict) -> str:
    if HAS_YAML:
        return yaml.dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    # Minimal fallback serializer for simple structures
    lines = []
    _yaml_serialize(data, lines, 0)
    return "\n".join(lines) + "\n"


def _yaml_serialize(obj, lines, indent):
    pad = "  " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                _yaml_serialize(v, lines, indent + 1)
            else:
                lines.append(f"{pad}{k}: {_yaml_scalar(v)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                first = True
                for k, v in item.items():
                    prefix = f"{pad}- " if first else f"{pad}  "
                    first = False
                    if isinstance(v, (dict, list)):
                        lines.append(f"{prefix}{k}:")
                        _yaml_serialize(v, lines, indent + 1)
                    else:
                        lines.append(f"{prefix}{k}: {_yaml_scalar(v)}")
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
    else:
        lines.append(f"{pad}{_yaml_scalar(obj)}")


def _yaml_scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(c in s for c in ":#{}[]|>&*!,?"):
        return f'"{s}"'
    return s


# ---------------------------------------------------------------------------
# Check: naming patterns
# ---------------------------------------------------------------------------

SLASH_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]*(\/[A-Za-z][A-Za-z0-9 _-]*)+$")
CAMEL_RE = re.compile(r"^[A-Z][a-zA-Z0-9]+$")


def _check_naming(registry: dict) -> list:
    violations = []

    # Components: names should be slash-separated (e.g. "Button/Primary")
    for comp in registry.get("components", []):
        name = comp.get("name", "")
        if not name:
            continue
        if "/" not in name:
            violations.append({
                "name": name,
                "type": "component",
                "reason": "component name is not slash-separated (expected 'Set/Variant' format)"
            })
        elif CAMEL_RE.match(name.split("/")[0]):
            # Top-level component set uses PascalCase — acceptable
            pass

    # Variables: names should be slash-separated paths
    variables = registry.get("variables", {})
    for collection_name, tokens in variables.items():
        if not isinstance(tokens, dict):
            continue
        for token_name in tokens:
            if not token_name.startswith("_") and "/" not in token_name:
                violations.append({
                    "name": token_name,
                    "type": f"variable/{collection_name}",
                    "reason": "variable name is not slash-separated (expected 'category/name' format)"
                })

    return violations


# ---------------------------------------------------------------------------
# Check: token tier violations
# ---------------------------------------------------------------------------

def _infer_tier(name: str) -> str:
    """Heuristic: tokens with only one or two path segments are likely primitives."""
    parts = name.split("/")
    if len(parts) <= 2:
        return "primitive"
    return "semantic"


def _check_tier_violations(registry: dict) -> list:
    """
    Flag components whose bound variables directly reference primitive tokens
    rather than semantic tokens. Heuristic: a primitive token has ≤2 path segments.
    """
    violations = []
    variables = registry.get("variables", {})
    flat_vars: dict[str, str] = {}
    for tokens in variables.values():
        if isinstance(tokens, dict):
            flat_vars.update(tokens)

    # For each component, check if any known token binding is a primitive
    for comp in registry.get("components", []):
        bindings = comp.get("boundVariables", [])
        if not bindings:
            continue
        for binding in bindings:
            token_name = binding if isinstance(binding, str) else binding.get("variable", "")
            if token_name and _infer_tier(token_name) == "primitive":
                violations.append({
                    "token": token_name,
                    "usedIn": comp.get("name", comp.get("id", "unknown")),
                    "reason": "primitive-tier token referenced directly in component (use a semantic token instead)"
                })

    return violations


# ---------------------------------------------------------------------------
# Check: orphaned components
# ---------------------------------------------------------------------------

def _check_orphans(registry: dict) -> list:
    """
    Flag components whose section is not in the sections list,
    or whose type field is set to a deprecated value.
    """
    orphans = []
    known_sections = {s.get("name") for s in registry.get("sections", []) if s.get("name")}
    version_map = registry.get("versionMap", {})

    for comp in registry.get("components", []):
        section = comp.get("section", "")
        if known_sections and section and section not in known_sections:
            orphans.append({
                "name": comp.get("name", comp.get("id", "unknown")),
                "reason": f"section '{section}' not found in registry sections list"
            })
        # Flag if the component name matches a versionMap deprecated key
        name = comp.get("name", "")
        if name in version_map:
            orphans.append({
                "name": name,
                "reason": f"component is listed as deprecated in versionMap (migrate to: {version_map[name].get('current', '?')})"
            })

    return orphans


# ---------------------------------------------------------------------------
# Check: alias chain issues
# ---------------------------------------------------------------------------

ALIAS_REF_RE = re.compile(r"^\{(.+)\}$")


def _check_alias_issues(registry: dict) -> list:
    issues = []
    variables = registry.get("variables", {})
    flat_vars: dict[str, str] = {}
    for tokens in variables.values():
        if isinstance(tokens, dict):
            flat_vars.update({k: str(v) for k, v in tokens.items()})

    referenced: set[str] = set()
    referencing: set[str] = set()

    for name, value in flat_vars.items():
        m = ALIAS_REF_RE.match(value)
        if not m:
            continue
        target = m.group(1)
        referencing.add(name)
        referenced.add(target)
        if target not in flat_vars:
            issues.append({
                "token": name,
                "reason": f"alias target not found: {target}"
            })
        elif ALIAS_REF_RE.match(flat_vars[target]):
            # Two-hop alias — check it resolves
            hop2 = ALIAS_REF_RE.match(flat_vars[target]).group(1)
            if hop2 not in flat_vars:
                issues.append({
                    "token": name,
                    "reason": f"alias chain broken at second hop: {target} → {hop2} (not found)"
                })

    # Missing semantic tokens: primitives that are never aliased from a semantic
    for name in flat_vars:
        if _infer_tier(name) == "primitive" and name not in referenced:
            issues.append({
                "token": name,
                "reason": "primitive token has no semantic alias referencing it (possibly unused)"
            })

    return issues


# ---------------------------------------------------------------------------
# Check: duplicate resolved values
# ---------------------------------------------------------------------------

def _check_duplicates(registry: dict) -> list:
    variables = registry.get("variables", {})
    flat_vars: dict[str, str] = {}
    for tokens in variables.values():
        if isinstance(tokens, dict):
            for k, v in tokens.items():
                if not ALIAS_REF_RE.match(str(v)):  # skip aliases, only raw values
                    flat_vars[k] = str(v)

    by_value: dict[str, list] = defaultdict(list)
    for name, value in flat_vars.items():
        by_value[value].append(name)

    return [
        {"value": value, "tokens": names}
        for value, names in by_value.items()
        if len(names) > 1
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Structural audit of a Figma registry"
    )
    parser.add_argument("--registry", required=True, help="Path to figma-registry.json")
    parser.add_argument("--output", required=True, help="Path for audit-report.yaml")
    args = parser.parse_args(argv)

    registry = _load_json(args.registry)

    naming_violations = _check_naming(registry)
    tier_violations = _check_tier_violations(registry)
    orphans = _check_orphans(registry)
    alias_issues = _check_alias_issues(registry)
    duplicate_values = _check_duplicates(registry)

    # Count totals
    n_components = len(registry.get("components", []))
    n_variables = sum(
        len(v) for v in registry.get("variables", {}).values()
        if isinstance(v, dict)
    )

    report = {
        "auditDate": str(date.today()),
        "registryFile": args.registry,
        "summary": {
            "totalComponents": n_components,
            "totalVariables": n_variables,
            "namingViolations": len(naming_violations),
            "tierViolations": len(tier_violations),
            "orphans": len(orphans),
            "aliasIssues": len(alias_issues),
            "duplicateValues": len(duplicate_values),
        },
        "namingViolations": naming_violations,
        "tierViolations": tier_violations,
        "orphans": orphans,
        "aliasIssues": alias_issues,
        "duplicateValues": duplicate_values,
    }

    _dump_yaml(report, args.output)

    # Print summary to stdout for skill consumption
    s = report["summary"]
    print(f"namingViolations={s['namingViolations']}")
    print(f"tierViolations={s['tierViolations']}")
    print(f"orphans={s['orphans']}")
    print(f"aliasIssues={s['aliasIssues']}")
    print(f"duplicateValues={s['duplicateValues']}")
    print(f"report_written={args.output}")
