"""Turning names into safe file system path components.

A work item's name seeds its artifact filenames, so the core makes that prefix safe; the host-side
sinks apply the same rule to every name they store under.
"""

import re
from typing import Final

_UNSAFE_CHARACTERS: Final[re.Pattern[str]] = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows treats these as devices, whatever the extension: `nul.txt` is the NUL device,
# so a write to it is discarded and a folder with that name cannot be created. The port
# numbers include 0 and the superscript digits, which Windows also reads as devices.
_DEVICE_PORT_NUMBERS: Final[tuple[str, ...]] = (*(str(number) for number in range(10)), "¹", "²", "³")
_RESERVED_DEVICE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{port_number}" for port_number in _DEVICE_PORT_NUMBERS),
        *(f"lpt{port_number}" for port_number in _DEVICE_PORT_NUMBERS),
    }
)


def safe_path_component(name: str) -> str:
    """Replace characters that no common file system accepts, and avoid reserved device names.

    A work item named `Q3: Plan / Draft.pdf` becomes `Q3_ Plan _ Draft.pdf`, and one named
    `CON.pdf` becomes `_CON.pdf`. Trailing dots and spaces are trimmed.
    """
    cleaned_name: str = _UNSAFE_CHARACTERS.sub("_", name).rstrip(" .")
    if not cleaned_name:
        return "_"
    name_before_extension: str = cleaned_name.split(".", 1)[0].rstrip(" ")
    if name_before_extension.casefold() in _RESERVED_DEVICE_NAMES:
        return f"_{cleaned_name}"
    return cleaned_name
