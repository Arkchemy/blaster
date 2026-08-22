#include <stdio.h>

double compute(double a, float b, unsigned int base);

int main(void) {
    printf("%.6f\n", compute(3.5, 1.25f, 100));
    return 0;
}
