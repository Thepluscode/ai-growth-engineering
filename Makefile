PY := python3
PYTHONPATH := src
DB := .age/growth.db

.PHONY: hooks test gate init seed scoreboard capability-map command-center demo clean sweep sweep-schedule

hooks:
	git config core.hooksPath .githooks
	@echo "hooks enabled: commits are restricted to main (see AGENTS.md)"

gate:
	$(PY) scripts/build_tree.py --selftest
	$(PY) scripts/build_tree.py --check
	$(PY) scripts/scope_gate.py --selftest
	$(PY) scripts/scope_gate.py

test: gate
	PYTHONPATH=$(PYTHONPATH) $(PY) -m unittest discover -s tests -v

init:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli init --db $(DB)

seed: init
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli seed-prospects --db $(DB) experiments/EXP-ACQ-0001/prospects.csv

capability-map:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli capability-map

scoreboard:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli scoreboard --db $(DB)

command-center: demo
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli command-center --db $(DB) --open-browser

demo: seed
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli seed-registries --db $(DB)
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli experiment-add --db $(DB) --experiment-id EXP-ACQ-0001 --hypothesis "Pipeline-leak messaging will produce >=10% meaningful reply rate" --primary-metric meaningful_reply_rate --success-threshold 0.10 --review-threshold 0.05 --minimum-sample 50 || true
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli experiment-add --db $(DB) --experiment-id EXP-ACQ-0002 --hypothesis "The same message delivered to a named buyer's own mailbox will produce >=10% meaningful reply rate" --primary-metric meaningful_reply_rate --success-threshold 0.10 --review-threshold 0.05 --minimum-sample 30 || true
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli import-outreach --db $(DB) experiments/EXP-ACQ-0001/sales/outreach.csv
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli experiment-result --db $(DB) --experiment-id EXP-ACQ-0001 --sample-size 50 --observed-value 0.0 --learning "50 counted sends, 0 meaningful replies. 48 of 50 went to a role inbox; 2 reached a named buyer. See experiments/EXP-ACQ-0001/VERDICT.md"
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli scoreboard --db $(DB)
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli recipient-split --db $(DB)

sweep:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli sweep-sources --db $(DB) --min-interval-hours 0 --pause-seconds 2

sweep-schedule:
	scripts/sweep-cron.sh install

clean:
	rm -rf .age __pycache__ src/ai_growth_engineering/__pycache__ tests/__pycache__
