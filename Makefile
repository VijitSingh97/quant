PY := PYTHONPATH=src python3

.PHONY: help install dev test dashboard monitor carry vrp log launchd-install launchd-uninstall clean

help:
	@echo "make install            editable install (pip install -e .)"
	@echo "make dev                editable install + dev deps (pytest)"
	@echo "make test               run unit tests"
	@echo "make dashboard          one-shot market snapshot"
	@echo "make monitor            cross-venue funding monitor"
	@echo "make carry [YEARS=2]    funding-carry backtest"
	@echo "make vrp                vol-risk-premium backtest"
	@echo "make log                append one row to data/timeseries.csv"
	@echo "make launchd-install    install the hourly logger launchd agent"
	@echo "make launchd-uninstall  remove the launchd agent"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	$(PY) -m pytest -q

dashboard:
	$(PY) -m btcvol.dashboard

monitor:
	$(PY) -m btcvol.monitor

carry:
	$(PY) -m btcvol.backtests.carry $(YEARS)

vrp:
	$(PY) -m btcvol.backtests.vrp

log:
	$(PY) -m btcvol.logger

launchd-install:
	./scripts/install_launchd.sh

launchd-uninstall:
	./scripts/uninstall_launchd.sh

clean:
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
