#!/usr/bin/env bash
set -euo pipefail

echo "[init] Waiting for mongo1 to accept connections..."
until mongosh --host mongo1:27017 --eval "db.adminCommand('ping')" >/dev/null 2>&1; do
  sleep 2
done

echo "[init] Running replica set init JS..."
mongosh --host mongo1:27017 /mongo-init/init.js

echo "[init] Waiting for PRIMARY election..."
for i in $(seq 1 60); do
  mongosh --host mongo1:27017 --eval "const s=rs.status(); quit(s.members.some(m=>m.stateStr==='PRIMARY')?0:1)" >/dev/null 2>&1     && echo "[init] PRIMARY ready" && exit 0
  sleep 2
done

echo "[init] PRIMARY not detected in time"
exit 1
