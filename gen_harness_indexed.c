/* Same purpose as gen_harness.c but for testdata/indexed.c's
 * compute(int *arr, int n), which takes a pointer -- the array is written
 * into ctx.mem at a fixed offset (well clear of the stack, which grows
 * down from near the top of mem) and that offset is passed as the
 * "pointer" in r3, PPC ABI arg 1. */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    ctx.r[1] = sizeof(ctx.mem) - 256; /* stack pointer, with headroom for stwu */

    const uint32_t arr_addr = 0x1000;
    for (int i = 0; i < 150; i++) {
        ppc_store_u32(&ctx, arr_addr + (uint32_t)i * 4, (uint32_t)(i - 50));
    }
    ctx.r[3] = arr_addr;
    ctx.r[4] = 120;

    ppc_compute(&ctx);

    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
