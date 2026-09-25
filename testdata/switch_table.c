/* A switch compiled to a jump table: a table of case addresses in .rodata,
 * loaded with lwzx and jumped through with mtctr/bctr. Built with
 * -mllvm -ppc-min-jump-table-entries=4 (see verify.sh), because clang's
 * 32-bit PowerPC backend otherwise lowers even a dense switch to a compare
 * tree; the retail binary's compiler uses tables.
 *
 * Pins a conquertron fix from 2026-09-26: recomp only understood a table of
 * branches straight after the bctr, so a jump through a table of addresses
 * went to ppc_dispatch, which knows only function entries, missed, and left
 * the function without running the case -- silently.
 *
 * The cases do different work, including calls, so the compiler cannot turn
 * the switch into a table of values instead. */
__attribute__((noinline)) int twice(int x) { return x * 2 + 1; }
__attribute__((noinline)) int thrice(int x) { return x * 3 - 7; }

__attribute__((noinline)) int route(int op, int x) {
    switch (op) {
        case 0: return x + 17;
        case 1: return twice(x);
        case 2: return x << 3;
        case 3: return thrice(x);
        case 4: return x ^ 0x1234;
        case 5: return x - 1000;
        case 6: return (x >> 2) | 1;
        case 7: return twice(x) + thrice(x);
        case 8: return x * 7;
        case 9: return ~x;
        case 10: return x & 0xf0f0f;
        case 11: return x | 0x0f0f;
        default: return -1;
    }
}

int compute(int mode) {
    int acc = mode * 31 + 5;
    for (int i = 0; i < 36; i++)
        acc = route((i * 5 + mode) % 13, acc) & 0xffffff;
    return acc;
}
