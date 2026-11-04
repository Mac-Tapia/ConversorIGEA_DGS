"""Descubre, filtra y carga los módulos enchufables (002:RF-8 a RF-15, RF-23 a RF-30).

Son dos pasos porque un módulo externo no permitido no debe llegar a importarse (RF-23) y
porque los procesos hijos deben usar lo que decidió el principal (RF-29):
:func:`resolver` solo lee los metadatos instalados y da un resultado que se puede enviar a
otro proceso; :func:`cargar` importa lo resuelto. Un módulo roto nunca para al conversor:
queda fuera y dicho en el diagnóstico (RF-11, RF-26).
"""
from __future__ import annotations

import json
import tomllib
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any

from .puertos import PUERTOS, VERSION_PUERTOS, Modulo, metodos_que_faltan

GRUPO = 'convertersmartgrid.modulos'
#: La distribución cuyos módulos son internos y no piden permiso (RF-27).
DISTRIBUCION_PROPIA = 'convertersmartgrid'
#: Lista local de permitidos; no hay ninguna ruta web que la cambie (RF-24).
RUTA_PERMITIDOS = Path('config') / 'modulos_permitidos.json'


@dataclass(frozen=True)
class Declarado:
    """Un entry point instalado; solo textos, para que cruce entre procesos (RF-29)."""

    nombre: str
    valor: str
    distribucion: str


@dataclass(frozen=True)
class Resolucion:
    """Qué módulos se pueden cargar, ya en orden, y por qué quedaron fuera los demás."""

    declarados: tuple[Declarado, ...] = ()
    permitidos: tuple[str, ...] = ()
    diagnostico: tuple[str, ...] = ()


@dataclass
class Registro:
    """Los módulos cargados, por nombre, y todo lo que se dejó fuera."""

    modulos: dict[str, Modulo] = field(default_factory=dict)
    diagnostico: list[str] = field(default_factory=list)

    def del_puerto(self, puerto: str) -> list[Modulo]:
        return [m for m in self.modulos.values() if m.puerto == puerto]


def leer_permitidos(raiz: Path) -> tuple[frozenset[str], tuple[str, ...]]:
    """La lista de permitidos y su diagnóstico: sin lista o con una rota, ningún externo."""
    ruta = Path(raiz) / RUTA_PERMITIDOS
    if not ruta.is_file():
        return frozenset(), ()
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
        nombres = datos['permitidos']
        if not isinstance(nombres, list) or not all(isinstance(n, str) for n in nombres):
            raise TypeError('«permitidos» no es una lista de nombres')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return frozenset(), (f'{ruta.name}: no se pudo leer ({exc}); no se permite ningún módulo externo.',)
    return frozenset(nombres), ()


def _instalados() -> list[Declarado]:
    puntos: Iterable[EntryPoint] = entry_points(group=GRUPO)
    return [Declarado(p.name, p.value, p.dist.name if p.dist else '') for p in puntos]


def resolver(raiz: Path, instalados: Iterable[Declarado] | None = None) -> Resolucion:
    """Ordena por nombre (RF-10) y aparta duplicados (RF-12) y externos sin permiso (RF-23), sin importar nada."""
    permitidos, diagnostico = leer_permitidos(raiz)
    diagnostico = list(diagnostico)
    # Una instalación editable y otra normal del mismo paquete dan el mismo punto dos veces:
    # eso no es un conflicto de dos paquetes.
    unicos = sorted(set(_instalados() if instalados is None else instalados),
                    key=lambda d: (d.nombre, d.distribucion, d.valor))
    por_nombre: dict[str, list[Declarado]] = defaultdict(list)
    for declarado in unicos:
        por_nombre[declarado.nombre].append(declarado)
    aceptados = []
    for nombre, grupo in sorted(por_nombre.items()):
        if len(grupo) > 1:
            paquetes = ' y '.join(d.distribucion or d.valor for d in grupo)
            diagnostico.append(f'{nombre}: lo declaran {paquetes}; se rechazan los dos.')
            continue
        declarado = grupo[0]
        if declarado.distribucion != DISTRIBUCION_PROPIA and declarado.nombre not in permitidos:
            diagnostico.append(f'{nombre} ({declarado.distribucion or "sin paquete"}): instalado, pero no está '
                               f'en {RUTA_PERMITIDOS.as_posix()}; no se importa.')
            continue
        aceptados.append(declarado)
    return Resolucion(tuple(aceptados), tuple(sorted(permitidos)), tuple(diagnostico))


def _mayor(version: str) -> str:
    return str(version).split('.', 1)[0]


def _motivo_de_exclusion(declarado: Declarado, modulo: Any) -> str | None:
    if not isinstance(modulo, Modulo):
        return f'{declarado.nombre}: {declarado.valor} no es un Modulo.'
    if modulo.nombre != declarado.nombre:
        return f'{declarado.nombre}: el módulo se llama {modulo.nombre!r}, no como su entry point.'
    if modulo.puerto not in PUERTOS:
        return f'{declarado.nombre}: puerto desconocido {modulo.puerto!r}.'
    if _mayor(modulo.version_puerto) != _mayor(VERSION_PUERTOS):
        return (f'{declarado.nombre}: declara el puerto {modulo.version_puerto} y el núcleo '
                f'tiene {VERSION_PUERTOS}.')
    faltan = metodos_que_faltan(modulo)
    if faltan:
        return f'{declarado.nombre}: no cumple el puerto {modulo.puerto}, le falta {", ".join(faltan)}.'
    return None


def cargar(resolucion: Resolucion) -> Registro:
    """Importa lo resuelto en orden; lo que falle se excluye y se nombra (RF-11, RF-25, RF-26)."""
    registro = Registro(diagnostico=list(resolucion.diagnostico))
    for declarado in resolucion.declarados:
        try:
            modulo = EntryPoint(declarado.nombre, declarado.valor, GRUPO).load()
        except Exception as exc:  # noqa: BLE001 - código ajeno: cualquier fallo solo lo excluye a él
            registro.diagnostico.append(f'{declarado.nombre}: no se pudo importar ({type(exc).__name__}: {exc}).')
            continue
        motivo = _motivo_de_exclusion(declarado, modulo)
        if motivo:
            registro.diagnostico.append(motivo)
            continue
        registro.modulos[declarado.nombre] = modulo
    return registro


# -------------------------------------------------------------- procesos hijos (RF-29)
_RESOLUCION_DEL_PROCESO: Resolucion | None = None


def instalar_en_proceso(resolucion: Resolucion | None) -> None:
    """El hijo guarda la resolución del principal y no vuelve a leer metadatos ni lista."""
    global _RESOLUCION_DEL_PROCESO
    _RESOLUCION_DEL_PROCESO = resolucion


def resolucion_del_proceso() -> Resolucion | None:
    return _RESOLUCION_DEL_PROCESO


# -------------------------------------------------------------- estudios (RF-14, RF-30)
def carril_de(modulo: Modulo) -> str:
    """Lo que usa PowerFactory va al carril único en serie; lo demás, al del motor."""
    if modulo.puerto == 'sesion' or getattr(modulo.implementacion, 'usa_powerfactory', False):
        return 'powerfactory'
    return 'engine'


def lanzar_estudio(trabajos: Any, espacio: str, modulo: Modulo, **parametros: Any) -> Any:
    """Un estudio o una sesión son siempre un trabajo en cola, con progreso y cancelable."""
    if modulo.puerto not in ('estudio', 'sesion'):
        raise ValueError(f'{modulo.nombre} es un {modulo.puerto}: no se lanza como estudio.')
    implementacion = modulo.implementacion
    return trabajos.submit(espacio, modulo.puerto, modulo.nombre,
                           lambda ctx: implementacion().ejecutar(ctx, **parametros),
                           lane=carril_de(modulo))


# -------------------------------------------------------------- instalación (RF-28)
def declarados_en_pyproject(raiz: Path) -> dict[str, str]:
    datos = tomllib.loads((Path(raiz) / 'pyproject.toml').read_text(encoding='utf-8'))
    return dict(datos['project'].get('entry-points', {}).get(GRUPO, {}))


def desfase_de_entry_points(declarados: Mapping[str, str], instalados: Iterable[Declarado]) -> list[str]:
    """Lo que difiere entre ``pyproject.toml`` y lo instalado; cada línea pide reinstalar."""
    propios = {d.nombre: d.valor for d in instalados if d.distribucion == DISTRIBUCION_PROPIA}
    if dict(declarados) == propios:
        return []
    distintos = sorted(k for k in declarados.keys() | propios.keys() if declarados.get(k) != propios.get(k))
    return [f'Entry point desfasado: {k}: reinstale con «pip install -e .».' for k in distintos]
