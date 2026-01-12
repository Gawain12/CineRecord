#!/bin/bash
echo "🚀 Updating CineRecord from git..."
git pull

echo "♻️ Rebuilding Docker container..."
docker compose down
docker compose build --no-cache

echo "▶️ Starting service..."
docker compose up -d

echo "📜 Tailing logs (Ctrl+C to exit)..."
docker logs -f cinerecord
