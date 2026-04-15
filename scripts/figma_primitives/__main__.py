"""
figma_primitives CLI router.

Usage:
    python -m figma_primitives <subcommand> [options]

Subcommands:
    parse-tokens        Parse CSS/Tailwind/Style Dictionary/Tokens Studio → normalized-tokens.json
    resolve-aliases     Flatten alias chains in normalized-tokens.json
    diff-tokens         Diff normalized tokens against Figma registry → drift-manifest.yaml
    generate-css        Generate CSS custom properties from figma-registry.json
    generate-utilities  Generate CSS utility classes from figma-registry.json
    scan-unbound        Find unbound fills/strokes/corners in a Figma export
    prep-bind           Generate Phase 4a-4d bind scripts from Phase 1+2 JSON
    prep-idmap          Generate Phase 3 swap script from Phase 2 idMap JSON
    audit               Registry structural audit → audit-report.yaml

Run `python -m figma_primitives <subcommand> --help` for per-subcommand options.
"""

import sys


SUBCOMMANDS = {
    "parse-tokens":       ("parse_tokens",       "main"),
    "resolve-aliases":    ("resolve_aliases",     "main"),
    "diff-tokens":        ("diff_tokens",         "main"),
    "generate-css":       ("generate_css",        "main"),
    "generate-utilities": ("generate_utilities",  "main"),
    "scan-unbound":       ("scan_unbound",        "main"),
    "prep-bind":          ("prep_bind",           "main"),
    "prep-idmap":         ("prep_idmap",          "main"),
    "audit":              ("audit",               "main"),
}


def _usage():
    print(__doc__.strip(), file=sys.stderr)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _usage()
        sys.exit(0)

    subcommand = sys.argv[1]
    if subcommand not in SUBCOMMANDS:
        print(f"ERROR: Unknown subcommand '{subcommand}'", file=sys.stderr)
        print(f"Valid subcommands: {', '.join(SUBCOMMANDS)}", file=sys.stderr)
        sys.exit(1)

    module_name, fn_name = SUBCOMMANDS[subcommand]

    # Import the module and call its main(), passing remaining args
    import importlib
    mod = importlib.import_module(f"figma_primitives.{module_name}")
    fn = getattr(mod, fn_name)
    fn(sys.argv[2:])


if __name__ == "__main__":
    main()
