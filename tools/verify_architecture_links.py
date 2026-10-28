"""Comprueba los enlaces públicos y locales del espacio Structurizr de la arquitectura."""

from __future__ import annotations

import argparse
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "docs" / "architecture" / "workspace.dsl"


def main(argv: list[str] | None = None) -> int:
    # Sin argumentos propios, pero `--help` no debe salir a internet (009:RF-6).
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    text = WORKSPACE.read_text(encoding="utf-8")
    urls = sorted(set(re.findall(r'^\s*url\s+"([^\"]+)"', text, flags=re.MULTILINE)))
    web_urls = [url for url in urls if url.startswith("https://")]
    file_urls = [url for url in urls if url.startswith("file:///")]
    if not web_urls:
        raise SystemExit("No public HTTPS links found in workspace.dsl")

    failures: list[str] = []
    for url in web_urls:
        request = urllib.request.Request(url, headers={"User-Agent": "ConversorIGEA-DGS-architecture-check"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = response.status
        except (urllib.error.URLError, TimeoutError) as exc:
            failures.append(f"{url}: {exc}")
            continue
        print(f"{status} {url}")
        if status >= 400:
            failures.append(f"{url}: HTTP {status}")

    for url in file_urls:
        parsed = urlparse(url)
        local_path = Path(unquote(parsed.path.lstrip("/")))
        if not local_path.exists():
            failures.append(f"{url}: local target does not exist")
        else:
            print(f"LOCAL {url}")

    if failures:
        raise SystemExit("Invalid architecture links:\n" + "\n".join(failures))
    print(f"Verified {len(web_urls)} public links and {len(file_urls)} local targets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
