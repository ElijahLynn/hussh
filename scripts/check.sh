#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -v
node --check assets/app.js
for file in scripts/*.sh startup/*.sh; do sh -n "$file"; done
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
c++ -std=c++17 -I tests/firmware_stub tests/test_firmware.cpp -o "$build/firmware-test"
"$build/firmware-test"
