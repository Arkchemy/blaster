#include <stdio.h>

#include "ppc_runtime.h"

void ppc_guarded(PpcContext *ctx);

int main(void) {
    static PpcContext ctx;
    static PpcSharedMemory ctx_shared;
    ctx.shared = &ctx_shared;
    ctx.r[1] = PPC_MEM_SIZE - 256;

    ctx.r[3] = (uint32_t)-5;
    ppc_guarded(&ctx);
    printf("%d\n", (int32_t)ctx.r[3]);

    ctx.r[3] = 7;
    ppc_guarded(&ctx);
    printf("%d\n", (int32_t)ctx.r[3]);

    return 0;
}
