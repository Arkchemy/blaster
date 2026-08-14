/* Same purpose as gen_harness.c but for testdata/division.c's
 * compute(int, int, unsigned, unsigned), which takes four args (PPC ABI:
 * r3-r6). */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    ctx.r[1] = sizeof(ctx.mem) - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);
    ctx.r[3] = (uint32_t)17;
    ctx.r[4] = (uint32_t)5;
    ctx.r[5] = 100u;
    ctx.r[6] = 7u;

    ppc_compute(&ctx);

    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
