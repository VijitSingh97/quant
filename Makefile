PY := PYTHONPATH=src python3

.PHONY: help install dev test dashboard monitor carry vrp combined histskew robust condor-bt structures skew book size analyze macro backfill carry-scan histskew2 live-paper live-monitor live-web log launchd-install launchd-uninstall clean

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
	@echo "make histskew           historical-skew condor backtest on our logged data (#6)"
	@echo "make robust             robustness / anti-overfit checks (sweep, walk-fwd, costs)"
	@echo "make structures         defined-risk option structures vs live chain"
	@echo "make skew               read the live implied-vol surface / skew"
	@echo "make book               delta-neutral book monitor (net-delta drift)"
	@echo "make size               position sizer (vol-target + fractional Kelly)"
	@echo "make analyze            analyze our own captured data/timeseries.csv"
	@echo "make macro              cross-asset VRP for equities/commodities (SPX/GOLD/OIL)"
	@echo "make backfill           backfill historical skew from Tardis free monthly snapshots"
	@echo "make carry-scan         rank cross-asset funding (best carry to deploy now)"
	@echo "make histskew2          condor with REAL historical skew (Tardis) vs static"
	@echo "make live-paper         run one paper reconcile cycle (carry, no real money)"
	@echo "make live-monitor       live book status + audit trail"
	@echo "make live-web           web dashboard -> http://localhost:8787"
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

histskew:
	$(PY) -m btcvol.backtests.histskew

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

macro:
	$(PY) -m btcvol.macro

backfill:
	$(PY) -m btcvol.backfill --start 2023-09

carry-scan:
	$(PY) -m btcvol.carryscan

histskew2:
	$(PY) -m btcvol.backtests.structures --histskew

log:
	$(PY) -m btcvol.logger

live-paper:
	$(PY) -m btcvol.live.engine

live-monitor:
	$(PY) -m btcvol.live.monitor

live-web:
	$(PY) -m btcvol.live.web

launchd-install:
	./scripts/install_launchd.sh

launchd-uninstall:
	./scripts/uninstall_launchd.sh

clean:
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
