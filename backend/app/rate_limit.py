"""IP-based rate limiting (docs/PLAN.md §5.4): caps how many lessons a single
client can kick off per hour, bounding worst-case Anthropic spend from one
abusive or misbehaving caller. In-memory limiter — the same single-process
MVP trade-off as ``app/state/store.py``; a shared store (e.g. Redis) is the
drop-in fix if multi-instance deployment is ever needed.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
