"""Publish current git-tracked tree to GitHub via REST (when git push times out)."""

from __future__ import annotations

import base64
import json
import subprocess
import time
from pathlib import Path

OWNER = 'Mac-Tapia'
REPO = 'ConversorIGEA_DGS'
ROOT = Path(__file__).resolve().parents[1]


def gh_api(method: str, path: str, payload: dict | None = None, retries: int = 5) -> dict:
    cmd = ['gh', 'api', '--method', method, path]
    raw = json.dumps(payload) if payload is not None else None
    last_err = ''
    for attempt in range(1, retries + 1):
        if payload is not None:
            proc = subprocess.run(
                cmd + ['--input', '-'],
                input=raw,
                text=True,
                capture_output=True,
            )
        else:
            proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode == 0:
            return json.loads(proc.stdout) if proc.stdout.strip() else {}
        last_err = (proc.stderr or proc.stdout or '').strip()
        wait = min(2 ** attempt, 20)
        print(f'  retry {attempt}/{retries} {method} {path}: {last_err[:160]}')
        time.sleep(wait)
    raise RuntimeError(f'API fail {method} {path}: {last_err}')


def main() -> None:
    files = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z'], text=False).split(b'\0')
    paths = [f.decode('utf-8', 'surrogateescape') for f in files if f]
    print(f'files: {len(paths)}')

    tree: list[dict] = []
    for i, rel in enumerate(paths, 1):
        data = (ROOT / rel).read_bytes()
        blob = gh_api('POST', f'/repos/{OWNER}/{REPO}/git/blobs', {
            'content': base64.b64encode(data).decode('ascii'),
            'encoding': 'base64',
        })
        mode = '100755' if rel.endswith('.bat') else '100644'
        tree.append({
            'path': rel.replace('\\', '/'),
            'mode': mode,
            'type': 'blob',
            'sha': blob['sha'],
        })
        if i % 5 == 0 or i == len(paths):
            print(f'  blobs {i}/{len(paths)} ({rel})')

    tree_obj = gh_api('POST', f'/repos/{OWNER}/{REPO}/git/trees', {'tree': tree})
    print('tree', tree_obj['sha'])

    parent = gh_api('GET', f'/repos/{OWNER}/{REPO}/git/ref/heads/main')['object']['sha']
    commit = gh_api('POST', f'/repos/{OWNER}/{REPO}/git/commits', {
        'message': (
            'Add NA205-style SED interiors and harden universal IGEA→DGS conversion.\n\n'
            'Nested MT/BT buses, TypTr2/ElmTr2 and feeder coupler inside each SecSubProd '
            'triangle; hide micro-stub d_lin dust; inventory/preview/export extras.'
        ),
        'tree': tree_obj['sha'],
        'parents': [parent],
    })
    print('commit', commit['sha'])

    gh_api('PATCH', f'/repos/{OWNER}/{REPO}/git/refs/heads/main', {
        'sha': commit['sha'],
        'force': False,
    })
    info = gh_api('GET', f'/repos/{OWNER}/{REPO}')
    print('DONE')
    print('url=https://github.com/Mac-Tapia/ConversorIGEA_DGS')
    print('size=', info.get('size'), 'sha=', commit['sha'])


if __name__ == '__main__':
    main()
