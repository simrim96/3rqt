def solve(data):
    out = []
    for line in data.splitlines():
        if not out or out[-1] != line:
            out.append(line)
    return "\n".join(out)
