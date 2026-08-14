#include <stdio.h>

#include "ppc_runtime.h"

void ppc_guarded(PpcContext *ctx);

int main(void) {
    static PpcContext ctx;
    ctx.r[1] = sizeof(ctx.mem) - 256;

    ctx.r[3] = (uint32_t)-5;
    ppc_guarded(&ctx);
    printf("%d\n", (int32_t)ctx.r[3]);

    ctx.r[3] = 7;
    ppc_guarded(&ctx);
    printf("%d\n", (int32_t)ctx.r[3]);

    return 0;
}
