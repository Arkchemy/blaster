#!/bin/sh
# Idempotent dev-environment setup for Milestone 1 (PowerPC->C recompiler
# PoC). Installs everything under ~/devtools so it doesn't touch system
# paths.
#
# NOTE: devkitPro's site is Cloudflare-blocked from at least one of the
# sandboxes this project has been developed in (403 on every path, even with
# a browser user-agent) -- see the Notion project log entry dated 2026-08-14.
# This script deliberately does NOT depend on devkitPro. It uses Zig's
# bundled clang-based cross-compiler (powerpc-freestanding-eabi and
# aarch64-linux-musl targets) instead, plus a source build of Capstone for
# PowerPC disassembly and a static qemu-aarch64 binary for running the
# cross-compiled ARM64 output without real hardware.
set -e

DEVTOOLS="${DEVTOOLS:-$HOME/devtools}"
mkdir -p "$DEVTOOLS"
cd "$DEVTOOLS"

ZIG_VERSION="0.13.0"
if [ ! -x "$DEVTOOLS/zig/zig" ]; then
    echo "== Installing Zig $ZIG_VERSION =="
    curl -sL -o zig.tar.xz "https://ziglang.org/download/${ZIG_VERSION}/zig-linux-x86_64-${ZIG_VERSION}.tar.xz"
    tar xf zig.tar.xz
    rm -f zig.tar.xz
    mv "zig-linux-x86_64-${ZIG_VERSION}" zig
else
    echo "== Zig already installed =="
fi
"$DEVTOOLS/zig/zig" version

if [ ! -x "$DEVTOOLS/qemu-aarch64-static" ]; then
    echo "== Downloading static qemu-aarch64 =="
    curl -sL -o qemu-aarch64-static \
        "https://github.com/multiarch/qemu-user-static/releases/download/v7.2.0-1/qemu-aarch64-static"
    chmod +x qemu-aarch64-static
else
    echo "== qemu-aarch64-static already present =="
fi
"$DEVTOOLS/qemu-aarch64-static" --version | head -1

if [ ! -f "$DEVTOOLS/capstone-install/lib64/libcapstone.a" ] && [ ! -f "$DEVTOOLS/capstone-install/lib/libcapstone.a" ]; then
    echo "== Building Capstone (PowerPC support) from source =="
    if [ ! -d capstone ]; then
        git clone --depth 1 --branch 5.0.3 https://github.com/capstone-engine/capstone.git
    fi
    mkdir -p capstone/build
    cd capstone/build
    cmake -DCMAKE_BUILD_TYPE=Release \
          -DCAPSTONE_ARCHITECTURE_DEFAULT=OFF \
          -DCAPSTONE_PPC_SUPPORT=ON \
          -DCMAKE_INSTALL_PREFIX="$DEVTOOLS/capstone-install" ..
    make -j"$(nproc)"
    make install
    cd "$DEVTOOLS"
else
    echo "== Capstone already built =="
fi

echo "== Done. Build the recomp tool with: =="
echo "   cmake -S recomp -B recomp/build && cmake --build recomp/build"
