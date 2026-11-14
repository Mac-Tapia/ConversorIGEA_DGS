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

import hashlib
import json
import re
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .experimentos import ContextoExperimento, clave_contexto, como_datos


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


# --------------------------------------------------------------------------- ficheros de ajustes (RF-2)
#: Cómo nombran cada campo los ficheros de ajustes de relés y reconectadores, en español y en inglés, y los ajustes
#: estilo SEL (``51P1P := 2.50``). Va en minúsculas y sin tildes; manda el primero que aparece en el fichero.
ETIQUETAS_AJUSTE: dict[str, tuple[str, ...]] = {
    'id': ('identificador', 'id del equipo', 'equipo', 'dispositivo', 'device id', 'relay id', 'rid', 'tid'),
    'fabricante': ('fabricante', 'manufacturer', 'marca', 'vendor'),
    'modelo': ('modelo', 'model', 'tipo de rele', 'relay type', 'fid'),
    'curva': ('curva', 'curve', 'caracteristica', 'characteristic', '51p1c', '51pc', 'tcc'),
    'arranque': ('arranque', 'pickup', 'pick-up', 'pick up', 'corriente de ajuste', '51p1p', '51pp'),
    'dial': ('dial', 'tms', 'time dial', 'multiplicador de tiempo', '51p1td', '51ptd'),
    'poder_corte_ka': ('poder de corte', 'capacidad de interrupcion', 'breaking capacity', 'interrupting rating',
                       'icu'),
    'cubiculo': ('cubiculo', 'cubicle', 'celda', 'bahia', 'bay'),
}
#: Un TC escrito como «600/5» junto a TC, CT o RTC.
_TC = re.compile(r'\b(?:t\.?c\.?|c\.?t\.?|rtc|ctr|relacion\s+(?:de\s+)?tc)\b[^0-9\n]{0,20}(\d+(?:[.,]\d+)?)\s*/\s*(1|5)\b')
_NUMERO = re.compile(r'[-+]?\d+(?:[.,]\d+)?')


def _sin_tildes(texto: str) -> str:
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()


def _valor_de_linea(linea: str, etiqueta: str) -> str | None:
    """Lo que sigue a la etiqueta en la línea: tras «:=», «=», «:» o espacios. ``None`` si la etiqueta no está."""
    m = re.search(rf'(?<![\w>]){re.escape(etiqueta)}(?![\w>])\s*(?::=|=|:|\s)\s*(.+)$', linea, re.IGNORECASE)
    return m.group(1).strip() if m else None


def leer_ajustes(texto: str, fichero: str, cubiculo: str | None = None) -> dict[str, Any]:
    """Un dispositivo de protección leído de su fichero de ajustes, con lo que falta para el estudio (049:RF-2).

    Usuario (2026-11-13): en Protecciones se cargan los TXT y PDF de ajustes del relé y del reconectador del alimentador
    en análisis, como se cargan los PDF de la solicitud. Nada se da por bueno: lo leído se confirma en la web y lo que
    falta lo dice :func:`validar_dispositivo`. Los ficheros cambian por fabricante; las etiquetas son las de
    :data:`ETIQUETAS_AJUSTE`, y una que no se reconoce queda vacía, no adivinada.
    """
    lineas = [_sin_tildes(l) for l in texto.splitlines() if l.strip()]
    originales = [l.strip() for l in texto.splitlines() if l.strip()]
    d: dict[str, Any] = {'fuente': fichero}
    for campo, etiquetas in ETIQUETAS_AJUSTE.items():
        for i, linea in enumerate(lineas):
            valor = next((v for e in etiquetas if (v := _valor_de_linea(linea, e))), None)
            if valor is None:
                continue
            if campo in ('arranque', 'dial', 'poder_corte_ka'):
                n = _NUMERO.search(valor)
                if n is None:
                    continue
                d[campo] = float(n.group(0).replace(',', '.'))
                if campo == 'arranque':
                    d['unidad_arranque'] = 'A sec' if re.search(r'\bsec|\ba\s*sec|secundari', valor) else 'A'
                if campo == 'poder_corte_ka' and re.search(r'\d\s*a\b(?!\s*sec)', valor) and d[campo] > 200:
                    d[campo] = d[campo] / 1000.0          # escrito en amperios
            else:
                # El texto como venía, sin pasarlo a minúsculas: el modelo y el fabricante se escriben así.
                bruto = _valor_de_linea(originales[i], next(e for e in etiquetas if _valor_de_linea(linea, e)))
                d[campo] = (bruto if bruto is not None else valor).strip().strip('"\'')
            break
    todo = '\n'.join(lineas)
    tc = _TC.search(todo)
    if tc:
        d['ct_primario_a'], d['ct_secundario_a'] = float(tc.group(1).replace(',', '.')), float(tc.group(2))
    if 'dial' in d:
        d['unidad_dial'] = 's' if re.search(r'tiempo definido|definite time|\bdt\b', todo) else 'dial'
    clase = ('reconectador' if re.search(r'reconectador|recloser', todo)
             else 'fusible' if re.search(r'\bfusible\b|\bfuse\b', todo) else 'rele')
    d['clase'] = clase
    if cubiculo and not d.get('cubiculo'):
        d['cubiculo'] = cubiculo
    if not d.get('id'):
        d['id'] = Path(fichero).stem
    faltan, errores = validar_dispositivo(d)
    return {'dispositivo': d, 'faltan': faltan, 'errores': errores,
            'leidos': sorted(k for k in d if k not in ('fuente',))}


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


# --------------------------------------------------------------------------- plan de fallas (RF-4, RF-8)
#: Esquema del plan que lee ``tools/protecciones_pf.py``.
ESQUEMA_PLAN = 'convertersmartgrid-protecciones-plan-v1'
#: Tipos de falla: ``iopt_shc`` que se escribe y código que devuelve ``ComShc.GetFaultType``
#: (referencia de Python 2024, 5.4.43), con el que el guion relee lo que quedó configurado.
TIPOS_FALLA: dict[str, tuple[str, int]] = {'trifasica': ('3psc', 0), 'monofasica': ('spgf', 1),
                                           'bifasica': ('2psc', 2), 'bifasica_tierra': ('2pgf', 3)}
#: Las que circulan por tierra: piden secuencia cero y puesta a tierra reales.
A_TIERRA = ('monofasica', 'bifasica_tierra')
FASES = ('a', 'b', 'c')
#: Clases de PowerFactory que aportan corriente de falla; una central como carga negativa no.
GENERACION_PF = ('ElmXnet', 'ElmSym', 'ElmGenstat', 'ElmAsm', 'ElmPvsys')
#: Prefijo de la variación de los ajustes propuestos (049:RF-8).
VARIACION_AJUSTES = 'CSG049_ajustes'


def _falla(f: Mapping[str, Any], ids: set[str], a_tierra_ok: bool) -> tuple[dict[str, Any] | None, list[str]]:
    """Una falla del plan normalizada, o los motivos por los que no se puede plantear."""
    nombre = str(f.get('id') or f.get('ubicacion') or '(sin nombre)')
    errores = []
    tipo = f.get('tipo')
    if tipo not in TIPOS_FALLA:
        errores.append(f'falla «{nombre}»: el tipo «{tipo}» no es ninguno de ' + ', '.join(TIPOS_FALLA))
    if _vacio(f.get('ubicacion')):
        errores.append(f'falla «{nombre}»: falta la barra donde ocurre')
    fase = f.get('fase')
    if tipo == 'monofasica' and fase not in FASES:
        errores.append(f'falla «{nombre}»: una falla monofásica dice su fase (a, b o c), no «{fase}»')
    if tipo in A_TIERRA and not a_tierra_ok:
        errores.append(f'falla «{nombre}»: una falla a tierra pide la secuencia cero y la puesta a tierra '
                       'reales de la fuente, y la fuente trae las de por defecto')
    impedancia = {}
    for k in ('r_ohm', 'x_ohm'):
        v = f.get(k)
        if not _numero_valido(v) or v < 0:
            errores.append(f'falla «{nombre}»: {k} tiene que ser un número de ohmios ≥ 0, no {v!r} '
                           '(una falla franca es 0)')
        else:
            impedancia[k] = float(v)
    protegen = [str(x) for x in f.get('protegen') or ()]
    errores += [f'falla «{nombre}»: «{x}» no es un dispositivo del inventario' for x in protegen if x not in ids]
    if errores:
        return None, errores
    return {'id': nombre, 'tipo': tipo, 'iopt_shc': TIPOS_FALLA[tipo][0], 'codigo_tipo': TIPOS_FALLA[tipo][1],
            'ubicacion': str(f['ubicacion']).strip(), 'fase': fase if tipo == 'monofasica' else None,
            **impedancia, 'escenario': f.get('escenario') or None, 'protegen': protegen}, []


def _aportes(generacion: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """La generación del caso tal como está, con su estado (049:RF-4).

    Una central que el modelo tiene como carga negativa no aporta corriente de falla: se
    rechaza en vez de dejar que el cortocircuito salga menor de lo que es (Chincha tenía su
    térmica como generador; una red de otra empresa puede no tenerla).
    """
    aportes, errores = [], []
    for g in generacion:
        nombre = str(g.get('nombre') or '')
        if g.get('modelo') == 'carga_negativa':
            errores.append(f'«{nombre}» es una central como carga negativa: no aporta corriente de falla; '
                           'hace falta su modelo de generador (' + ', '.join(GENERACION_PF[1:3]) + ')')
            continue
        if g.get('clase') not in GENERACION_PF:
            errores.append(f'«{nombre}» ({g.get("clase")}) no es una clase de generación de DIgSILENT')
            continue
        aportes.append({'nombre': nombre, 'clase': g['clase'], 'en_servicio': bool(g.get('en_servicio'))})
    return sorted(aportes, key=lambda a: (a['clase'], a['nombre'])), errores


def plan_protecciones(contexto: ContextoExperimento, inventario: Mapping[str, Any],
                      fallas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """El plan de fallas que ejecuta ``tools/protecciones_pf.py`` (049:RF-4, RF-8).

    Lleva la identidad del caso vinculado (``ContextoExperimento``), cada falla con su barra,
    tipo, fase e impedancia, la generación del caso con sus estados —sin sustituirla por
    demanda— y los ajustes propuestos, que solo se escriben en una variación aparte. Rechaza,
    con la lista entera, un dispositivo sin unidad o sin relación de TC, una falla mal planteada
    o un ajuste sobre el «Caso base».
    """
    if not isinstance(contexto, ContextoExperimento):
        raise ProteccionesError('el plan de protecciones pide el contexto del caso vinculado')
    errores: list[str] = []
    dispositivos = [dict(d) for d in inventario.get('dispositivos') or ()]
    for d in dispositivos:
        faltan, malos = validar_dispositivo(d)
        errores += faltan + malos
    ids = {str(d.get('id')) for d in dispositivos}
    if not dispositivos:
        errores.append('el plan no tiene dispositivos de protección')
    planteadas = []
    for f in fallas:
        falla, e = _falla(f, ids, bool(inventario.get('impedancia_real')))
        errores += e
        if falla is not None:
            planteadas.append(falla)
    if not fallas:
        errores.append('el plan no tiene ninguna falla')
    if len({f['id'] for f in planteadas}) != len(planteadas):
        errores.append('dos fallas tienen el mismo nombre')
    aportes, e = _aportes(inventario.get('generacion') or ())
    errores += e
    ajustes = [dict(a) for a in inventario.get('ajustes') or ()]
    if ajustes and contexto.case_role == 'caso_base':
        errores.append('el «Caso base» es la referencia: los ajustes propuestos van a una variación de '
                       '«Sin proyecto» o «Con proyecto»')
    for a in ajustes:
        if str(a.get('dispositivo')) not in ids:
            errores.append(f'ajuste sobre «{a.get("dispositivo")}», que no es un dispositivo del inventario')
        if _vacio(a.get('atributo')) or _vacio(a.get('unidad')):
            errores.append(f'ajuste de «{a.get("dispositivo")}»: dice su atributo de DIgSILENT y su unidad')
    atributos = ((inventario.get('capacidades') or {}).get('comandos') or {}).get('ComShc', {}).get('atributos') or {}
    sin_comprobar = [a for a in ATRIBUTOS_COMSHC.values() if not atributos.get(a)]
    if sin_comprobar:
        errores.append('ComShc no tiene comprobados en DIgSILENT los atributos ' + ', '.join(sin_comprobar)
                       + ': ejecute antes «Comprobar capacidades»')
    if errores:
        raise ProteccionesError('El estudio de protecciones no se puede plantear:\n' + '\n'.join(errores))
    publico = como_datos(contexto)
    return {'schema': ESQUEMA_PLAN, 'contexto': publico, 'clave_contexto': clave_contexto(contexto),
            'project': contexto.project, 'feeders': list(contexto.feeders), 'caso': contexto.case_id,
            'rol': contexto.case_role, 'anio': contexto.year,
            'fallas': sorted(planteadas, key=lambda f: f['id']),
            'dispositivos': sorted(dispositivos, key=lambda d: str(d['id'])), 'aportes': aportes,
            'atributos_comshc': dict(ATRIBUTOS_COMSHC),
            'escritura': {'variacion': VARIACION_AJUSTES, 'solo_variacion': True,
                          'ajustes': sorted(ajustes, key=lambda a: (str(a['dispositivo']), str(a['atributo'])))}}


# --------------------------------------------------------------------------- coordinación (RF-5 a RF-7)
#: Estados del estudio publicado: ``parcial`` y ``bloqueado`` nunca se leen como aprobado (RF-7).
CUMPLE, NO_CUMPLE, PARCIAL, BLOQUEADO = 'cumple', 'no_cumple', 'parcial', 'bloqueado'
#: Aviso que acompaña a todo resultado en la web (049:RF-10).
AVISO_SELECTIVIDAD = ('Que el flujo de potencia converja no dice nada de la selectividad: la coordinación sale de '
                      'los tiempos de cada falla en DIgSILENT, comparados con los criterios del perfil.')


def arranque_primario_a(d: Mapping[str, Any]) -> float | None:
    """El arranque en amperios primarios, con la relación del TC si va en secundarios o en p.u."""
    arranque, unidad = d.get('arranque'), d.get('unidad_arranque')
    if not _numero_valido(arranque):
        return None
    if unidad == 'A':
        return float(arranque)
    prim, sec = d.get('ct_primario_a'), d.get('ct_secundario_a')
    if not (_numero_valido(prim) and _numero_valido(sec)) or sec <= 0:
        return None
    return float(arranque) * prim / sec if unidad == 'A sec' else float(arranque) * prim if unidad == 'pu' else None


def _parejas(dispositivos: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """``(primaria, respaldo)`` según ``respalda_a`` de cada dispositivo."""
    return sorted({(str(p), str(d['id'])) for d in dispositivos for p in d.get('respalda_a') or ()})


def evaluar_coordinacion(resultados: Sequence[Mapping[str, Any]], inventario: Mapping[str, Any],
                         perfil: Mapping[str, Any]) -> dict[str, Any]:
    """Coordinación, sensibilidad y poder de corte sobre los tiempos de DIgSILENT (049:RF-5 a RF-7).

    ``resultados`` son las fallas del informe de ``tools/protecciones_pf.py``. Para cada pareja
    primaria-respaldo y cada falla en que opera la primaria, ``t_respaldo − t_primaria`` tiene que
    llegar al CTI del perfil. Cada dispositivo que debe despejar una falla (``protegen``) tiene que
    verla con al menos el factor de sensibilidad por encima de su arranque, y su poder de corte
    tiene que superar la mayor corriente que vio por el margen del perfil. Lo que no se pudo juzgar
    —una falla no evaluada, un criterio que el perfil no da, una corriente que DIgSILENT no dio—
    va a ``no_evaluados`` con su razón, y entonces el estudio es ``parcial``, nunca ``cumple``.
    """
    criterios, _sin = criterios_de_perfil(perfil)
    dispositivos = {str(d['id']): d for d in inventario.get('dispositivos') or ()}
    parejas = _parejas(dispositivos.values())
    violaciones, no_evaluados, margenes, tiempos, fallas = [], [], [], [], []
    for clave, que in CRITERIOS.items():
        if clave not in criterios:
            no_evaluados.append({'que': f'todas las fallas: {que}', 'razon': f'el perfil no da protecciones.{clave}'})
    corriente_max: dict[str, float] = {}
    for r in sorted(resultados, key=lambda r: str(r.get('id'))):
        falla = str(r.get('id'))
        fallas.append({'id': falla, 'tipo': r.get('tipo'), 'ubicacion': r.get('ubicacion'), 'estado': r.get('estado'),
                       'motivo': r.get('motivo')})
        if r.get('estado') != 'evaluada':
            no_evaluados.append({'que': f'falla {falla}', 'razon': r.get('motivo') or 'DIgSILENT no la evaluó'})
            continue
        vistos = {str(d['id']): d for d in r.get('dispositivos') or ()}
        for ident, d in sorted(vistos.items()):
            tiempos.append({'falla': falla, 'dispositivo': ident, 'tiempo_s': d.get('tiempo_s'),
                            'corriente_a': d.get('corriente_a'), 'estado': d.get('estado')})
            if _numero_valido(d.get('corriente_a')):
                corriente_max[ident] = max(corriente_max.get(ident, 0.0), float(d['corriente_a']))
        protegen = [str(x) for x in r.get('protegen') or ()]
        if not protegen:
            no_evaluados.append({'que': f'falla {falla}: sensibilidad',
                                 'razon': 'la falla no dice qué dispositivos deben despejarla'})
        for ident in protegen:
            d = vistos.get(ident) or {}
            if d.get('tiempo_s') is None:
                violaciones.append({'tipo': 'no_opera', 'falla': falla, 'dispositivo': ident,
                                    'detalle': 'debe despejar la falla y no arrancó'})
                continue
            arranque = arranque_primario_a(dispositivos.get(ident) or {})
            corriente = d.get('corriente_a')
            if 'factor_sensibilidad' not in criterios:
                continue
            if arranque is None or not _numero_valido(corriente):
                no_evaluados.append({'que': f'falla {falla}: sensibilidad de {ident}',
                                     'razon': 'DIgSILENT no dio la corriente que ve' if arranque is not None
                                     else 'su arranque no se puede llevar a amperios primarios'})
            elif corriente / arranque < criterios['factor_sensibilidad']:
                violaciones.append({'tipo': 'sensibilidad', 'falla': falla, 'dispositivo': ident,
                                    'valor': corriente / arranque, 'limite': criterios['factor_sensibilidad']})
        for primaria, respaldo in parejas:
            tp = (vistos.get(primaria) or {}).get('tiempo_s')
            if tp is None or (protegen and primaria not in protegen):
                continue
            tr = (vistos.get(respaldo) or {}).get('tiempo_s')
            if tr is None:
                violaciones.append({'tipo': 'sin_respaldo', 'falla': falla, 'dispositivo': respaldo,
                                    'detalle': f'no respalda a {primaria} en esta falla'})
                continue
            margen = tr - tp
            margenes.append({'falla': falla, 'primaria': primaria, 'respaldo': respaldo, 't_primaria_s': tp,
                             't_respaldo_s': tr, 'margen_s': margen, 'cti_s': criterios.get('cti_s')})
            if 'cti_s' in criterios and margen < criterios['cti_s']:
                violaciones.append({'tipo': 'cti', 'falla': falla, 'dispositivo': respaldo, 'valor': margen,
                                    'limite': criterios['cti_s'], 'detalle': f'respaldo de {primaria}'})
    if 'margen_poder_corte' in criterios:
        for ident, d in sorted(dispositivos.items()):
            pc = d.get('poder_corte_ka')
            if ident not in corriente_max:
                no_evaluados.append({'que': f'poder de corte de {ident}',
                                     'razon': 'ninguna falla evaluada dio la corriente que ve'})
            elif not _numero_valido(pc) or pc <= 0:
                no_evaluados.append({'que': f'poder de corte de {ident}', 'razon': 'sin poder de corte de ficha'})
            elif pc * 1000.0 < corriente_max[ident] * criterios['margen_poder_corte']:
                violaciones.append({'tipo': 'poder_corte', 'falla': '', 'dispositivo': ident,
                                    'valor': corriente_max[ident] / 1000.0, 'limite': pc / criterios['margen_poder_corte']})
    evaluadas = sum(1 for f in fallas if f['estado'] == 'evaluada')
    estado = (NO_CUMPLE if violaciones else BLOQUEADO if not evaluadas else PARCIAL if no_evaluados else CUMPLE)
    clave_orden = (lambda v: (v['tipo'], str(v.get('falla')), v['dispositivo']))
    return {'estado': estado, 'criterios': criterios, 'dispositivos': sorted(dispositivos), 'fallas': fallas,
            'cobertura': {'fallas': len(fallas), 'evaluadas': evaluadas}, 'tiempos': tiempos, 'margenes': margenes,
            'violaciones': sorted(violaciones, key=clave_orden), 'no_evaluados': no_evaluados,
            'aviso': AVISO_SELECTIVIDAD}


COLUMNAS_TIEMPOS = ('falla', 'dispositivo', 'tiempo_s', 'corriente_a', 'estado')
COLUMNAS_MARGENES = ('falla', 'primaria', 'respaldo', 't_primaria_s', 't_respaldo_s', 'margen_s', 'cti_s')
COLUMNAS_VIOLACIONES = ('tipo', 'falla', 'dispositivo', 'valor', 'limite', 'detalle')


def escribir_reporte(evaluacion: Mapping[str, Any], carpeta: Path, nombre: str) -> dict[str, str]:
    """El JSON y los CSV del estudio, iguales byte a byte para la misma evaluación (049:RF-7)."""
    from .util import escribir_csv

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = {'json': carpeta / f'{nombre}.json'}
    rutas['json'].write_text(json.dumps(evaluacion, indent=2, ensure_ascii=False, sort_keys=True) + '\n',
                             encoding='utf-8')
    for clave, columnas in (('tiempos', COLUMNAS_TIEMPOS), ('margenes', COLUMNAS_MARGENES),
                            ('violaciones', COLUMNAS_VIOLACIONES)):
        rutas[clave] = escribir_csv(evaluacion.get(clave) or [], columnas, carpeta / f'{nombre}_{clave}.csv')
    return {k: str(v) for k, v in rutas.items()}


#: Campos del contexto que tienen que coincidir para comparar «Sin proyecto» con «Con proyecto».
_COMPATIBLES = ('project', 'feeders', 'source_fingerprint', 'source_mode', 'year', 'period', 'profile_hash')


def comparar_casos(sin: Mapping[str, Any], con: Mapping[str, Any]) -> dict[str, Any]:
    """Violaciones que aparecen o desaparecen con el proyecto, solo entre contextos compatibles.

    Dos evaluaciones de otra fuente, otro año u otro perfil no se comparan: la diferencia no sería
    del proyecto. Cada evaluación lleva el ``contexto`` de su plan.
    """
    a, b = sin.get('contexto') or {}, con.get('contexto') or {}
    distintos = [k for k in _COMPATIBLES if a.get(k) != b.get(k)]
    if distintos or a.get('case_role') != 'sin_proyecto' or b.get('case_role') != 'con_proyecto':
        raise ProteccionesError('no se comparan: ' + (('difieren ' + ', '.join(distintos)) if distintos
                                                      else 'hace falta una de «Sin proyecto» y otra de «Con proyecto»'))

    def claves(e):
        return {(v['tipo'], str(v.get('falla')), v['dispositivo']) for v in e.get('violaciones') or ()}

    antes, despues = claves(sin), claves(con)
    return {'nuevas': sorted(despues - antes), 'resueltas': sorted(antes - despues),
            'estado_sin': sin.get('estado'), 'estado_con': con.get('estado')}


#: Rol del caso por el nombre de los casos de estudio del conversor (spec 011, 025, 037).
ROLES_DE_CASO = {'Caso base': 'caso_base', 'Sin proyecto': 'sin_proyecto', 'Con proyecto': 'con_proyecto'}


def _sha(valor: Any) -> str:
    texto = json.dumps(como_datos(valor), sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str)
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def contexto_de_capacidades(firmado: Mapping[str, Any], capacidades: Mapping[str, Any], caso: str, periodo: str,
                            perfil: Mapping[str, Any], dispositivos: Iterable[Mapping[str, Any]]) -> ContextoExperimento:
    """La identidad del caso que se estudia, con lo que DIgSILENT dejó leer en el inventario.

    Proyecto, alimentadores y fuente salen del contexto nativo firmado de la acción; la topología
    de protecciones y la generación, del inventario de capacidades; los controles, de los ajustes
    de los dispositivos. Así una evaluación de otro caso, otro año u otro perfil no se compara con
    esta (``comparar_casos``).
    """
    rol = ROLES_DE_CASO.get(caso) or ('cargas_nuevas' if caso.startswith('Cargas nuevas') else None)
    if rol is None:
        raise ProteccionesError(f'«{caso}» no es un caso de estudio del conversor')
    anio = next((int(p) for p in caso.split() if p.isdigit() and len(p) == 4), None)
    fuente = firmado.get('source') or {}
    try:
        return ContextoExperimento(
            source_run_id=fuente.get('source_run_id'), source_mode=fuente.get('source_mode'),
            source_fingerprint=fuente.get('source_fingerprint'), project=str(firmado.get('project') or ''),
            feeders=tuple(firmado.get('feeders') or ()), case_id=caso, case_role=rol, year=anio,
            period=str(periodo or ''), criterio_fijas='no_aplica', profile_hash=_sha(perfil),
            topology_hash=_sha(capacidades.get('clases') or {}),
            controls_hash=_sha(sorted((dict(d) for d in dispositivos), key=lambda d: str(d.get('id')))),
            scenario_hash=_sha(capacidades.get('generacion') or []))
    except (TypeError, ValueError) as exc:
        raise ProteccionesError(f'el caso «{caso}» no tiene identidad completa: {exc}') from exc
