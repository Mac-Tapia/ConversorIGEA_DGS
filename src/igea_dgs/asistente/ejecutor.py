"""Ejecuta un plan confirmado por las mismas rutas y trabajos de la web (spec 026, RF-10, RF-12).

Como ``tools/sistema_web.py``: lo que hace el asistente es lo mismo que haría el operador
en la web, con la misma API, sus validaciones y sus carriles (P5, P7). Cada paso llama a una
ruta; si devuelve un trabajo, se espera a que termine; si falla, se para y se dice en qué
paso. Al final, los entregables (DGS, informes, formatos) con su enlace.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TERMINADOS = ('done', 'failed', 'cancelled')
_ENTREGABLE = re.compile(r'\.(dgs|docx|xlsx|zip|csv)$', re.IGNORECASE)


@dataclass
class Paso:
    nombre: str
    metodo: str
    ruta: Any                               # texto, o función de los resultados anteriores
    cuerpo: Any = None                      # dict, o función de los resultados anteriores
    archivos: Callable | None = None        # para subir un fichero (multipart)
    espera: bool = True


class PasoFallido(RuntimeError):
    """Un paso devolvió un error o su trabajo no terminó bien."""


@dataclass
class ClienteWeb:
    """La API de la web desde dentro: ``http`` es una sesión de ``requests`` o el cliente de pruebas."""

    http: Any
    base: str
    espacio: str
    intervalo_s: float = 0.5
    cancelado: Callable[[], bool] = field(default=lambda: False)

    def _url(self, ruta: str) -> str:
        if ruta.startswith('/api/'):
            return self.base + ruta
        return f'{self.base}/api/workspaces/{self.espacio}{ruta}'

    def pedir(self, metodo: str, ruta: str, **kw) -> Any:
        r = self.http.request(metodo, self._url(ruta), **kw)
        if r.status_code >= 300:
            try:
                detalle = r.json().get('detail')
            except ValueError:
                detalle = r.text[:500]
            raise PasoFallido(f'{metodo} {ruta}: {detalle}')
        return r.json() if r.content else None

    def esperar(self, trabajo: dict) -> dict:
        cancelado = False
        while True:
            estado = self.pedir('GET', f"/api/jobs/{trabajo['id']}")
            if estado['status'] in TERMINADOS:
                return estado
            if self.cancelado() and not cancelado:
                self.pedir('POST', f"/api/jobs/{trabajo['id']}/cancel")
                cancelado = True
            time.sleep(self.intervalo_s)


def _feeders(datos: Mapping) -> list[str]:
    return [a for a in datos.get('alimentadores') or [] if a != 'todos']


def pasos(tarea: str, datos: Mapping[str, Any], extras: Mapping[str, Any] | None = None) -> list[Paso]:
    """Los pasos de la tarea; ``extras`` trae lo que la web sabe y el plan no (la última máxima,
    el formulario del informe guardado en 4.4, si hay que cargar la fuente antes)."""
    extras = extras or {}
    lista = _pasos(tarea, datos, extras)
    if extras.get('cargar_antes'):
        lista = [Paso('cargar la fuente', 'POST', '/load', {})] + lista
    return lista


def _pasos(tarea: str, datos: Mapping[str, Any], extras: Mapping[str, Any]) -> list[Paso]:
    feeders = _feeders(datos)
    proyecto = datos.get('proyecto') or ''
    todos = 'todos' in (datos.get('alimentadores') or [])
    if tarea == 'leer_proyectos':
        return [Paso('leer los proyectos de DIgSILENT', 'POST', '/powerfactory/projects', {})]
    if tarea == 'evaluar_gemelo':
        return [Paso('evaluar el gemelo', 'POST', '/digital-twin/evaluar', {})]
    if tarea == 'cargar_fuente':
        return [Paso('cargar la fuente', 'POST', '/load', {})]
    if tarea == 'convertir':
        return [Paso('convertir', 'POST', '/convert', {'feeders': feeders, 'all': todos})]
    if tarea == 'unir':
        return [Paso('convertir en una red unida', 'POST', '/convert',
                     {'feeders': feeders, 'all': todos, 'unir': True, 'nombre': ''})]
    if tarea == 'convertir_sistema':
        return [Paso('convertir por sistema eléctrico', 'POST', '/convert/sistema',
                     {'zonales': [datos['sistema']]})]
    if tarea == 'flujo':
        return [Paso('flujo en DIgSILENT', 'POST', '/powerfactory/flow', {'feeders': feeders})]
    if tarea == 'verificar_caso_base':
        return [Paso('verificar el «Caso base»', 'POST', '/powerfactory/caso-base',
                     {'project': proyecto, 'feeders': feeders})]
    if tarea == 'cargas_nuevas':
        ruta = Path(datos['ruta'])

        def fichero(_r):
            return {'create_file': (ruta.name, ruta.read_bytes(),
                                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}

        return [Paso('preparar el plan de las cargas nuevas', 'POST', '/lote/plan',
                     {'project': proyecto, 'feeders': feeders}, archivos=fichero, espera=False),
                Paso('aplicar las cargas nuevas', 'POST', lambda r: f"/lote/{r[-1]['token']}/apply", None)]
    if tarea == 'obras':
        return [Paso('leer las obras pendientes', 'GET', '/obras', espera=False),
                Paso('aplicar las obras', 'POST', '/pf/obras/aplicar', lambda r: {
                    'project': proyecto, 'feeders': feeders,
                    'ids': [o['id'] for o in r[-1] or [] if not feeders or o.get('alimentador') in feeders]})]
    if tarea == 'estudios':
        return [Paso('leer el catálogo de estudios', 'GET', '/api/pf/estudios', espera=False),
                Paso('preparar los estudios', 'POST', '/pf/estudios/plan', lambda r: {
                    'project': proyecto, 'feeders': feeders,
                    'estudios': [e['clave'] for e in r[-1].get('ofrecidos') or []]}, espera=False),
                Paso('ejecutar los estudios', 'POST', lambda r: f"/pf/estudios/{r[-1]['token']}/ejecutar", None)]
    if tarea == 'transferencia':
        return [Paso('transferencia de carga', 'POST', '/pf/transferencia',
                     {'project': proyecto, 'feeders': feeders[:2]})]
    if tarea == 'pide':
        return [Paso('PIDE', 'POST', '/pide', {'project': proyecto, 'feeders': feeders})]
    if tarea == 'gemelo_aprender':
        return [Paso('aprendizaje activo del gemelo', 'POST', '/digital-twin/aprender',
                     {'project': proyecto, 'feeders': feeders, 'n': int(datos.get('numero') or 20)})]
    if tarea == 'gemelo_entrenar':
        return [Paso('reentrenar la PINN', 'POST', '/digital-twin/entrenar', {'forzar': True})]
    if tarea == 'gemelo_temporal':
        maxima = extras.get('ultima_maxima') or {}
        pares = {r['alimentador']: r['medidor'] for r in (maxima.get('result') or {}).get('resultados') or []
                 if r.get('alimentador') and not r.get('error') and (not feeders or r['alimentador'] in feeders)}
        return [Paso('gemelo temporal del mes', 'POST', '/digital-twin/temporal',
                     {'job_id': maxima.get('id'), 'alimentadores': pares})]
    if tarea in ('informe_estudio', 'informe_factibilidad'):
        tipo = 'estudio' if tarea == 'informe_estudio' else 'factibilidad'
        formulario = dict(extras.get('formulario') or {})
        cuerpo = {**formulario, 'project': proyecto, 'alimentador': feeders[0] if feeders else ''}
        if tipo == 'factibilidad':
            cuerpo['sed'] = datos.get('sed') or formulario.get('sed') or ''
        return [Paso(f'informe de {tipo}', 'POST', f'/informes/{tipo}', cuerpo)]
    raise ValueError(f'la tarea {tarea!r} no tiene pasos: es una consulta o un proceso')


def describir(tarea: str, datos: Mapping[str, Any], extras: Mapping[str, Any] | None = None) -> list[str]:
    """Los pasos en palabras, para el plan que confirma el operador (RF-8)."""
    try:
        return [p.nombre for p in pasos(tarea, datos, extras)]
    except (ValueError, KeyError, OSError):
        return []


def entregables(resultado: Any) -> list[str]:
    """Los nombres de fichero que deja un trabajo (DGS, informes, formatos), para enlazarlos."""
    out: list[str] = []

    def recorrer(x):
        if isinstance(x, dict):
            for v in x.values():
                recorrer(v)
        elif isinstance(x, list):
            for v in x:
                recorrer(v)
        elif isinstance(x, str) and _ENTREGABLE.search(x) and len(x) < 400 and x not in out:
            out.append(x)

    recorrer(resultado)
    return out


def ejecutar(lista: list[Paso], cliente: ClienteWeb, log: Callable[[str], None] = lambda _m: None) -> dict:
    """Los pasos en orden; el resultado de cada uno queda para el siguiente."""
    resultados: list[Any] = []
    trabajos: list[dict] = []
    for i, p in enumerate(lista, 1):
        if cliente.cancelado():
            return {'completo': False, 'cancelado': True, 'pasos': trabajos}
        ruta = p.ruta(resultados) if callable(p.ruta) else p.ruta
        cuerpo = p.cuerpo(resultados) if callable(p.cuerpo) else p.cuerpo
        log(f'Asistente: paso {i} de {len(lista)}, {p.nombre}…')
        if p.archivos is not None:
            r = cliente.pedir(p.metodo, ruta, data=cuerpo or {}, files=p.archivos(resultados))
        elif p.metodo == 'GET':
            r = cliente.pedir('GET', ruta)
        else:
            r = cliente.pedir(p.metodo, ruta, json=cuerpo if cuerpo is not None else {})
        if p.espera and isinstance(r, dict) and r.get('id') and r.get('status'):
            fin = cliente.esperar(r)
            trabajos.append({'paso': p.nombre, 'trabajo': fin['id'], 'estado': fin['status'],
                             'error': fin.get('error')})
            if fin['status'] != 'done':
                raise PasoFallido(f"el paso «{p.nombre}» terminó {fin['status']}: {fin.get('error') or ''}".strip())
            r = fin.get('result')
        resultados.append(r)
    final = resultados[-1] if resultados else None
    return {'completo': True, 'pasos': trabajos, 'resultado': final, 'entregables': entregables(final)}
