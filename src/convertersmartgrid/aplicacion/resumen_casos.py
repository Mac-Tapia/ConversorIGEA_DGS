"""El resumen ejecutivo de un caso de DIgSILENT con lo guardado en el espacio, sin otra ejecución (017:RF-144 a RF-147).

Usuario (2026-11-25), Pisco: «debe haber un botón para hacer resúmenes ejecutivos de los casos sin proyecto, con cargas y
con proyecto»; y en «Con proyecto», «se deben identificar los bancos y en el resumen indicar los nodos, y el nodo de inicio
y fin en los tramos de cables y terna, reforzamiento». Aquí solo se arman las filas y las conclusiones; el Word y el libro
los escribe ``informe_docx`` y lo guardado lo lee la web. Nada de una distribuidora: los nombres son los de la red.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

#: Los casos que se resumen, con su nombre para el operador.
CASOS = {'sin_proyecto': 'Sin proyecto', 'cargas_nuevas': 'Cargas nuevas', 'con_proyecto': 'Con proyecto'}

#: 017:RF-150: estados de una calibración cuadrada que avisan sin bloquear (``dominio.native_action``).
AVISOS_QUE_NO_BLOQUEAN = frozenset({'AVISO_KVAR', 'AVISO_PERSISTENCIA_CORREGIDA'})


class ResumenError(ValueError):
    """Un caso que no se conoce o sin nada guardado que resumir."""


def _num(valor: Any, decimales: int = 0) -> str:
    if valor is None or valor == '':
        return '—'
    try:
        x = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    texto = f'{x:,.{decimales}f}'
    return texto.replace(',', ' ') if decimales == 0 else texto.replace(',', ' ')


def filas_sin_proyecto(informes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """017:RF-145: por alimentador, la calibración: la máxima de cabecera, el factor de las escaladas, si cuadró y por qué
    no, y los bancos en servicio."""
    cabecera = ('Alimentador', 'Máxima de cabecera (kW)', 'Factor de las escaladas', 'Calibración', 'Motivo o aviso')
    filas, validos, invalidos = [], [], []
    for inf in sorted(informes or [], key=lambda i: str(i.get('feeder') or '')):
        f = str(inf.get('feeder') or '—')
        objetivo = (inf.get('objetivo') or {}).get('kw')
        # 017:RF-150: cuadrada con un aviso que no bloquea (AVISO_KVAR, AVISO_PERSISTENCIA_CORREGIDA) es válida. Pisco
        # (2026-11-25): 16 de 17 salían «sin validar» por su aviso de kvar.
        estado = str(inf.get('status') or '').upper()
        bien = bool(inf.get('cuadrado')) and (estado in ('', 'OK', 'CUADRADO', 'VALIDADO', 'CALIBRADO')
                                              or estado in AVISOS_QUE_NO_BLOQUEAN)
        (validos if bien else invalidos).append(f)
        # Los avisos del informe son los del sistema entero: el de cada alimentador empieza por su nombre.
        propios = [str(a) for a in inf.get('avisos') or [] if str(a).startswith(f'{f}:')]
        motivo = str(inf.get('motivo') or '') or next(iter(propios), '')
        filas.append((f, _num(objetivo), _num(inf.get('factor_escala'), 3), 'válida' if bien else 'sin validar',
                      motivo[:160] or '—'))
    conclusiones = [f'{len(filas)} alimentadores calibrados; {len(validos)} con la calibración válida.']
    if invalidos:
        conclusiones.append('Sin validar: ' + ', '.join(invalidos) + '; vea su motivo.')
    return {'caso': CASOS['sin_proyecto'], 'cabecera': cabecera, 'filas': filas, 'conclusiones': conclusiones}


def filas_cargas_nuevas(cargas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """017:RF-146: por alimentador, las cargas nuevas aplicadas, su potencia y la barra donde se conectan."""
    cabecera = ('Alimentador', 'Carga nueva', 'Potencia (kW)', 'Barra de conexión')
    filas, por_alim = [], {}
    for c in sorted(cargas or [], key=lambda c: (str(c.get('alimentador') or ''), str(c.get('sed') or ''))):
        f = str(c.get('alimentador') or '—')
        kw = float(c.get('kw') or 0.0)
        por_alim[f] = por_alim.get(f, 0.0) + kw
        filas.append((f, str(c.get('sed') or c.get('variacion') or '—'), _num(kw), str(c.get('barra') or '—')))
    total = sum(por_alim.values())
    conclusiones = [f'{len(filas)} cargas nuevas en {len(por_alim)} alimentadores, {_num(total)} kW en total.']
    if por_alim:
        mayor = max(por_alim, key=por_alim.get)
        conclusiones.append(f'El de más carga nueva es {mayor}, con {_num(por_alim[mayor])} kW.')
    return {'caso': CASOS['cargas_nuevas'], 'cabecera': cabecera, 'filas': filas, 'conclusiones': conclusiones}


def ubicacion_de_obra(obra: Mapping[str, Any], nodos: Mapping[str, Sequence[str]]) -> str:
    """017:RF-152: dónde va una obra aplicada, con el nodo de inicio y de fin de cada tramo tomados de la última lectura
    guardada de su alimentador (``nodos``: tramo → (desde, hasta)); el tramo que no esté en ella se nombra solo."""
    from .escalera_optima import ubicacion

    tramos = [str(t) for t in obra.get('tramos') or []]
    if obra.get('clase') == 'condensador' or not tramos:
        return ubicacion(obra) if obra.get('clase') == 'condensador' else ''
    con = [{'tramo': t, 'desde': (nodos.get(t) or (None, None))[0], 'hasta': (nodos.get(t) or (None, None))[1]}
           for t in tramos]
    conocidos = [n for n in con if n['desde'] and n['hasta']]
    if not conocidos:
        return ubicacion(obra)
    texto = ubicacion({**obra, 'nodos': conocidos})
    sueltos = [n['tramo'] for n in con if not (n['desde'] and n['hasta'])]
    return texto + (('; y los tramos ' + ', '.join(sueltos)) if sueltos else '')


#: 017:RF-155: las obras de línea, las que llevan ficha en el resumen.
CLASES_DE_LINEA = ('terna', 'seccion')
_CONDUCTOR = re.compile(r'^([A-Z]+\d?)(\d{3})(\d{2})D', re.IGNORECASE)
_TYP = re.compile(r'typ_id ([^\s,]+) → ([^\s,]+)')
_NL = re.compile(r'nlnum (\d+) → (\d+)')


def conductor(nombre: Any) -> str:
    """El conductor con su sección legible si su nombre la trae (``AA12003D_FICHA`` → «AA 120 mm² (AA12003D_FICHA)»);
    si no, su nombre tal cual: los tipos son los del catálogo de cada empresa."""
    texto = str(nombre or '').strip()
    m = _CONDUCTOR.match(texto)
    return f'{m.group(1).upper()} {int(m.group(2))} mm² ({texto})' if m else (texto or '—')


def _punto(puntos: Sequence[Mapping[str, Any]], i: int) -> dict[str, Any] | None:
    p = puntos[i] if puntos else None
    return dict(p) if isinstance(p, Mapping) else None


def texto_punto(p: Mapping[str, Any] | None) -> str:
    """017:RF-155: «nodo: UTM (CRS) E … · N … (lat …, lon …)», con lo que haya."""
    if not p:
        return '—'
    partes = [str(p.get('barra') or '—')]
    if p.get('este') is not None and p.get('norte') is not None:
        partes.append(f"UTM {p.get('crs') or ''} E {_num(p['este'], 1)} · N {_num(p['norte'], 1)}".replace('UTM  ', 'UTM '))
    if p.get('lat') is not None and p.get('lon') is not None:
        partes.append(f"(lat {float(p['lat']):.6f}, lon {float(p['lon']):.6f})")
    return partes[0] + (': ' + ' '.join(partes[1:]) if len(partes) > 1 else '')


def ficha_obra_de_linea(obra: Mapping[str, Any], elementos: Sequence[Mapping[str, Any]] | None,
                        ubicacion: Sequence[Mapping[str, Any]] | None,
                        largos_km: Mapping[str, float] | None = None) -> dict[str, Any] | None:
    """017:RF-155: lo que el resumen ejecutivo dice de una terna o un cambio de sección aplicados.

    Usuario (2026-11-27), con la terna de SEN0001 en LL202: el resumen ejecutivo indica las coordenadas del punto de inicio
    y del final, si es nueva terna, refuerzo o cambio de conductor, la sección del cable y la longitud a intervenir, y
    «así debe ser cada vez que se haga este tipo de análisis». Con lo que dejó la obra en DIgSILENT: el cambio de cada
    tramo (``elementos``), sus extremos (``ubicacion``) y su largo (el del tramo o, sin él, ``largos_km``).
    """
    if obra.get('clase') not in CLASES_DE_LINEA:
        return None
    tramos = [str(t) for t in obra.get('tramos') or []]
    if not tramos:
        return None
    por_tramo = {str(e.get('elemento')): e for e in elementos or [] if e.get('clase') == 'ElmLne'}
    extremos = {str(u.get('elemento')): list(u.get('puntos') or []) for u in ubicacion or [] if isinstance(u, Mapping)}
    largos = dict(largos_km or {})
    grupos: dict[tuple[str, str], float] = {}
    finales: list[str] = []
    km_cambio = km_terna = total = 0.0
    sin_largo: list[str] = []
    cambia = terna = False
    for t in tramos:
        e = por_tramo.get(t) or {}
        cambio = str(e.get('cambio') or '')
        typ, nl = _TYP.search(cambio), _NL.search(cambio)
        km = (float(e['largo_m']) / 1000.0) if e.get('largo_m') is not None else largos.get(t)
        if km is None:
            sin_largo.append(t)
            km = 0.0
        nuevo = typ.group(2) if typ else str((obra.get('tipo') or {}).get('nombre') or '') if isinstance(obra.get('tipo'), Mapping) else ''
        if nuevo and nuevo not in finales:
            finales.append(nuevo)
        if typ and nl:
            clave = (conductor(typ.group(1)), f'Cambio a {conductor(nuevo)} + nueva terna {conductor(nuevo)}')
            km_cambio += km
            km_terna += km
        elif nl:
            clave = ('el existente, de igual o más sección', f'Solo nueva terna {conductor(nuevo)}')
            km_terna += km
        elif typ:
            clave = (conductor(typ.group(1)), f'Cambio de conductor a {conductor(nuevo)}')
            km_cambio += km
        else:
            clave = ('—', 'sin cambio registrado')
        grupos[clave] = grupos.get(clave, 0.0) + km
        total += km
        cambia, terna = cambia or bool(typ), terna or bool(nl)
    # Por lo que cambia en cada tramo, no por sus km: sin el largo leído, la terna seguía siendo terna.
    if terna and cambia:
        tipo = 'Nueva terna en paralelo con cambio de conductor'
    elif terna:
        tipo = 'Nueva terna en paralelo'
    else:
        tipo = 'Cambio de conductor (refuerzo de sección)'
    return {'alimentador': str(obra.get('alimentador') or ''), 'obra': tipo,
            'inicio': _punto(extremos.get(tramos[0]) or [], 0), 'fin': _punto(extremos.get(tramos[-1]) or [], -1),
            'longitud_km': round(total, 3), 'km_cambio': round(km_cambio, 3), 'km_terna': round(km_terna, 3),
            'tramos': len(tramos), 'primero': tramos[0], 'ultimo': tramos[-1],
            'conductor_final': ', '.join(conductor(x) for x in finales) or '—',
            'por_conductor': [(antes, round(km, 3), accion) for (antes, accion), km in grupos.items()],
            'sin_largo': sin_largo}


def filas_de_ficha(ficha: Mapping[str, Any], *, inversion: Any = None, costo_anual: Any = None) -> dict[str, Any]:
    """017:RF-155: la ficha en dos tablas, «Dato/Valor» y por conductor existente, como la del resumen del 27-11."""
    datos = [
        ['Alimentador', ficha.get('alimentador') or '—'],
        ['Obra', ficha.get('obra') or '—'],
        ['Punto de inicio', texto_punto(ficha.get('inicio'))],
        ['Punto final', texto_punto(ficha.get('fin'))],
        ['Longitud a intervenir', f"{_num(ficha.get('longitud_km'), 2)} km en {ficha.get('tramos')} tramos, de "
                                  f"{ficha.get('primero')} a {ficha.get('ultimo')}"],
        ['Conductor final', ficha.get('conductor_final') or '—'],
    ]
    if ficha.get('km_cambio') and ficha.get('km_terna'):
        datos.append(['Alcance', f"cambio de conductor en {_num(ficha['km_cambio'], 2)} km; nueva terna en "
                                 f"{_num(ficha['km_terna'], 2)} km"])
    if inversion is not None or costo_anual is not None:
        datos.append(['Inversión / costo anual', f'{_num(inversion)} / {_num(costo_anual)}'])
    if ficha.get('sin_largo'):
        datos.append(['Sin largo leído', ', '.join(ficha['sin_largo'])])
    conductores = [[a, _num(km, 2), accion] for a, km, accion in ficha.get('por_conductor') or []]
    conductores.append(['Total', _num(ficha.get('longitud_km'), 2), ''])
    return {'datos': datos, 'cabecera_conductores': ('Conductor actual', 'Longitud (km)', 'Qué se hace'),
            'conductores': conductores}


def _aplicadas_y_guardadas(propias: Sequence[Mapping[str, Any]],
                           guardadas: Sequence[Mapping[str, Any]]) -> list[tuple[Mapping[str, Any], bool]]:
    """017:RF-151: lo aplicado de ``f`` (sí) y las alternativas guardadas que no son lo aplicado (no), de menor a mayor
    costo; la guardada con el mismo nombre completa la aplicada (su inversión y sus nodos si no los trae)."""
    por_nombre = {str(g.get('nombre')): g for g in guardadas or []}
    filas = []
    for a in propias:
        g = por_nombre.get(str(a.get('nombre'))) or {}
        filas.append(({**g, **{k: v for k, v in a.items() if v not in (None, [], '')}}, True))
    nombres = {str(a.get('nombre')) for a in propias}
    filas += [(g, False) for g in guardadas or [] if str(g.get('nombre')) not in nombres]
    return sorted(filas, key=lambda x: (not x[1], float(x[0].get('costo_anual') or 0.0)))


def filas_con_proyecto(alternativas: Mapping[str, Sequence[Mapping[str, Any]]],
                       sin_obra: Sequence[str] = (),
                       aplicadas: Mapping[str, Sequence[Mapping[str, Any]]] | None = None) -> dict[str, Any]:
    """017:RF-147: por alimentador, sus alternativas de menor a mayor costo, la que se aplica, dónde va cada obra (el nodo
    de MT de cada banco; el nodo de inicio y de fin de cada tramo de sección, terna o refuerzo, 063:RF-31) y su costo.

    017:RF-151: con ``aplicadas`` (las obras aplicadas del proyecto, una por alternativa), lo que se aplica es eso, y
    las alternativas guardadas solo completan; sin ella, la elegida de las guardadas (como antes)."""
    cabecera = ('Alimentador', 'N.º', 'Alternativa', 'Ubicación (nodos)', 'Costo anual', 'Inversión', 'Se aplica')
    filas, total, con_obra = [], 0.0, []
    if aplicadas is None:
        por_alim = {f: [(a, bool(a.get('elegida'))) for a in alternativas[f] or []] for f in alternativas or {}}
    else:
        por_alim = {f: _aplicadas_y_guardadas(aplicadas.get(f) or [], (alternativas or {}).get(f) or [])
                    for f in sorted(set(aplicadas) | set(alternativas or {}))}
    for f in sorted(por_alim):
        for n, (a, se_aplica) in enumerate(por_alim[f], start=1):
            donde = '; '.join(str(u) for u in a.get('ubicacion') or [] if u) or '—'
            nombre = str(a.get('nombre') or '—')
            if a.get('origen') == 'operador':
                nombre = f'{nombre} (obra del operador)'
            numero = str(a.get('numero') or '—') if aplicadas is None else str(n)
            filas.append((f, numero, nombre, donde, _num(a.get('costo_anual')), _num(a.get('inversion')),
                          'sí' if se_aplica else ''))
            if se_aplica:
                total += float(a.get('costo_anual') or 0.0)
                if f not in con_obra:
                    con_obra.append(f)
    sin = sorted(set(sin_obra) - set(con_obra))
    for f in sin:
        filas.append((f, '—', 'sin obra: cumple con sus cargas nuevas o sin ellas', '—', '0', '0', 'sí'))
    conclusiones = [f'{len(con_obra)} alimentadores con obra; costo anual de las obras que se aplican: {_num(total)}.']
    if sin_obra:
        conclusiones.append(f'{len(sin)} alimentadores sin obra.')
    # 017:RF-155: de cada obra de línea que se aplica, su ficha: extremos con coordenadas, qué se hace y su longitud.
    fichas = []
    for f in sorted(por_alim):
        for a, se_aplica in por_alim[f]:
            for ficha in (a.get('fichas') or []) if se_aplica else []:
                fichas.append({**ficha, **filas_de_ficha(ficha, inversion=a.get('inversion'),
                                                         costo_anual=a.get('costo_anual'))})
                conclusiones.append(f"{ficha['alimentador']}: {ficha['obra'].lower()} de {_num(ficha['longitud_km'], 2)} km, "
                                    f"de {(ficha.get('inicio') or {}).get('barra') or ficha['primero']} a "
                                    f"{(ficha.get('fin') or {}).get('barra') or ficha['ultimo']}, en {ficha['conductor_final']}.")
    return {'caso': CASOS['con_proyecto'], 'cabecera': cabecera, 'filas': filas, 'conclusiones': conclusiones,
            'fichas_de_linea': fichas}


#: 017:RF-156, 063:RF-43: por debajo, una barra sin fuente (isla), no una caída de tensión.
UMBRAL_SIN_TENSION = 0.1                                 # el de cargas_pf (008:RF-29)
#: 017:RF-156: el orden de los casos en el cuadro de pérdidas.
ORDEN_CASOS = ('Sin proyecto', 'Cargas nuevas', 'Con proyecto')
#: 017:RF-156: las columnas del cuadro de pérdidas.
CABECERA_PERDIDAS = ('Proyecto', 'Alimentador', 'Caso', 'Cabecera (kW)', 'Pérdidas (kW)', 'Pérdidas (%)',
                     'Tramo más cargado', 'Cargabilidad (%)', 'Punto de MT más bajo', 'Tensión (p.u.)',
                     'Caída de tensión (%)')


def fila_de_perdidas(project: str, caso: str, feeder: str, m: Mapping[str, Any]) -> dict[str, Any]:
    """017:RF-156: de la medida de un alimentador en un estudio de flujo, sus pérdidas (kW y % de la cabecera), el tramo
    (``ElmLne``) más cargado y el punto de media tensión de menor tensión, con su caída en % de la nominal.

    Usuario (2026-11-27): «en la tabla de pérdidas debes incluir columnas de cargabilidad del tramo más crítico en %, la
    caída de tensión del punto más crítico en media tensión y su porcentaje de pérdidas». El más cargado del estudio
    (``mas_cargado``) puede ser un transformador: aquí solo cuentan los tramos; y la tensión mínima, solo la de media.
    """
    cab = numero_o_none(m.get('cabecera_kw'))
    perd = numero_o_none(m.get('perdidas_kw'))
    tramos = [(float(c), str(n)) for n, clase, c, *_r in m.get('elementos') or []
              if clase == 'ElmLne' and c is not None]
    # 063:RF-43: una barra a 0 p.u. es una isla sin fuente, no una caída (SM218 y SL143, 27-11): queda fuera y se cuenta.
    islas = {str(n) for n in m.get('sin_tension') or []}
    u = {str(n): float(v) for n, v, *_r in m.get('barras') or []
         if v is not None and float(v) > UMBRAL_SIN_TENSION and str(n) not in islas}
    mt = [str(n) for n in m.get('barras_mt') or []]
    en_mt = [(u[n], n) for n in mt if n in u] or [(v, n) for n, v in u.items()]
    carg, tramo = max(tramos) if tramos else (None, None)
    umin, barra = min(en_mt) if en_mt else (None, None)
    return {'proyecto': project, 'alimentador': feeder, 'caso': caso, 'converge': bool(m.get('converge', True)),
            'cabecera_kw': cab, 'perdidas_kw': perd,
            'perdidas_pct': (100.0 * perd / cab) if cab and perd is not None else None,
            'tramo': tramo, 'cargabilidad_pct': carg, 'barra_mt': barra, 'u_min_pu': umin,
            'caida_pct': max(0.0, 100.0 * (1.0 - umin)) if umin is not None else None,
            'solo_media': bool(mt), 'barras_sin_tension': len(islas)}


def numero_o_none(x: Any) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


#: 017:RF-157: lo que puede apartarse la cabecera medida en «Sin proyecto» de la calibrada sin avisar.
DESVIO_CABECERA = 0.02


def cuadro_de_perdidas(estudios: Sequence[Mapping[str, Any]],
                       calibradas: Mapping[tuple[str, str], float] | None = None) -> dict[str, Any]:
    """017:RF-156: el cuadro de pérdidas de los estudios de flujo dados (``{'project', 'caso', 'medidas'}``), una fila por
    proyecto, alimentador y caso, en el orden de :data:`ORDEN_CASOS`; y qué casos de cada proyecto faltan."""
    filas = [fila_de_perdidas(str(e.get('project') or ''), str(e.get('caso') or ''), f, m)
             for e in estudios for f, m in sorted((e.get('medidas') or {}).items()) if isinstance(m, Mapping)]
    orden = {c: i for i, c in enumerate(ORDEN_CASOS)}
    filas.sort(key=lambda r: (r['proyecto'], r['alimentador'], orden.get(r['caso'], 9), r['caso']))
    # 017:RF-157: PA217 (27-11) daba 12 411 kW en «Sin proyecto» calibrado a 9 447 kW (una SED cambiada a mano).
    for r in filas:
        cal = (calibradas or {}).get((r['proyecto'], r['alimentador']))
        r['cabecera_calibrada_kw'] = cal if r['caso'] == ORDEN_CASOS[0] else None
        r['aviso'] = None
        if r['caso'] == ORDEN_CASOS[0] and cal and r['cabecera_kw'] is not None \
                and abs(r['cabecera_kw'] - cal) > DESVIO_CABECERA * cal:
            r['aviso'] = (f"la cabecera da {r['cabecera_kw']:,.0f} kW y se calibró a {cal:,.0f} kW: algo cambió la "
                          'demanda calibrada (un cambio a mano o una orden posterior)')
    proyectos = sorted({r['proyecto'] for r in filas})
    faltan = [{'proyecto': p, 'caso': c} for p in proyectos for c in ORDEN_CASOS
              if not any(r['proyecto'] == p and r['caso'] == c for r in filas)]
    return {'filas': filas, 'faltan': faltan}


def seccion_de_perdidas(cuadro: Mapping[str, Any]) -> dict[str, Any] | None:
    """017:RF-156: el cuadro de pérdidas como sección del resumen ejecutivo del sistema (017:RF-149)."""
    filas = cuadro.get('filas') or []
    if not filas:
        return None
    return {'caso': 'Pérdidas por caso', 'cabecera': CABECERA_PERDIDAS,
            'filas': [(r['proyecto'], r['alimentador'], r['caso'], _num(r['cabecera_kw']), _num(r['perdidas_kw']),
                       _num(r['perdidas_pct'], 1), r['tramo'] or '—', _num(r['cargabilidad_pct'], 1), r['barra_mt'] or '—',
                       _num(r['u_min_pu'], 3), _num(r['caida_pct'], 1)) for r in filas],
            'conclusiones': [f"{r['alimentador']} · {r['caso']}: pérdidas {_num(r['perdidas_pct'], 1)} %, tramo más cargado "
                             f"al {_num(r['cargabilidad_pct'], 1)} %, caída en MT {_num(r['caida_pct'], 1)} %."
                             for r in filas]}


def resumen(caso: str, *, informes=None, cargas=None, alternativas=None, sin_obra=(), aplicadas=None) -> dict[str, Any]:
    """017:RF-144: las filas y conclusiones del caso pedido; ``ResumenError`` si el caso no existe o no hay nada."""
    if caso not in CASOS:
        raise ResumenError(f'Caso desconocido «{caso}»: use ' + ', '.join(CASOS) + '.')
    if caso == 'sin_proyecto':
        if not informes:
            raise ResumenError('El proyecto no tiene calibración aplicada: calibre antes de resumir «Sin proyecto».')
        return filas_sin_proyecto(informes)
    if caso == 'cargas_nuevas':
        if not cargas:
            raise ResumenError('El proyecto no tiene cargas nuevas aplicadas.')
        return filas_cargas_nuevas(cargas)
    if not alternativas and not sin_obra and not aplicadas:
        raise ResumenError('«Con proyecto» no tiene obras evaluadas: ejecútelo antes de resumirlo.')
    return filas_con_proyecto(alternativas or {}, sin_obra, aplicadas)


def resumen_del_sistema(*, informes=None, cargas=None, alternativas=None, sin_obra=(),
                        aplicadas=None, perdidas: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """017:RF-149: UN solo resumen del proyecto de sistema, con «Sin proyecto», «Cargas nuevas» y «Con proyecto» en
    secciones, y las conclusiones de las tres al principio. Usuario (2026-11-25): «tiene que ser un solo resumen
    ejecutivo; es un solo proyecto de sistema». Una sección sin datos se dice en las conclusiones, sin negar el resto."""
    secciones, conclusiones = [], []
    for caso, datos in (('sin_proyecto', {'informes': informes}), ('cargas_nuevas', {'cargas': cargas}),
                        ('con_proyecto', {'alternativas': alternativas, 'sin_obra': sin_obra,
                                          'aplicadas': aplicadas})):
        try:
            s = resumen(caso, **datos)
        except ResumenError as exc:
            conclusiones.append(f'{CASOS[caso]}: {exc}')
            continue
        secciones.append(s)
        conclusiones += [f"{s['caso']}: {c}" for c in s['conclusiones']]
    perd = seccion_de_perdidas(perdidas or {})                                       # 017:RF-156
    if perd is not None:
        secciones.append(perd)
        conclusiones += [f"Pérdidas por caso: {c}" for c in perd['conclusiones']]
    if (perdidas or {}).get('faltan'):
        conclusiones.append('Pérdidas por caso: sin estudio de flujo en ' + ', '.join(
            f"«{x['caso']}»" for x in perdidas['faltan']) + ' (córralo en Estudios).')
    if not secciones:
        raise ResumenError('El proyecto no tiene nada guardado que resumir: calibre, aplique cargas o evalúe «Con proyecto».')
    return {'caso': 'Sistema', 'secciones': secciones, 'conclusiones': conclusiones}
