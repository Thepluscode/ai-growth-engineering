# Evidence Model

## Evidence classes

- `observation`: directly visible fact
- `customer_quote`: exact customer/prospect language
- `crm`: internal commercial record
- `analytics`: measured funnel/platform data
- `experiment`: controlled result
- `third_party`: reputable external evidence
- `inference`: explicit interpretation, never stored as observation

## Rule

Every material claim must preserve:

```text
SOURCE
↓
EVIDENCE
↓
INFERENCE (if any)
↓
HYPOTHESIS
↓
EXPERIMENT
↓
RESULT
↓
COMMERCIAL CLAIM
```

Unsupported claims are blocked from publication.
