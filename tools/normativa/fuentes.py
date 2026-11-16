"""Comprobación permanente de las fuentes oficiales (orden de 28, 2026-11-15): todo generador o lector que use una
fuente oficial comprueba ANTES su sha256 contra el registrado; si no coincide, error claro con el fichero y los dos sha,
y se para. Motivo: los .xls de la RCD 217-2013 en NORMATIVA_OSINERGMIN se reescribieron al abrirlos con WPS por COM
(mismos valores, otros bytes) y un análisis se hizo sobre esas copias sin advertirlo.

Uso desde un generador:
    from fuentes import comprobar, comprobar_carpeta
    comprobar(ruta, sha_esperado)              # una fuente con su sha del registro
    comprobar_carpeta(carpeta)                 # todas las de una carpeta contra su SHA256SUMS.txt
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


class FuenteAlterada(SystemExit):
    """La fuente oficial no es la registrada: el generador se para."""


def sha256(ruta: Path | str) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def comprobar(ruta: Path | str, esperado: str) -> Path:
    ruta = Path(ruta)
    real = sha256(ruta)
    if real != esperado.lower():
        raise FuenteAlterada(f'FUENTE ALTERADA: {ruta} tiene sha256 {real} y el registrado es {esperado}. '
                             'No se lee: recupere el original (por ejemplo, del comprimido oficial) y repita.')
    return ruta


def sumas(carpeta: Path | str) -> dict[str, str]:
    """{nombre: sha256} de SHA256SUMS.txt (formato «sha  *nombre» o «sha  nombre»)."""
    tabla = {}
    for linea in (Path(carpeta) / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        if linea.strip() and not linea.startswith('#'):
            sha, nombre = linea.split(maxsplit=1)
            tabla[nombre.lstrip('*').strip()] = sha
    return tabla


def comprobar_carpeta(carpeta: Path | str, patron: str = '*') -> list[Path]:
    """Comprueba cada fichero de ``carpeta`` que encaje con ``patron`` contra SHA256SUMS.txt; uno sin suma es error."""
    carpeta = Path(carpeta)
    tabla = sumas(carpeta)
    salida = []
    for f in sorted(carpeta.glob(patron)):
        if f.name in ('SHA256SUMS.txt', 'LEEME.txt') or not f.is_file():
            continue
        if f.name not in tabla:
            raise FuenteAlterada(f'FUENTE SIN SUMA: {f} no está en {carpeta / "SHA256SUMS.txt"}; no se lee.')
        salida.append(comprobar(f, tabla[f.name]))
    return salida


# El usuario de la máquina se arma por partes para que el propio patrón no sea una ruta de la máquina.
_USUARIO = 'Lenovo' + ' ' + 'Legion'
_RUTA_ABSOLUTA = re.compile(r'(?<![^\W\d_])[A-Za-z]:[\\/]|(?<![A-Za-z0-9_.-])/d/|' + _USUARIO + r'|Users/')
_CC = re.compile(r'[A-Za-z]:/csg/PM_IMPL/CC_APOYO/([^/\s)]+)(?:/[^\s)]*)?')
_GEN = re.compile(r'[A-Za-z]:/csg/PM_IMPL/[^\s)]*/(generar_[a-z0-9_]+\.py)')


def sin_rutas(datos, raiz: Path | str):
    """El registro sin rutas de la máquina: ``fichero_local`` relativo a ``raiz`` (la carpeta de las fuentes
    oficiales, fuera de git), la procedencia del apoyo citada por su frente y «Generado por tools/normativa/…». Si
    queda alguna ruta absoluta, error: el registro va al repositorio."""
    raiz = Path(raiz).resolve().as_posix().rstrip('/') + '/'

    def limpiar(v, clave=''):
        if isinstance(v, dict):
            return {k: limpiar(x, k) for k, x in v.items()}
        if isinstance(v, list):
            return [limpiar(x) for x in v]
        if not isinstance(v, str):
            return v
        if clave == 'fichero_local':
            p = Path(v).resolve().as_posix() if re.match(r'[A-Za-z]:[\\/]', v) else v
            v = p[len(raiz):] if p.startswith(raiz) else p
        else:
            v = v.replace(raiz, '<fuentes>/')
        v = _GEN.sub(r'tools/normativa/\1', v)
        v = _CC.sub(lambda m: f'apoyo (cc), frente «{m.group(1)}»', v)
        if _RUTA_ABSOLUTA.search(v):
            raise FuenteAlterada(f'RUTA DE LA MÁQUINA en el registro ({clave or "texto"}): {v[:160]}')
        return v
    return limpiar(datos)
