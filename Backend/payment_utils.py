"""Payment method validation and masking utilities for FinAssist simulation.

Card numbers are validated using standard formatting and Luhn checks.
Only masked card details (brand, last4, exp_month, exp_year, cardholder name)
are ever persisted to the database.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime


def detect_card_brand(card_number: str) -> str:
    """Detect the card brand based on card number prefix (IIN/BIN)."""
    digits = re.sub(r"\D", "", card_number)
    if not digits:
        return "generic"
    if digits.startswith("4"):
        return "visa"
    if 51 <= int(digits[:2]) <= 55 or (len(digits) >= 4 and 2221 <= int(digits[:4]) <= 2720):
        return "mastercard"
    if digits.startswith(("34", "37")):
        return "amex"
    if digits.startswith(("6011", "65")) or (len(digits) >= 3 and 644 <= int(digits[:3]) <= 649):
        return "discover"
    return "generic"


def luhn_checksum_valid(digits: str) -> bool:
    """Verify card number using the standard Luhn algorithm."""
    total = 0
    reverse_digits = digits[::-1]
    for idx, char in enumerate(reverse_digits):
        digit = int(char)
        if idx % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def validate_card_details(
    *,
    card_holder_name: str,
    card_number: str,
    exp_month: int,
    exp_year: int,
    cvv: str,
) -> tuple[bool, str, str, str, int, int]:
    """Validate full card input and return (is_valid, error_message, brand, last4, exp_month, exp_year)."""
    # 1. Cardholder name
    cleaned_name = card_holder_name.strip()
    if not cleaned_name or len(cleaned_name) < 2:
        return False, "Please enter a valid cardholder name.", "", "", exp_month, exp_year

    # 2. Card number
    digits = re.sub(r"\D", "", card_number)
    if not digits or len(digits) < 13 or len(digits) > 19:
        return False, "Card number must be between 13 and 19 digits.", "", "", exp_month, exp_year

    if not luhn_checksum_valid(digits):
        return False, "Invalid card number checksum.", "", "", exp_month, exp_year

    brand = detect_card_brand(digits)
    last4 = digits[-4:]

    # 3. Expiration date
    if not (1 <= exp_month <= 12):
        return False, "Expiration month must be between 1 and 12.", "", "", exp_month, exp_year

    full_year = exp_year + 2000 if exp_year < 100 else exp_year
    now = datetime.now(UTC)
    current_year = now.year
    current_month = now.month

    if full_year < current_year or (full_year == current_year and exp_month < current_month):
        return False, "Card expiration date cannot be in the past.", "", "", exp_month, exp_year

    if full_year > current_year + 25:
        return False, "Expiration year is too far in the future.", "", "", exp_month, exp_year

    # 4. CVV
    cleaned_cvv = re.sub(r"\D", "", cvv)
    if len(cleaned_cvv) not in (3, 4) or (brand == "amex" and len(cleaned_cvv) != 4):
        if brand == "amex":
            return False, "American Express requires a 4-digit CVV/CVC.", "", "", exp_month, exp_year
        if len(cleaned_cvv) != 3:
            return False, "CVV/CVC must be 3 digits.", "", "", exp_month, exp_year

    return True, "", brand, last4, exp_month, full_year
