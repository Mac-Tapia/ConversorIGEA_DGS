"""065: permisos del equipo vinculados al plan; un modelo nunca concede autoridad.

El operador autoriza una tarea concreta, sobre la fuente que vio al proponerla.
Los revisores producen dictámenes; las rutas y carriles existentes hacen el trabajo.
Este gobierno no acredita calidad del LLM ni aceptación eléctrica (027/047/061).
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading
import uuid
from typing import Any
from urllib.parse import urlsplit

from . import almacen
from .tareas import TAREAS

ROLES_REVISION = ('fuentes', 'fisica', 'coste', 'riesgo')
_NATIVAS = frozenset({'leer_proyectos', 'flujo', 'verificar_caso_base', 'cargas_nuevas',
    'obras', 'estudios', 'transferencia', 'pide', 'gemelo_aprender', 'sistema_completo',
    'obras_escalera', 'optimizar_con_proyecto', 'informe_factibilidad', 'set_completo', 'alimentadores_completo',
    'calibrar', 'simular_calibracion', 'recalibrar', 'escanear', 'verificar_convergencia', 'carga_nueva_sola',
    'proyecto_entero'})
_CERROJO = threading.Lock()
_ACTIVOS: set[str] = set()


class PermisoDenegado(ValueError):
    """Una acción no pertenece al permiso concedido por el servidor."""


def _huella(dato: Any) -> str:
    return hashlib.sha256(json.dumps(dato, ensure_ascii=False, sort_keys=True,
                                    default=str, allow_nan=False).encode('utf-8')).hexdigest()


def _firma_plan(plan) -> str:
    return _huella({'id': plan.id, 'tarea': plan.tarea, 'datos': plan.datos,
                    'escribe': plan.escribe, 'modo': plan.modo})


def _contexto(ws, proyecto: str) -> dict:
    return {'espacio': ws.id, 'fuente': ws.loaded_source_fingerprint,
            'modo_fuente': ws.loaded_source_mode, 'proyecto': proyecto or None,
            'vinculo_proyecto_sha256': _huella((getattr(ws, 'pf_project_bindings', {}) or {}).get(proyecto))}


def inventario_equipo() -> dict:
    """Catálogo sin permisos implícitos: la disponibilidad no equivale a autorización.

    067:RF-40: el proyecto entero se confirma con una lista única, y aquí se dice. El inventario
    declaraba «confirmación obligatoria» por herramienta mientras un clic las confirmaba todas.
    """
    from .orquestador import ETAPAS

    en_proyecto = {e.tarea for e in ETAPAS}
    return {'modelos_conceden_permisos': False, 'autonomia_habilitada': False,
        'roles': [{'rol': r, 'puede_ejecutar': r == 'operador',
                   'requiere_permiso_del_plan': True} for r in ('operador', *ROLES_REVISION)],
        'herramientas': [{'herramienta': t.nombre, 'funcion': t.funcion, 'modo': t.modo,
            'escribe': t.escribe, 'carril': 'powerfactory' if t.nombre in _NATIVAS else 'engine',
            'permiso_efectivo': False, 'rol_ejecutor': 'operador',
            'confirmacion_obligatoria': t.escribe,
            'confirmacion_en_proyecto': 'lista_unica_mostrada' if t.nombre in en_proyecto else None}
            for t in TAREAS.values()],
        'proyecto_entero': {'confirmacion': 'lista_unica_mostrada', 'confirmacion_por_etapa': False,
            'etapas_escritura': [e.nombre for e in ETAPAS if TAREAS[e.tarea].escribe],
            'ruta_lista': 'POST /api/workspaces/{id}/agente/proyecto/lista'},
        'concurrencia': {'por_espacio': 1, 'motor_nativo': 'carril powerfactory de JobManager',
                         'revision': 'secuencial; máximo dos rondas'}}


class GobiernoEquipo:
    """Permiso interno del servidor, no construible desde texto libre del LLM.

    Debe crearse al guardar el plan y confirmarse desde la ruta autorizada. La
    exclusión protege acciones del asistente en este proceso; el único acceso
    nativo continúa serializado por JobManager y pf_arnes, también entre procesos.
    """

    @classmethod
    def desde_plan(cls, ws, plan, *, rol: str = 'operador', extras: dict | None = None):
        instancia = cls()
        instancia.ws = ws
        instancia.plan_id = plan.id
        instancia.tarea = plan.tarea
        instancia.datos = deepcopy(plan.datos)
        instancia.extras = deepcopy(extras or {})
        instancia.rol = rol
        instancia.firma = _firma_plan(plan)
        instancia.alcance = _contexto(ws, instancia.datos.get('proyecto', ''))
        instancia.archivos_entrada = {}
        ruta = instancia.datos.get('ruta')
        if ruta and Path(ruta).is_file():
            with Path(ruta).open('rb') as archivo:
                instancia.archivos_entrada[str(Path(ruta).resolve())] = hashlib.file_digest(archivo, 'sha256').hexdigest()
        instancia.confirmado = False
        instancia.listo = plan.listo
        instancia.lectura = plan.tarea in TAREAS and not TAREAS[plan.tarea].escribe
        instancia._activa = False
        return instancia

    def sello(self) -> dict:
        """Lo que se selló al proponer el plan, para guardarlo con él (067:RF-12)."""
        return {'firma': self.firma, 'alcance': deepcopy(self.alcance), 'rol': self.rol,
                'archivos_entrada': dict(self.archivos_entrada)}

    @classmethod
    def restaurar(cls, ws, plan, *, extras: dict | None, sello: dict):
        """El permiso de un plan guardado tras un reinicio: el contexto es el sellado al proponerlo,
        no el de ahora, y nunca vuelve confirmado (067:RF-13 a RF-16). Lo que había confirmado el
        operador se perdió con el proceso; ejecutarlo sin preguntar reanudaría una escritura sola."""
        instancia = cls.desde_plan(ws, plan, rol=sello.get('rol', 'operador'), extras=extras)
        if instancia.firma != sello.get('firma'):
            raise PermisoDenegado('el plan guardado no coincide con su firma; proponga otro plan')
        instancia.alcance = deepcopy(sello['alcance'])
        instancia.archivos_entrada = dict(sello.get('archivos_entrada') or {})
        return instancia

    def confirmar(self, plan) -> None:
        """Sella la confirmación del operador para el plan mostrado, sin ampliar su rol."""
        if _firma_plan(plan) != self.firma:
            raise PermisoDenegado('el plan cambió: vuelva a proponerlo y confirmarlo')
        self._validar_contexto()
        self.confirmado = True

    def _validar_contexto(self) -> None:
        if _contexto(self.ws, self.datos.get('proyecto', '')) != self.alcance:
            raise PermisoDenegado('cambió el contexto de fuente o espacio; proponga otro plan')
        for ruta, esperado in self.archivos_entrada.items():
            try:
                with Path(ruta).open('rb') as archivo:
                    actual = hashlib.file_digest(archivo, 'sha256').hexdigest()
            except OSError as exc:
                raise PermisoDenegado('archivo de entrada ya no disponible') from exc
            if actual != esperado:
                raise PermisoDenegado('archivo de entrada alterado; proponga otro plan')

    def _validar(self) -> None:
        self._validar_contexto()
        if self.rol != 'operador':
            raise PermisoDenegado(f'el rol {self.rol!r} no tiene permiso de ejecución')
        if self.tarea not in TAREAS:
            raise PermisoDenegado('herramienta desconocida o fuera de la lista permitida')
        if not self.listo:
            raise PermisoDenegado('el plan está incompleto')
        if not self.lectura and not self.confirmado:
            raise PermisoDenegado('la escritura requiere confirmación del operador')

    def publico(self) -> dict:
        """Permiso y límites del plan; nunca incorpora pesos ni datos empresariales."""
        try:
            self._validar()
            efectivo, motivo = True, ''
        except PermisoDenegado as exc:
            efectivo, motivo = False, str(exc)
        return {'plan': self.plan_id, 'responsable': self.rol, 'herramienta': self.tarea,
                'alcance': deepcopy(self.alcance), 'confirmada': self.confirmado,
                'permiso_efectivo': efectivo, 'motivo': motivo,
                'revision': 'confirmacion_operador; no es aceptación científica',
                'carril': 'powerfactory' if self.tarea in _NATIVAS else 'engine',
                'limite_concurrente_espacio': 1, 'autonomia_habilitada': False}

    @contextmanager
    def accion(self, *, cancelado=lambda: False):
        """Admisión y bitácora antes de ejecutar; el recurso siempre se libera."""
        accion_id = uuid.uuid4().hex
        base = {'accion': accion_id, 'plan': self.plan_id, 'herramienta': self.tarea,
            'responsable': self.rol, 'alcance': deepcopy(self.alcance),
            'entradas': deepcopy(self.datos), 'entrada_sha256': _huella(self.datos),
            'archivos_entrada': dict(self.archivos_entrada),
            'carril': 'powerfactory' if self.tarea in _NATIVAS else 'engine',
            'revision': {'decision': 'confirmada_operador' if self.confirmado else 'lectura_permitida',
                         'responsable': 'operador', 'plan_sha256': self.firma},
            'aceptacion_cientifica': False, 'aceptacion_nativa': None}
        try:
            self._validar()
            if cancelado():
                raise PermisoDenegado('acción cancelada antes de iniciar')
            with _CERROJO:
                if self.alcance['espacio'] in _ACTIVOS:
                    raise PermisoDenegado('límite de concurrencia del espacio alcanzado')
                _ACTIVOS.add(self.alcance['espacio'])
        except PermisoDenegado as exc:
            almacen.anotar('equipo_acciones', {**base, 'estado': 'rechazada', 'motivo': str(exc)})
            raise
        try:
            almacen.anotar('equipo_acciones', {**base, 'estado': 'iniciada'})
            self._registro = base
            self._activa = True
            self._solicitud = None
            self._trabajos = set()
            resultado = {}
            yield resultado
            almacen.anotar('equipo_acciones', {**base, 'estado': 'cancelada' if cancelado() else 'terminada',
                'salida_sha256': _huella(resultado.get('salida')),
                'salida': self._resumen(resultado.get('salida')), 'alcance_final': deepcopy(self.alcance)})
        except Exception as exc:
            almacen.anotar('equipo_acciones', {**base, 'estado': 'fallida', 'motivo': str(exc)})
            raise
        finally:
            self._activa = False
            with _CERROJO:
                _ACTIVOS.discard(self.alcance['espacio'])

    def validar_pasos(self, lista) -> None:
        """Compara el plan generado por el servidor, incluidas rutas y cuerpos dinámicos."""
        from .ejecutor import pasos
        esperados = pasos(self.tarea, self.datos, self.extras)
        if len(lista) != len(esperados):
            raise PermisoDenegado('lista de pasos distinta del plan autorizado')
        self._esperados = esperados

    def validar_cliente(self, cliente) -> None:
        if cliente.espacio != self.alcance['espacio']:
            raise PermisoDenegado('el cliente apunta a otro espacio')
        url = urlsplit(cliente.base)
        prueba_local = (url.hostname == 'testserver' and
                        type(cliente.http).__module__ == 'starlette.testclient')
        if cliente.base and (url.scheme not in ('http', 'https') or
                (url.hostname not in ('127.0.0.1', '::1', 'localhost') and not prueba_local)
                or url.username or url.password or url.query or url.fragment or url.path not in ('', '/')):
            raise PermisoDenegado('la API del asistente debe ser local y sin redirecciones externas')

    def autorizar_peticion(self, metodo: str, ruta: str, parametros: dict) -> None:
        """También la frontera HTTP exige permiso: no basta saltarse el bucle de pasos."""
        if self.rol != 'operador' or self.tarea not in TAREAS or not self.listo:
            raise PermisoDenegado('el rol o la herramienta no tienen permiso HTTP')
        if not self.lectura and not self.confirmado:
            raise PermisoDenegado('la escritura requiere confirmación del operador')
        if self._activa:
            solicitud = getattr(self, '_solicitud', None)
            cuerpo = parametros.get('json', parametros.get('data', {}))
            if solicitud and solicitud == (metodo, ruta, _huella(cuerpo), _huella(parametros.get('files'))):
                self._solicitud = None
                return
            for trabajo in self._trabajos:
                if (metodo, ruta) in (('GET', f'/api/jobs/{trabajo}'),
                                     ('POST', f'/api/jobs/{trabajo}/cancel')):
                    return
            raise PermisoDenegado('petición fuera del paso autorizado')
        self._validar()
        if metodo == 'GET' and (ruta in ('', '/obras') or ruta.startswith(('/demanda/sistema?project=', '/demanda/ajuste/ultimo?project='))):
            return
        raise PermisoDenegado('la petición requiere un paso activo del plan autorizado')

    def registrar_respuesta_http(self, respuesta) -> None:
        if isinstance(respuesta, dict) and respuesta.get('id') and respuesta.get('status'):
            if respuesta.get('workspace_id', self.alcance['espacio']) != self.alcance['espacio']:
                raise PermisoDenegado('la API devolvió un trabajo de otro espacio')
            self._trabajos.add(str(respuesta['id']))

    def validar_paso(self, indice: int, paso, resultados: list) -> None:
        self._validar_contexto()
        esperado = self._esperados[indice]
        def valor(c):
            return c(resultados) if callable(c) else c
        if (paso.metodo != esperado.metodo or valor(paso.ruta) != valor(esperado.ruta)
                or valor(paso.cuerpo) != valor(esperado.cuerpo)
                or paso.espera != esperado.espera or bool(paso.archivos) != bool(esperado.archivos)):
            raise PermisoDenegado('paso fuera de la ruta, método o entradas autorizados')
        if paso.archivos and _huella(paso.archivos(resultados)) != _huella(esperado.archivos(resultados)):
            raise PermisoDenegado('archivos del paso distintos del plan autorizado')
        almacen.anotar('equipo_acciones', {**self._registro, 'estado': 'paso_autorizado',
            'paso': indice + 1, 'nombre': paso.nombre, 'metodo': paso.metodo, 'ruta': valor(paso.ruta),
            'entrada_paso_sha256': _huella(valor(paso.cuerpo))})
        self._solicitud = (paso.metodo, valor(paso.ruta),
            _huella(valor(paso.cuerpo) or {}),
            _huella(esperado.archivos(resultados) if esperado.archivos else None))

    @staticmethod
    def _resumen(salida):
        if isinstance(salida, dict):
            return {k: v for k, v in salida.items() if
                    isinstance(v, (str, int, float, bool, type(None))) or k == 'entregables'}
        return salida if isinstance(salida, (str, int, float, bool, type(None))) else None

    def registrar_salida_paso(self, indice: int, salida) -> None:
        almacen.anotar('equipo_acciones', {**self._registro, 'estado': 'paso_terminado',
            'paso': indice + 1, 'salida_paso_sha256': _huella(salida), 'salida': self._resumen(salida)})

    def despues_paso(self, paso) -> None:
        # Cargar es la única transición prevista de fuente no cargada a cargada.
        # Una fuente ya vinculada nunca se puede sustituir desde el mismo permiso.
        if paso.ruta == '/load' and self.alcance['fuente'] is None:
            self.alcance = _contexto(self.ws, self.datos.get('proyecto', ''))

    def ejecutar_proceso(self, funcion, *, cancelado=lambda: False):
        """Aplica el mismo gobierno a las herramientas de proceso existentes."""
        if self.tarea not in TAREAS or TAREAS[self.tarea].modo != 'proceso':
            raise PermisoDenegado('la herramienta no pertenece al modo proceso')
        with self.accion(cancelado=cancelado) as evidencia:
            resultado = funcion()
            if isinstance(resultado, dict) and resultado.get('codigo', 0) != 0:
                raise RuntimeError(f"la herramienta terminó con código {resultado['codigo']}")
            evidencia['salida'] = resultado
            return resultado
