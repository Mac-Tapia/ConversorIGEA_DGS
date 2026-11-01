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

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ejecutor import ClienteWeb, ejecutar, pasos


@dataclass(frozen=True)
class Etapa:
    nombre: str
    tarea: str
    requiere: tuple[str, ...] = ()
    """Datos sin los que no se hace; si faltan y es ``opcional``, se omite."""
    opcional: bool = False
    proceso: bool = False
    """La hace una herramienta de ``tools/`` (``sistema_web.py``), no una ruta."""


#: Las etapas del proyecto desde cero (RF-43), en orden.
ETAPAS: tuple[Etapa, ...] = (
    Etapa('fuente', 'cargar_fuente'),
    Etapa('sistema', 'sistema_completo', ('sistema', 'periodo'), proceso=True),
    Etapa('caso_base', 'verificar_caso_base', ('proyecto',)),
    Etapa('cargas_nuevas', 'cargas_nuevas', ('proyecto', 'ruta_cargas'), opcional=True),
    Etapa('obras', 'obras', ('proyecto',)),
    Etapa('estudios', 'estudios', ('proyecto',)),
    Etapa('pide', 'pide', ('proyecto',)),
    Etapa('informe', 'informe_estudio', ('proyecto', 'formulario'), opcional=True),
)


@dataclass
class PuntoDeControl:
    """Las etapas hechas de un proyecto, en un JSON que sobrevive a un reinicio (RF-44)."""

    ruta: Path
    estado: dict[str, Any] = field(default_factory=dict)

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
        self.estado['etapas'][etapa] = {'estado': estado, 'resultado': resultado,
                                        'fecha': time.strftime('%Y-%m-%dT%H:%M:%S')}
        if datos is not None:
            self.estado['datos'] = dict(datos)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.estado, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
        tmp.replace(self.ruta)


def _resumen(resultado: Any) -> Any:
    """Lo que se guarda de una etapa: lo pequeño, no las curvas ni las tablas."""
    if isinstance(resultado, dict):
        return {k: v for k, v in resultado.items() if isinstance(v, (str, int, float, bool, type(None)))}
    return resultado if isinstance(resultado, (str, int, float, bool, type(None))) else None


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
                      etapas: tuple[Etapa, ...] = ETAPAS) -> dict[str, Any]:
    """Las etapas que faltan, en orden, con su punto de control (RF-43, RF-44)."""
    datos = {**control.estado.get('datos', {}), **dict(datos)}
    for i, e in enumerate(etapas, 1):
        if control.hecha(e.nombre):
            log(f'Agente: etapa {i} de {len(etapas)}, {e.nombre}: ya hecha, no se repite (027:RF-44)')
            continue
        if cliente.cancelado():
            return {'completo': False, 'cancelado': True, 'etapas': control.estado['etapas']}
        faltan = [k for k in e.requiere if not datos.get(k)]
        if not faltan and e.tarea == 'obras' and not (cliente.pedir('GET', '/obras') or []):
            log('Agente: etapa obras omitida: no hay obras pendientes en el espacio')
            control.marcar(e.nombre, 'omitida', {'falta': ['obras pendientes']}, datos)
            continue
        if faltan:
            if not e.opcional:
                raise ValueError(f'la etapa {e.nombre} necesita {", ".join(faltan)}')
            log(f'Agente: etapa {e.nombre} omitida: falta {", ".join(faltan)}')
            control.marcar(e.nombre, 'omitida', {'falta': faltan}, datos)
            continue
        log(f'Agente: etapa {i} de {len(etapas)}, {e.nombre}…')
        datos_tarea = {**datos, 'ruta': datos.get('ruta_cargas') if e.tarea == 'cargas_nuevas' else datos.get('ruta')}
        if e.proceso:
            resultado = proceso(e.tarea, datos_tarea)
        else:
            extras = {'formulario': datos.get('formulario') or {}}
            resultado = ejecutar(pasos(e.tarea, datos_tarea, extras), cliente, log)
        datos = _datos_tras(e, datos, cliente)
        control.marcar(e.nombre, 'hecha', _resumen(resultado if not isinstance(resultado, dict)
                                                     else resultado.get('resultado', resultado)), datos)
    return {'completo': True, 'etapas': control.estado['etapas'], 'datos': datos}
