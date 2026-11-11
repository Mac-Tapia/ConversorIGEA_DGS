"""El estudio de planeamiento: de su año de presentación salen todos sus años (spec 072).

El PIDE se presenta cada 4 años y el año 00 es el anterior a la presentación (art. 7.2 de la
metodología): con presentación en 2027, el año 00 es 2026 y el detalle del PIDE va de 2030 a 2033.
Por eso aquí no hay ningún año de calendario escrito: el usuario, el 2026-11-02, «esto no debe ser
fijo porque se presenta cada 4 años». Los desplazamientos salen de la metodología.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class EstudioError(ValueError):
    """Un estudio que no se puede formar: se dice, no se supone un año."""


@dataclass(frozen=True)
class Estudio:
    """Los años de un estudio, relativos al año 00 y de calendario (072:RF-1, RF-2)."""

    anio_presentacion: int
    anio_base: int
    largo_plazo: tuple[int, ...]
    detalle_pide: tuple[int, ...]
    ciclo_anios: int

    def calendario(self, relativo: int) -> int:
        """El año de calendario de un año relativo al año 00."""
        return self.anio_base + relativo

    def siguiente(self) -> 'Estudio':
        """El estudio del ciclo siguiente: los mismos desplazamientos, otros años."""
        return Estudio(self.anio_presentacion + self.ciclo_anios, self.anio_base + self.ciclo_anios,
                       self.largo_plazo, self.detalle_pide, self.ciclo_anios)

    def resumen(self) -> dict:
        """Lo que se guarda en el informe: los años relativos y su calendario."""
        return {'anio_presentacion': self.anio_presentacion, 'anio_base': self.anio_base,
                'largo_plazo': {f'{a:02d}': self.calendario(a) for a in self.largo_plazo},
                'detalle_pide': {f'{a:02d}': self.calendario(a) for a in self.detalle_pide}}


def _desplazamientos(horizonte: Mapping, clave: str) -> tuple[int, ...]:
    valores = horizonte.get(clave)
    if not valores or any(type(v) is not int or v < 0 for v in valores):
        raise EstudioError(f'la metodología no declara los años «{clave}» como enteros relativos al año 00')
    return tuple(sorted(valores))


def estudio_de(anio_presentacion: int, horizonte: Mapping) -> Estudio:
    """Forma el estudio con el año de presentación y el horizonte de la metodología (072:RF-1, RF-2)."""
    if type(anio_presentacion) is not int or anio_presentacion < 1:
        raise EstudioError(f'año de presentación no válido: {anio_presentacion!r}')
    ciclo = horizonte.get('ciclo_anios')
    if type(ciclo) is not int or ciclo < 1:
        raise EstudioError('la metodología no declara el ciclo de presentación')
    return Estudio(anio_presentacion, anio_presentacion - 1, _desplazamientos(horizonte, 'largo_plazo'),
                   _desplazamientos(horizonte, 'detalle_pide'), ciclo)


def aviso_del_anio_medido(estudio: Estudio, anio_medido: int | None) -> str | None:
    """Si el caso base no se calibró con mediciones del año 00, se dice y se sigue (072:RF-3)."""
    if anio_medido is None:
        return f'no consta el año de la medición del caso base; el año 00 del estudio es {estudio.anio_base}'
    if anio_medido != estudio.anio_base:
        return (f'el caso base se calibró con mediciones de {anio_medido} y el año 00 del estudio, que se '
                f'presenta en {estudio.anio_presentacion}, es {estudio.anio_base}')
    return None


#: 072:RF-29: los tres tipos de análisis que el operador elige en la web, en el orden en que se encadenan: el PIDE parte
#: de la obra de corto plazo (098:RF-37) y consume el plan de largo plazo (RF-4).
TIPOS_DE_ANALISIS = ('corto_plazo', 'pide', 'largo_plazo')
#: El nombre del entregable de cada tipo en ``informes_planeamiento.MODULOS``.
ENTREGABLE_DE = {'pide': 'PIDE', 'largo_plazo': 'Plan de largo plazo'}
#: La ``etapa`` de los artículos de cada tipo en la metodología (``config/pide_universal_2017.json``).
ETAPA_DE = {'pide': 'pide', 'largo_plazo': 'planeamiento_largo_plazo'}
#: 072:RF-31: las palabras de cada obra de la escalera (098:RF-45, RF-50); un código sin rótulo se muestra tal cual.
ROTULO_OBRA = {'bancos': 'Bancos de condensadores', 'seccion': 'Cambio de sección', 'terna': 'Nueva terna',
               'transferencia': 'Transferencia o traslado de carga', 'regulador': 'Regulador de tensión',
               'nivel': 'Cambio de nivel de tensión (p. ej. a 22,9 kV)', 'expreso': 'Alimentador nuevo (expreso)',
               'set_nueva': 'SET nueva'}
#: 072:RF-32: los entregables del corto plazo son los informes de la web (spec 017) con su libro (spec 066).
ENTREGABLES_CORTO = ({'clave': 'informe_estudio', 'titulo': 'Informe de estudio eléctrico', 'formatos': []},
                     {'clave': 'informe_factibilidad', 'titulo': 'Informe de factibilidad de suministro', 'formatos': []},
                     {'clave': 'libro_informe', 'titulo': 'Libro Excel de cada informe', 'formatos': []})


def _anios(relativos, estudio: Estudio | None) -> list[dict]:
    return [{'relativo': a, 'calendario': estudio.calendario(a) if estudio else None} for a in relativos]


def tipos_de_analisis(metodologia: Mapping, *, periodo_corto: int, modulos: Sequence[Mapping],
                      obras_corto: Sequence[str], obras_largo: Sequence[str],
                      anio_presentacion: int | None = None) -> dict:
    """Horizonte, obras, artículos y entregables de cada tipo de análisis (072:RF-29 a RF-32, RF-37).

    Todo sale de lo que se le pasa: la metodología (años, artículos y estado jurídico), los módulos de los informes (qué
    formatos son de cada entregable), las obras de cada plazo (098:RF-50) y el periodo de corto plazo del perfil
    (098:RF-37). Aquí no se escribe ningún año ni formato: la web antes no distinguía los tres y un solo «Planificar»
    escribía siempre los dos entregables (petición del usuario).
    """
    if type(periodo_corto) is not int or periodo_corto < 1:
        raise EstudioError(f'periodo de corto plazo no válido: {periodo_corto!r}')
    horizonte = metodologia.get('horizonte') or {}
    estudio = estudio_de(anio_presentacion, horizonte) if anio_presentacion is not None else None
    fuente = metodologia.get('fuente') or {}
    estado = str(metodologia.get('estado_juridico') or '')
    articulos = [a for a in metodologia.get('articulos') or () if isinstance(a, Mapping)]
    corto = [{'codigo': c, 'titulo': ROTULO_OBRA.get(c, c)} for c in obras_corto]
    largo = [{'codigo': c, 'titulo': ROTULO_OBRA.get(c, c)} for c in obras_largo]

    def de_la_norma(clave: str, relativos) -> dict:
        propios = [m for m in modulos if m['entregable'] == ENTREGABLE_DE[clave]]
        return {'articulos': [{'numero': a['numero'], 'titulo': a.get('titulo', '')} for a in articulos
                              if a.get('etapa') == ETAPA_DE[clave]],
                'anios': _anios(relativos, estudio),
                'formatos': [f for m in propios for f in m['formatos']],
                'entregables': [{'clave': m['clave'], 'titulo': f"{m['entregable']}: {m['titulo']}",
                                 'formatos': list(m['formatos'])} for m in propios]}

    tipos = [
        {'clave': 'corto_plazo', 'titulo': 'Corto plazo', 'articulos': [], 'formatos': [],
         'anios': _anios(range(0, periodo_corto + 1), estudio),
         'descripcion': ('La obra más barata que deja la red en norma hoy y aguanta hasta el año '
                         f'{periodo_corto:02d}; se aplica en «Con proyecto».'),
         'obras_admitidas': corto, 'obras_excluidas': largo, 'aplica_obras': True,
         'entregables': [dict(e) for e in ENTREGABLES_CORTO]},
        {'clave': 'pide', 'titulo': 'PIDE', **de_la_norma('pide', _desplazamientos(horizonte, 'detalle_pide')),
         'descripcion': ('Plan de inversiones del periodo, año a año, partiendo de la obra de corto plazo; consume el '
                         'plan de largo plazo del mismo estudio, que también se entrega.'),
         'obras_admitidas': corto + largo, 'obras_excluidas': [], 'aplica_obras': True},
        {'clave': 'largo_plazo', 'titulo': 'Planeamiento de largo plazo',
         **de_la_norma('largo_plazo', _desplazamientos(horizonte, 'largo_plazo')),
         'descripcion': ('Diagnóstico y alternativas de inversión del horizonte, con la solución integral y definitiva; '
                         'plantea las obras, no las aplica.'),
         'obras_admitidas': corto + largo, 'obras_excluidas': [], 'aplica_obras': False},
    ]
    return {'norma': {'acto': fuente.get('acto', ''), 'titulo': fuente.get('titulo', ''), 'estado_juridico': estado,
                      'vigente': estado not in ('', 'proyecto'), 'nota': fuente.get('nota', '')},
            'estudio': estudio.resumen() if estudio else None, 'periodo_corto': periodo_corto,
            'ciclo_anios': horizonte.get('ciclo_anios'), 'tipos': tipos}
