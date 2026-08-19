PY := python3
PYTHONPATH := src
DB := .age/growth.db

.PHONY: test init seed scoreboard demo clean

test:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m unittest discover -s tests -v

init:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli init --db $(DB)

seed: init
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli seed-prospects --db $(DB) data/seeds/prospects.csv

scoreboard:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli scoreboard --db $(DB)

demo: seed
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli experiment-add --db $(DB) --experiment-id EXP-ACQ-0001 --hypothesis "Pipeline-leak messaging will produce >=10% meaningful reply rate" --primary-metric meaningful_reply_rate --success-threshold 0.10 --kill-threshold 0.05 --minimum-sample 50 || true
	PYTHONPATH=$(PYTHONPATH) $(PY) -m ai_growth_engineering.cli scoreboard --db $(DB)

clean:
	rm -rf .age __pycache__ src/ai_growth_engineering/__pycache__ tests/__pycache__
