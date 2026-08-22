#include <stdio.h>

int compute(int a, int b, unsigned int c, unsigned int d);

int main(void) {
    printf("%d\n", compute(17, 5, 100u, 7u));
    return 0;
}
