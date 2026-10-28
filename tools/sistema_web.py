#!/usr/bin/env python
"""Un sistema eléctrico de punta a punta por la web: convertir, importar y calibrar (022:RF-56).

Hace lo mismo que el operador en la web, con la misma API y los mismos trabajos, para no
repetir a mano (o con guiones sueltos) la cadena de cada zonal. Nasca, Pisco, Ica y
Chincha (2026-10-18) se probaron así, uno tras otro y cada uno en su proyecto:

1. espera los trabajos en curso del espacio y carga la fuente si no lo está;
2. convierte por sistema eléctrico y lo importa en DIgSILENT, salvo que el espacio ya
   tenga el proyecto de ese sistema (``--reconvertir`` lo rehace);
3. sube los libros de demanda de ``--demanda-dir``, busca la máxima por barra de SET de los
   alimentadores con medidor, cruza los clientes y prepara el plan de la calibración;
4. aplica la calibración del sistema entero (``--transformadores`` antes simula y cambia
   los transformadores de las fijas sobrecargadas).

Qué carpeta es cada libro (medidores, cabecera, clientes, suministros) se reconoce por su
contenido, no por su nombre (025:RF-25b): cada empresa organiza sus carpetas a su manera.
Cualquiera se puede dar por opción. ``--periodo`` es un mes (``2026-07``) o un año entero
(``2025``, 025:RF-25): la calibración de otro año va a sus propios casos («Sin proyecto
2025»), sin tocar los de siempre.

Un corte de la conexión con la web mientras trabaja no la corta: se reintenta.

    python tools/sistema_web.py --espacio 47a003aac1f84cc6 --zonal Pisco \\
        --demanda-dir referencia --periodo 2025

Códigos de salida: 0 calibrado y válido, 1 calibrado con fallos, 2 no se pudo llegar.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

from igea_dgs.demanda_medida import (TIPOS_DEMANDA, DemandaError, clasificar_carpeta_demanda,
                                     descubrir_libro_suministros)

TERMINADOS = ('done', 'failed', 'cancelled')
#: Sin estos dos no hay calibración; sin clientes o suministros, todo por kVA (013:RF-13).
NECESARIOS = ('medidores', 'cabecera')


class Web:
    """La API de la web con reintentos: el servidor ocupado puede cortar una consulta."""

    def __init__(self, url: str, espacio: str, *, reintentos: int = 30, pausa: float = 10.0):
        self.url, self.espacio = url.rstrip('/'), espacio
        self.reintentos, self.pausa = reintentos, pausa
        self.http = requests.Session()

    def _pedir(self, metodo: str, ruta: str, **kw):
        for intento in range(self.reintentos):
            try:
                r = self.http.request(metodo, self.url + ruta, timeout=300, **kw)
                break
            except requests.RequestException as exc:
                if intento + 1 == self.reintentos:
                    raise
                print(f'  la web no respondió ({exc.__class__.__name__}); reintento', flush=True)
                time.sleep(self.pausa)
        if r.status_code >= 300:
            raise RuntimeError(f'{metodo} {ruta}: {r.status_code} {r.text[:1500]}')
        return r.json()

    def get(self, ruta: str, **kw):
        return self._pedir('GET', f'/api/workspaces/{self.espacio}{ruta}', **kw)

    def post(self, ruta: str, **kw):
        return self._pedir('POST', f'/api/workspaces/{self.espacio}{ruta}', **kw)

    def esperar(self, trabajo: dict, limite_s: float = 6 * 3600) -> dict:
        fin = time.monotonic() + limite_s
        while time.monotonic() < fin:
            estado = self._pedir('GET', f"/api/jobs/{trabajo['id']}")
            if estado['status'] in TERMINADOS:
                return estado
            time.sleep(5)
        raise TimeoutError(f"{trabajo.get('title')}: sin terminar en {limite_s / 3600:g} h")


def _resumen(estado: dict) -> tuple[int, int]:
    """Imprime el resultado de la calibración; devuelve (válidos, con fallos)."""
    validos = fallidos = 0
    resultado = estado.get('result') or {}
    sistema = resultado.get('sistema') or {}
    if sistema.get('sin_medidor'):
        print(f"Sin medidor (demanda del archivo): {', '.join(sistema['sin_medidor'])}")
    for inf in resultado.get('informes', []):
        val = inf.get('validacion_posterior_nativa') or {}
        estados = ([val.get('status')] if 'status' in val
                   else [x.get('status') for x in val.values() if isinstance(x, dict)])
        ok = bool(inf.get('cuadrado')) and all(e == 'VALIDO' for e in estados)
        validos, fallidos = validos + ok, fallidos + (not ok)
        desvio = (inf.get('desvio') or {}).get('kw')
        remedios = [x.get('remedio') for x in inf.get('remedios') or []]
        print(f"  {inf.get('feeder')}: {inf.get('status')}, {inf.get('flujos')} flujos"
              + (f', desvío {desvio:+.2%}' if desvio is not None else '')
              + (f", remedios {remedios}" if remedios else '')
              + f", validación {'/'.join(map(str, estados)) or '-'}", flush=True)
        for h in (inf.get('historial') or [])[:1]:
            if not h.get('converge'):
                print(f"    primer flujo: {h.get('motivo')}", flush=True)
    return validos, fallidos


def medidas_de(maxima: dict) -> dict[str, float]:
    """kW de cada alimentador en la máxima buscada (la de su barra o la suya)."""
    out: dict[str, float] = {}
    for x in maxima.get('resultados', []):
        if not x.get('error') and x.get('alimentador') and x.get('kw') is not None:
            out[x['alimentador']] = out.get(x['alimentador'], 0.0) + float(x['kw'])
    return out


def medida_de(alimentador: str, medidas: dict[str, float], barras: list[dict]) -> float:
    """Su medida o, sin medidor, la de su barra menos las de los demás (022:RF-59)."""
    if alimentador in medidas:
        return medidas[alimentador]
    barra = next((b for b in barras if alimentador in b.get('alimentadores', [])), None)
    # 022:RF-84: una barra de media sin registro en el instante de su barra de 60 kV no da
    # medida; la de 60 kV lleva además las pérdidas del transformador y no se reparte.
    if barra is None or barra.get('kw') is None or barra.get('alta'):
        return 0.0
    return float(barra['kw']) - sum(medidas.get(a, 0.0) for a in barra['alimentadores']
                                    if a != alimentador)


def resolver_libro_suministros(demanda_dir: Path) -> Path:
    """Elige por contenido el libro vigente, sin depender de nombres de empresa o periodo."""
    tipos, avisos = clasificar_carpeta_demanda(demanda_dir)
    if 'suministros' not in tipos:
        raise DemandaError(' '.join(a for a in avisos if '(suministros)' in a))
    return descubrir_libro_suministros(tipos['suministros'])


def libros_de_la_demanda(demanda_dir: Path, dados: dict[str, Path | None] | None = None
                         ) -> tuple[dict[str, Path], list[str]]:
    """Los libros de la demanda: los dados por opción y, los demás, por su contenido
    (025:RF-25b, RF-25c). Sin medidores o sin cabecera no se sigue."""
    dados = {t: p for t, p in (dados or {}).items() if p}
    tipos, avisos = clasificar_carpeta_demanda(demanda_dir) if demanda_dir.is_dir() else ({}, [])
    libros = {**tipos, **dados}
    avisos = [a for a in avisos if not any(f'({t})' in a for t in libros)]
    faltan = [t for t in NECESARIOS if t not in libros]
    if faltan:
        raise DemandaError(' '.join(avisos) or ('Faltan: ' + ', '.join(TIPOS_DEMANDA[t] for t in faltan)))
    if libros.get('suministros') and libros['suministros'].is_dir():
        libros['suministros'] = descubrir_libro_suministros(libros['suministros'])
    return libros, avisos


def correr(web: Web, zonal: str, *, demanda_dir: Path, periodo: str | None,
           reconvertir: bool, transformadores: bool, tension_pu: float | None,
           bancos: bool, solo: list[str] | None = None,
           reconstruir: list[str] | None = None,
           libros: dict[str, Path] | None = None) -> int:
    if libros is None:
        try:
            libros, avisos = libros_de_la_demanda(demanda_dir)
        except DemandaError as exc:
            print(f'ERROR: {exc}')
            return 2
        for aviso in avisos:
            print(f'  aviso: {aviso}', flush=True)
    for trabajo in [t for t in web.get('')['jobs'] if t['status'] not in TERMINADOS]:
        print(f"Esperando «{trabajo['title']}»…", flush=True)
        web.esperar(trabajo)
    if not web.get('').get('loaded'):
        print('Cargando la fuente…', flush=True)
        web.esperar(web.post('/load'))
    grupo = f'SISTEMA_{zonal.upper()}'
    proyecto = (web.get('').get('pf_projects') or {}).get(grupo)
    if proyecto is None or reconvertir:
        estado = web.esperar(web.post('/convert/sistema', json={'zonales': [zonal]}))
        res = estado.get('result') or {}
        print(f"Conversión: {estado['status']} {res.get('status')} {res.get('group')}", flush=True)
        if res.get('status') != 'ok':
            print(f"ERROR: {res.get('error') or estado.get('error')}")
            return 2
        estado = web.esperar(web.post('/powerfactory/flow', json={'feeders': [res['group']]}))
        print(f"DIgSILENT: {estado['status']} {(estado.get('result') or {}).get('lines')}", flush=True)
        proyecto = (web.get('').get('pf_projects') or {}).get(res['group'])
        if proyecto is None:
            print(f"ERROR: la importación no dejó proyecto: {estado.get('error')}")
            return 2
    print(f'Proyecto: {proyecto}', flush=True)
    for tipo in TIPOS_DEMANDA:
        if tipo in libros:
            print(f'  {TIPOS_DEMANDA[tipo]}: {libros[tipo]}', flush=True)
            web.post(f'/demanda/{tipo}/path', json={'path': str(libros[tipo])})
    # 025:RF-28, RF-34: el índice por año de la cabecera, el mismo que ve el operador.
    web.esperar(web.post('/demanda/cabecera/indexar'))
    if 'clientes' in libros:
        web.esperar(web.post('/demanda/clientes/indexar'))
    sistema = web.get('/demanda/sistema', params={'project': proyecto})['sistema']
    if sistema is None:
        print(f'ERROR: {proyecto} no es un proyecto por sistema eléctrico.')
        return 2
    # ``solo``: una parte del sistema, con el resto en los mismos flujos y la demanda del
    # archivo, para aislar qué alimentador impide converger (Chincha, 2026-10-18).
    elegidos = {a.upper() for a in solo or []}
    pares = [{'alimentador': a, 'medidor': m}
             for a, ms in sistema['medidores'].items() for m in ms
             if not elegidos or a.upper() in elegidos]
    print(f"{sistema['grupo']}: {len(sistema['alimentadores'])} alimentadores, "
          f"{len({p['alimentador'] for p in pares})} con medidor", flush=True)
    if not pares:
        print('Ningún alimentador del sistema tiene medidor: no hay qué calibrar.')
        return 2
    # 022:RF-88: dónde está cada central del libro, con la propuesta del perfil, como la ve
    # el operador en la web (la de Nasca en el tramo de NA205; CT_PEDREG en su barra).
    centrales = web.get('/demanda/centrales').get('centrales') or []
    del_sistema = {a.upper() for a in sistema['alimentadores']}
    tramo = {c['medidor']: c['tramo'] for c in centrales
             if c.get('tramo') and c['tramo'].upper() in del_sistema}
    for c in centrales:
        print(f"  central {c['medidor']} ({c['set'] or 'sin SET'}, {c['kv']} kV): "
              + (f"en el tramo de {c['tramo']}" if c.get('tramo') else 'en la barra'), flush=True)
    maxima = web.esperar(web.post('/demanda/cabecera/buscar', json={
        'medidores': pares, 'periodo': periodo, 'por_barra': True, 'centrales_tramo': tramo}))
    res = maxima.get('result') or {}
    for b in sorted(res.get('barras', []),
                    key=lambda x: (x.get('set', ''), not x.get('alta'), -float(x.get('kv') or 0))):
        trafos = b.get('transformadores') or {}
        medidos = ' + '.join(f'{m} ({trafos[m]})' if trafos.get(m) else m
                             for m in b.get('medidores') or [])
        kw = 'sin registro' if b.get('kw') is None else f"{b['kw']:,.1f} kW"
        centrales_b = b.get('centrales') or []
        print(f"  barra {b['clave']}: {kw} el {b['fecha']} [{medidos}]"
              + (f" en el instante de {b['de_alta']}" if b.get('de_alta') else '')
              + (f"; centrales {', '.join(c['medidor'] for c in centrales_b)}" if centrales_b else '')
              + (f" ({', '.join(b['alimentadores'])})" if b.get('alimentadores') else ''), flush=True)
    for aviso in res.get('avisos', []):
        print(f'  aviso: {aviso}', flush=True)
    # Los de una central («Central NA205», 022:RF-88) solo traen su curva al mismo instante:
    # no son cabeceras de alimentador y el plan los rechazaba (PROJECT_BINDING_FEEDER_MISMATCH,
    # Nasca, 2026-10-27), como ya los deja fuera la web al elegir los del ajuste.
    medidores = [x['medidor'] for x in res.get('resultados', [])
                 if not x.get('error') and not str(x.get('alimentador') or '').lower().startswith('central ')]
    if reconstruir:
        # 022:RF-57 a RF-61: con las medidas de esta máxima, se reconvierte uniendo cada uno a
        # la red de su vecino, se importa de nuevo y se calibra el proyecto nuevo.
        medidas = medidas_de(res)
        pedidos = {a: medida_de(a, medidas, res.get('barras', [])) for a in reconstruir}
        print(f'Reconstruir por medida: {pedidos}', flush=True)
        estado = web.esperar(web.post('/convert/sistema', json={
            'zonales': [zonal], 'reconstruir': pedidos, 'medidas_kw': medidas}))
        resultado = estado.get('result') or {}
        if resultado.get('status') != 'ok':
            print(f"ERROR: {resultado.get('error') or estado.get('error')}")
            return 2
        for r in ((resultado.get('estructura') or {}).get('reconstrucciones') or []):
            print(f"  {r['texto']}", flush=True)
        estado = web.esperar(web.post('/powerfactory/flow', json={'feeders': [resultado['group']]}))
        print(f"DIgSILENT: {estado['status']} {(estado.get('result') or {}).get('lines')}", flush=True)
        return correr(web, zonal, demanda_dir=demanda_dir, periodo=periodo, reconvertir=False,
                      transformadores=transformadores, tension_pu=tension_pu, bancos=bancos,
                      solo=solo, libros=libros)
    if 'clientes' in libros and 'suministros' in libros and (not periodo or len(periodo) == 7):
        # Con un año entero no hay un mes que cruzar aquí: el plan cruza cada alimentador
        # con el libro del mes de su máxima (025:RF-10).
        web.post('/demanda/clientes/cruzar', json={'alimentadores': sistema['alimentadores'],
                                                    'periodo': periodo})
    # El vínculo exige que la última relectura de DIgSILENT vea el proyecto (spec 018): tras
    # importar, Chincha (2026-10-18) dio PROJECT_BINDING_PROJECT_MISMATCH sin ella.
    web.esperar(web.post('/powerfactory/projects'))
    plan = web.post('/demanda/ajuste/plan', json={
        'project': proyecto, 'job_id': maxima['id'], 'medidores': medidores,
        'completar_bancos': bancos, 'tension_fuente_pu': tension_pu})
    for aviso in plan.get('avisos', []):
        if 'RF-62' not in aviso:              # las fijas compensadas, una por cliente
            print(f'  aviso: {aviso}', flush=True)
    token = plan['token']
    ultimo = None
    if transformadores:
        # 022:RF-62: los de todos los alimentadores y una sola recalibración del proyecto.
        sim = web.esperar(web.post(f'/demanda/ajuste/{token}/simular'))
        pedidos = {}
        for inf in (sim.get('result') or {}).get('informes', []):
            seds = [x['sed'] for x in inf.get('fijas_sobre_su_transformador') or []
                    if (x.get('propuesta') or {}).get('kva')
                    and len(x.get('transformadores') or []) == 1]
            if seds:
                pedidos[inf['feeder']] = seds
                print(f"Transformadores nuevos en {inf['feeder']}: {', '.join(seds)}", flush=True)
        if pedidos:
            ultimo = web.esperar(web.post(f'/demanda/ajuste/{token}/transformadores',
                                          json={'por_alimentador': pedidos}))
    if ultimo is None:
        ultimo = web.esperar(web.post(f'/demanda/ajuste/{token}/aplicar'))
    print(f"Calibración: {ultimo['status']} {ultimo.get('error') or ''}", flush=True)
    validos, fallidos = _resumen(ultimo)
    print(f'{validos} válido(s), {fallidos} con fallos.')
    return 0 if validos and not fallidos else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Convierte, importa y calibra un sistema eléctrico '
                                            'entero por la web (spec 022 y 025)')
    p.add_argument('--espacio', required=True, help='Id del espacio de trabajo de la web')
    p.add_argument('--zonal', required=True, help='Zonal de la estructura (Nasca, Pisco…)')
    p.add_argument('--demanda-dir', type=Path, required=True,
                   help='Carpeta con los libros de demanda; cada uno se reconoce por su contenido')
    p.add_argument('--medidores', type=Path, help='Libro de medidores por alimentador')
    p.add_argument('--cabecera', type=Path, help='Libro o carpeta (con sus años) de la cabecera')
    p.add_argument('--clientes', type=Path, help='Libro o carpeta de los clientes importantes')
    p.add_argument('--suministros', type=Path, help='Libro o carpeta de suministros')
    p.add_argument('--periodo', help='Mes AAAA-MM o año entero AAAA de la medición (025:RF-25)')
    p.add_argument('--url', default='http://127.0.0.1:8765', help='Dirección de la web')
    p.add_argument('--reconvertir', action='store_true',
                   help='Convertir e importar aunque el espacio ya tenga el proyecto')
    p.add_argument('--transformadores', action='store_true',
                   help='Cambiar antes los transformadores de las fijas sobrecargadas (spec 020)')
    p.add_argument('--tension-pu', type=float, help='Tensión en la fuente en p.u. (021:RF-61)')
    p.add_argument('--sin-bancos', action='store_true', help='No poner los bancos que faltan')
    p.add_argument('--reconstruir', nargs='+', metavar='COD',
                   help='Unir estos a la red vecina por el tramo que falta y repartir por medida '
                        '(022:RF-57 a RF-61); reconvierte e importa de nuevo')
    p.add_argument('--alimentadores', nargs='+', metavar='COD',
                   help='Calibrar solo estos; los demás del sistema, con la demanda del archivo')
    args = p.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except (AttributeError, ValueError):
        pass
    web = Web(args.url, args.espacio)
    try:
        demanda_dir = args.demanda_dir.resolve()
        dados = {t: (p if p.is_absolute() else demanda_dir / p)
                 for t, p in (('medidores', args.medidores), ('cabecera', args.cabecera),
                              ('clientes', args.clientes), ('suministros', args.suministros)) if p}
        libros, avisos = libros_de_la_demanda(demanda_dir, dados)
        for aviso in avisos:
            print(f'  aviso: {aviso}', flush=True)
        return correr(web, args.zonal, demanda_dir=demanda_dir,
                      periodo=args.periodo, reconvertir=args.reconvertir,
                      transformadores=args.transformadores, tension_pu=args.tension_pu,
                      bancos=not args.sin_bancos, solo=args.alimentadores,
                      reconstruir=args.reconstruir, libros=libros)
    except (RuntimeError, TimeoutError, DemandaError, requests.RequestException) as exc:
        print(f'ERROR: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
