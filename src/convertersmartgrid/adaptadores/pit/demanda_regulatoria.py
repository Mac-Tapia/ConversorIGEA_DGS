"""Demanda regulatoria del PIT, paso 3b (107 T28): F-102, F-101 y F-103 desde la medida del año representativo.

La norma (RCD 217-2013, reglas ``pit.demanda.definiciones_factores`` y ``pit.demanda.definiciones_participacion``):
  - F-102: P y Q de cada devanado en cuatro momentos: la máxima anual del sistema eléctrico, la de su SET, la del SEIN y
    la máxima no coincidente (la del propio devanado, en su instante);
  - F-101: FC = P media / P máxima; FCP = P a la hora de máxima de su nivel superior (la SET del devanado, el sistema de
    la SET) / su P máxima; FS = P a la hora de máxima del SEIN / su P máxima;
  - F-103: FPHMS = P del devanado a la hora de máxima del sistema / máxima del sistema; FPMWHS = energía del devanado /
    energía del sistema.

Reglas del diseño aceptado por el auditor (ca 04:55, 05:05, 05:25 y 05:40; 28, 23:31):
  - la curva de un devanado es la suma, instante a instante, de las de sus alimentadores. Un instante en el que falta el
    registro de alguno NO entra (ni en la máxima ni en la media) y se cuenta: nunca se rellena ni se escala. Sin la curva
    de un alimentador, el devanado entero es un hueco con su causa;
  - el instante de máxima del SEIN sale del registro de datos del COES (``coes.sein.maxima_anual.<año>``), nunca de la
    medida de la empresa. Sin él, la columna SEIN de F-102 y el FS quedan vacíos con su motivo;
  - la marca de tiempo del COES no declara si rotula el inicio o el fin de su intervalo de 15 minutos
    (``coes.sein.convencion_marca_tiempo``): se calculan las dos alineaciones, [h, h+15) y [h−15, h), con la convención
    del medidor de la empresa que declara el perfil. Si dan lo mismo dentro de la tolerancia, se usa la cifra con la
    marca; si difieren, hueco con las dos cifras. La tolerancia sale del perfil o del registro (``tolerancia_de``);
  - la máxima anual del COES es la fuente primaria. Las 12 mensuales son su contraste, y una diferencia se nombra. Una
    fecha anual fuera del año de su estadística es un error, salvo que el registro traiga la corrección con su marca.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ...dominio.registro_normativo import RegistroError, RegistroNormativo
from ...dominio.pit.ambito import AreaPit, PitError
from ...aplicacion.pit.red_area import RedArea

Punto = tuple[datetime, float, float | None]

# Tolerancia de las dos alineaciones del instante del SEIN (decisión del auditor 28, 2026-11-15), por procedencia:
#   1. la resolución del medidor que declara el perfil (kW), si la da;
#   2. si no, el error admisible de la clase del medidor del perfil (``medida.error_admisible_por_clase``,
#      RM 496-2005-MEM/DM, Tabla N° 01);
#   3. sin clase en el perfil, la clase por defecto en MT (``medida.clase_por_defecto_mt``, Guía TUPA del INACAL).
ORIGEN_TOLERANCIA_PERFIL = 'resolución del medidor declarada en el perfil'
ORIGEN_CLASE_PERFIL = 'clase del medidor declarada en el perfil'
ORIGEN_CLASE_DEFECTO = 'clase por defecto (práctica INACAL para MT, Guía TUPA, sha 6855ac9c, pág. 4)'
CONVENCIONES = ('inicio', 'fin')


@dataclass(frozen=True)
class Tolerancia:
    """Cuánto pueden diferir las dos alineaciones para «dar lo mismo», y de dónde sale."""
    origen: str
    kw: float | None = None
    relativa: float | None = None
    traza: Mapping[str, Any] = field(default_factory=dict)

    def en_kw(self, a: float, b: float) -> float:
        return self.kw if self.kw is not None else float(self.relativa or 0.0) * max(abs(a), abs(b))


def tolerancia_de(registro: RegistroNormativo, *, tolerancia_kw: float | None = None,
                  clase: str | None = None) -> Tolerancia:
    """La tolerancia según lo que declara el perfil del medidor, con la regla del registro que la respalda."""
    if tolerancia_kw is not None:
        return Tolerancia(ORIGEN_TOLERANCIA_PERFIL, kw=float(tolerancia_kw))
    try:
        vig = registro.regla('medida.error_admisible_por_clase')
    except RegistroError as exc:
        raise PitError(f'sin la resolución del medidor en el perfil hace falta el error admisible por clase del '
                       f'registro ({exc})') from exc
    tabla, origen = vig.regla.valor, ORIGEN_CLASE_PERFIL
    traza = {'regla': 'medida.error_admisible_por_clase', 'acto': vig.norma.acto, 'huella': vig.huella}
    if clase is None:
        try:
            defecto = registro.regla('medida.clase_por_defecto_mt')
        except RegistroError as exc:
            raise PitError(f'el perfil no declara la clase del medidor y el registro no trae la clase por defecto '
                           f'({exc})') from exc
        clase, origen = str(defecto.regla.valor), ORIGEN_CLASE_DEFECTO
        traza['clase_por_defecto'] = {'regla': 'medida.clase_por_defecto_mt', 'acto': defecto.norma.acto}
    if clase not in tabla:
        raise PitError(f'la clase {clase!r} del medidor no está en la tabla del error admisible ({", ".join(tabla)})')
    return Tolerancia(f'{origen}: {clase}, ±{tabla[clase]} %', relativa=float(tabla[clase]) / 100,
                      traza={**traza, 'clase': clase})


@dataclass
class CurvaSumada:
    """Curva de un devanado, una SET o un sistema: solo los instantes completos, y lo que quedó fuera."""
    nombre: str
    puntos: dict[datetime, tuple[float, float | None]]
    excluidos: int = 0
    instantes_esperados: int = 0
    hueco: str | None = None
    componentes: tuple[str, ...] = ()

    @property
    def cobertura(self) -> float:
        return len(self.puntos) / self.instantes_esperados if self.instantes_esperados else 0.0

    def maxima(self) -> tuple[datetime, float, float | None] | None:
        if not self.puntos:
            return None
        t = max(self.puntos, key=lambda k: (self.puntos[k][0], -k.timestamp()))
        return t, *self.puntos[t]


@dataclass
class Topologia:
    """Sistema eléctrico → SET → devanado → alimentadores, tal como lo dan el perfil del PIT y la red del área."""
    sistemas: Mapping[str, Sequence[str]]
    sets: Mapping[str, Sequence[str]]
    devanados: Mapping[str, Sequence[str]]

    def set_de(self, devanado: str) -> str:
        return next(s for s, ds in self.sets.items() if devanado in ds)

    def sistema_de(self, set_: str) -> str:
        return next(s for s, ss in self.sistemas.items() if set_ in ss)


@dataclass
class InstanteSein:
    """El instante de máxima del SEIN de un año, con su cita, o el motivo por el que no lo hay."""
    anio: int
    instante: datetime | None = None
    potencia_mw: float | None = None
    traza: dict[str, Any] = field(default_factory=dict)
    motivo: str | None = None
    avisos: list[str] = field(default_factory=list)


def _instantes_del_anio(anio: int, intervalo_min: int) -> int:
    return int((date(anio + 1, 1, 1) - date(anio, 1, 1)).days * 24 * 60 / intervalo_min)


def _sumar(nombre: str, partes: Mapping[str, CurvaSumada], esperados: int) -> CurvaSumada:
    huecos = [f'{n}: {c.hueco}' for n, c in partes.items() if c.hueco]
    if huecos:
        return CurvaSumada(nombre, {}, instantes_esperados=esperados, componentes=tuple(partes),
                           hueco='sin la curva completa de ' + '; '.join(huecos))
    todos = set().union(*(c.puntos for c in partes.values())) if partes else set()
    puntos, fuera = {}, 0
    for t in sorted(todos):
        if all(t in c.puntos for c in partes.values()):
            ps = [c.puntos[t] for c in partes.values()]
            q = None if any(p[1] is None for p in ps) else sum(p[1] for p in ps)
            puntos[t] = (sum(p[0] for p in ps), q)
        else:
            fuera += 1
    return CurvaSumada(nombre, puntos, fuera, esperados, componentes=tuple(partes))


def curvas_por_devanado(curvas: Mapping[str, Sequence[Punto]], topologia: Topologia, anio: int,
                        intervalo_min: int = 15) -> dict[str, CurvaSumada]:
    """La curva de cada devanado: la suma de las de sus alimentadores en los instantes del año representativo."""
    esperados = _instantes_del_anio(anio, intervalo_min)
    out = {}
    for dev, alimentadores in topologia.devanados.items():
        faltan = [a for a in alimentadores if a not in curvas or not curvas[a]]
        if faltan:
            out[dev] = CurvaSumada(dev, {}, instantes_esperados=esperados, componentes=tuple(alimentadores),
                                   hueco=f'sin medida de {", ".join(faltan)}: no se escala la parte que sí hay')
            continue
        partes = {a: CurvaSumada(a, {t: (p, q) for t, p, q in curvas[a] if t.year == anio}) for a in alimentadores}
        out[dev] = _sumar(dev, partes, esperados)
    return out


def curvas_de_niveles(devanados: Mapping[str, CurvaSumada], topologia: Topologia
                      ) -> tuple[dict[str, CurvaSumada], dict[str, CurvaSumada]]:
    """Curvas de cada SET (suma de sus devanados) y de cada sistema (suma de sus SET), con los mismos criterios."""
    esperados = next(iter(devanados.values())).instantes_esperados if devanados else 0
    sets = {s: _sumar(s, {d: devanados[d] for d in ds}, esperados) for s, ds in topologia.sets.items()}
    sistemas = {s: _sumar(s, {x: sets[x] for x in ss}, esperados) for s, ss in topologia.sistemas.items()}
    return sets, sistemas


def instante_sein(registro: RegistroNormativo, anio: int) -> InstanteSein:
    """La máxima anual del SEIN del registro del COES, comprobada contra su contraste mensual y las horas punta."""
    res = InstanteSein(anio)
    try:
        vig = registro.regla(f'coes.sein.maxima_anual.{anio}')
    except RegistroError as exc:
        res.motivo = f'el registro del COES no trae la máxima anual del SEIN de {anio} ({exc})'
        return res
    v = vig.regla.valor
    t = datetime.fromisoformat(f'{v["fecha"]}T{v["hora"]}')
    if t.year != anio:
        raise PitError(f'coes.sein.maxima_anual.{anio}: la fecha {v["fecha"]} cae fuera del año {anio} de su '
                       'estadística y el registro no trae la corrección con su marca')
    res.instante, res.potencia_mw = t, float(v['potencia_mw'])
    res.traza = {'regla': f'coes.sein.maxima_anual.{anio}', 'acto': vig.norma.acto, 'huella': vig.huella,
                 'cita': vig.regla.cita_literal, 'pagina': vig.regla.pagina}
    if 'publicado' in v:
        res.traza.update({'publicado': v['publicado'], 'marca': v.get('marca')})
        if not v.get('marca'):
            raise PitError(f'coes.sein.maxima_anual.{anio}: trae una fecha corregida sin su marca')
        res.avisos.append(f'máxima del SEIN de {anio}: el COES publica {v["publicado"]["fecha"]} '
                          f'{v["publicado"]["hora"]}; se usa {v["fecha"]} {v["hora"]} ({v["marca"]})')
    try:
        meses = registro.regla(f'coes.sein.maximas_mensuales.{anio}').regla.valor
        mayor = max(meses.values())
        if abs(mayor - res.potencia_mw) > 1e-6 * max(1.0, mayor):
            res.avisos.append(f'máxima del SEIN de {anio}: la anual ({res.potencia_mw:.3f} MW) no coincide con la mayor '
                              f'de las 12 mensuales ({mayor:.3f} MW); diferencia {res.potencia_mw - mayor:+.3f} MW')
    except RegistroError:
        res.avisos.append(f'máxima del SEIN de {anio}: sin las 12 mensuales del COES no se contrasta la anual')
    _contrastar_reporte(registro, res, t)
    try:
        res.traza['convencion_por_defecto'] = dict(registro.regla('coes.sein.convencion_por_defecto').regla.valor)
    except RegistroError:
        res.avisos.append('el registro no trae la convención por defecto del instante del SEIN: si las dos '
                          'alineaciones dan lo mismo se muestra [h, h+15)')
    try:
        hp = registro.regla('sein.horas_punta', t.date().isoformat()).regla.valor
        if not hp['desde'] <= t.strftime('%H:%M') <= hp['hasta']:
            res.avisos.append(f'máxima del SEIN de {anio}: {t:%H:%M} cae fuera de las horas punta '
                              f'{hp["desde"]}-{hp["hasta"]}')
    except RegistroError:
        res.avisos.append(f'máxima del SEIN de {anio}: ninguna norma del registro fija las horas punta vigentes el '
                          f'{t.date().isoformat()}; no se comprueba la ventana')
    return res


_MESES = ('ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SET', 'OCT', 'NOV', 'DIC')


def _contrastar_reporte(registro: RegistroNormativo, res: InstanteSein, t: datetime) -> None:
    """Tercera fuente: el reporte mensual de máxima demanda del COES (MW de medidores, no consolidados). Si su mes de
    la anual trae la misma fecha y hora, la confirma; si su mayor mes no es el de la anual, se nombra. Manda la anual."""
    try:
        meses = registro.regla(f'coes.sein.reporte_mensual.{res.anio}').regla.valor
    except RegistroError:
        res.avisos.append(f'máxima del SEIN de {res.anio}: sin el reporte mensual del COES no se contrasta la fecha')
        return
    propio = meses.get(_MESES[t.month - 1]) or {}
    confirma = propio.get('fecha') == t.date().isoformat() and propio.get('hora') == t.strftime('%H:%M')
    res.traza['reporte_mensual'] = {'confirma_fecha_y_hora': confirma, 'mes': _MESES[t.month - 1], **propio}
    if not confirma:
        res.avisos.append(f'máxima del SEIN de {res.anio}: el reporte mensual del COES da {propio.get("fecha")} '
                          f'{propio.get("hora")} en ese mes, no {t:%Y-%m-%d %H:%M}')
    mayor = max(meses, key=lambda m: meses[m]['potencia_mw'])
    if mayor != _MESES[t.month - 1]:
        m = meses[mayor]
        res.avisos.append(f'máxima del SEIN de {res.anio}: el reporte mensual del COES (MW de medidores) da la mayor en '
                          f'{mayor} ({m["fecha"]} {m["hora"]}, {m["potencia_mw"]:.3f} MW) y la Estadística Anual en '
                          f'{_MESES[t.month - 1]}; manda la estadística')


def _valor_sein(curva: CurvaSumada, sein: InstanteSein, convencion: str | None,
                tolerancia: Tolerancia, intervalo_min: int) -> dict[str, Any]:
    """P y Q de la curva en el instante del SEIN, por las dos alineaciones del intervalo del COES."""
    if sein.instante is None:
        return {'valor': None, 'motivo': sein.motivo}
    if convencion not in CONVENCIONES:
        return {'valor': None, 'motivo': 'el perfil no declara si la marca del medidor de la empresa rotula el inicio o '
                                         'el fin del intervalo; no se supone'}
    h, d = sein.instante, timedelta(minutes=intervalo_min)
    # El intervalo [a, a+d) lleva la marca a (inicio) o a+d (fin) en el medidor de la empresa.
    marcas = {'[h, h+15)': h if convencion == 'inicio' else h + d, '[h-15, h)': h - d if convencion == 'inicio' else h}
    vals = {k: curva.puntos.get(t) for k, t in marcas.items()}
    if any(v is None for v in vals.values()):
        falta = [f'{k} (marca {marcas[k]:%Y-%m-%d %H:%M})' for k, v in vals.items() if v is None]
        return {'valor': None, 'motivo': f'la curva no tiene el instante del SEIN en {", ".join(falta)}',
                'alineaciones': {k: (v[0] if v else None) for k, v in vals.items()}}
    a, b = vals['[h, h+15)'], vals['[h-15, h)']
    tol = tolerancia.en_kw(a[0], b[0])
    origen = tolerancia.origen
    alineaciones = {k: v[0] for k, v in vals.items()}
    if abs(a[0] - b[0]) <= tol:
        # Decisión de 28 (2026-11-15): si hay que mostrar una sola, la de fin de intervalo, [h-15, h), con la marca de
        # su procedencia (práctica observada del COES, no norma). Sin esa regla en el registro, [h, h+15) y se dice.
        defecto = (sein.traza.get('convencion_por_defecto') or {})
        fin = defecto.get('alineacion') == 'fin'
        clave = '[h-15, h)' if fin else '[h, h+15)'
        marca = 'convención no declarada; resultado igual en las dos; ' + (
            f'se muestra la de fin del intervalo {clave}: {defecto.get("marca")}' if fin
            else 'sin convención por defecto en el registro, se muestra [h, h+15)')
        return {'valor': vals[clave], 'marca': marca, 'alineaciones': alineaciones, 'tolerancia_kw': tol,
                'tolerancia_origen': origen, 'instante': marcas[clave]}
    return {'valor': None, 'alineaciones': alineaciones, 'tolerancia_kw': tol, 'tolerancia_origen': origen,
            'motivo': (f'las dos alineaciones del intervalo del COES dan {a[0]:.2f} y {b[0]:.2f} kW (más de '
                       f'{tol:.2f} kW de diferencia): la convención no declarada cambia el resultado')}


def _momento(curva: CurvaSumada, t: datetime | None, motivo: str | None = None) -> dict[str, Any]:
    if t is None or t not in curva.puntos:
        return {'fecha': None, 'hora': None, 'kw': None, 'kvar': None,
                'motivo': motivo or 'el instante no está entre los instantes completos de la curva'}
    p, q = curva.puntos[t]
    return {'fecha': t.strftime('%Y/%m/%d'), 'hora': t.strftime('%H:%M'), 'kw': round(p, 2),
            'kvar': None if q is None else round(q, 2), 'instante': t}


def datos_f102(devanados: Mapping[str, CurvaSumada], topologia: Topologia, sein: InstanteSein, *,
               convencion: str | None, tolerancia: Tolerancia, intervalo_min: int = 15) -> dict[str, Any]:
    """Los cuatro momentos de F-102 por devanado, y la no coincidente y la coincidente de cada SET en la traza."""
    sets, sistemas = curvas_de_niveles(devanados, topologia)
    filas, huecos = [], []
    for dev, curva in devanados.items():
        s = topologia.set_de(dev)
        sis = topologia.sistema_de(s)
        if curva.hueco:
            huecos.append({'devanado': dev, 'motivo': curva.hueco})
            continue
        m_sis, m_set = sistemas[sis].maxima(), sets[s].maxima()
        sein_v = _valor_sein(curva, sein, convencion, tolerancia, intervalo_min)
        momento_sein = (_momento(curva, sein_v['instante']) if sein_v.get('valor') is not None
                        else {'fecha': None, 'hora': None, 'kw': None, 'kvar': None, 'motivo': sein_v['motivo']})
        momento_sein['traza_sein'] = {**{k: v for k, v in sein_v.items() if k not in ('valor', 'instante')},
                                      **sein.traza}
        filas.append({
            'sistema': sis, 'set': s, 'devanado': dev,
            'sistema_electrico': _momento(curva, m_sis[0] if m_sis else None, sistemas[sis].hueco),
            'set_maxima': _momento(curva, m_set[0] if m_set else None, sets[s].hueco),
            'sein': momento_sein,
            'no_coincidente': _momento(curva, curva.maxima()[0] if curva.maxima() else None),
            'excluidos': curva.excluidos, 'cobertura': round(curva.cobertura, 6)})
    por_set = {}
    for s, c in sets.items():
        maximas = [devanados[d].maxima() for d in topologia.sets[s] if devanados[d].maxima()]
        mc = c.maxima()
        por_set[s] = {'no_coincidente_kw': round(sum(m[1] for m in maximas), 2) if len(maximas) == len(topologia.sets[s])
                      else None, 'coincidente_kw': round(mc[1], 2) if mc else None,
                      'calculo': 'no coincidente = suma de la máxima de cada devanado en su instante; coincidente = '
                                 'máxima de la suma', 'hueco': c.hueco}
    return {'filas': filas, 'huecos': huecos, 'sets': por_set, 'avisos': _avisos(devanados, sein)}


def _avisos(devanados: Mapping[str, CurvaSumada], sein: InstanteSein) -> list[str]:
    avisos = list(sein.avisos)
    for d, c in devanados.items():
        if c.hueco:
            continue
        if c.cobertura < 1:
            avisos.append(f'{d}: la curva cubre el {100 * c.cobertura:.1f} % del año ({len(c.puntos)} de '
                          f'{c.instantes_esperados} instantes); el FC usa las horas medidas')
        if c.excluidos:
            avisos.append(f'{d}: {c.excluidos} instantes excluidos por faltar el registro de algún alimentador')
    return avisos


def _cita(registro: RegistroNormativo, clave: str) -> dict[str, Any]:
    vig = registro.regla(clave)
    return {'regla': clave, 'acto': vig.norma.acto, 'huella': vig.huella}


def datos_f101(devanados: Mapping[str, CurvaSumada], topologia: Topologia, sein: InstanteSein,
               registro: RegistroNormativo, *, convencion: str | None, tolerancia: Tolerancia,
               intervalo_min: int = 15) -> dict[str, Any]:
    """FC, FCP y FS de cada devanado, SET y sistema, con la fórmula y la regla citadas."""
    cita = _cita(registro, 'pit.demanda.definiciones_factores')
    sets, sistemas = curvas_de_niveles(devanados, topologia)
    niveles = ([('devanado', n, c, sets[topologia.set_de(n)]) for n, c in devanados.items()]
               + [('set', n, c, sistemas[topologia.sistema_de(n)]) for n, c in sets.items()]
               + [('sistema', n, c, c) for n, c in sistemas.items()])
    filas, avisos_fcp = [], []
    for nivel, nombre, c, superior in niveles:
        m = c.maxima()
        if c.hueco or m is None or m[1] == 0:
            filas.append({'nivel': nivel, 'nombre': nombre, 'fc': None, 'fcp': None, 'fs': None,
                          'motivo': c.hueco or 'curva sin instantes completos o con máxima nula'})
            continue
        pmax = m[1]
        fc = sum(p for p, _q in c.puntos.values()) / len(c.puntos) / pmax
        ms = superior.maxima()
        # Los dos términos salen de las mismas curvas de la empresa (el mismo año y la misma marca de 15 minutos), así
        # que la alineación del FCP es la del medidor y no la del COES: no hay dos alineaciones que comparar aquí.
        fcp = (c.puntos[ms[0]][0] / pmax) if ms and ms[0] in c.puntos else None
        if fcp is not None and fcp > 1 + 1e-9:
            avisos_fcp.append(f'{nombre}: FCP {fcp:.4f} mayor que 1; revisar la curva')
        sv = _valor_sein(c, sein, convencion, tolerancia, intervalo_min)
        fs = sv['valor'][0] / pmax if sv.get('valor') is not None else None
        filas.append({
            'nivel': nivel, 'nombre': nombre, 'fc': round(fc, 4), 'fcp': None if fcp is None else round(fcp, 4),
            'fs': None if fs is None else round(fs, 4), 'motivo_fs': None if fs is not None else sv['motivo'],
            'traza': {**cita, 'fc': 'P media de los instantes completos / P máxima',
                      'fcp': f'P a la hora de máxima de {superior.nombre} / P máxima',
                      'fs': 'P a la hora de máxima del SEIN / P máxima', 'instantes': len(c.puntos),
                      'excluidos': c.excluidos, 'sein': {k: v for k, v in sv.items() if k not in ('valor', 'instante')}}})
    return {'filas': filas, 'avisos': _avisos(devanados, sein) + avisos_fcp}


def datos_f103(devanados: Mapping[str, CurvaSumada], topologia: Topologia, registro: RegistroNormativo,
               intervalo_min: int = 15) -> dict[str, Any]:
    """FPHMS y FPMWHS de cada devanado respecto de su sistema eléctrico."""
    cita = _cita(registro, 'pit.demanda.definiciones_participacion')
    _sets, sistemas = curvas_de_niveles(devanados, topologia)
    horas = intervalo_min / 60
    filas = []
    for dev, c in devanados.items():
        sis = sistemas[topologia.sistema_de(topologia.set_de(dev))]
        m = sis.maxima()
        if c.hueco or sis.hueco or m is None:
            filas.append({'devanado': dev, 'fphms': None, 'fpmwhs': None, 'motivo': c.hueco or sis.hueco or
                          'el sistema no tiene instantes completos'})
            continue
        e_sis = sum(p for p, _q in sis.puntos.values()) * horas
        e_dev = sum(c.puntos[t][0] for t in sis.puntos) * horas
        filas.append({'devanado': dev, 'sistema': sis.nombre, 'fphms': round(c.puntos[m[0]][0] / m[1], 4),
                      'fpmwhs': round(e_dev / e_sis, 4) if e_sis else None,
                      'traza': {**cita, 'fphms': f'P del devanado el {m[0]:%Y/%m/%d %H:%M} / máxima de {sis.nombre}',
                                'fpmwhs': 'energía del devanado / energía del sistema, en los instantes completos del '
                                          'sistema', 'energia_kwh': {'devanado': round(e_dev, 2),
                                                                     'sistema': round(e_sis, 2)}}})
    return {'filas': filas}


def topologia_desde(area: AreaPit, red: RedArea, sistemas: Mapping[str, Sequence[str]] | None,
                    barra_de_alimentador: Mapping[str, str] | None = None) -> tuple[Topologia, list[str]]:
    """La topología de F-102 desde el perfil del PIT y la red del área, sin suponer lo que no se declara.

    - ``sistemas`` (``pit.areas[].sistemas_electricos``: sistema → SET): sin él no hay F-102 por sistema, y es un error
      que lo nombra; nunca se supone que el área sea un solo sistema.
    - La barra de cada alimentador es la de ``barra_de_alimentador`` (``pit.areas[].barra_de_alimentador``) o, si la SET
      tiene una sola barra de carga en la red, esa.
    - El devanado de una barra es el lado (``lv`` o ``mv``) del transformador de la SET conectado a ella. Una barra sin
      devanado, o con varios en paralelo (el reparto entre ellos no se supone), deja a sus alimentadores en un hueco.
    """
    if not sistemas:
        raise PitError(f'{area.codigo}: el perfil no declara los sistemas eléctricos del área '
                       '(pit.areas[].sistemas_electricos); el F-102 por sistema no se supone')
    huecos: list[str] = []
    sets_declarados = {s for ss in sistemas.values() for s in ss}
    for s in area.set:
        if s not in sets_declarados:
            huecos.append(f'{s}: la SET no está en ningún sistema eléctrico del perfil')
    barras_carga: dict[str, list[str]] = {}
    for b in red.de_tipo('barra'):
        if b.get('rol') == 'carga' and b.get('set'):
            barras_carga.setdefault(str(b['set']), []).append(str(b['id']))
    lados: dict[str, list[str]] = {}
    for tipo, ls in (('trafo2', ('lv',)), ('trafo3', ('mv', 'lv'))):
        for t in red.de_tipo(tipo):
            for lado in ls:
                if t.get(lado):
                    lados.setdefault(str(t[lado]), []).append(f'{t["id"]}:{lado}')
    devanados: dict[str, list[str]] = {}
    sets: dict[str, list[str]] = {}
    for s in area.set:
        if s not in sets_declarados:
            continue
        for a in area.set_alimentadores.get(s, ()):
            barra = (barra_de_alimentador or {}).get(a)
            if barra is None:
                propias = barras_carga.get(s, [])
                if len(propias) != 1:
                    huecos.append(f'{a}: la SET {s} tiene {len(propias)} barras de carga y el perfil no dice a cuál va '
                                  '(pit.areas[].barra_de_alimentador)')
                    continue
                barra = propias[0]
            devs = lados.get(barra, [])
            if len(devs) != 1:
                huecos.append(f'{a}: la barra {barra} tiene {len(devs)} devanados'
                              + (' en paralelo; el reparto entre ellos no se supone' if devs else ''))
                continue
            devanados.setdefault(devs[0], []).append(a)
            if devs[0] not in sets.setdefault(s, []):
                sets[s].append(devs[0])
    topo = Topologia(sistemas={k: [s for s in v if s in sets] for k, v in sistemas.items()},
                     sets=sets, devanados=devanados)
    return topo, huecos


def curvas_de_la_medida(rutas: Sequence[Path | str], topologia: Topologia, *,
                        pares: Sequence[tuple[str, str]] | None = None,
                        centrales: Mapping[str, Mapping[str, str]] | None = None
                        ) -> tuple[dict[str, list[Punto]], dict[str, Any], list[str]]:
    """Las curvas medidas de los alimentadores de la topología, con su fuente, desde los libros de cabecera del
    perfil (``pronostico_demanda.curvas_de_cabecera``: medidores sumados y central descontada si se declara).

    ``pares`` son ``(alimentador, medidor)``; sin ellos, cada alimentador se busca por su propio código. Lo que la
    lectura aparta (un medidor sin curva, un libro roto, una central sin todos sus medidores) vuelve como hueco con su
    motivo, y el devanado de ese alimentador queda en hueco en ``curvas_por_devanado``: nunca se escala lo que sí hay.
    """
    from .. import pronostico_demanda

    alimentadores = list(dict.fromkeys(a for als in topologia.devanados.values() for a in als))
    pares = [p for p in (pares or [(a, a) for a in alimentadores]) if p[0] in alimentadores]
    leidas, apartados = pronostico_demanda.curvas_de_cabecera(rutas, pares, centrales=centrales)
    curvas = {a: list(info['curva']) for a, info in leidas.items()}
    fuentes = {a: info['fuente'] for a, info in leidas.items()}
    huecos = [f'{ap["objetivo"]}: {ap["motivo"]}' for ap in apartados]
    huecos += [f'cabecera:{a}: sin curva en los libros' for a in alimentadores
               if a not in curvas and not any(ap['objetivo'] == f'cabecera:{a}' for ap in apartados)]
    return curvas, fuentes, huecos


def demanda_regulatoria(registro: RegistroNormativo, area: AreaPit, red: RedArea,
                        sistemas: Mapping[str, Sequence[str]] | None, rutas: Sequence[Path | str], anio: int, *,
                        convencion: str | None, tolerancia_kw: float | None = None, clase: str | None = None,
                        barra_de_alimentador: Mapping[str, str] | None = None,
                        pares: Sequence[tuple[str, str]] | None = None,
                        centrales: Mapping[str, Mapping[str, str]] | None = None, intervalo_min: int = 15
                        ) -> dict[str, Any]:
    """F-101, F-102 y F-103 de un área y un año representativo, de punta a punta: perfil y red → topología; libros
    de cabecera → curvas; registro del COES y de la medida → instante del SEIN y tolerancia. Cada paso deja sus huecos
    con su causa en la salida; ninguno se rellena."""
    topologia, huecos_topologia = topologia_desde(area, red, sistemas, barra_de_alimentador)
    curvas, fuentes, huecos_medida = curvas_de_la_medida(rutas, topologia, pares=pares, centrales=centrales)
    devanados = curvas_por_devanado(curvas, topologia, anio, intervalo_min)
    sein = instante_sein(registro, anio)
    tolerancia = tolerancia_de(registro, tolerancia_kw=tolerancia_kw, clase=clase)
    return {
        'area': area.codigo, 'anio': anio,
        'huecos': {'topologia': huecos_topologia, 'medida': huecos_medida},
        'fuentes': fuentes, 'sein': {'instante': sein.instante, 'motivo': sein.motivo, 'traza': sein.traza,
                                     'avisos': sein.avisos},
        'tolerancia': {'origen': tolerancia.origen, **dict(tolerancia.traza)},
        'f102': datos_f102(devanados, topologia, sein, convencion=convencion, tolerancia=tolerancia,
                           intervalo_min=intervalo_min),
        'f101': datos_f101(devanados, topologia, sein, registro, convencion=convencion, tolerancia=tolerancia,
                           intervalo_min=intervalo_min),
        'f103': datos_f103(devanados, topologia, registro, intervalo_min),
    }


_MOMENTOS = ('sistema_electrico', 'set_maxima', 'sein', 'no_coincidente')


def barra_y_tension(red: RedArea, devanado: str) -> tuple[str | None, float | None, str | None]:
    """La barra del lado del transformador (``T:lv`` o ``T:mv``) y su tensión en la red del área, o el motivo."""
    trafo, _, lado = devanado.partition(':')
    t = next((e for tipo in ('trafo2', 'trafo3') for e in red.de_tipo(tipo) if str(e.get('id')) == trafo), None)
    if t is None or not t.get(lado):
        return None, None, f'la red del área no trae el transformador {trafo} con su lado {lado}'
    barra = str(t[lado])
    b = next((e for e in red.de_tipo('barra') if str(e.get('id')) == barra), None)
    if b is None or b.get('kv') in (None, ''):
        return barra, None, f'la barra {barra} no trae su tensión en la red del área'
    return barra, float(b['kv']), None


def filas_f102(f102: Mapping[str, Any], red: RedArea) -> list[dict[str, Any]]:
    """Las filas del bloque «devanados» de F-102 para el motor de plantillas, con el motivo de cada vacío."""
    filas = []
    for f in f102['filas']:
        barra, kv, motivo = barra_y_tension(red, f['devanado'])
        fila: dict[str, Any] = {'sistema': f['sistema'], 'set': f['set'], 'barra': barra, 'tension_kv': kv,
                                '_motivos': {}}
        if motivo:
            fila['_motivos'].update({'barra': motivo, 'tension_kv': motivo} if barra is None else {'tension_kv': motivo})
        for m in _MOMENTOS:
            mom = f[m]
            for campo in ('fecha', 'hora', 'kw', 'kvar'):
                fila[f'{m}_{campo}'] = mom.get(campo)
                if mom.get(campo) is None:
                    fila['_motivos'][f'{m}_{campo}'] = mom.get('motivo') or 'la medida no trae el kVAR'
        filas.append(fila)
    return filas


def filas_f103(f103: Mapping[str, Any], f102: Mapping[str, Any], red: RedArea) -> list[dict[str, Any]]:
    """Las filas del bloque «devanados» de F-103: la Pmax es la del F-102 en el día de máxima del sistema eléctrico
    (nota 1 del formato) y la energía, la del año representativo en MWh (nota 3)."""
    de102 = {f['devanado']: f for f in f102['filas']}
    filas = []
    for f in f103['filas']:
        base = de102.get(f['devanado'], {})
        barra, kv, motivo = barra_y_tension(red, f['devanado'])
        energia = ((f.get('traza') or {}).get('energia_kwh') or {}).get('devanado')
        pmax = (base.get('sistema_electrico') or {}).get('kw')
        fila = {'sistema': f.get('sistema') or base.get('sistema'), 'set': base.get('set'), 'barra': barra,
                'tension_kv': kv, 'pmax_sistema_kw': pmax, 'fphms': f.get('fphms'),
                'energia_mwh': None if energia is None else round(energia / 1000, 3), 'fpmwhs': f.get('fpmwhs'),
                '_motivos': {}}
        for campo in ('pmax_sistema_kw', 'fphms', 'energia_mwh', 'fpmwhs', 'set'):
            if fila[campo] is None:
                fila['_motivos'][campo] = f.get('motivo') or (base.get('sistema_electrico') or {}).get('motivo') \
                    or 'sin dato del F-102 para este devanado'
        if motivo:
            fila['_motivos']['tension_kv'] = motivo
        filas.append(fila)
    return filas


def celdas_f102_f103(registro: RegistroNormativo, salida: Mapping[str, Any], red: RedArea,
                     fuente: Mapping[str, str]) -> dict[str, Any]:
    """F-102 y F-103 llenados por el motor común de plantillas (``pit.plantillas``), desde la salida de
    ``demanda_regulatoria``; ``fuente`` lleva el ``nombre`` y la ``huella`` de lo medido."""
    from .plantillas import celdas_de_formato

    datos102 = {'fuente': fuente, 'cabecera': {}, 'bloques': {'devanados': filas_f102(salida['f102'], red)}}
    datos103 = {'fuente': fuente, 'cabecera': {},
                'bloques': {'devanados': filas_f103(salida['f103'], salida['f102'], red)}}
    return {'F-102': celdas_de_formato(registro, 'F-102', datos102),
            'F-103': celdas_de_formato(registro, 'F-103', datos103)}


def grupos_f101(f101: Mapping[str, Any], f102: Mapping[str, Any], red: RedArea) -> list[dict[str, Any]]:
    """Los miembros del grupo «sistemas» de F-101: por sistema eléctrico, una fila por devanado (SET, barra y tensión
    de la red, FC, FCP y FS) y, en el total, solo el FC del sistema (nota 2 del formato)."""
    por_nombre = {(f['nivel'], f['nombre']): f for f in f101['filas']}
    sistemas: dict[str, list[dict[str, Any]]] = {}
    for f in f102['filas']:
        sistemas.setdefault(f['sistema'], []).append(f)
    miembros = []
    for sis, filas102 in sistemas.items():
        filas = []
        for f in filas102:
            d = por_nombre.get(('devanado', f['devanado']), {})
            barra, kv, motivo = barra_y_tension(red, f['devanado'])
            fila = {'sistema': sis, 'set': f['set'], 'barra': barra, 'tension_kv': kv,
                    'fc': d.get('fc'), 'fcp': d.get('fcp'), 'fs': d.get('fs'), '_motivos': {}}
            for campo in ('fc', 'fcp'):
                if fila[campo] is None:
                    fila['_motivos'][campo] = d.get('motivo') or 'sin factores del devanado'
            if fila['fs'] is None:
                fila['_motivos']['fs'] = d.get('motivo_fs') or d.get('motivo') or 'sin el instante del SEIN'
            if motivo:
                fila['_motivos']['tension_kv'] = motivo
            filas.append(fila)
        s = por_nombre.get(('sistema', sis), {})
        total = {'fc': s.get('fc')}
        if s.get('fc') is None:
            total['_motivo:fc'] = s.get('motivo') or 'sin el FC del sistema'
        miembros.append({'nombre': sis, 'filas': filas, 'total': total})
    return miembros


def celdas_f101(registro: RegistroNormativo, salida: Mapping[str, Any], red: RedArea,
                fuente: Mapping[str, str]) -> dict[str, Any]:
    """F-101 llenado por el motor común, un bloque por sistema eléctrico, desde la salida de ``demanda_regulatoria``."""
    from .plantillas import celdas_de_formato

    datos = {'fuente': fuente, 'cabecera': {},
             'grupos': {'sistemas': grupos_f101(salida['f101'], salida['f102'], red)}}
    return celdas_de_formato(registro, 'F-101', datos)
