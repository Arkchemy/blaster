#include <stdio.h>

int guarded(int x);

int main(void) {
    printf("%d\n", guarded(-5));
    printf("%d\n", guarded(7));
    return 0;
}
