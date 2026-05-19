# ---------- build stage ----------
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.txt ./
COPY cjs/ ./cjs/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# ---------- runtime stage ----------
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd --create-home --uid 1000 cjs
USER cjs
WORKDIR /home/cjs

# Copy installed packages and source from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/cjs /usr/local/bin/cjs
COPY --from=builder /app /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["cjs"]
CMD ["--help"]
