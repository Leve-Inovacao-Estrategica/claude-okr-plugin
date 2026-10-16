#!/usr/bin/env python3
"""Leve OKR CLI, shared by Claude Code and Codex (Python 3.9+)."""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import shlex
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser


class CLIError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self):
        self.base = os.environ.get('OKR_BASE_URL', 'https://okr.leveinovacao.com.br').rstrip('/')
        self.config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'leve-okr'
        self.credentials = self.config / 'credentials'
        self.pending = self.config / 'pending-device-code'
        self.opener = urllib.request.build_opener(NoRedirect())

    def store(self, path, content):
        self.config.mkdir(parents=True, exist_ok=True, mode=0o700)
        # On Windows, filesystem ACLs control access; chmod is not an ACL substitute.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
        if os.name != 'nt':
            path.chmod(0o600)

    def token(self):
        try:
            content = self.credentials.read_text(encoding='utf-8').strip()
        except FileNotFoundError:
            raise CLIError('AUTH_REQUIRED: rode login-start, mostre a URL no chat e rode login-wait.', 2)
        # Read legacy Bash credentials without sourcing or executing their contents.
        try:
            fields = shlex.split(content)
        except ValueError:
            fields = []
        token = fields[0][len('OKR_TOKEN='):] if len(fields) == 1 and fields[0].startswith('OKR_TOKEN=') else ''
        if not token or '\n' in token or '\r' in token:
            raise CLIError('AUTH_REQUIRED: credenciais inválidas. Refaça o login.', 2)
        return token

    def request(self, method, path, data=None, token=None, content_type='application/json'):
        url = urllib.parse.urljoin(self.base + '/', path)
        base_parts, url_parts = urllib.parse.urlsplit(self.base), urllib.parse.urlsplit(url)
        if url_parts.scheme not in ('http', 'https') or (url_parts.scheme, url_parts.netloc) != (base_parts.scheme, base_parts.netloc):
            raise CLIError('O caminho deve pertencer ao servidor definido em OKR_BASE_URL.')
        headers = {'Accept': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if data is not None:
            headers['Content-Type'] = content_type
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=30) as response:
                return response.status, response.read().decode('utf-8')
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode('utf-8', errors='replace')
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise CLIError('Falha de rede ao chamar o Leve OKR: ' + str(error))

    def checked(self, method, path, **kwargs):
        status, body = self.request(method, path, **kwargs)
        if status >= 300:
            if body:
                print(body)
            raise CLIError(f'HTTP {status} em {method} {path} — veja a resposta acima.')
        return body

    def authenticated(self):
        token = self.token()
        status, body = self.request('GET', '/api/agent/projects', token=token)
        if status in (401, 403):
            raise CLIError('AUTH_REQUIRED: token inválido ou acesso negado. Refaça o login.', 2)
        if status >= 300:
            if body:
                print(body)
            raise CLIError(f'HTTP {status} ao verificar autenticação.')
        return token, body

    def login_start(self, client_name):
        body = self.checked('POST', '/api/cli/auth/start', data=json.dumps({'clientName': client_name}).encode())
        info = json.loads(body)
        self.store(self.pending, info['deviceCode'])
        disabled = os.environ.get('OKR_NO_BROWSER', os.environ.get('CLAUDE_OKR_NO_BROWSER', '0')) == '1'
        opened = False
        if not disabled:
            try:
                opened = webbrowser.open(info['verificationUriComplete'])
            except webbrowser.Error:
                pass
        public = dict(user_code=info['userCode'], verification_uri=info['verificationUriComplete'],
                      expires_in_seconds=info['expiresIn'], browser_opened=bool(opened))
        print(json.dumps(public, ensure_ascii=False, indent=2))
        return public

    def login_wait(self):
        if not self.pending.exists():
            raise CLIError('Sem código pendente. Rode login-start primeiro.')
        device_code = self.pending.read_text(encoding='utf-8')
        deadline = time.monotonic() + 540
        while time.monotonic() < deadline:
            body = self.checked('POST', '/api/cli/auth/poll', data=json.dumps({'deviceCode': device_code}).encode())
            info = json.loads(body)
            status = info.get('status')
            if status == 'pending':
                time.sleep(3)
            elif status == 'approved':
                self.store(self.credentials, 'OKR_TOKEN=' + shlex.quote(info['token']) + '\n')
                self.pending.unlink(missing_ok=True)
                user = info.get('user', {})
                print(f"Autenticado como {user.get('name', '')} ({user.get('email', '')}).")
                return
            elif status in ('denied', 'expired'):
                self.pending.unlink(missing_ok=True)
                raise CLIError('Autorização negada.' if status == 'denied' else 'Código expirou. Rode login-start novamente.')
            else:
                raise CLIError('Status inesperado na autorização: ' + str(status))
        raise CLIError('Timeout aguardando autorização. Rode login-start novamente.')

    def upload(self, filename):
        file = Path(filename)
        if not file.is_file():
            raise CLIError('Arquivo não encontrado: ' + filename)
        token, _ = self.authenticated()
        boundary = 'okr-' + uuid.uuid4().hex
        # Quote the filename safely for Content-Disposition.
        name = file.name.replace('"', '_').replace('\r', '_').replace('\n', '_')
        mime = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        prefix = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                  f'Content-Type: {mime}\r\n\r\n').encode('utf-8')
        data = prefix + file.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
        print(self.checked('POST', '/api/agent/uploads/image', token=token, data=data,
                           content_type='multipart/form-data; boundary=' + boundary))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Leve OKR CLI para Claude Code e Codex')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('login', 'login-start'):
        sub = commands.add_parser(name)
        sub.add_argument('client_name', nargs='?', default=f'Leve OKR CLI ({socket.gethostname()})')
    for name in ('login-wait', 'whoami', 'logout', 'ensure-login'):
        commands.add_parser(name)
    call = commands.add_parser('call')
    call.add_argument('method', choices=['GET', 'POST', 'PATCH', 'PUT', 'DELETE'])
    call.add_argument('path')
    call.add_argument('body', nargs='?', help='JSON; use @arquivo.json ou - para ler stdin')
    commands.add_parser('upload').add_argument('file')
    args = parser.parse_args(argv)
    client = Client()
    try:
        if args.command in ('login', 'login-start'):
            public = client.login_start(args.client_name)
            if args.command == 'login':
                print('Autorize no navegador: ' + public['verification_uri'], file=sys.stderr)
                client.login_wait()
        elif args.command == 'login-wait':
            client.login_wait()
        elif args.command == 'logout':
            client.credentials.unlink(missing_ok=True)
            client.pending.unlink(missing_ok=True)
            print('Credenciais locais removidas.')
        elif args.command in ('ensure-login', 'whoami'):
            _, body = client.authenticated()
            if args.command == 'whoami':
                projects = json.loads(body)
                print(f'Token válido. {len(projects) if isinstance(projects, list) else 0} projeto(s) visível(eis).')
            else:
                print('ok: token válido')
        elif args.command == 'call':
            data = None
            if args.body is not None:
                body = (sys.stdin.read() if args.body == '-' else
                        Path(args.body[1:]).read_text(encoding='utf-8-sig') if args.body.startswith('@') else args.body)
                data = json.dumps(json.loads(body), ensure_ascii=False).encode('utf-8')
            token, _ = client.authenticated()
            print(client.checked(args.method, args.path, token=token, data=data))
        elif args.command == 'upload':
            client.upload(args.file)
        return 0
    except CLIError as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Erro no arquivo local, JSON ou resposta do servidor: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    sys.exit(main())
