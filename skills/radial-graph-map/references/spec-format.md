# Graph Spec Format & Extraction Recipes

Everything `scripts/radial_graph.py` consumes is one JSON file. This document
gives the full schema, then recipes for building specs from common sources.

## Full schema

```json
{
  "title":    "Human title rendered top-left",
  "subtitle": "One line of context (sources, date, scope)",
  "footer":   "Bottom-right credit line (provenance, generated-by, date)",
  "root":     "node-id of the focal entity, or null for auto (highest degree)",

  "types": {
    "my_custom_type": ["#e0e7ff", "#4338ca"]
  },

  "nodes": [
    {
      "id":   "fastow",
      "type": "person",
      "label": "ANDREW FASTOW",
      "subs": ["EVP/CFO · founded LJM/LJM2", "ousted Oct '01"],
      "tip":  "Hover provenance: source, date, verbatim quote."
    }
  ],

  "edges": [
    {
      "source": "fastow", "target": "ljm2",
      "label": "AUTHORED · Aug 2, 2001 directive",
      "style": "green"
    }
  ]
}
```

### Field rules

| Field | Required | Rules |
|---|---|---|
| `nodes[].id` | ✔ | unique string; referenced by edges |
| `nodes[].type` | – | built-ins: `person entity document event amount news legal group place product other`. Custom types via top-level `types` (`[fill, stroke]` hex pair). Unknown → neutral gray. |
| `nodes[].label` | ✔ | ALL-CAPS reads best; keep ≤ ~24 chars or the box widens |
| `nodes[].subs` | – | 1–3 property lines, each ≤ ~40 chars (box auto-sizes) |
| `nodes[].tip` | – | hover provenance — put your evidence here |
| `edges[].label` | ✔ | **every edge needs one**, ≤ ~30 chars; wraps at `·` and `;` |
| `edges[].style` | – | `struct solid co dash green money legal spouse news meet` (see below) |
| `edges[].source/target` | ✔ | must reference existing node ids; self-loops ignored |

### Edge style vocabulary

| style | look | use for |
|---|---|---|
| `struct` | solid slate | verified/structural facts |
| `solid` | solid dark | generic relationships |
| `co` | dashed light gray | co-mention / co-occurrence counts |
| `dash` | dashed gray | generic contextual links |
| `green` | solid green, thick | THE key action (directive, order, approval) |
| `money` | solid amber | payments, fees, losses |
| `legal` | dashed purple | accusations, subpoenas, probes |
| `spouse` | solid pink | family |
| `news` | dashed gray | press reporting |
| `meet` | solid olive | meetings/attendance |

A spec passes the suite's quality gate only if every edge style is in this
vocabulary (extend `STYLES` in the engine if you need more, then re-run tests).

## Minimal example

```json
{
  "title": "Karate club — after the split",
  "nodes": [
    {"id": "mr_hi", "type": "person", "label": "MR. HI", "subs": ["instructor"]},
    {"id": "john_a", "type": "person", "label": "JOHN A.", "subs": ["officer"]}
  ],
  "edges": [
    {"source": "mr_hi", "target": "john_a", "label": "trained · left with Hi", "style": "struct"}
  ]
}
```

## Extraction recipes

### CSV → spec (Python)

```python
import csv, json, collections
rows = list(csv.DictReader(open("people.csv")))
deg = collections.Counter()
for r in rows:
    deg[r["from"]] += 1; deg[r["to"]] += 1
spec = {
  "title": "My network", "subtitle": "from people.csv",
  "root": deg.most_common(1)[0][0],
  "nodes": [{"id": name, "type": "person", "label": name.upper()}
            for name in deg],
  "edges": [{"source": r["from"], "target": r["to"],
             "label": (r.get("relation") or "related")[:30],
             "style": "struct"} for r in rows],
}
json.dump(spec, open("graph.json", "w"), indent=1)
```

### SQLite / SQL → spec

```python
import sqlite3, json
db = sqlite3.connect("data.db")
people = {eid: {"id": eid, "type": "person", "label": name.upper()}
          for eid, name in db.execute("SELECT id, name FROM people")}
edges = [{"source": a, "target": b, "label": kind[:30], "style": "struct"}
         for a, b, kind in db.execute("""
             SELECT src, dst, kind FROM links WHERE weight >= ?""", (threshold,))]
spec = {"title": "DB graph", "root": None, "nodes": list(people.values()), "edges": edges}
```

Rules of thumb for SQL sources: aggregate duplicate pairs into one edge with a
count in the label (`"co-mention 247"`); filter by weight/counts before
mapping — see the scale table in SKILL.md.

### Email corpus → co-mention graph

Count pairs of names appearing together in messages (From + To/Cc/Body hits),
then: node per person, edge per pair with `label = f"co-mention {n}"`,
`style = "co"`, and add semantic edges (`money`, `legal`, `green`) for the
handful of high-signal relationships you verified by reading the actual
messages. Keep `tip` quotes verbatim.

### Org chart / hierarchy → spec

Parent-child rows map directly: `{"source": manager, "target": report,
"label": "direct report", "style": "struct"}`. Add team/group nodes for
departments, and one or two `dash` edges from groups to the product(s) they
deliver — see `examples/simple-org-chart.json`.

### From an LLM/graph-ish analysis (the "dossier" pattern)

When the dataset is documents rather than tables: extract claims first
(who/what/when/amount/source), then build the spec so that:
- node per entity, document, event, and amount, typed accordingly;
- one edge per verified claim, labeled with date + short quote;
- `tip` = full verbatim quote + citation;
- focal person = `root`.
See `examples/fraud-investigation.json` for a complete worked dossier.

## Validating before render

```bash
python3 - <<'EOF'
import json, sys
sys.path.insert(0, "scripts")
import radial_graph as rg
spec = json.load(open("graph.json"))
lay = rg.compute_layout(spec)
print("OK", lay["node_count"], "nodes,", lay["edge_count"], "edges,",
      lay["chord_crossings"], "chord crossings, scale", round(lay["K"], 2))
EOF
```

Then render (SKILL.md step 3) and run the invariant suite (step 4). To lock a
new spec's invariants permanently, append its path to `EXAMPLES` in
`tests/test_invariants.py`.
