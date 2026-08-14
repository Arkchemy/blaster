#include <stdio.h>

int compute(int a, int b, int which);

int main(void) {
    printf("%d\n", compute(10, 20, 0));
    printf("%d\n", compute(10, 20, 1));
    return 0;
}
