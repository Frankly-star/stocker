"""Stocker dev server launcher.

Uses uvicorn factory mode to avoid double-initialization when reload=True.
FutuRuntime and broker are only created once in the worker process.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def create_application():
    """App factory called by uvicorn — only runs in the worker process."""
    from stocker.api.app import create_app
    return create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "runserver:create_application",
        factory=True,
        host="127.0.0.1",
        port=8899,
        reload=True,
        reload_dirs=["src"],
    )
