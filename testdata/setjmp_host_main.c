#include <stdio.h>
int compute(int mode);
int main(void) {
    for (int m = 0; m < 3; m++) printf("%d\n", compute(m));
    return 0;
}
