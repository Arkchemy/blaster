/* Same purpose as gen_harness.c but for testdata/carry.c's compute(unsigned
 * int, unsigned int), which takes two args (PPC ABI: r3, r4) and returns a
 * 64-bit value split across two registers (PPC ABI: high word in r3, low
 * word in r4). */
#include <stdio.h>
#include <stdint.h>

#include "ppc_runtime.h"

void ppc_compute(PpcContext *ctx);
void ppc_init_globals(PpcContext *ctx);

int main(void) {
    static PpcContext ctx; /* zero-initialized by BSS */
    ctx.r[1] = sizeof(ctx.mem) - 256; /* stack pointer, with headroom for stwu */
    ppc_init_globals(&ctx);
    ctx.r[3] = 0x12345678u;
    ctx.r[4] = 0x9ABCDEF0u;

    ppc_compute(&ctx);

    int64_t result = ((int64_t)(int32_t)ctx.r[3] << 32) | (uint32_t)ctx.r[4];
    printf("%lld\n", (long long)result);
    return 0;
}
