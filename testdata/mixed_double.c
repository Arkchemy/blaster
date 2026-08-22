double compute(double a, int *arr, int n) {
    double result = 0.0;
    for (int i = 0; i < n; i++) {
        result += (double)arr[i];
    }
    double av = a;
    if (av < 0.0) av = -av;
    return result + av;
}
