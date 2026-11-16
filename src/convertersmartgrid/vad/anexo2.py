"""Validación de las tablas del estudio contra los formatos del anexo 2 de los TdR (108:RF-2, RF-3).

Los formatos (tabla, fila, columna, unidad y periodo) están transcritos con su cita en
``config/vad/anexo2_formatos.json``; aquí solo se comparan. **Nunca se rellena nada**: una tabla que falta, una fila
que falta, un campo vacío o una unidad distinta se devuelven como hueco con su tabla y su campo, y la tabla de salida
es la de entrada tal cual. Un formato que el anexo no deja leer en la copia local (páginas en imagen) se nombra como
«sin transcribir» y el conjunto no se da por completo: decir que se validó sería decir algo que no se comprobó.

Forma de una tabla de entrada::

    {'formato': 'A-I-1', 'periodo': '2025', 'unidades': {columna: unidad},
     'filas': {fila: {'unidad': unidad_de_la_fila, columna: valor, ...}}}
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from . import VadError

#: Los tipos de hueco que devuelve :func:`validar_tablas`.
TIPOS = ('falta_tabla', 'falta_campo', 'campo_vacio', 'unidad_distinta', 'periodo_distinto', 'sin_transcribir',
         'formato_desconocido')


@dataclass(frozen=True)
class Campo:
    id: str
    nombre: str
    unidad: str
    obligatoria: bool = True
    formula: str = ''


@dataclass(frozen=True)
class Formato:
    id: str
    titulo: str
    categoria: str
    obligatorio: bool
    transcrito: bool
    pagina: str
    lineas: str
    periodo: str = ''
    motivo: str = ''
    filas: tuple[Campo, ...] = ()
    columnas: tuple[Campo, ...] = ()


@dataclass(frozen=True)
class Formatos:
    acto: str
    formatos: tuple[Formato, ...]

    def todos(self) -> tuple[Formato, ...]:
        return self.formatos

    def transcritos(self) -> tuple[Formato, ...]:
        return tuple(f for f in self.formatos if f.transcrito)

    def formato(self, id_formato: str) -> Formato:
        for f in self.formatos:
            if f.id == id_formato:
                return f
        raise VadError(f'el anexo 2 transcrito no tiene el formato {id_formato!r}')


@dataclass(frozen=True)
class Hueco:
    tabla: str
    campo: str
    tipo: str
    detalle: str

    def linea(self) -> str:
        return f'{self.tabla} · {self.campo or "(tabla)"} · {self.tipo}: {self.detalle}'


@dataclass
class ResultadoAnexo2:
    tablas: dict[str, Any]
    huecos: list[Hueco] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        """Sin ningún hueco, tampoco de formatos sin transcribir."""
        return not self.huecos


def _campos(datos: Any) -> tuple[Campo, ...]:
    return tuple(Campo(**{k: v for k, v in c.items() if k in Campo.__dataclass_fields__}) for c in datos or ())


def cargar_formatos(ruta: Path | str) -> Formatos:
    datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    if datos.get('esquema') != 'vad_anexo2_v1':
        raise VadError(f'{ruta}: no es la transcripción del anexo 2 (vad_anexo2_v1)')
    formatos = []
    for f in datos['formatos']:
        campos = {k: v for k, v in f.items() if k in Formato.__dataclass_fields__ and k not in ('filas', 'columnas')}
        formatos.append(Formato(**campos, filas=_campos(f.get('filas')), columnas=_campos(f.get('columnas'))))
    return Formatos(acto=datos['fuente']['acto'], formatos=tuple(formatos))


def _vacio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _validar_una(nombre: str, tabla: Mapping[str, Any], formato: Formato, periodo: str | None) -> list[Hueco]:
    huecos: list[Hueco] = []
    if periodo is not None and str(tabla.get('periodo') or '') != str(periodo):
        huecos.append(Hueco(nombre, 'periodo', 'periodo_distinto',
                            f'la tabla es del periodo {tabla.get("periodo")!r} y el estudio pide {periodo!r}'))
    unidades = tabla.get('unidades') or {}
    for c in formato.columnas:
        if c.id not in unidades:
            if c.obligatoria:
                huecos.append(Hueco(nombre, c.id, 'falta_campo', f'falta la unidad de la columna «{c.nombre}»'))
        elif unidades[c.id] != c.unidad:
            huecos.append(Hueco(nombre, c.id, 'unidad_distinta',
                                f'«{c.nombre}» viene en {unidades[c.id]!r} y el anexo 2 pide {c.unidad!r}'))
    filas = tabla.get('filas') or {}
    for f in formato.filas:
        if f.id not in filas:
            if f.obligatoria:
                huecos.append(Hueco(nombre, f.id, 'falta_campo', f'falta la fila «{f.nombre}»'))
            continue
        fila = filas[f.id]
        if fila.get('unidad') != f.unidad:
            huecos.append(Hueco(nombre, f'{f.id}.unidad', 'unidad_distinta',
                                f'«{f.nombre}» viene en {fila.get("unidad")!r} y el anexo 2 pide {f.unidad!r}'))
        if not f.obligatoria:
            continue
        for c in formato.columnas:
            if c.obligatoria and _vacio(fila.get(c.id)):
                huecos.append(Hueco(nombre, f'{f.id}.{c.id}', 'campo_vacio',
                                    f'«{f.nombre}» / «{c.nombre}» está vacío; no se rellena'))
    return huecos


def validar_tablas(tablas: Mapping[str, Any], formatos: Formatos, *, periodo: str | None = None) -> ResultadoAnexo2:
    """Compara cada tabla con su formato. La salida trae solo lo que vino en la entrada, copiado sin tocar."""
    huecos: list[Hueco] = []
    salida: dict[str, Any] = {}
    conocidos = {f.id for f in formatos.todos()}
    for nombre in sorted(tablas):
        if nombre not in conocidos:
            huecos.append(Hueco(nombre, '', 'formato_desconocido', 'la tabla no corresponde a ningún formato del anexo 2'))
        salida[nombre] = copy.deepcopy(tablas[nombre])
    for formato in formatos.todos():
        if not formato.transcrito:
            huecos.append(Hueco(formato.id, '', 'sin_transcribir',
                                f'{formato.titulo}: {formato.motivo} (anexo 2, {formato.pagina}, líneas {formato.lineas})'))
            continue
        if formato.id not in tablas:
            if formato.obligatorio:
                huecos.append(Hueco(formato.id, '', 'falta_tabla',
                                    f'falta la tabla obligatoria «{formato.titulo}»; no se crea'))
            continue
        huecos.extend(_validar_una(formato.id, tablas[formato.id], formato, periodo))
    return ResultadoAnexo2(salida, huecos)
