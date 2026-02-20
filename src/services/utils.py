"""Shared utility functions for services."""
import re
from typing import Optional


def parse_bought(value) -> Optional[int]:
    """Parse 'X+ bought in past month' or numeric values into an int.

    Handles formats like '1K+', '10K+', '500', '1,000', etc.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.lower().replace(",", "").strip()
        if not cleaned:
            return None
        # Handle "1K+", "10K+" style
        if "k" in cleaned:
            num_part = cleaned.split("k")[0].strip().rstrip("+").strip()
            try:
                return int(float(num_part) * 1000)
            except (ValueError, TypeError):
                return None
        # Extract first number
        match = re.search(r"(\d+)", cleaned)
        if match:
            return int(match.group(1))
    return None
