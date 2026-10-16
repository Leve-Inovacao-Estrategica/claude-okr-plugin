"""Install the complete shared skill in a chosen repository or user skill directory."""
import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description='Instala a skill OKR para o Codex')
    parser.add_argument('--dest', type=Path, default=Path.cwd() / '.agents' / 'skills',
                        help='Diretório de skills (default: .agents/skills no diretório atual)')
    parser.add_argument('--force', action='store_true', help='Atualiza uma instalação existente')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / 'plugins' / 'okr' / 'skills' / 'okr'
    target = args.dest.expanduser().resolve() / 'okr'
    if target.exists() and not args.force:
        parser.error(f'{target} já existe. Use --force para atualizar.')
    if target == source or source in target.parents or target in source.parents:
        parser.error('O destino não pode conter nem estar dentro da skill fonte.')
    shutil.copytree(source, target, dirs_exist_ok=args.force,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    print(f'Skill instalada em {target}. Reabra o Codex se ela não aparecer.')


if __name__ == '__main__':
    main()
