FROM rust:1-bookworm@sha256:114c7a4425406451c2866b6aafe69fe29b1b298832db1277d411ac73c82d04d6 AS builder

WORKDIR /build

COPY Cargo.toml Cargo.lock ./
COPY src ./src

# Two jobs: a parallel Rust build under a per-user pids limit (rootless
# Docker in the lab) took the daemon down once (2026-10-07).
ENV CARGO_BUILD_JOBS=2

RUN cargo build --release --locked

# resieve-watch (compose service): the watcher and resieve, which it runs
# (also by hand: tools/resieve).
FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587 AS watch

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder \
    /build/target/release/mailstack-resieve \
    /usr/local/bin/mailstack-resieve
COPY watch.py /usr/local/bin/resieve-watch

ENTRYPOINT ["python3", "/usr/local/bin/resieve-watch"]
