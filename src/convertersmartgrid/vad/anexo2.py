"""Validación de las tablas del estudio contra los formatos del anexo 2 de los TdR (108:RF-2, RF-3).

Los formatos (tabla, fila, columna, unidad y periodo) están transcritos con su cita en
``config/vad/anexo2_formatos.json``; aquí solo se comparan. **Nunca se rellena nada**: una tabla que falta, una fila
que falta, un campo vacío o una unidad distinta se devuelven como hueco con su tabla y su campo, y la tabla de salida
es la de entrada tal cual. Una celda que el formato sombrea en gris («no aplica», ``no_aplica`` de la fila) no se
exige; si trae dato, se avisa (``avisos``) sin borrarlo ni contarlo como hueco. Una fila de ``tipo`` «grupo» es solo
el rótulo del formato y no se pide; una de «total» es una fila más del formato. La ``llamada`` de una fila remite a
las ``notas`` del formato. Un formato de ``forma`` «larga» (A-V-3) trae ``bloques`` con sus ``claves`` (empresa,
sistema, mes, …) y las filas de cada uno. Un formato que el anexo no deja leer en la copia local (páginas en
imagen) se nombra como «sin transcribir» y el conjunto no se da por completo: decir que se validó sería decir algo que no se comprobó.

Forma de una tabla de entrada::

    {'formato': 'A-I-1', 'periodo': '2025', 'unidades': {columna: unidad},
     'filas': {fila: {'unidad': unidad_de_la_fila, columna: valor, ...}}}

y de una de forma larga::

    {'formato': 'A-V-3', 'periodo': '2025', 'unidades': {...},
     'bloques': [{'claves': {'Empresa': ..., 'Sistema': ..., 'Mes': 1, ...}, 'filas': {...}}, ...]}
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
         'formato_desconocido', 'falta_bloque', 'bloque_repetido')
#: Las formas de un formato: «ancha» (una fila por código) y «larga» (un bloque por cada combinación de claves).
FORMAS = ('ancha', 'larga')
#: Los tipos de aviso: no impiden dar el conjunto por completo, pero se dicen.
AVISOS = ('dato_en_no_aplica', 'limitacion_del_formato', 'codigos_casados_por_rotulo')
#: Los tipos de fila del formato: «dato» (la de siempre), «grupo» (solo rótulo) y «total».
TIPOS_FILA = ('dato', 'grupo', 'total')


@dataclass(frozen=True)
class Campo:
    id: str
    nombre: str
    unidad: str
    obligatoria: bool = True
    formula: str = ''
    tipo: str = 'dato'
    no_aplica: tuple[str, ...] = ()
    llamada: str = ''
    rango_de: str = ''
    nota: str = ''


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
    notas: Mapping[str, str] = field(default_factory=dict)
    forma: str = 'ancha'
    claves_de_fila: tuple[str, ...] = ()
    #: Qué columnas forman el costo reconocible y cuáles se informan sin sumar (A-VII-1: la PTU), con sus citas y
    #: las limitaciones del formato.
    reconocible: Mapping[str, Any] = field(default_factory=dict)
    #: Avisos que el formato da siempre que se valida su tabla (p. ej. los códigos del IX casados por rótulo).
    avisos_al_validar: tuple[Mapping[str, str], ...] = ()


@dataclass(frozen=True)
class Formatos:
    acto: str
    formatos: tuple[Formato, ...]
    #: La tabla de equivalencias de códigos entre formatos (decisión anotada en la config).
    equivalencias: tuple[Mapping[str, Any], ...] = ()

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
    avisos: list[Hueco] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        """Sin ningún hueco, tampoco de formatos sin transcribir."""
        return not self.huecos


def _campo(c: Mapping[str, Any]) -> Campo:
    datos = {k: v for k, v in c.items() if k in Campo.__dataclass_fields__}
    datos['no_aplica'] = tuple(datos.get('no_aplica') or ())
    campo = Campo(**datos)
    if campo.tipo not in TIPOS_FILA:
        raise VadError(f'la fila {campo.id!r} tiene un tipo desconocido {campo.tipo!r}; los tipos son {TIPOS_FILA}')
    return campo


def _campos(datos: Any) -> tuple[Campo, ...]:
    return tuple(_campo(c) for c in datos or ())


def cargar_formatos(ruta: Path | str) -> Formatos:
    datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    if datos.get('esquema') != 'vad_anexo2_v1':
        raise VadError(f'{ruta}: no es la transcripción del anexo 2 (vad_anexo2_v1)')
    formatos = []
    for f in datos['formatos']:
        campos = {k: v for k, v in f.items() if k in Formato.__dataclass_fields__ and k not in ('filas', 'columnas')}
        filas, columnas = _campos(f.get('filas')), _campos(f.get('columnas'))
        ids = {c.id for c in columnas}
        for col in columnas:
            if col.llamada and col.llamada not in (f.get('notas') or {}):
                raise VadError(f'{f["id"]}: la columna {col.id!r} llama a la nota ({col.llamada}) '
                               'y el formato no la trae')
        rec = f.get('reconocible') or {}
        fuera = sorted((set(rec.get('suman') or ()) | set(rec.get('no_suman') or ())) - ids)
        if fuera:
            raise VadError(f'{f["id"]}: el costo reconocible nombra columnas que el formato no tiene: {fuera}')
        for fila in filas:
            if set(fila.no_aplica) - ids:
                raise VadError(f'{f["id"]}: la fila {fila.id!r} marca «no aplica» en columnas que el formato no tiene: '
                               f'{sorted(set(fila.no_aplica) - ids)}')
            if fila.llamada and fila.llamada not in (f.get('notas') or {}):
                raise VadError(f'{f["id"]}: la fila {fila.id!r} llama a la nota ({fila.llamada}) '
                               'y el formato no la trae')
        campos['claves_de_fila'] = tuple(campos.get('claves_de_fila') or ())
        campos['avisos_al_validar'] = tuple(campos.get('avisos_al_validar') or ())
        for a in campos['avisos_al_validar']:
            if a.get('tipo') not in AVISOS or not a.get('texto'):
                raise VadError(f'{f["id"]}: aviso al validar sin tipo conocido o sin texto: {a}')
        formato = Formato(**campos, filas=filas, columnas=columnas)
        if formato.forma not in FORMAS or (formato.forma == 'larga' and not formato.claves_de_fila):
            raise VadError(f'{formato.id}: forma {formato.forma!r} sin sus claves de fila; las formas son {FORMAS}')
        formatos.append(formato)
    equivalencias = tuple((datos.get('equivalencias_de_codigos') or {}).get('filas') or ())
    return Formatos(acto=datos['fuente']['acto'], formatos=tuple(formatos), equivalencias=equivalencias)


def _vacio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _cabecera(nombre: str, tabla: Mapping[str, Any], formato: Formato, periodo: str | None) -> list[Hueco]:
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
    return huecos


def _filas(nombre: str, filas: Mapping[str, Any], formato: Formato, avisos: list[Hueco],
           prefijo: str = '') -> list[Hueco]:
    """Las filas de una tabla (o de un bloque de la forma larga) contra las del formato."""
    huecos: list[Hueco] = []
    for f in formato.filas:
        if f.tipo == 'grupo':
            continue
        rotulo = f.nombre or f.id
        if f.id not in filas:
            if f.obligatoria:
                huecos.append(Hueco(nombre, f'{prefijo}{f.id}', 'falta_campo', f'falta la fila «{rotulo}»'))
            continue
        fila = filas[f.id]
        if fila.get('unidad') != f.unidad:
            huecos.append(Hueco(nombre, f'{prefijo}{f.id}.unidad', 'unidad_distinta',
                                f'«{rotulo}» viene en {fila.get("unidad")!r} y el anexo 2 pide {f.unidad!r}'))
        if not f.obligatoria:
            continue
        for c in formato.columnas:
            if c.id in f.no_aplica:
                if not _vacio(fila.get(c.id)):
                    avisos.append(Hueco(nombre, f'{prefijo}{f.id}.{c.id}', 'dato_en_no_aplica',
                                        f'«{rotulo}» / «{c.nombre}» no aplica en el formato y trae '
                                        f'{fila.get(c.id)!r}; no se borra'))
                continue
            if c.obligatoria and _vacio(fila.get(c.id)):
                huecos.append(Hueco(nombre, f'{prefijo}{f.id}.{c.id}', 'campo_vacio',
                                    f'«{rotulo}» / «{c.nombre}» está vacío; no se rellena'))
    return huecos


def _validar_una(nombre: str, tabla: Mapping[str, Any], formato: Formato, periodo: str | None,
                 avisos: list[Hueco]) -> list[Hueco]:
    return _cabecera(nombre, tabla, formato, periodo) + _filas(nombre, tabla.get('filas') or {}, formato, avisos)


def _validar_larga(nombre: str, tabla: Mapping[str, Any], formato: Formato, periodo: str | None,
                   avisos: list[Hueco]) -> list[Hueco]:
    """Forma larga (A-V-3): las filas del formato son la plantilla de un bloque que se repite por cada combinación de
    ``claves_de_fila`` (empresa, sistema, mes, …). Cada bloque se valida como una tabla; una clave vacía, un bloque
    repetido y un mes del 1 al 12 que falta (por el resto de claves) se nombran. Nada se rellena."""
    huecos = _cabecera(nombre, tabla, formato, periodo)
    bloques = tabla.get('bloques') or []
    if not bloques:
        return huecos + [Hueco(nombre, 'bloques', 'falta_campo', 'la tabla de forma larga no trae ningún bloque')]
    claves = formato.claves_de_fila
    vistos: set[tuple[str, ...]] = set()
    meses: dict[tuple[str, ...], set[int]] = {}
    for n, bloque in enumerate(bloques, 1):
        valores = bloque.get('claves') or {}
        for k in claves:
            if _vacio(valores.get(k)):
                huecos.append(Hueco(nombre, f'bloque {n}.{k}', 'campo_vacio', f'el bloque {n} no dice «{k}»'))
        clave = tuple(str(valores.get(k, '')) for k in claves)
        etiqueta = ' / '.join(clave)
        if clave in vistos:
            huecos.append(Hueco(nombre, f'bloque {n}', 'bloque_repetido', f'el bloque «{etiqueta}» ya vino antes'))
        vistos.add(clave)
        huecos.extend(_filas(nombre, bloque.get('filas') or {}, formato, avisos, prefijo=f'{etiqueta} · '))
        if 'Mes' in claves:
            resto = tuple(v for k, v in zip(claves, clave) if k != 'Mes')
            try:
                meses.setdefault(resto, set()).add(int(str(valores.get('Mes'))))
            except ValueError:
                huecos.append(Hueco(nombre, f'bloque {n}.Mes', 'campo_vacio',
                                    f'el mes del bloque {n} no es un número de 1 a 12: {valores.get("Mes")!r}'))
    for resto, vistos_mes in sorted(meses.items()):
        faltan = sorted(set(range(1, 13)) - vistos_mes)
        if faltan:
            huecos.append(Hueco(nombre, ' / '.join(resto), 'falta_bloque',
                                f'faltan los meses {faltan} de «{" / ".join(resto)}»; no se crean'))
    return huecos


def validar_tablas(tablas: Mapping[str, Any], formatos: Formatos, *, periodo: str | None = None) -> ResultadoAnexo2:
    """Compara cada tabla con su formato. La salida trae solo lo que vino en la entrada, copiado sin tocar."""
    huecos: list[Hueco] = []
    avisos: list[Hueco] = []
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
        validar = _validar_larga if formato.forma == 'larga' else _validar_una
        huecos.extend(validar(formato.id, tablas[formato.id], formato, periodo, avisos))
        for a in formato.avisos_al_validar:
            avisos.append(Hueco(formato.id, '', a['tipo'], a['texto']))
        for n, texto in enumerate(formato.reconocible.get('limitaciones') or (), 1):
            avisos.append(Hueco(formato.id, f'reconocible.limitacion {n}', 'limitacion_del_formato', texto))
    return ResultadoAnexo2(salida, huecos, avisos)


def costo_reconocible(formato: Formato, fila: Mapping[str, Any]) -> tuple[float | None, list[str]]:
    """El costo reconocible de una fila: la suma de las columnas que ``reconocible.suman`` nombra. Las de
    ``no_suman`` (A-VII-1: la PTU, nota (3) y TdR 6.14) se informan pero no entran. Una columna que suma y viene vacía
    se nombra y el costo no se da (``None``): no se rellena con cero."""
    rec = formato.reconocible
    if not rec:
        raise VadError(f'{formato.id}: el formato no define un costo reconocible')
    faltan = [c for c in rec['suman'] if _vacio(fila.get(c))]
    if faltan:
        return None, faltan
    return float(sum(float(fila[c]) for c in rec['suman'])), []
