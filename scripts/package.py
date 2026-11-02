"""Export tracked source files and the PDF, refusing to include known runtime secrets."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    destination = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'reports/practice1-submission.zip'
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    paths = [Path(name) for name in tracked if name]
    paths.append(Path('reports/technical-report.pdf'))
    private_file = ROOT / 'work/private.json'
    secret_values = json.loads(private_file.read_text()).values() if private_file.exists() else []
    forbidden = []
    for value in secret_values:
        if len(value) >= 24:
            forbidden.extend([value.encode(), base64.b64encode(value.encode())])
    payloads = []
    for path in sorted(set(paths)):
        if path.parts[0] in {'work', '.git', '.venv'} or 'runs' in path.parts or path.suffix == '.credentials':
            raise RuntimeError('Private or raw runtime path is tracked: ' + str(path))
        blob = (ROOT / path).read_bytes()
        if any(value in blob for value in forbidden):
            raise RuntimeError('Known runtime secret found in ' + str(path))
        payloads.append((path.as_posix(), blob))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, blob in payloads:
            archive.writestr('practice1/' + name, blob)
    print(f'{len(payloads)} files; secret scan PASS; {destination}')

if __name__ == '__main__':
    main()
