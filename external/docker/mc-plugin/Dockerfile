# Stage 1: Build the MC plugin (Rust CLI that generates TSV + JSON)
FROM rust:1.86-alpine AS builder

RUN apk add --no-cache pkgconf openssl-dev openssl-libs-static musl-dev

WORKDIR /build

# Copy source from submodule
COPY external/dragncards-mc-plugin/ .

RUN cargo build --release

# Generate card database (TSV) and deck files (JSON) using offline fixtures
RUN cargo run --release -- database --offline --output /build/marvelcdb.tsv
RUN cargo run --release -- decks --offline

# Stage 2: Collect just the plugin artifacts
FROM alpine:3 AS artifacts

COPY --from=builder /build/marvelcdb.tsv /plugin/tsv/marvelcdb.tsv
COPY --from=builder /build/json/ /plugin/json/

# This image is used as a source for COPY --from in other Dockerfiles
