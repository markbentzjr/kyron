#!/bin/bash
# Fetch Florida DBPR public restaurant extracts (7 districts) into raw/.
set -euo pipefail
cd "$(dirname "$0")"; mkdir -p raw
B=https://www2.myfloridalicense.com/sto/file_download/extracts
for n in 1 2 3 4 5 6 7; do
  curl -sfL --retry 3 -o "raw/hrfood$n.csv" "$B/hrfood$n.csv"
  curl -sfL --retry 3 -o "raw/${n}fdinspi.csv" "$B/${n}fdinspi.csv"
done
ls -la raw
