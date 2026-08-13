#!/bin/sh
# End-to-end verification for Milestone 1: recompile testdata/arithmetic.c's
# PowerPC build, then check that both a host-native build and a
# QEMU-emulated ARM64 build of the generated C produce the same result as a
# plain native build of the original source (ground truth).
set -e
cd "$(dirname "$0")/.."

ZIG="${ZIG:-$HOME/devtools/zig/zig}"
QEMU_AARCH64="${QEMU_AARCH64:-$HOME/devtools/qemu-aarch64-static}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== Building recomp tool =="
cmake -S recomp -B recomp/build -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build recomp/build -j"$(nproc)" >/dev/null
RECOMP="recomp/build/recomp"

echo "== Ground truth (native build of original source) =="
gcc -O0 testdata/arithmetic.c testdata/host_main.c -o "$WORK/ground_truth"
GROUND_TRUTH="$("$WORK/ground_truth")"
echo "ground truth result: $GROUND_TRUTH"

echo "== Compiling test program for PowerPC =="
testdata/build_ppc.sh "$WORK/arithmetic_ppc.o" >/dev/null

echo "== Recompiling PPC object to C =="
"$RECOMP" "$WORK/arithmetic_ppc.o" -o "$WORK/generated.c"

echo "== Host-native check =="
gcc -O0 -Irecomp/include "$WORK/generated.c" tools/gen_harness.c -o "$WORK/generated_host"
HOST_RESULT="$("$WORK/generated_host")"
echo "host recompiled result: $HOST_RESULT"

echo "== ARM64 cross-compile + QEMU check =="
"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/generated.c" tools/gen_harness.c -o "$WORK/generated_arm64" 2>/dev/null
ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/generated_arm64")"
echo "arm64 recompiled result (qemu): $ARM64_RESULT"

echo "== Stripped-binary check (heuristic function boundary recovery) =="
"$ZIG" cc -target powerpc-freestanding-eabi -O0 -fwrapv -fno-sanitize=undefined -nostdlib \
    -Wl,-e,compute -o "$WORK/linked.elf" testdata/arithmetic.c
"$RECOMP" --stripped --entry-alias compute "$WORK/linked.elf" -o "$WORK/stripped_generated.c" >&2
gcc -O0 -Irecomp/include "$WORK/stripped_generated.c" tools/gen_harness.c -o "$WORK/stripped_generated_host"
STRIPPED_RESULT="$("$WORK/stripped_generated_host")"
echo "stripped/recovered result: $STRIPPED_RESULT"

echo "=========================================="
if [ "$GROUND_TRUTH" = "$HOST_RESULT" ] && [ "$GROUND_TRUTH" = "$ARM64_RESULT" ] && [ "$GROUND_TRUTH" = "$STRIPPED_RESULT" ]; then
    echo "PASS: all results match ($GROUND_TRUTH)"
    exit 0
else
    echo "FAIL: results differ (ground truth=$GROUND_TRUTH, host=$HOST_RESULT, arm64=$ARM64_RESULT, stripped=$STRIPPED_RESULT)"
    exit 1
fi
