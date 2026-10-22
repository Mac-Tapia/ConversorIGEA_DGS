#!/usr/bin/env python
"""Aceptación nativa del caso dorado del gemelo digital (spec 024, T8, RF-24 a RF-27).

Lee dos veces el proyecto de DIgSILENT, cada vez en un proceso nuevo, con
``tools/digital_twin_snapshot_pf.py`` (solo lectura), comprueba los hechos del caso
dorado y registra su episodio en el búfer. Los hechos (proyecto, nodos, enlace,
seccionador, tensiones) van en el JSON ``--esperado``, no en el código: el caso de
Electro Dunas es IN111–TA225, y otro caso dorado es otro JSON.

    python tools/accept_digital_twin_in111_ta225.py --esperado caso.json --output-json informe.json

Códigos de salida: 0 aceptado, 2 alguna comprobación falla o no hay vínculo, 3 sin API.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve()
LECTURA = HERE.with_name('digital_twin_snapshot_pf.py')


def _por_nombre(lectura: dict) -> dict[str, str]:
    """Nombre de barra → identidad, de la lectura."""
    return {v['nombre']: k for k, v in ((lectura.get('topologia') or {}).get('barras') or {}).items()}


def _componente(lectura: dict, ident: str | None) -> list[str]:
    return next((c for c in (lectura.get('topologia') or {}).get('componentes') or [] if ident in c), [])


def comprobar(a: dict, b: dict, esperado: dict) -> dict[str, dict]:
    """Los hechos del caso dorado en la segunda lectura, y que las dos coinciden (RF-24 a RF-27)."""
    tol = float(esperado.get('tolerancia_pu', 0.002))
    nombres = _por_nombre(b)
    barras = (b.get('topologia') or {}).get('barras') or {}
    origen, destino = (nombres.get(esperado['nodos'][k]) for k in ('origen', 'transferido'))
    c_origen, c_destino = _componente(b, origen), _componente(b, destino)
    kv = {i: (barras.get(i) or {}).get('kv') for i in set(c_origen) | set(c_destino)}

    def cerca(x, y):
        return x is not None and abs(float(kv[x] or 0) - y) <= 0.05 * y

    out = {}
    out['nodos_presentes'] = {'pass': origen is not None and destino is not None,
                              'detalle': esperado['nodos']}
    out['sin_continuidad'] = {'pass': bool(c_origen) and destino not in c_origen,
                              'detalle': 'el nodo transferido no está en la isla del de origen'}
    out['tension_origen'] = {'pass': bool(c_origen) and all(cerca(i, esperado['kv_origen']) for i in c_origen),
                             'detalle': f"isla de origen a {esperado['kv_origen']} kV"}
    out['tension_transferida'] = {'pass': any(cerca(i, esperado['kv_transferido']) for i in c_destino),
                                  'detalle': f"isla transferida a {esperado['kv_transferido']} kV"}
    estados = (b.get('topologia') or {}).get('estados') or {}
    sec = estados.get(esperado['frontera_cerrada']) or {}
    out['frontera_corregida'] = {'pass': bool(sec.get('cerrado')),
                                 'detalle': f"{esperado['frontera_cerrada']}: {sec or 'no encontrado'}"}
    enlace = esperado['enlace']
    ha, hb = (((x.get('topologia') or {}).get('huellas_gps') or {}).get(enlace) for x in (a, b))
    out['enlace_conservado'] = {'pass': bool(ha) and ha == hb and bool((estados.get(enlace) or {}).get('en_servicio')),
                                'detalle': f'huella {hb}'}
    tensiones = ((b.get('flujo') or {}).get('tensiones') or {}).get('valores') or {}
    for nombre, pu in sorted(esperado['tensiones_pu'].items()):
        valor = tensiones.get(nombres.get(nombre))
        out[f'tension_{nombre}'] = {'pass': valor is not None and abs(valor - pu) <= tol,
                                    'detalle': f'{valor} p.u. (esperado {pu})'}
    if tensiones:
        ident, vmin = min(tensiones.items(), key=lambda kv_: kv_[1])
        nombre_min = (barras.get(ident) or {}).get('nombre')
    else:
        nombre_min, vmin = None, None
    m = esperado['minima']
    out['minima'] = {'pass': nombre_min == m['barra'] and vmin is not None and abs(vmin - m['pu']) <= tol,
                     'detalle': f'{vmin} p.u. en {nombre_min} (esperado {m["pu"]} en {m["barra"]})'}
    misma = ((a.get('topologia') or {}).get('componentes') == (b.get('topologia') or {}).get('componentes'))
    out['dos_lecturas_iguales'] = {'pass': misma and bool(a.get('reopen_verified')) and bool(b.get('reopen_verified')),
                                   'detalle': 'misma topología en dos procesos nuevos'}
    return out


def _leer_en_proceso_nuevo(plan: Path, salida: Path) -> tuple[int, dict]:
    rc = subprocess.call([sys.executable, str(LECTURA), '--plan', str(plan),
                          '--output-json', str(salida)], cwd=str(HERE.parents[1]))
    try:
        return rc, json.loads(salida.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return rc, {'error': f'la lectura terminó con el código {rc} sin dejar informe'}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Aceptación nativa del caso dorado del gemelo '
                                            'digital (spec 024, RF-24 a RF-27)')
    p.add_argument('--esperado', type=Path, required=True, help='JSON con los hechos del caso dorado')
    p.add_argument('--output-json', type=Path, required=True)
    p.add_argument('--vinculos', type=Path,
                   help='Registro de vínculos de la web (por defecto, el de output/web)')
    args = p.parse_args(argv)

    from igea_dgs.digital_twin.buffer import BuferEpisodios
    from igea_dgs.digital_twin.capture import construir_episodio
    from igea_dgs.digital_twin.episode import Caso
    from igea_dgs.digital_twin.integration import limites_combinados, normas_de
    from igea_dgs.native_action import build_native_action_context
    from igea_dgs.perfil_empresa import datos_perfil, estructura_empresa
    from igea_dgs.powerfactory_binding import vinculo_guardado
    from igea_dgs.web.workspace import REGISTRO_VINCULOS_FILE, data_root

    esperado = json.loads(args.esperado.read_text(encoding='utf-8'))
    registro = args.vinculos or data_root() / REGISTRO_VINCULOS_FILE
    vinculo = vinculo_guardado(type('Ws', (), {'vinculos_compartidos': registro,
                                               'pf_project_bindings': {}})(), esperado['project'])
    informe = {'project': esperado['project'], 'comprobaciones': {}, 'episodio': None}
    if not vinculo:
        informe['error'] = f"el proyecto {esperado['project']} no tiene vínculo en {registro}"
        args.output_json.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(informe['error'])
        return 2
    feeders = list(esperado['feeders'])
    contexto = build_native_action_context(vinculo, esperado['project'], feeders,
                                           'digital_twin_aceptacion')
    plan = {'project': esperado['project'], 'folder': esperado.get('folder'), 'feeders': feeders,
            'case': esperado.get('case', 'con_proyecto'), 'huellas_gps_de': [esperado['enlace']],
            'estados_de': [esperado['frontera_cerrada'], esperado['enlace']],
            'native_action_context': contexto}
    with tempfile.TemporaryDirectory() as tmp:
        ruta_plan = Path(tmp) / 'plan.json'
        ruta_plan.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
        rc_a, a = _leer_en_proceso_nuevo(ruta_plan, Path(tmp) / 'a.json')
        if rc_a == 3:
            print('ERROR: no hay API de DIgSILENT')
            return 3
        rc_b, b = _leer_en_proceso_nuevo(ruta_plan, Path(tmp) / 'b.json')
    informe['lecturas'] = {'a': {'codigo': rc_a, 'error': a.get('error'), 'avisos': a.get('avisos')},
                           'b': {'codigo': rc_b, 'error': b.get('error'), 'avisos': b.get('avisos')}}
    informe['comprobaciones'] = comprobar(a, b, esperado)
    perfil = datos_perfil()
    lectura = {**b, 'reopen_verified': bool(informe['comprobaciones']['dos_lecturas_iguales']['pass'])}
    episodio = construir_episodio(
        plan, {'status': 'OK' if rc_b == 0 else 'NO_CONVERGE', 'converged': rc_b == 0},
        lectura if b.get('flujo') else None, [], caso=Caso(plan['case']),
        limites=limites_combinados(perfil, normas_de(estructura_empresa(), feeders)),
        referencia=None, calibracion_cuadra=None,
        creado=datetime.now(UTC).isoformat(timespec='seconds'))
    BuferEpisodios().guardar(episodio)
    informe['episodio'] = {'episode_id': episodio.episode_id, 'clase': episodio.clase.value,
                           'violaciones': list(episodio.aceptacion.get('violaciones') or [])[:20]}
    informe['comprobaciones']['clase'] = {'pass': episodio.clase.value == esperado['clase'],
                                          'detalle': episodio.clase.value}
    args.output_json.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    fallos = [k for k, v in informe['comprobaciones'].items() if not v['pass']]
    for k, v in informe['comprobaciones'].items():
        print(f"{'OK ' if v['pass'] else 'MAL'} {k}: {v['detalle']}")
    return 2 if fallos else 0


if __name__ == '__main__':
    raise SystemExit(main())
