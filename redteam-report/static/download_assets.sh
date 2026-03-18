#!/usr/bin/env bash
# 下载 Bootstrap CSS 与 Plotly JS，用于报告完全离线使用。仅需在联网环境执行一次。
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Downloading Bootstrap 5.3.3 CSS..."
curl -sL -o css/bootstrap.min.css "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
echo "  -> $(wc -c < css/bootstrap.min.css) bytes"

echo "Downloading Plotly 2.30.0..."
curl -sL -o js/plotly-2.30.0.min.js "https://cdn.plot.ly/plotly-2.30.0.min.js"
echo "  -> $(wc -c < js/plotly-2.30.0.min.js) bytes (expect ~3MB+)"

echo "Done. Reports can now be used fully offline."
