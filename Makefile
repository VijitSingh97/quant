PY := PYTHONPATH=src python3

.PHONY: help install dev test test-integration dashboard monitor carry vrp combined histskew robust condor-bt structures skew book size analyze macro backfill carry-scan rotation regime validate histskew2 live-paper live-auto live-monitor live-web log launchd-install launchd-uninstall live-auto-install live-auto-uninstall docker-up docker-down docker-logs clean

help:
	@echo "make install            editable install (pip install -e .)"
	@echo "make dev                editable install + dev deps (pytest)"
	@echo "make test               run unit tests (offline, fast)"
	@echo "make test-integration   live-venue smoke tests (opt-in, network)"
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
	@echo "make rotation           backtest carry rotation vs fixed (net of cost)"
	@echo "make regime             regime study: carry vs vol allocation by regime (#17)"
	@echo "make validate           run the self-validation report now (-> research.db)"
	@echo "make histskew2          condor with REAL historical skew (Tardis) vs static"
	@echo "make live-paper         run one paper reconcile cycle (carry, no real money)"
	@echo "make live-auto          auto-select the best persistent-carry asset and rotate (paper)"
	@echo "make live-monitor       live book status + audit trail"
	@echo "make live-web           web dashboard -> http://localhost:8787"
	@echo "make log                append one row to data/timeseries.csv"
	@echo "make launchd-install    install the hourly logger launchd agent"
	@echo "make launchd-uninstall  remove the launchd agent"
	@echo "make live-auto-install  install the hourly auto-rotating PAPER agent"
	@echo "make live-auto-uninstall remove the auto-rotating agent"
	@echo "make docker-up          build + run the home-server stack (scheduler + web)"
	@echo "make docker-down        stop the docker stack (keeps the data volume)"
	@echo "make docker-logs        tail the scheduler logs"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	$(PY) -m pytest -q

test-integration:
	$(PY) -m pytest -q -m integration -rs

dashboard:
	$(PY) -m basis.dashboard

monitor:
	$(PY) -m basis.monitor

carry:
	$(PY) -m basis.backtests.carry $(YEARS)

vrp:
	$(PY) -m basis.backtests.vrp

condor-bt:
	$(PY) -m basis.backtests.structures

combined:
	$(PY) -m basis.backtests.combined

histskew:
	$(PY) -m basis.backtests.histskew

robust:
	$(PY) -m basis.backtests.robustness

structures:
	$(PY) -m basis.structures

skew:
	$(PY) -m basis.skew

book:
	$(PY) -m basis.book

size:
	$(PY) -m basis.size

analyze:
	$(PY) -m basis.analyze

macro:
	$(PY) -m basis.macro

backfill:
	$(PY) -m basis.backfill --start 2023-09

carry-scan:
	$(PY) -m basis.carryscan

rotation:
	$(PY) -m basis.backtests.rotation

regime:
	$(PY) -m basis.backtests.regime

validate:
	$(PY) -m basis.live.validate --force

histskew2:
	$(PY) -m basis.backtests.structures --histskew

log:
	$(PY) -m basis.logger

live-paper:
	$(PY) -m basis.live.engine

live-auto:
	$(PY) -m basis.live.auto

live-monitor:
	$(PY) -m basis.live.monitor

live-web:
	$(PY) -m basis.live.web

launchd-install:
	./scripts/install_launchd.sh

launchd-uninstall:
	./scripts/uninstall_launchd.sh

live-auto-install:
	./scripts/install_live_auto.sh

live-auto-uninstall:
	./scripts/uninstall_live_auto.sh

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f basis

clean:
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
