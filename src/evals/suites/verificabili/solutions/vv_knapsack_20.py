def solve(data):
    lines = data.split()
    n, W = int(lines[0]), int(lines[1])
    dp = [0] * (W + 1)
    for i in range(n):
        w, v = int(lines[2 + 2 * i]), int(lines[3 + 2 * i])
        for cap in range(W, w - 1, -1):
            dp[cap] = max(dp[cap], dp[cap - w] + v)
    return str(dp[W])
