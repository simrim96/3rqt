def solve(data):
    nums = [int(t) for t in data.split()]
    m = max(nums)
    sieve = bytearray([1]) * (m + 1)
    sieve[0] = 0
    if m >= 1:
        sieve[1] = 0
    i = 2
    while i * i <= m:
        if sieve[i]:
            sieve[i * i :: i] = bytearray(len(sieve[i * i :: i]))
        i += 1
    counts, run = [], 0
    sieve_count = []
    for v in sieve:
        run += v
        sieve_count.append(run)
    for n in nums:
        counts.append(str(sieve_count[n]))
    return "\n".join(counts)
