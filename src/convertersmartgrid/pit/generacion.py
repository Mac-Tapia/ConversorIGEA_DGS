"""F-124, datos de generación del área, deducidos de la medición de las centrales (107:RF-9; tarjeta PIT-F124).

La empresa no declara su generación en ningún libro que el conversor lea, pero sí mide sus centrales térmicas: el
perfil las declara en ``centrales_termicas`` (alimentador → medidores de generación, llegada y salida, 021:RF-27), y la
calibración ya las lee de los libros de cabecera. De ese medidor de generación salen, por central:

- la central (el alimentador del perfil y su medidor) y un solo grupo, «medido en conjunto»: el medidor no separa los
  grupos de la central;
- la capacidad efectiva como la **máxima potencia medida** en el periodo (MW), anotada así: es una deducción de la
  medición de cabecera, no la capacidad declarada de la central;
- el sustento, con el medidor, el periodo y el número de registros.

Lo que la medición no da (el titular de la generación, el año de ingreso en operación, el tipo de sistema) sale vacío
con su aviso, salvo que quien llama lo traiga. Sin centrales en el perfil, el formato sale vacío con ese aviso.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = ['DEDUCIDA', 'datos_f124', 'generacion_medida']

DEDUCIDA = 'máxima potencia medida en la cabecera de la central: deducida de la medición, no capacidad declarada'


def generacion_medida(rutas: Sequence[Path | str], centrales: Mapping[str, Mapping[str, str]]
                      ) -> tuple[dict[str, list[tuple[Any, float, float | None]]], dict[str, Any], list[str]]:
    """La curva del medidor de generación de cada central del perfil, desde los libros de cabecera (el mismo lector
    que la calibración). Lo que no se lee vuelve como hueco con su motivo."""
    from .. import pronostico_demanda

    pares = [(alimentador, c['generacion']) for alimentador, c in centrales.items()]
    if not pares:
        return {}, {}, []
    leidas, apartados = pronostico_demanda.curvas_de_cabecera(rutas, pares)
    return ({a: list(i['curva']) for a, i in leidas.items()}, {a: i['fuente'] for a, i in leidas.items()},
            [f'{ap["objetivo"]}: {ap["motivo"]}' for ap in apartados])


def datos_f124(centrales: Mapping[str, Mapping[str, str]], curvas: Mapping[str, Sequence[tuple[Any, float, Any]]],
               fuente: Mapping[str, str], *, area: str | None = None, titular: str | None = None,
               tipo_sistema: str | None = None, huecos: Sequence[str] = ()) -> dict[str, Any]:
    """Los datos de F-124 para el motor de plantillas: una fila por central medida."""
    filas = []
    avisos = list(huecos)
    if not centrales:
        avisos.append('el perfil no declara centrales (centrales_termicas): el F-124 sale vacío')
    for alimentador, c in centrales.items():
        curva = list(curvas.get(alimentador) or ())
        motivos = {'anio': 'la medición no da el año de ingreso en operación de la central',
                   '_calculo:capacidad_mw': DEDUCIDA}
        if titular is None:
            motivos['titular'] = 'la medición no da el titular de la generación'
        fila: dict[str, Any] = {'titular': titular, 'central': f'{alimentador} (medidor {c["generacion"]})',
                                'anio': None, 'grupo': 'Grupo 1 (medido en conjunto)', '_motivos': motivos}
        if not curva:
            fila.update(capacidad_mw=None, sustento=None)
            motivos['capacidad_mw'] = motivos['sustento'] = f'sin curva del medidor de generación {c["generacion"]}'
            avisos.append(f'central {alimentador}: sin curva de su medidor de generación')
        else:
            potencias = [abs(p) for _t, p, _q in curva]
            instantes = [t for t, _p, _q in curva]
            fila['capacidad_mw'] = round(max(potencias) / 1000, 4)
            fila['sustento'] = (f'medición de cabecera del medidor {c["generacion"]} del {min(instantes):%Y-%m-%d} al '
                                f'{max(instantes):%Y-%m-%d} ({len(curva)} registros); {DEDUCIDA}')
        filas.append(fila)
    cabecera = {'area': area, 'tipo_sistema': tipo_sistema}
    return {'fuente': fuente, 'cabecera': cabecera, 'bloques': {'grupos': filas}, 'avisos': avisos,
            '_motivos_cabecera': {'tipo_sistema': 'la medición no da el tipo de sistema (SSTG, SSTGD, SCTG o SCTGD)'}}
