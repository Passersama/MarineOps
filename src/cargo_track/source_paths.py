"""Local saved references are data, not permission to contact file servers."""
import ntpath
import os
import re
import stat
from pathlib import Path, PureWindowsPath


class SourcePathError(ValueError):
    pass


def _lexical(value, *, allow_relative=False):
    raw = os.fspath(value) if isinstance(value, os.PathLike) else value
    if not isinstance(raw, str) or not raw or '\0' in raw:
        raise SourcePathError('Use a nonempty local database path for saved plan sources.')
    windows = PureWindowsPath(raw)
    if (windows.drive.startswith('\\\\') or raw.startswith(('\\', '//'))
        or (re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', raw) and not re.match(r'^[a-zA-Z]:[\\/]', raw))
        or (windows.drive and not windows.root)
        or (os.name == 'nt' and windows.root and not windows.drive)):
        raise SourcePathError('Network, device, URI and drive-relative paths are not supported for saved plan sources.')
    if (os.name == 'nt' or windows.drive) and (':' in raw[2:] or windows.is_reserved()
        or any(PureWindowsPath(part).is_reserved() for part in windows.parts[1:])):
        raise SourcePathError('Use an ordinary local database path for saved plan sources.')
    if not allow_relative and not (windows.is_absolute() if os.name == 'nt' else Path(raw).is_absolute()):
        raise SourcePathError('Saved plan source paths must be absolute local paths.')
    return raw


def source_path_key(value):
    """Normalize metadata without resolve/stat/samefile or other file access."""
    raw = _lexical(value)
    return ntpath.normcase(ntpath.normpath(raw)) if os.name == 'nt' else os.path.normpath(raw)


def _drive_is_local(root):
    if os.name != 'nt':
        return True
    import ctypes
    # GetDriveType checks the drive mapping before any path component is followed.
    return ctypes.windll.kernel32.GetDriveTypeW(str(root)) in (2, 3, 5, 6)


def local_source_path(value, *, allow_relative=False):
    """Inspect aliases without following remote/unknown reparse points.

    This protects references supplied by files. It is not a sandbox against a
    process already permitted to replace the user's directories concurrently.
    """
    raw = _lexical(value, allow_relative=allow_relative)
    candidate = Path(os.path.abspath(raw))
    for _ in range(40):
        _lexical(candidate)
        if not _drive_is_local(candidate.anchor):
            raise SourcePathError('Use a local database copy. Network drives are not supported for saved plan sources.')
        cursor = Path(candidate.anchor)
        parts = candidate.parts[1:]
        for index, part in enumerate(parts):
            cursor /= part
            try:
                info = os.lstat(cursor)
            except FileNotFoundError:
                return candidate
            reparse = bool(getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            if not stat.S_ISLNK(info.st_mode) and not reparse:
                continue
            if reparse and getattr(info, 'st_reparse_tag', 0) not in (
                    stat.IO_REPARSE_TAG_SYMLINK, stat.IO_REPARSE_TAG_MOUNT_POINT):
                raise SourcePathError('Use a regular local database copy. This source reparse point is not supported.')
            target = os.readlink(cursor)
            # Windows returns an extended prefix for a normal local junction.
            # Only strip this OS-provided local prefix, never a supplied one.
            if target.startswith('\\\\?\\') and re.match(r'^[a-zA-Z]:[\\/]', target[4:]):
                target = target[4:]
            _lexical(target, allow_relative=True)
            replacement = Path(target) if os.path.isabs(target) else cursor.parent / target
            candidate = Path(os.path.abspath(replacement.joinpath(*parts[index + 1:])))
            break
        else:
            return candidate
    raise SourcePathError('The saved source contains too many linked paths. Use a regular local database copy.')
