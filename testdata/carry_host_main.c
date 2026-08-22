#include <stdio.h>

long long compute(unsigned int a, unsigned int b);

int main(void) {
    printf("%lld\n", compute(0x12345678u, 0x9ABCDEF0u));
    return 0;
}
