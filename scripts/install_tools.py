"""Install versioned CLIs into tools/bin; verify publisher SHA256 checksums."""
import hashlib
import io
import json
import os
import platform
import tarfile
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = json.loads((ROOT / 'config/versions.json').read_text())

def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'practice1-lab'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()

def github_asset(repo, version, filename):
    try:
        release = json.loads(fetch(f'https://api.github.com/repos/{repo}/releases/tags/{version}'))
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 429):
            raise
        base = f'https://github.com/{repo}/releases/download/{version}/'
        checksum_name = filename + '.sha256sum' if repo.endswith('/kind') else f'velero-{version}-checksums.txt'
        lines = fetch(base + checksum_name).decode().splitlines()
        matching = [line.split()[0] for line in lines if filename in line]
        if len(matching) != 1:
            raise RuntimeError('Cannot find unique publisher checksum')
        blob = fetch(base + filename)
        if hashlib.sha256(blob).hexdigest() != matching[0]:
            raise RuntimeError('Checksum mismatch: ' + filename)
        return blob
    assets = {a['name']: a for a in release['assets']}
    asset = assets[filename]
    blob = fetch(asset['browser_download_url'])
    expected = asset.get('digest') or ''
    if expected.startswith('sha256:'):
        expected = expected.split(':', 1)[1]
    else:
        candidates = [a for n, a in assets.items() if n == filename + '.sha256sum'
                      or ('checksum' in n.lower() and n.endswith('.txt'))]
        expected = None
        for item in candidates:
            for line in fetch(item['browser_download_url']).decode().splitlines():
                fields = line.split()
                if len(fields) >= 2 and fields[-1].lstrip('*') == filename:
                    expected = fields[0]
        if not expected:
            raise RuntimeError(f'No publisher checksum for {filename}')
    if hashlib.sha256(blob).hexdigest() != expected:
        raise RuntimeError(f'Checksum mismatch: {filename}')
    return blob

def main():
    system = {'Windows': 'windows', 'Linux': 'linux', 'Darwin': 'darwin'}[platform.system()]
    arch = 'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'amd64'
    suffix = '.exe' if system == 'windows' else ''
    target = ROOT / 'tools/bin'
    target.mkdir(parents=True, exist_ok=True)
    kind = github_asset('kubernetes-sigs/kind', VERSIONS['kind'], f'kind-{system}-{arch}')
    kubectl_url = f"https://dl.k8s.io/release/{VERSIONS['kubernetes']}/bin/{system}/{arch}/kubectl{suffix}"
    kubectl = fetch(kubectl_url)
    if hashlib.sha256(kubectl).hexdigest() != fetch(kubectl_url + '.sha256').decode().strip():
        raise RuntimeError('kubectl checksum mismatch')
    name = f"velero-{VERSIONS['velero']}-{system}-{arch}"
    archive = github_asset('velero-io/velero', VERSIONS['velero'], name + '.tar.gz')
    # Read just the expected executable; do not extract arbitrary archive paths.
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        member = tar.extractfile(f'{name}/velero{suffix}')
        if member is None:
            raise RuntimeError('Velero binary missing from archive')
        velero = member.read()
    for command, blob in [('kind', kind), ('kubectl', kubectl), ('velero', velero)]:
        dest = target / (command + suffix)
        dest.write_bytes(blob)
        os.chmod(dest, 0o755)
        print(f'{command}: installed; SHA256={hashlib.sha256(blob).hexdigest()}')

if __name__ == '__main__':
    main()
