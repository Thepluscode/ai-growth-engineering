# Digital Marketing Project

> Build and operate measurable digital marketing systems that acquire customers, increase conversion, and grow revenue.

**Digital Marketing is what this project does. AI Growth Engineering is how it does it:** an
evidence-driven, experimental and AI-enabled methodology for researching markets, creating and
distributing marketing, measuring acquisition economics, and improving revenue outcomes across
digital channels.

This repository is the engineering and automation layer of the Digital Marketing Project. It is not
a customer-facing marketing SaaS product, and it is not locked to cybersecurity, MSPs, outbound, or
any single channel. Markets are tested one at a time; software is built only when repeated marketing
workflows and customer evidence justify it.

## Project scope

1. **Market intelligence:** market, competitor and customer research; demand discovery
2. **Strategy:** segmentation, brand, positioning, offers, pricing and messaging
3. **Creative:** copy, images, UGC, video, hooks and creative testing
4. **Distribution:** SEO, AI search, social, content, email, paid media, outbound, affiliates, creators and partnerships
5. **Conversion:** ecommerce, landing pages, CRO, lead capture, qualification and booking
6. **Revenue:** marketing automation, CRM, lifecycle, sales handoff, retention and expansion
7. **Measurement:** attribution, CAC, LTV, contribution profit, pipeline and revenue
8. **AI Growth Engineering:** skills, agents, automation, experiments, evidence, policies and controls

## Active market experiment

`EXP-ACQ-0001` is the first market experiment, not the project definition.

- **Market:** UK cybersecurity consultancies and MSPs
- **Buyer:** Founder / MD / Commercial leader
- **Problem hypothesis:** Acquisition activity is not reliably becoming qualified pipeline
- **Entry offer:** Growth Leak Teardown
- **Core offer:** 30-Day Pipeline Engineering Sprint
- **Primary channel:** Direct B2B outbound
- **Primary outcome:** Evidence that the message earns qualified conversations

## 30-day gate

Immediate market-test scoreboard:

| Metric | Current / next target |
| --- | ---: |
| Qualified prospects | 20 / 20 |
| Deep researches | 10 / 10 |
| Teardowns completed | 10 / 10 |
| Outreach sent | 10 / 10 |
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
6. Within each validation experiment, use one ICP, one problem, one offer, one CTA, one primary channel and one primary metric.
7. No proprietary SaaS until repeated paid workflow pain exists.
8. Every claim needs evidence lineage.
9. Every action-producing agent sits behind authority, policy and audit controls.
10. Reusable controls feed the shared Control Plane.

## Quick start

```bash
python -m ai_growth_engineering.cli init --db .age/growth.db
python -m ai_growth_engineering.cli seed-prospects --db .age/growth.db experiments/EXP-ACQ-0001/prospects.csv
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
capability_map.json         full Digital Marketing scope, 106 capabilities with build status
src/ai_growth_engineering/  engineering layer: deterministic evidence core + CLI
scripts/scope_gate.py       keeps the engine market-neutral (runs in make test + CI)
experiments/EXP-ACQ-0001/   the UK cyber/MSP experiment: prospects, queue, teardowns, outreach
skills/                     portable workflow skills
policies/                   action and evidence guardrails
templates/                  teardown/discovery artifacts
docs/                       Digital Marketing architecture, decisions and execution plan
tests/                      deterministic acceptance tests
```
