#!/usr/bin/env bash
set -e

echo "Starting Food_Kub Backend API on 127.0.0.1:8000..."
(cd blackend_py && python -m uvicorn main:app --host 127.0.0.1 --port 8000) &

sleep 2

echo "Starting Food_Kub Frontend Web on 0.0.0.0:${PORT:-8001}..."
cd front_py
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8001}"
