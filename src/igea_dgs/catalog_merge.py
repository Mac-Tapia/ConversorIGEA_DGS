"""Completa el catálogo de equipos cuando el export llega incompleto.

El fallo que motiva esto, medido sobre una entrega real. El export del 24 de septiembre
traía un ``Equipos.txt`` con **9 tipos de línea** y una convención de nombres distinta
(``AAAC1203``, ``ATVB1-22.9KV-050``), mientras la red usaba **43** códigos de la
convención anterior (``AA03503D``, ``AA12003D``…). Resultado: los 38.879 tramos —los
4.194,6 km de red, el **100 %**— se resolvían a ``DEFAULT``, con R = 0,4 Ω/km para todo,
cuando los valores reales van de 0,18 a 3,38.

Lo grave no es que falle, es que **no falla**. El conversor produce un modelo completo,
que converge en PowerFactory y da un flujo de potencia impecable con todas las
impedancias equivocadas. Las pérdidas técnicas y las caídas de tensión que salgan de ahí
no significan nada, y nada en el resultado lo delata.

Qué hace este módulo. Toma el catálogo cargado y lo completa con otro fichero de
equipos —normalmente una entrega anterior más completa— añadiendo **solo los códigos que
faltan**. Lo ya cargado nunca se sobrescribe: si el operador entregó un catálogo nuevo
para un conductor, ese manda; lo que se rellena son los huecos.

Con el catálogo anterior de la misma empresa, la cobertura pasó del 0 % al 99,4 %: el
0,6 % restante son los ramales de acometida de 0,3 m, que el propio export deja en
``DEFAULT`` a propósito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

#: Tablas del BD_Equipo que aportan tipos de línea. Son las que importan para la
#: impedancia; el resto del catálogo (protecciones, filtros) no se usa todavía.
TABLAS_DE_TIPOS = ('LINE', 'CONCENTRIC NEUTRAL CABLE')

#: Tablas que también conviene completar cuando faltan, aunque no cambien la impedancia.
TABLAS_COMPLEMENTARIAS = ('CONDUCTOR', 'SPACING TABLE FOR LINE', 'SUBSTATION',
                          'TRANSFORMER')


@dataclass
class InformeCatalogo:
    """Qué faltaba, qué se añadió y de dónde."""

    codigos_en_red: set[str] = field(default_factory=set)
    codigos_en_catalogo: set[str] = field(default_factory=set)
    anadidos: dict[str, list[str]] = field(default_factory=dict)
    """Fichero de origen → códigos que aportó."""
    sin_resolver: set[str] = field(default_factory=set)

    @property
    def cobertura_inicial(self) -> float:
        if not self.codigos_en_red:
            return 1.0
        return len(self.codigos_en_red & self.codigos_en_catalogo) / len(self.codigos_en_red)

    @property
    def cobertura_final(self) -> float:
        if not self.codigos_en_red:
            return 1.0
        return 1.0 - len(self.sin_resolver) / len(self.codigos_en_red)

    @property
    def total_anadidos(self) -> int:
        return sum(len(v) for v in self.anadidos.values())

    def texto(self) -> str:
        lineas = [
            f'Tipos de línea que usa la red : {len(self.codigos_en_red)}',
            f'Estaban en el catálogo        : '
            f'{len(self.codigos_en_red & self.codigos_en_catalogo)} '
            f'({self.cobertura_inicial * 100:.0f} %)',
        ]
        for origen, codigos in self.anadidos.items():
            lineas.append(f'Completados desde {Path(origen).name}: {len(codigos)}')
        lineas.append(
            f'Cobertura final               : {self.cobertura_final * 100:.0f} %')
        if self.sin_resolver:
            faltan = sorted(self.sin_resolver)
            lineas.append(
                f'Siguen sin catálogo           : {len(faltan)} '
                f'({", ".join(faltan[:8])}{"…" if len(faltan) > 8 else ""})'
            )
        return '\n'.join(lineas)


def codigos_usados(dataset: Any) -> set[str]:
    """Códigos de conductor que la red referencia, vengan o no en el catálogo."""
    codigos: set[str] = set()
    for fila in (dataset.line_configurations or {}).values():
        codigo = str(fila.get('LineCableID', '') or '').strip()
        if codigo:
            codigos.add(codigo)
    return codigos


def codigos_en_catalogo(dataset: Any) -> set[str]:
    codigos: set[str] = set()
    for tabla in TABLAS_DE_TIPOS:
        for fila in (dataset.equipment_tables.get(tabla) or ()):
            codigo = str(fila.get('ID', '') or '').strip()
            if codigo:
                codigos.add(codigo)
    return codigos


def _leer_equipos(ruta: Path) -> dict[str, list[dict[str, str]]]:
    """Tablas de un BD_Equipo TXT, con el mismo criterio que el lector principal."""
    tablas: dict[str, list[dict[str, str]]] = {}
    seccion: str | None = None
    columnas: list[str] | None = None
    with ruta.open('r', encoding='utf-8', errors='replace', newline='') as fh:
        for linea in fh:
            s = linea.strip()
            if not s:
                continue
            if s.startswith('[') and s.endswith(']'):
                seccion = s[1:-1].strip().upper()
                columnas = None
                continue
            if seccion is None:
                continue
            if s.upper().startswith('FORMAT'):
                columnas = [c.strip() for c in s.split('=', 1)[1].split(',')]
                continue
            if columnas is None:
                continue
            valores = [v.strip() for v in s.split(',')]
            fila = {c: (valores[i] if i < len(valores) else '')
                    for i, c in enumerate(columnas)}
            tablas.setdefault(seccion, []).append(fila)
    return tablas


def completar(
    dataset: Any, fuentes: Iterable[Path | str], *, incluir_complementarias: bool = True,
) -> InformeCatalogo:
    """Rellena los huecos del catálogo con otros ficheros de equipos.

    **Lo ya cargado nunca se sobrescribe.** Si la entrega nueva trae un conductor, ese
    es el que vale; lo que se completa son los códigos que la red usa y el catálogo no
    tiene. Un catálogo de otra entrega es una muleta razonable para no perder la
    impedancia real, pero no es motivo para pisar un dato que el operador acaba de dar.
    """
    informe = InformeCatalogo(
        codigos_en_red=codigos_usados(dataset),
        codigos_en_catalogo=codigos_en_catalogo(dataset),
    )
    faltan = informe.codigos_en_red - informe.codigos_en_catalogo

    tablas = TABLAS_DE_TIPOS + (TABLAS_COMPLEMENTARIAS if incluir_complementarias else ())
    for fuente in fuentes:
        ruta = Path(fuente)
        if not ruta.is_file():
            continue
        try:
            extra = _leer_equipos(ruta)
        except OSError:
            continue

        aportados: list[str] = []
        for tabla in tablas:
            presentes = {
                str(f.get('ID', '') or '').strip()
                for f in (dataset.equipment_tables.get(tabla) or ())
            }
            # equipment_tables guarda tuplas; hay que convertir para poder añadir.
            destino = list(dataset.equipment_tables.get(tabla) or ())
            for fila in extra.get(tabla, ()):
                codigo = str(fila.get('ID', '') or '').strip()
                if not codigo or codigo in presentes:
                    continue
                # Solo se traen los tipos de línea que la red necesita; el resto del
                # catálogo ajeno no pinta nada aquí y solo añadiría ruido.
                if tabla in TABLAS_DE_TIPOS and codigo not in faltan:
                    continue
                destino.append(fila)
                presentes.add(codigo)
                if tabla in TABLAS_DE_TIPOS:
                    aportados.append(codigo)
            dataset.equipment_tables[tabla] = destino
        if aportados:
            informe.anadidos[str(ruta)] = sorted(aportados)
            faltan -= set(aportados)

    informe.sin_resolver = set(faltan)
    return informe


def diagnosticar(dataset: Any) -> InformeCatalogo:
    """Cobertura del catálogo sin tocar nada. Para avisar antes de convertir."""
    informe = InformeCatalogo(
        codigos_en_red=codigos_usados(dataset),
        codigos_en_catalogo=codigos_en_catalogo(dataset),
    )
    informe.sin_resolver = informe.codigos_en_red - informe.codigos_en_catalogo
    return informe
