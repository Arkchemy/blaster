#include <stdio.h>

int compute(int *arr, int n);

int main(void) {
    int arr[150];
    for (int i = 0; i < 150; i++) arr[i] = i - 50;
    printf("%d\n", compute(arr, 120));
    return 0;
}
