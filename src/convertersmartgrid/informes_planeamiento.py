"""Los dos entregables de un estudio: largo plazo y PIDE (072:RF-4, RF-13, RF-14, RF-17).

Los dos salen del mismo ``DatosPlaneamiento``: el PIDE consume el largo plazo y no lo vuelve a calcular,
porque dos cálculos del mismo estudio podrían no coincidir. Aquí solo se presenta lo que ya se midió; no
hay texto de análisis que no salga de un dato, y lo que falta se dice en su sitio con su motivo.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .estudio_planeamiento import Estudio
from .informe_docx import Escritor, guardar_informe, preparar_modelo
from .informes import InformeError
from .pide import FORMATOS

#: Filas de un formato que caben en el Word; el libro de formatos lleva todas.
TOPE_DE_FILAS = 60

FORMATOS_LARGO_PLAZO = ('F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07')
FORMATOS_PIDE = ('F08', 'F09', 'F10', 'F11', 'F12', 'F13', 'F14', 'F15')
#: Columna del año en los formatos que lo llevan, para quedarse con el periodo del PIDE.
_COLUMNA_ANIO = {'F08': 0, 'F09': 0, 'F10': 0, 'F11': 1, 'F12': 1, 'F13': 1}
#: Columna del código de obra en las fichas, que no llevan año.
_COLUMNA_CODIGO = {'F14': 0, 'F15': 0}


@dataclass(frozen=True)
class DatosPlaneamiento:
    """Lo que ya calculó un estudio; las rutas de los modelos vienen del perfil de la empresa."""

    estudio: Estudio
    formatos: Mapping[str, Any]
    anios: Sequence[Mapping[str, Any]] = ()
    obras: Sequence[Mapping[str, Any]] = ()
    con_y_sin: Mapping[str, Any] = field(default_factory=dict)
    empresa: str | None = None
    proyecto: str | None = None
    metodo_proyeccion: str | None = None
    modelos: Mapping[str, Path | None] = field(default_factory=dict)
    rotulos_cabecera: Mapping[str, str] = field(default_factory=dict)


def _documento(datos: DatosPlaneamiento, tipo: str, titulo: str):
    """El modelo de la empresa si su perfil lo da; sin él, un documento en blanco y no un error."""
    modelo = datos.modelos.get(tipo)
    if modelo is None:
        import docx

        return docx.Document()
    if not Path(modelo).is_file():
        raise InformeError(f'No existe el modelo del informe de {titulo}: {modelo}.')
    return preparar_modelo(Path(modelo), datos.rotulos_cabecera, {'referencia': titulo})


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
    e.parrafo('Años de largo plazo: ' + ', '.join(f'{a:02d} ({est.calendario(a)})' for a in est.largo_plazo) + '.')
    e.parrafo('Años de detalle del PIDE: ' + ', '.join(f'{a:02d} ({est.calendario(a)})' for a in est.detalle_pide) + '.')


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


def _diagnostico(e: Escritor, datos: DatosPlaneamiento) -> None:
    if not datos.anios:
        e.hueco('diagnóstico: el estudio no trae años calculados')
        return
    e.tabla(('Año', 'Calendario', 'Converge', 'Tensión mínima p.u.', 'Problemas', 'Pérdidas kW'),
            [[f"{a['anio']:02d}", str(datos.estudio.calendario(int(a['anio']))), 'sí' if a.get('converge') else 'no',
              _texto(a.get('vm_min')), str(_cuantos(a.get('problemas'))), _texto(a.get('perdidas_kw'))] for a in datos.anios])


def _cuantos(problemas: Any) -> int:
    """El resultado de la web guarda el número; el informe de DIgSILENT, la lista."""
    return problemas if isinstance(problemas, int) else len(problemas or [])


def _con_obras(e: Escritor, datos: DatosPlaneamiento) -> None:
    filas = [a for a in datos.anios if a.get('con_proyecto')]
    if not filas:
        e.parrafo('Sin medir: ninguna obra se aplicó en «Con proyecto», así que no hay caso con obras por año (072:RF-12).')
        return
    e.tabla(('Año', 'Obras acumuladas', 'Converge', 'Problemas que quedan', 'Pérdidas kW'),
            [[f"{a['anio']:02d}", ', '.join(a['con_proyecto'].get('obras') or []) or 'ninguna',
              'sí' if a['con_proyecto'].get('converge') else 'no', str(_cuantos(a['con_proyecto'].get('problemas'))),
              _texto(a['con_proyecto'].get('perdidas_kw'))] for a in filas])


def _huecos(e: Escritor, datos: DatosPlaneamiento, codigos: Sequence[str]) -> list[dict]:
    propios = [h for h in datos.formatos['huecos'] if h['formato'].split()[0] in codigos]
    if propios:
        e.tabla(('Formato', 'Campo', 'Filas', 'Motivo'),
                [[h['formato'], h.get('campo') or '(todo el formato)', str(h.get('filas') or ''), h['motivo']] for h in propios])
    else:
        e.parrafo('Ninguno.')
    return propios


def escribir_informe_largo_plazo(destino: Path, datos: DatosPlaneamiento) -> list[str]:
    """El estudio de largo plazo: mercado, diagnóstico, alternativas y plan de obras (072:RF-13)."""
    e = Escritor(_documento(datos, 'largo_plazo', 'Estudio de planeamiento de largo plazo'))
    e.titulo('ESTUDIO DE PLANEAMIENTO DE LARGO PLAZO')
    e.titulo('1. GENERALIDADES')
    _generalidades(e, datos)
    e.titulo('2. ANÁLISIS DEL MERCADO ELÉCTRICO')
    e.campo('Método de proyección, elegido contra lo ocurrido: ', datos.metodo_proyeccion, 'método de proyección')
    _tabla_de_formato(e, datos, 'F01', _f01_en_anios_del_estudio(datos))
    e.titulo('3. DIAGNÓSTICO DE LA RED, AÑO POR AÑO')
    _diagnostico(e, datos)
    for codigo in ('F03', 'F04', 'F05', 'F06'):
        _tabla_de_formato(e, datos, codigo)
    e.titulo('4. METRADOS')
    _tabla_de_formato(e, datos, 'F02')
    e.titulo('5. ALTERNATIVAS Y ANÁLISIS TÉCNICO-ECONÓMICO')
    _tabla_de_formato(e, datos, 'F07')
    e.titulo('6. PLAN DE OBRAS')
    _plan_de_obras(e, datos.obras)
    _con_obras(e, datos)
    e.titulo('7. DATOS QUE FALTAN')
    huecos = _huecos(e, datos, FORMATOS_LARGO_PLAZO)
    guardar_informe(e.d, destino, {'tipo': 'largo_plazo', 'estudio': datos.estudio.resumen(), 'huecos': huecos, 'por_llenar': e.huecos})
    return e.huecos


def _f01_en_anios_del_estudio(datos: DatosPlaneamiento) -> list[list]:
    """F01 en el Word solo en el año base y los de largo plazo: el libro lleva todos los años."""
    est = datos.estudio
    anios = {est.anio_base, *(est.calendario(a) for a in est.largo_plazo)}
    return [f for f in datos.formatos['filas'].get('F01 Proyección') or [] if f[1] in anios]


def _plan_de_obras(e: Escritor, obras: Sequence[Mapping[str, Any]]) -> None:
    cartera = [o for o in obras if not (o.get('descartada') or o.get('sobredimensionada'))]
    if not cartera:
        e.parrafo('Ninguna obra quedó en la cartera.')
        return
    e.tabla(('Año', 'Código', 'Alternativa', 'Alimentador', 'Causa', 'Costo US$', 'Aplicada en DIgSILENT'),
            [[f"{o['anio']:02d}", o['codigo'], o['alternativa'], str(o.get('alimentador') or ''), o['causa'],
              _texto(o.get('ci') or None), o.get('variacion_autonoma') or 'no'] for o in sorted(cartera, key=lambda x: x['anio'])])


def _del_periodo(datos: DatosPlaneamiento, codigo: str) -> list[list]:
    """Las filas de un formato del PIDE que son de su periodo: lo posterior es de largo plazo."""
    ultimo = max(datos.estudio.detalle_pide)
    filas = datos.formatos['filas'].get(_nombre_del_formato(codigo)) or []
    if codigo in _COLUMNA_ANIO:
        return [f for f in filas if f[_COLUMNA_ANIO[codigo]] <= ultimo]
    del_periodo = {o['codigo'] for o in datos.obras if o['anio'] <= ultimo}
    return [f for f in filas if f[_COLUMNA_CODIGO[codigo]] in del_periodo]


def _evaluacion(e: Escritor, con_y_sin: Mapping[str, Any]) -> None:
    if not con_y_sin or con_y_sin.get('hueco'):
        e.parrafo('Sin evaluar: ' + (con_y_sin.get('hueco') or 'el estudio no trae la comparación') + '.')
        return
    tir = con_y_sin.get('tir')
    e.tabla(('Indicador', 'Valor'), [['VAN US$ (tasa regulada)', _texto(con_y_sin.get('van'))],
                                     ['TIR', f'{tir:.2%}' if tir is not None else 'no tiene: el ahorro no recupera la inversión']])
    e.parrafo('Solo mide el ahorro de pérdidas entre los dos casos de cada año. La energía no servida y la calidad de '
              'suministro no entran en este flujo, de modo que un VAN negativo no dice por sí solo que la obra no se justifique.')
    for aviso in con_y_sin.get('avisos') or []:
        e.parrafo(f'Aviso: {aviso}.')


def _priorizacion(e: Escritor, obras: Sequence[Mapping[str, Any]], ultimo: int) -> None:
    del_periodo = [o for o in obras if o['anio'] <= ultimo]
    if not del_periodo:
        e.parrafo('Ninguna obra en este periodo.')
        return
    e.tabla(('Prioridad', 'Código', 'Alternativa', 'Puntaje', 'Situación'),
            [[str(o.get('prioridad') or ''), o['codigo'], o['alternativa'], _texto(o.get('puntaje')),
              'descartada' if o.get('descartada') else 'sobredimensionada' if o.get('sobredimensionada') else 'en cartera']
             for o in sorted(del_periodo, key=lambda x: x.get('prioridad') or 0)])


def escribir_informe_pide(destino: Path, datos: DatosPlaneamiento) -> list[str]:
    """El PIDE: alternativas, evaluación, priorización y propuesta de su periodo (072:RF-4, RF-14)."""
    e = Escritor(_documento(datos, 'pide', 'Plan de Inversiones en Distribución Eléctrica'))
    ultimo = max(datos.estudio.detalle_pide)
    e.titulo('PLAN DE INVERSIONES EN DISTRIBUCIÓN ELÉCTRICA (PIDE)')
    e.titulo('1. GENERALIDADES')
    _generalidades(e, datos)
    e.parrafo('Las cifras de este plan son las del estudio de largo plazo del mismo proyecto, sin recalcular.')
    e.titulo('2. ALTERNATIVAS DEL PERIODO')
    _tabla_de_formato(e, datos, 'F08', _del_periodo(datos, 'F08'))
    e.titulo('3. EVALUACIÓN TÉCNICA')
    _con_obras(e, datos)
    e.titulo('4. EVALUACIÓN ECONÓMICA CON Y SIN PROYECTO')
    _evaluacion(e, datos.con_y_sin)
    _tabla_de_formato(e, datos, 'F09', _del_periodo(datos, 'F09'))
    e.titulo('5. PRIORIZACIÓN')
    _priorizacion(e, datos.obras, ultimo)
    e.titulo('6. PROPUESTA')
    for codigo in ('F10', 'F11', 'F12', 'F13', 'F14', 'F15'):
        _tabla_de_formato(e, datos, codigo, _del_periodo(datos, codigo))
    e.titulo('7. DATOS QUE FALTAN')
    huecos = _huecos(e, datos, FORMATOS_PIDE)
    guardar_informe(e.d, destino, {'tipo': 'pide', 'estudio': datos.estudio.resumen(), 'con_y_sin': datos.con_y_sin, 'huecos': huecos,
                            'por_llenar': e.huecos})
    return e.huecos
