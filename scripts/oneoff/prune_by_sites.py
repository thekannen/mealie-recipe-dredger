#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src_dir = repo_root / "src"
    src_dir_text = str(src_dir)
    if src_dir_text not in sys.path:
        sys.path.insert(0, src_dir_text)


def main() -> int:
    _bootstrap_src_path()
    from mealie_recipe_dredger.site_alignment import main as align_main

    return align_main()


if __name__ == "__main__":
    raise SystemExit(main())
