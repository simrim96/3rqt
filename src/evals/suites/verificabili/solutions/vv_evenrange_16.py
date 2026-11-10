def solve(data):
    out = []
    for line in data.splitlines():
        if not line.strip():
            continue
        a, b = map(int, line.split())
        out.append(str(b // 2 - (a - 1) // 2 if a else b // 2 + 1))
    return "\n".join(out)
