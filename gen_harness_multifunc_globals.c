/* Same purpose as gen_harness_globals.c, but testdata/multifunc_globals.c
 * specifically checks that *different* functions (bump, read_shared,
 * compute) resolve the same global to the same synthetic address --
 * assign_global_addrs runs once per program, not once per function, and
 * this is the test that would catch it if that stopped being true. */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    ctx.r[1] = sizeof(ctx.mem) - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);
    ctx.r[3] = 10;
    ctx.r[4] = 20;

    ppc_compute(&ctx);

    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
