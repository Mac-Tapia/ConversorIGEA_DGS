"""Ejecuta un plan confirmado por las mismas rutas y trabajos de la web (spec 026, RF-10, RF-12).

Como ``tools/sistema_web.py``: lo que hace el asistente es lo mismo que haría el operador
en la web, con la misma API, sus validaciones y sus carriles (P5, P7). Cada paso llama a una
ruta; si devuelve un trabajo, se espera a que termine; si falla, se para y se dice en qué
paso. Al final, los entregables (DGS, informes, formatos) con su enlace.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..sesion_web import cabeceras_locales

TERMINADOS = ('done', 'parcial', 'no_converge', 'failed', 'cancelled')
_ENTREGABLE = re.compile(r'\.(dgs|docx|xlsx|zip|csv)$', re.IGNORECASE)


@dataclass
class Paso:
    nombre: str
    metodo: str
    ruta: Any                               # texto, o función de los resultados anteriores
    cuerpo: Any = None                      # dict, o función de los resultados anteriores
    archivos: Callable | None = None        # para subir un fichero (multipart)
    espera: bool = True
    formulario: bool = False                # ruta de formulario sin fichero (la carga sola, 070:RF-29)


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
    gobierno: Any = None

    def _url(self, ruta: str) -> str:
        if ruta.startswith('/api/'):
            return self.base + ruta
        return f'{self.base}/api/workspaces/{self.espacio}{ruta}'

    def pedir(self, metodo: str, ruta: str, **kw) -> Any:
        if self.gobierno is not None:
            self.gobierno.validar_cliente(self)
            self.gobierno.autorizar_peticion(metodo, ruta, kw)
            # Una redirección HTTP no puede sacar la orden local de la máquina (P9).
            import requests
            if isinstance(self.http, requests.Session):
                self.http.trust_env = False
                kw['allow_redirects'] = False
        # 086:RF-19: la API también se lo exige a sí misma; solo sale si la dirección es de esta máquina.
        if credenciales := cabeceras_locales(self.base):
            kw['headers'] = {**credenciales, **(kw.get('headers') or {})}
        r = self.http.request(metodo, self._url(ruta), **kw)
        if r.status_code >= 300:
            try:
                detalle = r.json().get('detail')
            except ValueError:
                detalle = r.text[:500]
            raise PasoFallido(f'{metodo} {ruta}: {detalle}')
        respuesta = r.json() if r.content else None
        if self.gobierno is not None:
            self.gobierno.registrar_respuesta_http(respuesta)
        return respuesta

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


def _ultima_calibracion(proyecto: str) -> Paso:
    """La base se lee al ejecutar: en el proyecto entero la calibración no existe aún al proponerlo."""
    return Paso('buscar la última calibración', 'GET', f'/demanda/ajuste/ultimo?project={quote(proyecto)}', espera=False)


def _id_calibracion(respuesta: Any, proyecto: str) -> str:
    ajuste = (respuesta or {}).get('ajuste') if isinstance(respuesta, Mapping) else None
    if not ajuste or not ajuste.get('id'):
        raise PasoFallido(f'{proyecto} no tiene ninguna calibración aplicada: calíbrelo antes.')
    return str(ajuste['id'])


def _cuerpo_de_obras(proyecto: str, feeders: list[str], datos: Mapping[str, Any], extras: Mapping[str, Any]) -> dict:
    """070:RF-13: sin el libro y el tipo de cambio de la orden, la ruta costeaba sin ellos o se rechazaba."""
    cuerpo: dict[str, Any] = {'project': proyecto, 'feeders': feeders}
    if datos.get('ruta'):
        cuerpo['capex'] = str(datos['ruta'])
    if extras.get('tipo_cambio'):
        cuerpo['tipo_cambio'] = extras['tipo_cambio']
    if extras.get('directo_set_nueva'):
        cuerpo['directo_set_nueva'] = True
    if datos.get('set'):
        cuerpo['set_nueva_nombre'] = str(datos['set'])
    if extras.get('cargas'):
        cuerpo['cargas'] = list(extras['cargas'])
    return cuerpo


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

        # 070:RF-9: la base es la de la última calibración, como cuando el operador la elige en 3.
        return [_ultima_calibracion(proyecto),
                Paso('preparar el plan de las cargas nuevas', 'POST', '/lote/plan',
                     lambda r: {'project': proyecto, 'feeders': feeders, 'ajuste_job_id': _id_calibracion(r[-1], proyecto)},
                     archivos=fichero, espera=False),
                Paso('aplicar las cargas nuevas', 'POST', lambda r: f"/lote/{r[-1]['token']}/apply", None)]
    if tarea == 'obras':
        return [Paso('leer las obras pendientes', 'GET', '/obras', espera=False),
                Paso('aplicar las obras', 'POST', '/pf/obras/aplicar', lambda r: {
                    'project': proyecto, 'feeders': feeders,
                    'ids': [o['id'] for o in r[-1] or [] if not feeders or o.get('alimentador') in feeders]})]
    if tarea == 'estudios':
        # 070:RF-1, RF-3: sin la base, el plan de estudios se rechazaba; y el catálogo sin espacio
        # ofrecía estudios que el libro o la licencia del proyecto no permiten.
        elegido = datos.get('estudio')
        return [_ultima_calibracion(proyecto),
                Paso('leer el catálogo de estudios', 'GET', f'/pf/estudios?project={quote(proyecto)}', espera=False),
                Paso('preparar los estudios', 'POST', '/pf/estudios/plan', lambda r: {
                    'project': proyecto, 'feeders': feeders, 'ajuste_job_id': _id_calibracion(r[-2], proyecto),
                    'estudios': [elegido] if elegido else [e['clave'] for e in r[-1].get('ofrecidos') or []]},
                     espera=False),
                Paso('ejecutar los estudios', 'POST', lambda r: f"/pf/estudios/{r[-1]['token']}/ejecutar", None)]
    if tarea == 'obras_escalera':
        return [Paso('escalera de obras', 'POST', '/pf/obras/escalera', _cuerpo_de_obras(proyecto, feeders, datos, extras))]
    if tarea == 'optimizar_con_proyecto':
        return [Paso('optimizar «Con proyecto»', 'POST', '/pf/obras/con-proyecto',
                     _cuerpo_de_obras(proyecto, feeders, datos, extras))]
    if tarea == 'transferencia':
        return [Paso('transferencia de carga', 'POST', '/pf/transferencia',
                     {'project': proyecto, 'feeders': feeders[:2]})]
    if tarea == 'pide':
        # 072:RF-18: por la misma ruta que la web, con su año de presentación si la orden lo dice.
        anio = str(datos.get('periodo') or '')[:4]
        # Los libros que la orden nombra, con los mismos campos que manda el formulario de la web.
        libros = {k: extras[k] for k in ('capex', 'formato_01') if extras.get(k)}
        return [Paso('PIDE', 'POST', '/pide', {'project': proyecto, 'feeders': feeders,
                                               **({'anio_presentacion': int(anio)} if anio.isdigit() else {}),
                                               **libros})]
    if tarea == 'gemelo_aprender':
        return [Paso('aprendizaje activo del gemelo', 'POST', '/digital-twin/aprender',
                     {'project': proyecto, 'feeders': feeders, 'n': int(datos.get('numero') or 20)})]
    if tarea == 'gemelo_entrenar':
        return [Paso('reentrenar la PINN', 'POST', '/digital-twin/entrenar', {'forzar': True})]
    if tarea == 'gemelo_temporal':
        # 046:RF-23: el pronóstico solo con su formulario; por defecto sigue la reconstrucción del mes.
        if extras.get('pronostico'):
            return [Paso('pronóstico de demanda', 'POST', '/digital-twin/temporal',
                         {**extras['pronostico'], 'modo': 'pronostico'})]
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
        # 070:RF-12: la ruta hace un informe por alimentador; se pedía el del primero y se perdían los demás.
        return [Paso(f'informe de {tipo} de {a}' if len(feeders) > 1 else f'informe de {tipo}', 'POST',
                     f'/informes/{tipo}', {**cuerpo, 'alimentador': a}) for a in (feeders or [''])]
    nuevos = _pasos_070(tarea, datos, extras, proyecto, feeders)
    if nuevos is not None:
        return nuevos
    raise ValueError(f'la tarea {tarea!r} no tiene pasos: es una consulta o un proceso')


def _pasos_de_calibrar(proyecto: str, extras: Mapping[str, Any], ultimo: str, nombre: str) -> list[Paso]:
    """Como ``sistema_web``: relee los proyectos (el vínculo lo exige, spec 018), prepara el plan y lo ejecuta."""
    maxima = extras.get('ultima_maxima') or {}
    # Los de una central (022:RF-88) solo traen su curva al instante: el plan rechaza que sean cabeceras.
    medidores = [r['medidor'] for r in (maxima.get('result') or {}).get('resultados') or []
                 if not r.get('error') and r.get('medidor') and not str(r.get('alimentador') or '').lower().startswith('central ')]
    return [Paso('releer los proyectos de DIgSILENT', 'POST', '/powerfactory/projects', {}),
            Paso('preparar el plan de la calibración', 'POST', '/demanda/ajuste/plan',
                 {'project': proyecto, 'job_id': maxima.get('id'), 'medidores': medidores,
                  'completar_bancos': bool(extras.get('completar_bancos'))}, espera=False),
            Paso(nombre, 'POST', lambda r: f"/demanda/ajuste/{r[-1]['token']}/{ultimo}", None)]


def _pasos_070(tarea: str, datos: Mapping[str, Any], extras: Mapping[str, Any], proyecto: str,
               feeders: list[str]) -> list[Paso] | None:
    """Las tareas de la spec 070, cada una por la ruta que usa el operador (026:RF-10)."""
    if tarea == 'convertir_set':
        return [Paso('convertir la SET', 'POST', '/convert/sistema', {'zonales': [], 'sets': [datos['set']]})]
    if tarea == 'buscar_maxima':
        return [Paso('buscar la máxima', 'POST', '/demanda/cabecera/buscar', dict(extras.get('maxima') or {}))]
    if tarea == 'cruzar_clientes':
        return [Paso('cruzar los clientes', 'POST', '/demanda/clientes/cruzar',
                     {'alimentadores': feeders, 'periodo': datos.get('periodo'),
                      'maximas': dict(extras.get('maximas_clientes') or {})}, espera=False)]
    if tarea == 'calibrar':
        return _pasos_de_calibrar(proyecto, extras, 'aplicar', 'aplicar la calibración')
    if tarea == 'simular_calibracion':
        return _pasos_de_calibrar(proyecto, extras, 'simular', 'simular la calibración')
    if tarea == 'escanear':
        return [Paso('escanear', 'POST', '/powerfactory/escanear', {'project': proyecto, 'feeders': feeders})]
    if tarea == 'verificar_convergencia':
        return [Paso('verificar la convergencia', 'POST', '/powerfactory/verificar', {'project': proyecto, 'feeders': feeders})]
    if tarea == 'carga_nueva_sola':
        nueva = json.dumps(extras.get('nueva') or {}, ensure_ascii=False)
        return [_ultima_calibracion(proyecto),
                Paso('preparar la carga nueva', 'POST', '/lote/plan',
                     lambda r: {'project': proyecto, 'feeders': feeders, 'nueva': nueva,
                                'ajuste_job_id': _id_calibracion(r[-1], proyecto)}, espera=False, formulario=True),
                Paso('conectar la carga nueva', 'POST', lambda r: f"/lote/{r[-1]['token']}/apply", None)]
    if tarea == 'cancelar_trabajo':
        return [Paso(f"cancelar «{t.get('titulo')}»", 'POST', f"/api/jobs/{t['id']}/cancel", {}, espera=False)
                for t in extras.get('cancelar') or []]
    if tarea == 'leer_solicitud':
        rutas = [Path(r) for r in extras.get('documentos') or []]

        def ficheros(_r):
            return [('files', (p.name, p.read_bytes(), 'application/pdf')) for p in rutas]

        return [Paso('leer los documentos del solicitante', 'POST', '/informes/documentos',
                     {'tipo': extras.get('tipo_documentos') or 'factibilidad'}, archivos=ficheros)]
    if tarea == 'descargar_resultados':
        return [Paso('preparar el ZIP de los resultados', 'POST', '/outputs/archive', {'feeders': feeders})]
    if tarea == 'pronostico':
        return [Paso('pronóstico de demanda', 'POST', '/digital-twin/temporal',
                     {**(extras.get('pronostico') or {}), 'modo': 'pronostico'})]
    return None


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


def _valores(datos: Mapping[str, Any]) -> dict[str, list[str]]:
    """Los datos de una orden como texto normalizado, para compararlos."""
    out = {}
    for tipo, vs in (datos or {}).items():
        lista = vs if isinstance(vs, list) else [vs]
        out[tipo] = sorted(str(v.get('valor') if isinstance(v, dict) else v).strip().lower() for v in lista)
    return out


def revisar_tras_error(texto: str, tarea: str, datos: Mapping[str, Any], error: str, modelo: Any = None
                       ) -> dict[str, Any]:
    """Qué hacer con una orden cuyo paso falló (027:RF-20): el modelo recibe el error y su
    contexto. Si mantiene la tarea y los datos (un fallo pasajero, como el 4002 de DIgSILENT
    ocupado), se reintenta una vez; si propone otros, vuelve al operador con la propuesta, que
    se confirma como cualquier escritura (RF-19). Sin modelo, se reintenta igual una vez."""
    if modelo is None:
        return {'accion': 'reintentar', 'motivo': 'sin modelo que revise el error'}
    r = modelo.interpretar(f'{texto}\nLa ejecución falló con este error: {error}\n'
                           'Revisa la tarea y los datos de la orden.')
    if r is None or not r.get('tarea'):
        return {'accion': 'reintentar', 'motivo': 'el modelo no respondió'}
    if r['tarea'] != tarea:
        return {'accion': 'operador', 'tarea': r['tarea'], 'datos': r.get('datos') or {},
                'motivo': f"el modelo propone otra tarea ({r['tarea']})"}
    nuevos = {k: v for k, v in _valores(r.get('datos') or {}).items() if v}
    if not nuevos or all(_valores(datos).get(k) == v for k, v in nuevos.items()):
        return {'accion': 'reintentar', 'motivo': 'el modelo mantiene la tarea y los datos'}
    return {'accion': 'operador', 'tarea': tarea, 'datos': r.get('datos') or {},
            'motivo': 'el modelo propone otros datos: confírmelos'}


def ejecutar(lista: list[Paso], cliente: ClienteWeb, log: Callable[[str], None] = lambda _m: None) -> dict:
    """Los pasos en orden; el resultado de cada uno queda para el siguiente."""
    if cliente.gobierno is not None:
        with cliente.gobierno.accion(cancelado=cliente.cancelado) as evidencia:
            cliente.gobierno.validar_cliente(cliente)
            cliente.gobierno.validar_pasos(lista)
            resultado = _ejecutar(lista, cliente, log)
            evidencia['salida'] = resultado
            return resultado
    return _ejecutar(lista, cliente, log)


def _ejecutar(lista: list[Paso], cliente: ClienteWeb, log: Callable[[str], None]) -> dict:
    """Bucle compartido; el gobierno, cuando está vinculado, valida cada paso real."""
    resultados: list[Any] = []
    trabajos: list[dict] = []
    for i, p in enumerate(lista, 1):
        if cliente.cancelado():
            return {'completo': False, 'cancelado': True, 'pasos': trabajos}
        if cliente.gobierno is not None:
            cliente.gobierno.validar_paso(i - 1, p, resultados)
        ruta = p.ruta(resultados) if callable(p.ruta) else p.ruta
        cuerpo = p.cuerpo(resultados) if callable(p.cuerpo) else p.cuerpo
        log(f'Asistente: paso {i} de {len(lista)}, {p.nombre}…')
        if p.archivos is not None:
            r = cliente.pedir(p.metodo, ruta, data=cuerpo or {}, files=p.archivos(resultados))
        elif p.formulario:
            r = cliente.pedir(p.metodo, ruta, data=cuerpo or {})
        elif p.metodo == 'GET':
            r = cliente.pedir('GET', ruta)
        else:
            r = cliente.pedir(p.metodo, ruta, json=cuerpo if cuerpo is not None else {})
        if p.espera and isinstance(r, dict) and r.get('id') and r.get('status'):
            fin = cliente.esperar(r)
            trabajos.append({'paso': p.nombre, 'trabajo': fin['id'], 'estado': fin['status'],
                             'error': fin.get('error')})
            # 081:RF-20: parcial o sin converger no para el plan: lo calibrado queda y se dice.
            if fin['status'] not in ('done', 'parcial', 'no_converge'):
                raise PasoFallido(f"el paso «{p.nombre}» terminó {fin['status']}: {fin.get('error') or ''}".strip())
            r = fin.get('result')
        resultados.append(r)
        if cliente.gobierno is not None:
            cliente.gobierno.registrar_salida_paso(i - 1, r)
            cliente.gobierno.despues_paso(p)
    final = resultados[-1] if resultados else None
    # 070:RF-16: de todos los pasos; con un informe por alimentador se perdían todos menos el último.
    return {'completo': True, 'pasos': trabajos, 'resultado': final, 'entregables': entregables(resultados)}
