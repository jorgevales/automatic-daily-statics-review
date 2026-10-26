"""Checks for the --diagnose reports. Run from the project folder: python -m unittest discover -s tests"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('case_review_runner', ROOT / 'case_review_runner.py')
runner = importlib.util.module_from_spec(spec)
sys.modules['case_review_runner'] = runner
spec.loader.exec_module(runner)


class SanitizerTests(unittest.TestCase):
    def setUp(self):
        self.s = runner.DiagSanitizer()

    def test_paths_with_spaces_and_unc_are_labelled(self):
        text = self.s.clean(r'Cannot open S:\Team Share\Some User 1\logs\edge-startup.json because it is locked, also \\fileserver01\evidence\a.pdf')
        self.assertNotIn('Team Share', text)
        self.assertNotIn('fileserver01', text)
        self.assertIn('<PATH-1 S: depth=5 ext=.json>', text)
        self.assertIn('because it is locked', text)
        self.assertIn('UNC', text)

    def test_folder_names_containing_words_are_not_cut(self):
        # Real failure: a folder called "... and Projects" was split at "and", leaking the rest of the path.
        text = self.s.clean(r"OSError: [Errno 2] No such file or directory: '\\\\srv01\\share\\Shared and Projects\\UK\\Projects\\Daily review\\users\\x\\f.py'")
        for leaked in ('Projects', 'Daily', 'review', 'Shared', 'srv01', 'UK'):
            self.assertNotIn(leaked, text)
        text = self.s.clean('Log: \\\\srv01\\share\\Shared and Projects\\UK\\logs\\dependency-install.log. No C: fallback was used.')
        self.assertNotIn('Projects', text)
        self.assertIn('No C: fallback was used', text)
        text = self.s.clean('File "S:\\Shared and Projects\\runner.py", line 9, in _main')
        self.assertNotIn('Projects', text)
        self.assertIn('line 9, in _main', text)

    def test_same_value_same_label(self):
        a = self.s.clean(r'C:\Users\x y\z.txt')
        b = self.s.clean(r'again C:\Users\x y\z.txt')
        self.assertIn(a, b)

    def test_known_values_and_ids(self):
        self.s.learn('USER', 'jvales')
        self.s.learn('ACCOUNT', 'AB12345')
        text = self.s.clean('user JVALES opened case 77-AB12345 as jvales')
        self.assertNotIn('jvales', text.lower())
        self.assertNotIn('AB12345', text)
        self.assertEqual(text.count('<USER-1>'), 2)

    def test_urls(self):
        text = self.s.clean('open https://m365.cloud.microsoft/chat/conversation/abc?x=1 and https://intranet.corp.example/app/42?id=9')
        self.assertIn('https://m365.cloud.microsoft/chat/...', text)
        self.assertNotIn('intranet', text)
        self.assertNotIn('42', text)

    def test_loopback_and_versions_kept_other_ips_removed(self):
        text = self.s.clean('127.0.0.1:9237 Edg/131.0.2903.70 server 10.20.30.40')
        self.assertIn('127.0.0.1:9237', text)
        self.assertIn('131.0.2903.70', text)
        self.assertNotIn('10.20.30.40', text)

    def test_hash_guid_email_run(self):
        text = self.s.clean('a@b.com 123e4567-e89b-12d3-a456-426614174000 ' + 'f' * 32 + ' run-20261026-101010-abcdef12')
        for bad in ('a@b.com', '123e4567', 'ffffffff', 'run-2026'):
            self.assertNotIn(bad, text)

    def test_browser_lines_unverified_removed(self):
        ok = self.s.browser_line('[1:2:1026/101010.1:ERROR:foo.cc(12)] Failed to bind')
        bad = self.s.browser_line('[1:2:1026/101010.1:ERROR:foo.cc(12)] user profile /home/alice/docs/x had trouble')
        self.assertIn('Failed to bind', ok)
        self.assertEqual(bad, '<line removed: unverified free text>')
        self.assertEqual(self.s.unverified, 1)

    def test_private_values_removed(self):
        out = self.s.obj({'name': 'HTTP_PROXY', 'value': runner.Private('http://secret-proxy:8080')})
        self.assertNotIn('secret', json.dumps(out))


class WindowsFactTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows only')
    def test_system_facts_are_collectable(self):
        self.assertGreater(runner.diag_processes()['total'], 5)
        self.assertIn('on_configured_port', runner.diag_listeners(9237))
        self.assertEqual(runner.diag_loopback()['local_connection_between_own_sockets'], 'ok')
        self.assertIn('platform', runner.diag_machine())
        self.assertIsInstance(runner.diag_policies(), list)
        self.assertIn('environment', runner.diag_proxy())

    @unittest.skipUnless(os.name == 'nt', 'Windows only')
    def test_listener_is_seen_on_a_real_port(self):
        import socket
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]
        try:
            found = runner.diag_listeners(port)['on_configured_port']
            self.assertTrue(any(item['pid'] == os.getpid() for item in found), found)
            probe = runner.diag_probe_port(port)
            self.assertEqual(probe['127.0.0.1']['tcp_connect'], 'connected')
        finally:
            server.close()


class EdgeMemoryTests(unittest.TestCase):
    def test_winner_is_tried_first_and_history_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = {'home': Path(folder)}
            memory = runner.edge_memory_read(paths)
            self.assertEqual([v['name'] for v in runner.edge_variant_order(memory)],
                             ['pipe-installed-edge', 'pipe-edge-channel', 'pipe-normal-folders',
                              'configured-port', 'normal-windows-folders', 'automatic-port'])
            attempts = [{'variant': 'pipe-installed-edge', 'label': 'a', 'ready': False},
                        {'variant': 'configured-port', 'label': 'b', 'ready': True}]
            winner = next(v for v in runner.EDGE_VARIANTS if v['name'] == 'configured-port')
            runner.edge_memory_record(paths, memory, attempts, winner, {'detected_by': 'listening port owned by new Edge', 'port': 9100})
            memory = runner.edge_memory_read(paths)
            self.assertEqual(memory['winner'], 'configured-port')
            self.assertEqual(memory['history']['pipe-installed-edge'], {'ok': 0, 'failed': 1})
            self.assertEqual([v['name'] for v in runner.edge_variant_order(memory)][0], 'configured-port')
            self.assertEqual([v['name'] for v in runner.edge_cdp_variants(runner.edge_variant_order(memory))][0], 'configured-port')

    def test_forced_test_mode_uses_only_normal_folders(self):
        names = [v['name'] for v in runner.edge_variant_order({}, forced_normal_folders=True)]
        self.assertEqual(names, ['pipe-normal-folders', 'normal-windows-folders'])

    def test_refusal_message_is_explained(self):
        attempts = [{'variant': 'configured-port', 'label': 'configured', 'seconds': 50, 'new_edge_processes': 3,
                     'closed': {'terminated': {1: 'closed'}}, 'assessment': {'devtools_refusal': 'DevTools remote debugging requires a non-default data directory.'}}]
        text = ' '.join(runner.edge_explain_attempts(attempts))
        self.assertIn('refused remote debugging in all 1 ways', text)


class ExplainTests(unittest.TestCase):
    base = {'configured_port': 9237, 'listeners_on_port': [], 'probe': {}, 'devtools_active_port': None,
            'new_edge_processes': [], 'policy_blocks': [], 'singleton': False}

    def explain(self, **changes):
        return ' '.join(runner.diag_explain_edge({**self.base, **changes}))

    def test_policy(self):
        self.assertIn('Company policy', self.explain(policy_blocks=['RemoteDebuggingAllowed=0']))

    def test_opened_but_unreadable(self):
        text = self.explain(listeners_on_port=[{'program': 'msedge.exe'}], probe={'127.0.0.1': {'http_error': 'timeout'}})
        self.assertIn('could not read its answer', text)

    def test_other_program_owns_port(self):
        self.assertIn('another program', self.explain(listeners_on_port=[{'program': 'java.exe'}]))

    def test_window_without_port(self):
        self.assertIn('never opened the debugging port', self.explain(new_edge_processes=[{'pid': 1}]))

    def test_no_new_process(self):
        self.assertIn('did not start a new process', self.explain())

    def test_different_port(self):
        self.assertIn('instead of 9237', self.explain(devtools_active_port={'port': '51000'}, new_edge_processes=[{'pid': 1}], listeners_on_port=[{'program': 'msedge.exe'}]))


class RecorderTests(unittest.TestCase):
    def test_end_to_end_reports_hide_identifying_details(self):
        with tempfile.TemporaryDirectory() as folder:
            user = os.environ.get('USERNAME') or 'someone'
            recorder = runner.DiagnosticRecorder(Path(folder) / 'run', ['--diagnose'])
            runner._RECORDER = recorder
            try:
                recorder.learn_cases([{'instruction_id': 'INS-998877', 'account_number': 'XY1234567', 'folder_name': 'INS-998877 XY1234567',
                                       'state': 'ready', 'manifest': [{'name': 'Audit Trail INS-998877.csv'}]}])
                runner.print(r'Source root: C:\Users\{}\Documents\Case Root\INS-998877 XY1234567'.format(user))
                recorder.facts.update(edge_causes=['Edge started and its window opened, but it never opened the debugging port.'])
                recorder.failure(RuntimeError('Edge endpoint did not become available'), 'Traceback ... File "C:\\Secret Place\\runner.py", line 9')
                internal, external = recorder.finish(1)
            finally:
                runner._RECORDER = None
            text_in, text_out = internal.read_text(encoding='utf-8'), external.read_text(encoding='utf-8')
            self.assertIn('Case Root', text_in)
            for secret in ('Case Root', 'INS-998877', 'XY1234567', 'Secret Place', user):
                self.assertNotIn(secret.lower(), text_out.lower(), secret)
            self.assertIn('What was removed', text_out)
            self.assertIn('never opened the debugging port', text_out)
            self.assertIn('Label key', text_in)


if __name__ == '__main__':
    unittest.main()
