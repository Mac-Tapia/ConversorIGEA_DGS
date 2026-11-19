#!/usr/bin/env python
"""Rellena la identidad 043 de los episodios del gemelo grabados sin ella, en un registro aparte (086:RF-120).

Los episodios son inmutables (024:RF-10) y su ``episode_id`` es la huella de su contenido: no se reescriben. Lo que se
puede deducir (periodo y criterio de fijas de la calibración del proyecto anterior al episodio, y la huella del perfil
vigente) va a ``identidad_043.jsonl`` del búfer, con su origen, y ``preparar_ciclo_aprendizaje.py`` lo combina con el
objeto. Por defecto solo dice qué rellenaría y de dónde; con ``--aplicar`` escribe ese registro y nada más.

  python tools/rellenar_identidad_043.py --twin BUFER [--espacios RAIZ] [--perfil P] [--aplicar --declarado-por R]
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))


def _instante(texto: str) -> datetime:
    valor = datetime.fromisoformat(str(texto))
    return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)


def _periodo(valor: Any) -> Any:
    """La lectura de una calibración guarda ``{clientes, maxima, status}``; la identidad usa el mes de la máxima."""
    return valor.get('maxima') if isinstance(valor, dict) else valor


def _episodios(twin: Path) -> list:
    """Los episodios legibles de ``objetos/``, sin abrir el índice: ``BuferEpisodios`` podría rehacerlo."""
    from convertersmartgrid.dominio.digital_twin.episode import leer_episodio
    salida = []
    for ruta in sorted((twin / 'objetos').glob('*/*.json')):
        try:
            salida.append(leer_episodio(json.loads(ruta.read_text(encoding='utf-8'))))
        except ValueError:
            continue    # un objeto ilegible no tiene identidad que rellenar; preparar_ciclo lo aparta con su motivo
    return salida


def calibraciones(episodios: list, espacios: list[Path]) -> dict[str, list[dict]]:
    """Por proyecto, las calibraciones con mes y criterio de fijas: las que capturó el gemelo y las de los espacios."""
    por_proyecto: dict[str, list[dict]] = {}
    for e in episodios:
        fisico = e.contexto_fisico or {}
        periodo, criterio = _periodo(fisico.get('period')), fisico.get('criterio_fijas')
        if str(e.accion.get('tipo') or '').startswith('ajuste') and periodo and criterio and 'ausente' not in fisico:
            por_proyecto.setdefault(str(e.nativo.get('project') or ''), []).append({
                'instante': _instante(e.creado), 'feeders': set(e.nativo.get('feeders') or ()), 'id': e.episode_id,
                'period': str(periodo), 'criterio_fijas': str(criterio),
                'origen': f'deducido del episodio de calibración {e.episode_id} del proyecto '
                          f'{e.nativo.get("project")} ({e.creado})'})
    for raiz in espacios:
        for espacio in sorted(p for p in Path(raiz).iterdir() if p.is_dir() and not p.name.startswith('_')):
            for ruta in sorted((*espacio.glob('runs/*/salida/ajuste_cabecera_aplicacion_*.json'),
                                *espacio.glob('salida/ajuste_cabecera_aplicacion_*.json'))):
                try:
                    d = json.loads(ruta.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                fecha = (d.get('objetivo') or {}).get('fecha') if isinstance(d, dict) else None
                if not isinstance(d, dict) or d.get('error') or not d.get('project') or not fecha or not d.get('criterio_fijas'):
                    continue
                por_proyecto.setdefault(str(d['project']), []).append({
                    'instante': datetime.fromtimestamp(ruta.stat().st_mtime, timezone.utc),
                    'feeders': {str(d.get('feeder') or '')} - {''}, 'id': str(ruta),
                    'period': str(fecha)[:7], 'criterio_fijas': str(d['criterio_fijas']),
                    'origen': f'deducido de la calibración {ruta} del proyecto {d["project"]}'})
    return por_proyecto


def _calibracion_anterior(e, propias: list[dict]) -> dict | None:
    """La última calibración del proyecto anterior al episodio; antes la de sus alimentadores, si la hay."""
    instante, feeders = _instante(e.creado), set(e.nativo.get('feeders') or ())
    previas = [c for c in propias if c['instante'] <= instante and c['id'] != e.episode_id]
    suyas = [c for c in previas if c['feeders'] & feeders]
    return max(suyas or previas, key=lambda c: (c['instante'], c['id']), default=None)


def huella_del_perfil(perfil: Path | None) -> tuple[str | None, str | None]:
    """``(huella, origen)`` del perfil vigente, con la herencia de ``perfiles/`` junto a él, como la web."""
    from convertersmartgrid.aplicacion.evaluacion_modelos import huella
    from convertersmartgrid.dominio.perfil_empresa import datos_perfil, ruta_perfil_activo
    ruta = Path(perfil) if perfil is not None else ruta_perfil_activo()
    if not ruta.is_file():
        return None, f'no hay perfil vigente en {ruta}'
    carpeta = ruta.parent / 'perfiles'
    datos = datos_perfil(ruta, carpeta=carpeta if carpeta.is_dir() else None)
    modificado = datetime.fromtimestamp(ruta.stat().st_mtime, timezone.utc).isoformat(timespec='seconds')
    return huella(datos), f'huella del perfil vigente {ruta} (modificado {modificado}), declarada al rellenar'


def deducir(twin: Path, espacios: list[Path], perfil: Path | None) -> dict:
    """Qué se rellenaría de cada episodio con identidad incompleta, y de dónde; lo que no, con su motivo."""
    from convertersmartgrid.adaptadores.digital_twin.buffer import CAMPOS_IDENTIDAD_043, leer_identidades_043
    from convertersmartgrid.adaptadores.digital_twin.oraculo import por_que_no_ensena
    if not (twin / 'objetos').is_dir():
        raise ValueError(f'{twin}: no tiene objetos/ de episodios')
    episodios = _episodios(twin)
    registradas = leer_identidades_043(twin)
    por_proyecto = calibraciones(episodios, espacios)
    sha_perfil, origen_perfil = huella_del_perfil(perfil)
    rellenos, sin_deducir, ya = [], {}, 0
    for e in episodios:
        fisico = e.contexto_fisico
        if fisico is None or 'ausente' in fisico:
            continue        # sin lectura nativa no hay identidad que completar: no es lo que falta
        leidos = {'period': _periodo(fisico.get('period')), 'criterio_fijas': fisico.get('criterio_fijas'),
                  'profile_hash': fisico.get('profile_hash')}
        faltan = [c for c in CAMPOS_IDENTIDAD_043 if leidos[c] is None]
        if not faltan:
            continue
        if e.episode_id in registradas:
            ya += 1
            continue
        campos, origen, motivos = {}, {}, []
        if {'period', 'criterio_fijas'} & set(faltan):
            cal = _calibracion_anterior(e, por_proyecto.get(str(e.nativo.get('project') or ''), []))
            if cal is None:
                motivos.append('ninguna calibración del proyecto anterior al episodio trae mes y criterio de fijas')
            elif leidos['period'] is not None and str(leidos['period']) != cal['period']:
                motivos.append(f'la calibración anterior es de {cal["period"]} y el episodio de {leidos["period"]}')
            elif leidos['criterio_fijas'] is not None and leidos['criterio_fijas'] != cal['criterio_fijas']:
                motivos.append(f'la calibración anterior es de criterio {cal["criterio_fijas"]} y el episodio de '
                               f'{leidos["criterio_fijas"]}')
            else:
                for campo in ('period', 'criterio_fijas'):
                    if campo in faltan:
                        campos[campo], origen[campo] = cal[campo], cal['origen']
        if 'profile_hash' in faltan:
            if sha_perfil is None:
                motivos.append(origen_perfil)
            else:
                campos['profile_hash'], origen['profile_hash'] = sha_perfil, origen_perfil
        fila = {'episode_id': e.episode_id, 'proyecto': e.nativo.get('project'), 'ensena': por_que_no_ensena(e) is None}
        if motivos:
            sin_deducir[e.episode_id] = {**fila, 'faltan': faltan, 'motivo': '; '.join(motivos)}
        else:
            rellenos.append({**fila, 'campos': campos, 'origen': origen})
    return {'rellenaria': rellenos, 'sin_deducir': sin_deducir, 'ya_registradas': ya}


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument('--twin', type=Path, required=True, help='Búfer del gemelo (con objetos/); objetos/ nunca se escribe')
    a.add_argument('--espacios', type=Path, action='append', default=[],
                   help='Raíz de espacios de la web, para leer sus calibraciones; repetible; solo se lee')
    a.add_argument('--perfil', type=Path, help='Perfil vigente (por defecto, el activo); da la huella del perfil')
    a.add_argument('--aplicar', action='store_true', help='Escribe identidad_043.jsonl en el búfer; sin ella, en seco')
    a.add_argument('--declarado-por', default='', help='Responsable de lo deducido; obligatorio con --aplicar')
    args = a.parse_args(argv)
    if args.aplicar and not args.declarado_por.strip():
        print('error: declare --declarado-por: lo que se deduce tiene responsable', file=sys.stderr)
        return 1
    try:
        resumen = deducir(args.twin, list(args.espacios), args.perfil)
        escritas = 0
        if args.aplicar and resumen['rellenaria']:
            from convertersmartgrid.adaptadores.digital_twin.buffer import (
                ESQUEMA_IDENTIDAD_043, registrar_identidades_043)
            fecha = datetime.now(timezone.utc).isoformat(timespec='seconds')
            escritas = registrar_identidades_043(args.twin, [
                {'schema': ESQUEMA_IDENTIDAD_043, 'episode_id': f['episode_id'], 'campos': f['campos'],
                 'origen': f['origen'], 'fecha': fecha, 'declarado_por': args.declarado_por.strip()}
                for f in resumen['rellenaria']])
    except (OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    print(json.dumps({**resumen, 'aplicado': bool(args.aplicar), 'escritas': escritas,
                      'cuentas': {'rellenaria': len(resumen['rellenaria']), 'sin_deducir': len(resumen['sin_deducir']),
                                  'ensenan_rellenaria': sum(f['ensena'] for f in resumen['rellenaria']),
                                  'ensenan_sin_deducir': sum(f['ensena'] for f in resumen['sin_deducir'].values())}},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
