from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

_saver: SqliteSaver | None = None
_path: Path | None = None


def get_checkpointer() -> SqliteSaver:
    global _saver, _path
    from config.settings import checkpoint_path

    path = checkpoint_path()
    if _saver is not None and _path == path:
        return _saver

    reset_checkpointer()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), check_same_thread=False)
    _saver = SqliteSaver(connection)
    _path = path
    return _saver


def reset_checkpointer() -> None:
    global _saver, _path
    saver = _saver
    _saver = None
    _path = None
    if saver is not None:
        saver.conn.close()
