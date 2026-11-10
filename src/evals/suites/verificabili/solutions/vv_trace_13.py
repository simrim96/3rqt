def solve(data):
    rows = data.splitlines()
    n = int(rows[0])
    tot = 0
    for i in range(n):
        tot += int(rows[i + 1].split()[i])
    return str(tot)
