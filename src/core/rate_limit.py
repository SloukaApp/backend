from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.core.errors import RateLimitExceededError, RateLimitUnavailableError

# One hash stores the two adjacent fixed intervals. Rejected requests never write.
_SCRIPT = """
local time = redis.call('TIME')
local now = tonumber(time[1]) + tonumber(time[2]) / 1000000
local states = {}
local retry = 0
for i, key in ipairs(KEYS) do
    local window = tonumber(ARGV[2 * i - 1])
    local maximum = tonumber(ARGV[2 * i])
    local interval = math.floor(now / window)
    local elapsed = now - interval * window
    local values = redis.call('HMGET', key, 'interval', 'current', 'previous')
    local stored = tonumber(values[1])
    local current = 0
    local previous = 0
    if stored == interval then
        current = tonumber(values[2]) or 0
        previous = tonumber(values[3]) or 0
    elseif stored == interval - 1 then
        previous = tonumber(values[2]) or 0
    end
    local estimate = current + previous * (1 - elapsed / window)
    if estimate + 1 > maximum then
        local delay
        if current + 1 <= maximum and previous > 0 then
            delay = window * (current + previous + 1 - maximum) / previous - elapsed
        else
            -- After rollover current becomes previous; solve its linear decay.
            delay = window - elapsed
            if current > 0 then
                delay = delay + window * math.max(0, (current + 1 - maximum) / current)
            end
        end
        retry = math.max(retry, math.max(1, math.ceil(delay)))
    end
    states[i] = {interval, current, previous, window}
end
if retry > 0 then return retry end
for i, key in ipairs(KEYS) do
    local state = states[i]
    redis.call('HSET', key, 'interval', state[1],
               'current', state[2] + 1, 'previous', state[3])
    redis.call('EXPIRE', key, 2 * state[4])
end
return 0
"""


class RateLimiter:
    def __init__(self, redis: Redis, key_prefix: str) -> None:
        self.redis = redis
        self.key_prefix = key_prefix

    async def check_many(self, budgets: list[tuple[str, int, int]]) -> None:
        """Check all budgets atomically; a denial consumes none of them."""
        keys = [f"{self.key_prefix}:rate_limit:{{rate_limit}}:{item[0]}" for item in budgets]
        arguments: list[int] = []
        for _, window, maximum in budgets:
            arguments.extend((window, maximum))
        try:
            result = cast(int, await self.redis.eval(_SCRIPT, len(keys), *keys, *arguments))
        except RedisError as exc:
            raise RateLimitUnavailableError() from exc
        if result:
            raise RateLimitExceededError(result)
