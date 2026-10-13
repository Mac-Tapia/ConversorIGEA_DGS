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
