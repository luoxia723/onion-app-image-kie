"""Bounded concurrency and explicitly configured timeout replacement policy."""

DEFAULT_POLICY = {"concurrency": 3, "generation_timeout_seconds": 240, "max_timeout_restarts": 1}


def normalize_policy(value=None, *, legacy=False):
    if value is not None and not isinstance(value, dict):
        raise ValueError("execution_policy must be an object")
    policy = {**DEFAULT_POLICY, **({"max_timeout_restarts": 0} if legacy else {}), **(value or {})}
    bounds = {"concurrency": (1, 12), "generation_timeout_seconds": (1, 900), "max_timeout_restarts": (0, 1)}
    if set(policy) != set(bounds):
        raise ValueError("unknown execution_policy field")
    for key, (low, high) in bounds.items():
        if type(policy[key]) is not int or not low <= policy[key] <= high:
            raise ValueError(f"execution_policy.{key} must be an integer between {low} and {high}")
    return policy
