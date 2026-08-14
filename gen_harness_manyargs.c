#include <stdio.h>
#include "ppc_runtime.h"
void ppc_compute(PpcContext *ctx);
int main(void) {
    static PpcContext ctx;
    ctx.r[1] = sizeof(ctx.mem) - 256;
    ppc_compute(&ctx);
    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
