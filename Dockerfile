FROM python:3.11-slim

LABEL lane="kucoin-lane"
LABEL lane_number="4"
LABEL description="KuCoin margin trading bot — autonomous, self-healing, self-upgrading"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY config/ config/
COPY governance/ governance/
COPY tests/ tests/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV EXECUTION_MODE=dry_run

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/app/src/execution/execution_engine.py') else 1)"

ENTRYPOINT ["python", "-m", "src.execution.execution_engine"]
