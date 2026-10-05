"""Human-readable elapsed times and byte sizes for log lines."""

from typing import Final

_SECONDS_PER_MINUTE: Final[int] = 60
_SECONDS_PER_HOUR: Final[int] = 3600
_BYTES_PER_KB: Final[int] = 1024
_BYTES_PER_MB: Final[int] = 1024 * 1024
_BYTES_PER_GB: Final[int] = 1024 * 1024 * 1024


def format_elapsed(elapsed_seconds: float) -> str:
    """`3.214s`, `1m 3.250s` or `1h 2m 3.250s`, whichever reads best."""
    if elapsed_seconds >= _SECONDS_PER_HOUR:
        hours: int = int(elapsed_seconds // _SECONDS_PER_HOUR)
        remainder: float = elapsed_seconds - hours * _SECONDS_PER_HOUR
        minutes: int = int(remainder // _SECONDS_PER_MINUTE)
        seconds: float = remainder - minutes * _SECONDS_PER_MINUTE
        return f"{hours}h {minutes}m {seconds:.3f}s"
    if elapsed_seconds >= _SECONDS_PER_MINUTE:
        whole_minutes: int = int(elapsed_seconds // _SECONDS_PER_MINUTE)
        remaining_seconds: float = elapsed_seconds - whole_minutes * _SECONDS_PER_MINUTE
        return f"{whole_minutes}m {remaining_seconds:.3f}s"
    return f"{elapsed_seconds:.3f}s"


def format_byte_size(byte_size: int) -> str:
    """`512 B`, `56.5 KB`, `4.6 MB` or `13.40 GB`: the largest unit that reads as a small number."""
    if byte_size >= _BYTES_PER_GB:
        return f"{byte_size / _BYTES_PER_GB:.2f} GB"
    if byte_size >= _BYTES_PER_MB:
        return f"{byte_size / _BYTES_PER_MB:.1f} MB"
    if byte_size >= _BYTES_PER_KB:
        return f"{byte_size / _BYTES_PER_KB:.1f} KB"
    return f"{byte_size} B"
