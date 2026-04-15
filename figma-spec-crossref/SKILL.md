---
name: figma-spec-crossref
description: >
  Cross-reference a technical spec or design brief against existing Figma
  components, producing REUSE / EXTEND / CREATE / UNCLEAR verdicts per
  screen or feature. Use when starting design work from requirements and
  needing to know what already exists in Figma. Triggers on: "what does this
  spec mean for Figma," "do we already have components for this,"
  "check if Figma has these components," or after spec-design-interpreter
  produces a design companion.
allowed-tools: Bash(cat *) Bash(ls *)
---

# Figma: Spec Cross-Reference

Augments a spec analysis with live Figma cross-references. Answers the question: "what can we reuse vs. what needs new design work?"

**Prerequisite:** Run `figma-workspace` first to gather context about the target Figma file.

---

## Step 1: Produce Design Companion

Run the `spec-design-interpreter` skill to produce a design companion from the spec. If a design companion already exists (from a prior `spec-design-interpreter` or `design-brief` run), use it as input instead of re-analyzing.

---

## Step 2: Extract Queryable Terms

From the companion doc, pull:
- **Component types** mentioned or implied (drawer, form, modal, table, card, sidebar)
- **Interaction patterns** (progressive disclosure, multi-step wizard, inline edit, drag-and-drop)
- **Data types** implied (user list, role selector, org picker, date range)

Map these to search queries for Figma.

---

## Step 3: Run Figma Context Gathering

Use `search_design_system` with each queryable term. Pull visual specs (`get_design_context`) for matches. Use `figma-workspace` registry to check known component names before querying — registry hits save a round-trip.

---

## Step 4: Produce Cross-Reference

For each screen or component the spec implies, assign a verdict:

| Verdict | Meaning | Action |
|---|---|---|
| **REUSE** | Existing component handles this | Name the component, key, and which variant to use |
| **EXTEND** | Existing component needs a new variant or property | Describe what needs adding |
| **CREATE** | Nothing exists — new component needed | Flag for human design decision |
| **UNCLEAR** | Spec is ambiguous about what's needed | Surface as blocking question |

### Escalation rules

- **REUSE / EXTEND** = high confidence → can proceed to building
- **CREATE** = flag for human design decision before building. Do not invent components.
- **UNCLEAR** = surface as blocking question in the companion doc. Do not assume.

---

## Step 5: Append to Companion Doc

Add a `## Figma Cross-Reference` section:

```markdown
## Figma Cross-Reference

| Spec Implies | Verdict | Component | Action Needed |
|---|---|---|---|
| User create form | REUSE | Drawer v2 + Drawer Form Field | Configure for user fields |
| Role selector | EXTEND | Drawer Form Field | Add Radio Card variant |
| Primary org picker | CREATE | — | New component, needs design |
| Notification preferences | UNCLEAR | — | Spec doesn't define interaction model |
```

Optionally include: list of Figma component keys ready for instantiation.
