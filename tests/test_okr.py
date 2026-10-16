import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'plugins/okr/skills/okr/scripts/okr.py'
spec = importlib.util.spec_from_file_location('okr', HELPER)
okr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(okr)


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temp.name,
                                     'OKR_BASE_URL': 'https://okr.example.test', 'OKR_NO_BROWSER': '1'})
        env.start()
        self.addCleanup(env.stop)
        self.client = okr.Client()

    def run_main(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = okr.main(list(args))
        return result, output.getvalue(), errors.getvalue()

    def test_missing_auth_exit_two(self):
        result, _, error = self.run_main('ensure-login')
        self.assertEqual(result, 2)
        self.assertIn('AUTH_REQUIRED', error)

    def test_legacy_credentials_are_read_without_execution(self):
        self.client.store(self.client.credentials, 'OKR_TOKEN=test\\-token\n')
        self.assertEqual(self.client.token(), 'test-token')
        self.client.store(self.client.credentials, "OKR_TOKEN='literal$(echo secret)'\n")
        self.assertEqual(self.client.token(), 'literal$(echo secret)')

    def test_login_start_only_prints_public_fields(self):
        reply = dict(deviceCode='private-device', userCode='ABCD', verificationUriComplete='https://example.test/auth', expiresIn=600)
        with patch.object(self.client, 'request', return_value=(200, json.dumps(reply))), patch.object(okr.webbrowser, 'open') as browser:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                public = self.client.login_start('Codex')
        self.assertNotIn('private-device', output.getvalue())
        self.assertFalse(public['browser_opened'])
        browser.assert_not_called()
        self.assertEqual(self.client.pending.read_text(), 'private-device')

    def test_pending_then_approved_persists_token(self):
        self.client.store(self.client.pending, 'device')
        replies = [(200, '{"status":"pending"}'), (200, '{"status":"approved","token":"test-token","user":{"name":"Rafael","email":"test@example.test"}}')]
        with patch.object(self.client, 'request', side_effect=replies), patch.object(okr.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()) as output:
            self.client.login_wait()
        self.assertEqual(self.client.token(), 'test-token')
        self.assertFalse(self.client.pending.exists())
        self.assertNotIn('test-token', output.getvalue())

    def test_denied_and_expired_remove_pending(self):
        for status in ('denied', 'expired'):
            self.client.store(self.client.pending, 'device')
            with patch.object(self.client, 'request', return_value=(200, json.dumps({'status': status}))):
                with self.assertRaises(okr.CLIError):
                    self.client.login_wait()
            self.assertFalse(self.client.pending.exists())

    def test_http_error_preserves_body(self):
        error = urllib.error.HTTPError('https://okr.example.test/api', 400, 'Bad Request', {}, io.BytesIO(b'{"error":"content is required"}'))
        with patch.object(self.client.opener, 'open', side_effect=error):
            status, body = self.client.request('POST', '/api')
        self.assertEqual(status, 400)
        self.assertIn('content is required', body)

    def test_auth_failure_and_server_failure_are_distinct(self):
        self.client.store(self.client.credentials, 'OKR_TOKEN=test-token')
        for status, expected in ((401, 2), (403, 2), (500, 1)):
            with patch.object(okr.Client, 'request', return_value=(status, '{"error":"failure"}')):
                result, _, _ = self.run_main('ensure-login')
            self.assertEqual(result, expected)

    def test_post_json_from_file_keeps_unicode_and_is_not_retried(self):
        self.client.store(self.client.credentials, 'OKR_TOKEN=test-token')
        payload = Path(self.temp.name) / 'payload.json'
        payload.write_text('{"title":"Revisão"}', encoding='utf-8-sig')
        with patch.object(okr.Client, 'request', side_effect=[(200, '[]'), (400, '{"error":"goal required"}')]) as request:
            result, output, _ = self.run_main('call', 'POST', '/api/agent/tasks', '@' + str(payload))
        self.assertEqual(result, 1)
        self.assertIn('goal required', output)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(json.loads(request.call_args.kwargs['data']), {'title': 'Revisão'})

    def test_json_from_stdin(self):
        with patch.object(okr.Client, 'authenticated', return_value=('token', '[]')), patch.object(okr.Client, 'checked', return_value='{}') as checked, patch.object(sys, 'stdin', io.StringIO('{"notes":"Olá"}')):
            result, _, _ = self.run_main('call', 'POST', '/api/test', '-')
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(checked.call_args.kwargs['data']), {'notes': 'Olá'})

    def test_invalid_json_does_not_send_request(self):
        with patch.object(okr.Client, 'request') as request:
            result, _, _ = self.run_main('call', 'POST', '/api/test', '{broken')
        self.assertEqual(result, 1)
        request.assert_not_called()

    def test_foreign_url_and_redirect_do_not_leak_token(self):
        with patch.object(self.client.opener, 'open') as opened:
            for path in ('https://other.example.test/api', '//other.example.test/api'):
                with self.assertRaises(okr.CLIError):
                    self.client.request('GET', path, token='test-token')
            opened.assert_not_called()
        self.assertIsNone(okr.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example.test'))

    def test_upload_is_multipart(self):
        image = Path(self.temp.name) / 'print.png'
        image.write_bytes(b'fake-image')
        with patch.object(self.client, 'authenticated', return_value=('token', '[]')), patch.object(self.client, 'checked', return_value='{"url":"/image.png"}') as checked, contextlib.redirect_stdout(io.StringIO()):
            self.client.upload(str(image))
        self.assertIn(b'name="file"', checked.call_args.kwargs['data'])
        self.assertIn(b'fake-image', checked.call_args.kwargs['data'])
        self.assertIn('multipart/form-data', checked.call_args.kwargs['content_type'])

    def test_action_rejects_dropped_tags_before_sending(self):
        page = Path(self.temp.name) / 'acao.html'
        page.write_text('<p>Ação</p><table><tr><td>x</td></tr></table>', encoding='utf-8')
        with patch.object(okr.Client, 'request') as request:
            result, _, error = self.run_main('acao', '745', str(page))
        self.assertEqual(result, 1)
        self.assertIn('table', error)
        request.assert_not_called()

    def test_action_posts_utf8_and_verifies_stored_content(self):
        page = Path(self.temp.name) / 'acao.html'
        page.write_text('<p>Validação — ok</p><img src="/api/task-images/a.png" />', encoding='utf-8')
        stored = [{'id': 'act1', 'content': '<p>Validação — ok</p><img src="/api/task-images/a.png">'}]
        replies = ['{"id":"act1"}', json.dumps(stored)]
        with patch.object(okr.Client, 'authenticated', return_value=('token', '[]')), patch.object(okr.Client, 'checked', side_effect=replies) as checked:
            result, output, _ = self.run_main('acao', '745', str(page))
        self.assertEqual(result, 0)
        method, path = checked.call_args_list[0].args
        self.assertEqual((method, path), ('POST', '/api/agent/tasks/745/actions'))
        self.assertEqual(json.loads(checked.call_args_list[0].kwargs['data'])['content'], page.read_text(encoding='utf-8'))
        self.assertIn('act1', output)

    def test_action_detects_corrupted_storage_and_edits_by_id(self):
        page = Path(self.temp.name) / 'acao.html'
        page.write_text('<p>Revisão</p>', encoding='utf-8')
        replies = ['{}', json.dumps({'actions': [{'id': 'act9', 'content': '<p>Revis�o</p>'}]})]
        with patch.object(okr.Client, 'authenticated', return_value=('token', '[]')), patch.object(okr.Client, 'checked', side_effect=replies) as checked:
            result, _, error = self.run_main('acao', '745', str(page), '--editar', 'act9')
        self.assertEqual(result, 1)
        self.assertEqual(checked.call_args_list[0].args, ('PATCH', '/api/agent/tasks/745/actions/act9'))
        self.assertIn('U+FFFD', error)

    def test_attachments_download_images_from_description_and_actions(self):
        task = {'description': '<p>Ver</p><img src="/api/task-images/d.jpeg">',
                'actions': [{'id': 'a1', 'content': '<img src="/api/task-images/x.png"><img src="https://other.example.test/y.png">'}]}
        folder = Path(self.temp.name) / 'anexos'
        with patch.object(okr.Client, 'authenticated', return_value=('token', '[]')), patch.object(okr.Client, 'checked', return_value=json.dumps(task)), patch.object(okr.Client, 'download') as download:
            download.side_effect = [None, None, okr.CLIError('Imagem fora do servidor do Leve OKR')]
            result, _, error = self.run_main('anexos', '745', '--saida', str(folder))
        self.assertEqual(result, 1)
        self.assertIn('fora do servidor', error)
        targets = [call.args[1].name for call in download.call_args_list]
        self.assertEqual(targets[:2], ['descricao_1.jpeg', 'acao_a1_1.png'])

    def test_download_refuses_foreign_host(self):
        with patch.object(self.client.opener, 'open') as opened:
            with self.assertRaises(okr.CLIError):
                self.client.download('https://other.example.test/x.png', Path(self.temp.name) / 'x.png', 'test-token')
            opened.assert_not_called()

    def test_logout_removes_both_files(self):
        self.client.store(self.client.credentials, 'OKR_TOKEN=test-token')
        self.client.store(self.client.pending, 'device')
        self.assertEqual(self.run_main('logout')[0], 0)
        self.assertFalse(self.client.credentials.exists())
        self.assertFalse(self.client.pending.exists())

    def test_installed_skill_is_self_contained_and_overwrite_is_explicit(self):
        destination = Path(self.temp.name) / 'skills'
        command = [sys.executable, str(ROOT / 'scripts/install-codex-skill.py'), '--dest', str(destination)]
        result = subprocess.run(command, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = destination / 'okr/scripts/okr.py'
        self.assertTrue((destination / 'okr/SKILL.md').exists())
        self.assertEqual(installed.read_bytes(), HELPER.read_bytes())
        result = subprocess.run([sys.executable, str(installed), '--help'], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run(command + ['--force'], capture_output=True).returncode, 0)

    def test_manifests_share_version_and_point_to_existing_skill(self):
        plugin = ROOT / 'plugins/okr'
        claude = json.loads((plugin / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
        codex = json.loads((plugin / '.codex-plugin/plugin.json').read_text(encoding='utf-8'))
        marketplace = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
        self.assertEqual(claude['version'], codex['version'])
        self.assertEqual(claude['version'], marketplace['plugins'][0]['version'])
        self.assertTrue((plugin / codex['skills'] / 'okr/SKILL.md').is_file())


if __name__ == '__main__':
    unittest.main()
