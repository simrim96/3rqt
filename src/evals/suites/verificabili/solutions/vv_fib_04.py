def solve(data):
    out = []
    for tok in data.split():
        n = int(tok)
        a, b = 0, 1
        for _ in range(n):
            a, b = b, (a + b) % 1000000007
        out.append(str(a))
    return "\n".join(out)
