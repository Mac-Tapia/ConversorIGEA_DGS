"""Genera la página distribuible de la arquitectura C4 interactiva desde su fuente en git."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "architecture" / "arquitectura-interactiva-c4.html"

SHELL_STYLE = """
:root {
  --background: #ffffff; --foreground: #17202a; --card: #ffffff;
  --muted: #eef1f4; --muted-foreground: #68717d; --border: #dfe3e8;
  --primary: #1261a0; --viz-series-1: #2684ff; --viz-series-2: #f2994a;
  --viz-series-3: #27ae60; --viz-series-4: #9b51e0; --viz-series-5: #7d6fe8;
}
body { margin: 0; padding: 16px; background: var(--background); color: var(--foreground);
  font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
.btn, .nav-link { border: 1px solid var(--border); border-radius: 999px; background: var(--card);
  color: var(--foreground); cursor: pointer; padding: .55rem .8rem; text-decoration: none; }
.btn-primary, .nav-link.active { background: var(--foreground); color: var(--background); }
.btn-ghost, .nav-link { border-color: transparent; }
.card { border-radius: 14px; background: var(--muted); padding: .8rem; }
.form-range { accent-color: var(--primary); }
""".strip()


def build(output_dir: Path) -> tuple[Path, Path]:
    fragment = SOURCE.read_text(encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    fragment_path = output_dir / "arquitectura-interactiva-c4.html"
    standalone_path = output_dir / "index.html"
    fragment_path.write_text(fragment, encoding="utf-8")
    standalone_path.write_text(
        "<!doctype html>\n<html lang=\"es\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>Arquitectura C4 interactiva - Conversor IGEA-DGS</title>\n"
        f"<style>{SHELL_STYLE}</style>\n</head>\n<body>\n{fragment}\n</body>\n</html>\n",
        encoding="utf-8",
    )
    return fragment_path, standalone_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "output" / "arquitectura",
        help="Destination directory (default: output/arquitectura).",
    )
    args = parser.parse_args()
    fragment, standalone = build(args.output_dir.resolve())
    print(fragment)
    print(standalone)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
