# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Install runtime dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt

# Install the operator package itself.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --prefix=/install --no-deps .

# ---- runtime image ----
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Copy the installed site-packages and console scripts from the builder.
COPY --from=builder /install /usr/local

# Run as an unprivileged user. (Note: Debian already ships a system user named
# "operator", so we use a distinct name to avoid a UID/name collision.)
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
USER 10001

EXPOSE 8080
ENTRYPOINT ["slo-operator"]
