#!/usr/bin/env python
"""Aceptación automática de una versión del conversor (spec 100): recorre la matriz de casos y da su veredicto.

La matriz (``config/aceptacion/matriz.json``) dice cada caso: su fuente (TXT, MDB o VNR-GIS, nunca mezcladas), su
alcance (un alimentador, varios unidos o un sistema entero), la herramienta que lo corre como el operador
(``tools/sistema_web.py`` por la web, ``tools/aceptacion_nativa.py`` por el arnés de DIgSILENT) y sus argumentos. Los
datos de la empresa no están en la matriz: sus ``${CSG_...}`` salen del entorno o de ``--variables`` (un JSON fuera de
git). Nada de esto crea tareas ni casillas de pendiente (RF-4): el resultado es el informe.

- Recorrido en serie (RF-2): un caso tras otro, sin intervención. Un caso que se corta por una causa recuperable (lo
  dice el código de salida de su herramienta, declarado en la matriz) se relanza hasta los ``intentos`` de la matriz;
  al relanzar la aceptación entera, los casos ya aceptados sobre la misma versión no se repiten (RF-5).
- Informe por caso (RF-3): ``<salida>/casos/<id>.json`` con la revisión, el estado, el rc, la duración, los intentos,
  las cifras de la herramienta (su resumen JSON) y las huellas sha256 del registro y del resumen; y
  ``<salida>/informe.json`` con la versión, el árbol, la hora de inicio y de fin, cada caso y el veredicto.
- Veredicto (RF-7): la versión queda aceptada solo si todos los casos de la matriz se aceptaron sobre esa misma
  revisión. Un fallo del conversor (RF-6) va con su causa al informe y deja un borrador de comprobación permanente en
  ``docs/regresiones/pendientes/`` (081:RF-46: entra en ``docs/regresiones/`` con la prueba que lo reproduce, en el
  cambio que lo corrige).

    python tools/aceptacion_version.py --matriz config/aceptacion/matriz.json --version <hash> --salida <carpeta>
        [--desde <caso>] [--solo <id,...>] [--variables vars.json]

Códigos de salida: 0 versión aceptada; 1 no aceptada (el informe dice qué caso y por qué); 2 matriz inválida.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ESQUEMA = 'aceptacion_matriz_v1'
FUENTES = ('txt', 'mdb', 'vnr')
ALCANCES = ('alimentador', 'varios', 'sistema')
ESTADOS = ('aceptado', 'fallo', 'recuperable')
CAMPOS_CASO = {'id', 'fuente', 'alcance', 'herramienta', 'argumentos'}
_VARIABLE = re.compile(r'\$\{([A-Z][A-Z0-9_]*)\}')

#: ``ejecutar(argv, registro, cwd) -> rc``: corre la herramienta y deja su salida en ``registro``. Las pruebas la
#: sustituyen por una web falsa.
Ejecutor = Callable[[Sequence[str], Path, Path], int]


class MatrizError(ValueError):
    """La matriz no se puede usar: dice por qué."""


def cargar_matriz(ruta: Path | str) -> dict[str, Any]:
    """La matriz validada (RF-1, RF-5): cada fuente con cada alcance, un caso de una sola fuente, ids únicos,
    herramientas declaradas con su significado de cada código, y ningún dato literal de una empresa en los argumentos
    que lo son (espacio, red, zonal): esos van como ``${CSG_...}``."""
    try:
        m = json.loads(Path(ruta).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatrizError(f'no se puede leer la matriz {ruta}: {exc}') from exc
    if not isinstance(m, dict) or m.get('esquema') != ESQUEMA:
        raise MatrizError(f'{ruta}: no es una matriz de aceptación ({ESQUEMA})')
    if not isinstance(m.get('intentos'), int) or m['intentos'] < 1:
        raise MatrizError('la matriz necesita «intentos», un entero de 1 o más: los relanzamientos de un caso')
    herramientas = m.get('herramientas')
    if not isinstance(herramientas, dict) or not herramientas:
        raise MatrizError('la matriz no declara sus herramientas')
    for nombre, h in herramientas.items():
        if not isinstance(h, dict) or not str(h.get('guion') or '').strip():
            raise MatrizError(f'la herramienta {nombre} no dice su guion')
        codigos = h.get('codigos')
        if not isinstance(codigos, dict) or '0' not in codigos or set(codigos.values()) - set(ESTADOS):
            raise MatrizError(f'la herramienta {nombre}: «codigos» tiene que dar el 0 y solo {", ".join(ESTADOS)}')
    casos = m.get('casos')
    if not isinstance(casos, list) or not casos:
        raise MatrizError('la matriz no trae casos')
    vistos: set[str] = set()
    cubiertos: set[tuple[str, str]] = set()
    for c in casos:
        if not isinstance(c, dict) or set(c) != CAMPOS_CASO:
            raise MatrizError(f'un caso tiene que traer exactamente {sorted(CAMPOS_CASO)}: {c!r}')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', str(c['id'])) or c['id'] in vistos:
            raise MatrizError(f'id de caso inválido o repetido: {c["id"]!r}')
        vistos.add(c['id'])
        if c['fuente'] not in FUENTES or c['alcance'] not in ALCANCES:
            raise MatrizError(f'{c["id"]}: fuente {c["fuente"]!r} o alcance {c["alcance"]!r} desconocidos')
        if c['herramienta'] not in herramientas:
            raise MatrizError(f'{c["id"]}: la herramienta {c["herramienta"]!r} no está declarada')
        args = c['argumentos']
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise MatrizError(f'{c["id"]}: «argumentos» tiene que ser una lista de textos')
        for opcion, valor in itertools.pairwise(args):
            if opcion in ('--espacio', '--red', '--zonal', '--set', '--alimentador', '--proyecto') \
                    and not _VARIABLE.fullmatch(valor):
                raise MatrizError(f'{c["id"]}: {opcion} {valor!r} es un dato de la empresa; va como ${{CSG_...}}')
        cubiertos.add((c['fuente'], c['alcance']))
    faltan = sorted({(f, a) for f in FUENTES for a in ALCANCES} - cubiertos)
    if faltan:
        raise MatrizError('faltan en la matriz: ' + ', '.join(f'{f} con {a}' for f, a in faltan))
    return m


def resolver_argumentos(args: Sequence[str], variables: Mapping[str, str]) -> tuple[list[str] | None, list[str]]:
    """Los argumentos con sus ``${VAR}`` resueltas; un argumento que es solo una variable con espacios da varios
    (``--red A B``). Si falta alguna variable: None y cuáles faltan."""
    faltan = sorted({v for a in args for v in _VARIABLE.findall(a) if not str(variables.get(v) or '').strip()})
    if faltan:
        return None, faltan
    salida: list[str] = []
    for a in args:
        m = _VARIABLE.fullmatch(a)
        if m:
            salida += str(variables[m.group(1)]).split()
        else:
            salida.append(_VARIABLE.sub(lambda x: str(variables[x.group(1)]), a))
    return salida, []


def _sha256(ruta: Path) -> str | None:
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.is_file() else None


def _ahora() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds')


def _ejecutar_proceso(argv: Sequence[str], registro: Path, cwd: Path) -> int:
    with registro.open('w', encoding='utf-8') as salida:
        return subprocess.run(list(argv), cwd=cwd, stdout=salida, stderr=subprocess.STDOUT, check=False).returncode


def _arbol(repo: Path) -> str | None:
    try:
        r = subprocess.run(['git', 'write-tree'], cwd=repo, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return r.stdout.strip() or None


def correr_caso(matriz: Mapping[str, Any], caso: Mapping[str, Any], version: str, salida: Path,
                variables: Mapping[str, str], ejecutar: Ejecutor = _ejecutar_proceso, *, repo: Path = REPO,
                python: str = sys.executable) -> dict[str, Any]:
    """Un caso de la matriz, con sus relanzamientos (RF-5), y su informe (RF-3)."""
    h = matriz['herramientas'][caso['herramienta']]
    inicio = time.monotonic()
    informe: dict[str, Any] = {'id': caso['id'], 'fuente': caso['fuente'], 'alcance': caso['alcance'],
                               'herramienta': caso['herramienta'], 'revision': version, 'inicio': _ahora(),
                               'intentos': 0, 'rc': None, 'estado': None, 'causa': '', 'cifras': None,
                               'evidencia': [], 'huellas': {}}
    args, faltan = resolver_argumentos(caso['argumentos'], variables)
    if args is None:
        informe.update(estado='sin_datos', causa=f'faltan las variables {", ".join(faltan)}: el caso no se corrió')
    else:
        carpeta = salida / 'casos' / caso['id']
        carpeta.mkdir(parents=True, exist_ok=True)
        while informe['intentos'] < int(matriz['intentos']):
            informe['intentos'] += 1
            registro = carpeta / f'intento_{informe["intentos"]}.log'
            resumen = carpeta / f'resumen_{informe["intentos"]}.json'
            argv = [python, str(repo / h['guion']), *args] + ([h['resumen'], str(resumen)] if h.get('resumen') else [])
            rc = ejecutar(argv, registro, repo)
            estado = h['codigos'].get(str(rc), 'fallo')
            informe.update(rc=rc, estado=estado)
            informe['evidencia'].append(str(registro))
            informe['huellas'][registro.name] = _sha256(registro)
            if resumen.is_file():
                informe['huellas'][resumen.name] = _sha256(resumen)
                try:
                    informe['cifras'] = json.loads(resumen.read_text(encoding='utf-8'))
                except json.JSONDecodeError as exc:
                    informe['cifras'] = {'ilegible': str(exc)}
            if estado != 'recuperable':
                break
        if informe['estado'] == 'recuperable':
            informe.update(estado='fallo', causa=f'se cortó {informe["intentos"]} veces por una causa recuperable '
                                                 f'(último rc={informe["rc"]}); se agotaron los intentos de la matriz')
        elif informe['estado'] == 'fallo' and not informe['causa']:
            informe['causa'] = (f'{h["guion"]} terminó con rc={informe["rc"]}: defecto del conversor; las cifras y el '
                                'registro dicen dónde')
    informe['fin'] = _ahora()
    informe['duracion_s'] = round(time.monotonic() - inicio, 3)
    return informe


def veredicto(casos: Mapping[str, Mapping[str, Any]], matriz: Mapping[str, Any], version: str) -> dict[str, Any]:
    """Aceptada solo si todos los casos de la matriz están aceptados sobre esta misma revisión (RF-7)."""
    no = []
    for c in matriz['casos']:
        r = casos.get(c['id'])
        if r is None:
            no.append(f'{c["id"]}: sin correr')
        elif r.get('revision') != version:
            no.append(f'{c["id"]}: aceptado sobre otra revisión ({str(r.get("revision"))[:12]})')
        elif r.get('estado') != 'aceptado':
            no.append(f'{c["id"]}: {r.get("estado")}: {r.get("causa")}')
    return {'aceptada': not no, 'version': version, 'motivos': no}


def borrador_de_regresion(caso: Mapping[str, Any], version: str, carpeta: Path) -> Path:
    """El borrador de la comprobación permanente de un fallo (RF-6, 081:RF-46), con sus cuatro apartados; entra en
    ``docs/regresiones/`` con su prueba en el cambio que lo corrige."""
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f'{datetime.now(UTC):%Y-%m-%d}-aceptacion-{caso["id"]}.md'
    evidencia = '\n'.join(f'- `{e}` (sha256 {caso["huellas"].get(Path(e).name)})' for e in caso.get('evidencia') or ())
    ruta.write_text(
        f'# Aceptación de la versión {version[:12]}: falla el caso «{caso["id"]}»\n\n'
        f'## Síntoma\nEl caso {caso["id"]} ({caso["fuente"]}, {caso["alcance"]}) terminó en «{caso["estado"]}» con '
        f'rc={caso["rc"]} tras {caso["intentos"]} intento(s).\n{evidencia}\n\n'
        f'## Causa\n{caso["causa"]}\n\n'
        '## Comprobación permanente\nPor escribir en el cambio que lo corrige: la comprobación que impide que vuelva.\n\n'
        '## Prueba\nPor escribir: la prueba que reproduce el fallo con datos sintéticos; con ella, esta entrada sube a '
        '`docs/regresiones/`.\n', encoding='utf-8', newline='\n')
    return ruta


def aceptar_version(matriz: Mapping[str, Any], version: str, salida: Path | str, *,
                    variables: Mapping[str, str] | None = None, desde: str | None = None,
                    solo: Sequence[str] | None = None, ejecutar: Ejecutor = _ejecutar_proceso, repo: Path = REPO,
                    regresiones: Path | None = None) -> dict[str, Any]:
    """El recorrido en serie de la matriz y el informe de la versión (RF-2, RF-3, RF-5, RF-6, RF-7)."""
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    variables = dict(os.environ if variables is None else variables)
    ids = [c['id'] for c in matriz['casos']]
    for pedido in [desde, *(solo or ())]:
        if pedido is not None and pedido not in ids:
            raise MatrizError(f'el caso {pedido!r} no está en la matriz')
    previo_ruta = salida / 'informe.json'
    previo = json.loads(previo_ruta.read_text(encoding='utf-8')) if previo_ruta.is_file() else {}
    casos: dict[str, Any] = dict(previo.get('casos') or {}) if previo.get('version') == version else {}
    informe: dict[str, Any] = {'version': version, 'arbol': _arbol(repo), 'inicio': _ahora(), 'casos': casos}
    empezar = ids.index(desde) if desde else 0
    for c in matriz['casos'][empezar:]:
        if solo and c['id'] not in solo:
            continue
        hecho = casos.get(c['id'])
        if hecho and hecho.get('estado') == 'aceptado' and hecho.get('revision') == version:
            continue  # RF-5: relanzar desde donde quedó, sin repetir lo aceptado sobre la misma versión
        r = correr_caso(matriz, c, version, salida, variables, ejecutar, repo=repo)
        if r['estado'] == 'fallo':
            r['regresion'] = str(borrador_de_regresion(r, version, regresiones or repo / 'docs' / 'regresiones'
                                                       / 'pendientes'))
        casos[c['id']] = r
        (salida / 'casos').mkdir(parents=True, exist_ok=True)
        (salida / 'casos' / f'{c["id"]}.json').write_text(json.dumps(r, ensure_ascii=False, indent=1) + '\n',
                                                          encoding='utf-8')
        previo_ruta.write_text(json.dumps({**informe, 'casos': casos}, ensure_ascii=False, indent=1) + '\n',
                               encoding='utf-8')
    informe['fin'] = _ahora()
    informe['veredicto'] = veredicto(casos, matriz, version)
    previo_ruta.write_text(json.dumps(informe, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return informe


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--matriz', type=Path, default=REPO / 'config' / 'aceptacion' / 'matriz.json')
    p.add_argument('--version', required=True, help='Revisión (hash) que se acepta')
    p.add_argument('--salida', type=Path, required=True, help='Carpeta del informe de la versión')
    p.add_argument('--desde', help='Empieza en este caso de la matriz')
    p.add_argument('--solo', help='Solo estos casos, separados por comas')
    p.add_argument('--variables', type=Path, help='JSON con los ${CSG_...} de la matriz (fuera de git)')
    a = p.parse_args(argv)
    try:
        matriz = cargar_matriz(a.matriz)
        variables = dict(os.environ)
        if a.variables:
            variables.update({k: str(v) for k, v in json.loads(a.variables.read_text(encoding='utf-8')).items()})
        informe = aceptar_version(matriz, a.version, a.salida, variables=variables, desde=a.desde,
                                  solo=[s for s in (a.solo or '').split(',') if s] or None)
    except MatrizError as exc:
        print(f'matriz inválida: {exc}', file=sys.stderr)
        return 2
    v = informe['veredicto']
    print(f'versión {a.version}: {"ACEPTADA" if v["aceptada"] else "NO ACEPTADA"}')
    for m in v['motivos']:
        print(f'  {m}')
    return 0 if v['aceptada'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
