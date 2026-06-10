# Global pytest configuration
import sys
from pathlib import Path

# Ensure repository root is on sys.path for imports like `import src.xxx`
repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

def pytest_ignore_collect(collection_path, config):
    """Skip example scripts that perform live HTTP requests.

    These files are useful for manual experimentation but are not intended to be
    part of the automated test suite.
    """
    ignore_names = {
        "test_creation_info.py",
        "test_metadata.py",
        "test_v3meta.py",
    }
        # First, ignore the known example script filenames
    if collection_path.name in ignore_names:
        return True
    # Then, ignore any files that reside within backup or workspace directories
    path_str = str(collection_path)
    if ".local-backup" in path_str or "workspace-" in path_str:
        return True
    return False
