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

Un corte de la conexión con la web mientras trabaja no la corta: se reintenta.

    python tools/sistema_web.py --espacio 47a003aac1f84cc6 --zonal Pisco \\
        --demanda-dir referencia --periodo 2026-07

Códigos de salida: 0 calibrado y válido, 1 calibrado con fallos, 2 no se pudo llegar.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

LIBROS = (('medidores', '1.-medidoralimentador/medidoralimentador.xlsx'),
          ('cabecera', '2.-medicioncabecera'),
          ('suministros', '3.-suministrocliente/ML_1225.xlsx'),
          ('clientes', '4.-clientesimportantes'))
TERMINADOS = ('done', 'failed', 'cancelled')


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
    if barra is None:
        return 0.0
    return float(barra['kw']) - sum(medidas.get(a, 0.0) for a in barra['alimentadores']
                                    if a != alimentador)


def correr(web: Web, zonal: str, *, demanda_dir: Path, periodo: str | None,
           reconvertir: bool, transformadores: bool, tension_pu: float | None,
           bancos: bool, solo: list[str] | None = None,
           reconstruir: list[str] | None = None) -> int:
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
    for tipo, ruta in LIBROS:
        web.post(f'/demanda/{tipo}/path', json={'path': str(demanda_dir / ruta)})
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
    maxima = web.esperar(web.post('/demanda/cabecera/buscar', json={
        'medidores': pares, 'periodo': periodo, 'por_barra': True}))
    res = maxima.get('result') or {}
    for b in res.get('barras', []):
        print(f"  barra {b['clave']}: {b['kw']:,.1f} kW el {b['fecha']} "
              f"({', '.join(b['alimentadores'])})", flush=True)
    medidores = [x['medidor'] for x in res.get('resultados', []) if not x.get('error')]
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
                      solo=solo)
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
                                            'entero por la web (spec 022)')
    p.add_argument('--espacio', required=True, help='Id del espacio de trabajo de la web')
    p.add_argument('--zonal', required=True, help='Zonal de la estructura (Nasca, Pisco…)')
    p.add_argument('--demanda-dir', type=Path, required=True,
                   help='Carpeta con los cuatro libros de demanda (medidores, cabecera…)')
    p.add_argument('--periodo', help='Mes de análisis AAAA-MM')
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
        return correr(web, args.zonal, demanda_dir=args.demanda_dir.resolve(),
                      periodo=args.periodo, reconvertir=args.reconvertir,
                      transformadores=args.transformadores, tension_pu=args.tension_pu,
                      bancos=not args.sin_bancos, solo=args.alimentadores,
                      reconstruir=args.reconstruir)
    except (RuntimeError, TimeoutError, requests.RequestException) as exc:
        print(f'ERROR: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
