def solve(data):
    out = []
    for line in data.splitlines():
        vals = []
        for w in line.split():
            t = "".join(c.lower() for c in w if c.isalnum())
            vals.append("1" if t == t[::-1] else "0")
        out.append(" ".join(vals))
    return "\n".join(out)
