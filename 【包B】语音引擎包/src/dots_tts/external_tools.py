from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExternalToolResolution:
    name: str
    path: str
    source: str
    checked_locations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "source": self.source,
            "checked_locations": list(self.checked_locations),
        }


class ExternalToolNotFoundError(FileNotFoundError):
    def __init__(self, name: str, checked_locations: list[str]):
        checked = "\n".join(f"  - {item}" for item in checked_locations)
        super().__init__(
            f"Required tool {name!r} was not found. Checked locations:\n{checked}\n"
            f"Recovery: set DOTS_TTS_{name.upper()} to an executable, place the "
            "matching macOS/Windows binary in a package bin directory, or add it to PATH."
        )
        self.name = name
        self.checked_locations = tuple(checked_locations)


def _candidate_names(name: str) -> tuple[str, ...]:
    return (f"{name}.exe", name) if os.name == "nt" else (name,)


def _package_candidates(package_root: Path, name: str) -> list[Path]:
    directories = (
        package_root / "bin",
        package_root / "_internal" / "bin",
        package_root / "wzf" / "ffmpeg" / "bin",
        package_root / "wzf" / "rubberband",
        package_root / "ffmpeg" / "bin",
        package_root / "rubberband",
    )
    return [directory / filename for directory in directories for filename in _candidate_names(name)]


def _usable_file(path: Path) -> bool:
    return path.is_file() and (os.name == "nt" or os.access(path, os.X_OK))


def resolve_external_tool(
    name: str,
    *,
    explicit_path: str | Path | None = None,
    package_root: str | Path | None = None,
    required: bool = True,
) -> ExternalToolResolution | None:
    normalized_name = str(name).strip().lower()
    if not normalized_name:
        raise ValueError("Tool name must not be empty.")

    checked: list[str] = []
    configured = explicit_path or os.environ.get(f"DOTS_TTS_{normalized_name.upper()}")
    if configured:
        configured_path = Path(configured).expanduser()
        explicit_candidates = (
            [configured_path / item for item in _candidate_names(normalized_name)]
            if configured_path.is_dir()
            else [configured_path]
        )
        for candidate in explicit_candidates:
            checked.append(f"explicit:{candidate}")
            if _usable_file(candidate):
                return ExternalToolResolution(
                    normalized_name,
                    str(candidate.resolve()),
                    "explicit",
                    tuple(checked),
                )

    if package_root is not None:
        for candidate in _package_candidates(Path(package_root), normalized_name):
            checked.append(f"package:{candidate}")
            if _usable_file(candidate):
                return ExternalToolResolution(
                    normalized_name,
                    str(candidate.resolve()),
                    "package",
                    tuple(checked),
                )

    for executable_name in _candidate_names(normalized_name):
        checked.append(f"PATH:{executable_name}")
        discovered = shutil.which(executable_name)
        if discovered:
            return ExternalToolResolution(
                normalized_name,
                str(Path(discovered).resolve()),
                "PATH",
                tuple(checked),
            )

    if required:
        raise ExternalToolNotFoundError(normalized_name, checked)
    return None
