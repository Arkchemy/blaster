int sumn(int n, volatile int *acc) {
    int s = 0;
    for (int i = 0; i < n; i++) {
        s = s + *acc;
    }
    return s;
}
