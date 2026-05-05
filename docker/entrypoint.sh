#!/bin/sh
set -e
cd /app
echo "Running Alembic migrations..."
alembic upgrade head
echo "Starting bot..."
exec "$@"
