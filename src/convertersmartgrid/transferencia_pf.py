"""Lo que la transferencia de carga de la spec 011 decide sin DIgSILENT.

El guion ``tools/transferencia_pf.py`` toma el camino entre dos alimentadores por su
punto de enlace (la troncal de ``ComBbone``), cierra el enlace y abre, uno tras otro desde
el enlace hacia la cabecera del que cede, cada punto del camino, con un flujo de carga en
cada paso (RF-109). Aquí está lo que no necesita PowerFactory, para probarlo con caminos
sorteados:

- los pasos del camino y la carga que transfiere cada uno (RF-110);
- si un paso es viable y, si no, qué lo limita (RF-111, RF-114);
- el máximo por seccionador y por nodo de un sentido (RF-112, RF-113, RF-115 a RF-117,
  RF-129);
- el fichero con una fila por caso, sentido, enlace y paso (RF-121).

Y, de la spec 013, el instante común del mes (RF-22 a RF-29): los instantes en que los dos
alimentadores tienen registro de cabecera, los que no domina ningún otro y, tras verificar
cada uno en DIgSILENT, el crítico (el que deja la menor transferencia viable).

Los límites son los de los estudios (``estudios_pf.Limites``, RF-35): la transferencia no
tiene otros.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .estudios_pf import Limites, escribir_csv, violaciones

#: Clases de punto del camino.
NODO, SECCIONADOR = 'nodo', 'seccionador'

COLUMNAS = (
    'caso', 'cede', 'recibe', 'enlace', 'paso', 'punto', 'tipo', 'carga_kw', 'carga_kva',
    'converge', 'viable', 'vm_min', 'vm_min_barra', 'cargabilidad_max', 'mas_cargado',
    'cabecera_recibe_kw', 'cabecera_recibe_kvar', 'motivo', 'elemento_limita')


@dataclass(frozen=True)
class Punto:
    """Un punto del camino, desde el enlace hacia la cabecera del que cede.

    Una barra lleva la carga que cuelga de ella, derivaciones incluidas: la que pasa al
    que recibe si queda del lado del enlace.
    """

    nombre: str
    tipo: str
    carga_kw: float = 0.0
    carga_kvar: float = 0.0


@dataclass(frozen=True)
class Paso:
    """Abrir el camino en un punto: lo que queda del lado del enlace pasa al que recibe."""

    indice: int
    punto: str
    tipo: str
    carga_kw: float
    carga_kvar: float

    @property
    def carga_kva(self) -> float:
        return math.hypot(self.carga_kw, self.carga_kvar)


def pasos_del_camino(puntos: Sequence[Punto]) -> list[Paso]:
    """Un paso por punto del camino, con la carga que transfiere (RF-110).

    Abrir un seccionador transfiere las barras anteriores a él; abrir en una barra (el
    resultado por nodos, RF-113) transfiere hasta ella incluida, como si allí hubiera un
    seccionador aguas arriba. Un seccionador sin ninguna barra antes no transfiere nada y
    no es un paso.
    """
    pasos, kw, kvar, hay_barra = [], 0.0, 0.0, False
    for p in puntos:
        if p.tipo == NODO:
            kw, kvar, hay_barra = kw + p.carga_kw, kvar + p.carga_kvar, True
        elif p.tipo != SECCIONADOR:
            raise ValueError(f'Punto de camino desconocido: {p.tipo!r} ({p.nombre}).')
        elif not hay_barra:
            continue
        pasos.append(Paso(len(pasos) + 1, p.nombre, p.tipo, kw, kvar))
    return pasos


def _gravedad(v: Mapping[str, Any]) -> float:
    """Cuánto se pasa de su límite, relativo: compara una sobrecarga con una tensión."""
    return abs(v['valor'] - v['limite']) / v['limite']


def juzgar(paso: Paso, medida: Mapping[str, Any], limites: Limites) -> tuple[bool, dict | None]:
    """``(viable, lo que limita)`` de un paso (RF-111, RF-114).

    ``medida`` es la del alimentador que recibe y la parte transferida tras el flujo del
    paso: ``converge``, ``barras`` ``[(nombre, u)]`` y ``elementos`` ``[(nombre, clase,
    cargabilidad)]``. Con varias violaciones limita la que más se pasa de su límite.
    """
    if not medida.get('converge'):
        return False, {'motivo': 'no converge', 'elemento': None, 'valor': None, 'limite': None}
    fuera = violaciones(medida, limites)
    if not fuera:
        return True, None
    peor = max(fuera, key=lambda v: (_gravedad(v), v['elemento']))
    motivo = 'sobrecarga' if peor['tipo'] == 'sobrecarga' else 'tension'
    return False, {'motivo': motivo, 'elemento': peor['elemento'], 'valor': peor['valor'],
                   'limite': peor['limite']}


def _extremos(medida: Mapping[str, Any]) -> dict[str, Any]:
    barras = [(n, u) for n, u in medida.get('barras') or () if u is not None]
    elementos = [(n, c) for n, _clase, c in medida.get('elementos') or () if c is not None]
    lo = min(barras, key=lambda b: (b[1], b[0])) if barras else (None, None)
    hi = max(elementos, key=lambda e: (e[1], e[0])) if elementos else (None, None)
    return {'vm_min': lo[1], 'vm_min_barra': lo[0], 'cargabilidad_max': hi[1], 'mas_cargado': hi[0]}


def _maximo(paso: Paso | None) -> dict[str, Any] | None:
    if paso is None:
        return None
    return {'punto': paso.punto, 'carga_kw': paso.carga_kw, 'carga_kva': paso.carga_kva}


def resumir_sentido(pasos: Sequence[Paso], medidas: Sequence[Mapping[str, Any]], limites: Limites,
                    *, seccionadores_reconocidos: bool = True) -> dict[str, Any]:
    """El resultado de un sentido y un enlace (RF-112 a RF-117, RF-129).

    El máximo por seccionador es el del seccionador viable más lejano del enlace; el
    máximo por nodo, el de la barra viable más lejana. Lo que limita es lo del primer
    paso no viable. Si después de un paso no viable hay otro que sí lo es, el resultado
    no crece con la carga como cabe esperar, y se avisa.
    """
    if len(pasos) != len(medidas):
        raise ValueError(f'{len(pasos)} pasos y {len(medidas)} medidas.')
    filas, avisos, limita = [], [], None
    ultimo = {NODO: None, SECCIONADOR: None}
    for paso, medida in zip(pasos, medidas):
        viable, motivo = juzgar(paso, medida, limites)
        filas.append({'paso': paso.indice, 'punto': paso.punto, 'tipo': paso.tipo,
                      'carga_kw': paso.carga_kw, 'carga_kva': paso.carga_kva,
                      'converge': bool(medida.get('converge')), 'viable': viable,
                      **_extremos(medida),
                      'cabecera_recibe_kw': medida.get('cabecera_kw'),
                      'cabecera_recibe_kvar': medida.get('cabecera_kvar'),
                      'motivo': (motivo or {}).get('motivo'),
                      'elemento_limita': (motivo or {}).get('elemento')})
        if viable:
            if limita is not None:
                avisos.append(f'El paso {paso.punto} es viable aunque {limita["punto"]}, antes, '
                              'no lo es: revise el camino o los límites.')
            ultimo[paso.tipo] = paso
        elif limita is None:
            limita = {'paso': paso.indice, 'punto': paso.punto, **motivo}

    por_seccionador = seccionadores_reconocidos and any(p.tipo == SECCIONADOR for p in pasos)
    if not seccionadores_reconocidos:
        avisos.append('El proyecto no distingue los seccionadores de los demás equipos de '
                      'maniobra: solo se da el resultado por nodos. Hay que volver a convertir '
                      'el alimentador o cargar su entrada.')
    elif not por_seccionador:
        avisos.append('El camino no tiene ningún seccionador: solo se da el resultado por nodos.')
    admite = any(f['viable'] for f in filas)
    if not admite and limita is not None:
        avisos.append(f'Este sentido no admite transferencia: ya en el primer paso limita '
                      f'{limita["elemento"] or "el flujo"} ({limita["motivo"]}).')
    return {'admite': admite,
            'maximo_seccionador': _maximo(ultimo[SECCIONADOR]) if por_seccionador else None,
            'maximo_nodo': _maximo(ultimo[NODO]),
            'limita': limita, 'pasos': filas, 'avisos': avisos}


def filas_fichero(resultados: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Una fila por caso, sentido, enlace y paso (RF-121), en un orden que no depende del
    de llegada."""
    filas = []
    for r in resultados:
        for paso in r.get('pasos') or ():
            filas.append({'caso': r['caso'], 'cede': r['cede'], 'recibe': r['recibe'],
                          'enlace': r['enlace'], 'instante': r.get('instante'), **paso})
    return sorted(filas, key=lambda f: (f['caso'], f['cede'], f['recibe'], f['enlace'], f['paso']))


#: Columnas de la hoja de SED transferidas (013:RF-24, RF-26).
COLUMNAS_SED = ('caso', 'cede', 'recibe', 'enlace', 'instante', 'punto', 'sed', 'kw', 'kvar', 'kva')
#: Columnas de la hoja de cobertura temporal (013:RF-28).
COLUMNAS_COBERTURA = ('instante', 'alimentador', 'objetivo_kw', 'objetivo_kvar', 'medido_kw',
                      'medido_kvar', 'verificado', 'motivo')


def filas_sed(resultados: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Una fila por SED transferida en el punto viable más lejano de cada sentido (013:RF-24)."""
    filas = []
    for r in resultados:
        for s in r.get('sed_transferidas') or ():
            filas.append({'caso': r['caso'], 'cede': r['cede'], 'recibe': r['recibe'],
                          'enlace': r['enlace'], 'instante': r.get('instante'),
                          'punto': r.get('punto_transferido'), **s})
    return sorted(filas, key=lambda f: (f['caso'], f['cede'], f['enlace'], f['sed']))


def filas_cobertura(temporal: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Una fila por candidato y alimentador, con el objetivo y lo medido tras ajustarlo (013:RF-28)."""
    filas = []
    for c in (temporal or {}).get('candidatos') or ():
        for f, (kw, kvar) in sorted(c['objetivos'].items()):
            medido = (c.get('medido') or {}).get(f) or (None, None)
            filas.append({'instante': c['instante'], 'alimentador': f, 'objetivo_kw': kw,
                          'objetivo_kvar': kvar, 'medido_kw': medido[0], 'medido_kvar': medido[1],
                          'verificado': c.get('verificado'), 'motivo': c.get('motivo') or ''})
    return filas


def escribir_fichero(resultados: Iterable[Mapping[str, Any]], destino: Path,
                     temporal: Mapping[str, Any] | None = None) -> Path:
    """El fichero descargable de las transferencias.

    Con extensión ``.xlsx``, un libro con las hojas «Pasos», «SED transferidas» y «Cobertura
    temporal» (013:RF-26, RF-28): la lista de SED no cabe en la fila de un paso. Con otra,
    el CSV de los pasos, como los de los estudios (011:RF-121).
    """
    resultados = list(resultados)
    if destino.suffix.lower() != '.xlsx':
        return escribir_csv(filas_fichero(resultados), COLUMNAS, destino)
    from openpyxl import Workbook

    libro = Workbook()
    hojas = (('Pasos', ('instante', *COLUMNAS), filas_fichero(resultados)),
             ('SED transferidas', COLUMNAS_SED, filas_sed(resultados)),
             ('Cobertura temporal', COLUMNAS_COBERTURA, filas_cobertura(temporal)))
    for n, (nombre, columnas, filas) in enumerate(hojas):
        hoja = libro.active if n == 0 else libro.create_sheet()
        hoja.title = nombre
        hoja.append(list(columnas))
        for f in filas:
            hoja.append([f.get(c) for c in columnas])
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal_path = destino.with_name(destino.name + '.tmp')
    libro.save(temporal_path)
    temporal_path.replace(destino)
    return destino


# --------------------------------------------------------------------------- instante común (013)
@dataclass(frozen=True)
class InstanteTransferencia:
    """Un instante con registro de cabecera de los dos alimentadores: ``objetivos`` da
    ``alimentador → (kW, kVAR)``; el kVAR puede faltar."""

    fecha: datetime
    objetivos: dict[str, tuple[float, float | None]]


def en_el_periodo(fecha: datetime, periodo: str) -> bool:
    """``AAAA-MM`` (un mes) o ``AAAA`` (todo el año, 025:RF-7)."""
    return fecha.strftime('%Y-%m' if len(periodo) == 7 else '%Y') == periodo


def curva_del_alimentador(curvas: Sequence[Sequence[tuple[datetime, float | None, float | None]]]
                          ) -> list[tuple[datetime, float, float | None]]:
    """La cabecera de un alimentador con varios medidores: su suma en los instantes que
    tienen registro con kW en todos, sin interpolar (013:RF-27). Un kVAR que falte en uno
    deja el kVAR de ese instante sin valor, no en cero."""
    por_medidor = [{t: (kw, kvar) for t, kw, kvar in c if kw is not None} for c in curvas]
    if not por_medidor:
        return []
    comunes = set(por_medidor[0]).intersection(*por_medidor[1:])
    out = []
    for t in sorted(comunes):
        kw = sum(m[t][0] for m in por_medidor)
        qs = [m[t][1] for m in por_medidor]
        q = None if any(x is None for x in qs) else float(sum(x for x in qs if x is not None))
        out.append((t, float(kw), q))
    return out


def instantes_comunes(curvas: Mapping[str, Sequence[tuple[datetime, float | None, float | None]]],
                      periodo: str) -> list[InstanteTransferencia]:
    """Los instantes del periodo con registro de kW en la cabecera de todos los alimentadores
    (013:RF-22, RF-27). Coinciden solo las fechas iguales: no se interpola ni se redondea."""
    por_alim = {f: {t: (kw, kvar) for t, kw, kvar in c if kw is not None and en_el_periodo(t, periodo)}
                for f, c in curvas.items()}
    if not por_alim:
        return []
    nombres = sorted(por_alim)
    comunes = set(por_alim[nombres[0]]).intersection(*(por_alim[f] for f in nombres[1:]))
    return [InstanteTransferencia(t, {f: por_alim[f][t] for f in nombres}) for t in sorted(comunes)]


def _componentes(i: InstanteTransferencia, cede: str, recibe: str) -> tuple | None:
    """``(P del que cede, |Q| del que cede, P del que recibe, |Q| del que recibe)``, o None si
    falta un kVAR: sin él no se puede decir que un instante sea menos exigente que otro."""
    (pc, qc), (pr, qr) = i.objetivos[cede], i.objetivos[recibe]
    if qc is None or qr is None:
        return None
    return (pc, abs(qc), pr, abs(qr))


def _domina(a: tuple, b: tuple) -> bool:
    return all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b))


def frontera_no_dominada(instantes: Sequence[InstanteTransferencia], cede: str, recibe: str
                         ) -> tuple[list[InstanteTransferencia], dict[datetime, datetime]]:
    """Los instantes que ningún otro domina para el sentido ``cede → recibe`` (013:RF-27).

    Un instante domina a otro si cede y recibe al menos la misma P y la misma |Q| en los
    cuatro valores y más en alguno: con más carga en los dos, la transferencia viable no
    puede ser mayor, así que el dominado no puede ser el crítico. Un instante sin kVAR en
    alguno de los dos no se descarta ni descarta a otro. Devuelve los candidatos, en orden
    de fecha, y cada descartado con el instante que lo domina. No hay tope de candidatos:
    recortarlos dejaría el resultado sin comprobar (RF-29).
    """
    con_q = [(i, c) for i in instantes if (c := _componentes(i, cede, recibe)) is not None]
    # En orden de suma decreciente, un dominado solo puede estar después de quien lo domina,
    # y si lo domina uno descartado también lo domina uno de la frontera: basta con ella.
    con_q.sort(key=lambda ic: (-sum(ic[1]), ic[0].fecha))
    frontera: list[tuple[InstanteTransferencia, tuple]] = []
    descartados: dict[datetime, datetime] = {}
    for i, c in con_q:
        quien = next((f for f, fc in frontera if _domina(fc, c)), None)
        if quien is None:
            frontera.append((i, c))
        else:
            descartados[i.fecha] = quien.fecha
    candidatos = [i for i, _c in frontera] + [i for i in instantes if _componentes(i, cede, recibe) is None]
    return sorted(candidatos, key=lambda i: i.fecha), descartados


def candidatos_de_transferencia(instantes: Sequence[InstanteTransferencia], a: str, b: str
                                ) -> tuple[list[InstanteTransferencia], dict[str, Any]]:
    """Los candidatos de los dos sentidos (unión de las dos fronteras) y la cobertura que
    los justifica (013:RF-27, RF-28)."""
    fronteras = {}
    for cede, recibe in ((a, b), (b, a)):
        cand, desc = frontera_no_dominada(instantes, cede, recibe)
        fronteras[f'{cede}->{recibe}'] = {'candidatos': [_iso(i.fecha) for i in cand],
                                          'descartados': {_iso(t): _iso(d) for t, d in desc.items()}}
    elegidos = {i.fecha for i in instantes
                if any(_iso(i.fecha) in fr['candidatos'] for fr in fronteras.values())}
    candidatos = [i for i in instantes if i.fecha in elegidos]
    cobertura = {'instantes_comunes': len(instantes), 'candidatos': len(candidatos),
                 'desde': _iso(instantes[0].fecha) if instantes else None,
                 'hasta': _iso(instantes[-1].fecha) if instantes else None,
                 'por_sentido': fronteras}
    return candidatos, cobertura


#: Cómo se elige el instante crítico (013:RF-28), para el informe.
CRITERIO = ('instantes con registro de cabecera de los dos alimentadores, sin interpolar; '
            'se descartan los dominados en P y |Q| de los dos; cada candidato se ajusta en '
            'DIgSILENT a sus dos cabeceras y el crítico es el que deja la menor transferencia viable')


def _iso(t: datetime) -> str:
    return t.isoformat(sep=' ')


def transferida_kw(resultado: Mapping[str, Any]) -> float:
    """La carga que pasa en el punto viable más lejano: el seccionador, o el nodo si el
    camino no tiene seccionadores reconocidos; cero si el sentido no admite transferencia."""
    if not resultado.get('admite'):
        return 0.0
    m = resultado.get('maximo_seccionador') or resultado.get('maximo_nodo') or {}
    return float(m.get('carga_kw') or 0.0)


def seleccionar_critico(verificaciones: Sequence[Mapping[str, Any]],
                        candidatos: Sequence[str], *, cancelado: bool = False
                        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """El instante crítico de cada caso, sentido y enlace (013:RF-27 a RF-29).

    ``verificaciones``: una por candidato, caso, sentido y enlace, con ``instante``,
    ``verificado`` (ajuste cuadrado y flujo de cada paso hecho) y el resultado del sentido.
    El crítico es el de menor transferencia viable; a igual, el primero. Si un candidato
    no se verificó en algún sentido, o se canceló, el resultado no es aceptable: se da lo
    observado sin llamarlo capacidad comprobada, y la evidencia que falta.
    """
    grupos: dict[tuple, list[Mapping[str, Any]]] = {}
    for v in verificaciones:
        grupos.setdefault((v['caso'], v['cede'], v['recibe'], v['enlace']), []).append(v)
    criticos, faltantes = [], []
    for clave in sorted(grupos):
        filas = grupos[clave]
        hechos = {v['instante'] for v in filas if v.get('verificado')}
        for v in filas:
            if not v.get('verificado'):
                faltantes.append(f"{v['caso']} · {v['cede']} → {v['recibe']} por {v['enlace']}: "
                                 f"el instante {v['instante']} no se verificó ({v.get('motivo') or 'sin motivo'})")
        for t in candidatos:
            if t not in {v['instante'] for v in filas}:
                faltantes.append(f'{clave[0]} · {clave[1]} → {clave[2]} por {clave[3]}: '
                                 f'el instante {t} no se calculó')
        validos = [v for v in filas if v['instante'] in hechos and v.get('verificado')]
        if not validos:
            continue
        critico = min(validos, key=lambda v: (transferida_kw(v), v['instante']))
        criticos.append({**critico, 'transferida_kw': transferida_kw(critico)})
    if cancelado:
        faltantes.append('el cálculo se canceló antes de verificar todos los instantes')
    if not candidatos:
        faltantes.append('no hay ningún instante con registro de cabecera de los dos alimentadores')
    aceptable = not faltantes and bool(criticos)
    return criticos, {'aceptable': aceptable, 'faltantes': faltantes, 'criterio': CRITERIO}


# --------------------------------------------------------------------------- capacidad
#: Hasta cuántas veces la carga transferida se busca la capacidad del enlace por flujos
#: sucesivos (RF-125). Más allá, el límite no es del enlace sino de otra cosa: se dice.
TOPE_FACTOR = 1024.0
#: Precisión relativa de la bisección: 0,1 % del factor, muy por debajo de lo que
#: distingue un límite de otro en una red de distribución.
TOLERANCIA_FACTOR = 1e-3


def maximo_factor(es_viable, *, tope: float = TOPE_FACTOR,
                  tolerancia: float = TOLERANCIA_FACTOR) -> tuple[float, bool]:
    """El mayor factor de escala de la parte transferida que sigue siendo viable (RF-125).

    ``es_viable(k)`` ejecuta el flujo con la carga transferida multiplicada por ``k``. Se
    parte de 1, que es viable (es la configuración del seccionador viable más lejano), se
    dobla hasta el primero que no lo es y se biseca entre los dos. Devuelve el factor y si
    se llegó al tope sin encontrar límite.
    """
    bajo, alto = 1.0, 2.0
    while es_viable(alto):
        bajo = alto
        if alto >= tope:
            return bajo, True
        alto = min(alto * 2.0, tope)
    while alto - bajo > tolerancia * bajo:
        medio = (bajo + alto) / 2.0
        if es_viable(medio):
            bajo = medio
        else:
            alto = medio
    return bajo, False


def margen(capacidad_kw: float | None, transferida_kw: float) -> float | None:
    """Lo que el enlace puede llevar además de lo que ya transfiere (RF-123)."""
    return None if capacidad_kw is None else capacidad_kw - transferida_kw
