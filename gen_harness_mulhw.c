/* Same purpose as gen_harness.c but for testdata/mulhw.c's
 * compute(int, unsigned int), built at -O1 since division-by-constant
 * (the only thing that emits mulhw/mulhwu) doesn't show up at -O0. */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    ctx.r[1] = sizeof(ctx.mem) - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);
    ctx.r[3] = (uint32_t)12345678;
    ctx.r[4] = 4000000000u;

    ppc_compute(&ctx);

    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
