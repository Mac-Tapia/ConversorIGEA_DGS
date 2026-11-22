"""Muda la carpeta principal del entorno de desarrollo a ``ConverterSmartGrid`` sin perder nada (spec 058, RF-6, T6).

Uso:
  python tools/mudar_carpeta_principal.py [--destino CARPETA] [--aplicar] [--respaldo CARPETA] [--informe FICHERO]

Sin ``--aplicar`` solo dice lo que haría (el plan, en JSON) y por qué no podría. Con ``--aplicar``:

1. comprueba que se puede: el destino no existe y está en el mismo disco, la carpeta lleva su fichero de identidad (sin
   él, los espacios de trabajo quedarían en otra carpeta de datos) y ningún programa corre desde ella;
2. hace la foto de los espacios de trabajo (``output/web/<id>/workspace.json``) y, con ``--respaldo``, copia fuera su
   ``workspace.json`` y su ``conversiones.json`` (086 T9, paso 3); después renombra la carpeta;
3. repara los worktrees de git (``git worktree repair``), en los dos sentidos;
4. vuelve a apuntar las uniones (``node_modules``, ``.venv``…) de los worktrees que apuntaban a la carpeta vieja;
5. reinstala el paquete en el ``.venv`` en modo editable, sin red (``pip install -e . --no-deps``), y pone la ruta nueva
   en sus guiones de activación;
6. cambia la ruta en los ficheros de ``config/`` que la llevan escrita, en las variables de entorno del usuario y en los
   accesos directos del escritorio y del menú Inicio, que pasan a llamarse «ConverterSmartGrid (desarrollo)»;
7. verifica: el ``.venv`` importa el paquete desde la carpeta nueva, cada worktree responde a git y la identidad (y
   con ella la carpeta de los espacios de trabajo) es la misma de antes, y los espacios son los de la foto.

Solo usa la biblioteca estándar. Código de salida: 0 bien, 1 no se pudo (el informe dice en qué paso y por qué).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

FICHERO_INSTALACION = '.convertersmartgrid-instalacion.json'
NOMBRE_NUEVO = 'ConverterSmartGrid'
ACCESO_NUEVO = 'ConverterSmartGrid (desarrollo).lnk'
#: 086 T9, pasos 2, 3 y 10: los espacios que la web debe abrir después, y lo que se respalda de cada uno antes de renombrar.
ESPACIOS = Path('output') / 'web'
FICHEROS_DEL_ESPACIO = ('workspace.json', 'conversiones.json')
GUIONES_VENV = ('Scripts/activate', 'Scripts/activate.bat', 'Scripts/Activate.ps1', 'Scripts/activate.fish',
                'pyvenv.cfg')


def formas(ruta: Path) -> list[str]:
    """Cómo puede estar escrita una ruta en un fichero: con «\\», con «/» y con «\\\\» (dentro de un JSON)."""
    win = str(ruta).replace('/', '\\')
    return sorted({win, win.replace('\\', '/'), win.replace('\\', '\\\\')}, key=len, reverse=True)


def reemplazar_ruta(texto: str, origen: Path, destino: Path) -> str:
    """Cambia cada forma de ``origen`` por la misma forma de ``destino``; la letra de la unidad, sin distinguir."""
    for vieja in formas(origen):
        sep = '\\\\' if '\\\\' in vieja else ('\\' if '\\' in vieja else '/')
        nueva = str(destino).replace('/', '\\').replace('\\', sep)
        for v in {vieja, vieja[:1].lower() + vieja[1:], vieja[:1].upper() + vieja[1:]}:
            texto = texto.replace(v, nueva)
    return texto


def _dentro(ruta: str | Path, raiz: Path) -> bool:
    try:
        Path(os.path.normcase(os.path.abspath(ruta))).relative_to(os.path.normcase(os.path.abspath(raiz)))
        return True
    except ValueError:
        return False


@dataclass
class Plan:
    origen: Path
    destino: Path
    impedimentos: list[str] = field(default_factory=list)
    worktrees: list[str] = field(default_factory=list)
    uniones: list[dict] = field(default_factory=list)
    ficheros: list[str] = field(default_factory=list)
    entorno: dict[str, str] = field(default_factory=dict)
    accesos: list[dict] = field(default_factory=list)
    identidad: str | None = None
    espacios: list[str] = field(default_factory=list)
    respaldo: Path | None = None

    def como_dict(self) -> dict:
        return {'origen': str(self.origen), 'destino': str(self.destino), 'impedimentos': self.impedimentos,
                'worktrees': self.worktrees, 'uniones': self.uniones, 'ficheros': self.ficheros,
                'entorno': sorted(self.entorno), 'accesos': self.accesos, 'identidad': self.identidad,
                'espacios': self.espacios, 'respaldo': str(self.respaldo) if self.respaldo else None}


# --- lo que se mira en la máquina (inyectable en las pruebas) ---------------------------------------------------------

def git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')


def worktrees_de(repo: Path) -> list[Path]:
    """Los worktrees enlazados (sin el principal), de ``git worktree list --porcelain``."""
    salida = git('worktree', 'list', '--porcelain', cwd=repo).stdout
    rutas = [Path(linea[len('worktree '):]) for linea in salida.splitlines() if linea.startswith('worktree ')]
    return [r for r in rutas if os.path.normcase(os.path.abspath(r)) != os.path.normcase(os.path.abspath(repo))]


def uniones_hacia(carpetas: Iterable[Path], origen: Path) -> list[dict]:
    """Uniones y enlaces de primer nivel (y de ``frontend/``) que apuntan dentro de ``origen``."""
    halladas = []
    for raiz in carpetas:
        for madre in (raiz, raiz / 'frontend'):
            try:
                hijos = list(madre.iterdir())
            except OSError:
                continue
            for h in hijos:
                try:
                    if not (h.is_symlink() or h.is_junction()):
                        continue
                    destino = os.readlink(h)
                except (OSError, AttributeError):
                    continue
                destino = destino[4:] if destino.startswith('\\\\?\\') else destino
                if _dentro(destino, origen):
                    halladas.append({'enlace': str(h), 'apunta': destino, 'union': h.is_junction()})
    return halladas


def procesos_desde(origen: Path) -> list[str]:
    """Los procesos cuyo ejecutable está dentro de ``origen`` (por la ruta del ejecutable, nunca por su línea)."""
    if os.name != 'nt':
        return []
    orden = ("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath } | "
             "ForEach-Object { \"$($_.ProcessId)`t$($_.ExecutablePath)\" }")
    salida = subprocess.run(['powershell', '-NoProfile', '-Command', orden], capture_output=True, text=True,
                            encoding='utf-8', errors='replace').stdout
    return [linea for linea in salida.splitlines() if '\t' in linea and _dentro(linea.split('\t', 1)[1], origen)]


def entorno_de_usuario() -> dict[str, str]:
    if os.name != 'nt':
        return {}
    import winreg
    valores = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as clave:
        i = 0
        while True:
            try:
                nombre, valor, _ = winreg.EnumValue(clave, i)
            except OSError:
                break
            if isinstance(valor, str):
                valores[nombre] = valor
            i += 1
    return valores


def poner_entorno_de_usuario(nombre: str, valor: str) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment', 0, winreg.KEY_SET_VALUE) as clave:
        tipo = winreg.REG_EXPAND_SZ if '%' in valor else winreg.REG_SZ
        winreg.SetValueEx(clave, nombre, 0, tipo, valor)


def _carpetas_de_accesos() -> list[Path]:
    appdata = Path(os.environ.get('APPDATA', ''))
    perfil = Path(os.environ.get('USERPROFILE', Path.home()))
    return [perfil / 'Desktop', appdata / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs']


def _ps(guion: str, *args: str) -> list[str]:
    """``powershell -Command`` no pasa argumentos a ``$args``: van dentro de un bloque, entre comillas simples."""
    citados = ' '.join("'" + a.replace("'", "''") + "'" for a in args)
    return ['powershell', '-NoProfile', '-Command', f'& {{ {guion} }} {citados}']


_PS_LEER = ("$s=New-Object -ComObject WScript.Shell; Get-ChildItem -LiteralPath $args[0] -Filter *.lnk "
            "-ErrorAction SilentlyContinue | ForEach-Object { $l=$s.CreateShortcut($_.FullName); "
            "\"$($_.FullName)`t$($l.TargetPath)`t$($l.WorkingDirectory)\" }")
_PS_ESCRIBIR = ("$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut($args[0]); $l.TargetPath=$args[1]; "
                "$l.WorkingDirectory=$args[2]; $l.Save()")


def accesos_hacia(origen: Path, carpetas: Iterable[Path] | None = None) -> list[dict]:
    if os.name != 'nt':
        return []
    hallados = []
    for carpeta in carpetas or _carpetas_de_accesos():
        salida = subprocess.run(_ps(_PS_LEER, str(carpeta)), capture_output=True,
                                text=True, encoding='utf-8', errors='replace').stdout
        for linea in salida.splitlines():
            partes = linea.split('\t')
            if len(partes) == 3 and (_dentro(partes[1], origen) or _dentro(partes[2] or '?', origen)):
                hallados.append({'acceso': partes[0], 'objetivo': partes[1], 'carpeta': partes[2]})
    return hallados


def escribir_acceso(ruta: Path, objetivo: str, carpeta: str) -> None:
    subprocess.run(_ps(_PS_ESCRIBIR, str(ruta), objetivo, carpeta), check=True,
                   capture_output=True)


def espacios_de(raiz: Path) -> list[str]:
    """Los espacios de trabajo de la carpeta: los que tienen su ``workspace.json``, por su identificador."""
    carpeta = Path(raiz) / ESPACIOS
    return sorted(d.name for d in carpeta.iterdir() if (d / 'workspace.json').is_file()) if carpeta.is_dir() else []


def respaldar_espacios(raiz: Path, espacios: Iterable[str], respaldo: Path) -> int:
    """Copia fuera ``workspace.json`` y ``conversiones.json`` de cada espacio; devuelve cuántos ficheros copió."""
    n = 0
    for e in espacios:
        for nombre in FICHEROS_DEL_ESPACIO:
            f = Path(raiz) / ESPACIOS / e / nombre
            if f.is_file():
                (respaldo / e).mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, respaldo / e / nombre)
                n += 1
    return n


def identidad(raiz: Path) -> str | None:
    try:
        return str(json.loads((raiz / FICHERO_INSTALACION).read_text(encoding='utf-8')).get('id') or '') or None
    except (OSError, ValueError):
        return None


@dataclass
class Maquina:
    """Lo que se mira y se toca fuera de la carpeta; las pruebas lo sustituyen."""
    procesos: Callable[[Path], list[str]] = procesos_desde
    entorno: Callable[[], dict[str, str]] = entorno_de_usuario
    poner_entorno: Callable[[str, str], None] = poner_entorno_de_usuario
    accesos: Callable[[Path], list[dict]] = accesos_hacia
    escribir_acceso: Callable[[Path, str, str], None] = escribir_acceso
    reinstalar: Callable[[Path], subprocess.CompletedProcess] = lambda destino: subprocess.run(
        [str(destino / '.venv' / 'Scripts' / 'python.exe'), '-m', 'pip', 'install', '-e', str(destino), '--no-deps',
         '--no-index', '--no-build-isolation', '-q'], cwd=destino, capture_output=True, text=True)
    importar: Callable[[Path], str] = lambda destino: subprocess.run(
        [str(destino / '.venv' / 'Scripts' / 'python.exe'), '-c',
         'import convertersmartgrid, pathlib; print(pathlib.Path(convertersmartgrid.__file__).resolve())'],
        cwd=Path.home(), capture_output=True, text=True).stdout.strip()


# --- el plan y su aplicación ------------------------------------------------------------------------------------------

def planear(origen: Path, destino: Path, maquina: Maquina | None = None, respaldo: Path | None = None) -> Plan:
    m = maquina or Maquina()
    p = Plan(Path(origen), Path(destino), identidad=identidad(Path(origen)), espacios=espacios_de(Path(origen)),
             respaldo=Path(respaldo) if respaldo else None)
    if p.respaldo is not None and _dentro(p.respaldo, p.origen):
        p.impedimentos.append(f'{p.respaldo}: el respaldo de los espacios va fuera de la carpeta que se muda')
    if not (p.origen / '.git').is_dir():
        p.impedimentos.append(f'{p.origen}: no es la carpeta principal de un repositorio git')
    if p.identidad is None:
        p.impedimentos.append(f'{FICHERO_INSTALACION}: falta o no se lee; sin él, los espacios de trabajo quedarían '
                              'en otra carpeta de datos')
    if p.destino.exists():
        p.impedimentos.append(f'{p.destino}: ya existe')
    if os.path.splitdrive(os.path.abspath(p.origen))[0].lower() != os.path.splitdrive(os.path.abspath(p.destino))[0].lower():
        p.impedimentos.append('el destino está en otro disco: se movería copiando, no renombrando')
    vivos = m.procesos(p.origen)
    if vivos:
        p.impedimentos.append(f'{len(vivos)} programas corren desde la carpeta: ' + '; '.join(vivos[:5]))
    wts = worktrees_de(p.origen) if (p.origen / '.git').is_dir() else []
    p.worktrees = [str(w) for w in wts]
    p.uniones = uniones_hacia([p.origen, *wts], p.origen)
    p.ficheros = sorted(str(f.relative_to(p.origen)) for f in (p.origen / 'config').rglob('*.json')
                        if any(v in f.read_text(encoding='utf-8', errors='replace') for v in formas(p.origen)))
    p.entorno = {k: v for k, v in m.entorno().items() if any(f.casefold() in v.casefold() for f in formas(p.origen))}
    p.accesos = m.accesos(p.origen)
    return p


def aplicar(p: Plan, maquina: Maquina | None = None) -> list[dict]:
    m = maquina or Maquina()
    pasos: list[dict] = []

    def paso(nombre: str, ok: bool, detalle: str = '') -> bool:
        pasos.append({'paso': nombre, 'ok': ok, 'detalle': detalle})
        return ok

    if p.impedimentos:
        paso('comprobar', False, '; '.join(p.impedimentos))
        return pasos
    paso('comprobar', True)
    if p.respaldo is not None:
        paso('respaldo', True, f'{respaldar_espacios(p.origen, p.espacios, p.respaldo)} ficheros de '
                               f'{len(p.espacios)} espacios en {p.respaldo}')
    os.rename(p.origen, p.destino)
    paso('renombrar', p.destino.is_dir() and not p.origen.exists(), f'{p.origen} → {p.destino}')
    # Los worktrees que vivían dentro de la carpeta se mudaron con ella: se reparan en su ruta nueva.
    worktrees = [reemplazar_ruta(w, p.origen, p.destino) for w in p.worktrees]
    r = git('worktree', 'repair', *worktrees, cwd=p.destino)
    if not paso('worktrees', r.returncode == 0, (r.stderr or r.stdout).strip()):
        return pasos
    for u in p.uniones:
        enlace = Path(reemplazar_ruta(u['enlace'], p.origen, p.destino))
        nuevo = reemplazar_ruta(u['apunta'], p.origen, p.destino)
        if u['union'] and os.name == 'nt':
            import _winapi
            os.rmdir(enlace)  # quita la unión; rmdir nunca entra en la carpeta a la que apunta
            _winapi.CreateJunction(nuevo, str(enlace))
        else:
            enlace.unlink()
            enlace.symlink_to(nuevo, target_is_directory=True)
    paso('uniones', True, f'{len(p.uniones)} vueltas a apuntar')
    for rel in GUIONES_VENV:
        f = p.destino / '.venv' / rel
        if f.is_file():
            f.write_text(reemplazar_ruta(f.read_text(encoding='utf-8', errors='replace'), p.origen, p.destino),
                         encoding='utf-8', newline='')
    r = m.reinstalar(p.destino)
    if not paso('venv', r.returncode == 0, (r.stderr or '').strip()[-500:]):
        return pasos
    for rel in p.ficheros:
        f = p.destino / rel
        f.write_text(reemplazar_ruta(f.read_text(encoding='utf-8'), p.origen, p.destino), encoding='utf-8', newline='')
    paso('config', True, f'{len(p.ficheros)} ficheros')
    for nombre, valor in p.entorno.items():
        m.poner_entorno(nombre, reemplazar_ruta(valor, p.origen, p.destino))
    paso('entorno', True, ', '.join(sorted(p.entorno)))
    for a in p.accesos:
        viejo = Path(a['acceso'])
        nuevo = viejo.with_name(ACCESO_NUEVO)
        m.escribir_acceso(nuevo, reemplazar_ruta(a['objetivo'], p.origen, p.destino),
                          reemplazar_ruta(a['carpeta'], p.origen, p.destino))
        if nuevo != viejo:
            viejo.unlink(missing_ok=True)
    paso('accesos', True, f'{len(p.accesos)} accesos directos')
    importado = m.importar(p.destino)
    errores = [w for w in worktrees if git('status', '--short', cwd=Path(w)).returncode]
    despues = espacios_de(p.destino)
    faltan, sobran = sorted(set(p.espacios) - set(despues)), sorted(set(despues) - set(p.espacios))
    paso('verificar', _dentro(importado, p.destino) and not errores and identidad(p.destino) == p.identidad
         and not faltan and not sobran,
         f'paquete en {importado}; worktrees sin git: {errores}; identidad {identidad(p.destino)}; '
         f'{len(despues)} espacios de {len(p.espacios)} de la foto (faltan {faltan}, sobran {sobran})')
    return pasos


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument('--origen', type=Path, default=Path(__file__).resolve().parents[1])
    a.add_argument('--destino', type=Path)
    a.add_argument('--aplicar', action='store_true')
    a.add_argument('--respaldo', type=Path, help='carpeta, fuera de la que se muda, para la copia de los espacios')
    a.add_argument('--informe', type=Path)
    args = a.parse_args(argv)
    origen = args.origen.resolve()
    destino = args.destino or origen.with_name(NOMBRE_NUEVO)
    plan = planear(origen, destino, respaldo=args.respaldo)
    informe = {'plan': plan.como_dict()}
    if args.aplicar:
        informe['pasos'] = aplicar(plan)
    texto = json.dumps(informe, ensure_ascii=False, indent=1)
    if args.informe:
        args.informe.write_text(texto + '\n', encoding='utf-8')
    print(texto)
    ok = not plan.impedimentos and all(p['ok'] for p in informe.get('pasos', []))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
