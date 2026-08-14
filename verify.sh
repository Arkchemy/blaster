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
testdata/build_ppc.sh testdata/arithmetic.c "$WORK/arithmetic_ppc.o" >/dev/null

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
    echo "PASS (integer/arithmetic): all results match ($GROUND_TRUTH)"
else
    echo "FAIL (integer/arithmetic): results differ (ground truth=$GROUND_TRUTH, host=$HOST_RESULT, arm64=$ARM64_RESULT, stripped=$STRIPPED_RESULT)"
    exit 1
fi

echo ""
echo "== Floating-point pipeline (testdata/floating.c) =="
gcc -O0 testdata/floating.c testdata/float_host_main.c -o "$WORK/float_ground_truth"
FLOAT_GROUND_TRUTH="$("$WORK/float_ground_truth")"
echo "ground truth result: $FLOAT_GROUND_TRUTH"

testdata/build_ppc.sh testdata/floating.c "$WORK/floating_ppc.o" >/dev/null
"$RECOMP" "$WORK/floating_ppc.o" -o "$WORK/float_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/float_generated.c" tools/gen_harness_float.c -o "$WORK/float_generated_host"
FLOAT_HOST_RESULT="$("$WORK/float_generated_host")"
echo "host recompiled result: $FLOAT_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/float_generated.c" tools/gen_harness_float.c -o "$WORK/float_generated_arm64" 2>/dev/null
FLOAT_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/float_generated_arm64")"
echo "arm64 recompiled result (qemu): $FLOAT_ARM64_RESULT"

echo "=========================================="
if [ "$FLOAT_GROUND_TRUTH" = "$FLOAT_HOST_RESULT" ] && [ "$FLOAT_GROUND_TRUTH" = "$FLOAT_ARM64_RESULT" ]; then
    echo "PASS (floating-point): all results match ($FLOAT_GROUND_TRUTH)"
else
    echo "FAIL (floating-point): results differ (ground truth=$FLOAT_GROUND_TRUTH, host=$FLOAT_HOST_RESULT, arm64=$FLOAT_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Bitwise/shift/byte-halfword pipeline (testdata/bitops.c) =="
gcc -O0 testdata/bitops.c testdata/bitops_host_main.c -o "$WORK/bitops_ground_truth"
BITOPS_GROUND_TRUTH="$("$WORK/bitops_ground_truth")"
echo "ground truth result: $BITOPS_GROUND_TRUTH"

testdata/build_ppc.sh testdata/bitops.c "$WORK/bitops_ppc.o" >/dev/null
"$RECOMP" "$WORK/bitops_ppc.o" -o "$WORK/bitops_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/bitops_generated.c" tools/gen_harness.c -o "$WORK/bitops_generated_host"
BITOPS_HOST_RESULT="$("$WORK/bitops_generated_host")"
echo "host recompiled result: $BITOPS_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/bitops_generated.c" tools/gen_harness.c -o "$WORK/bitops_generated_arm64" 2>/dev/null
BITOPS_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/bitops_generated_arm64")"
echo "arm64 recompiled result (qemu): $BITOPS_ARM64_RESULT"

echo "=========================================="
if [ "$BITOPS_GROUND_TRUTH" = "$BITOPS_HOST_RESULT" ] && [ "$BITOPS_GROUND_TRUTH" = "$BITOPS_ARM64_RESULT" ]; then
    echo "PASS (bitwise/shift): all results match ($BITOPS_GROUND_TRUTH)"
else
    echo "FAIL (bitwise/shift): results differ (ground truth=$BITOPS_GROUND_TRUTH, host=$BITOPS_HOST_RESULT, arm64=$BITOPS_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Rotate/mask pipeline (testdata/rotate.c, -O1 -- rlwinm/rlwimi/clrlwi/rotlwi only show up above -O0) =="
gcc -O0 testdata/rotate.c testdata/rotate_host_main.c -o "$WORK/rotate_ground_truth"
ROTATE_GROUND_TRUTH="$("$WORK/rotate_ground_truth")"
echo "ground truth result: $ROTATE_GROUND_TRUTH"

testdata/build_ppc.sh testdata/rotate.c "$WORK/rotate_ppc.o" -O1 >/dev/null
"$RECOMP" "$WORK/rotate_ppc.o" -o "$WORK/rotate_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/rotate_generated.c" tools/gen_harness_rotate.c -o "$WORK/rotate_generated_host"
ROTATE_HOST_RESULT="$("$WORK/rotate_generated_host")"
echo "host recompiled result: $ROTATE_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/rotate_generated.c" tools/gen_harness_rotate.c -o "$WORK/rotate_generated_arm64" 2>/dev/null
ROTATE_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/rotate_generated_arm64")"
echo "arm64 recompiled result (qemu): $ROTATE_ARM64_RESULT"

echo "=========================================="
if [ "$ROTATE_GROUND_TRUTH" = "$ROTATE_HOST_RESULT" ] && [ "$ROTATE_GROUND_TRUTH" = "$ROTATE_ARM64_RESULT" ]; then
    echo "PASS (rotate/mask): all results match ($ROTATE_GROUND_TRUTH)"
else
    echo "FAIL (rotate/mask): results differ (ground truth=$ROTATE_GROUND_TRUTH, host=$ROTATE_HOST_RESULT, arm64=$ROTATE_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Carry (64-bit arithmetic) pipeline (testdata/carry.c) =="
gcc -O0 testdata/carry.c testdata/carry_host_main.c -o "$WORK/carry_ground_truth"
CARRY_GROUND_TRUTH="$("$WORK/carry_ground_truth")"
echo "ground truth result: $CARRY_GROUND_TRUTH"

testdata/build_ppc.sh testdata/carry.c "$WORK/carry_ppc.o" >/dev/null
"$RECOMP" "$WORK/carry_ppc.o" -o "$WORK/carry_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/carry_generated.c" tools/gen_harness_carry.c -o "$WORK/carry_generated_host"
CARRY_HOST_RESULT="$("$WORK/carry_generated_host")"
echo "host recompiled result: $CARRY_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/carry_generated.c" tools/gen_harness_carry.c -o "$WORK/carry_generated_arm64" 2>/dev/null
CARRY_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/carry_generated_arm64")"
echo "arm64 recompiled result (qemu): $CARRY_ARM64_RESULT"

echo "=========================================="
if [ "$CARRY_GROUND_TRUTH" = "$CARRY_HOST_RESULT" ] && [ "$CARRY_GROUND_TRUTH" = "$CARRY_ARM64_RESULT" ]; then
    echo "PASS (carry/64-bit): all results match ($CARRY_GROUND_TRUTH)"
else
    echo "FAIL (carry/64-bit): results differ (ground truth=$CARRY_GROUND_TRUTH, host=$CARRY_HOST_RESULT, arm64=$CARRY_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Division pipeline (testdata/division.c) =="
gcc -O0 testdata/division.c testdata/division_host_main.c -o "$WORK/division_ground_truth"
DIVISION_GROUND_TRUTH="$("$WORK/division_ground_truth")"
echo "ground truth result: $DIVISION_GROUND_TRUTH"

testdata/build_ppc.sh testdata/division.c "$WORK/division_ppc.o" >/dev/null
"$RECOMP" "$WORK/division_ppc.o" -o "$WORK/division_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/division_generated.c" tools/gen_harness_division.c -o "$WORK/division_generated_host"
DIVISION_HOST_RESULT="$("$WORK/division_generated_host")"
echo "host recompiled result: $DIVISION_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/division_generated.c" tools/gen_harness_division.c -o "$WORK/division_generated_arm64" 2>/dev/null
DIVISION_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/division_generated_arm64")"
echo "arm64 recompiled result (qemu): $DIVISION_ARM64_RESULT"

echo "=========================================="
if [ "$DIVISION_GROUND_TRUTH" = "$DIVISION_HOST_RESULT" ] && [ "$DIVISION_GROUND_TRUTH" = "$DIVISION_ARM64_RESULT" ]; then
    echo "PASS (division): all results match ($DIVISION_GROUND_TRUTH)"
else
    echo "FAIL (division): results differ (ground truth=$DIVISION_GROUND_TRUTH, host=$DIVISION_HOST_RESULT, arm64=$DIVISION_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Indexed load/store pipeline (testdata/indexed.c) =="
gcc -O0 testdata/indexed.c testdata/indexed_host_main.c -o "$WORK/indexed_ground_truth"
INDEXED_GROUND_TRUTH="$("$WORK/indexed_ground_truth")"
echo "ground truth result: $INDEXED_GROUND_TRUTH"

testdata/build_ppc.sh testdata/indexed.c "$WORK/indexed_ppc.o" >/dev/null
"$RECOMP" "$WORK/indexed_ppc.o" -o "$WORK/indexed_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/indexed_generated.c" tools/gen_harness_indexed.c -o "$WORK/indexed_generated_host"
INDEXED_HOST_RESULT="$("$WORK/indexed_generated_host")"
echo "host recompiled result: $INDEXED_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/indexed_generated.c" tools/gen_harness_indexed.c -o "$WORK/indexed_generated_arm64" 2>/dev/null
INDEXED_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/indexed_generated_arm64")"
echo "arm64 recompiled result (qemu): $INDEXED_ARM64_RESULT"

echo "=========================================="
if [ "$INDEXED_GROUND_TRUTH" = "$INDEXED_HOST_RESULT" ] && [ "$INDEXED_GROUND_TRUTH" = "$INDEXED_ARM64_RESULT" ]; then
    echo "PASS (indexed load/store): all results match ($INDEXED_GROUND_TRUTH)"
else
    echo "FAIL (indexed load/store): results differ (ground truth=$INDEXED_GROUND_TRUTH, host=$INDEXED_HOST_RESULT, arm64=$INDEXED_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Float comparison pipeline (testdata/fcmp.c) =="
gcc -O0 testdata/fcmp.c testdata/fcmp_host_main.c -o "$WORK/fcmp_ground_truth"
FCMP_GROUND_TRUTH="$("$WORK/fcmp_ground_truth")"
echo "ground truth result: $FCMP_GROUND_TRUTH"

testdata/build_ppc.sh testdata/fcmp.c "$WORK/fcmp_ppc.o" >/dev/null
"$RECOMP" "$WORK/fcmp_ppc.o" -o "$WORK/fcmp_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/fcmp_generated.c" tools/gen_harness_fcmp.c -o "$WORK/fcmp_generated_host"
FCMP_HOST_RESULT="$("$WORK/fcmp_generated_host")"
echo "host recompiled result: $FCMP_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/fcmp_generated.c" tools/gen_harness_fcmp.c -o "$WORK/fcmp_generated_arm64" 2>/dev/null
FCMP_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/fcmp_generated_arm64")"
echo "arm64 recompiled result (qemu): $FCMP_ARM64_RESULT"

echo "=========================================="
if [ "$FCMP_GROUND_TRUTH" = "$FCMP_HOST_RESULT" ] && [ "$FCMP_GROUND_TRUTH" = "$FCMP_ARM64_RESULT" ]; then
    echo "PASS (float comparison): all results match ($FCMP_GROUND_TRUTH)"
else
    echo "FAIL (float comparison): results differ (ground truth=$FCMP_GROUND_TRUTH, host=$FCMP_HOST_RESULT, arm64=$FCMP_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== mulhw/mulhwu pipeline (testdata/mulhw.c, -O1 -- division-by-constant only shows up above -O0) =="
gcc -O0 testdata/mulhw.c testdata/mulhw_host_main.c -o "$WORK/mulhw_ground_truth"
MULHW_GROUND_TRUTH="$("$WORK/mulhw_ground_truth")"
echo "ground truth result: $MULHW_GROUND_TRUTH"

testdata/build_ppc.sh testdata/mulhw.c "$WORK/mulhw_ppc.o" -O1 >/dev/null
"$RECOMP" "$WORK/mulhw_ppc.o" -o "$WORK/mulhw_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/mulhw_generated.c" tools/gen_harness_mulhw.c -o "$WORK/mulhw_generated_host"
MULHW_HOST_RESULT="$("$WORK/mulhw_generated_host")"
echo "host recompiled result: $MULHW_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/mulhw_generated.c" tools/gen_harness_mulhw.c -o "$WORK/mulhw_generated_arm64" 2>/dev/null
MULHW_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/mulhw_generated_arm64")"
echo "arm64 recompiled result (qemu): $MULHW_ARM64_RESULT"

echo "=========================================="
if [ "$MULHW_GROUND_TRUTH" = "$MULHW_HOST_RESULT" ] && [ "$MULHW_GROUND_TRUTH" = "$MULHW_ARM64_RESULT" ]; then
    echo "PASS (mulhw/mulhwu): all results match ($MULHW_GROUND_TRUTH)"
else
    echo "FAIL (mulhw/mulhwu): results differ (ground truth=$MULHW_GROUND_TRUTH, host=$MULHW_HOST_RESULT, arm64=$MULHW_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Double-precision pipeline (testdata/double.c) =="
gcc -O0 testdata/double.c testdata/double_host_main.c -o "$WORK/double_ground_truth"
DOUBLE_GROUND_TRUTH="$("$WORK/double_ground_truth")"
echo "ground truth result: $DOUBLE_GROUND_TRUTH"

testdata/build_ppc.sh testdata/double.c "$WORK/double_ppc.o" >/dev/null
"$RECOMP" "$WORK/double_ppc.o" -o "$WORK/double_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/double_generated.c" tools/gen_harness_double.c -o "$WORK/double_generated_host"
DOUBLE_HOST_RESULT="$("$WORK/double_generated_host")"
echo "host recompiled result: $DOUBLE_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/double_generated.c" tools/gen_harness_double.c -o "$WORK/double_generated_arm64" 2>/dev/null
DOUBLE_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/double_generated_arm64")"
echo "arm64 recompiled result (qemu): $DOUBLE_ARM64_RESULT"

echo "=========================================="
if [ "$DOUBLE_GROUND_TRUTH" = "$DOUBLE_HOST_RESULT" ] && [ "$DOUBLE_GROUND_TRUTH" = "$DOUBLE_ARM64_RESULT" ]; then
    echo "PASS (double-precision): all results match ($DOUBLE_GROUND_TRUTH)"
else
    echo "FAIL (double-precision): results differ (ground truth=$DOUBLE_GROUND_TRUTH, host=$DOUBLE_HOST_RESULT, arm64=$DOUBLE_ARM64_RESULT)"
    exit 1
fi

echo ""
echo "== Misc bitops pipeline (testdata/misc_bitops.c -- cntlzw/andc/eqv/subfic) =="
gcc -O0 testdata/misc_bitops.c testdata/misc_bitops_host_main.c -o "$WORK/misc_bitops_ground_truth"
MISC_GROUND_TRUTH="$("$WORK/misc_bitops_ground_truth")"
echo "ground truth result: $MISC_GROUND_TRUTH"

testdata/build_ppc.sh testdata/misc_bitops.c "$WORK/misc_bitops_ppc.o" >/dev/null
"$RECOMP" "$WORK/misc_bitops_ppc.o" -o "$WORK/misc_bitops_generated.c" >&2

gcc -O0 -Irecomp/include "$WORK/misc_bitops_generated.c" tools/gen_harness_misc_bitops.c -o "$WORK/misc_bitops_generated_host"
MISC_HOST_RESULT="$("$WORK/misc_bitops_generated_host")"
echo "host recompiled result: $MISC_HOST_RESULT"

"$ZIG" cc -target aarch64-linux-musl -static -Irecomp/include \
    "$WORK/misc_bitops_generated.c" tools/gen_harness_misc_bitops.c -o "$WORK/misc_bitops_generated_arm64" 2>/dev/null
MISC_ARM64_RESULT="$("$QEMU_AARCH64" "$WORK/misc_bitops_generated_arm64")"
echo "arm64 recompiled result (qemu): $MISC_ARM64_RESULT"

echo "=========================================="
if [ "$MISC_GROUND_TRUTH" = "$MISC_HOST_RESULT" ] && [ "$MISC_GROUND_TRUTH" = "$MISC_ARM64_RESULT" ]; then
    echo "PASS (misc bitops): all results match ($MISC_GROUND_TRUTH)"
    exit 0
else
    echo "FAIL (misc bitops): results differ (ground truth=$MISC_GROUND_TRUTH, host=$MISC_HOST_RESULT, arm64=$MISC_ARM64_RESULT)"
    exit 1
fi
