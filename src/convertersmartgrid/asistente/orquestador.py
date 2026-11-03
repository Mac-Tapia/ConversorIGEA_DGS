"""El proyecto entero desde un espacio vacío, etapa por etapa (spec 027, T21; RF-43, RF-44).

El agente encadena lo que el operador hace a mano en la web, por las mismas rutas y trabajos:
cargar la fuente, el sistema eléctrico de punta a punta (convertir, importar en DIgSILENT y
calibrar, ``tools/sistema_web.py``), verificar el «Caso base», integrar las cargas nuevas,
aplicar las obras, los estudios, el PIDE y el informe. Al terminar cada etapa guarda un punto
de control; si la ejecución se corta (DIgSILENT ocupado, la web reiniciada), la siguiente
retoma desde la primera etapa sin hacer y no repite nada (RF-44). Una etapa que necesita un
dato que no se dio (el libro de cargas nuevas, el formulario del informe) se omite y se dice.
"""
from __future__ import annotations

from ..runtime_paths import staging_publicacion

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..evaluacion_modelos import huella
from .ejecutor import ClienteWeb, ejecutar, pasos
from .tareas import TAREAS


@dataclass(frozen=True)
class Etapa:
    nombre: str
    tarea: str
    requiere: tuple[str, ...] = ()
    """Datos sin los que no se hace; si faltan y es ``opcional``, se omite."""
    opcional: bool = False
    proceso: bool = False
    """La hace una herramienta de ``tools/`` (``sistema_web.py``), no una ruta."""
    condicion: str = ''
    """Cuándo hace falta, comprobado al llegar a ella; vacío, siempre (070:RF-53, RF-54)."""


#: Las etapas del proyecto desde cero (RF-43), en orden.
ETAPAS: tuple[Etapa, ...] = (
    Etapa('fuente', 'cargar_fuente'),
    Etapa('sistema', 'sistema_completo', ('sistema', 'periodo', 'ruta'), proceso=True),
    Etapa('caso_base', 'verificar_caso_base', ('proyecto',)),
    Etapa('cargas_nuevas', 'cargas_nuevas', ('proyecto', 'ruta_cargas'), opcional=True),
    Etapa('obras', 'obras', ('proyecto',)),
    Etapa('estudios', 'estudios', ('proyecto',)),
    Etapa('pide', 'pide', ('proyecto',)),
    Etapa('informe', 'informe_estudio', ('proyecto', 'formulario'), opcional=True),
)


#: 070:RF-50: evaluar una carga nueva. El informe se hace al evaluar porque ya prepara los casos y concluye
#: (063:RF-1); solo se rehace si hubo obras. Su libro lo decide el perfil, dentro del propio informe (066:RF-1).
ETAPAS_CARGA: tuple[Etapa, ...] = (
    Etapa('diagnostico', 'verificar_convergencia', ('proyecto',)),
    Etapa('calibracion', 'recalibrar', ('proyecto', 'periodo'), condicion='sin_calibracion'),
    Etapa('carga', 'carga_nueva_sola', ('proyecto', 'alimentadores', 'sed', 'nueva')),
    Etapa('evaluacion', 'informe_factibilidad', ('proyecto', 'alimentadores', 'sed', 'formulario')),
    Etapa('obras', 'optimizar_con_proyecto', ('proyecto', 'alimentadores'), condicion='si_no_factible'),
    Etapa('informe', 'informe_factibilidad', ('proyecto', 'alimentadores', 'sed', 'formulario'), condicion='si_hubo_obras'),
)

#: Qué se enseña de una condición antes de que se pueda comprobar.
_CONDICIONES = {'sin_calibracion': 'solo si no tiene calibración', 'si_no_factible': 'solo si la evaluación pide obras',
                'si_hubo_obras': 'solo si hubo obras'}

#: Datos que deja una etapa para las siguientes, y que por eso no faltan antes de empezar.
LOS_DEJA_UNA_ETAPA = ('proyecto', 'alimentadores')


@dataclass
class PuntoDeControl:
    """Las etapas hechas de un proyecto, en un JSON que sobrevive a un reinicio (RF-44)."""

    ruta: Path
    estado: dict[str, Any] = field(default_factory=dict)
    identidad_actual: Callable[[],dict] | None = field(default=None,repr=False)

    def validar_identidad(self) -> None:
        if self.identidad_actual is not None and self.estado.get('identidad')!=self.identidad_actual():
            raise ValueError('la identidad de la fuente cambió durante la ejecución; se detiene el agente')

    @classmethod
    def abrir(cls, ruta: Path | str) -> PuntoDeControl:
        ruta = Path(ruta)
        estado = json.loads(ruta.read_text(encoding='utf-8')) if ruta.is_file() else {}
        estado.setdefault('etapas', {})
        estado.setdefault('datos', {})
        return cls(ruta, estado)

    def hecha(self, etapa: str) -> bool:
        return (self.estado['etapas'].get(etapa) or {}).get('estado') in ('hecha', 'omitida')

    def marcar(self, etapa: str, estado: str, resultado: Any = None, datos: Mapping[str, Any] | None = None) -> None:
        if self.identidad_actual is not None:
            if etapa=='fuente' and estado=='hecha':
                self.estado['identidad']=self.identidad_actual()
            else:self.validar_identidad()
        self.estado['etapas'][etapa] = {'estado': estado, 'resultado': resultado,
                                        'fecha': time.strftime('%Y-%m-%dT%H:%M:%S')}
        if datos is not None:
            self.estado['datos'] = dict(datos)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with staging_publicacion(self.ruta) as tmp:
            tmp.write_text(json.dumps(self.estado, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
            tmp.replace(self.ruta)


def lista_de_etapas(datos: Mapping[str, Any], control: Mapping[str, Any], contexto: Mapping[str, Any],
                    *, reiniciar: bool = False, etapas: tuple[Etapa, ...] = ETAPAS,
                    omitir: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Lo que hará el proyecto entero, antes del único clic (067:RF-37, RF-39).

    Un clic confirmaba todas las etapas sin enseñarlas. La huella ata la confirmación a lo que se vio:
    otra fuente, otros datos u otras etapas hechas ya no son lo que el operador aceptó.
    """
    hechas = {} if reiniciar else (control.get('etapas') or {})
    conocidos = {**({} if reiniciar else (control.get('datos') or {})), **dict(datos)}
    # El proyecto y sus alimentadores los deja la etapa del sistema: no faltan si aún va a correr.
    if (hechas.get('sistema') or {}).get('estado') not in ('hecha', 'omitida'):
        conocidos.setdefault('proyecto', '(lo deja la etapa del sistema)')
    filas = []
    omitir = omitir or {}
    for e in etapas:
        falta = [k for k in e.requiere if not conocidos.get(k)]
        if (hechas.get(e.nombre) or {}).get('estado') in ('hecha', 'omitida'):
            estado = 'hecha'
        elif e.nombre in omitir:
            estado, falta = 'se_omitira', []
        elif falta:
            estado = 'se_omitira' if e.opcional else 'falta_dato'
        else:
            estado = 'pendiente'
        filas.append({'nombre': e.nombre, 'tarea': e.tarea, 'descripcion': TAREAS[e.tarea].descripcion,
                      'escribe': TAREAS[e.tarea].escribe, 'estado': estado, 'falta': falta,
                      'motivo': omitir.get(e.nombre, ''), 'condicion': _CONDICIONES.get(e.condicion, '')})
    escrituras = [f['nombre'] for f in filas if f['escribe'] and f['estado'] == 'pendiente']
    identidad = None if reiniciar else control.get('identidad')
    return {'etapas': filas, 'etapas_escritura': escrituras, 'bloqueo': (
                'Hay un punto de control de otra fuente o solicitud: marque «Empezar de nuevo».'
                if hechas and identidad != {**dict(contexto), 'solicitud': dict(datos)} else ''),
            'confirmacion': huella({'contexto': dict(contexto), 'solicitud': dict(datos), 'reiniciar': reiniciar,
                                     'etapas': [(f['nombre'], f['estado']) for f in filas]})}


def _resumen(resultado: Any) -> Any:
    """Lo que se guarda de una etapa: lo pequeño, no las curvas ni las tablas."""
    if isinstance(resultado, dict):
        return {k: v for k, v in resultado.items() if isinstance(v, (str, int, float, bool, type(None)))}
    return resultado if isinstance(resultado, (str, int, float, bool, type(None))) else None


def _factible(resumen: Any) -> Any:
    return resumen.get('factible') if isinstance(resumen, Mapping) else None


def _motivo_para_omitir(e: Etapa, cliente: ClienteWeb, datos: Mapping[str, Any], control: PuntoDeControl) -> str:
    """Por qué esta etapa no hace falta ahora; vacío si hace falta (070:RF-53, RF-54)."""
    if e.condicion == 'sin_calibracion':
        respuesta = cliente.pedir('GET', f"/demanda/ajuste/ultimo?project={quote(str(datos.get('proyecto') or ''))}") or {}
        return f"{datos.get('proyecto')} ya tiene calibración aplicada." if respuesta.get('ajuste') else ''
    previa = control.estado['etapas'].get('evaluacion') or {}
    if e.condicion == 'si_no_factible':
        # Solo un «no» explícito lleva a obras: sin conclusión no se construye nada por si acaso (063:RF-8).
        return '' if _factible(previa.get('resultado')) is False else 'la evaluación concluye que se conecta sin obras.'
    if e.condicion == 'si_hubo_obras':
        return '' if (control.estado['etapas'].get('obras') or {}).get('estado') == 'hecha' else 'no hubo obras: vale el informe de la evaluación.'
    return ''


def _extras_de_etapa(e: Etapa, datos: Mapping[str, Any]) -> dict[str, Any]:
    formulario = dict(datos.get('formulario') or {})
    if e.tarea == 'informe_factibilidad':
        formulario['preparar_casos'] = True                                   # 063:RF-1: en un paso
    extras: dict[str, Any] = {'formulario': formulario}
    if e.tarea == 'carga_nueva_sola':
        extras['nueva'] = datos.get('nueva')
    if e.tarea == 'optimizar_con_proyecto' and datos.get('sed'):
        extras['cargas'] = [datos['sed']]                                     # 063:RF-23: la de esta evaluación
    if datos.get('tipo_cambio'):
        extras['tipo_cambio'] = datos['tipo_cambio']
    return extras


def _datos_tras(etapa: Etapa, datos: dict[str, Any], cliente: ClienteWeb) -> dict[str, Any]:
    """Lo que una etapa deja para las siguientes: tras el sistema, su proyecto y alimentadores."""
    if etapa.tarea != 'sistema_completo':
        return datos
    estado = cliente.pedir('GET', '') or {}
    grupo = f"SISTEMA_{str(datos['sistema']).upper()}"
    proyecto = (estado.get('pf_projects') or {}).get(grupo)
    if not proyecto:
        raise RuntimeError(f'tras el sistema {datos["sistema"]} no hay proyecto de DIgSILENT ({grupo})')
    sistema = (cliente.pedir('GET', f'/demanda/sistema?project={proyecto}') or {}).get('sistema') or {}
    return {**datos, 'proyecto': proyecto,
            'alimentadores': list(sistema.get('alimentadores') or datos.get('alimentadores') or [])}


def ejecutar_proyecto(datos: Mapping[str, Any], *, cliente: ClienteWeb, control: PuntoDeControl,
                      proceso: Callable[[str, Mapping[str, Any]], Any],
                      log: Callable[[str], None] = lambda _m: None,
                      etapas: tuple[Etapa, ...] = ETAPAS,
                      gobierno_etapa: Callable | None = None,
                      avance: Callable[[int,int,str],None] = lambda *_a:None) -> dict[str, Any]:
    """Las etapas que faltan, en orden, con su punto de control (RF-43, RF-44)."""
    datos = {**control.estado.get('datos', {}), **dict(datos)}
    # 070:RF-8: lo que no va a aparecer por el camino se dice antes de empezar: se cargaba la fuente y
    # la etapa siguiente moría por una opción obligatoria de ``sistema_web.py``.
    previos = sorted({k for e in etapas if not e.opcional and not e.condicion and not control.hecha(e.nombre)
                      for k in e.requiere if k not in LOS_DEJA_UNA_ETAPA and not datos.get(k)})
    if previos:
        raise ValueError(f'el proyecto necesita {", ".join(previos)} antes de empezar')
    for i, e in enumerate(etapas, 1):
        control.validar_identidad()
        avance(i-1,len(etapas),e.nombre)
        if control.hecha(e.nombre):
            log(f'Agente: etapa {i} de {len(etapas)}, {e.nombre}: ya hecha, no se repite (027:RF-44)')
            avance(i,len(etapas),e.nombre)
            continue
        if cliente.cancelado():
            return {'completo': False, 'cancelado': True, 'etapas': control.estado['etapas']}
        if e.condicion and (motivo := _motivo_para_omitir(e, cliente, datos, control)):
            log(f'Agente: etapa {e.nombre} omitida: {motivo}')
            control.marcar(e.nombre, 'omitida', {'motivo': motivo}, datos)
            avance(i,len(etapas),e.nombre)
            continue
        faltan = [k for k in e.requiere if not datos.get(k)]
        if not faltan and e.tarea == 'obras' and not (cliente.pedir('GET', '/obras') or []):
            log('Agente: etapa obras omitida: no hay obras pendientes en el espacio')
            control.marcar(e.nombre, 'omitida', {'falta': ['obras pendientes']}, datos)
            avance(i,len(etapas),e.nombre)
            continue
        if faltan:
            if not e.opcional:
                raise ValueError(f'la etapa {e.nombre} necesita {", ".join(faltan)}')
            log(f'Agente: etapa {e.nombre} omitida: falta {", ".join(faltan)}')
            control.marcar(e.nombre, 'omitida', {'falta': faltan}, datos)
            avance(i,len(etapas),e.nombre)
            continue
        log(f'Agente: etapa {i} de {len(etapas)}, {e.nombre}…')
        datos_tarea = {**datos, 'ruta': datos.get('ruta_cargas') if e.tarea == 'cargas_nuevas' else datos.get('ruta')}
        extras = _extras_de_etapa(e, datos)
        gobierno = gobierno_etapa(e.tarea, datos_tarea, extras) if gobierno_etapa is not None else None
        cliente.gobierno = gobierno
        if e.proceso:
            resultado = (gobierno.ejecutar_proceso(lambda: proceso(e.tarea, datos_tarea),
                                                  cancelado=cliente.cancelado) if gobierno is not None
                         else proceso(e.tarea, datos_tarea))
            if isinstance(resultado,dict) and resultado.get('codigo',0)!=0:
                raise RuntimeError(f'la etapa {e.nombre} terminó con código {resultado["codigo"]}; no se marca hecha')
        else:
            resultado = ejecutar(pasos(e.tarea, datos_tarea, extras), cliente, log)
        if e.tarea == 'verificar_convergencia':
            final = resultado.get('resultado') if isinstance(resultado, Mapping) else None
            if isinstance(final, Mapping) and final.get('returncode', 0) != 0:
                # 070:RF-50: nada se conecta sobre una red que no converge: se dice y se para.
                raise RuntimeError(f"{datos.get('proyecto')} no converge en el diagnóstico (informe {final.get('report')}): "
                                   'corrija la causa antes de evaluar la carga')
        datos = _datos_tras(e, datos, cliente)
        control.marcar(e.nombre, 'hecha', _resumen(resultado if not isinstance(resultado, dict)
                                                     else resultado.get('resultado', resultado)), datos)
        avance(i,len(etapas),e.nombre)
    return {'completo': True, 'etapas': control.estado['etapas'], 'datos': datos}
