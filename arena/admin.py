"""Organizer inspection of submissions. Validation is automatic in the sandbox."""
import os
from pathlib import Path
from arena.bootstrap import ROOT
from arena.core.storage import Store
from arena.core.submissions import SubmissionStore

if __name__ == '__main__':
    store = SubmissionStore(Store(Path(os.environ.get('ARENA_DATA_DIR', ROOT / 'data'))), ROOT/'bots/bot_sdk.py')
    for row in store.list():
        print(f"{row['id']}  {row['status']}  {row['name']}  {row['validation']}")
