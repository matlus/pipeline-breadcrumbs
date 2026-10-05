"""Turning names into safe file system path components."""

import re
from typing import Final

_UNSAFE_CHARACTERS: Final[re.Pattern[str]] = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows treats these as devices, whatever the extension: `nul.txt` is the NUL device,
# so a write to it is discarded and a folder with that name cannot be created.
_RESERVED_DEVICE_NAMES: Final[frozenset[str]] = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{number}" for number in range(1, 10)), *(f"lpt{number}" for number in range(1, 10))}
)


def safe_path_component(name: str) -> str:
    """Replace characters that no common file system accepts, and avoid reserved device names.

    A work item named `Q3: Plan / Draft.pdf` becomes `Q3_ Plan _ Draft.pdf`, and one named
    `CON.pdf` becomes `_CON.pdf`. Trailing dots and spaces are trimmed.
    """
    cleaned: str = _UNSAFE_CHARACTERS.sub("_", name).rstrip(" .")
    if not cleaned:
        return "_"
    name_before_extension: str = cleaned.split(".", 1)[0].rstrip(" ")
    if name_before_extension.casefold() in _RESERVED_DEVICE_NAMES:
        return f"_{cleaned}"
    return cleaned
