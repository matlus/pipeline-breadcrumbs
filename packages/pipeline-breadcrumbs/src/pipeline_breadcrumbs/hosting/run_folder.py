"""One folder per run, so a repeat run never overwrites an earlier one."""

from pathlib import Path
from typing import Final

from pipeline_breadcrumbs.clock import Clock
from pipeline_breadcrumbs.hosting.paths import safe_path_component

_MAX_COLLISION_SUFFIX: Final[int] = 1000


def create_run_folder(root: Path, label: str, *, clock: Clock | None = None) -> Path:
    """Create `<root>/<yyyymmdd_hhmmss>_<label>/` and return it.

    The timestamp is part of the folder name, so folders sort by time and running the same
    file twice keeps both runs. The `label` is the host's choice: the file's name for a
    single-file run, `batch` for several. If two runs start in the same second the second
    folder gets a numeric suffix instead of colliding.
    """
    resolved_clock: Clock = clock or Clock.system()
    base_name: str = f"{resolved_clock.now():%Y%m%d_%H%M%S}_{safe_path_component(label)}"
    root.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, _MAX_COLLISION_SUFFIX + 1):
        folder: Path = root / (base_name if attempt == 1 else f"{base_name}_{attempt}")
        try:
            folder.mkdir()
        except FileExistsError:
            continue
        return folder
    raise FileExistsError(f"Could not create a unique run folder for '{base_name}' under {root}")
