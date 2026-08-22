int compute(unsigned int x, int *arr, int n) {
    int total = 0;
    unsigned int masked = x & 0x1F;
    if (masked == 0) {
        return -1;
    }
    for (int i = 0; i < n; i++) {
        total += arr[i];
    }
    return (int)masked + total;
}
