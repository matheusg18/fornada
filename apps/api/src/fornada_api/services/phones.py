"""Brazilian phone numbers in E.164, the format the `customers` table stores."""

import re

from fornada_api.services.errors import InvalidPhone

_NON_DIGITS = re.compile(r"\D")


def normalize_phone(raw: str) -> str:
    """`(81) 98765-4321`, `81987654321` or `+55 81 98765-4321` -> `+5581987654321`.

    The length decides: 10 or 11 digits are area code + number, 12 or 13
    digits starting with `55` already carry the country code. A leading `+`
    always means a country code, so `+1 415…` is rejected, not read as local.
    """
    digits = _NON_DIGITS.sub("", raw).lstrip("0")
    international = raw.strip().startswith("+")
    if len(digits) in (10, 11) and not international:
        return f"+55{digits}"
    if len(digits) in (12, 13) and digits.startswith("55"):
        return f"+{digits}"
    raise InvalidPhone(
        f"invalid phone {raw!r}: expected a Brazilian number with area code, "
        "for example (81) 98765-4321"
    )
