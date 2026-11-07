"""Estudio de protecciones: disponibilidad, contrato de ajustes, fallas y coordinación (spec 049).

El catálogo de estudios nombraba ``ComProtgraphic`` y con eso parecía que la coordinación era
cuestión de pulsar un botón. No lo es: la referencia de Python de PowerFactory 2024 documenta
``ComProtgraphic`` solo para refrescar páginas de gráficos (``AddToUpdatePages``), y ninguna
fuente trae los ajustes. El TXT de CYMDIST trae en FUSE, RECLOSER, BREAKER y RELAY una única
fila ``DEFAULT`` con ``InterruptingRating = 0``; la base Access y el VNR-GIS no traen curvas.
Un flujo que converge no dice nada de la selectividad (049:RF-10).

Por eso este módulo separa:

- **la disponibilidad** (RF-1, RF-2): qué falta, dispositivo por dispositivo y campo por campo,
  y qué no se comprobó en la versión y la licencia de DIgSILENT conectadas. Nada se supone de
  la versión por lo que anuncie el fabricante para otra;
- **el contrato de cada ajuste** (RF-3), en ``schemas/protecciones_v1.schema.json``, con su
  modelo, sus unidades y de qué libro, hoja y fila sale;
- **el plan de fallas** (RF-4, RF-8) que ejecuta ``tools/protecciones_pf.py`` con la generación
  y los estados del caso vinculado, y con los ajustes propuestos solo en una variación;
- **la coordinación** (RF-5 a RF-7) sobre los tiempos que devuelve DIgSILENT: CTI entre
  primaria y respaldo, sensibilidad y poder de corte, con las fallas no evaluadas a la vista.

CTI, factor de sensibilidad y margen de poder de corte salen del perfil de empresa
(``protecciones`` en ``config/perfil_empresa.json``); sin el dato, esa comprobación queda
bloqueada y se dice (constitución P13).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


class ProteccionesError(ValueError):
    """Datos o plan de protecciones que no se pueden usar; el mensaje es para el operador."""


def _esquema() -> dict[str, Any]:
    ruta = Path(__file__).resolve().parent / 'schemas' / 'protecciones_v1.schema.json'
    return json.loads(ruta.read_text(encoding='utf-8'))


_DISPOSITIVO = _esquema()['$defs']['dispositivo']
_PROPIEDADES = _DISPOSITIVO['properties']

#: Campos sin los que un dispositivo no entra al estudio (049:RF-2), los del esquema.
CAMPOS_OBLIGATORIOS: tuple[str, ...] = tuple(_DISPOSITIVO['required'])
#: Clases de dispositivo con su nombre para el operador.
CLASES: dict[str, str] = dict(_PROPIEDADES['clase']['x-titulos'])
#: Clase de PowerFactory que modela cada una: sin ella en el proyecto no hay curva que operar.
CLASE_PF: dict[str, str] = dict(_PROPIEDADES['clase']['x-clase-pf'])
#: Las que llevan dial o retardo; el fusible opera por su curva y su corriente nominal.
CON_DIAL: tuple[str, ...] = tuple(_DISPOSITIVO['x-con-dial'])
UNIDADES_ARRANQUE: tuple[str, ...] = tuple(_PROPIEDADES['unidad_arranque']['enum'])
UNIDADES_DIAL: tuple[str, ...] = tuple(_PROPIEDADES['unidad_dial']['enum'])
DIRECCIONES: tuple[str, ...] = tuple(_PROPIEDADES['direccion']['enum'])
#: Campos que pasan a ser obligatorios según el valor de otro (TC con arranque secundario, TT
#: con dirección): ``{campo: {valor: (campos, …)}}``.
REQUIERE: dict[str, dict[str, tuple[str, ...]]] = {
    campo: {valor: tuple(otros) for valor, otros in _PROPIEDADES[campo]['x-requiere'].items()}
    for campo in ('unidad_arranque', 'direccion')}
_NUMEROS = tuple(k for k, v in _PROPIEDADES.items() if v.get('type') == 'number')
_TITULO_CAMPO = {
    'id': 'el identificador', 'cubiculo': 'el cubículo', 'clase': 'la clase', 'fabricante': 'el fabricante',
    'modelo': 'el modelo', 'curva': 'la curva tiempo-corriente', 'arranque': 'el arranque (pickup)',
    'unidad_arranque': 'la unidad del arranque', 'dial': 'el dial o retardo', 'unidad_dial': 'la unidad del dial',
    'ct_primario_a': 'el primario del TC', 'ct_secundario_a': 'el secundario del TC',
    'vt_primario_kv': 'el primario del TT', 'vt_secundario_v': 'el secundario del TT',
    'direccion': 'la dirección', 'poder_corte_ka': 'el poder de corte', 'fuente': 'la fuente documental'}

#: Tablas del catálogo de equipos de una fuente que nombran protecciones (las del TXT).
TABLAS_FUENTE = ('FUSE', 'RECLOSER', 'BREAKER', 'RELAY')

#: Órdenes que el estudio usa, y los métodos de la referencia de Python de PowerFactory 2024
#: (cap. 5.4) que el guion llama: el cortocircuito y su traza, que da el tiempo de cada
#: dispositivo (``GetDeviceTime``) y cuáles dispararon o arrancaron, sin adivinar nombres de
#: variables de resultado.
COMANDOS_REQUERIDOS: tuple[str, ...] = ('ComShc', 'ComShctrace')
METODOS_REQUERIDOS: dict[str, tuple[str, ...]] = {
    'ComShc': ('GetFaultType',),
    'ComShctrace': ('ExecuteInitialStep', 'ExecuteNextStep', 'NextStepAvailable', 'GetDeviceTime',
                    'GetTrippedDevices', 'GetStartedDevices'),
}
#: Órdenes cuya licencia se prueba ejecutándolas en el modo de capacidades; la de la traza
#: solo se prueba con una falla configurada, y la da la ejecución del plan.
LICENCIA_PREVIA: tuple[str, ...] = ('ComShc',)
#: Atributos de ``ComShc`` que el guion escribe para definir cada falla. La referencia de Python
#: no los lista (solo ``Rf`` y ``Xf``, en ``ExecuteRXSweep``): son candidatos que el modo de
#: capacidades comprueba con ``HasAttribute`` en la versión conectada antes de usarlos, y el
#: tipo se relee con ``GetFaultType``, que sí está documentado.
ATRIBUTOS_COMSHC: dict[str, str] = {'ubicacion': 'shcobj', 'tipo': 'iopt_shc', 'r_ohm': 'Rf', 'x_ohm': 'Xf',
                                    'seleccion': 'iopt_allbus'}

#: Criterios del perfil de empresa (sección ``protecciones``), todos positivos.
CRITERIOS: dict[str, str] = {
    'cti_s': 'el intervalo de coordinación entre primaria y respaldo',
    'factor_sensibilidad': 'el factor mínimo entre la corriente de falla y el arranque',
    'margen_poder_corte': 'el margen mínimo entre el poder de corte y la corriente de falla',
}


# --------------------------------------------------------------------------- contrato (RF-3)
def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _numero_valido(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validar_dispositivo(d: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Lo que le falta a un dispositivo y lo que trae mal, con su identificador (RF-2, RF-3).

    Las faltas bloquean solo ese dispositivo; los errores son valores que el contrato no admite
    (una unidad que no es ninguna de las suyas): con ellos el tiempo saldría en otra magnitud.
    """
    nombre = str(d.get('id') or '(sin identificador)')
    faltan, errores = [], []
    clase = d.get('clase')
    requeridos = list(CAMPOS_OBLIGATORIOS)
    if clase in CON_DIAL:
        requeridos += ['dial', 'unidad_dial']
    for campo, por_valor in REQUIERE.items():
        requeridos += list(por_valor.get(str(d.get(campo)), ()))
    for campo in dict.fromkeys(requeridos):
        if _vacio(d.get(campo)):
            faltan.append(f'«{nombre}»: falta {_TITULO_CAMPO.get(campo, campo)}')
    if not _vacio(clase) and clase not in CLASES:
        errores.append(f'«{nombre}»: la clase «{clase}» no es ninguna de ' + ', '.join(CLASES.values()))
    for campo, admitidas in (('unidad_arranque', UNIDADES_ARRANQUE), ('unidad_dial', UNIDADES_DIAL),
                             ('direccion', DIRECCIONES)):
        v = d.get(campo)
        if not _vacio(v) and v not in admitidas:
            errores.append(f'«{nombre}»: {_TITULO_CAMPO[campo]} «{v}» no es ninguna de ' + ', '.join(admitidas))
    for campo in _NUMEROS:
        v = d.get(campo)
        if _vacio(v):
            continue
        if not _numero_valido(v):
            errores.append(f'«{nombre}»: {_TITULO_CAMPO[campo]} «{v}» no es un número')
        elif v < 0 or (v == 0 and 'exclusiveMinimum' in _PROPIEDADES[campo]):
            # Poder de corte cero es la fila DEFAULT de la fuente, no una ficha (049:RF-2).
            faltan.append(f'«{nombre}»: {_TITULO_CAMPO[campo]} es {v:g}, que no es un dato de ficha')
    return faltan, errores


def es_fila_por_defecto(fila: Mapping[str, Any]) -> bool:
    """La fila de catálogo que la fuente trae sin ficha: ``DEFAULT`` o poder de corte nulo."""
    if str(fila.get('ID') or fila.get('EquipmentId') or '').strip().upper() == 'DEFAULT':
        return True
    try:
        return not float(fila.get('InterruptingRating') or 0) > 0
    except (TypeError, ValueError):
        return True


def _filas(tabla: Any) -> list[Mapping[str, Any]]:
    filas = tabla.values() if hasattr(tabla, 'values') else (tabla or ())
    return [f for f in filas if isinstance(f, Mapping)]


def inventario_protecciones(libro: Any = None, *, tablas_fuente: Mapping[str, Any] | None = None,
                            impedancia_real: bool = False) -> dict[str, Any]:
    """Las entradas del estudio: los dispositivos del libro de la empresa y lo que trae la fuente.

    ``impedancia_real``: la potencia e impedancia de cortocircuito de cada cabecera es real, no
    el valor por defecto de la fuente (``studies``, entrada «impedancia»). Las filas de la fuente
    se cuentan aparte: una ``DEFAULT`` no es una ficha y no se convierte en dispositivo.
    """
    por_defecto = reales = 0
    for nombre in TABLAS_FUENTE:
        for fila in _filas((tablas_fuente or {}).get(nombre)):
            if es_fila_por_defecto(fila):
                por_defecto += 1
            else:
                reales += 1
    return {'dispositivos': [dict(d) for d in (getattr(libro, 'protecciones', None) or ())],
            'filas_fuente': {'por_defecto': por_defecto, 'reales': reales},
            'impedancia_real': impedancia_real}


def criterios_de_perfil(datos: Mapping[str, Any] | None) -> tuple[dict[str, float], list[str]]:
    """CTI y márgenes de la sección ``protecciones`` del perfil, y los que no da (049:RF-5, RF-6).

    Un valor imposible es un error, no se ignora: coordinar con un CTI negativo aprobaría
    cualquier pareja. Sin el dato no se supone ninguno.
    """
    seccion = (datos or {}).get('protecciones') or {}
    if not isinstance(seccion, Mapping):
        raise ProteccionesError('protecciones del perfil de empresa tiene que ser una sección {clave: valor}.')
    criterios, faltan = {}, []
    for clave, que in CRITERIOS.items():
        v = seccion.get(clave)
        if v is None:
            faltan.append(f'{que} (protecciones.{clave} del perfil de empresa)')
            continue
        if not _numero_valido(v) or v <= 0:
            raise ProteccionesError(f'protecciones.{clave} del perfil tiene que ser un número positivo, no {v!r}.')
        criterios[clave] = float(v)
    return criterios, faltan


def _bloqueos_de_capacidades(capacidades: Mapping[str, Any], funciones: Iterable[str],
                             clases_pf: Iterable[str]) -> list[str]:
    """Lo que la versión conectada no comprobó (049:RF-1); nada se supone por la versión."""
    if not capacidades:
        return ['no se ha comprobado en DIgSILENT la versión, la licencia ni los dispositivos del proyecto: '
                'ejecute «Comprobar capacidades» de Protecciones']
    version = str(capacidades.get('version') or 'de versión desconocida')
    comandos = capacidades.get('comandos') or {}
    bloqueos = []
    for clase in dict.fromkeys((*COMANDOS_REQUERIDOS, *funciones)):
        c = comandos.get(clase) or {}
        if not c.get('existe'):
            bloqueos.append(f'la orden {clase} no está en DIgSILENT {version}: una función anunciada para otra '
                            'versión no se supone en esta')
            continue
        if clase in LICENCIA_PREVIA and c.get('ejecuta') is None:
            bloqueos.append(f'la licencia de {clase} no se ha comprobado ejecutándola en DIgSILENT {version}')
        elif c.get('ejecuta') is False:
            bloqueos.append(f'la licencia de DIgSILENT {version} no incluye el módulo {clase}')
        metodos = c.get('metodos') or {}
        bloqueos += [f'{clase}.{m} no está en DIgSILENT {version}' for m in METODOS_REQUERIDOS.get(clase, ())
                     if not metodos.get(m)]
    atributos = (comandos.get('ComShc') or {}).get('atributos') or {}
    if (comandos.get('ComShc') or {}).get('existe'):
        bloqueos += [f'ComShc.{a} no se ha comprobado (HasAttribute) en DIgSILENT {version}'
                     for a in ATRIBUTOS_COMSHC.values() if not atributos.get(a)]
    modelos = capacidades.get('clases') or {}
    for clase_pf in dict.fromkeys(clases_pf):
        if not (modelos.get(clase_pf) or {}).get('cuantos'):
            bloqueos.append(f'el proyecto no tiene dispositivos {clase_pf} modelados en DIgSILENT {version}')
    return bloqueos


def disponibilidad_protecciones(inventario: Mapping[str, Any], capacidades: Mapping[str, Any],
                                perfil: Mapping[str, Any]) -> dict[str, Any]:
    """Si el estudio se puede hacer y, si no, la lista concreta de lo que falta (049:RF-1, RF-2).

    ``faltan`` son datos (dispositivos, campos, impedancia de la fuente, criterios del perfil);
    ``bloqueos``, lo que DIgSILENT no comprobó: orden, método, atributo, licencia o modelo del
    dispositivo en el proyecto. El alcance dice qué dispositivos entran completos.
    """
    dispositivos = list(inventario.get('dispositivos') or ())
    faltan: list[str] = []
    fuente = inventario.get('filas_fuente') or {}
    if not dispositivos:
        texto = 'los dispositivos de protección con su curva, ajustes y poder de corte (libro de la empresa, hoja «Protecciones»)'
        if fuente.get('por_defecto') and not fuente.get('reales'):
            texto += (f"; la fuente solo trae {fuente['por_defecto']} fila(s) DEFAULT con poder de corte 0, "
                      'que no son fichas')
        faltan.append(texto)
    completos, clases_pf, errores = [], [], []
    vistos: set[str] = set()
    modelos = (capacidades or {}).get('clases') or {}
    for d in dispositivos:
        f, e = validar_dispositivo(d)
        ident = str(d.get('id') or '')
        if ident and ident in vistos:
            e.append(f'«{ident}» está dos veces')
        vistos.add(ident)
        clase_pf = CLASE_PF.get(d.get('clase'))
        if clase_pf:
            clases_pf.append(clase_pf)
            nombres = (modelos.get(clase_pf) or {}).get('nombres')
            if capacidades and nombres is not None and ident and ident not in nombres:
                f.append(f'«{ident}» no está en el proyecto de DIgSILENT como {clase_pf}')
        faltan += f
        errores += e
        if not f and not e:
            completos.append(ident)
    faltan += errores
    if not inventario.get('impedancia_real'):
        faltan.append('la potencia e impedancia de cortocircuito real de cada subestación de cabecera '
                      '(la fuente trae el valor por defecto): sin ella las corrientes de falla no sirven')
    criterios, sin_criterio = criterios_de_perfil(perfil)
    faltan += sin_criterio
    bloqueos = _bloqueos_de_capacidades(capacidades or {}, inventario.get('funciones') or (), clases_pf)
    return {'disponible': not faltan and not bloqueos, 'faltan': faltan, 'bloqueos': bloqueos,
            'alcance': {'dispositivos': completos, 'incompletos': len(dispositivos) - len(completos),
                        'version': (capacidades or {}).get('version'), 'caso': (capacidades or {}).get('caso')},
            'criterios': criterios}
