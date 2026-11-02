import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lab', ROOT / 'scripts/lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

class IntegrityTests(unittest.TestCase):
    def test_control_totals(self):
        value = lab.expected_fingerprint()
        self.assertEqual(value['accounts'], 100)
        self.assertEqual(value['orders'], 1000)
        self.assertEqual(value['amount_cents'], 8508500)

    def test_same_count_and_sum_do_not_hide_swapped_data(self):
        a = '1,1,10,first\n2,1,20,second\n'
        b = '1,1,20,first\n2,1,10,second\n'
        first = lab.canonical_fingerprint('1,user\n', a)
        second = lab.canonical_fingerprint('1,user\n', b)
        self.assertEqual(first['amount_cents'], second['amount_cents'])
        self.assertEqual(first['orders'], second['orders'])
        self.assertNotEqual(first['sha256'], second['sha256'])

    def test_line_endings_are_portable(self):
        self.assertEqual(lab.canonical_fingerprint('1,x\n', '1,1,17,x\n'),
                         lab.canonical_fingerprint('1,x\r\n', '1,1,17,x\r\n'))

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.backup = {'status': {'phase': 'Completed', 'errors': 0}}
        self.pvb = [{'spec': {'volume': 'backup-data'},
                     'status': {'phase': 'Completed', 'progress': {'totalBytes': 100}}}]

    def test_healthy_backup_is_accepted(self):
        lab.assert_backup_usable(self.backup, self.pvb)

    def test_object_only_backup_cannot_authorize_deletion(self):
        with self.assertRaises(RuntimeError):
            lab.assert_backup_usable(self.backup, [])

    def test_partial_backup_cannot_authorize_deletion(self):
        self.backup['status']['phase'] = 'PartiallyFailed'
        with self.assertRaises(RuntimeError):
            lab.assert_backup_usable(self.backup, self.pvb)

    def test_failed_volume_cannot_authorize_deletion(self):
        self.pvb[0]['status']['phase'] = 'Failed'
        with self.assertRaises(RuntimeError):
            lab.assert_backup_usable(self.backup, self.pvb)

    def test_zero_bytes_rejected(self):
        self.pvb[0]['status']['progress']['totalBytes'] = 0
        with self.assertRaises(RuntimeError):
            lab.assert_backup_usable(self.backup, self.pvb)

    def test_restore_namespace_guard(self):
        for name in ['default', 'velero', 'kube-system', 'practice1-app', 'practice1-restore-../x']:
            with self.assertRaises(ValueError):
                lab.assert_clean_namespace(name)
        lab.assert_clean_namespace('practice1-restore-check')

class ManifestTests(unittest.TestCase):
    def test_only_dump_volume_is_backed_up(self):
        pod = next(x for x in lab.manifest('manifests/application.yaml') if x['kind'] == 'Pod')
        annotations = pod['metadata']['annotations']
        self.assertEqual(annotations['backup.velero.io/backup-volumes'], 'backup-data')
        self.assertEqual(annotations['pre.hook.backup.velero.io/on-error'], 'Fail')
        self.assertIn('post.hook.backup.velero.io/command', annotations)

    def test_no_embedded_secret_values(self):
        for path in (ROOT / 'manifests').glob('*.yaml'):
            for obj in lab.manifest(str(path.relative_to(ROOT))):
                self.assertNotEqual(obj['kind'], 'Secret', path.name)

    def test_daily_schedule_excludes_physical_pvs(self):
        template = lab.manifest('manifests/schedule.yaml')[0]['spec']['template']
        self.assertFalse(template['snapshotVolumes'])
        self.assertFalse(template['includeClusterResources'])
        self.assertIn('persistentvolumes', template['excludedResources'])

    def test_restore_drops_original_pv_binding(self):
        import json
        import yaml
        cm = lab.manifest('manifests/restore-modifiers.yaml')[0]
        rules = yaml.safe_load(cm['data']['modifiers.yaml'])['resourceModifierRules']
        patch = json.loads(rules[0]['mergePatches'][0]['patchData'])
        self.assertIsNone(patch['spec']['volumeName'])
        self.assertIsNone(patch['metadata']['annotations']['volume.kubernetes.io/selected-node'])

if __name__ == '__main__':
    unittest.main()
