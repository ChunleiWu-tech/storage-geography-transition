"""Resolve portable relative paths in archived source-table manifests."""
from pathlib import Path, PurePosixPath, PureWindowsPath


def source_path(root: Path, name: str) -> Path:
    """Accept POSIX and legacy Windows separators; reject paths outside root."""
    relative = PurePosixPath(name.replace('\\', '/'))
    if (not relative.parts or relative.is_absolute()
            or PureWindowsPath(name).drive or '..' in relative.parts):
        raise ValueError(f'Invalid relative source path: {name!r}')
    root = Path(root).resolve()
    result = root.joinpath(*relative.parts).resolve()
    if not result.is_relative_to(root):
        raise ValueError(f'Source path escapes package: {name!r}')
    return result
