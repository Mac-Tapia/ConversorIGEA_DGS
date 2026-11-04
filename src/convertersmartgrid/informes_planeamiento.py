"""Los entregables de un estudio, un documento ligero por módulo (072:RF-4, RF-13, RF-14, RF-17, RF-21).

El usuario, el 2026-11-02: «para que sea ligero, los informes se hagan por módulos y entregables». El
plan de largo plazo son el diagnóstico y la formulación de alternativas; el PIDE, la formulación en su
periodo, la evaluación técnica, la económica, la priorización y selección, y la propuesta. Cada módulo
sigue su artículo de la metodología paso a paso y lleva sus tablas y sus formatos del anexo.

Todos salen del mismo ``DatosPlaneamiento``: el PIDE consume el largo plazo y no lo vuelve a calcular,
porque dos cálculos del mismo estudio podrían no coincidir. Solo se presenta lo que ya se midió; lo que
falta se dice en su sitio con su motivo.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .estudio_planeamiento import Estudio
from .formatos_pide import huecos_de
from .informe_docx import Escritor, guardar_informe, preparar_modelo
from .informes import InformeError, filas_alternativas_escalera, notas_alternativas_escalera
from .pide import FORMATOS

#: Filas de un formato que caben en el Word; el libro de formatos lleva todas.
TOPE_DE_FILAS = 60
#: Puntos de la letra en las tablas.
TAMANO_DE_TABLA = 8

#: Columna del año en los formatos que lo llevan, para quedarse con el periodo del PIDE.
_COLUMNA_ANIO = {'F08': 0, 'F09': 0, 'F10': 0, 'F11': 1, 'F12': 1, 'F13': 1}
#: Columna del código de obra en las fichas, que no llevan año.
_COLUMNA_CODIGO = {'F14': 0, 'F15': 0}


@dataclass(frozen=True)
class DatosPlaneamiento:
    """Lo que ya calculó un estudio; el modelo y los rótulos vienen del perfil de la empresa."""

    estudio: Estudio
    formatos: Mapping[str, Any]
    articulos: Sequence[Mapping[str, Any]] = ()
    anios: Sequence[Mapping[str, Any]] = ()
    obras: Sequence[Mapping[str, Any]] = ()
    con_y_sin: Mapping[str, Any] = field(default_factory=dict)
    empresa: str | None = None
    proyecto: str | None = None
    metodo_proyeccion: str | None = None
    modelo: Path | None = None
    rotulos_cabecera: Mapping[str, str] = field(default_factory=dict)
    #: 042:RF-58: hasta 3 alternativas por alimentador, de menor a mayor costo anual.
    alternativas_escalera: Mapping[str, Any] = field(default_factory=dict)


class _EscritorDeModulo(Escritor):
    """Tablas compactas y títulos separados: F13 tiene 15 columnas, y a letra normal partía «Año» en dos líneas."""

    def titulo(self, texto: str) -> None:
        from docx.shared import Pt

        super().titulo(texto)
        self.d.paragraphs[-1].paragraph_format.space_before = Pt(12)

    def tabla(self, cabecera: Sequence[str], filas: Sequence[Sequence[str]]) -> None:
        from docx.shared import Pt

        super().tabla(cabecera, filas)
        for fila in self.d.tables[-1].rows:
            for celda in fila.cells:
                for parrafo in celda.paragraphs:
                    for trozo in parrafo.runs:
                        trozo.font.size = Pt(TAMANO_DE_TABLA)


def _documento(datos: DatosPlaneamiento, titulo: str):
    """El modelo de la empresa si su perfil lo da; sin él, un documento apaisado en blanco y no un error."""
    if datos.modelo is None:
        import docx
        from docx.enum.section import WD_ORIENT

        documento = docx.Document()
        seccion = documento.sections[0]
        seccion.orientation = WD_ORIENT.LANDSCAPE
        seccion.page_width, seccion.page_height = seccion.page_height, seccion.page_width
        return documento
    if not Path(datos.modelo).is_file():
        raise InformeError(f'No existe el modelo de los informes de planeamiento: {datos.modelo}.')
    return preparar_modelo(Path(datos.modelo), datos.rotulos_cabecera, {'referencia': titulo})


def _texto(valor: Any) -> str:
    if valor is None or valor == '':
        return ''
    if isinstance(valor, float):
        return f'{valor:,.2f}'
    return str(valor)


def _nombre_del_formato(codigo: str) -> str:
    return next(n for n in FORMATOS if n.split()[0] == codigo)


def _generalidades(e: Escritor, datos: DatosPlaneamiento) -> None:
    est = datos.estudio
    e.campo('Empresa: ', datos.empresa, 'nombre de la empresa («empresa» del perfil)')
    e.campo('Proyecto de DIgSILENT: ', datos.proyecto, 'proyecto del estudio')
    e.parrafo(f'Año de presentación: {est.anio_presentacion}. Año base (00): {est.anio_base}.')


def _metodologia(e: Escritor, datos: DatosPlaneamiento, numeros: Sequence[int]) -> None:
    """El paso a paso del módulo, con las palabras de la metodología y no con unas propias."""
    filas = [a for a in datos.articulos if a['numero'] in numeros]
    if not filas:
        e.hueco('metodología: el estudio no trae los artículos de este módulo')
        return
    e.tabla(('Art.', 'Paso', 'Entradas', 'Procedimiento', 'Evidencias', 'Entregables'),
            [[str(a['numero']), a['titulo'], '; '.join(a['entradas']), '; '.join(a['procedimiento']),
              '; '.join(a['evidencias']), '; '.join(a['entregables'])] for a in filas])


def _tabla_de_formato(e: Escritor, datos: DatosPlaneamiento, codigo: str, filas: Sequence[Sequence[Any]] | None = None) -> None:
    """Un formato: sus filas hasta el tope, o por qué no tiene ninguna."""
    nombre = _nombre_del_formato(codigo)
    filas = (datos.formatos['filas'].get(nombre) or []) if filas is None else filas
    e.titulo(nombre)
    if not filas:
        motivo = next((h['motivo'] for h in datos.formatos['huecos'] if h['formato'] == nombre and h.get('campo') is None),
                      'sin filas en este periodo')
        e.parrafo(f'Sin datos: {motivo}.')
        return
    e.tabla(FORMATOS[nombre], [[_texto(c) for c in f] for f in filas[:TOPE_DE_FILAS]])
    if len(filas) > TOPE_DE_FILAS:
        e.parrafo(f'Se muestran {TOPE_DE_FILAS} de {len(filas)} filas; el libro de formatos las lleva todas.')


def _cuantos(problemas: Any) -> int:
    """El resultado de la web guarda el número; el informe de DIgSILENT, la lista."""
    return problemas if isinstance(problemas, int) else len(problemas or [])


def _f01_en_anios_del_estudio(datos: DatosPlaneamiento) -> list[list]:
    """F01 en el Word solo en el año base y los de largo plazo: el libro lleva todos los años."""
    est = datos.estudio
    anios = {est.anio_base, *(est.calendario(a) for a in est.largo_plazo)}
    return [f for f in datos.formatos['filas'].get('F01 Proyección') or [] if f[1] in anios]


def _del_periodo(datos: DatosPlaneamiento, codigo: str) -> list[list]:
    """Las filas de un formato del PIDE que son de su periodo: lo posterior es de largo plazo."""
    ultimo = max(datos.estudio.detalle_pide)
    filas = datos.formatos['filas'].get(_nombre_del_formato(codigo)) or []
    if codigo in _COLUMNA_ANIO:
        return [f for f in filas if f[_COLUMNA_ANIO[codigo]] <= ultimo]
    del_periodo = {o['codigo'] for o in datos.obras if o['anio'] <= ultimo}
    return [f for f in filas if f[_COLUMNA_CODIGO[codigo]] in del_periodo]


# ------------------------------------------------------------------ cuerpo de cada módulo
def _diagnostico(e: Escritor, datos: DatosPlaneamiento) -> None:
    est = datos.estudio
    e.titulo('Análisis del mercado eléctrico')
    e.campo('Método de proyección, elegido contra lo ocurrido: ', datos.metodo_proyeccion, 'método de proyección')
    _tabla_de_formato(e, datos, 'F01', _f01_en_anios_del_estudio(datos))
    e.titulo('Diagnóstico de la red, año por año')
    e.parrafo('Años de largo plazo: ' + ', '.join(f'{a:02d} ({est.calendario(a)})' for a in est.largo_plazo) + '.')
    if datos.anios:
        e.tabla(('Año', 'Calendario', 'Converge', 'Tensión mínima p.u.', 'Problemas', 'Pérdidas kW'),
                [[f"{a['anio']:02d}", str(est.calendario(int(a['anio']))), 'sí' if a.get('converge') else 'no',
                  _texto(a.get('vm_min')), str(_cuantos(a.get('problemas'))), _texto(a.get('perdidas_kw'))] for a in datos.anios])
    else:
        e.hueco('diagnóstico: el estudio no trae años calculados')
    for codigo in ('F02', 'F03', 'F04', 'F05', 'F06'):
        _tabla_de_formato(e, datos, codigo)


def _alternativas_por_alimentador(e: Escritor, datos: DatosPlaneamiento) -> None:
    if datos.alternativas_escalera:                                             # 042:RF-58
        e.titulo('Alternativas de solución por alimentador')
        e.parrafo('De menor a mayor costo anual; todas cumplen con la máxima en DIgSILENT.')
        e.tabla(*filas_alternativas_escalera(datos.alternativas_escalera))
        for nota in notas_alternativas_escalera(datos.alternativas_escalera):   # 042:RF-67
            e.parrafo(nota)


def _alternativas(e: Escritor, datos: DatosPlaneamiento) -> None:
    _tabla_de_formato(e, datos, 'F07')
    _alternativas_por_alimentador(e, datos)
    e.titulo('Plan de obras de largo plazo')
    cartera = [o for o in datos.obras if not (o.get('descartada') or o.get('sobredimensionada'))]
    if not cartera:
        e.parrafo('Ninguna obra quedó en la cartera.')
        return
    e.tabla(('Año', 'Código', 'Alternativa', 'Alimentador', 'Causa', 'Costo US$', 'Aplicada en DIgSILENT'),
            [[f"{o['anio']:02d}", o['codigo'], o['alternativa'], str(o.get('alimentador') or ''), o['causa'],
              _texto(o.get('ci') or None), o.get('variacion_autonoma') or 'no'] for o in sorted(cartera, key=lambda x: x['anio'])])


def _formulacion_pide(e: Escritor, datos: DatosPlaneamiento) -> None:
    est = datos.estudio
    e.parrafo('Años de detalle del PIDE: ' + ', '.join(f'{a:02d} ({est.calendario(a)})' for a in est.detalle_pide) + '.')
    e.parrafo('Las cifras son las del estudio de largo plazo del mismo proyecto, sin recalcular.')
    _tabla_de_formato(e, datos, 'F08', _del_periodo(datos, 'F08'))
    _alternativas_por_alimentador(e, datos)


def _evaluacion_tecnica(e: Escritor, datos: DatosPlaneamiento) -> None:
    filas = [a for a in datos.anios if a.get('con_proyecto')]
    if not filas:
        e.parrafo('Sin medir: ninguna obra se aplicó en «Con proyecto», así que no hay caso con obras por año (072:RF-12).')
        return
    e.tabla(('Año', 'Obras acumuladas', 'Converge', 'Problemas sin obras', 'Problemas con obras', 'Pérdidas sin obras kW',
             'Pérdidas con obras kW'),
            [[f"{a['anio']:02d}", ', '.join(a['con_proyecto'].get('obras') or []) or 'ninguna',
              'sí' if a['con_proyecto'].get('converge') else 'no', str(_cuantos(a.get('problemas'))),
              str(_cuantos(a['con_proyecto'].get('problemas'))), _texto(a.get('perdidas_kw')),
              _texto(a['con_proyecto'].get('perdidas_kw'))] for a in filas])


def _evaluacion_economica(e: Escritor, datos: DatosPlaneamiento) -> None:
    con_y_sin = datos.con_y_sin
    e.titulo('Con y sin proyecto')
    if not con_y_sin or con_y_sin.get('hueco'):
        e.parrafo('Sin evaluar: ' + (con_y_sin.get('hueco') or 'el estudio no trae la comparación') + '.')
    else:
        tir = con_y_sin.get('tir')
        e.tabla(('Indicador', 'Valor'), [['VAN US$ (tasa regulada)', _texto(con_y_sin.get('van'))],
                                         ['TIR', f'{tir:.2%}' if tir is not None else 'no tiene: el ahorro no recupera la inversión']])
        e.parrafo('Solo mide el ahorro de pérdidas entre los dos casos de cada año. La energía no servida y la calidad de '
                  'suministro no entran en este flujo, de modo que un VAN negativo no dice por sí solo que la obra no se justifique.')
        for aviso in con_y_sin.get('avisos') or []:
            e.parrafo(f'Aviso: {aviso}.')
    _tabla_de_formato(e, datos, 'F09', _del_periodo(datos, 'F09'))


def _priorizacion(e: Escritor, datos: DatosPlaneamiento) -> None:
    ultimo = max(datos.estudio.detalle_pide)
    del_periodo = [o for o in datos.obras if o['anio'] <= ultimo]
    if not del_periodo:
        e.parrafo('Ninguna obra en este periodo.')
        return
    e.tabla(('Prioridad', 'Código', 'Alternativa', 'Puntaje', 'Situación'),
            [[str(o.get('prioridad') or ''), o['codigo'], o['alternativa'], _texto(o.get('puntaje')),
              'descartada' if o.get('descartada') else 'sobredimensionada' if o.get('sobredimensionada') else 'seleccionada']
             for o in sorted(del_periodo, key=lambda x: x.get('prioridad') or 0)])


def _propuesta(e: Escritor, datos: DatosPlaneamiento) -> None:
    for codigo in ('F10', 'F11', 'F12', 'F13', 'F14', 'F15'):
        _tabla_de_formato(e, datos, codigo, _del_periodo(datos, codigo))


@dataclass(frozen=True)
class Modulo:
    clave: str
    entregable: str
    titulo: str
    articulos: tuple[int, ...]
    formatos: tuple[str, ...]
    cuerpo: Callable[[Escritor, DatosPlaneamiento], None]


#: En el orden que dio el usuario el 2026-11-02; los artículos y formatos, los de la metodología.
MODULOS = (
    Modulo('diagnostico', 'Plan de largo plazo', 'Diagnóstico', (7, 8), ('F01', 'F02', 'F03', 'F04', 'F05', 'F06'), _diagnostico),
    Modulo('alternativas', 'Plan de largo plazo', 'Formulación de alternativas de inversión', (9, 10), ('F07',), _alternativas),
    Modulo('formulacion_pide', 'PIDE', 'Formulación de alternativas del periodo', (11, 12), ('F08',), _formulacion_pide),
    Modulo('evaluacion_tecnica', 'PIDE', 'Evaluación técnica', (13,), (), _evaluacion_tecnica),
    Modulo('evaluacion_economica', 'PIDE', 'Evaluación económica', (14,), ('F09',), _evaluacion_economica),
    Modulo('priorizacion', 'PIDE', 'Priorización y selección', (15,), (), _priorizacion),
    Modulo('propuesta_pide', 'PIDE', 'Propuesta del PIDE', (16, 17), ('F10', 'F11', 'F12', 'F13', 'F14', 'F15'), _propuesta),
)


def _huecos_del_modulo(modulo: Modulo, datos: DatosPlaneamiento) -> list[dict[str, Any]]:
    """Lo que le falta a lo que el módulo muestra: el PIDE no cuenta las obras posteriores a su periodo."""
    if modulo.entregable == 'PIDE':
        visibles = {_nombre_del_formato(c): _del_periodo(datos, c) for c in modulo.formatos}
        return [h for h in huecos_de(visibles) if h['formato'] in visibles]
    return [h for h in datos.formatos['huecos'] if h['formato'].split()[0] in modulo.formatos]


def _agrupados(huecos: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    """Una fila por formato y motivo: F13 repetía la misma frase por cada una de sus nueve columnas."""
    grupos: dict[tuple[str, str], list[str]] = {}
    for h in huecos:
        grupos.setdefault((h['formato'], h['motivo']), []).append(h.get('campo') or '(todo el formato)')
    return [[formato, ', '.join(campos), motivo] for (formato, motivo), campos in grupos.items()]


def escribir_modulo(destino: Path, modulo: Modulo, datos: DatosPlaneamiento) -> list[str]:
    """Un módulo: su metodología, sus tablas y formatos, y lo que le falta (072:RF-21)."""
    titulo = f'{modulo.entregable}: {modulo.titulo}'
    e = _EscritorDeModulo(_documento(datos, titulo))
    e.titulo(titulo.upper())
    _generalidades(e, datos)
    e.titulo('Metodología')
    _metodologia(e, datos, modulo.articulos)
    e.titulo('Resultados')
    modulo.cuerpo(e, datos)
    e.titulo('Datos que faltan')
    huecos = _huecos_del_modulo(modulo, datos)
    if huecos:
        e.tabla(('Formato', 'Campos', 'Motivo'), _agrupados(huecos))
    else:
        e.parrafo('Ninguno en sus formatos.')
    guardar_informe(e.d, destino, {'modulo': modulo.clave, 'entregable': modulo.entregable, 'estudio': datos.estudio.resumen(),
                                   'huecos': huecos, 'por_llenar': e.huecos})
    return e.huecos


def escribir_modulos(carpeta: Path, sufijo: str, datos: DatosPlaneamiento) -> tuple[list[str], list[str]]:
    """Todos los módulos; uno que falle no pierde a los demás. Devuelve (ficheros, fallos)."""
    hechos, fallos = [], []
    for i, modulo in enumerate(MODULOS, start=1):
        nombre = f'{i}_{modulo.clave}_{sufijo}.docx'
        try:
            escribir_modulo(Path(carpeta) / nombre, modulo, datos)
            hechos.append(nombre)
        except (InformeError, OSError) as exc:
            fallos.append(f'{nombre}: {exc}')
    return hechos, fallos
