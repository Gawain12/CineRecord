FROM rust:1.93-bookworm AS builder

WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
COPY web/static ./web/static
COPY web/templates ./web/templates

RUN cargo build --locked --release -p cinerecord-server

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 cinerecord \
    && mkdir -p /var/lib/cinerecord \
    && chown -R cinerecord:cinerecord /var/lib/cinerecord

COPY --from=builder /src/target/release/cinerecord-server /usr/local/bin/cinerecord

ENV CINERECORD_HOME=/var/lib/cinerecord \
    CINERECORD_HOST=0.0.0.0 \
    CINERECORD_PORT=18000 \
    RUST_LOG=info,tower_http=warn

USER cinerecord
VOLUME ["/var/lib/cinerecord"]
EXPOSE 18000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:18000/api/v2/health || exit 1

ENTRYPOINT ["/usr/local/bin/cinerecord"]
