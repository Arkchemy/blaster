#include <stdio.h>

double compute(double a, int *arr, int n);

int main(void) {
    int arr[5] = {1, 2, 3, 4, 5};
    printf("%.9g\n", compute(-3.5, arr, 5));
    return 0;
}
