#include <stdio.h>

int compute(unsigned int x, unsigned int y);

int main(void) {
    printf("%d\n", compute(0x0F0F0F0Fu, 0xFF00FF00u));
    return 0;
}
