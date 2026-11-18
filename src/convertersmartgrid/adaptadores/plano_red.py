"""El plano de la red (spec 111): cada elemento por su código de la fuente y la revisión de la red.

- Identidad (111:RF-2): barra (``node_id``), tramo (``section_id``), SED (su código) y maniobra (su número de equipo),
  con el nombre que les da el DGS en DIgSILENT, calculado con ``dgs.nombre_en_pf`` y nunca con una copia de la regla.
  Dos códigos que dan el mismo nombre en la misma clase se avisan, y ese nombre no se traduce a ninguno: un resultado
  de DIgSILENT nunca se pinta en otro elemento.
- Vista del plano (111:RF-1, RF-3): por alimentador, todos los vértices de su fuente sin simplificar; por elemento,
  su dato original, lo deducido con su regla y su motivo, y su estado de calidad. Una doble terna son dos elementos en
  el mismo trazo; un alimentador sin coordenadas se lista y no se pinta.
- Revisión de la red (111:RF-11): la huella SHA-256 del ``run_id`` de la fuente y de los manifiestos
  ``<alimentador>_geography.json`` elegidos. Cada variación y cada resultado la llevan; uno de otra revisión no se
  pinta.

- Unifilar (111:RF-23): cada vista lleva su cabecera (``fuente``) y el nivel y el orden de cada barra desde ella
  (``dominio.disposicion_unifilar``, la misma regla que el unifilar del PIT); los tramos, las SED y las maniobras se
  pintan con sus códigos de la vista.

Solo lee: no cambia el modelo, la geografía ni el DGS.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .dgs import letras_de_fase, nombre_en_pf
from ..dominio.disposicion_unifilar import unifilar_de_vista
from ..dominio.model import FeederModel


def codigo_de_maniobra(dev) -> str:
    """El código de la fuente de una maniobra: su número de equipo, su identificador o su tramo."""
    return dev.eq_number or dev.eq_id or dev.section_id


def identidad(model: FeederModel) -> dict[str, Any]:
    """Los elementos del alimentador con su código de la fuente y su nombre en DIgSILENT, y las colisiones.

    Devuelve ``{'alimentador', 'elementos': [{tipo, codigo, nombre_pf}], 'colisiones': [{tipo, nombre_pf, codigos}]}``,
    en orden estable (tipo y código), para que dos lecturas iguales den lo mismo.
    """
    elementos: list[dict[str, str]] = []
    elementos += [{'tipo': 'barra', 'codigo': n, 'nombre_pf': nombre_en_pf(n)} for n in sorted(model.nodes)]
    elementos += [{'tipo': 'tramo', 'codigo': ln.section_id, 'nombre_pf': nombre_en_pf(ln.section_id)}
                  for ln in sorted(model.lines, key=lambda ln: ln.section_id)]
    elementos += [{'tipo': 'sed', 'codigo': s.code, 'nombre_pf': nombre_en_pf(s.loc_name)}
                  for s in sorted(model.seds, key=lambda s: (s.code, s.load_key))]
    # El DGS nombra el StaSwitch por su número de equipo, su identificador o su clase.
    elementos += [{'tipo': 'maniobra', 'codigo': codigo_de_maniobra(d),
                   'nombre_pf': nombre_en_pf(d.eq_number or d.eq_id or d.kind)}
                  for d in sorted(model.devices, key=lambda d: (codigo_de_maniobra(d), d.terminal_side))]
    por_nombre: dict[tuple[str, str], set[str]] = {}
    for e in elementos:
        por_nombre.setdefault((e['tipo'], e['nombre_pf']), set()).add(e['codigo'])
    colisiones = [{'tipo': tipo, 'nombre_pf': nombre, 'codigos': sorted(codigos)}
                  for (tipo, nombre), codigos in sorted(por_nombre.items()) if len(codigos) > 1]
    return {'alimentador': model.name, 'elementos': elementos, 'colisiones': colisiones}


def codigo_de_nombre(ident: Mapping[str, Any], tipo: str, nombre_pf: str) -> str | None:
    """El código de la fuente de un nombre de DIgSILENT, o ``None`` si no existe o si dos códigos lo comparten."""
    codigos = {e['codigo'] for e in ident['elementos'] if e['tipo'] == tipo and e['nombre_pf'] == nombre_pf}
    return next(iter(codigos)) if len(codigos) == 1 else None


def revision_red(run_id: str, manifiestos: Mapping[str, Path | str]) -> str:
    """La revisión de la red: SHA-256 del ``run_id`` y de cada manifiesto de geografía, por alimentador en orden."""
    h = hashlib.sha256()
    h.update(b'convertersmartgrid-plano-v1\0' + str(run_id).encode('utf-8') + b'\0')
    for alimentador in sorted(manifiestos):
        contenido = Path(manifiestos[alimentador]).read_bytes()
        h.update(str(alimentador).encode('utf-8') + b'\0' + hashlib.sha256(contenido).digest())
    return h.hexdigest()


def _decision(d: Any) -> dict[str, Any]:
    """Una decisión de reconstrucción (``ReconstructionDecision`` o su ``to_dict``) en las palabras del inspector."""
    d = d.to_dict() if hasattr(d, 'to_dict') else dict(d)
    nivel = d.get('level')
    return {'codigo': str(d.get('entity_id', '')), 'campo': d.get('field', ''), 'original': d.get('original_value'),
            'valor': d.get('applied_value'), 'regla': d.get('rule', ''), 'motivo': d.get('reason', ''),
            'confianza': d.get('confidence'), 'nivel': getattr(nivel, 'value', nivel)}


def _por_codigo(mensajes: Iterable[str]) -> dict[str, list[str]]:
    """Los mensajes «<código>: <texto>» de la validación, agrupados por código."""
    salida: dict[str, list[str]] = {}
    for m in mensajes or ():
        codigo, sep, texto = str(m).partition(': ')
        if sep:
            salida.setdefault(codigo, []).append(texto)
    return salida


def _calidad(codigo: str, errores: Mapping[str, list[str]], avisos: Mapping[str, list[str]]) -> str:
    return 'error' if errores.get(codigo) else ('aviso' if avisos.get(codigo) else 'ok')


def _deducida(campo: str, original: Any, valor: Any, regla: str, motivo: str) -> dict[str, Any]:
    return {'campo': campo, 'original': original, 'valor': valor, 'regla': regla, 'motivo': motivo,
            'confianza': None, 'nivel': 'inferred'}


def vista(model: FeederModel, geografia: Mapping[str, Any] | None, *, validacion: Mapping[str, Any] | None = None,
          decisiones: Iterable[Any] = ()) -> dict[str, Any]:
    """La vista del plano de un alimentador. ``geografia`` es su manifiesto (``geography_to_dict``) o ``None``.

    ``validacion`` es el informe de ``geography.validate_geography`` (o de la auditoría, con la misma forma) y
    ``decisiones``, las de la reconstrucción. Nada se recalcula: los vértices son los del manifiesto, enteros.
    """
    ident = identidad(model)
    nombre = {(e['tipo'], e['codigo']): e['nombre_pf'] for e in ident['elementos']}
    geografia = geografia or {}
    lineas_geo: Mapping[str, Any] = geografia.get('lines') or {}
    nodos_geo: Mapping[str, Any] = geografia.get('nodes') or {}
    sin_coordenadas = not lineas_geo
    errores = _por_codigo((validacion or {}).get('errors', ()))
    avisos = _por_codigo((validacion or {}).get('warnings', ()))
    deducido: dict[str, list[dict[str, Any]]] = {}
    for d in decisiones:
        fila = _decision(d)
        deducido.setdefault(fila.pop('codigo'), []).append(fila)
    trazos: dict[frozenset, list[str]] = {}
    for ln in model.lines:
        trazos.setdefault(frozenset((ln.from_node, ln.to_node)), []).append(ln.section_id)

    tramos = []
    for ln in sorted(model.lines, key=lambda ln: ln.section_id):
        propio = list(deducido.get(ln.section_id, ()))
        if ln.length_source == 'georef':
            propio.append(_deducida('longitud_m', ln.txt_length_m, ln.length_m, 'longitud_del_trazado',
                                    'la fuente no da la longitud: se mide en el trazado'))
        if ln.type_key != ln.source_type_code:
            propio.append(_deducida('tipo', ln.source_type_code, ln.type_key, 'alias_del_catalogo',
                                    'el tipo de la fuente se resuelve con el catálogo'))
        camino = (lineas_geo.get(ln.section_id) or {}).get('path') or []
        tramos.append({
            'codigo': ln.section_id, 'nombre_pf': nombre[('tramo', ln.section_id)],
            'desde': ln.from_node, 'hasta': ln.to_node, 'fases': letras_de_fase(ln.phase), 'tipo': ln.type_key,
            'aereo': ln.overhead, 'longitud_m': ln.length_m,
            'vertices': [[p['lat'], p['lon']] for p in camino],
            'paralelo_con': sorted(s for s in trazos[frozenset((ln.from_node, ln.to_node))] if s != ln.section_id),
            'original': {'tipo': ln.source_type_code, 'fase': ln.phase,
                         'longitud_m': ln.txt_length_m if ln.txt_length_m is not None else ln.length_m},
            'deducido': propio,
            'calidad': 'sin_coordenadas' if sin_coordenadas else _calidad(ln.section_id, errores, avisos),
            'avisos': avisos.get(ln.section_id, []), 'errores': errores.get(ln.section_id, []),
        })
    barras = []
    for n in sorted(model.nodes):
        punto = nodos_geo.get(n) or {}
        propio = list(deducido.get(n, ()))
        if model.nodes[n].coord_inferida:
            propio.append(_deducida('coordenadas', None, [punto.get('lat'), punto.get('lon')], 'posicion_por_el_grafo',
                                    'la fuente no da su posición: se deduce del grafo; sirve para dibujar, no para medir'))
        barras.append({'codigo': n, 'nombre_pf': nombre[('barra', n)], 'lat': punto.get('lat'), 'lon': punto.get('lon'),
                       'deducido': propio,
                       'calidad': 'sin_coordenadas' if not punto else _calidad(n, errores, avisos),
                       'avisos': avisos.get(n, []), 'errores': errores.get(n, [])})
    sed = [{'codigo': s.code, 'nombre_pf': nombre[('sed', s.code)], 'barra': s.node_id, 'tramo': s.section_id,
            'kva': s.design_kva} for s in sorted(model.seds, key=lambda s: (s.code, s.load_key))]
    maniobras = [{'codigo': codigo_de_maniobra(d), 'nombre_pf': nombre[('maniobra', codigo_de_maniobra(d))],
                  'clase': d.kind, 'tramo': d.section_id, 'barra': d.node_id,
                  'estado': 'cerrado' if d.on_off == 1 else 'abierto'}
                 for d in sorted(model.devices, key=lambda d: (codigo_de_maniobra(d), d.terminal_side))]
    salida = {'alimentador': model.name, 'kv': model.nominal_kv, 'fuente': model.source_node,
              'source_crs': geografia.get('source_crs'), 'target_crs': geografia.get('target_crs'),
              'sin_coordenadas': sin_coordenadas, 'tramos': tramos, 'barras': barras, 'sed': sed,
              'maniobras': maniobras, 'tipos_de_linea': sorted(model.line_types),
              'colisiones': ident['colisiones'], 'avisos': list((validacion or {}).get('warnings', ()))}
    # 111:RF-23: el unifilar del mismo alimentador, con los mismos códigos y desde su cabecera; solo coloca barras.
    salida['unifilar'] = unifilar_de_vista(salida)
    return salida


def resumen_plano(vistas: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Los alimentadores del plano, en el orden dado, y los que no tienen coordenadas (listados, sin pintar)."""
    vistas = list(vistas)
    return {'alimentadores': [v['alimentador'] for v in vistas],
            'sin_coordenadas': [v['alimentador'] for v in vistas if v['sin_coordenadas']]}
