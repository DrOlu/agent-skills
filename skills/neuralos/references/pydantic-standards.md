# Pydantic model standards (v2)

## Non-negotiables in generated models

- `model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)` —
  unknown columns are errors, not surprises.
- One class per table / record shape, PascalCase from the table name.
- Every field carries a `description` with its observed statistics
  (type, db type, min/max, null counts, example values).
- `Optional[...] = None` exactly where nulls were observed — nowhere else.
- datetime fields are annotated `datetime` with a `field_validator(mode="before")`
  that tries every datetime format the profiler saw, then rejects.

## Type mapping

| Profile detected_type | Python annotation | Constraints added |
|---|---|---|
| integer | `int` | `ge=min, le=max` |
| number | `float` | `ge=min, le=max` |
| boolean | `bool` | — |
| datetime | `datetime` | before-validator over DT_FORMATS |
| string (≤12 distinct) | `Literal["a", "b", …]` | — |
| string | `str` | `min_length, max_length` |
| log capture | `str` | `pattern` from the template regex |
| nullable variant | `Optional[X] = None` | same constraints |

## Editing rules (the model is a draft you finalize)

- Rename cryptic columns in the model, not in the bridge — keep one source of
  truth for field names per layer.
- Promote string columns to domain Enums when the user supplies labels
  (e.g. Status 0–6 → New/Assigned/…); keep the raw value in a validator.
- `extra="forbid"` may be relaxed to `"ignore"` for sources that append new
  columns routinely — note the decision in the class docstring.
- Money is `decimal.Decimal` with a validator when precision matters; the
  generator emits float, which is fine for counts and dashboards only.

## Verification hook

The generator's `bridge` counts every parse into `_VALIDATION`
(parsed/failed/errors[≤5]). Coverage below ~95% means: sample missed dirty
rows, constraints are too tight, or the source mutates. Fix the model, not the
data — and re-run Phase 4.
