# basis — market-neutral crypto carry & volatility toolkit.
# Stdlib-only Python, so the image is tiny: just the interpreter + the package.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BASIS_MODE=paper \
    BASIS_DATA_DIR=/app/data

WORKDIR /app

# Only what pip needs to build/install the package (keeps the layer cache tight).
COPY pyproject.toml README.md ./
COPY src ./src

# INSTALL_LIVE=1 also pulls the [live] signer deps (eth-account + hyperliquid-python-sdk)
# for testnet/live order signing. Default 0 keeps the paper image stdlib-only and tiny.
ARG INSTALL_LIVE=0
RUN if [ "$INSTALL_LIVE" = "1" ]; then pip install --no-cache-dir ".[live]"; \
    else pip install --no-cache-dir .; fi \
 && mkdir -p /app/data \
 && useradd -u 10001 -m basis \
 && chown -R basis /app
USER basis

# Persist the SQLite books / CSV / heartbeat across container recreation.
VOLUME ["/app/data"]

# Healthy = the supervisor loop wrote a fresh heartbeat.
HEALTHCHECK --interval=5m --timeout=10s --start-period=3m --retries=3 \
  CMD python -m basis.live.healthcheck || exit 1

# Default process: the self-healing scheduler (the web service overrides CMD).
CMD ["python", "-m", "basis.live.scheduler"]
