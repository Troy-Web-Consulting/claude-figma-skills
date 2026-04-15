"""
figma_primitives — deterministic script layer for Figma skills.

Each submodule is idempotent, takes structured JSON/YAML input,
and returns structured JSON/YAML output. No taste judgment lives here.

Usage:
    python -m figma_primitives <subcommand> [--input <file>] [--output <file>]

Subcommands:
    parse-tokens        CSS/Tailwind/Style Dictionary/Tokens Studio → normalized-tokens.json
    resolve-aliases     normalized-tokens.json → resolved aliases flattened in-place
    diff-tokens         normalized-tokens.json + registry → drift-manifest.yaml
    generate-css        registry.json → CSS custom properties file
    generate-utilities  registry.json → CSS utility classes file
    scan-unbound        Figma node export → unbound-report.json
    prep-bind           phase1.json + phase2.json → phase4a-4d Plugin API scripts
    prep-idmap          phase2-idmap.json + node-id → phase3 Plugin API script
    audit               registry.json → audit-report.yaml (naming, tiers, orphans, aliases)
"""

__version__ = "0.2.0"
