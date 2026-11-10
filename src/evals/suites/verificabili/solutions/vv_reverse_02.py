def solve(data):
    return "\n".join(line[::-1] for line in data.splitlines())
