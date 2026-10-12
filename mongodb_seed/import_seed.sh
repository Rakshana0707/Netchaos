#!/usr/bin/env bash
# ============================================================
# NetChaos - MongoDB Seed Script
# Usage: bash import_seed.sh [--host localhost] [--port 27017]
# ============================================================
HOST=${HOST:-localhost}
PORT=${PORT:-27017}
DB="netchaos"

echo "Importing seed data into MongoDB database: $DB"
echo "Host: $HOST:$PORT"
echo ""

collections=(
  "networks"
  "nodes"
  "links"
  "traffic_simulations"
  "chaos_experiments"
  "failure_detections"
  "recovery_events"
)

for col in "${collections[@]}"; do
  FILE="$(dirname "$0")/${col}.json"
  if [ -f "$FILE" ]; then
    echo "Importing $col ..."
    mongoimport \
      --host "$HOST" \
      --port "$PORT" \
      --db "$DB" \
      --collection "$col" \
      --file "$FILE" \
      --jsonArray \
      --drop
    echo "  ✓ $col imported"
  else
    echo "  ⚠ $FILE not found, skipping"
  fi
done

echo ""
echo "Done! Database '$DB' is ready."
