"""La estructura de una empresa: zonales, SET y alimentadores (spec 022).

Las fuentes (TXT, MDB, VNR-GIS) traen la cabecera de cada alimentador —su nodo y su
tensión— pero no la SET de la que sale ni el zonal o el sistema eléctrico al que
pertenece. Electro Dunas los publica en su tabla «Sistemas eléctricos Electrodunas»
(2026-10-17: 4 zonales, cada SET con sus alimentadores y su sistema eléctrico con su
sector típico y su norma). Esa tabla va en el perfil de empresa o se sube en Excel, nunca
en el código (constitución 13): sin estructura, la red unida sigue como antes (RF-6).
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class EstructuraError(ValueError):
    """La estructura no se puede usar: dice la fila o la clave que falla (022:RF-5)."""


@dataclass(frozen=True)
class Sistema:
    codigo: str
    nombre: str
    sector: str = ''
    norma: str = ''


@dataclass(frozen=True)
class SetElectrica:
    codigo: str                     # «SET 21»
    nombre: str                     # «El Carmen»
    zonal: str
    siglas: tuple[str, ...] = ()    # de los medidores de barra (022:RF-38): «CA»

    @property
    def rotulo(self) -> str:
        return f'{self.codigo} {self.nombre}'.strip()


@dataclass(frozen=True)
class AlimentadorEstructura:
    codigo: str
    set_codigo: str
    sistema: str = ''               # código del sistema eléctrico: «SE1043»


@dataclass
class Estructura:
    zonales: list[str]
    sets: dict[str, SetElectrica]
    alimentadores: dict[str, AlimentadorEstructura]
    sistemas: dict[str, Sistema] = field(default_factory=dict)
    zonales_por_set: set[str] = field(default_factory=set)
    """Zonales con una red por SET (022:RF-64): el de Nasca va de la costa a la sierra y su
    diagrama único no cabía en la hoja de DIgSILENT (usuario, 2026-10-23)."""
    deducidos: dict[str, str] = field(default_factory=dict)
    """Alimentadores de la entrega que la estructura no traía, con la regla que los colocó
    (022:RF-71 a RF-74, RF-78): la tabla de la empresa va por detrás de las entregas."""

    def set_de(self, alimentador: str) -> SetElectrica | None:
        a = self.alimentadores.get(clave(alimentador))
        return self.sets.get(a.set_codigo) if a else None

    def set_de_siglas(self, siglas: str) -> SetElectrica | None:
        s = clave(siglas)
        return next((x for x in self.sets.values() if s in {clave(y) for y in x.siglas}), None)


def clave(codigo: Any) -> str:
    """El código como se compara: sin espacios de más y en mayúsculas («PN1T2  »)."""
    return ' '.join(str(codigo or '').split()).upper()


# =========================================================================== lectura
def estructura_de_dict(datos: Mapping[str, Any], origen: str = 'estructura') -> Estructura:
    """La estructura del perfil: ``{"zonales": [{"nombre", "dividir_por_set", "sets":
    [{"codigo", "nombre", "siglas", "alimentadores": [{"codigo", "sistema"}]}]}],
    "sistemas": {...}}``."""
    if not isinstance(datos, Mapping) or not isinstance(datos.get('zonales'), list):
        raise EstructuraError(f'{origen}: falta la lista «zonales».')
    sistemas = {}
    for codigo, s in (datos.get('sistemas') or {}).items():
        if not isinstance(s, Mapping):
            raise EstructuraError(f'{origen}: el sistema {codigo} no es un objeto.')
        sistemas[clave(codigo)] = Sistema(clave(codigo), str(s.get('nombre') or ''),
                                          str(s.get('sector') or ''), str(s.get('norma') or ''))
    filas = []
    for z in datos['zonales']:
        zonal = str((z or {}).get('nombre') or '').strip()
        for st in (z or {}).get('sets') or []:
            for a in st.get('alimentadores') or []:
                a = a if isinstance(a, Mapping) else {'codigo': a}
                filas.append({'zonal': zonal, 'set': st.get('codigo'), 'set_nombre': st.get('nombre'),
                              'siglas': st.get('siglas') or [], 'alimentador': a.get('codigo'),
                              'sistema': a.get('sistema')})
            if not st.get('alimentadores'):
                filas.append({'zonal': zonal, 'set': st.get('codigo'), 'set_nombre': st.get('nombre'),
                              'siglas': st.get('siglas') or [], 'alimentador': None, 'sistema': None})
    e = _construir(filas, sistemas, origen)
    e.zonales_por_set = {str(z.get('nombre') or '').strip() for z in datos['zonales']
                         if isinstance(z, Mapping) and z.get('dividir_por_set') is True}
    return e


def _construir(filas: Iterable[Mapping[str, Any]], sistemas: dict[str, Sistema],
               origen: str) -> Estructura:
    zonales: list[str] = []
    sets: dict[str, SetElectrica] = {}
    alimentadores: dict[str, AlimentadorEstructura] = {}
    for n, f in enumerate(filas, 1):
        donde = f"{origen}, fila {f.get('fila', n)}"
        zonal = str(f.get('zonal') or '').strip()
        codigo_set = clave(f.get('set'))
        if not codigo_set:
            if f.get('alimentador'):
                raise EstructuraError(f"{donde}: el alimentador {f['alimentador']} no tiene SET.")
            continue
        if not zonal:
            raise EstructuraError(f'{donde}: la SET {codigo_set} no tiene zonal.')
        previa = sets.get(codigo_set)
        siglas = tuple(clave(s) for s in (f.get('siglas') or []) if clave(s))
        if previa is not None and previa.zonal != zonal:
            raise EstructuraError(f'{donde}: la SET {codigo_set} está en {previa.zonal} y en {zonal}.')
        if previa is None:
            sets[codigo_set] = SetElectrica(codigo_set, str(f.get('set_nombre') or '').strip(),
                                            zonal, siglas)
        elif siglas and not set(siglas) <= set(previa.siglas):
            sets[codigo_set] = SetElectrica(previa.codigo, previa.nombre or str(f.get('set_nombre') or ''),
                                            zonal, tuple(dict.fromkeys(previa.siglas + siglas)))
        if zonal not in zonales:
            zonales.append(zonal)
        codigo = clave(f.get('alimentador'))
        if not codigo:
            continue
        if codigo in alimentadores:
            raise EstructuraError(f'{donde}: el alimentador {codigo} está repetido '
                                  f'(ya en {alimentadores[codigo].set_codigo}).')
        sistema = clave(f.get('sistema'))
        if sistema and sistema not in sistemas:
            sistemas[sistema] = Sistema(sistema, str(f.get('sistema_nombre') or '').strip(),
                                        str(f.get('sector') or '').strip(), str(f.get('norma') or '').strip())
        alimentadores[codigo] = AlimentadorEstructura(codigo, codigo_set, sistema)
    if not alimentadores:
        raise EstructuraError(f'{origen}: no tiene ningún alimentador.')
    return Estructura(zonales, sets, alimentadores, sistemas)


def estructura_de_perfil(datos: Mapping[str, Any], base: Path | None = None) -> Estructura | None:
    """La estructura del perfil de empresa (022:RF-1), o ``None`` si no la trae (RF-6).

    ``estructura`` puede ser el objeto o el nombre de un JSON junto al perfil (la de
    Electro Dunas va aparte: es larga y se actualiza sola).
    """
    valor = datos.get('estructura')
    if valor is None:
        return None
    if isinstance(valor, str):
        ruta = Path(valor) if base is None or Path(valor).is_absolute() else base / valor
        try:
            valor = json.loads(ruta.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise EstructuraError(f'estructura: no se puede leer {ruta.name}: {exc}') from exc
        return estructura_de_dict(valor, ruta.name)
    return estructura_de_dict(valor)


#: Columnas de la tabla en Excel (022:RF-4), por su nombre normalizado y con alias.
ALIAS_TABLA = {
    'zonal': ('zonal', 'zona'),
    'set': ('codigo set', 'set', 'cod set'),
    'set_nombre': ('nombre set', 'set nombre'),
    'siglas': ('siglas',),
    'sistema': ('codigo sist elect', 'codigo sistema electrico', 'codigo sistema', 'sistema'),
    'sistema_nombre': ('nombre sist elect', 'nombre sistema electrico', 'nombre sistema'),
    'sector': ('aplicacion final 2023 2026', 'sector tipico', 'sector'),
    'norma': ('norma',),
    'alimentador': ('codigo vnr alimentador', 'alimentador', 'codigo alimentador'),
}


def leer_tabla_excel(ruta: Path | str) -> Estructura:
    """La tabla de la estructura en Excel, como la publica la empresa (022:RF-4, RF-5).

    Una fila por alimentador; la SET puede venir con su nombre («SET 21 EL CARMEN») o en
    columnas aparte, y el zonal en todas sus filas.
    """
    from .demanda_medida import ALIAS, _abrir, _buscar_cabecera, _filas, _texto, normalizar

    alias = {**ALIAS, **{k: tuple(normalizar(x) for x in v) for k, v in ALIAS_TABLA.items()}}
    libro = _abrir(ruta)
    for hoja in libro.sheet_names:
        filas = _filas(libro, hoja)
        hallada = _buscar_cabecera(filas, tuple(ALIAS_TABLA), alias, ('zonal', 'set', 'alimentador'))
        if hallada is None:
            continue
        i, cols = hallada
        datos = []
        for n, fila in enumerate(filas[i + 1:], start=i + 2):
            f = {k: _texto(fila, cols.get(k)) for k in ALIAS_TABLA}
            if not any(f.values()):
                continue
            set_, nombre = _partir_set(f['set'], f['set_nombre'])
            datos.append({**f, 'fila': n, 'set': set_, 'set_nombre': nombre,
                          'siglas': [s for s in f['siglas'].replace(';', ',').split(',')]})
        return _construir(datos, {}, f'{Path(ruta).name} › {hoja}')
    raise EstructuraError(f'{Path(ruta).name}: ninguna hoja tiene «Zonal», «Código SET» y '
                          '«Alimentador».')


def _partir_set(codigo: str, nombre: str) -> tuple[str, str]:
    """«SET 21 EL CARMEN» → («SET 21», «EL CARMEN»); con el nombre aparte, tal cual."""
    partes = codigo.split()
    if not nombre and len(partes) > 2 and partes[0].upper() == 'SET':
        return ' '.join(partes[:2]), ' '.join(partes[2:])
    return codigo, nombre


# =========================================================================== nuevos
def siglas_de(codigo: Any) -> str:
    """Las letras del código antes del número: «PA» de PA219, «CHI» de CHI201 (022:RF-71)."""
    m = re.match(r'([A-Z]+)\d', clave(codigo))
    return m.group(1) if m else ''


def cabeceras_de_inventario(filas: Iterable[Mapping[str, Any]]) -> dict[str, tuple[float, float] | None]:
    """Alimentador → coordenadas de su cabecera, de las filas del inventario (022:RF-77)."""
    out: dict[str, tuple[float, float] | None] = {}
    for f in filas:
        xy = f.get('cabecera_xy')
        out[clave(f.get('feeder'))] = (float(xy[0]), float(xy[1])) if xy else None
    return out


def completar(estructura: Estructura,
              cabeceras: Mapping[str, tuple[float, float] | None]) -> Estructura:
    """La estructura con los alimentadores de la entrega que no traía (022:RF-71 a RF-76).

    La tabla de la empresa va por detrás de las entregas: RED_231026 trajo la SET Chincha
    Nueva (CN101 a CN201), PA219, COH101 y SC215, y quedaban «Sin SET», fuera de la
    conversión por zonal. Las siglas dicen la SET (PA219 → Paracas); si no llevan a
    ninguna, los de unas mismas siglas forman una SET deducida en el zonal de la cabecera
    conocida más cercana. La distancia solo elige el zonal, sin umbral: no hace falta el
    CRS, y no distingue SET (CN101 está a 6,5 km de El Carmen y es otra SET). La de entrada
    no cambia.
    """
    nuevos = sorted({clave(a) for a in cabeceras} - set(estructura.alimentadores) - {''})
    if not nuevos:
        return estructura
    xy = {clave(a): p for a, p in cabeceras.items() if p and any(p)}
    por_siglas_set = {s: st.codigo for st in estructura.sets.values() for s in st.siglas}
    sets_de_siglas: dict[str, set[str]] = defaultdict(set)
    sistemas_de_set: dict[str, set[str]] = defaultdict(set)
    for a in estructura.alimentadores.values():
        sets_de_siglas[siglas_de(a.codigo)].add(a.set_codigo)
        sistemas_de_set[a.set_codigo].add(a.sistema)
    sets = dict(estructura.sets)
    alimentadores = dict(estructura.alimentadores)
    deducidos = dict(estructura.deducidos)
    grupos: dict[str, list[str]] = defaultdict(list)
    for n in nuevos:
        s = siglas_de(n)
        if s in por_siglas_set:
            codigo, regla = por_siglas_set[s], f'siglas {s} de la SET'
        elif len(sets_de_siglas.get(s, ())) == 1:
            codigo, regla = next(iter(sets_de_siglas[s])), f'siglas {s} de sus alimentadores'
        else:
            if s:
                grupos[s].append(n)
            continue
        sistemas = sistemas_de_set[codigo]
        alimentadores[n] = AlimentadorEstructura(n, codigo, next(iter(sistemas)) if len(sistemas) == 1 else '')
        deducidos[n] = f'{regla} → {codigo}'
    conocidos = sorted((a, xy[a]) for a in estructura.alimentadores if a in xy)
    for s, miembros in sorted(grupos.items()):
        cerca = min(((math.dist(xy[m], p), a) for m in miembros if m in xy for a, p in conocidos),
                    default=None)
        if cerca is None:
            continue                                                       # RF-75
        zonal = estructura.sets[estructura.alimentadores[cerca[1]].set_codigo].zonal
        codigo = clave(f'SET {s}')
        while codigo in sets:
            codigo += '*'
        sets[codigo] = SetElectrica(codigo, '', zonal, (s,))
        for m in miembros:
            alimentadores[m] = AlimentadorEstructura(m, codigo, '')
            deducidos[m] = f'SET deducida por sus siglas, zonal {zonal} por la cabecera de {cerca[1]}'
    return Estructura(list(estructura.zonales), sets, alimentadores, dict(estructura.sistemas),
                      set(estructura.zonales_por_set), deducidos)


def aviso_deducidos(estructura: Estructura, alimentadores: Iterable[str]) -> str:
    """El aviso de los alimentadores colocados sin estar en la tabla (022:RF-78), o vacío."""
    lineas = []
    for a in sorted({clave(x) for x in alimentadores} & set(estructura.deducidos)):
        st = estructura.set_de(a)
        lineas.append(f'{a} en {st.rotulo} ({st.zonal}): {estructura.deducidos[a]}')
    if not lineas:
        return ''
    return (f'{len(lineas)} alimentador(es) que la estructura no traía, colocados por la '
            'entrega (022:RF-78): ' + '; '.join(lineas) + '.')


# =========================================================================== asignación
@dataclass
class Asignacion:
    """Qué SET y zonal tiene cada alimentador de la entrega (022:RF-19, RF-20, RF-25b)."""

    set_de: dict[str, str] = field(default_factory=dict)
    sin_set: list[str] = field(default_factory=list)
    faltan: list[str] = field(default_factory=list)
    sets: list[str] = field(default_factory=list)        # con redes, en orden de código
    zonales: list[str] = field(default_factory=list)     # con redes, en el orden del perfil
    sistemas: list[str] = field(default_factory=list)    # con redes
    omitidos: dict[str, list[str]] = field(default_factory=dict)


def asignar(estructura: Estructura, alimentadores: Iterable[str]) -> Asignacion:
    """Cada alimentador de la entrega con su SET; los que no están, «Sin SET» (RF-19); los de
    la estructura que no vienen, faltan (RF-20); SET, sistemas y zonales sin redes, omitidos
    (RF-25b). Recorre la entrega una vez y la estructura una vez (escala)."""
    out = Asignacion()
    vistos = set()
    for codigo in sorted({clave(a) for a in alimentadores if clave(a)}):
        vistos.add(codigo)
        st = estructura.set_de(codigo)
        if st is None:
            out.sin_set.append(codigo)
        else:
            out.set_de[codigo] = st.codigo
    out.faltan = sorted(set(estructura.alimentadores) - vistos)
    con_redes = set(out.set_de.values())
    out.sets = sorted(con_redes)
    zonales_con = {estructura.sets[s].zonal for s in con_redes}
    out.zonales = [z for z in estructura.zonales if z in zonales_con]
    sistemas_con = {estructura.alimentadores[a].sistema for a in out.set_de} - {''}
    out.sistemas = sorted(sistemas_con)
    out.omitidos = {
        'sets': sorted(set(estructura.sets) - con_redes),
        'zonales': [z for z in estructura.zonales if z not in zonales_con],
        'sistemas': sorted(set(estructura.sistemas) - sistemas_con),
    }
    return out
