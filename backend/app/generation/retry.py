"""Shared retry classification for Anthropic API calls.

The SDK already retries 429/5xx/connection errors internally with backoff
(default ``max_retries=2``) before ever raising to our code. If we still see
one of these after that, it's worth one more attempt from our own retry loop
(transient overload, e.g. HTTP 529, can outlast the SDK's built-in backoff) —
but only if an attempt is still available; a genuine bug (bad request, auth
failure) should fail immediately rather than burn the retry budget.
"""

from anthropic import APIConnectionError, APIStatusError, RateLimitError


def is_retryable(exc: Exception) -> bool:
    if isinstance(exc, RateLimitError | APIConnectionError):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500
