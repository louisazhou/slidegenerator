#!/usr/bin/env python3
"""Utility helpers for resolving output and temporary directories.

This module is the single source-of-truth for all path decisions in the
slide_generator package.  Every public entry point must supply an explicit
``output_dir`` (called *workspace* in CLI terms).  A sub-directory named
``.sg_tmp`` inside that output directory is used for throw-away assets
unless that cannot be created (e.g. read-only share).  In that case we fall
back to :pyfunc:`tempfile.mkdtemp`.

The temporary directory is deleted automatically via an ``atexit`` hook
unless ``keep_tmp`` is True *and* the temporary directory lives inside the
given output directory.
"""
from __future__ import annotations

import atexit
import errno
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Tuple


__all__ = ["prepare_workspace"]


def prepare_workspace(output_dir: str | Path, *, keep_tmp: bool = False) -> Dict[str, Path]:
    """Resolve the output directory, create a working tmp dir and register cleanup.

    Parameters
    ----------
    output_dir
        Directory where final assets (PPTX, preview HTML, etc.) should be
        written.  Created if it does not exist.
    keep_tmp
        If ``True`` and the temporary directory is *inside* ``output_dir`` it
        will **not** be deleted at process exit.  If the code had to fall
        back to a system temporary directory, the directory is always
        removed.

    Returns
    -------
    dict with keys:
        ``output_dir`` – absolute :class:`pathlib.Path`
        ``tmp_dir``    – absolute :class:`pathlib.Path` where scratch files
                          should be placed
    """

    out_path = Path(output_dir).expanduser().resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    proposed_tmp = out_path / ".sg_tmp"
    use_fallback = False

    try:
        proposed_tmp.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # permission denied, read-only FS, …
        if exc.errno not in (errno.EACCES, errno.EROFS):
            raise
        use_fallback = True

    if use_fallback:
        tmp_path = Path(tempfile.mkdtemp(prefix="slidegen_tmp_"))
    else:
        tmp_path = proposed_tmp

    should_cleanup = not keep_tmp or use_fallback

    def _cleanup() -> None:
        try:
            if should_cleanup and tmp_path.exists():
                shutil.rmtree(tmp_path, ignore_errors=True)
        except Exception:
            # Never fail the interpreter at exit.
            pass

    atexit.register(_cleanup)

    return {
        "output_dir": out_path,
        "tmp_dir": tmp_path,
    }


def resolve_asset(
    src: str,
    *,
    base_dir: Path,
) -> Tuple[str, str]:
    """Return (browser_src, absolute_path) for *src*.

    browser_src   – value to place into ``<img src="…">`` so the measurement
                    browser can load it.
    absolute_path – original file on disk; later passed to python-pptx.

    Rules
    -----
    1. Remote or data-URIs are returned unchanged.
    2. ``file://`` URLs are stripped to an absolute path first.
    3. Relative paths are resolved against *base_dir*.
    """
    # 1. Already remote / embedded
    if src.startswith(("http://", "https://", "data:")):
        return src, src

    # 2. Deal with file:// prefix
    if src.startswith("file://"):
        abs_path = Path(src[7:]).expanduser().resolve()
    else:
        abs_path = (base_dir / src).expanduser().resolve()

    browser_src = f"file://{abs_path}"

    return browser_src, str(abs_path) 