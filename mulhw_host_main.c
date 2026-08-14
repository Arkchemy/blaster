#include <stdio.h>

int compute(int a, unsigned int b);

int main(void) {
    printf("%d\n", compute(12345678, 4000000000u));
    return 0;
}
