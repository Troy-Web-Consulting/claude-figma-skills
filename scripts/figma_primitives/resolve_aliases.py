"""
resolve_aliases.py — Flatten alias chains in a normalized-tokens.json file.

Takes the output of parse_tokens and resolves each alias token to its
terminal (non-alias) value. Detects circular references and reports them.

Input:  normalized-tokens.json (list of token objects from parse_tokens)
Output: normalized-tokens.json with aliasResolved and resolvedValue fields added

Added fields on each token:
  resolvedValue   -- the terminal value after following alias chain (null if circular or unresolved)
  resolvedChain   -- list of figmaName hops from this token to the terminal
  circularAlias   -- true if this token is part of a circular alias chain

CLI:
    python -m figma_primitives resolve-aliases --input <normalized-tokens.json> --output <file>
"""

import sys
import json
import argparse
from pathlib import Path


def resolve(tokens: list) -> list:
    """
    Walk alias chains and annotate each token with resolvedValue + resolvedChain.
    Returns a new list — does not mutate input.
    """
    token_map = {t["figmaName"]: t for t in tokens}
    cache: dict[str, tuple] = {}  # figmaName → (resolvedValue, chain, is_circular)

    def _resolve(name: str, visiting: set) -> tuple:
        """Returns (resolvedValue, chain, is_circular)."""
        if name in cache:
            return cache[name]

        token = token_map.get(name)
        if token is None:
            result = (None, [name], False)
            cache[name] = result
            return result

        if not token.get("isAlias") or not token.get("aliasTarget"):
            result = (token["value"], [name], False)
            cache[name] = result
            return result

        target = token["aliasTarget"]

        if target in visiting:
            result = (None, list(visiting) + [target], True)
            cache[name] = result
            return result

        child_val, child_chain, child_circular = _resolve(target, visiting | {name})
        result = (child_val, [name] + child_chain, child_circular)
        cache[name] = result
        return result

    output = []
    circular_names = set()

    for token in tokens:
        t = dict(token)
        val, chain, is_circular = _resolve(t["figmaName"], set())
        t["resolvedValue"] = val
        t["resolvedChain"] = chain
        t["circularAlias"] = is_circular
        if is_circular:
            circular_names.update(chain)
        output.append(t)

    return output, circular_names


def summarize(tokens: list, circular_names: set) -> dict:
    """Return a summary dict for stderr reporting."""
    alias_count = sum(1 for t in tokens if t.get("isAlias"))
    resolved_count = sum(1 for t in tokens if t.get("isAlias") and t.get("resolvedValue") is not None)
    unresolved = [t["figmaName"] for t in tokens
                  if t.get("isAlias") and t.get("resolvedValue") is None and not t.get("circularAlias")]
    return {
        "total": len(tokens),
        "aliases": alias_count,
        "resolved": resolved_count,
        "circular": len(circular_names),
        "unresolved": unresolved,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Resolve alias chains in normalized-tokens.json",
        prog="figma_primitives resolve-aliases",
    )
    parser.add_argument("--input", required=True, help="normalized-tokens.json from parse-tokens")
    parser.add_argument("--output", required=True, help="Output path (annotated tokens)")
    args = parser.parse_args(argv)

    with open(args.input) as f:
        tokens = json.load(f)

    resolved, circular_names = resolve(tokens)
    summary = summarize(resolved, circular_names)

    print(f"Tokens: {summary['total']}  Aliases: {summary['aliases']}  "
          f"Resolved: {summary['resolved']}  Circular: {summary['circular']}", file=sys.stderr)

    if circular_names:
        print(f"WARNING: Circular alias chains detected:", file=sys.stderr)
        for name in sorted(circular_names):
            print(f"  {name}", file=sys.stderr)

    if summary["unresolved"]:
        print(f"WARNING: {len(summary['unresolved'])} aliases could not be resolved (target missing):",
              file=sys.stderr)
        for name in summary["unresolved"][:10]:
            print(f"  {name}", file=sys.stderr)
        if len(summary["unresolved"]) > 10:
            print(f"  ... and {len(summary['unresolved']) - 10} more", file=sys.stderr)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(resolved, f, indent=2)
    print(f"Wrote: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
