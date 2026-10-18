"""Perfil de empresa: las convenciones de una distribuidora, fuera del código (spec 002).

El conversor es universal (constitución P13). Hasta la spec 002, tres convenciones de
Electro Dunas iban como valores por defecto: el CRS de Ica (UTM 18S), la exclusión
de las SED cuyo código empieza por ``M`` (sus «trafomix») y la escala del diagrama de
NA205. En otra empresa la primera desplazaba la red cientos de kilómetros sin aviso, y la
segunda borraba SED reales que se llamaran ``M…``.

Ahora cada una sale de un perfil (RF-31):

- ``config/perfil_empresa.json``, local y fuera de git, es el perfil activo. Puede dar los
  valores él mismo o heredar los de un perfil con nombre con ``"perfil": "<nombre>"``.
- ``config/perfiles/<nombre>.json`` son perfiles con nombre, en git, con convenciones y
  nunca datos de la red. ``electro_dunas.json`` es uno más (RF-35).

Sin perfil, nada se supone: sin CRS no se convierte con georreferenciación hasta que el
usuario lo elija (RF-32), y sin patrón no se excluye ninguna SED por su nombre (RF-33).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

#: Clave con la que el perfil activo hereda de un perfil con nombre.
CLAVE_BASE = 'perfil'
#: Claves de convención que este módulo valida; el resto (carpeta de DIgSILENT, límites
#: de los estudios) las leen sus módulos, del mismo fichero.
CLAVES = ('crs_origen', 'patron_sed_medicion', 'escala_diagrama', 'forma_alimentador',
          'patron_libro_clientes')
_NOMBRE_VALIDO = re.compile(r'^[a-z0-9_]+$')


class PerfilError(ValueError):
    """El perfil de empresa no se puede leer o trae un valor imposible."""


@dataclass(frozen=True)
class PerfilEmpresa:
    """Convenciones de una empresa. Un campo en None es «no se supone nada»."""

    nombre: str = ''
    crs_origen: str | None = None
    #: Expresión regular del código de las SED que son medición en MT y no SED reales.
    patron_sed_medicion: str | None = None
    #: Unidades de diagrama por metro; None deja la escala del motor.
    escala_diagrama: float | None = None
    #: Expresión regular que deben cumplir los nombres de alimentador; solo avisa.
    forma_alimentador: str | None = None
    #: Expresión regular con grupos «mes» y «anio» para los libros de clientes.
    patron_libro_clientes: str | None = None

    def __post_init__(self) -> None:
        for clave in ('patron_sed_medicion', 'forma_alimentador', 'patron_libro_clientes'):
            patron = getattr(self, clave)
            if patron is None:
                continue
            if not isinstance(patron, str) or not patron.strip():
                raise PerfilError(f'{clave} tiene que ser una expresión regular, no {patron!r}.')
            try:
                compilado = re.compile(patron)
            except re.error as exc:
                raise PerfilError(f'{clave} no es una expresión regular válida ({exc}): {patron!r}.') from exc
            if clave == 'patron_libro_clientes':
                faltan = {'mes', 'anio'} - set(compilado.groupindex)
                if faltan:
                    raise PerfilError(
                        f'{clave} debe tener grupos nombrados «mes» y «anio» '
                        f'(faltan: {", ".join(sorted(faltan))}).')
        if self.crs_origen is not None and (not isinstance(self.crs_origen, str)
                                            or not self.crs_origen.strip()):
            raise PerfilError(f'crs_origen tiene que ser un código como «EPSG:xxxxx», no {self.crs_origen!r}.')
        if self.escala_diagrama is not None:
            if isinstance(self.escala_diagrama, bool) or not isinstance(self.escala_diagrama, (int, float)):
                raise PerfilError(f'escala_diagrama tiene que ser un número, no {self.escala_diagrama!r}.')
            if not self.escala_diagrama > 0:
                raise PerfilError(f'escala_diagrama tiene que ser mayor que 0: {self.escala_diagrama}.')

    def valores(self) -> dict[str, Any]:
        """El perfil tal como se registra en el manifiesto del lote (RF-37)."""
        return asdict(self)

    def nombre_fuera_de_forma(self, nombres: list[str]) -> list[str]:
        """Nombres de alimentador que no cumplen ``forma_alimentador`` (vacío sin forma)."""
        if not self.forma_alimentador:
            return []
        forma = re.compile(self.forma_alimentador)
        return [n for n in nombres if not forma.fullmatch(n)]


#: Sin perfil: ninguna convención supuesta.
SIN_PERFIL = PerfilEmpresa()


def _raiz() -> Path:
    from .powerfactory_env import project_root

    return project_root()


#: Variable de entorno con otra ruta del perfil activo. Las pruebas la apuntan a un
#: fichero que no existe: si leyeran el perfil de la máquina, darían otro resultado en
#: cada equipo.
VARIABLE_RUTA = 'IGEA_PERFIL_EMPRESA'


def ruta_perfil_activo() -> Path:
    import os

    otra = os.environ.get(VARIABLE_RUTA, '').strip()
    return Path(otra) if otra else _raiz() / 'config' / 'perfil_empresa.json'


def carpeta_perfiles() -> Path:
    return _raiz() / 'config' / 'perfiles'


def perfiles_disponibles(carpeta: Path | None = None) -> list[str]:
    """Nombres de los perfiles de ``config/perfiles``, ordenados."""
    carpeta = carpeta_perfiles() if carpeta is None else Path(carpeta)
    if not carpeta.is_dir():
        return []
    return sorted(p.stem for p in carpeta.glob('*.json') if _NOMBRE_VALIDO.match(p.stem))


def _leer_json(ruta: Path) -> dict[str, Any]:
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise PerfilError(f'No se pudo leer el perfil de empresa {ruta.name}: {exc}') from exc
    if not isinstance(datos, dict):
        raise PerfilError(f'El perfil de empresa {ruta.name} debe ser un objeto JSON.')
    return datos


def _construir(nombre: str, datos: dict[str, Any], origen: str) -> PerfilEmpresa:
    try:
        return PerfilEmpresa(nombre=nombre, **{k: datos[k] for k in CLAVES if k in datos})
    except PerfilError as exc:
        raise PerfilError(f'{exc} (perfil {origen})') from exc


def perfil_con_nombre(nombre: str, carpeta: Path | None = None) -> PerfilEmpresa:
    """El perfil ``config/perfiles/<nombre>.json``."""
    if not isinstance(nombre, str) or not _NOMBRE_VALIDO.match(nombre):
        raise PerfilError(f'Nombre de perfil no válido: {nombre!r} (minúsculas, cifras y «_»).')
    carpeta = carpeta_perfiles() if carpeta is None else Path(carpeta)
    ruta = carpeta / f'{nombre}.json'
    if not ruta.is_file():
        disponibles = ', '.join(perfiles_disponibles(carpeta)) or 'ninguno'
        raise PerfilError(f'No existe el perfil de empresa «{nombre}» (disponibles: {disponibles}).')
    return _construir(nombre, _leer_json(ruta), ruta.name)


def crs_o_perfil(crs: str | None) -> str | None:
    """``crs`` si se indicó; si no, el del perfil activo; None si ninguno lo da."""
    return crs or cargar_perfil().crs_origen


def cargar_perfil(ruta: Path | None = None, *, carpeta: Path | None = None) -> PerfilEmpresa:
    """El perfil activo: ``config/perfil_empresa.json`` sobre el perfil del que hereda.

    Sin fichero, :data:`SIN_PERFIL`. Una clave del perfil activo pisa la heredada; una
    clave puesta a ``null`` la anula, para no heredar una convención que no aplica.
    """
    ruta = ruta_perfil_activo() if ruta is None else Path(ruta)
    if not ruta.is_file():
        return SIN_PERFIL
    datos = _leer_json(ruta)
    base = datos.get(CLAVE_BASE)
    if base is None:
        return _construir('', datos, ruta.name)
    heredado = perfil_con_nombre(base, carpeta)
    valores = {k: v for k, v in heredado.valores().items() if k in CLAVES}
    valores.update({k: datos[k] for k in CLAVES if k in datos})
    return _construir(heredado.nombre, valores, ruta.name)


def factor_potencia_cargas(datos: dict[str, Any],
                           clave: str = 'factor_potencia_cargas') -> float | None:
    """Un factor de potencia de la sección ``calibracion`` del perfil (015:RF-57), o None.

    ``factor_potencia_cargas``: el de las SED escaladas (RF-54); ``factor_potencia_minimo_fijas``:
    el mínimo de los clientes fijos, compensados por su banco propio (RF-62). Electro Dunas
    pide 0,98 en los dos (2026-10-15). Sin la clave no se supone nada (RF-55).
    """
    valor = (datos.get('calibracion') or {}).get(clave)
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not 0 < valor <= 1:
        raise PerfilError(f'calibracion.{clave} tiene que estar entre 0 (sin incluirlo) y 1, '
                          f'no {valor!r}.')
    return float(valor)


def bancos_kvar_por_tension(datos: dict[str, Any]) -> dict[float, float] | None:
    """El tamaño de banco por tensión de ``calibracion.bancos_kvar_por_tension`` (021:RF-65).

    Electro Dunas: 300 kvar en 10 kV y 450 kvar en 22,9 kV, los mismos de los bancos nuevos
    del informe de estudio. Sin la clave, ``None``: no se supone ninguno (P13).
    """
    valor = (datos.get('calibracion') or {}).get('bancos_kvar_por_tension')
    if valor is None:
        return None
    if not isinstance(valor, dict) or not valor:
        raise PerfilError('calibracion.bancos_kvar_por_tension tiene que ser {"kV": kvar, ...}.')
    out = {}
    for kv, kvar in valor.items():
        try:
            tension = float(str(kv).replace(',', '.'))
        except ValueError as exc:
            raise PerfilError(f'calibracion.bancos_kvar_por_tension: {kv!r} no es una tensión en kV.') from exc
        if tension <= 0 or not _positivo(kvar):
            raise PerfilError(f'calibracion.bancos_kvar_por_tension: {kv!r} → {kvar!r} tiene que '
                              'ser positivo.')
        out[tension] = float(kvar)
    return out


def _positivo(v: Any) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and v > 0


def transformadores_sed(datos: dict[str, Any]) -> dict[str, Any] | None:
    """Las fichas de transformadores de ``calibracion.transformadores_sed`` (020:RF-29 a RF-31).

    Con ellas se proponen transformadores nuevos para las SED fijas sobrecargadas. En PA217
    (2026-10-16) SE30940 pedía 3818 kVA sobre 400 kVA y hubo que buscar a mano la ficha de
    la NTP 370.400; la norma es de Perú, así que va en el perfil y no en el código (P13).
    Devuelve ``None`` sin la sección; si no, el umbral, las tablas válidas (``fichas`` por
    kVA, ``(po_w, pc_w, io_pct, uk_pct)``) y un aviso por cada fila o tabla descartada.
    """
    seccion = (datos.get('calibracion') or {}).get('transformadores_sed')
    if seccion is None:
        return None
    umbral = seccion.get('umbral_carga_pct')
    if not _positivo(umbral) or umbral > 100:
        raise PerfilError('calibracion.transformadores_sed.umbral_carga_pct tiene que estar '
                          f'entre 0 (sin incluirlo) y 100, no {umbral!r}.')
    perfil = datos.get(CLAVE_BASE) or 'activo'
    tablas, avisos = [], []
    for n, tabla in enumerate(seccion.get('tablas') or [], 1):
        norma = str(tabla.get('norma') or f'tabla {n}')
        kv_min, kv_max = tabla.get('kv_min'), tabla.get('kv_max')
        if (isinstance(kv_min, bool) or not isinstance(kv_min, (int, float)) or kv_min < 0
                or not _positivo(kv_max) or kv_max <= kv_min):
            avisos.append(f'perfil {perfil}: la tabla «{norma}» no tiene un rango de tensión '
                          f'primaria válido ({kv_min!r} a {kv_max!r} kV); no se usa.')
            continue
        fichas = {}
        for kva, fila in (tabla.get('fichas') or {}).items():
            try:
                potencia = float(kva)
            except (TypeError, ValueError):
                potencia = None
            if (potencia is None or potencia <= 0 or not isinstance(fila, list)
                    or len(fila) != 4 or not all(_positivo(v) for v in fila)):
                avisos.append(f'perfil {perfil}: la fila {kva!r} de la tabla «{norma}» tiene que '
                              f'ser [Po W, Pc W, Io %, uk %] positivos, no {fila!r}; no se usa.')
                continue
            fichas[int(potencia) if potencia.is_integer() else potencia] = tuple(fila)
        if not fichas:
            avisos.append(f'perfil {perfil}: la tabla «{norma}» no tiene ninguna fila válida; '
                          'no se usa.')
            continue
        tablas.append({'norma': norma, 'codigo': str(tabla.get('codigo') or ''),
                       'kv_min': kv_min, 'kv_max': kv_max, 'fichas': dict(sorted(fichas.items()))})
    return {'umbral_carga_pct': umbral, 'tablas': tablas, 'avisos': avisos}


#: Medidores de una central térmica en un tramo de un alimentador (021:RF-25, RF-27).
CAMPOS_CENTRAL = ('generacion', 'llegada', 'salida')


def centrales_termicas(datos: dict[str, Any]) -> dict[str, dict[str, str]]:
    """La sección ``centrales_termicas`` del perfil: ``{alimentador: {generacion, llegada,
    salida, nodo}}`` (021:RF-27), o vacía.

    NA205 tiene en su troncal la central de Nasca, y el libro de medidores la trae como
    tres «alimentadores» que no son de la red (CTBarra, CTLADOSET, CTLADOCARGA). Es un
    dato de la red de la empresa, no una convención: va en el perfil local. ``nodo`` es
    optativo: el nombre de la barra en DIgSILENT cambia con cada proyecto importado.
    """
    seccion = datos.get('centrales_termicas')
    if seccion is None:
        return {}
    if not isinstance(seccion, dict):
        raise PerfilError('centrales_termicas tiene que ser un objeto {alimentador: {generacion, '
                          f'llegada, salida, nodo}}, no {seccion!r}.')
    out = {}
    for alimentador, central in seccion.items():
        if not isinstance(central, dict):
            raise PerfilError(f'centrales_termicas.{alimentador} tiene que ser un objeto, no {central!r}.')
        faltan = [c for c in CAMPOS_CENTRAL if not str(central.get(c) or '').strip()]
        if faltan:
            raise PerfilError(f'centrales_termicas.{alimentador}: falta el medidor de '
                              f'{", ".join(faltan)}.')
        out[str(alimentador).strip()] = {
            **{c: str(central[c]).strip() for c in CAMPOS_CENTRAL},
            'nodo': str(central.get('nodo') or '').strip(),
        }
    return out


def datos_perfil(ruta: Path | None = None, *, carpeta: Path | None = None) -> dict[str, Any]:
    """Todas las claves del perfil activo, con la herencia resuelta.

    :func:`cargar_perfil` solo valida las convenciones de la conversión; las secciones de
    otros módulos (``informes`` de la spec 017) también se heredan del perfil con nombre,
    para que las bandas de Electro Dunas no haya que copiarlas al perfil local. Una clave
    del perfil activo pisa la heredada entera.
    """
    ruta = ruta_perfil_activo() if ruta is None else Path(ruta)
    if not ruta.is_file():
        return {}
    datos = _leer_json(ruta)
    base = datos.get(CLAVE_BASE)
    if base is None:
        return datos
    perfil_con_nombre(base, carpeta)   # valida el nombre y que exista
    carpeta = carpeta_perfiles() if carpeta is None else Path(carpeta)
    heredados = _leer_json(carpeta / f'{base}.json')
    return {**heredados, **datos}


def estructura_empresa(ruta: Path | None = None, *, carpeta: Path | None = None):
    """La estructura zonal → SET → alimentadores del perfil activo, o ``None`` (022:RF-1, RF-6).

    El JSON aparte que nombra ``estructura`` se busca junto al perfil activo y, si no está,
    junto a los perfiles con nombre: el local de Electro Dunas solo dice
    ``{"perfil": "electro_dunas"}`` y la tabla va en ``config/perfiles``.
    """
    from .estructura import EstructuraError, estructura_de_perfil

    datos = datos_perfil(ruta, carpeta=carpeta)
    valor = datos.get('estructura')
    if valor is None:
        return None
    activo = ruta_perfil_activo() if ruta is None else Path(ruta)
    base = carpeta_perfiles() if carpeta is None else Path(carpeta)
    if isinstance(valor, str) and not (activo.parent / valor).is_file():
        activo = base / 'x.json'
    try:
        return estructura_de_perfil(datos, activo.parent)
    except EstructuraError as exc:
        raise PerfilError(str(exc)) from exc
