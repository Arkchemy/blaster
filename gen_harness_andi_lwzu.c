#include <stdio.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);

int main(void) {
    static PpcContext ctx;
    static PpcSharedMemory ctx_shared;
    ctx.shared = &ctx_shared;
    ctx.r[1] = PPC_MEM_SIZE - 256;

    uint32_t arr_addr = 0x1000;
    int arr[5] = {10, 20, 30, 40, 50};
    for (int i = 0; i < 5; i++) {
        ppc_store_u32(&ctx, arr_addr + (uint32_t)i * 4, (uint32_t)arr[i]);
    }
    ctx.r[3] = 0x23;
    ctx.r[4] = arr_addr;
    ctx.r[5] = 5;
    ppc_compute(&ctx);

    printf("%d\n", (int32_t)ctx.r[3]);
    return 0;
}
