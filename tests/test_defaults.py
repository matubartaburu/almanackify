import inspect
import os
import unittest
from pathlib import Path

from almanackify import core, mcp_server, server

ROOT = Path(__file__).resolve().parent.parent


def inside_repo(p) -> bool:
    """Compara sin distinguir mayúsculas: en macOS `~/Almanackify` y `~/almanackify` son la misma carpeta."""
    a, b = str(Path(p).expanduser()).lower(), str(ROOT).lower()
    return os.path.commonpath([a, b]) == b


class DefaultOutputDirs(unittest.TestCase):
    def test_default_output_dirs_are_not_inside_the_source_tree(self):
        for name, value in {
            "core.build": inspect.signature(core.build).parameters["output_dir"].default,
            "core.build_book": inspect.signature(core.build_book).parameters["output_dir"].default,
            "mcp_server": mcp_server.DEFAULT_OUT,
            "web jobs": server.DEFAULT_JOBS,
        }.items():
            self.assertFalse(inside_repo(value), f"{name} -> {value}")


if __name__ == "__main__":
    unittest.main()
