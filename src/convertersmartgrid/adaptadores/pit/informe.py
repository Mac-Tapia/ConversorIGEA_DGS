"""Resumen ejecutivo del estudio del PIT: demanda, alternativa elegida y programa de inversiones (107:RF-13).

Por qué así. El resumen es lo primero que lee el regulador, y una cifra suya que no coincida con el cuerpo del
expediente es una observación segura. Por eso no se calcula nada aquí: cada cifra se toma de lo que el expediente ya
escribió (``diagnostico.json``, ``alternativas.json`` y ``programa.json``), y cada apartado cita el fichero del que sale
con su huella. ``resumen_ejecutivo`` trabaja sobre esos datos tal como se escriben; ``desde_carpeta`` los lee de un
expediente emitido y da exactamente lo mismo.

La alternativa elegida la nombra el operador: el resumen no la elige, y una alternativa que no está en la comparación,
o que quedó incompleta, es un error que la nombra.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ...dominio.pit import PitError

__all__ = ['FICHEROS', 'desde_carpeta', 'resumen_ejecutivo']

#: Apartado del resumen → fichero del expediente del que sale.
FICHEROS = {'demanda': 'diagnostico.json', 'alternativa': 'alternativas.json', 'programa': 'programa.json'}


def resumen_ejecutivo(diagnostico: Mapping[str, Any], alternativas: Mapping[str, Any], programa: Mapping[str, Any],
                      alternativa: str, huellas: Mapping[str, str]) -> dict[str, Any]:
    """Los tres apartados del resumen desde los datos del expediente; ``huellas``: fichero → sha256."""
    faltan = [f for f in FICHEROS.values() if not huellas.get(f)]
    if faltan:
        raise PitError(f'el resumen ejecutivo cita sus fuentes: falta la huella de {faltan}')
    elegida = next((a for a in alternativas.get('alternativas') or () if a.get('nombre') == alternativa), None)
    if elegida is None:
        nombres = [a.get('nombre') for a in alternativas.get('alternativas') or ()]
        raise PitError(f'la alternativa elegida {alternativa!r} no está en la comparación del expediente ({nombres})')
    if not elegida.get('completa'):
        raise PitError(f'la alternativa elegida {alternativa!r} está incompleta: {elegida.get("motivos")}')

    def fuente(apartado: str) -> dict[str, str]:
        fichero = FICHEROS[apartado]
        return {'fichero': fichero, 'sha256': huellas[fichero]}

    orden = list(alternativas.get('orden') or ())
    filas = list(programa.get('filas') or ())
    por_anio: dict[int, int] = {}
    por_titular: dict[str, int] = {}
    for f in filas:
        por_anio[int(f['anio'])] = por_anio.get(int(f['anio']), 0) + 1
        por_titular[str(f['titular'])] = por_titular.get(str(f['titular']), 0) + 1
    avisos = []
    if orden and orden[0] != alternativa:
        avisos.append(f'la alternativa elegida ({alternativa}) no es la de menor valor presente ({orden[0]}): '
                      'el expediente tiene que sustentar la elección')
    if diagnostico.get('sin_demanda'):
        avisos.append(f'años sin demanda proyectada: {diagnostico["sin_demanda"]}')
    if not diagnostico.get('completo'):
        avisos.append('el diagnóstico no está completo (faltantes, compartidos sin asignar, años sin demanda o '
                      'cancelación): ver diagnostico.json')
    return {
        'estudio': 'PIT', 'area': diagnostico.get('area'),
        'demanda': {'fuente': fuente('demanda'), 'motor': diagnostico.get('motor'),
                    'por_anio': [{'anio': a['anio'], 'demanda_mw': a['demanda_mw']}
                                 for a in diagnostico.get('anios') or ()],
                    'sin_demanda': list(diagnostico.get('sin_demanda') or ())},
        'alternativa': {'fuente': fuente('alternativa'), 'nombre': alternativa,
                        'posicion': orden.index(alternativa) + 1 if alternativa in orden else None,
                        'de': len(orden), 'inversion': elegida.get('inversion') or {},
                        'coym_anual': elegida.get('coym_anual') or {},
                        'valor_presente': elegida.get('valor_presente') or {},
                        'motor': alternativas.get('motor'), 'demanda_huella': alternativas.get('demanda_huella')},
        'programa': {'fuente': fuente('programa'),
                     'filas': [{k: f.get(k) for k in ('anio', 'accion', 'elemento', 'titular', 'instalacion')}
                               for f in filas],
                     'por_anio': [{'anio': a, 'filas': n} for a, n in sorted(por_anio.items())],
                     'por_titular': dict(sorted(por_titular.items()))},
        'avisos': avisos,
    }


def desde_carpeta(carpeta: Path | str, alternativa: str) -> dict[str, Any]:
    """El resumen de un expediente emitido, leído de sus ficheros; el que falta es un error que lo nombra."""
    carpeta = Path(carpeta)
    datos, huellas = {}, {}
    for fichero in FICHEROS.values():
        ruta = carpeta / fichero
        if not ruta.is_file():
            raise PitError(f'{carpeta.name}: falta {fichero}, y el resumen ejecutivo no inventa sus cifras')
        crudo = ruta.read_bytes()
        huellas[fichero] = hashlib.sha256(crudo).hexdigest()
        datos[fichero] = json.loads(crudo.decode('utf-8'))
    return resumen_ejecutivo(datos[FICHEROS['demanda']], datos[FICHEROS['alternativa']], datos[FICHEROS['programa']],
                             alternativa, huellas)
