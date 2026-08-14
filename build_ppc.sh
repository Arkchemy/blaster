#!/bin/sh
# Compiles a testdata/*.c source as an unstripped, big-endian PowerPC32
# relocatable object -- the recomp tool's input.
#
# -fwrapv -fno-sanitize=undefined: without these, zig cc/clang inserts
# UBSan-style trap sequences around signed arithmetic (overflow checks),
# which drags in instructions well outside this milestone's supported
# subset and isn't representative of how a retail game binary is built
# anyway.
set -e
cd "$(dirname "$0")/.."

ZIG="${ZIG:-$HOME/devtools/zig/zig}"
SRC="${1:-testdata/arithmetic.c}"
OUT="${2:-/tmp/$(basename "$SRC" .c)_ppc.o}"

"$ZIG" cc -target powerpc-freestanding-eabi -O0 -fwrapv -fno-sanitize=undefined \
    -c "$SRC" -o "$OUT"

echo "wrote $OUT"
