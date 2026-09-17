"""Deterministic financial rules. All amounts are integer minor units."""
from typing import List


def allocate(target: int, members: int, period: int = 0) -> List[int]:
    """Rotate remainder units so every member contributes exactly target per rotation."""
    if target <= 0 or members < 1 or period < 0:
        raise ValueError("Positive target/member count and nonnegative period required")
    base, remainder = divmod(target, members)
    return [base + (1 if (i - period) % members < remainder else 0)
            for i in range(members)]
