#include <stdio.h>

int sumn(int n, volatile int *acc);

int main(void) {
    volatile int value = 7;
    printf("%d\n", sumn(5, &value));
    return 0;
}
