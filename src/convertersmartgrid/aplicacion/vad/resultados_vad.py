"""Cargo fijo, VAD por nivel de tensión, factor de economía de escala y reajuste (108:RF-16, RF-9, RF-13).

Todo sale del registro normativo (``config/vad/``), nunca del código:

* ``vad.conceptos.<ámbito>``: qué conceptos se calculan en cada ámbito (en el TdR 2026: LCE y LGER).
* ``vad.variantes.<concepto>``: si un concepto tiene variantes (en el TdR 2026, las ``_SER`` según quién es dueño de
  la inversión). El estudio declara la variante de cada sistema; sin declararla, el concepto es un hueco.
* ``vad.formula.<concepto>`` o ``vad.formula.<concepto>.<variante>``: la fórmula, evaluada por :mod:`.formulas`.
* ``vad.ponderacion``: con qué variable se pondera cada concepto a nivel empresa.
* ``vad.formula.FEE``, ``vad.reajuste.factores`` y ``vad.reajuste.parametros``; ``vad.formula.reajuste`` si el
  registro la trae (el TdR 2026 no la da en forma cerrada: la propone la empresa).

Cada valor lleva la regla que lo dio, su norma, si obliga y su huella (108:RF-9). Una variable que falta, una división
entre cero o una regla que no está son **huecos nombrados**, nunca 0. Una regla que no obliga (norma no comprobada o
sin cita) deja el resultado ``no_conforme`` (108:RF-10).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ...dominio.registro_normativo import RegistroError, RegistroNormativo, ReglaVigente
from . import VadError
from .formulas import FormulaError, evaluar

ESTADOS = ('conforme', 'incompleto', 'no_conforme')
#: Tolerancia de una suma de proporciones que por definición vale 1 (no es una cifra de la norma).
TOLERANCIA_PROPORCION = 1e-9


@dataclass(frozen=True)
class ValorVad:
    concepto: str
    valor: float | None
    moneda: str = ''
    unidad: str = ''
    variante: str = ''
    #: Regla del registro que dio el valor (o la que faltó) y su norma.
    regla: str = ''
    acto: str = ''
    obligatoria: bool = False
    huella: str = ''
    #: Por qué el valor es un hueco; vacío si hay valor.
    motivo: str = ''

    @property
    def hueco(self) -> bool:
        return self.valor is None


@dataclass(frozen=True)
class DatosSistema:
    """Lo que el estudio entrega de un sistema eléctrico para el cálculo del VAD."""

    sistema: str
    ambito: str
    moneda: str
    #: Variable de las fórmulas → valor (anualidades, COyM, demandas, clientes, FFR…).
    valores: Mapping[str, float] = field(default_factory=dict)
    #: Concepto → variante declarada para este sistema (por ejemplo, la propiedad de la inversión).
    variantes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for campo in ('sistema', 'ambito', 'moneda'):
            if not str(getattr(self, campo) or '').strip():
                raise VadError(f'los datos del sistema necesitan «{campo}»: {self!r}')


@dataclass(frozen=True)
class ResultadoSistema:
    sistema: str
    ambito: str
    valores: tuple[ValorVad, ...]

    def valor(self, concepto: str) -> ValorVad:
        for v in self.valores:
            if v.concepto == concepto:
                return v
        raise VadError(f'el sistema {self.sistema} no tiene el concepto {concepto}')


@dataclass(frozen=True)
class ResultadoVad:
    sistemas: tuple[ResultadoSistema, ...]
    empresa: tuple[ValorVad, ...]
    estado: str
    motivos: tuple[str, ...] = ()


def _regla(registro: RegistroNormativo, clave: str, fecha: str | None) -> ReglaVigente | None:
    try:
        return registro.regla(clave, fecha)
    except RegistroError:
        return None


def _lista_de_textos(rv: ReglaVigente, clave: str) -> list[str]:
    valor = rv.regla.valor
    if not isinstance(valor, list) or not valor or not all(isinstance(x, str) and x.strip() for x in valor):
        raise VadError(f'la regla {clave} del registro tiene que ser una lista de nombres, no {valor!r}')
    if len(set(valor)) != len(valor):
        raise VadError(f'la regla {clave} del registro repite nombres: {valor!r}')
    return list(valor)


def ambitos(registro: RegistroNormativo) -> list[str]:
    """Los ámbitos que el registro define (``vad.conceptos.<ámbito>``)."""
    return sorted({r.clave.removeprefix('vad.conceptos.') for n in registro.normas.values() for r in n.reglas
                   if r.clave.startswith('vad.conceptos.')})


def conceptos(registro: RegistroNormativo, ambito: str, fecha: str | None = None) -> list[str]:
    rv = _regla(registro, f'vad.conceptos.{ambito}', fecha)
    if rv is None:
        raise VadError(f'el registro no define el ámbito {ambito!r}; los que define son: '
                       f'{", ".join(ambitos(registro)) or "ninguno"}')
    return _lista_de_textos(rv, f'vad.conceptos.{ambito}')


def _desde_regla(concepto: str, rv: ReglaVigente, valor: float | None, *, moneda: str = '', variante: str = '',
                 motivo: str = '') -> ValorVad:
    return ValorVad(concepto=concepto, valor=valor, moneda=moneda, unidad=rv.regla.unidad, variante=variante,
                    regla=rv.regla.clave, acto=rv.norma.acto, obligatoria=rv.obligatoria, huella=rv.huella(),
                    motivo=motivo)


def _formula(registro: RegistroNormativo, concepto: str, valores: Mapping[str, Any], clave: str,
             fecha: str | None, *, moneda: str = '', variante: str = '') -> ValorVad:
    rv = _regla(registro, clave, fecha)
    if rv is None:
        return ValorVad(concepto=concepto, valor=None, moneda=moneda, variante=variante, regla=clave,
                        motivo=f'la regla {clave} no está en el registro normativo')
    try:
        return _desde_regla(concepto, rv, evaluar(rv.regla.valor, valores), moneda=moneda, variante=variante)
    except FormulaError as exc:
        return _desde_regla(concepto, rv, None, moneda=moneda, variante=variante, motivo=str(exc))


def calcular_sistema(registro: RegistroNormativo, datos: DatosSistema, fecha: str | None = None) -> ResultadoSistema:
    """Cada concepto del ámbito del sistema, con su variante y la regla que lo dio."""
    lista = conceptos(registro, datos.ambito, fecha)
    sobrantes = sorted(set(datos.variantes) - set(lista))
    if sobrantes:
        raise VadError(f'el sistema {datos.sistema} declara variantes de conceptos que su ámbito {datos.ambito} no '
                       f'tiene: {", ".join(sobrantes)}')
    out: list[ValorVad] = []
    for concepto in lista:
        clave_variantes = f'vad.variantes.{concepto}'
        rv_var = _regla(registro, clave_variantes, fecha)
        declarada = str(datos.variantes.get(concepto) or '').strip()
        if rv_var is None:
            if declarada:
                raise VadError(f'el sistema {datos.sistema} declara la variante {declarada!r} de {concepto}, que '
                               'el registro no tiene')
            out.append(_formula(registro, concepto, datos.valores, f'vad.formula.{concepto}', fecha,
                                moneda=datos.moneda))
            continue
        opciones = _lista_de_textos(rv_var, clave_variantes)
        if not declarada:
            out.append(_desde_regla(concepto, rv_var, None, moneda=datos.moneda,
                                    motivo=f'el sistema {datos.sistema} no declara la variante de {concepto} '
                                           f'(el registro admite: {", ".join(opciones)})'))
            continue
        if declarada not in opciones:
            raise VadError(f'la variante {declarada!r} de {concepto} del sistema {datos.sistema} no está en el '
                           f'registro (admite: {", ".join(opciones)})')
        out.append(_formula(registro, concepto, datos.valores, f'vad.formula.{concepto}.{declarada}', fecha,
                            moneda=datos.moneda, variante=declarada))
    return ResultadoSistema(datos.sistema, datos.ambito, tuple(out))


def _ponderar(registro: RegistroNormativo, concepto: str, por_sistema: Sequence[tuple[DatosSistema, ValorVad]],
              fecha: str | None) -> ValorVad:
    rv = _regla(registro, 'vad.ponderacion', fecha)
    if rv is None:
        return ValorVad(concepto=concepto, valor=None, regla='vad.ponderacion',
                        motivo='la regla vad.ponderacion no está en el registro normativo')
    pesos = rv.regla.valor if isinstance(rv.regla.valor, Mapping) else {}
    variable = pesos.get(concepto)
    if not isinstance(variable, str) or not variable:
        return _desde_regla(concepto, rv, None, motivo=f'el registro no dice con qué se pondera {concepto}')
    monedas = sorted({v.moneda for _, v in por_sistema})
    if len(monedas) != 1:
        return _desde_regla(concepto, rv, None, motivo=f'{concepto} sale en varias monedas ({", ".join(monedas)}): '
                                                       'no se ponderan juntas')
    huecos = [d.sistema for d, v in por_sistema if v.hueco]
    if huecos:
        return _desde_regla(concepto, rv, None, moneda=monedas[0],
                            motivo=f'{concepto} es un hueco en: {", ".join(huecos)}')
    sin_peso = [d.sistema for d, _ in por_sistema
                if not isinstance(d.valores.get(variable), (int, float)) or isinstance(d.valores.get(variable), bool)
                or not math.isfinite(d.valores[variable]) or d.valores[variable] < 0]
    if sin_peso:
        return _desde_regla(concepto, rv, None, moneda=monedas[0],
                            motivo=f'falta el peso {variable} (o no es un número no negativo) en: {", ".join(sin_peso)}')
    total = math.fsum(d.valores[variable] for d, _ in por_sistema)
    if total <= 0:
        return _desde_regla(concepto, rv, None, moneda=monedas[0], motivo=f'la suma de {variable} es 0')
    valor = math.fsum(v.valor * d.valores[variable] for d, v in por_sistema) / total  # type: ignore[operator]
    return _desde_regla(concepto, rv, valor, moneda=monedas[0])


def _estado(valores: Iterable[ValorVad]) -> tuple[str, tuple[str, ...]]:
    motivos: list[str] = []
    no_obliga = False
    for v in valores:
        if v.regla and v.acto and not v.obligatoria:
            no_obliga = True
            motivos.append(f'{v.concepto}: la regla {v.regla} de {v.acto} no obliga (norma no comprobada o sin cita)')
        if v.hueco:
            motivos.append(f'{v.concepto}{f" ({v.variante})" if v.variante else ""}: {v.motivo}')
    estado = 'no_conforme' if no_obliga else ('incompleto' if motivos else 'conforme')
    return estado, tuple(dict.fromkeys(motivos))


def calcular_vad(registro: RegistroNormativo, sistemas: Sequence[DatosSistema],
                 fecha: str | None = None) -> ResultadoVad:
    """Por sistema y ponderado a nivel empresa; el estado dice si se puede emitir."""
    if not sistemas:
        raise VadError('no hay ningún sistema eléctrico que calcular')
    nombres = [d.sistema for d in sistemas]
    repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
    if repetidos:
        raise VadError(f'sistemas repetidos: {", ".join(repetidos)}')
    resultados = tuple(calcular_sistema(registro, d, fecha) for d in sistemas)
    orden: list[str] = []
    for r in resultados:
        orden.extend(v.concepto for v in r.valores if v.concepto not in orden)
    empresa = tuple(_ponderar(registro, c, [(d, r.valor(c)) for d, r in zip(sistemas, resultados)
                                            if any(v.concepto == c for v in r.valores)], fecha) for c in orden)
    estado, motivos = _estado([v for r in resultados for v in r.valores] + list(empresa))
    return ResultadoVad(resultados, empresa, estado, motivos)


def _proporcion(nombre: str, valor: Any) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor) \
            or not 0 <= valor <= 1:
        raise VadError(f'{nombre} tiene que ser una proporción entre 0 y 1, no {valor!r}')
    return float(valor)


def calcular_fee(registro: RegistroNormativo, concepto: str, *, proporcion_fija: float, proporcion_variable: float,
                 crecimiento: float, fecha: str | None = None) -> ValorVad:
    """El FEE de un concepto con la fórmula registrada (``vad.formula.FEE``: variables Pfc, Pvc y tc)."""
    pfc = _proporcion('la proporción fija', proporcion_fija)
    pvc = _proporcion('la proporción variable', proporcion_variable)
    if abs(pfc + pvc - 1) > TOLERANCIA_PROPORCION:
        raise VadError(f'las proporciones fija y variable de {concepto} suman {pfc + pvc}, no 1')
    if isinstance(crecimiento, bool) or not isinstance(crecimiento, (int, float)) or not math.isfinite(crecimiento) \
            or crecimiento <= -1:
        raise VadError(f'la tasa de crecimiento de {concepto} tiene que ser un número mayor que -1, no {crecimiento!r}')
    return _formula(registro, f'FEE.{concepto}', {'Pfc': pfc, 'Pvc': pvc, 'tc': float(crecimiento)},
                    'vad.formula.FEE', fecha)


@dataclass(frozen=True)
class Reajuste:
    #: Factor (FAVADMT…) → valor del factor, o hueco con su motivo.
    factores: tuple[ValorVad, ...]
    #: Factor → parámetro → incidencia validada (suman 1).
    incidencias: Mapping[str, Mapping[str, float]]


def factores_reajuste(registro: RegistroNormativo, ambito: str, incidencias: Mapping[str, Mapping[str, float]], *,
                      indices: Mapping[str, tuple[float, float]] | None = None,
                      fecha: str | None = None) -> Reajuste:
    """La estructura de incidencias de cada factor de reajuste del ámbito y, si el registro trae la fórmula
    (``vad.formula.reajuste``, con las series ``a``, ``I`` e ``I0`` en el orden de los parámetros registrados), su
    valor con los índices ``(base, actual)`` de cada parámetro."""
    rv_f = _regla(registro, 'vad.reajuste.factores', fecha)
    rv_p = _regla(registro, 'vad.reajuste.parametros', fecha)
    if rv_f is None or rv_p is None:
        raise VadError('el registro no trae vad.reajuste.factores y vad.reajuste.parametros')
    por_ambito = rv_f.regla.valor if isinstance(rv_f.regla.valor, Mapping) else {}
    if ambito not in por_ambito:
        raise VadError(f'el registro no define factores de reajuste del ámbito {ambito!r} '
                       f'(define: {", ".join(sorted(por_ambito)) or "ninguno"})')
    factores = list(por_ambito[ambito])
    parametros = _lista_de_textos(rv_p, 'vad.reajuste.parametros')
    sobrantes = sorted(set(incidencias) - set(factores))
    if sobrantes:
        raise VadError(f'incidencias de factores que el ámbito {ambito} no tiene: {", ".join(sobrantes)}')
    validadas: dict[str, dict[str, float]] = {}
    for factor in factores:
        if factor not in incidencias:
            continue
        inc = incidencias[factor]
        extra = sorted(set(inc) - set(parametros))
        falta = sorted(set(parametros) - set(inc))
        if extra or falta:
            raise VadError(f'las incidencias de {factor} no coinciden con los parámetros registrados '
                           f'(sobran: {", ".join(extra) or "—"}; faltan: {", ".join(falta) or "—"})')
        valores = {p: _proporcion(f'la incidencia de {p} en {factor}', inc[p]) for p in parametros}
        if abs(math.fsum(valores.values()) - 1) > TOLERANCIA_PROPORCION:
            raise VadError(f'las incidencias de {factor} suman {math.fsum(valores.values())}, no 1')
        validadas[factor] = valores
    rv_formula = _regla(registro, 'vad.formula.reajuste', fecha)
    out: list[ValorVad] = []
    for factor in factores:
        if factor not in validadas:
            out.append(_desde_regla(factor, rv_f, None, motivo=f'el estudio no da las incidencias de {factor}'))
        elif rv_formula is None:
            out.append(_desde_regla(factor, rv_f, None, motivo=(
                f'el TdR registrado no da la fórmula de reajuste en forma cerrada ({rv_f.norma.acto}, líneas '
                f'{rv_f.regla.lineas}): queda la estructura de incidencias, y la fórmula la propone la empresa')))
        elif not indices or sorted(set(parametros) - set(indices)):
            out.append(_desde_regla(factor, rv_formula, None,
                                    motivo=f'faltan los índices (base, actual) de: '
                                           f'{", ".join(sorted(set(parametros) - set(indices or {})))}'))
        else:
            series = {'a': [validadas[factor][p] for p in parametros], 'I0': [indices[p][0] for p in parametros],
                      'I': [indices[p][1] for p in parametros]}
            out.append(_formula(registro, factor, series, 'vad.formula.reajuste', fecha))
    return Reajuste(tuple(out), validadas)
