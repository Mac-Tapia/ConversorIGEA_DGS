"""Lo que el asistente responde con lo que ya hay, sin escribir ni abrir DIgSILENT (spec 070, RF-40 a RF-49).

El operador preguntaba «¿qué SED tiene este alimentador?» y no había tarea: el modelo proponía otra cosa o se
inventaba. Aquí cada respuesta sale de una función de lectura de la web, dice su fuente y, si el dato no está,
dice «no lo encuentro» y qué hacer. Nada se deduce: el usuario, el 2026-11-02, «no alucinen».
``svc`` es ``web/services``, recibido como parámetro: importarlo cerraría un ciclo.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from ..asistente.sinteticos import normalizar

#: Lo que devolvió la consulta, por espacio: la búsqueda en internet no puede sacarlo de la máquina (P9, 070:RF-46).
_DEVUELTOS: dict[str, set[str]] = {}
#: Por orden: «¿qué medidores tiene la SED…?» es de medidores antes que de SED.
_CLASES: tuple[tuple[str, str], ...] = (
    ('medidores', r'\bmedidor(es)?\b'),
    ('maximas', r'\bmaximas?\b'),
    ('clientes', r'\bclientes?\b|\bfij[ao]s\b'),
    ('sed', r'\bseds?\b|\bsedes\b'),
    ('anios', r'\banos\b'),
    ('catalogo', r'\bcatalogo\b|\bconductores\b|\bfichas?\b'),
    ('variaciones', r'\bvariacion(es)?\b|\bescane\w*\b|\ba mano\b'),
    ('calibracion', r'\bcalibracion\b|\bcalibrado\b'),
    ('proyectos', r'\bproyectos\b'),
    ('alimentadores', r'\balimentador(es)?\b'),
)


def clase_de_consulta(texto: str) -> str | None:
    t = normalizar(texto)
    return next((clase for clase, patron in _CLASES if re.search(patron, t)), None)


def _no_lo_encuentro(dato: str, que_hacer: str) -> dict:
    return {'dato': dato, 'encontrado': False, 'filas': [], 'fuente': None, 'que_hacer': que_hacer,
            'texto': f'No lo encuentro. {que_hacer}'}


def _hallado(ws, dato: str, filas: list, fuente: str, texto: str) -> dict:
    terminos = _DEVUELTOS.setdefault(ws.id, set())
    for fila in filas:
        for valor in (fila.values() if isinstance(fila, dict) else [fila]):
            for v in (valor if isinstance(valor, (list, tuple)) else [valor]):
                if isinstance(v, str) and len(v.strip()) >= 3:
                    terminos.add(v.strip())
    return {'dato': dato, 'encontrado': True, 'filas': filas, 'fuente': fuente, 'texto': f'{texto} Fuente: {fuente}.'}


def terminos_devueltos(ws) -> Sequence[str]:
    return sorted(_DEVUELTOS.get(ws.id, ()))


def _alimentadores(svc, ws) -> dict:
    filas = svc.feeder_rows(ws)
    if not filas:
        return _no_lo_encuentro('alimentadores', 'Cargue la fuente del espacio: «carga la fuente».')
    return _hallado(ws, 'alimentadores', filas, 'el inventario de la fuente cargada', f'{len(filas)} alimentador(es).')


def _sed(svc, ws, feeders: list[str]) -> dict:
    if not feeders:
        return _no_lo_encuentro('sed', 'Dígame de qué alimentador.')
    if ws.dataset is None:
        return _no_lo_encuentro('sed', 'Cargue la fuente del espacio: las SED salen de ella.')
    filas: list[dict] = []
    for f in feeders:
        try:
            filas += [{**s, 'alimentador': f} for s in svc.sed_de_alimentador(ws, f)['seds']]
        except svc.UserError as exc:
            return _no_lo_encuentro('sed', str(exc))
    if not filas:
        return _no_lo_encuentro('sed', f"{', '.join(feeders)} no tiene SED en la fuente cargada.")
    return _hallado(ws, 'sed', filas, 'el modelo de la fuente cargada, con las reglas del DGS',
                    f"{len(filas)} SED en {', '.join(feeders)}.")


def _medidores(svc, ws, feeders: list[str]) -> dict:
    meta = (ws.demanda or {}).get('medidores') or {}
    if not meta.get('path'):
        return _no_lo_encuentro('medidores', 'Asigne el libro de medidores en «2.1».')
    fuente = f"el libro de medidores {meta.get('name') or ''}".strip()
    if not feeders:
        lista = svc.demanda_alimentadores(ws).get('alimentadores') or []
        return _hallado(ws, 'medidores', lista, fuente, f'{len(lista)} alimentador(es) con medidor.')
    medidores = svc.medidores_por_alimentador(ws, feeders)
    filas = [{'alimentador': a, 'medidores': m} for a, m in medidores.items() if m]
    if not filas:
        return _no_lo_encuentro('medidores', f"{', '.join(feeders)} no está en el libro de medidores.")
    return _hallado(ws, 'medidores', filas, fuente, f'{sum(len(f["medidores"]) for f in filas)} medidor(es).')


def _maximas_vivas(trabajos: list[dict]) -> list[dict]:
    return [j for j in trabajos if j.get('kind') == 'demanda_cabecera' and j.get('status') == 'done']


def _maximas(ws, trabajos: list[dict]) -> dict:
    vivas = _maximas_vivas(trabajos)
    if not vivas:
        # 070:RF-44: viven en memoria. Decir «no hay» sería falso si se buscó antes de reiniciar.
        return _no_lo_encuentro('maximas', 'Vuelva a buscarla: las máximas viven en memoria y no sobreviven a un reinicio de la web.')
    ultima = vivas[-1]
    filas = [{k: r.get(k) for k in ('alimentador', 'medidor', 'fecha', 'kw', 'kvar', 'fp', 'error')}
             for r in (ultima.get('result') or {}).get('resultados') or []]
    return _hallado(ws, 'maximas', filas, f"el trabajo «{ultima.get('title')}» de esta sesión", f'{len(filas)} medidor(es) en la última búsqueda.')


def _clientes(svc, ws, feeders: list[str], periodo: str | None, trabajos: list[dict]) -> dict:
    meta = (ws.demanda or {}).get('clientes') or {}
    if not meta.get('path'):
        return _no_lo_encuentro('clientes', 'Asigne el libro de clientes importantes en «2.1».')
    if not feeders:
        return _no_lo_encuentro('clientes', 'Dígame de qué alimentador.')
    vivas = _maximas_vivas(trabajos)
    if not vivas and not periodo:
        return _no_lo_encuentro('clientes', 'Busque antes su máxima o dígame el mes: el cruce depende de la fecha, y las máximas no sobreviven a un reinicio.')
    filas_max = ((vivas[-1].get('result') or {}).get('resultados') or []) if vivas else []
    maximas = {f['alimentador']: {k: f.get(k) for k in ('fecha', 'kw', 'kvar', 'fp')} for f in filas_max
               if f.get('alimentador') in feeders and f.get('fecha') and not f.get('error')}
    try:
        r = svc.demanda_clientes(ws, feeders, periodo=periodo if periodo and len(periodo) == 7 else None,
                                      maximas=maximas or None, criterio=None)
    except svc.UserError as exc:
        return _no_lo_encuentro('clientes', str(exc))
    filas = [{k: c.get(k) for k in ('alimentador', 'sed', 'nis', 'cliente', 'kw', 'metodo')} for c in r.get('cruzados') or []]
    if not filas:
        return _no_lo_encuentro('clientes', f"Ningún cliente del libro cruza con {', '.join(feeders)}.")
    return _hallado(ws, 'clientes', filas, f"el libro de clientes {meta.get('name') or ''} cruzado con la fuente".strip(),
                    f'{len(filas)} cliente(s) fijos.')


def _anios(ws) -> dict:
    meta = (ws.demanda or {}).get('cabecera') or {}
    anios = meta.get('anios') or []
    if not anios:
        return _no_lo_encuentro('anios', 'Asigne la carpeta de la medición de cabecera en «2.1» e indéxela.')
    return _hallado(ws, 'anios', [str(a) for a in anios], f"la carpeta de cabecera {meta.get('name') or ''}".strip(),
                    f"Años con medición: {', '.join(str(a) for a in anios)}.")


def _catalogo(svc, ws) -> dict:
    informe = ws.catalog_report
    fichas = svc.fichas_conductores_de(ws) if ws.dataset is not None else {}
    if not informe and not fichas:
        return _no_lo_encuentro('catalogo', 'Cargue la fuente: el catálogo de equipos sale de ella.')
    filas = [{'codigo': c, **(f if isinstance(f, dict) else {})} for c, f in sorted(fichas.items())]
    return _hallado(ws, 'catalogo', filas, 'el catálogo de la fuente cargada y las fichas técnicas', f'{len(filas)} ficha(s) de conductor.')


def _variaciones(ws, proyecto: str | None) -> dict:
    escaneos = ws.escaneo or {}
    if not proyecto and len(escaneos) == 1:
        proyecto = next(iter(escaneos))
    if not proyecto:
        return _no_lo_encuentro('variaciones', 'Dígame de qué proyecto.')
    guardado = escaneos.get(proyecto)
    if not guardado:
        return _no_lo_encuentro('variaciones', f'{proyecto} no se ha escaneado: pida «escanea {proyecto}».')
    filas = [{'alimentador': a, **r} for a, r in (guardado.get('resumen') or {}).items()]
    return _hallado(ws, 'variaciones', filas, f'el último escaneo de {proyecto}', f'Escaneo de {len(filas)} alimentador(es).')


def _proyectos(svc, ws) -> dict:
    nombres = [p.get('name') for p in svc.pf_proyectos_guardados(ws).get('projects') or [] if p.get('name')]
    if not nombres:
        return _no_lo_encuentro('proyectos', 'La web aún no los leyó: pida «lee los proyectos de DIgSILENT».')
    return _hallado(ws, 'proyectos', nombres, 'la última lectura de DIgSILENT', f'{len(nombres)} proyecto(s).')


def _calibracion(svc, ws, proyecto: str | None) -> dict:
    if not proyecto:
        return _no_lo_encuentro('calibracion', 'Dígame de qué proyecto.')
    ajuste = svc.ajuste_aplicado_en_disco(ws, proyecto)
    if ajuste is None:
        return _no_lo_encuentro('calibracion', f'{proyecto} no tiene calibración aplicada en este espacio: pida calibrarlo.')
    filas = [{k: i.get(k) for k in ('feeder', 'status', 'cuadrado', 'objetivo', 'desvio', 'caso')} for i in ajuste.get('informes') or []]
    return _hallado(ws, 'calibracion', filas, f"el informe {ajuste.get('report')}", f"Última calibración de {proyecto}: {len(filas)} alimentador(es).")


def responder(svc, ws, plan, trabajos: list[dict]) -> dict:
    """La consulta de datos; ``dato`` dice qué se entendió, para que el operador lo corrija (070:RF-41)."""
    d = plan.datos
    feeders = [a for a in d.get('alimentadores') or [] if a != 'todos']
    clase = clase_de_consulta(plan.texto)
    if clase == 'alimentadores':
        return _alimentadores(svc, ws)
    if clase == 'sed':
        return _sed(svc, ws, feeders)
    if clase == 'medidores':
        return _medidores(svc, ws, feeders)
    if clase == 'maximas':
        return _maximas(ws, trabajos)
    if clase == 'clientes':
        return _clientes(svc, ws, feeders, d.get('periodo'), trabajos)
    if clase == 'anios':
        return _anios(ws)
    if clase == 'catalogo':
        return _catalogo(svc, ws)
    if clase == 'variaciones':
        return _variaciones(ws, d.get('proyecto'))
    if clase == 'proyectos':
        return _proyectos(svc, ws)
    if clase == 'calibracion':
        return _calibracion(svc, ws, d.get('proyecto'))
    opciones = 'alimentadores, SED, medidores, clientes fijos, máximas, años de medición, catálogo, variaciones, proyectos o la última calibración'
    return {'dato': None, 'encontrado': False, 'filas': [], 'fuente': None, 'que_hacer': f'Pregunte por {opciones}.',
            'texto': f'No entendí qué dato pide. Pregunte por {opciones}.'}


#: Lo que no está en el catálogo de estudios, con su motivo verificable en las specs.
_FUERA_DEL_CATALOGO: tuple[tuple[str, str, str], ...] = (
    ('optimización no lineal', r'\bpnl\b|\bno lineal\b|\bmixta\b',
     'la optimización mixta y no lineal está especificada (spec 048) y aún no implementada.'),
)
_CLAVES_DEL_CATALOGO: tuple[tuple[str, str], ...] = (
    ('cortocircuito', r'\bcortocircuito\b|\bfalla\b'),
    ('protecciones', r'\bproteccion(es)?\b|\breles?\b|\bselectividad\b|\bcoordinacion\b'),
    ('cuasi', r'\bcuasi\w*\b'),
    ('flujo_optimo', r'\bflujo optimo\b'),
    ('armonicos', r'\barmonic\w*\b'),
)


def no_disponible(svc, ws, plan) -> dict:
    """Por qué no se puede, sin ejecutar nada ni dar cifras (070:RF-47 a RF-49)."""
    t = normalizar(plan.texto)
    catalogo = svc.estudios_catalogo(ws, plan.datos.get('proyecto') or '') if ws is not None else {}
    negados = catalogo.get('no_ofrecidos') or []
    pedido = normalizar(str(plan.datos.get('estudio') or '')).strip()
    fila = next((e for e in negados if pedido and pedido in (normalizar(str(e['clave'])), normalizar(str(e['nombre']))) ), None)
    if fila is None:
        for clave, patron in _CLAVES_DEL_CATALOGO:
            if re.search(patron, t):
                fila = next((e for e in negados if clave in normalizar(str(e['clave'])) or clave in normalizar(str(e['nombre']))), None)
                if fila is not None:
                    break
    if fila is not None:
        return {'disponible': False, 'estudio': fila['clave'], 'motivo': fila['motivo'], 'falta': fila.get('falta') or [],
                'fuente': 'el catálogo de estudios', 'texto': f"{fila['nombre']} no está disponible: {fila['motivo']}."}
    for nombre, patron, motivo in _FUERA_DEL_CATALOGO:
        if re.search(patron, t):
            return {'disponible': False, 'estudio': nombre, 'motivo': motivo, 'falta': [], 'fuente': 'las specs del proyecto',
                    'texto': f'{nombre.capitalize()} no está disponible: {motivo}'}
    if pedido and any(pedido == normalizar(str(e.get('clave'))) for e in catalogo.get('ofrecidos') or []):
        return {'disponible': True, 'estudio': pedido, 'motivo': '', 'falta': [], 'fuente': 'el catálogo de estudios',
                'texto': f'{pedido} sí se ofrece: pida que se corra.'}
    return {'disponible': False, 'estudio': pedido or None, 'motivo': 'no está en el catálogo de esta versión', 'falta': [],
            'fuente': 'el catálogo de estudios', 'texto': 'Eso no está en el catálogo de estudios de esta versión.'}
