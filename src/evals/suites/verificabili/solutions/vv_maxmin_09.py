def solve(data):
    nums = [int(t) for t in data.split()]
    return str(max(nums) - min(nums))
