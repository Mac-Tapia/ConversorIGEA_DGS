"""045:RF-3 a RF-5 — qué física representa el grafo del gemelo y qué no.

El grafo de DIgSILENT pasaba al gemelo sin decir de qué estaba hecho: un transformador de tres
devanados o un regulador no eran rama, una toma automática quedaba en la posición escrita y una
central no entraba, y la PINN predecía igual sobre esa red. Aquí se declara lo representado y lo
que no lo está se rechaza con su motivo, nunca aproximado en silencio.

Este contrato no es la física de referencia de la conversión, que es ``convertersmartgrid.oraculo``
(pandapower, spec 082): aquella valida el modelo antes de DIgSILENT, y esta dice qué sabe calcular
la PINN sobre lo que se lee de DIgSILENT.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..evaluacion_modelos import huella
from .native_snapshot import componentes

#: Versión del grafo. La 2 traía los acopladores y la consigna de las fuentes. La 3 separa carga,
#: generación y bancos, trae tomas, fases y alcance, y cuenta las unidades en paralelo: un
#: episodio versión 2 pudo capturarse antes o después de la 074 (``ntnum``, SM218 al 131 % frente
#: al 65 % de DIgSILENT) y no hay forma de distinguirlo, así que no enseña.
VERSION_GRAFO = 3

#: Lo único que sabe calcular la física del gemelo: una fase equivalente por barra, sin desfase de grupo.
REPRESENTACION = 'equilibrada_secuencia_positiva'

#: Lo que la física deja fuera por diseño, en redes de MT: se declara, no bloquea.
APROXIMACIONES = ('sin susceptancia de línea', 'sin magnetización ni pérdidas en vacío de transformadores',
                  'sin desfase de grupo de conexión')

#: Equipos de cálculo que no son ni nodo ni rama del grafo: su efecto no está en la física.
CLASES_NO_REPRESENTADAS = ('ElmTr3', 'ElmTr4', 'ElmVoltreg', 'ElmZpu', 'ElmSind', 'ElmScap', 'ElmPvsys',
                           'ElmAsm', 'ElmSvs', 'ElmVsc', 'ElmVscmono', 'ElmRec', 'ElmInv')

#: Ajustes del ``ComLdf`` sin los que no se sabe qué calculó DIgSILENT.
CONTROLES_LDF = ('iopt_net', 'iopt_lev', 'iopt_pq', 'iopt_at', 'iopt_asht')

#: ``av_mode`` de una central que inyecta lo escrito; con otro, la Q la decide un control.
MODOS_PQ = ('constq',)

#: Holgura entre lo escrito y lo consumido (como ``CONSUMO_REL`` de ``tools/ajuste_cabecera_pf.py``).
CONSUMO_REL = 1e-3
#: Por debajo de esto (MW) lo escrito y lo consumido son lo mismo; una carga nula no da cociente.
CONSUMO_ABS_MW = 1e-5

UNIDADES = {'kv': 'kV', 'p_mw': 'MW', 'q_mvar': 'Mvar', 'r_ohm': 'ohm', 'x_ohm': 'ohm', 'inom_ka': 'kA',
            'v_pu': 'p.u.', 'angulo_deg': 'grados', 'paso_pct': '%'}


def _muestra_de(ids: Iterable[str], cuantos: int = 3) -> str:
    return ', '.join(str(i) for i in list(ids)[:cuantos])


def _motivos_de_comldf(grafo: Mapping[str, Any]) -> list[str]:
    comldf = (grafo.get('controles') or {}).get('comldf')
    if not isinstance(comldf, Mapping):
        return ['el grafo no trae los ajustes del flujo (ComLdf)']
    faltan = [k for k in CONTROLES_LDF if comldf.get(k) is None]
    if faltan:
        return [f'faltan ajustes del flujo: {", ".join(faltan)}']
    motivos = []
    # 054:RF-7: con tramos de menos de 3 fases la etiqueta sale del flujo desequilibrado, y esa no
    # es la física de esta red (spec 045, fuera de alcance).
    if comldf['iopt_net']:
        motivos.append('flujo desequilibrado (iopt_net): la física del gemelo es equilibrada')
    if comldf['iopt_at']:
        automaticas = [r.get('id') for r in grafo.get('ramas') or [] if (r.get('toma') or {}).get('automatica')]
        if automaticas:
            motivos.append(f'{len(automaticas)} toma(s) automática(s) con iopt_at: la posición efectiva '
                           f'no está representada (p. ej. {_muestra_de(automaticas)})')
    if comldf['iopt_asht']:
        bancos = [b.get('id') for b in grafo.get('bancos') or [] if b.get('en_servicio')]
        if bancos:
            motivos.append(f'{len(bancos)} banco(s) con ajuste automático (iopt_asht): el escalón efectivo '
                           f'no está representado (p. ej. {_muestra_de(bancos)})')
    if comldf['iopt_lev']:
        distintos = _consumo_distinto(grafo.get('nodos') or {})
        if distintos:
            # CA101 (2026-10-15) consumía el 73 % de lo escrito: iopt_lev vuelve las cargas impedancia.
            motivos.append(f'adaptación automática del modelo (iopt_lev): {len(distintos)} barra(s) consumen '
                           f'otra cosa que lo escrito o no se midió (p. ej. {_muestra_de(distintos)})')
    return motivos


def _consumo_distinto(nodos: Mapping[str, Mapping[str, Any]]) -> list[str]:
    distintos = []
    for n, d in sorted(nodos.items()):
        for escrita, medida in (('carga_p_mw', 'carga_p_efectiva_mw'), ('carga_q_mvar', 'carga_q_efectiva_mvar')):
            e = d.get(escrita)
            if not e:
                continue
            m = d.get(medida)
            if m is None or abs(m - e) > max(CONSUMO_REL * abs(e), CONSUMO_ABS_MW):
                distintos.append(n)
                break
    return distintos


def _motivos_de_fuentes(grafo: Mapping[str, Any]) -> list[str]:
    nodos = grafo.get('nodos') or {}
    con_fuente = [n for n, d in sorted(nodos.items()) if d.get('fuente')]
    if not con_fuente:
        return ['el grafo no tiene ninguna fuente']
    motivos = []
    sin_consigna = [n for n in con_fuente if nodos[n].get('v_pu') is None]
    if sin_consigna:
        motivos.append(f'{len(sin_consigna)} fuente(s) sin consigna de tensión (p. ej. {_muestra_de(sin_consigna)})')
    for f in grafo.get('fuentes') or []:
        if f.get('modo') not in (None, 'SL', 'referencia'):
            motivos.append(f"la fuente {f.get('id')} no es de referencia (modo {f.get('modo')})")
    if len(con_fuente) > 1:
        tramos = [(r.get('desde'), r.get('hasta'), r.get('cerrada', True)) for r in grafo.get('ramas') or []
                  if r.get('desde') in nodos and r.get('hasta') in nodos]
        for isla in componentes(nodos, tramos):
            angulos = {nodos[n].get('angulo_deg') for n in isla if nodos[n].get('fuente')}
            # Sin el desfase de los grupos de conexión, dos ángulos en una isla no se pueden comparar.
            if len(angulos) > 1:
                motivos.append(f'fuentes con ángulos distintos en una misma isla (p. ej. {_muestra_de(isla)})')
    return motivos


def validar_alcance_fisico(grafo: Mapping[str, Any]) -> tuple[str, ...]:
    """Por qué la física del gemelo no vale para este grafo (045:RF-4); vacío si vale.

    Un grafo hecho por el propio gemelo desde una muestra trae los motivos de su original.
    """
    if 'bloqueos_heredados' in grafo:
        return tuple(grafo['bloqueos_heredados'])
    version = grafo.get('version')
    if version != VERSION_GRAFO:
        return (f'grafo de la versión {version}, el contrato vigente es la {VERSION_GRAFO}: '
                'hay que capturarlo de nuevo',)
    motivos = []
    alcance = grafo.get('alcance_fisico')
    if not isinstance(alcance, Mapping):
        motivos.append('el grafo no declara su alcance físico')
    else:
        if alcance.get('representacion') != REPRESENTACION:
            motivos.append(f"representación {alcance.get('representacion')} no soportada")
        for clase, ids in sorted((alcance.get('no_representados') or {}).items()):
            if ids:
                motivos.append(f'{len(ids)} {clase} sin representación física (p. ej. {_muestra_de(ids)})')
    motivos += _motivos_de_comldf(grafo)
    motivos += _motivos_de_fuentes(grafo)
    for grupo, nombre in (('ramas', 'rama'), ('bancos', 'banco'), ('generadores', 'central')):
        for e in grafo.get(grupo) or []:
            if e.get('faltan'):
                motivos.append(f"{nombre} {e.get('id')}: falta {', '.join(e['faltan'])}")
    for g in grafo.get('generadores') or []:
        if g.get('en_servicio') and g.get('control') not in MODOS_PQ and not g.get('referencia'):
            motivos.append(f"central {g.get('id')} con control {g.get('control')}: su Q no es lo escrito")
    return tuple(motivos)


def _suma(valores: Iterable[Any]) -> float | None:
    """Suma de lo medido; ``None`` si falta alguno: un total parcial parecería una diferencia real."""
    total = 0.0
    for v in valores:
        if v is None:
            return None
        total += float(v)
    return total


def contexto_fisico(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Los controles y el caso de una lectura nativa, con las huellas de ``ContextoExperimento``.

    045:RF-3: ajustes del flujo, consignas escritas y resultados efectivos se guardan los tres, sin
    que uno sustituya a otro. Lo que la lectura no trae queda en ``None``, no con un valor supuesto.
    """
    grafo = (snapshot.get('topologia') or {}).get('grafo')
    caso = snapshot.get('caso_nativo') or {}
    if not isinstance(grafo, Mapping) or not grafo.get('nodos'):
        return {'ausente': 'la lectura no trae el grafo eléctrico'}
    if not caso.get('id') or not caso.get('rol'):
        return {'ausente': 'la lectura no identifica el caso de DIgSILENT'}
    plan = snapshot.get('contexto') or {}
    nodos = grafo['nodos']
    ramas = grafo.get('ramas') or []
    bancos, generadores = grafo.get('bancos') or [], grafo.get('generadores') or []
    comldf = (grafo.get('controles') or {}).get('comldf')
    topologia = {'nodos': {n: d.get('kv') for n, d in sorted(nodos.items())},
                 'ramas': sorted(([r.get('id'), r.get('desde'), r.get('hasta'), bool(r.get('cerrada', True)),
                                   r.get('r_ohm'), r.get('x_ohm'), r.get('fases')] for r in ramas),
                                 key=lambda f: str(f[0]))}
    controles = {'comldf': comldf, 'criterio_fijas': plan.get('criterio_fijas'),
                 'tomas': {str(r.get('id')): r['toma'] for r in ramas if r.get('toma')},
                 'bancos': [[b.get('id'), b.get('q_mvar'), b.get('en_servicio'), b.get('escalones')] for b in bancos],
                 'centrales': [[g.get('id'), g.get('p_mw'), g.get('q_mvar'), g.get('en_servicio'), g.get('control'),
                                g.get('usetp')] for g in generadores],
                 'fuentes': {n: [d.get('v_pu'), d.get('angulo_deg')] for n, d in sorted(nodos.items()) if d.get('fuente')}}
    escenario = {'rol': caso['rol'], 'caso': caso['id'], 'year': plan.get('year'), 'period': plan.get('period'),
                 'escenario': (snapshot.get('topologia') or {}).get('escenario'),
                 'variaciones': (snapshot.get('topologia') or {}).get('variaciones_activas'),
                 'demanda': {n: [d.get('p_mw'), d.get('q_mvar')] for n, d in sorted(nodos.items())}}
    con_carga = [d for d in nodos.values() if d.get('carga_p_mw') or d.get('carga_q_mvar')]
    return {
        'case_role': caso['rol'], 'case_id': caso['id'], 'year': plan.get('year'), 'period': plan.get('period'),
        'criterio_fijas': plan.get('criterio_fijas'), 'comldf': comldf,
        'topology_hash': huella(topologia), 'controls_hash': huella(controles), 'scenario_hash': huella(escenario),
        'consignas': {'carga_p_mw': _suma(d.get('carga_p_mw') or 0.0 for d in nodos.values()),
                      'carga_q_mvar': _suma(d.get('carga_q_mvar') or 0.0 for d in nodos.values()),
                      'banco_q_mvar': _suma(b.get('q_mvar') or 0.0 for b in bancos if b.get('en_servicio')),
                      'central_p_mw': _suma(g.get('p_mw') or 0.0 for g in generadores if g.get('en_servicio'))},
        'efectivos': {'carga_p_mw': _suma(d.get('carga_p_efectiva_mw') for d in con_carga),
                      'carga_q_mvar': _suma(d.get('carga_q_efectiva_mvar') for d in con_carga),
                      'banco_q_mvar': _suma(b.get('q_medida_mvar') for b in bancos if b.get('en_servicio')),
                      'central_p_mw': _suma(g.get('p_medida_mw') for g in generadores if g.get('en_servicio'))},
        'bloqueos_fisicos': list(validar_alcance_fisico(grafo)),
    }
