"""El resumen ejecutivo de un caso de DIgSILENT con lo guardado en el espacio, sin otra ejecución (017:RF-144 a RF-147).

Usuario (2026-11-25), Pisco: «debe haber un botón para hacer resúmenes ejecutivos de los casos sin proyecto, con cargas y
con proyecto»; y en «Con proyecto», «se deben identificar los bancos y en el resumen indicar los nodos, y el nodo de inicio
y fin en los tramos de cables y terna, reforzamiento». Aquí solo se arman las filas y las conclusiones; el Word y el libro
los escribe ``informe_docx`` y lo guardado lo lee la web. Nada de una distribuidora: los nombres son los de la red.
"""

from __future__ import annotations

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
    return {'caso': CASOS['con_proyecto'], 'cabecera': cabecera, 'filas': filas, 'conclusiones': conclusiones}


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
                        aplicadas=None) -> dict[str, Any]:
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
    if not secciones:
        raise ResumenError('El proyecto no tiene nada guardado que resumir: calibre, aplique cargas o evalúe «Con proyecto».')
    return {'caso': 'Sistema', 'secciones': secciones, 'conclusiones': conclusiones}

