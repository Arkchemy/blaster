#!/bin/sh
# Compiles testdata/arithmetic.c as an unstripped, big-endian PowerPC32
# relocatable object -- the recomp tool's input for this milestone.
#
# -fwrapv -fno-sanitize=undefined: without these, zig cc/clang inserts
# UBSan-style trap sequences around signed arithmetic (overflow checks),
# which drags in instructions well outside this milestone's supported
# subset and isn't representative of how a retail game binary is built
# anyway.
set -e
cd "$(dirname "$0")/.."

ZIG="${ZIG:-$HOME/devtools/zig/zig}"
OUT="${1:-/tmp/arithmetic_ppc.o}"

"$ZIG" cc -target powerpc-freestanding-eabi -O0 -fwrapv -fno-sanitize=undefined \
    -c testdata/arithmetic.c -o "$OUT"

echo "wrote $OUT"
