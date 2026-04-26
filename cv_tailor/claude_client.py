"""Claude API wrappers: simple call, cached call, session token stats."""
import time

from anthropic import RateLimitError

from .constants import MODEL_NAME, RATE_LIMIT_RETRY_SEC

_session_stats = {
    "jobs": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_read_tokens": 0,
    "total_cost": 0.0,
}


def reset_session_stats():
    """Reset all session-level token counters to zero."""
    _session_stats.update({"jobs": 0, "input_tokens": 0, "output_tokens": 0,
                           "cache_read_tokens": 0, "total_cost": 0.0})


def print_session_summary():
    """Print cumulative token + cost summary for the current bulk session."""
    s = _session_stats
    jobs = max(s["jobs"], 1)
    print(f"\n{'='*50}")
    print(f"[SESSION SUMMARY]")
    print(f"  Jobs processed:      {s['jobs']}")
    print(f"  Total input tokens:  {s['input_tokens']}")
    print(f"  Total output tokens: {s['output_tokens']}")
    print(f"  Total cache reads:   {s['cache_read_tokens']}")
    print(f"  Total cost:          ${s['total_cost']:.4f}")
    print(f"  Avg cost per CV:     ${s['total_cost']/jobs:.4f}")
    print(f"  Cache hit rate:      {s['cache_read_tokens']/(s['input_tokens'] or 1)*100:.1f}%")
    print(f"{'='*50}\n")


def _log_usage(msg, text, call_name="unknown"):
    """Print per-call token audit and accumulate into session stats."""
    u = msg.usage
    cc = getattr(u, "cache_creation_input_tokens", 0) or 0
    cr = getattr(u, "cache_read_input_tokens", 0) or 0

    cost_in = (u.input_tokens * 3) / 1_000_000
    cost_out = (u.output_tokens * 15) / 1_000_000
    cost_cache = (cr * 0.30) / 1_000_000
    total_cost = cost_in + cost_out + cost_cache

    print(f"\n{'='*50}")
    print(f"[TOKEN AUDIT] Call: {call_name}")
    print(f"  Input tokens:        {u.input_tokens}")
    print(f"  Output tokens:       {u.output_tokens}")
    print(f"  Cache created:       {cc}")
    print(f"  Cache read:          {cr}")
    print(f"  Effective input:     {u.input_tokens - cr} (non-cached)")
    print(f"  Estimated cost:      ${total_cost:.6f}")
    if cr > 0:
        cache_status = "YES ✓ — reading from cache"
    elif cc > 0:
        cache_status = "POPULATING — cache created, next call will be cheaper"
    else:
        cache_status = "NO ✗ — cache not working, check cache_control setup"
    print(f"  Cache status:        {cache_status}")
    print(f"{'='*50}\n")

    _session_stats["input_tokens"] += u.input_tokens
    _session_stats["output_tokens"] += u.output_tokens
    _session_stats["cache_read_tokens"] += cr
    _session_stats["total_cost"] += total_cost


def claude_call(client, system, user, max_tokens, retries=1, call_name="unknown"):
    """Call Anthropic once, retrying on RateLimit once. Returns raw text."""
    last_err = None
    for _ in range(retries + 2):
        try:
            msg = client.messages.create(
                model=MODEL_NAME, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}])
            text = msg.content[0].text
            _log_usage(msg, text, call_name)
            return text
        except RateLimitError as e:
            last_err = e
            time.sleep(RATE_LIMIT_RETRY_SEC)
            continue
    raise last_err


def claude_call_cached(client, system, cached_user, fresh_user,
                       max_tokens, retries=1, call_name="unknown"):
    """Like claude_call, but marks system + cached_user for prompt caching.

    Cached blocks cost 10% of the normal input rate on a cache-hit and
    ~125% on cache creation. For the CV generation flow, system prompt
    and profile are static across calls, only the JD changes.
    """
    last_err = None
    for _ in range(retries + 2):
        try:
            msg = client.messages.create(
                model=MODEL_NAME,
                max_tokens=max_tokens,
                system=[{
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": cached_user,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {"type": "text", "text": fresh_user},
                    ],
                }],
            )
            text = msg.content[0].text
            _log_usage(msg, text, call_name)
            return text
        except RateLimitError as e:
            last_err = e
            time.sleep(RATE_LIMIT_RETRY_SEC)
            continue
    raise last_err
