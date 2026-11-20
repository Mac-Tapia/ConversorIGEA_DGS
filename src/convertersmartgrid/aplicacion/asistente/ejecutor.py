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

from ...dominio.sesion_web import cabeceras_locales

#: 070:RF-87 (C2 del diagnóstico del 18-11, H03): «interrumpido» (096: la web cayó con el trabajo en marcha) también
#: termina la espera; sin él, el asistente consultaba sin fin un trabajo que ya no iba a seguir.
TERMINADOS = ('done', 'parcial', 'no_converge', 'failed', 'cancelled', 'interrumpido')
#: 070:RF-87: cuánto espera una petición a la web (las subidas grandes incluidas) y la espera entera de un trabajo.
TIEMPO_PETICION_S = 300.0
PLAZO_TRABAJO_S = 24 * 3600.0
#: 070:RF-87: cuántas consultas seguidas sin respuesta de la web dan la espera por perdida.
FALLOS_SEGUIDOS = 5
#: 070:RF-88: las rutas síncronas largas (cargar la fuente, preparar los planes, regenerar una norma, que espera su
#: subproceso hasta 1800 s) llevan su plazo; con los 300 s comunes, la petición se cortaba con la web aún trabajando.
PLAZO_SINCRONO_S = 1900.0
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
    plazo_s: float | None = None            # 070:RF-88: el plazo de su petición, si no es el común


class PasoFallido(RuntimeError):
    """Un paso devolvió un error o su trabajo no terminó bien."""


class PeticionSinRespuesta(PasoFallido):
    """070:RF-88: la web no respondió a tiempo o se cayó la conexión. Es un :class:`PasoFallido` para quien ejecuta los
    pasos (la orden falla con su motivo, no con la excepción de la biblioteca de red), y ``esperar`` lo sigue contando
    como un fallo pasajero hasta ``FALLOS_SEGUIDOS``."""


def _errores_de_red() -> tuple[type[BaseException], ...]:
    errores: list[type[BaseException]] = [OSError, TimeoutError]
    try:
        import requests
        errores.append(requests.RequestException)
    except ImportError:
        pass
    try:
        import httpx
        errores.append(httpx.HTTPError)
    except ImportError:
        pass
    return tuple(errores)


@dataclass
class ClienteWeb:
    """La API de la web desde dentro: ``http`` es una sesión de ``requests`` o el cliente de pruebas."""

    http: Any
    base: str
    espacio: str
    intervalo_s: float = 0.5
    cancelado: Callable[[], bool] = field(default=lambda: False)
    gobierno: Any = None
    tiempo_peticion_s: float = TIEMPO_PETICION_S
    plazo_trabajo_s: float = PLAZO_TRABAJO_S

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
        kw.setdefault('timeout', self.tiempo_peticion_s)          # 070:RF-87: ninguna petición espera sin límite
        try:
            r = self.http.request(metodo, self._url(ruta), **kw)
        except _errores_de_red() as exc:                          # 070:RF-88
            raise PeticionSinRespuesta(f"{metodo} {ruta}: la web no respondió en {float(kw['timeout']):g} s "
                                       f'({type(exc).__name__})') from exc
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
        """Hasta que el trabajo termina (también «interrumpido»), con un plazo total; si la web deja de responder
        ``FALLOS_SEGUIDOS`` veces seguidas, lo dice y no sigue esperando (070:RF-87)."""
        cancelado = False
        fin = time.monotonic() + self.plazo_trabajo_s
        fallos = 0
        while True:
            try:
                estado = self.pedir('GET', f"/api/jobs/{trabajo['id']}")
                fallos = 0
            except PeticionSinRespuesta as exc:   # 070:RF-88: antes que PasoFallido, para seguir contando fallos
                fallos += 1
                if fallos >= FALLOS_SEGUIDOS:
                    raise PasoFallido(f"la web no responde al consultar el trabajo {trabajo['id']} "
                                      f'({fallos} veces seguidas): {exc}') from exc
                time.sleep(self.intervalo_s)
                continue
            except PasoFallido:
                raise
            except Exception as exc:  # la web caída o lenta: requests, httpx u OSError
                fallos += 1
                if fallos >= FALLOS_SEGUIDOS:
                    raise PasoFallido(f"la web no responde al consultar el trabajo {trabajo['id']} "
                                      f'({fallos} veces seguidas): {type(exc).__name__}') from exc
                time.sleep(self.intervalo_s)
                continue
            if estado['status'] in TERMINADOS:
                return estado
            if time.monotonic() >= fin:
                raise PasoFallido(f"el trabajo {trabajo['id']} no terminó en {self.plazo_trabajo_s / 3600:g} h: "
                                  'sigue en la web; el asistente deja de esperarlo')
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
        cuerpo = {'project': proyecto, 'feeders': feeders, **({'anio_presentacion': int(anio)} if anio.isdigit() else {}),
                  **libros}
        if extras.get('plazo') == 'largo_plazo':
            # 072:RF-34, RF-35: el plan de largo plazo plantea las obras y escribe solo sus módulos; con el
            # ``implementar`` por defecto de la ruta, las aplicaba en «Con proyecto».
            return [Paso('plan de largo plazo (plantea las obras, no las aplica)', 'POST', '/pide',
                         {**cuerpo, 'plazo': 'largo_plazo', 'implementar': False})]
        return [Paso('PIDE', 'POST', '/pide', cuerpo)]
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
    nuevos = (_pasos_nube_y_correo(tarea, extras) or _pasos_pit(tarea, extras) or _pasos_vad(tarea, extras)
              or _pasos_plano(tarea, datos, extras) or _pasos_026_rf44(tarea, feeders, extras)
              or _pasos_026_rf46(tarea, datos, extras) or _pasos_026_rf42(tarea, extras))
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
        return _pasos_026_rf45(extras) or [
            Paso('preparar el ZIP de los resultados', 'POST', '/outputs/archive', {'feeders': feeders})]
    if tarea == 'pronostico':
        return [Paso('pronóstico de demanda', 'POST', '/digital-twin/temporal',
                     {**(extras.get('pronostico') or {}), 'modo': 'pronostico'})]
    return None


def cuenta_de_correo(cuentas: Any, preferido: str | None) -> dict:
    """070:RF-79: la cuenta conectada con la que sale el correo: la del proveedor que nombra la orden, o la única."""
    lista = [c for c in (cuentas or {}).get('cuentas') or [] if isinstance(c, dict) and c.get('conectada') and c.get('cuenta')]
    if preferido:
        lista = [c for c in lista if c.get('nombre') == preferido]
    if not lista:
        raise PasoFallido('No hay ninguna cuenta de correo conectada' + (f' de {preferido}' if preferido else '') +
                          ': conéctela antes, por ejemplo con «conecta mi cuenta de google».')
    if len(lista) > 1:
        raise PasoFallido('Hay más de una cuenta conectada: diga en la orden si sale por Gmail o por Outlook.')
    return lista[0]


def _pasos_nube_y_correo(tarea: str, extras: Mapping[str, Any]) -> list[Paso] | None:
    """070:RF-79 a RF-81: el asistente solo lee y prepara. Enviar, publicar, compartir, importar y conectar son el clic
    del operador en la tarjeta que queda en su panel, que el navegador manda por la ruta de siempre."""
    if tarea == 'enviar_informe':
        def peticion(r):
            c = cuenta_de_correo(r[-1], extras.get('proveedor'))
            return {'informe': extras['informe'], 'cuenta': c['cuenta'], 'proveedor': c['nombre'],
                    'para': list(extras['para']), 'origen': 'asistente'}

        return [Paso('leer las cuentas conectadas', 'GET', '/nube/cuentas', espera=False),
                Paso('preparar el borrador del correo', 'POST', '/correo/vista-previa', peticion, espera=False)]
    if tarea == 'compartir_nube':
        return [Paso('leer los expedientes publicados', 'GET', '/nube/recibos', espera=False),
                Paso('leer las cuentas conectadas', 'GET', '/nube/cuentas', espera=False)]
    if tarea in ('publicar_nube', 'importar_nube'):
        return [Paso('leer las cuentas conectadas', 'GET', '/nube/cuentas', espera=False)]
    if tarea == 'conectar_nube':
        return [Paso('leer los proveedores registrados', 'GET', '/api/nube/proveedores', espera=False)]
    return None


def _pasos_pit(tarea: str, extras: Mapping[str, Any]) -> list[Paso] | None:
    """070:RF-79: el PIT por sus rutas (``/api/pit``): sube los ficheros al espacio, pide el trabajo y lo sigue."""
    if tarea not in ('pit_diagnostico', 'pit_expediente'):
        return None
    pit = extras['pit']
    rutas = [Path(pit['libro_red']), Path(pit['proyeccion']), *([Path(pit['alternativas'])] if pit.get('alternativas') else [])]

    def ficheros(_r):
        return [('files', (p.name, p.read_bytes(), 'application/octet-stream')) for p in rutas]

    def pedido(r):
        subidas = r[-1]['rutas']
        cuerpo = {'workspace_id': pit['workspace_id'], 'area': pit['area'], 'anios': list(pit['anios']),
                  'libro_red': subidas[0], 'proyeccion': subidas[1]}
        if tarea == 'pit_expediente':
            cuerpo['periodo'] = pit['periodo']
            if pit.get('alternativas'):
                cuerpo.update(alternativas=subidas[2], alternativa_elegida=pit.get('alternativa_elegida'))
        return cuerpo

    que, ruta = (('el diagnóstico del PIT', '/api/pit/diagnostico') if tarea == 'pit_diagnostico'
                 else ('el expediente del PIT', '/api/pit/expediente'))
    return [Paso('subir el libro de la red y la proyección al espacio', 'POST', '/api/pit/entradas',
                 {'workspace_id': pit['workspace_id']}, archivos=ficheros),
            Paso(f'pedir {que}', 'POST', ruta, pedido, espera=False),
            Paso(f'esperar {que}', 'GET', lambda r: f"/api/jobs/{r[-1]['job']}")]


def _pasos_vad(tarea: str, extras: Mapping[str, Any]) -> list[Paso] | None:
    """070:RF-79, RF-86: el VAD por sus rutas: crear el estudio, o subir el caso y seguir el armado de la empresa modelo."""
    vad = extras.get('vad') or {}
    if tarea == 'vad_crear_estudio':
        return [Paso('crear el estudio del VAD', 'POST', '/vad/estudios',
                     {'grupo': vad['grupo'], 'periodo': vad['periodo'], 'version_tdr': vad['version_tdr']}, espera=False)]
    if tarea == 'vad_empresa_modelo':
        rutas = [Path(r) for r in vad['ficheros']]

        def ficheros(_r):
            return [('files', (p.name, p.read_bytes(), 'application/json')) for p in rutas]

        return [Paso('subir el caso y armar la empresa modelo', 'POST', f"/vad/{vad['estudio']}/armar", {},
                     archivos=ficheros)]
    return None


def _pasos_026_rf44(tarea: str, feeders: list[str], extras: Mapping[str, Any]) -> list[Paso] | None:
    """026:RF-44: el Estudio VNR (108) y la Evolución de clientes fijos (105) por sus rutas de la web. El VNR toma por
    defecto la red que dejó la carga del espacio y el SICODI de sus fuentes, como la pestaña; aquí solo van sus datos."""
    if tarea == 'vnr_estudio':
        vnr = extras['vnr']
        return [Paso('el estudio VNR por la Guía 232', 'POST', '/vnr/estudio',
                     {k: vnr[k] for k in ('sector', 'sector_sicodi', 'resolucion', 'anio', 'moneda')}, formulario=True)]
    if tarea == 'clientes_fijos_evolucion':
        fijos = extras['clientes_fijos']
        return [Paso('la evolución de los clientes fijos', 'POST', '/clientes-fijos/evolucion',
                     {'alimentadores': feeders, 'desde': fijos['desde'], 'hasta': fijos['hasta'],
                      'con_cabecera': bool(fijos.get('con_cabecera', True))})]   # el de la API, salvo que la orden diga otro
    return None


def _pasos_026_rf46(tarea: str, datos: Mapping[str, Any], extras: Mapping[str, Any]) -> list[Paso] | None:
    """026:RF-46: la biblioteca normativa por sus rutas (107:RF-21, RF-22). Agregar sube el .json a la capa del usuario;
    regenerar primero corre el generador en una carpeta temporal y compara con la vigente (qué reglas entran, salen o
    cambian), y solo después escribe con la ficha de esa vista previa; lo que entró va en el resultado."""
    if tarea == 'normativa_agregar':
        ruta = Path(datos['ruta'])

        def fichero(_r):
            return {'file': (ruta.name, ruta.read_bytes(), 'application/json')}

        return [Paso('agregar la norma a la biblioteca', 'POST', '/api/normativa', None, archivos=fichero, espera=False)]
    if tarea == 'normativa_regenerar':
        generador = extras['normativa']['generador']
        return [Paso('regenerar y comparar con la vigente', 'POST', '/api/normativa/regenerar',
                     {'generador': generador}, espera=False),
                Paso('escribir lo regenerado en la biblioteca', 'POST',
                     lambda r: f"/api/normativa/regenerar/{r[-1]['token']}/aplicar", None, espera=False)]
    return None


#: 026:RF-45: cómo se nombra cada módulo en los pasos que el operador confirma.
_DEL_MODULO = {'pide': 'del PIDE', 'pit': 'del PIT', 'vad': 'del VAD', 'vnr': 'del VNR', 'informes': 'de los informes'}


def _pasos_026_rf45(extras: Mapping[str, Any]) -> list[Paso] | None:
    """026:RF-45: los entregables de un módulo por las rutas que los sirven en la web. Los de la salida (PIDE, VNR e
    informes) van en el ZIP de la salida con su selección (``preparar_zip`` elige por nombre o por prefijo); el PIT y el
    VAD los dejan en su carpeta del espacio y se leen de su trabajo o de su estudio, para enlazarlos uno por uno."""
    entrega = extras.get('entrega') or {}
    if not entrega:
        return None
    del_modulo = _DEL_MODULO.get(entrega.get('modulo') or '', '')
    if entrega.get('trabajo'):
        return [Paso(f'leer los entregables {del_modulo}', 'GET', f"/api/jobs/{quote(str(entrega['trabajo']))}",
                     espera=False)]
    if entrega.get('estudio'):
        return [Paso(f'leer los entregables {del_modulo}', 'GET', f"/vad/{quote(str(entrega['estudio']))}", espera=False)]
    return [Paso(f'preparar el ZIP {del_modulo}', 'POST', '/outputs/archive', {'feeders': list(entrega['seleccion'])})]


def _pasos_026_rf42(tarea: str, extras: Mapping[str, Any]) -> list[Paso] | None:
    """026:RF-42: las entradas del espacio por las rutas de la web. La casilla recibe el fichero por su subida, que lo
    valida en su sitio aparte antes de tocar la entrada vigente (086:RF-3); el libro entra en las fuentes de la empresa
    con su clase y su año (109:RF-25)."""
    if tarea == 'asignar_entrada':
        entrada = extras['entrada']
        ruta = Path(entrada['ruta'])

        def fichero(_r):
            return {'file': (ruta.name, ruta.read_bytes(), 'application/octet-stream')}

        return [Paso(f"asignar «{ruta.name}» a la casilla «{entrada['etiqueta']}»", 'POST',
                     f"/inputs/{quote(entrada['casilla'])}", None, archivos=fichero, espera=False)]
    if tarea == 'subir_fuente_empresa':
        fuente = extras['fuente']
        ruta = Path(fuente['ruta'])

        def libro(_r):
            return {'file': (ruta.name, ruta.read_bytes(), 'application/octet-stream')}

        return [Paso(f"subir «{ruta.name}» a las fuentes de la empresa"
                     + (f" ({fuente['periodo']})" if fuente.get('periodo') else ''), 'POST', '/fuentes',
                     {'clase': fuente['clase'], 'periodo': fuente.get('periodo') or ''}, archivos=libro, espera=False)]
    return None


def _pasos_plano(tarea: str, datos: Mapping[str, Any], extras: Mapping[str, Any]) -> list[Paso] | None:
    """070:RF-79: el plano por sus rutas (111): la vista y su revisión, una variación, la maniobra y su estudio."""
    if tarea != 'plano_maniobra':
        return None
    plano = extras['plano']
    alimentador = plano['alimentador']

    def abrir(r):
        vista = next((v for v in (r[-1] or {}).get('vistas') or [] if v.get('alimentador') == alimentador), None)
        if vista is None:
            raise PasoFallido(f'El alimentador {alimentador} no está en el plano: conviértalo antes.')
        codigos = [m['codigo'] for m in vista.get('maniobras') or []]
        if plano['maniobra'] not in codigos:
            raise PasoFallido(f"La maniobra {plano['maniobra']} no está en {alimentador}; las que hay son "
                              + (', '.join(codigos[:12]) or 'ninguna') + '.')
        return {'alimentador': alimentador, 'caso': plano['caso'], 'revision': vista['revision']}

    return [Paso('leer el plano del alimentador', 'GET', f'/plano?alimentador={quote(alimentador)}', espera=False),
            Paso('abrir una variación sobre la red actual', 'POST', '/plano/variaciones', abrir, espera=False),
            Paso(f"{'abrir' if plano['estado'] == 'abierto' else 'cerrar'} la maniobra {plano['maniobra']}", 'PATCH',
                 lambda r: f"/plano/variaciones/{r[-1]['id']}",
                 lambda r: {'version': r[-1]['version'],
                            'edicion': {'tipo': 'maniobra', 'codigo': plano['maniobra'], 'estado': plano['estado']}},
                 espera=False),
            Paso('estudiar la variación', 'POST', lambda r: f"/plano/variaciones/{r[-1]['id']}/estudiar",
                 {'project': datos.get('proyecto') or None})]


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


#: 070:RF-88: las rutas que responden cuando terminan (no encolan): su petición lleva ``PLAZO_SINCRONO_S``.
RUTAS_SINCRONAS_LARGAS = ('/load', '/lote/plan', '/pf/estudios/plan', '/api/normativa/regenerar')


def plazo_del_paso(p: Paso, ruta: str) -> dict[str, float]:
    """El ``timeout`` de la petición de un paso: el suyo, el de las rutas síncronas largas o el común (070:RF-88)."""
    if p.plazo_s:
        return {'timeout': float(p.plazo_s)}
    return {'timeout': PLAZO_SINCRONO_S} if ruta in RUTAS_SINCRONAS_LARGAS else {}


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
        plazo = plazo_del_paso(p, ruta)                            # 070:RF-88
        if p.archivos is not None:
            r = cliente.pedir(p.metodo, ruta, data=cuerpo or {}, files=p.archivos(resultados), **plazo)
        elif p.formulario:
            r = cliente.pedir(p.metodo, ruta, data=cuerpo or {}, **plazo)
        elif p.metodo == 'GET':
            r = cliente.pedir('GET', ruta, **plazo)
        else:
            r = cliente.pedir(p.metodo, ruta, json=cuerpo if cuerpo is not None else {}, **plazo)
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
