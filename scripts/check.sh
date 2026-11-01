#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -v
for js in assets/app.js assets/preview.js assets/reconnect.js; do node --check "$js"; done
python3 -m py_compile scripts/porkbun-dns.py
for file in scripts/*.sh startup/*.sh; do sh -n "$file"; done
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
c++ -std=c++17 -I tests/firmware_stub tests/test_firmware.cpp -o "$build/firmware-test"
"$build/firmware-test"
