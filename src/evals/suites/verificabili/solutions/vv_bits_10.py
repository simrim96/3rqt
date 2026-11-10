def solve(data):
    return "\n".join(str(bin(int(t)).count("1")) for t in data.split())
