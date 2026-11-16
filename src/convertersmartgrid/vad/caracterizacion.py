"""Caracterización de la carga del Anexo 4 del TdR VAD vigente (108:RF-4, T4).

Desde la medición del conversor (``demanda_medida.Registro``, cada 15 min), calcula por elemento (SED o usuario), por
nivel (MT y BT, sin mezclarse), por opción tarifaria y por las siete agrupaciones del Anexo, y también por sistema
eléctrico o sector típico cuando la clasificación los trae (``vad.anexo4.ambito``):

- el factor de carga, demanda media / demanda máxima (``vad.anexo4.factor_carga``);
- los factores de coincidencia en punta y fuera de punta, con las dos demandas dentro de su periodo
  (``vad.anexo4.factor_coincidencia_punta`` y ``…_fuera_punta``);
- el factor de pérdidas por integración, con la corriente: √(P²+Q²) si todos los registros traen kvar; si no, P,
  que equivale a un factor de potencia constante (``vad.anexo4.factor_perdidas_integral``), y el empírico
  0,7·fc² + 0,3·fc con los coeficientes del registro (``vad.anexo4.factor_perdidas_empirico``);
- la curva por unidad del día útil más representativo (``vad.anexo4.curvas_tipicas``).

Ningún número sale del código: horas de punta, coeficientes, resolución, cuadros y agrupaciones se leen del registro
normativo (``config/vad/tdr_vad_2026_anexo4.json``). Las lecturas del TdR que no son literales van en la
``interpretacion`` de su regla. Una SED sin medición se nombra como hueco y no recibe curva
(``vad.anexo4.sed_sin_medicion``). Los NHUBTIP, NHUBTIB y NHUBTIM de la BT5I son un hueco: el Anexo los define sin
fórmula ni horas de bloque, y aquí no se suponen. Un registro sin kW no cuenta como cero (práctica del conversor,
``curva_de_registros``): queda fuera y se dice cuántos.

La punta es la del TdR, la regla del estudio. Si en la fecha de los registros la RM de horas de punta del registro
(``sein.horas_punta``) da otra ventana, o no hay ninguna vigente, el resultado lo avisa con las dos citas.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Mapping, Sequence

from ..demanda_medida import Registro, curva_de_registros
from ..registro_normativo import RegistroError, RegistroNormativo, ReglaVigente
from . import VadError

NIVELES = ('MT', 'BT')
CLAVE_RM = 'sein.horas_punta'
#: Columnas de los cuadros del Anexo 4 que calcula esta tarea; las demás se nombran como no calculadas.
CALCULADAS = ('FCPP', 'FCFP', 'Factor de Carga', 'Factor de Pérdidas')
REGLAS = ('vad.anexo4.ambito', 'vad.anexo4.horas_punta', 'vad.anexo4.resolucion_registros',
          'vad.anexo4.factor_carga', 'vad.anexo4.factor_coincidencia_punta',
          'vad.anexo4.factor_coincidencia_fuera_punta', 'vad.anexo4.factor_perdidas_integral',
          'vad.anexo4.factor_perdidas_empirico', 'vad.anexo4.curvas_tipicas', 'vad.anexo4.campana_minima',
          'vad.anexo4.sed_sin_medicion', 'vad.anexo4.cuadro_por_opcion', 'vad.anexo4.cuadro_por_agrupacion',
          'vad.anexo4.nhubt_bt5i')

Serie = list[tuple[datetime, float, float | None]]


@dataclass(frozen=True)
class Factores:
    """Factores de una curva (de un elemento o de la suma de un grupo)."""

    factor_carga: float | None
    factor_perdidas: float | None
    factor_perdidas_empirico: float | None
    #: ``corriente`` (√(P²+Q²)) o ``potencia_activa`` (sin kvar: factor de potencia constante supuesto).
    base_perdidas: str
    #: ``(HH:MM, pu)`` del día útil más representativo; base, la máxima de ese día.
    curva_pu: tuple[tuple[str, float], ...]
    dia_tipico: str | None


@dataclass(frozen=True)
class Elemento(Factores):
    nombre: str = ''
    nivel: str = ''
    opcion: str | None = None
    registros: int = 0
    #: Registros sin fecha o sin kW, que no cuentan.
    fuera: int = 0


@dataclass(frozen=True)
class Grupo(Factores):
    nombre: str = ''
    nivel: str = ''
    elementos: tuple[str, ...] = ()
    fcpp: float | None = None
    fcfp: float | None = None
    #: Instantes medidos en todos los elementos del grupo (los únicos que se suman) y los que no.
    instantes: int = 0
    descartados: int = 0
    #: Columnas del cuadro que no aplican (celdas grises) y las que aplican pero no calcula la T4.
    no_aplica: tuple[str, ...] = ()
    no_calculados: tuple[str, ...] = ()


@dataclass(frozen=True)
class Conjunto:
    grupos: dict[str, Grupo] = field(default_factory=dict)
    por_opcion: dict[str, Grupo] = field(default_factory=dict)
    por_agrupacion: dict[str, Grupo] = field(default_factory=dict)


@dataclass(frozen=True)
class Caracterizacion(Conjunto):
    por_elemento: dict[str, Elemento] = field(default_factory=dict)
    por_sistema: dict[str, Conjunto] = field(default_factory=dict)
    por_sector: dict[str, Conjunto] = field(default_factory=dict)
    #: Clave de cada regla usada → su huella (108:RF-9).
    reglas: dict[str, str] = field(default_factory=dict)
    huecos: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()
    #: Reglas usadas que no obligan (norma sin comprobar o sin cita).
    motivos: tuple[str, ...] = ()

    @property
    def conforme(self) -> bool:
        return not self.huecos and not self.motivos


@dataclass
class _Contexto:
    desde: time
    hasta: time
    coef_cuadratico: float
    coef_lineal: float
    huecos: list[str]
    avisos: list[str]

    def en_punta(self, t: datetime) -> bool:
        h = t.time()
        if self.desde < self.hasta:
            return self.desde <= h < self.hasta
        return h >= self.desde or h < self.hasta


def _hora(texto: Any, clave: str) -> time:
    try:
        return datetime.strptime(str(texto), '%H:%M').time()
    except ValueError:
        raise VadError(f'{clave}: la hora {texto!r} no es HH:MM') from None


def _ventana(valor: Mapping[str, Any]) -> str:
    return f'{valor.get("desde")}-{valor.get("hasta")}'


def _cita(rv: ReglaVigente) -> str:
    r = rv.regla
    donde = ', '.join(x for x in (r.articulo_o_anexo, r.pagina, f'líneas {r.lineas}' if r.lineas else '') if x)
    return f'{rv.norma.acto} ({donde}: «{r.cita_literal}»)'


def _cociente(a: float, b: float) -> float | None:
    return a / b if b > 0 else None


def _factores(serie: Serie, ctx: _Contexto, quien: str) -> Factores:
    """Factores de una curva ya ordenada; un denominador nulo es un hueco nombrado, nunca un cero."""
    kws = [p for _t, p, _q in serie]
    maximo = max(kws)
    fc = _cociente(sum(kws) / len(kws), maximo)
    corriente = all(q is not None for _t, _p, q in serie)
    i2 = [p * p + (q * q if corriente else 0.0) for _t, p, q in serie]
    fp = _cociente(sum(i2) / len(i2), max(i2))
    if fc is None or fp is None:
        ctx.huecos.append(f'{quien}: la demanda máxima medida es {maximo} kW; sin demanda no hay factor de carga '
                          'ni de pérdidas')
    emp = None if fc is None else ctx.coef_cuadratico * fc ** 2 + ctx.coef_lineal * fc
    curva, dia = _curva_tipica(serie, ctx, quien)
    return Factores(fc, fp, emp, 'corriente' if corriente else 'potencia_activa', curva, dia)


def _curva_tipica(serie: Serie, ctx: _Contexto, quien: str) -> tuple[tuple[tuple[str, float], ...], str | None]:
    """La curva por unidad del día útil medido cuya demanda media está más cerca de la de los días útiles."""
    dias: dict[date, list[tuple[datetime, float]]] = {}
    for t, p, _q in serie:
        if t.weekday() < 5:
            dias.setdefault(t.date(), []).append((t, p))
    if not dias:
        ctx.huecos.append(f'{quien}: ningún registro es de un día útil; sin él no hay curva típica')
        return (), None
    medias = {d: sum(p for _t, p in v) / len(v) for d, v in dias.items()}
    media = sum(medias.values()) / len(medias)
    dia = min(sorted(medias), key=lambda d: abs(medias[d] - media))
    puntos = dias[dia]
    base = max(p for _t, p in puntos)
    if base <= 0:
        return (), dia.isoformat()
    return tuple((t.strftime('%H:%M'), p / base) for t, p in puntos), dia.isoformat()


def _paso_minutos(serie: Serie) -> float | None:
    pasos = Counter((b[0] - a[0]).total_seconds() / 60 for a, b in zip(serie, serie[1:]) if b[0] > a[0])
    return pasos.most_common(1)[0][0] if pasos else None


def _grupo(nombre: str, nivel: str, miembros: Sequence[str], series: Mapping[str, Serie], ctx: _Contexto,
           no_aplica: Sequence[str] = (), columnas: Sequence[str] = ()) -> Grupo:
    """Suma de las curvas en los instantes medidos en todos; las máximas de cada uno, en el mismo periodo."""
    miembros = tuple(sorted(miembros))
    por_t = [{t: (p, q) for t, p, q in series[m]} for m in miembros]
    todos = set().union(*por_t)
    comunes = sorted(set.intersection(*(set(d) for d in por_t)))
    if len(todos) > len(comunes):
        ctx.avisos.append(f'{nombre}: {len(todos) - len(comunes)} instantes no están medidos en todos sus elementos '
                          'y no se suman')
    if not comunes:
        ctx.huecos.append(f'{nombre}: sus elementos no tienen ningún instante medido en común')
        return Grupo(None, None, None, 'potencia_activa', (), None, nombre=nombre, nivel=nivel, elementos=miembros,
                     descartados=len(todos), no_aplica=tuple(no_aplica),
                     no_calculados=tuple(c for c in columnas if c not in CALCULADAS and c not in no_aplica))
    suma: Serie = []
    for t in comunes:
        qs = [d[t][1] for d in por_t]
        suma.append((t, sum(d[t][0] for d in por_t), None if None in qs else sum(qs)))
    coincidencia = {}
    for clave, periodo in (('fcpp', 'punta'), ('fcfp', 'fuera de punta')):
        dentro = [k for k, t in enumerate(comunes) if ctx.en_punta(t) == (clave == 'fcpp')]
        if not dentro:
            ctx.huecos.append(f'{nombre}: ningún registro en horas de {periodo}; sin {clave.upper()}')
            coincidencia[clave] = None
            continue
        coincidente = max(suma[k][1] for k in dentro)
        individuales = sum(max(d[comunes[k]][0] for k in dentro) for d in por_t)
        coincidencia[clave] = _cociente(coincidente, individuales)
        if coincidencia[clave] is None:
            ctx.huecos.append(f'{nombre}: sin demanda en horas de {periodo}; sin {clave.upper()}')
    f = _factores(suma, ctx, nombre)
    return Grupo(**vars(f), nombre=nombre, nivel=nivel, elementos=miembros, instantes=len(comunes),
                 descartados=len(todos) - len(comunes), no_aplica=tuple(no_aplica),
                 no_calculados=tuple(c for c in columnas if c not in CALCULADAS and c not in no_aplica), **coincidencia)


def _conjunto(prefijo: str, clases: Mapping[str, tuple[str, str | None]], series: Mapping[str, Serie],
              cuadro: Mapping[str, Mapping[str, Any]], agrupaciones: Sequence[Mapping[str, Any]],
              columnas_agr: Sequence[str], ctx: _Contexto) -> Conjunto:
    def miembros(cond) -> list[str]:
        return [n for n, (nivel, op) in clases.items() if cond(nivel, op)]

    grupos = {nivel: _grupo(f'{prefijo}{nivel}', nivel, m, series, ctx)
              for nivel in NIVELES if (m := miembros(lambda nv, _o, x=nivel: nv == x))}
    por_opcion = {}
    for op, fila in cuadro.items():
        if m := miembros(lambda _n, o, x=op: o == x):
            por_opcion[op] = _grupo(f'{prefijo}opción {op}', fila['nivel'], m, series, ctx,
                                    fila.get('no_aplica_gris') or (), fila.get('columnas') or ())
    por_agrupacion = {}
    for agr in agrupaciones:
        nombre = '+'.join(agr['opciones'])
        if m := miembros(lambda _n, o, x=agr['opciones']: o in x):
            por_agrupacion[nombre] = _grupo(f'{prefijo}agrupación {nombre}', agr['nivel'], m, series, ctx, (),
                                            columnas_agr)
    return Conjunto(grupos, por_opcion, por_agrupacion)


def _clasificar(nombre: str, valor: Any, cuadro: Mapping[str, Mapping[str, Any]],
                huecos: list[str]) -> tuple[str, str | None, str | None, str | None] | None:
    """(nivel, opción, sistema, sector) o None si no se puede caracterizar; cada problema es un hueco nombrado."""
    datos = valor if isinstance(valor, Mapping) else {'nivel': valor}
    nivel, opcion = datos.get('nivel'), datos.get('opcion')
    if opcion is not None:
        fila = cuadro.get(opcion)
        if fila is None:
            huecos.append(f'{nombre}: la opción tarifaria {opcion!r} no está en el cuadro por opción del Anexo 4')
            opcion = None
        elif nivel is not None and nivel != fila['nivel']:
            huecos.append(f'{nombre}: la opción {opcion} es de {fila["nivel"]} y la clasificación dice {nivel!r}')
            return None
        else:
            nivel = fila['nivel']
    if nivel not in NIVELES:
        huecos.append(f'{nombre}: nivel {nivel!r}; el Anexo 4 caracteriza MT y BT por separado')
        return None
    return nivel, opcion, datos.get('sistema'), datos.get('sector')


def _avisos_horas_punta(fechas: set[date], registro: RegistroNormativo, tdr: ReglaVigente) -> list[str]:
    """Aviso, por tramo de fechas, si la RM vigente da otra ventana que el TdR o si no hay ninguna RM vigente."""
    ventana = _ventana(tdr.regla.valor)
    uso = f'se usa la del TdR, {ventana}, regla del estudio: {_cita(tdr)}'
    if not fechas:
        return []
    if not any(r.clave == CLAVE_RM for n in registro.normas.values() for r in n.reglas):
        return [f'Horas de punta: el registro no trae «{CLAVE_RM}» y no se cotejó con la RM vigente; {uso}']
    tramos: list[list[Any]] = []
    for dia in sorted(fechas):
        try:
            rv = registro.regla(CLAVE_RM, dia)
        except RegistroError:
            rv = None
        acto = rv.norma.acto if rv else None
        if tramos and tramos[-1][0] == acto:
            tramos[-1][2] = dia
        else:
            tramos.append([acto, dia, dia, rv])
    avisos = []
    for _acto, d0, d1, rv in tramos:
        dias = f'el {d0}' if d0 == d1 else f'del {d0} al {d1}'
        if rv is None:
            avisos.append(f'Horas de punta: {dias} no hay ninguna RM de horas de punta vigente en el registro; {uso}')
        elif _ventana(rv.regla.valor) != ventana:
            avisos.append(f'Horas de punta: {dias} la RM vigente da {_ventana(rv.regla.valor)}: {_cita(rv)}; {uso}')
    return avisos


def caracterizar(registros: Mapping[str, Sequence[Registro]], clasificacion: Mapping[str, Any],
                 registro: RegistroNormativo, *, fecha_estudio: str | None = None) -> Caracterizacion:
    """Caracteriza la carga según el Anexo 4 (108:RF-4).

    ``registros``: medición de cada elemento. ``clasificacion``: de cada elemento, su nivel (``'MT'`` o ``'BT'``) o
    un diccionario con ``nivel``, ``opcion`` (la del cuadro del Anexo), ``sistema`` y ``sector``. Las reglas se
    toman del TdR vigente en ``fecha_estudio`` (por defecto, el registrado).
    """
    reglas: dict[str, ReglaVigente] = {}
    for clave in REGLAS:
        try:
            reglas[clave] = registro.regla(clave, fecha_estudio)
        except RegistroError as exc:
            raise VadError(f'caracterización del Anexo 4: {exc}') from None
    motivos = [f'{c}: la regla no obliga ({rv.estado}{"" if rv.regla.citada else ", sin cita"})'
               for c, rv in reglas.items() if not rv.obligatoria]
    hp = reglas['vad.anexo4.horas_punta'].regla.valor
    emp = reglas['vad.anexo4.factor_perdidas_empirico'].regla.valor
    ctx = _Contexto(_hora(hp.get('desde'), 'vad.anexo4.horas_punta'), _hora(hp.get('hasta'), 'vad.anexo4.horas_punta'),
                    float(emp['coef_cuadratico']), float(emp['coef_lineal']), [], [])
    tabla = reglas['vad.anexo4.cuadro_por_opcion'].regla.valor
    cuadro = {f['opcion']: {**f, 'columnas': tabla['columnas']} for f in tabla['filas']}
    agr = reglas['vad.anexo4.cuadro_por_agrupacion'].regla.valor
    resolucion = float(reglas['vad.anexo4.resolucion_registros'].regla.valor)
    sin_medicion = reglas['vad.anexo4.sed_sin_medicion'].regla

    clases: dict[str, tuple[str, str | None, str | None, str | None]] = {}
    for nombre in sorted(clasificacion):
        clase = _clasificar(nombre, clasificacion[nombre], cuadro, ctx.huecos)
        if clase is not None:
            clases[nombre] = clase
    for nombre in sorted(set(registros) - set(clasificacion)):
        ctx.huecos.append(f'{nombre}: tiene medición pero no clasificación (nivel u opción tarifaria)')

    series: dict[str, Serie] = {}
    por_elemento: dict[str, Elemento] = {}
    sin_kvar, otra_resolucion, campana_corta, fechas = [], [], [], set()
    for nombre, (nivel, opcion, _s, _t) in clases.items():
        serie, fuera = curva_de_registros(registros.get(nombre) or ())
        if not serie:
            ctx.huecos.append(f'{nombre}: sin medición; el Anexo 4 no le da curva ({sin_medicion.pagina}: '
                              f'«{sin_medicion.cita_literal}»)')
            continue
        f = _factores(serie, ctx, nombre)
        if f.factor_carga is None:
            continue
        series[nombre] = serie
        por_elemento[nombre] = Elemento(**vars(f), nombre=nombre, nivel=nivel, opcion=opcion, registros=len(serie),
                                        fuera=fuera)
        dias = {t.date() for t, _p, _q in serie}
        fechas |= dias
        if f.base_perdidas != 'corriente':
            sin_kvar.append(nombre)
        paso = _paso_minutos(serie)
        if paso is not None and paso != resolucion:
            otra_resolucion.append(f'{nombre} ({paso:g} min)')
        if len(dias) < 7 or not {5, 6} <= {d.weekday() for d in dias}:
            campana_corta.append(nombre)
    if sin_kvar:
        ctx.avisos.append('Pérdidas con la potencia activa, sin kvar en todos los registros (equivale a suponer un '
                          'factor de potencia constante): ' + ', '.join(sin_kvar))
    if otra_resolucion:
        ctx.avisos.append(f'Registros con otro paso que el del Anexo 4 ({resolucion:g} min): '
                          + ', '.join(otra_resolucion))
    if campana_corta:
        ctx.avisos.append('Medición de menos de una semana con sábado y domingo, la campaña mínima del Anexo 4: '
                          + ', '.join(campana_corta))
    nhubti = reglas['vad.anexo4.nhubt_bt5i'].regla
    if any(clases[n][1] == 'BT5I' for n in por_elemento):
        ctx.huecos.append(f'BT5I: NHUBTIP, NHUBTIB y NHUBTIM están definidos en el Anexo 4 ({nhubti.pagina}) sin '
                          'fórmula ni horas de los bloques base y media; no se calculan ni se suponen')
    ctx.avisos.extend(_avisos_horas_punta(fechas, registro, reglas['vad.anexo4.horas_punta']))

    medidos = {n: (clases[n][0], clases[n][1]) for n in por_elemento}
    general = _conjunto('', medidos, series, cuadro, agr['grupos'], agr['columnas'], ctx)
    ambitos: dict[str, dict[str, Conjunto]] = {}
    for indice, campo in ((2, 'sistema'), (3, 'sector')):
        valores = sorted({clases[n][indice] for n in por_elemento if clases[n][indice] is not None})
        ambitos[campo] = {v: _conjunto(f'{campo} {v} / ', {n: c for n, c in medidos.items() if clases[n][indice] == v},
                                       series, cuadro, agr['grupos'], agr['columnas'], ctx) for v in valores}
    return Caracterizacion(general.grupos, general.por_opcion, general.por_agrupacion, por_elemento=por_elemento,
                           por_sistema=ambitos['sistema'], por_sector=ambitos['sector'],
                           reglas={c: rv.huella() for c, rv in reglas.items()}, huecos=tuple(ctx.huecos),
                           avisos=tuple(ctx.avisos), motivos=tuple(motivos))
