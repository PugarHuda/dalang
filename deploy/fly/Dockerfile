# DALANG agent keep-online worker (Fly.io) — sends the OKX "online" heartbeat 24/7.
# NOTE: DALANG's paid renders are served by the Vercel endpoint; this worker is ONLY the
# marketplace online-status heartbeat. The wallet session lives on a persistent volume.
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*
# Install the onchainos CLI (linux binary, checksum-verified by the official installer)
RUN curl -sSL https://raw.githubusercontent.com/okx/onchainos-skills/main/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
# session + config persist here (mount a Fly volume at this path)
VOLUME ["/root/.onchainos"]
CMD ["/entrypoint.sh"]
