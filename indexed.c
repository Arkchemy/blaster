int compute(int *arr, int n) {
    int sum = 0;
    for (int i = 0; i < n; i++) {
        sum += arr[i];
    }
    unsigned int u = (unsigned int)n;
    int flag = (u >= 100u) ? 1 : 0;
    return sum + flag;
}
