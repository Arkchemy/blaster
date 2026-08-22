#include <stdio.h>

int classify(int x);

int main(void) {
    for (int x = 0; x <= 6; x++) {
        printf("%d\n", classify(x));
    }
    return 0;
}
