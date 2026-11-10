def solve(data):
    grid = [[int(t) for t in ln.split()] for ln in data.splitlines() if ln.strip()]
    w = len(grid[0])
    dp = [float("inf")] * w
    dp[0] = 0
    for row in grid:
        for j in range(w):
            best = min(dp[j], dp[j - 1] if j else float("inf"))
            dp[j] = best + row[j]
    return str(dp[-1])
