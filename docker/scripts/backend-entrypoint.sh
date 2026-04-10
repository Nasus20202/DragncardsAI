#!/bin/bash
set -e

echo "==> Installing Hex and Rebar..."
mix local.hex --force
mix local.rebar --force

echo "==> Fetching dependencies..."
mix deps.get

echo "==> Setting up database..."
mix ecto.setup

echo "==> Seeding dev user and Marvel Champions plugin..."
mix run /app/priv/seed_plugin.exs

echo "==> Starting Phoenix server..."
exec mix phx.server
