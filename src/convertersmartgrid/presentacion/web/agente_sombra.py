"""El agente MASAC en sombra desde la web: propone, se lee y el operador confirma o deshace (spec 114, T4).

La propuesta se calcula con la red que el gemelo capturó del proyecto (el mismo búfer de episodios que usan el
oráculo y la 074) y con el motor abierto; DIgSILENT no se abre. No aplica nada: el agente está en sombra hasta pasar
sus puertas (114:RF-7), y confirmar o deshacer solo deja la decisión del operador en el registro de experiencia, para
el siguiente entrenamiento (114:RF-11). Aplicar una obra sigue siendo lo de siempre, con su botón y su confirmación
(114:RF-9).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .requisitos import UserError

#: Pesos de la comparación en sombra, en unidades del banco: no son costos de ninguna empresa, solo ordenan la
#: propuesta del agente frente a la escalera con la misma vara (un banco vale 10; una maniobra, 1; un MW de pérdidas, 5).
PESOS_SOMBRA = {'costo_banco': 10.0, 'costo_maniobra': 1.0, 'costo_perdidas_mw': 5.0}
#: Episodios con que se entrena la primera política, en CPU, si aún no hay ninguna.
EPISODIOS_PRIMERA_POLITICA = 30
#: Propuestas que devuelve la lectura: la web muestra la última y el marcador de todas.
PROPUESTAS_LEIDAS = 10
VARIABLE_DATOS = 'CSG_AGENTE_DATA'
CASOS = ('sin_proyecto', 'con_proyecto')


def raiz_agente() -> Path:
    """``CSG_AGENTE_DATA`` o ``_agente_masac`` junto a los espacios de la web: siempre local, como el gemelo."""
    env = os.environ.get(VARIABLE_DATOS, '').strip()
    if env:
        return Path(env)
    from ...dominio.runtime_paths import raiz_datos_web

    return raiz_datos_web() / '_agente_masac'


def _registro():
    from ...adaptadores.masac_sombra import RegistroExperiencia

    return RegistroExperiencia(raiz_agente() / 'registro')


def exigir_vinculado(ws: Any, project: str) -> str:
    from ...adaptadores.powerfactory_binding import alimentadores_vinculados

    project = str(project or '').strip()
    if not project or not alimentadores_vinculados(ws, project):
        raise UserError(f'El proyecto «{project}» no está vinculado en este espacio.')
    return project


def red_del_proyecto(project: str, caso: str, feeders: list[str]) -> dict[str, Any]:
    """La red del gemelo del proyecto, recortada a los alimentadores pedidos con su camino a la fuente."""
    from ...adaptadores.digital_twin.buffer import BuferEpisodios, Consulta
    from ...adaptadores.digital_twin.evolutivo import red_del_gemelo
    from ...adaptadores.madrl_obras import subred, zonas_por_alimentador

    grafo = red_del_gemelo(BuferEpisodios().consultar(Consulta(proyecto=project, caso=caso)))
    if grafo is None:
        raise UserError(f'No hay red capturada de «{project}» en «{caso}»: calibre o estudie el proyecto antes, '
                        'y el gemelo la guarda.')
    if not feeders:
        return grafo
    ramas = {str(r.get('id')): r for r in grafo.get('ramas') or []}
    zonas = zonas_por_alimentador(grafo)

    def nombre(clave: str) -> str:
        return str((ramas.get(clave) or {}).get('alimentador') or clave)

    pedidos = {f.strip() for f in feeders if f.strip()}
    elegidas = [z for z in zonas if nombre(z) in pedidos or any(p in z for p in pedidos)]
    if not elegidas:
        vistos = ', '.join(sorted(nombre(z) for z in zonas)[:10])
        raise UserError(f'La red capturada no tiene {", ".join(sorted(pedidos))}; tiene: {vistos}.')
    return subred(grafo, {n for z in elegidas for n in zonas[z]})


def _parametros(grafo: dict[str, Any], banco_kvar: float | None):
    """Los límites del perfil (los mismos de los estudios) y el banco del perfil por tensión, o el que pide el operador."""
    from collections import Counter

    from ...adaptadores.madrl_obras import ParametrosObras
    from ...adaptadores.masac_entorno import ParametrosAgente
    from ...aplicacion.estudios_pf import EstudiosError, limites_de_perfil
    from ...dominio.perfil_empresa import PerfilError, bancos_kvar_por_tension, datos_perfil

    try:
        limites = limites_de_perfil()
        por_tension = bancos_kvar_por_tension(datos_perfil())
    except (EstudiosError, PerfilError) as exc:
        raise UserError(str(exc)) from exc
    if banco_kvar is None and por_tension:
        # La tensión de media más frecuente de la red: la de sus alimentadores.
        kv = Counter(round(float(d.get('kv') or 0), 1) for d in (grafo.get('nodos') or {}).values()
                     if 1 <= float(d.get('kv') or 0) < 35).most_common(1)
        if kv:
            banco_kvar = next((v for t, v in por_tension.items() if abs(t - kv[0][0]) <= 0.2), None)
    if banco_kvar is None:
        raise UserError('Indique el tamaño del banco en kvar: el perfil de empresa no lo da para la tensión de esta red.')
    obras = ParametrosObras(limites.tension_min_pu, limites.tension_max_pu, limites.cargabilidad_max_pct,
                            banco_kvar / 1000.0, PESOS_SOMBRA['costo_banco'], candidatos=3, max_bancos=3, max_pasos=4)
    return ParametrosAgente(obras, PESOS_SOMBRA['costo_maniobra'], PESOS_SOMBRA['costo_perdidas_mw'])


def _politica(entorno, ctx) -> tuple[Any, bool]:
    """La política guardada si vale para estos huecos de acción; si no hay ninguna, se entrena la primera en CPU."""
    from ...adaptadores.masac_politica import ConfigMASAC, cargar_masac, entrenar_masac, guardar_masac

    carpeta = raiz_agente() / 'modelo'
    if (carpeta / 'modelo.json').is_file():
        politica = cargar_masac(carpeta)
        if politica.dims == entorno.dimensiones():
            return politica, False
        ctx.log('La política guardada es de otros huecos de acción: se entrena otra para estos.')
    ctx.log(f'Aún no hay política del agente: se entrena una en CPU con {EPISODIOS_PRIMERA_POLITICA} episodios.')

    def avance(hechos: int, total: int) -> None:
        ctx.check_cancel()
        ctx.progress(hechos, total + 1, 'Entrenando la política del agente')

    politica, _curva = entrenar_masac(entorno, ConfigMASAC(episodios=EPISODIOS_PRIMERA_POLITICA), al_episodio=avance)
    guardar_masac(carpeta, politica, origen='primera política, entrenada desde la web')
    return politica, True


def proponer(ws: Any, ctx: Any, project: str, feeders: list[str], caso: str, banco_kvar: float | None) -> dict[str, Any]:
    """El trabajo: la red del gemelo, la política y la propuesta en sombra junto a la escalera, registrada."""
    from ...adaptadores.masac_entorno import EntornoAgente
    from ...adaptadores.masac_sombra import proponer_en_sombra

    project = exigir_vinculado(ws, project)
    if caso not in CASOS:
        raise UserError(f'El caso es «sin_proyecto» o «con_proyecto», no «{caso}».')
    grafo = red_del_proyecto(project, caso, feeders)
    p = _parametros(grafo, banco_kvar)
    politica, entrenada = _politica(EntornoAgente(grafo, p), ctx)
    ctx.progress(1, 1, 'Proponiendo en sombra')
    contexto = {'espacio': ws.id, 'proyecto': project, 'caso': caso, 'feeders': list(feeders)}
    r = proponer_en_sombra(grafo, p, politica, registro=_registro(), contexto=contexto)
    quien = {'agente': 'acierta el agente', 'regla': 'acierta la regla actual', 'empate': 'empatan'}[r['acierta']]
    ctx.log(f'Propuesta en sombra de {project}: {quien}. No se aplicó nada.')
    return {'project': project, 'entrenada': entrenada, 'propuesta': r['propuesta'], 'acierta': r['acierta'],
            'aplicada': False}


def _vista(f: dict[str, Any]) -> dict[str, Any]:
    """Lo que necesita la web de una propuesta: sin las observaciones del agente, que son para entrenar."""
    resumen = ('en_norma', 'costo', 'costo_maniobras', 'vm_min', 'perdidas_mw', 'obras')
    return {'propuesta': f['propuesta'], 'fecha': f.get('fecha'), 'caso': f.get('caso'), 'feeders': f.get('feeders') or [],
            'acierta': f['acierta'], 'agente': {k: f['agente'].get(k) for k in resumen},
            'regla': {k: f['regla'].get(k) for k in resumen},
            'decisiones': [{'id': d['id'], 'agente': d['agente'], 'tipo': d['accion']['tipo'],
                            'elemento': d['accion']['elemento'], 'explicacion': d['explicacion'],
                            'estado': d['estado'], 'confirmo': d['confirmo']} for d in f['decisiones']]}


def estado(ws: Any, project: str) -> dict[str, Any]:
    """Las propuestas del proyecto y el marcador frente a la regla actual (114:RF-7)."""
    project = exigir_vinculado(ws, project)
    reg = _registro()
    modelo = raiz_agente() / 'modelo' / 'modelo.json'
    return {'project': project, 'modo': 'sombra', 'aciertos': reg.aciertos(proyecto=project),
            'propuestas': [_vista(f) for f in reg.propuestas(proyecto=project)[:PROPUESTAS_LEIDAS]],
            'hay_politica': modelo.is_file()}


def decidir(ws: Any, ident: str, accion: str) -> dict[str, Any]:
    """El operador confirma o deshace una decisión: queda en el registro y no se aplica nada (114:RF-9, RF-11)."""
    from ...adaptadores.masac_sombra import SombraError

    reg = _registro()
    try:
        d = reg.decision(ident)
    except SombraError as exc:
        raise UserError(str(exc)) from exc
    exigir_vinculado(ws, d.get('proyecto') or '')
    if d['estado'] != 'propuesta':
        raise UserError(f'Esa propuesta ya está {d["estado"]}.')
    if accion == 'confirmar':
        reg.confirmar(ident, 'operador')
    else:
        reg.deshacer(ident, 'operador')
    d = reg.decision(ident)
    return {'id': ident, 'estado': d['estado'], 'confirmo': d['confirmo'], 'aplicada': False}
