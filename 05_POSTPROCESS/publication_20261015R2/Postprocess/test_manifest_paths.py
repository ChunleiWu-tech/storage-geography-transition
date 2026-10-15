"""Regression checks for POSIX and legacy Windows source manifest paths."""
import hashlib
import json
from pathlib import Path, PurePosixPath
from manifest_paths import source_path

root = Path(__file__).resolve().parent
manifest = json.loads((root/'SOURCE_TABLES_SHA256.json').read_text(encoding='utf8'))
for name, expected in manifest.items():
    portable = name.replace('\\', '/')
    assert PurePosixPath(*portable.split('/')).as_posix() == portable
    for spelling in (portable, portable.replace('/', '\\')):
        path = source_path(root, spelling)
        assert path == root.joinpath(*PurePosixPath(portable).parts).resolve()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
for invalid in ('../outside.csv', '..\\outside.csv', '/absolute.csv', 'C:\\absolute.csv', 'C:relative.csv', '\\\\host\\share\\file', ''):
    try:
        source_path(root, invalid)
    except ValueError:
        continue
    raise AssertionError(f'Unsafe path accepted: {invalid!r}')
print(json.dumps({'status':'PASS', 'source_files':len(manifest), 'separator_variants_checked':2*len(manifest), 'rejected_invalid_paths':7}))
