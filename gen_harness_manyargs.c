#include <stdio.h>
#include "ppc_runtime.h"
void ppc_compute(PpcContext *ctx);
int main(void) {
    static PpcContext ctx;
    static PpcSharedMemory ctx_shared;
    ctx.shared = &ctx_shared;
    ctx.r[1] = PPC_MEM_SIZE - 256;
    ppc_compute(&ctx);
    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
