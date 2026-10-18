"""Cross-process project cache lock for downloaders and offline parsers."""
import contextlib,fcntl
@contextlib.contextmanager
def project_lock(folder,blocking=True):
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'.parse.lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|(0 if blocking else fcntl.LOCK_NB))
        try:yield
        finally:fcntl.flock(stream,fcntl.LOCK_UN)
