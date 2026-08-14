/* Same purpose as gen_harness_float.c but for testdata/double.c's
 * compute(double, double), which takes/returns double (PPC ABI: f1, f2). */
#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    ctx.r[1] = sizeof(ctx.mem) - 256; /* stack pointer, with headroom for stwu */
    ctx.f[1] = 3.5;
    ctx.f[2] = 7.25;

    ppc_compute(&ctx);

    printf("%.9g\n", ctx.f[1]);
    return 0;
}
