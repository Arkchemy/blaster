/* Same purpose as gen_harness.c but for testdata/mixed_double.c's
 * compute(double, int *, int) -- an integration test combining
 * int-array accumulation into a double, int-to-double conversion, and
 * double abs-via-negate, all through already-supported instructions. No
 * new opcodes here; this exists to catch interaction bugs between
 * features that each pass their own dedicated test individually. */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    static PpcSharedMemory ctx_shared;
    ctx.shared = &ctx_shared;
    ctx.r[1] = PPC_MEM_SIZE - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);
    ctx.f[1] = -3.5;

    const uint32_t arr_addr = 0x1000;
    int arr[5] = {1, 2, 3, 4, 5};
    for (int i = 0; i < 5; i++) {
        ppc_store_u32(&ctx, arr_addr + (uint32_t)i * 4, (uint32_t)arr[i]);
    }
    ctx.r[3] = arr_addr;
    ctx.r[4] = 5;

    ppc_compute(&ctx);

    printf("%.9g\n", ctx.f[1]);
    return 0;
}
