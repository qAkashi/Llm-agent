#!/usr/bin/env python3
"""Reproducible kind / PostgreSQL / Velero lab. All cluster calls use a private kubeconfig."""
from __future__ import annotations
import argparse
import base64
import contextlib
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import yaml

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = json.loads((ROOT / 'config/versions.json').read_text())
APP = 'practice1-app'
STORAGE = 'practice1-storage'
CONTEXT = 'kind-practice1'
KUBECONFIG = ROOT / 'work/kubeconfig'
STATE = ROOT / 'work/state.json'
BUCKET = 'practice1-backups'
ENDPOINT = 'http://minio.practice1-storage.svc.cluster.local:9000'
TERMINAL = {'Completed', 'PartiallyFailed', 'Failed', 'FailedValidation'}

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def unique(prefix):
    return prefix + '-' + dt.datetime.now(dt.timezone.utc).strftime('%m%d%H%M%S') + '-' + secrets.token_hex(2)

def executable(name):
    suffix = '.exe' if os.name == 'nt' else ''
    local = ROOT / 'tools/bin' / (name + suffix)
    if local.exists():
        return str(local)
    found = shutil.which(name)
    if found:
        return found
    if name == 'docker' and os.name == 'nt':
        for base in [Path(os.environ['LOCALAPPDATA']) / 'Programs/DockerDesktop',
                     Path('C:/Program Files/Docker/Docker')]:
            candidate = base / 'resources/bin/docker.exe'
            if candidate.exists():
                return str(candidate)
    raise RuntimeError(f'{name} not installed; see docs/RUNBOOK.md')

def manifest(filename):
    text = (ROOT / filename).read_text(encoding='utf-8')
    for key, value in VERSIONS.items():
        text = text.replace('${' + key + '}', value)
    return [obj for obj in yaml.safe_load_all(text) if obj]

def canonical_fingerprint(accounts, orders):
    data = ('ACCOUNTS\n' + accounts.replace('\r\n', '\n') +
            'ORDERS\n' + orders.replace('\r\n', '\n')).encode('utf-8')
    rows = list(csv.reader(io.StringIO(orders)))
    return {'sha256': hashlib.sha256(data).hexdigest(),
            'accounts': len(list(csv.reader(io.StringIO(accounts)))),
            'orders': len(rows), 'amount_cents': sum(int(row[2]) for row in rows)}

def expected_fingerprint():
    accounts = ''.join(f'{n},account-{n:03d}\n' for n in range(1, 101))
    orders = ''.join(f'{n},{(n-1)%100+1},{n*17},order-{n:04d}\n' for n in range(1, 1001))
    return canonical_fingerprint(accounts, orders)

def assert_backup_usable(backup, pvb):
    status = backup.get('status', {})
    if status.get('phase') != 'Completed' or status.get('errors', 0) != 0:
        raise RuntimeError('Backup is not Completed with zero errors')
    volumes = [x for x in pvb if x.get('spec', {}).get('volume') == 'backup-data']
    if len(volumes) != 1 or volumes[0].get('status', {}).get('phase') != 'Completed':
        raise RuntimeError('Expected one completed PodVolumeBackup for backup-data')
    if volumes[0].get('status', {}).get('progress', {}).get('totalBytes', 0) <= 0:
        raise RuntimeError('PodVolumeBackup has no recorded bytes')

def assert_clean_namespace(name):
    if not re.fullmatch(r'practice1-restore-[a-z0-9-]{1,35}', name):
        raise ValueError('Restore target must match practice1-restore-<suffix>')

class Lab:
    def __init__(self, command):
        self.run_id = unique(command)
        self.out = ROOT / 'reports/runs' / self.run_id
        self.out.mkdir(parents=True, exist_ok=True)
        self.rows = []
        self.hidden = []
        self.state = json.loads(STATE.read_text()) if STATE.exists() else {}
        self.creds_path = ROOT / 'work/private.json'
        if self.creds_path.exists():
            self.creds = json.loads(self.creds_path.read_text())
            self.hidden = list(self.creds.values())
        else:
            self.creds = {}

    def redact(self, text):
        for value in self.hidden:
            if len(value) >= 6:
                text = text.replace(value, '[REDACTED]')
                text = text.replace(base64.b64encode(value.encode()).decode(), '[REDACTED]')
        return text

    def save(self, name, value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        (self.out / name).write_text(self.redact(text), encoding='utf-8')

    def save_state(self):
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(self.state, indent=2), encoding='utf-8')

    @contextlib.contextmanager
    def step(self, name):
        started, timestamp = time.monotonic(), utc()
        row = {'step': name, 'started_utc': timestamp, 'status': 'PASS'}
        print(f'[{timestamp}] {name}', flush=True)
        try:
            yield
        except BaseException as exc:
            row['status'] = 'FAIL'
            row['error'] = self.redact(str(exc))
            raise
        finally:
            row['seconds'] = round(time.monotonic() - started, 3)
            row['finished_utc'] = utc()
            self.rows.append(row)
            self.save('steps.json', self.rows)
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=['step', 'started_utc', 'finished_utc', 'status', 'seconds', 'error'])
            writer.writeheader()
            writer.writerows(self.rows)
            self.save('steps.csv', stream.getvalue())

    def run(self, args, data=None, check=True, timeout=900, private=False):
        args = [str(a) for a in args]
        started = time.monotonic()
        result = subprocess.run(args, input=data, text=True, encoding='utf-8', errors='replace',
                                capture_output=True, timeout=timeout, cwd=ROOT)
        record = {'utc': utc(), 'seconds': round(time.monotonic()-started, 3),
                  'command': '[private input; payload omitted]' if private else args,
                  'returncode': result.returncode,
                  'stdout': '[omitted]' if private else result.stdout,
                  'stderr': '[omitted]' if private else result.stderr}
        with (self.out / 'commands.jsonl').open('a', encoding='utf-8') as log:
            log.write(self.redact(json.dumps(record, ensure_ascii=False)) + '\n')
        if check and result.returncode:
            raise RuntimeError(f'{Path(args[0]).name} failed ({result.returncode}): ' +
                               ('private operation; inspect Kubernetes events' if private else self.redact(result.stderr[-3000:])))
        return result

    def k(self, *args, **kwargs):
        return self.run([executable('kubectl'), '--kubeconfig', KUBECONFIG,
                         '--context', CONTEXT, *args], **kwargs)

    def v(self, *args, **kwargs):
        return self.run([executable('velero'), '--kubeconfig', KUBECONFIG,
                         '--kubecontext', CONTEXT, *args], **kwargs)

    def obj(self, kind, name, namespace='velero'):
        return json.loads(self.k('get', kind, name, '-n', namespace, '-o', 'json', private=(kind == 'secret')).stdout)

    def items(self, kind, selector, namespace='velero'):
        return json.loads(self.k('get', kind, '-n', namespace, '-l', selector, '-o', 'json').stdout)['items']

    def apply(self, objects, private=False):
        if isinstance(objects, dict):
            objects = [objects]
        return self.k('apply', '-f', '-', data=json.dumps({'apiVersion': 'v1', 'kind': 'List', 'items': objects}), private=private)

    def namespace(self, name):
        self.apply({'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': name, 'labels': {'practice1/managed': 'true'}}})

    def secret(self, name, namespace, fields):
        self.hidden.extend(fields.values())
        self.apply({'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': name, 'namespace': namespace},
                    'type': 'Opaque', 'data': {k: base64.b64encode(v.encode()).decode() for k, v in fields.items()}}, private=True)

    def wait(self, description, probe, timeout=600, interval=3):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = probe()
            if value:
                return value
            time.sleep(interval)
        raise TimeoutError(description)

    def terminal(self, kind, name, timeout=900):
        def probe():
            obj = self.obj(kind, name)
            return obj if obj.get('status', {}).get('phase') in TERMINAL else None
        return self.wait(f'{kind}/{name} did not finish', probe, timeout)

    def diagnose(self):
        if not KUBECONFIG.exists():
            return
        for ns in [APP, STORAGE, 'velero']:
            for kind in ['pods', 'events']:
                result = self.k('get', kind, '-n', ns, '-o', 'wide', check=False, timeout=20)
                self.save(f'diagnostic-{ns}-{kind}.txt', result.stdout + result.stderr)

    def preflight(self):
        with self.step('preflight'):
            versions = {}
            for cmd in ['docker', 'kind', 'kubectl', 'velero']:
                versions[cmd] = executable(cmd)
            info = self.run([versions['docker'], 'info', '--format', '{{json .}}'], timeout=30)
            data = json.loads(info.stdout)
            if data.get('OSType') != 'linux':
                raise RuntimeError('Docker must run Linux containers')
            self.save('environment.json', {'executables': versions, 'docker_server': data.get('ServerVersion'),
                                           'memory_bytes': data.get('MemTotal'), 'cpus': data.get('NCPU')})

    def mc_job(self, script, name=None):
        name = name or unique('minio')
        obj = {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': name, 'namespace': STORAGE},
               'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 180, 'ttlSecondsAfterFinished': 86400,
                        'template': {'spec': {'restartPolicy': 'Never', 'automountServiceAccountToken': False,
                         'containers': [{'name': 'mc', 'image': VERSIONS['mc'], 'command': ['/bin/sh', '-ec',
                         'mc alias set lab ' + ENDPOINT + ' "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null\n' + script],
                         'envFrom': [{'secretRef': {'name': 'minio-auth'}}, {'secretRef': {'name': 'minio-users'}}]}]}}}}
        self.apply(obj)
        def done():
            status = self.obj('job', name, STORAGE).get('status', {})
            if status.get('failed'):
                raise RuntimeError(f'MinIO Job {name} failed')
            return status.get('succeeded')
        try:
            self.wait('MinIO Job timeout', done, 210)
        finally:
            logs = self.k('logs', '-n', STORAGE, 'job/' + name, check=False).stdout
            self.save(name + '.log', logs)
        return logs

    def bootstrap(self):
        self.preflight()
        with self.step('create-kind-cluster'):
            clusters = self.run([executable('kind'), 'get', 'clusters']).stdout.split()
            if 'practice1' in clusters:
                if not KUBECONFIG.exists():
                    raise RuntimeError('Existing practice1 cluster has no local kubeconfig; refusing adoption')
            else:
                self.run([executable('kind'), 'create', 'cluster', '--name', 'practice1', '--config',
                          ROOT / 'config/kind.yaml', '--image', VERSIONS['node_image'], '--kubeconfig', KUBECONFIG, '--wait', '180s'])
            self.k('wait', '--for=condition=Ready', 'nodes', '--all', '--timeout=180s')
            self.apply(manifest('manifests/storage.yaml'))
            self.namespace(STORAGE)
            self.namespace(APP)
            self.namespace('velero')
        with self.step('build-and-load-minio-images'):
            for component in ['minio', 'mc']:
                image = VERSIONS[component]
                present = self.run([executable('docker'), 'image', 'inspect', image], check=False)
                if present.returncode:
                    self.run([executable('docker'), 'build', '-t', image, '-f',
                              ROOT / 'docker' / ('Dockerfile.' + component), ROOT / 'docker'], timeout=1800)
                self.run([executable('kind'), 'load', 'docker-image', image, '--name', 'practice1'], timeout=300)
        with self.step('generate-private-secrets'):
            if not self.creds:
                self.creds = {key: secrets.token_hex(24) for key in ['pg', 'api', 'root', 's3', 'denied', 'repository']}
                self.creds.update({'root_user': 'practice1-admin', 's3_user': 'practice1-velero', 'denied_user': 'practice1-denied'})
                self.creds_path.write_text(json.dumps(self.creds), encoding='utf-8')
                os.chmod(self.creds_path, 0o600)
            self.hidden.extend(self.creds.values())
            self.secret('minio-auth', STORAGE, {'MINIO_ROOT_USER': self.creds['root_user'], 'MINIO_ROOT_PASSWORD': self.creds['root']})
            self.secret('minio-users', STORAGE, {'S3_USER': self.creds['s3_user'], 'S3_PASSWORD': self.creds['s3'],
                                               'DENIED_USER': self.creds['denied_user'], 'DENIED_PASSWORD': self.creds['denied']})
            self.secret('postgres-auth', APP, {'password': self.creds['pg'], 'app-password': self.creds['api']})
            self.secret('api-auth', APP, {'uri': f"postgres://reader:{self.creds['api']}@postgres:5432/app"})
        with self.step('deploy-minio-and-create-bucket'):
            self.apply(manifest('manifests/minio.yaml'))
            self.k('rollout', 'status', 'deployment/minio', '-n', STORAGE, '--timeout=300s')
            policy = {'Version': '2012-10-17', 'Statement': [
                {'Effect': 'Allow', 'Action': ['s3:GetBucketLocation', 's3:ListBucket', 's3:ListBucketMultipartUploads'], 'Resource': ['arn:aws:s3:::' + BUCKET]},
                {'Effect': 'Allow', 'Action': ['s3:GetObject', 's3:PutObject', 's3:DeleteObject', 's3:AbortMultipartUpload', 's3:ListMultipartUploadParts'], 'Resource': ['arn:aws:s3:::' + BUCKET + '/*']}]}
            denied = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Deny', 'Action': ['s3:*'], 'Resource': ['arn:aws:s3:::*']}]}
            self.mc_job(f'mc mb --ignore-existing lab/{BUCKET}\n' +
                "cat > /tmp/allow.json <<'POLICY'\n" + json.dumps(policy) + '\nPOLICY\n' +
                "cat > /tmp/deny.json <<'POLICY'\n" + json.dumps(denied) + '\nPOLICY\n' +
                'mc admin user add lab "$S3_USER" "$S3_PASSWORD"\n' +
                'mc admin policy create lab practice1-policy /tmp/allow.json\n' +
                'mc admin policy attach lab practice1-policy --user "$S3_USER"\n' +
                'mc admin user add lab "$DENIED_USER" "$DENIED_PASSWORD"\n' +
                'mc admin policy create lab practice1-deny /tmp/deny.json\n' +
                'mc admin policy attach lab practice1-deny --user "$DENIED_USER"')
        with self.step('install-velero'):
            credentials = '[default]\naws_access_key_id=' + self.creds['s3_user'] + '\naws_secret_access_key=' + self.creds['s3'] + '\n'
            path = ROOT / 'work/s3.credentials'
            path.write_text(credentials, encoding='utf-8')
            os.chmod(path, 0o600)
            self.secret('velero-repo-credentials', 'velero', {'repository-password': self.creds['repository']})
            self.v('install', '--provider', 'aws', '--plugins', 'velero/velero-plugin-for-aws:' + VERSIONS['aws_plugin'],
                   '--image', 'velero/velero:' + VERSIONS['velero'], '--bucket', BUCKET, '--secret-file', path,
                   '--backup-location-config', 'region=us-east-1,s3ForcePathStyle=true,s3Url=' + ENDPOINT,
                   '--use-volume-snapshots=false', '--use-node-agent', '--uploader-type', 'kopia',
                   '--default-volumes-to-fs-backup=false', '--privileged-node-agent', '--apply')
            # The Windows CLI joins host paths with backslashes; the kind nodes are Linux.
            self.apply_node_agent_paths()
            self.k('rollout', 'status', 'deployment/velero', '-n', 'velero', '--timeout=300s')
            self.k('rollout', 'status', 'daemonset/node-agent', '-n', 'velero', '--timeout=300s')
            self.wait('BSL is unavailable', lambda: self.obj('backupstoragelocation', 'default').get('status', {}).get('phase') == 'Available', 180)
        with self.step('deploy-app-and-seed'):
            self.apply({'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'database-scripts', 'namespace': APP},
                        'data': {name: (ROOT / 'scripts' / name).read_text() for name in ['backup.sh', 'restore.sh']}})
            self.apply(manifest('manifests/application.yaml'))
            self.k('wait', '-n', APP, '--for=condition=Ready', 'pod/postgres', '--timeout=300s')
            exists = self.sql(APP, "SELECT to_regclass('public.orders') IS NOT NULL;").strip()
            if exists == 'f':
                self.k('exec', '-i', '-n', APP, 'postgres', '-c', 'postgres', '--',
                       'psql', '-U', 'postgres', '-d', 'app', '-v', 'ON_ERROR_STOP=1', data=(ROOT / 'sql/seed.sql').read_text())
            # Reader has read-only transactions; disable LISTEN and refresh schema after seed.
            self.k('rollout', 'restart', 'deployment/api', '-n', APP)
            self.k('rollout', 'status', 'deployment/api', '-n', APP, '--timeout=300s')
            baseline = self.fingerprint(APP)
            if baseline != expected_fingerprint():
                raise RuntimeError('Unexpected control dataset; refusing to reset existing data')
            self.state['baseline'] = baseline
            self.save('baseline.json', baseline)
            self.save_state()
            self.api_check(APP)
            # Verify local PV support, not only a successful PVC bind.
            for pvc in ['pgdata', 'backup-data']:
                pv = self.obj('pvc', pvc, APP)['spec']['volumeName']
                if 'local' not in self.obj('pv', pv, APP)['spec']:
                    raise RuntimeError(f'{pv} is not a local PV; inspect local-path provisioner')
        with self.step('install-daily-schedule'):
            self.apply(manifest('manifests/schedule.yaml'))

    def apply_node_agent_paths(self):
        daemonset = self.obj('daemonset', 'node-agent')
        volumes = daemonset['spec']['template']['spec']['volumes']
        fixed = [{'name': volume['name'], 'hostPath': {'path': volume['hostPath']['path'].replace('\\', '/')}}
                 for volume in volumes if 'hostPath' in volume]
        patch = {'spec': {'template': {'spec': {'volumes': fixed}}}}
        self.k('patch', 'daemonset', 'node-agent', '-n', 'velero', '--type=strategic', '-p', json.dumps(patch))

    def sql(self, namespace, query):
        return self.k('exec', '-n', namespace, 'postgres', '-c', 'postgres', '--', 'psql', '-X', '-U', 'postgres',
                      '-d', 'app', '-v', 'ON_ERROR_STOP=1', '-A', '-t', '-c', query).stdout

    def fingerprint(self, namespace):
        accounts = self.sql(namespace, 'COPY (SELECT id,name FROM accounts ORDER BY id) TO STDOUT WITH CSV;')
        orders = self.sql(namespace, 'COPY (SELECT id,account_id,amount_cents,description FROM orders ORDER BY id) TO STDOUT WITH CSV;')
        return canonical_fingerprint(accounts, orders)

    def api_check(self, namespace):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        args = [executable('kubectl'), '--kubeconfig', str(KUBECONFIG), '--context', CONTEXT,
                '-n', namespace, 'port-forward', 'svc/api', f'{port}:3000', '--address', '127.0.0.1']
        with (self.out / (namespace + '-port-forward.log')).open('w') as log:
            process = subprocess.Popen(args, stdout=log, stderr=log)
            try:
                def probe():
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/orders?order=id&limit=1', timeout=3) as response:
                            return json.load(response)
                    except (OSError, ValueError):
                        return None
                data = self.wait('API did not return data', probe, 90)
                if data != [{'id': 1, 'account_id': 1, 'amount_cents': 17, 'description': 'order-0001'}]:
                    raise RuntimeError('API returned unexpected control row')
                self.save(namespace + '-api.json', data)
            finally:
                process.terminate()
                process.wait(timeout=10)

    def backup_spec(self):
        return manifest('manifests/schedule.yaml')[0]['spec']['template']

    def capture(self, kind, name, obj=None):
        self.save(f'{name}-{kind}.json', obj or self.obj(kind, name))
        # Signed S3 URLs point to an in-cluster service, which the Windows host cannot resolve.
        # Fetch logs from an in-cluster mc Job rather than silently saving empty CLI stdout.
        try:
            log_file = f'restore-{name}-logs.gz' if kind == 'restore' else f'{name}-logs.gz'
            logs = self.mc_job(f'mc cat lab/{BUCKET}/{kind}s/{name}/{log_file} | gzip -d')
        except RuntimeError:
            # A killed server may never upload that operation's log object.
            server = self.k('logs', '-n', 'velero', 'deployment/velero', '--since=15m', check=False)
            logs = 'S3 operation log unavailable; fallback Velero server log follows.\n' + server.stdout + server.stderr
        self.save(f'{name}.log', logs)
        resource, label = ('podvolumebackups', 'backup-name') if kind == 'backup' else ('podvolumerestores', 'restore-name')
        items = self.items(resource, 'velero.io/' + label + '=' + name)
        self.save(f'{name}-{resource}.json', items)
        return items

    def backup(self, name=None):
        name = name or unique('manual')
        with self.step('manual-backup'):
            self.apply({'apiVersion': 'velero.io/v1', 'kind': 'Backup', 'metadata': {'name': name, 'namespace': 'velero'}, 'spec': self.backup_spec()})
            obj = self.terminal('backup', name)
            pvb = self.capture('backup', name, obj)
            assert_backup_usable(obj, pvb)
            self.state['backup'] = name
            self.state['baseline'] = self.fingerprint(APP)
            self.save_state()
            self.save('dump-bytes.txt', self.k('exec', '-n', APP, 'postgres', '-c', 'postgres', '--', 'cat', '/backup/dump-bytes.txt').stdout)
            self.mc_job(f'mc du --json lab/{BUCKET}\nmc ls --recursive --json lab/{BUCKET}')
        return name

    def scheduled_proof(self):
        with self.step('scheduled-backup-proof'):
            obj = manifest('manifests/schedule.yaml')[0]
            obj['metadata']['name'] = unique('practice1-proof')
            obj['spec']['schedule'] = '* * * * *'
            name = obj['metadata']['name']
            self.apply(obj)
            try:
                backups = self.wait('Scheduler did not create a Backup', lambda: self.items('backups', 'velero.io/schedule-name=' + name), 150)
                self.k('patch', 'schedule', name, '-n', 'velero', '--type=merge', '-p', '{"spec":{"paused":true}}')
                backup = backups[0]['metadata']['name']
                result = self.terminal('backup', backup)
                assert_backup_usable(result, self.capture('backup', backup, result))
                self.state['scheduled_backup'] = backup
                self.save_state()
            finally:
                self.k('delete', 'schedule', name, '-n', 'velero', '--ignore-not-found', check=False)

    def destroy_app(self, backup):
        with self.step('delete-source-namespace'):
            assert_backup_usable(self.obj('backup', backup), self.items('podvolumebackups', 'velero.io/backup-name=' + backup))
            if self.fingerprint(APP) != self.state.get('baseline'):
                raise RuntimeError('Source changed since baseline; create a new backup')
            ns = self.obj('namespace', APP, APP)
            if ns['metadata'].get('labels', {}).get('practice1/managed') != 'true':
                raise RuntimeError('Namespace ownership guard failed')
            self.k('patch', 'schedule', 'practice1-daily', '-n', 'velero', '--type=merge', '-p', '{"spec":{"paused":true}}')
            self.k('delete', 'namespace', APP, '--wait=true', '--timeout=180s')

    def start_restore(self, backup, target):
        assert_clean_namespace(target)
        if self.k('get', 'namespace', target, '--ignore-not-found', '-o', 'name').stdout.strip():
            raise RuntimeError('Restore requires an absent target namespace')
        name = unique('restore')
        self.apply(manifest('manifests/restore-modifiers.yaml'))
        self.apply({'apiVersion': 'velero.io/v1', 'kind': 'Restore', 'metadata': {'name': name, 'namespace': 'velero'},
                    'spec': {'backupName': backup, 'includedNamespaces': [APP], 'namespaceMapping': {APP: target},
                             'includeClusterResources': False, 'restorePVs': True,
                             'resourceModifier': {'kind': 'ConfigMap', 'name': 'practice1-restore-modifiers'},
                             'excludedResources': ['events', 'jobs', 'persistentvolumes']}})
        return name

    def restore(self, backup, target):
        with self.step('restore-to-new-namespace'):
            assert_backup_usable(self.obj('backup', backup), self.items('podvolumebackups', 'velero.io/backup-name=' + backup))
            name = self.start_restore(backup, target)
            result = self.terminal('restore', name)
            pvr = self.capture('restore', name, result)
            if result['status']['phase'] != 'Completed' or result['status'].get('errors', 0):
                raise RuntimeError(f'Restore failed: {result["status"]}')
            if not pvr or any(x.get('status', {}).get('phase') != 'Completed' for x in pvr):
                raise RuntimeError('PodVolumeRestore not completed')
            self.k('wait', '-n', target, '--for=condition=Ready', 'pod/postgres', '--timeout=300s')
            self.k('rollout', 'status', 'deployment/api', '-n', target, '--timeout=300s')
            self.state['restore'] = name
            self.state['target'] = target
            self.save_state()
        self.verify(target)

    def verify(self, target):
        with self.step('verify-data-schema-and-api'):
            actual = self.fingerprint(target)
            baseline = self.state.get('baseline')
            self.save('verification.json', {'before': baseline, 'after': actual, 'equal': actual == baseline})
            if not baseline or actual != baseline or actual != expected_fingerprint():
                raise RuntimeError('Control data mismatch')
            checks = self.sql(target, "SELECT count(*) FROM pg_constraint WHERE conrelid IN ('public.accounts'::regclass,'public.orders'::regclass);").strip()
            sequence = self.sql(target, 'SELECT last_value, is_called FROM orders_id_seq;').strip()
            if int(checks) != 5 or sequence != '1000|t':
                raise RuntimeError('Schema constraints or sequence state mismatch')
            self.save('schema-check.txt', f'constraints={checks}\nsequence={sequence}\n')
            logs = self.k('logs', '-n', target, 'postgres', '-c', 'postgres').stdout
            self.save('postgres-restored.log', logs)
            if 'RESTORE_IMPORT_COMPLETED' not in logs:
                raise RuntimeError('Database import marker is absent; empty PGDATA was not initialized from dump')
            self.api_check(target)

    def storage_failures(self):
        cases = [('missing-bucket', self.creds['root_user'], self.creds['root'], unique('absent'), r'NoSuchBucket|does not exist|not found'),
                 ('wrong-key', 'practice1-nonexistent-key', secrets.token_hex(24), BUCKET, r'InvalidAccessKeyId|access key|AccessDenied|Forbidden'),
                 ('access-denied', self.creds['denied_user'], self.creds['denied'], BUCKET, r'AccessDenied|Access Denied|Forbidden')]
        for case, key, password, bucket, pattern in cases:
            with self.step('failure-' + case):
                name = unique('test-' + case)
                cloud = f'[default]\naws_access_key_id={key}\naws_secret_access_key={password}\n'
                self.secret(name, 'velero', {'cloud': cloud})
                self.apply({'apiVersion': 'velero.io/v1', 'kind': 'BackupStorageLocation', 'metadata': {'name': name, 'namespace': 'velero'},
                    'spec': {'provider': 'aws', 'objectStorage': {'bucket': bucket}, 'credential': {'name': name, 'key': 'cloud'},
                    'validationFrequency': '10s', 'config': {'region': 'us-east-1', 's3ForcePathStyle': 'true', 's3Url': ENDPOINT}}})
                try:
                    self.wait('Faulty BSL did not become Unavailable', lambda: self.obj('backupstoragelocation', name).get('status', {}).get('phase') == 'Unavailable', 120)
                    bsl = self.obj('backupstoragelocation', name)
                    self.save(name + '-bsl.json', bsl)
                    message = bsl.get('status', {}).get('message', '')
                    if not re.search(pattern, message, re.I):
                        raise RuntimeError('Unexpected error category: ' + message)
                    spec = self.backup_spec()
                    spec['storageLocation'] = name
                    self.apply({'apiVersion': 'velero.io/v1', 'kind': 'Backup', 'metadata': {'name': name, 'namespace': 'velero'}, 'spec': spec})
                    result = self.terminal('backup', name, 180)
                    self.save(name + '-backup.json', result)
                    if result['status']['phase'] not in {'Failed', 'FailedValidation', 'PartiallyFailed'}:
                        raise RuntimeError('Fault injection unexpectedly succeeded')
                finally:
                    self.k('delete', 'backupstoragelocation', name, '-n', 'velero', '--ignore-not-found', check=False)
                    self.k('delete', 'secret', name, '-n', 'velero', '--ignore-not-found', check=False, private=True)
                if self.obj('backupstoragelocation', 'default')['status']['phase'] != 'Available':
                    raise RuntimeError('Healthy BSL affected by isolated fault test')

    def interruption(self, backup):
        target = 'practice1-restore-interrupt-' + secrets.token_hex(2)
        with self.step('failure-interrupted-restore'):
            daemonset = self.obj('daemonset', 'node-agent')
            original = daemonset['spec']['template']['spec'].get('nodeSelector', {})
            blocked = dict(original, **{'practice1/restore-gate': 'closed'})
            patch = lambda value: json.dumps({'spec': {'template': {'spec': {'nodeSelector': value}}}})
            restore_name = None
            try:
                self.k('patch', 'daemonset', 'node-agent', '-n', 'velero', '--type=merge', '-p', patch(blocked))
                self.wait('Node agents did not stop', lambda: not self.items('pods', 'name=node-agent'), 120)
                restore_name = self.start_restore(backup, target)
                def active():
                    result = self.obj('restore', restore_name)
                    phase = result.get('status', {}).get('phase')
                    if phase in TERMINAL:
                        raise RuntimeError('Restore ended before interruption; fault was not injected')
                    return phase in {'InProgress', 'WaitingForPluginOperations'} and self.items('podvolumerestores', 'velero.io/restore-name=' + restore_name)
                self.wait('No active restore volume operation', active, 180, 1)
                self.save('interruption-before.json', self.obj('restore', restore_name))
                self.k('scale', 'deployment/velero', '-n', 'velero', '--replicas=0')
                self.wait('Velero server did not stop', lambda: not self.items('pods', 'deploy=velero'), 120)
                self.k('scale', 'deployment/velero', '-n', 'velero', '--replicas=1')
                self.k('rollout', 'status', 'deployment/velero', '-n', 'velero', '--timeout=180s')
                result = self.terminal('restore', restore_name, 180)
                self.capture('restore', restore_name, result)
                if result['status']['phase'] not in {'Failed', 'PartiallyFailed'}:
                    raise RuntimeError('Expected interrupted restore to fail')
            finally:
                reset = dict(original, **{'practice1/restore-gate': None})
                self.k('patch', 'daemonset', 'node-agent', '-n', 'velero', '--type=merge', '-p', patch(reset), check=False)
                self.k('scale', 'deployment/velero', '-n', 'velero', '--replicas=1', check=False)
                self.k('rollout', 'status', 'daemonset/node-agent', '-n', 'velero', '--timeout=180s')
            # Discard only the namespace created by this fault test, then retry cleanly.
            self.k('delete', 'namespace', target, '--ignore-not-found', '--wait=true', '--timeout=180s')
        self.restore(backup, 'practice1-restore-retry-' + secrets.token_hex(2))

    def demo(self):
        self.bootstrap()
        self.scheduled_proof()
        backup = self.backup()
        self.storage_failures()
        self.destroy_app(backup)
        self.restore(backup, 'practice1-restore-main-' + secrets.token_hex(2))
        self.interruption(backup)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['preflight', 'bootstrap', 'demo', 'backup', 'scheduled-proof', 'destroy-app', 'restore', 'verify', 'failures', 'interrupt'])
    parser.add_argument('--backup')
    parser.add_argument('--target')
    args = parser.parse_args()
    lab = Lab(args.command)
    try:
        backup = args.backup or lab.state.get('backup')
        target = args.target or lab.state.get('target')
        if args.command in {'destroy-app', 'restore', 'interrupt'} and not backup:
            parser.error('A successful backup is required')
        if args.command in {'restore', 'verify'} and not target:
            parser.error('--target is required')
        actions = {'preflight': lab.preflight, 'bootstrap': lab.bootstrap, 'demo': lab.demo,
                   'backup': lab.backup, 'scheduled-proof': lab.scheduled_proof,
                   'destroy-app': lambda: lab.destroy_app(backup), 'restore': lambda: lab.restore(backup, target),
                   'verify': lambda: lab.verify(target), 'failures': lab.storage_failures,
                   'interrupt': lambda: lab.interruption(backup)}
        actions[args.command]()
        lab.save('result.json', {'status': 'PASS', 'command': args.command, 'finished_utc': utc()})
        print('PASS; evidence:', lab.out)
    except Exception as exc:
        lab.save('result.json', {'status': 'FAIL', 'command': args.command, 'error': lab.redact(str(exc)), 'finished_utc': utc()})
        try:
            lab.diagnose()
        except Exception:
            pass
        print('FAIL:', lab.redact(str(exc)), file=sys.stderr)
        print('Evidence:', lab.out, file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
