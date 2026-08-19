# AI Growth Engineering

> Engineer measurable customer-acquisition systems that turn market attention into qualified pipeline and revenue.

This repository is **not** a marketing SaaS product. It is the operating system for proving the business before software gets priority.

## Current wedge

- **ICP:** UK cybersecurity consultancies and MSPs
- **Buyer:** Founder / MD / Commercial leader
- **Problem:** Acquisition activity is not reliably becoming qualified pipeline
- **Entry offer:** Growth Leak Teardown
- **Core offer:** 30-Day Pipeline Engineering Sprint
- **Primary channel:** Direct B2B outbound
- **Primary outcome:** First paying customer and measurable revenue evidence

## 30-day gate

Immediate market-test scoreboard:

| Metric | Current / next target |
| --- | ---: |
| Qualified prospects | 20 / 20 |
| Deep researches | 10 / 10 |
| Teardowns completed | 10 / 10 |
| Outreach sent | 0 / 10 |
| Meaningful replies | ? |
| Calls | ? |

The teardown count includes the researched Foresite disqualification. Littlefish replaces Foresite in
the 20-account qualified pool, while Morcan replaces it in the send-ready batch. Staged drafts do not
count as outreach.

Longer-horizon commercial targets:

| Metric | Target |
| --- | ---: |
| Qualified prospects | 100 |
| Outreach sent | 100 |
| Meaningful responses | 20 |
| Discovery calls | 10 |
| Diagnostics proposed | 5 |
| Commercial proposals | 3 |
| Paying customers | 1 |
| Collected revenue | £5,000 stretch |

## Doctrine

1. Revenue > vanity metrics.
2. Customer evidence > AI-generated assumptions.
3. Experiments > opinions.
4. Qualified pipeline > raw leads.
5. Contribution profit > ROAS screenshots.
6. One ICP, one problem, one offer, one CTA, one primary channel during validation.
7. No proprietary SaaS until repeated paid workflow pain exists.
8. Every claim needs evidence lineage.
9. Every action-producing agent sits behind authority, policy and audit controls.
10. Reusable controls feed the shared Control Plane.

## Quick start

```bash
python -m ai_growth_engineering.cli init --db .age/growth.db
python -m ai_growth_engineering.cli seed-prospects --db .age/growth.db data/seeds/prospects.csv
python -m ai_growth_engineering.cli scoreboard --db .age/growth.db
python -m ai_growth_engineering.cli gate-check --db .age/growth.db
```

Create a teardown packet:

```bash
python -m ai_growth_engineering.cli teardown \
  --db .age/growth.db \
  --company "CloudTech24" \
  --observation "Service pages converge on a generic sales path" \
  --hypothesis "A problem-specific diagnostic CTA may improve qualified booking rate" \
  --metric "qualified_booking_rate"
```

Preregister an experiment:

```bash
python -m ai_growth_engineering.cli experiment-add \
  --db .age/growth.db \
  --experiment-id EXP-ACQ-0001 \
  --hypothesis "Pipeline-leak messaging will produce >=10% meaningful reply rate" \
  --primary-metric meaningful_reply_rate \
  --success-threshold 0.10 \
  --kill-threshold 0.05 \
  --minimum-sample 50
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

## Repository map

```text
src/ai_growth_engineering/  deterministic core + CLI
skills/                     portable workflow skills
policies/                   action and evidence guardrails
templates/                  teardown/discovery artifacts
data/seeds/                 initial prospect working set
docs/                       doctrine, architecture and execution plan
tests/                      deterministic acceptance tests
```
