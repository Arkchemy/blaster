int add(int a, int b) { return a + b; }
int mul(int a, int b) { return a * b; }

typedef int (*FnPtr)(int, int);

int compute(int a, int b, int which) {
    FnPtr fn = which ? mul : add;
    return fn(a, b);
}
