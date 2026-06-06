PY := PYTHONPATH=src python3

.PHONY: help install dev test dashboard monitor carry vrp combined robust condor-bt structures skew book size analyze log launchd-install launchd-uninstall clean

help:
	@echo "make install            editable install (pip install -e .)"
	@echo "make dev                editable install + dev deps (pytest)"
	@echo "make test               run unit tests"
	@echo "make dashboard          one-shot market snapshot"
	@echo "make monitor            cross-venue funding monitor"
	@echo "make carry [YEARS=2]    funding-carry backtest"
	@echo "make vrp                vol-risk-premium backtest"
	@echo "make condor-bt          backtest the monthly condor-selling rule"
	@echo "make combined           combined carry + filtered-condor book backtest"
	@echo "make robust             robustness / anti-overfit checks (sweep, walk-fwd, costs)"
	@echo "make structures         defined-risk option structures vs live chain"
	@echo "make skew               read the live implied-vol surface / skew"
	@echo "make book               delta-neutral book monitor (net-delta drift)"
	@echo "make size               position sizer (vol-target + fractional Kelly)"
	@echo "make analyze            analyze our own captured data/timeseries.csv"
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

condor-bt:
	$(PY) -m btcvol.backtests.structures

combined:
	$(PY) -m btcvol.backtests.combined

robust:
	$(PY) -m btcvol.backtests.robustness

structures:
	$(PY) -m btcvol.structures

skew:
	$(PY) -m btcvol.skew

book:
	$(PY) -m btcvol.book

size:
	$(PY) -m btcvol.size

analyze:
	$(PY) -m btcvol.analyze

log:
	$(PY) -m btcvol.logger

launchd-install:
	./scripts/install_launchd.sh

launchd-uninstall:
	./scripts/uninstall_launchd.sh

clean:
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
