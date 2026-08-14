#include <stdio.h>

int compute(unsigned int x, int *arr, int n);

int main(void) {
    int arr[5] = {10, 20, 30, 40, 50};
    printf("%d\n", compute(0x23, arr, 5));
    return 0;
}
