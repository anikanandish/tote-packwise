#!/usr/bin/env sh
# Builds the PackWise packer service on Linux/macOS with g++ or clang++.
set -e
cd "$(dirname "$0")"
mkdir -p build
CXX="${CXX:-g++}"
$CXX -std=c++17 -O2 -Iinclude -Isrc src/main.cpp src/packer_core.cpp src/optimizer_core.cpp -o build/packer_service -pthread
$CXX -std=c++17 -O2 -Isrc tests/test_core.cpp src/packer_core.cpp src/optimizer_core.cpp -o build/test_core
./build/test_core
echo "Done. Start with: ./build/packer_service 8090"
