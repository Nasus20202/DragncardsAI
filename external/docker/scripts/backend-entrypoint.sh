#!/bin/sh
set -e

echo "==> Setting up database..."
mix ecto.setup

echo "==> Seeding dev user and Marvel Champions plugin..."
mix run /app/priv/seed_plugin.exs

echo "==> Starting Phoenix server..."
exec mix phx.server
