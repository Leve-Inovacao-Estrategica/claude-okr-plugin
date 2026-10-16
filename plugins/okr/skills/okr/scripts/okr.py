#!/usr/bin/env python3
"""Leve OKR CLI, shared by Claude Code and Codex (Python 3.9+)."""
import argparse
import html.parser
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

    def download(self, src, target, token):
        url = urllib.parse.urljoin(self.base + '/', src)
        base_parts, url_parts = urllib.parse.urlsplit(self.base), urllib.parse.urlsplit(url)
        if (url_parts.scheme, url_parts.netloc) != (base_parts.scheme, base_parts.netloc):
            raise CLIError('Imagem fora do servidor do Leve OKR: ' + src)
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
        try:
            with self.opener.open(req, timeout=60) as response:
                target.write_bytes(response.read())
        except urllib.error.HTTPError as error:
            raise CLIError(f'HTTP {error.code} ao baixar {src}')
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise CLIError('Falha de rede ao baixar a imagem: ' + str(error))

    def attachments(self, task, folder):
        """Baixa os <img> da descrição e das ações de uma tarefa."""
        token, _ = self.authenticated()
        info = json.loads(self.checked('GET', f'/api/agent/tasks/{task}', token=token))
        sources = [('descricao', info.get('description'))]
        sources += [(f"acao_{action.get('id', n)}", action.get('content'))
                    for n, action in enumerate(info.get('actions') or [])]
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        saved = []
        for origin, content in sources:
            for n, src in enumerate(parse_html(content).images, 1):
                target = folder / f'{origin}_{n}{Path(urllib.parse.urlsplit(src).path).suffix or ".png"}'
                self.download(src, target, token)
                saved.append(str(target))
        print(json.dumps({'folder': str(folder.resolve()), 'files': saved}, ensure_ascii=False, indent=2))

    def action(self, task, filename, action_id=None):
        """Registra (ou corrige) uma ação a partir de um arquivo HTML e confere o que foi gravado."""
        content = Path(filename).read_text(encoding='utf-8-sig').strip()
        sent = parse_html(content)
        dropped = sorted(sent.tags & DROPPED_TAGS)
        if dropped:
            raise CLIError(f'O Leve OKR descarta {dropped}: renderize tabelas como imagem e troque <code> por texto.')
        unknown = sorted(sent.tags - KEPT_TAGS)
        if unknown:
            print(f'Aviso: tags sem garantia de preservação: {unknown}', file=sys.stderr)
        token, _ = self.authenticated()
        data = json.dumps({'content': content}, ensure_ascii=False).encode('utf-8')
        path = f'/api/agent/tasks/{task}/actions' + (f'/{action_id}' if action_id else '')
        reply = json.loads(self.checked('PATCH' if action_id else 'POST', path, data=data, token=token) or '{}')
        action_id = action_id or reply.get('id') or (reply.get('action') or {}).get('id')
        # O backend responde 201 mesmo quando altera o conteúdo; a releitura é a prova.
        actions = json.loads(self.checked('GET', f'/api/agent/tasks/{task}/actions', token=token))
        if isinstance(actions, dict):
            actions = actions.get('actions', [])
        stored = next((a for a in actions if a.get('id') == action_id), None)
        if stored is None:
            raise CLIError(f'Ação gravada, mas {action_id} não apareceu na releitura. Confira na tela.')
        problems = []
        if '�' in (stored.get('content') or ''):
            problems.append('acentos corrompidos (U+FFFD)')
        if len(parse_html(stored.get('content')).images) != len(sent.images):
            problems.append('quantidade de imagens diferente da enviada')
        if problems:
            raise CLIError(f'Ação {action_id} gravada com problema: ' + '; '.join(problems))
        print(json.dumps({'task': task, 'actionId': action_id, 'images': len(sent.images)}, ensure_ascii=False))


# O conteúdo de ações só preserva estas tags; as demais viram texto corrido com HTTP 201.
KEPT_TAGS = {'p', 'strong', 'ul', 'ol', 'li', 'br', 'img'}
DROPPED_TAGS = {'table', 'thead', 'tbody', 'tr', 'td', 'th', 'code', 'pre'}


class HTMLSummary(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.images = set(), []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        src = dict(attrs).get('src') if tag == 'img' else None
        if src:
            self.images.append(src)


def parse_html(content):
    summary = HTMLSummary()
    summary.feed(content or '')
    return summary


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
    attachments = commands.add_parser('anexos', help='baixa as imagens da descrição e das ações de uma tarefa')
    attachments.add_argument('task')
    attachments.add_argument('--saida', help='pasta de destino (default: okr_<tarefa>_anexos)')
    action = commands.add_parser('acao', help='registra ação a partir de um arquivo HTML e confere o que foi gravado')
    action.add_argument('task')
    action.add_argument('file')
    action.add_argument('--editar', metavar='ACTION_ID', help='corrige uma ação existente')
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
        elif args.command == 'anexos':
            client.attachments(args.task, args.saida or f'okr_{args.task}_anexos')
        elif args.command == 'acao':
            client.action(args.task, args.file, args.editar)
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
