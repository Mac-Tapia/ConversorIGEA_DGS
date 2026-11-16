"""Balance de potencia y energía (num. 6.10, Cuadro N° 20 = formato A-VI) y pérdidas estándar (num. 6.9) del VAD
(spec 108, RF-8, RF-9, RF-13).

Las filas derivadas salen de las fórmulas del formato A-VI transcrito (``config/vad/anexo2_formatos.json``) y se
evalúan con el intérprete cerrado de :mod:`.formulas`; ninguna fórmula ni ningún coeficiente está escrito aquí.

- :func:`balance_real`: el balance de la red real por sistema y en total. Cierra por dentro cuando las pérdidas no
  estándar (47) son cero (las no técnicas reales son «totales − técnicas», ``vad.perdidas_no_tecnicas.reales``), y por
  fuera cuando la potencia resultante coincide con la máxima simultánea medida (``vad.balance.cierre_red_real``). El TdR
  dice «coincidirá» sin cifra: la tolerancia por defecto es el error admisible de la CLASE DEL MEDIDOR
  (``medida.error_admisible_por_clase``, RM 496-2005-MEM/DM, Tabla N° 01), con la clase del perfil o, sin ella, la
  clase por defecto en MT marcada como tal; el perfil la puede sustituir con su sustento (decisión de 28). La
  diferencia se muestra siempre.
- :func:`balance_adaptado`: «solo se modificarán los valores de pérdidas» (``vad.balance.adaptado``): cualquier otra
  fila distinta se rechaza. Da las pérdidas no estándar (47), los porcentajes con los decimales del registro
  (``vad.perdidas_estandar.expresion``) y la demanda máxima de MT y de BT (``vad.balance.demanda_maxima_mt_bt``).
- :func:`factores_incremento`: los factores facultativos del 6.9 con sus topes, que se validan siempre; la forma de
  combinarlos la declara el perfil, y sin ella es un hueco (decisión P-6); se muestran la suma y el producto.

La potencia resultante de un sistema es lo que entra en él según el A-VI, con los términos y signos de la regla
``vad.balance.potencia_resultante`` (decisión de c3; cada fila con su cita literal del formato): hoy (1) Ingreso a MAT +
(5) Compras en AT + (12) Compras en MT + (13) Generación Propia Neta − (14) Consumo Propio. Las filas de la regla tienen
que ser las del formato con su nombre; si no, el resultado no es conforme. El total de la empresa suma sus sistemas; en potencia, la suma
solo es coincidente si los datos son de la hora de punta de la empresa, y se avisa.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..registro_normativo import RegistroError, RegistroNormativo, ReglaVigente
from . import VadError
from .anexo2 import Formato, cargar_formatos
from .formulas import FormulaError, evaluar

FORMATO = 'A-VI'
MAGNITUDES = ('energia_mwh', 'potencia_kw')
REGLAS = ('vad.balance.cuadro20', 'vad.balance.cierre_red_real', 'vad.balance.adaptado',
          'vad.balance.demanda_maxima_mt_bt', 'vad.perdidas_estandar.expresion', 'vad.perdidas_no_tecnicas.reales',
          'vad.balance.potencia_resultante')
REGLA_INCREMENTO = 'vad.perdidas_estandar.factores_incremento'
REGLA_CLASE = 'medida.error_admisible_por_clase'
REGLA_CLASE_DEFECTO = 'medida.clase_por_defecto_mt'
#: Filas de pérdidas del A-VI: las únicas que cambian en el balance adaptado (técnicas y no técnicas de MT y de BT).
FILAS_PERDIDAS = ('(18)', '(19)', '(29)', '(30)')
REGLA_RESULTANTE = 'vad.balance.potencia_resultante'
FACTORES = {'divergencia': 'divergencia_cargas_max', 'asimetria': 'asimetria_fases_max'}
COMBINACIONES = ('suma', 'producto')
_FILA = re.compile(r'\((\d+)\)')


def _cita(v: ReglaVigente) -> str:
    return (f'{v.norma.acto}, {v.regla.articulo_o_anexo}, pág. {v.regla.pagina}, líneas {v.regla.lineas}: '
            f'«{v.regla.cita_literal}»')


def formato_vi(ruta: Path | str) -> Formato:
    return cargar_formatos(ruta).formato(FORMATO)


# --------------------------------------------------------------------------------------------- tolerancia
@dataclass(frozen=True)
class Tolerancia:
    relativa: float
    origen: str
    traza: Mapping[str, Any] = field(default_factory=dict)


def tolerancia_cierre(registro: RegistroNormativo, *, clase: str | None = None, relativa: float | None = None,
                      sustento: str = '', fecha: str | None = None) -> Tolerancia:
    """La tolerancia del «coincidirá»: la del perfil con su sustento, o el error admisible de la clase del medidor."""
    if relativa is not None:
        if not sustento.strip():
            raise VadError('la tolerancia del cierre que declara el perfil necesita su sustento')
        return Tolerancia(float(relativa), f'tolerancia declarada por el perfil: {sustento}', {'perfil': sustento})
    try:
        tabla = registro.regla(REGLA_CLASE, fecha)
    except RegistroError as exc:
        raise VadError(f'sin tolerancia del perfil hace falta el error admisible por clase ({REGLA_CLASE}): {exc}') \
            from exc
    traza: dict[str, Any] = {'regla': REGLA_CLASE, 'acto': tabla.norma.acto, 'huella': tabla.huella(),
                             'estado': tabla.estado}
    marca = ''
    if clase is None:
        try:
            defecto = registro.regla(REGLA_CLASE_DEFECTO, fecha)
        except RegistroError as exc:
            raise VadError(f'el perfil no declara la clase del medidor y el registro no trae la clase por defecto '
                           f'({exc})') from exc
        clase, marca = str(defecto.regla.valor), ' (clase por defecto en MT, el perfil no la declara)'
        traza['clase_por_defecto'] = {'regla': REGLA_CLASE_DEFECTO, 'acto': defecto.norma.acto}
    if clase not in tabla.regla.valor:
        raise VadError(f'la clase {clase!r} del medidor no está en la tabla del error admisible '
                       f'({", ".join(tabla.regla.valor)})')
    traza['clase'] = clase
    return Tolerancia(float(tabla.regla.valor[clase]) / 100.0,
                      f'tolerancia por defecto: error admisible de la clase {clase}{marca} ({tabla.norma.acto}, '
                      f'{tabla.regla.articulo_o_anexo})', traza)


# -------------------------------------------------------------------------------------------- filas del A-VI
def _ident(fila: str) -> str:
    return 'f' + fila.strip('()')


def calcular_filas(entrada: Mapping[str, float], formato: Formato) -> tuple[dict[str, float], list[str]]:
    """Las filas del A-VI: las de dato, de ``entrada``; las derivadas, con sus fórmulas (en el orden que haga falta).
    Devuelve (filas, huecos): una fila de dato obligatoria que falta es un hueco y sus derivadas no se calculan."""
    valores: dict[str, float] = {}
    huecos: list[str] = []
    formulas: dict[str, str] = {}
    for c in formato.filas:
        if c.formula:
            izq, _, der = c.formula.partition('=')
            if izq.strip() != c.id:
                raise VadError(f'{formato.id}: la fórmula de {c.id} no la define: {c.formula!r}')
            formulas[c.id] = _FILA.sub(lambda m: 'f' + m.group(1), der).strip()
        elif c.id in entrada and entrada[c.id] is not None:
            valores[c.id] = float(entrada[c.id])
        elif c.obligatoria:
            huecos.append(f'falta la fila {c.id} «{c.nombre}»')
    sobran = sorted(set(entrada) - {c.id for c in formato.filas})
    if sobran:
        raise VadError(f'{formato.id}: filas que el formato no tiene: {sobran}')
    pendientes = dict(formulas)
    while pendientes:
        avance = False
        for fila, expr in list(pendientes.items()):
            try:
                valores[fila] = evaluar(expr, {_ident(k): v for k, v in valores.items()})
            except FormulaError:
                continue
            del pendientes[fila]
            avance = True
        if not avance:
            break
    for fila in sorted(pendientes):
        huecos.append(f'la fila {fila} no se calcula: le faltan filas de entrada')
    return valores, huecos


# ------------------------------------------------------------------------------------------------- balance
@dataclass
class BalanceSistema:
    filas: dict[str, dict[str, float]] = field(default_factory=dict)
    """magnitud → fila → valor."""
    porcentajes: dict[str, dict[str, float]] = field(default_factory=dict)
    """magnitud → «MT», «BT», «total» → % con los decimales del registro."""
    cierre_interno: dict[str, dict[str, Any]] = field(default_factory=dict)
    cierre_medida: dict[str, Any] = field(default_factory=dict)
    demanda_maxima: dict[str, float] = field(default_factory=dict)
    huecos: list[str] = field(default_factory=list)


@dataclass
class ResultadoBalance:
    tipo: str
    sistemas: dict[str, BalanceSistema] = field(default_factory=dict)
    total: BalanceSistema | None = None
    tolerancia: Tolerancia | None = None
    avisos: list[str] = field(default_factory=list)
    huecos: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)
    reglas: dict[str, str] = field(default_factory=dict)

    @property
    def conforme(self) -> bool:
        return not self.motivos

    @property
    def cierra(self) -> bool:
        """Todo sistema calculado cierra por dentro y, si hay medida, por fuera."""
        if not self.sistemas:
            return False
        for b in self.sistemas.values():
            if b.huecos or not b.cierre_interno:
                return False
            if not all(c['cierra'] for c in b.cierre_interno.values()):
                return False
            if b.cierre_medida and not b.cierre_medida['cierra']:
                return False
        return True


def _reglas(registro: RegistroNormativo, res: ResultadoBalance, fecha: str | None) -> dict[str, ReglaVigente]:
    out = {}
    for clave in REGLAS:
        try:
            v = registro.regla(clave, fecha)
        except RegistroError as exc:
            res.motivos.append(f'falta la regla {clave} del registro: {exc}')
            continue
        res.reglas[clave] = v.huella()
        if not v.obligatoria:
            res.motivos.append(f'la regla {clave} no obliga (estado «{v.estado}» o sin cita): no es conforme')
        out[clave] = v
    return out


def _cotejo_cuadro20(reglas: Mapping[str, ReglaVigente], formato: Formato, res: ResultadoBalance) -> None:
    v = reglas.get('vad.balance.cuadro20')
    if v is None:
        return
    filas = list(v.regla.valor['filas'])
    nombres = [c.nombre for c in formato.filas]
    if filas != nombres:
        res.motivos.append(f'el Cuadro N° 20 del registro ({len(filas)} filas) y el formato A-VI ({len(nombres)}) '
                           'no coinciden fila a fila')


def terminos_resultante(reglas: Mapping[str, ReglaVigente], formato: Formato,
                        res: ResultadoBalance) -> tuple[tuple[str, float], ...]:
    """(fila, signo) de la potencia resultante, de ``vad.balance.potencia_resultante``; cada fila tiene que ser del
    formato y con el mismo nombre. Si no, el resultado no es conforme y no hay términos."""
    v = reglas.get(REGLA_RESULTANTE)
    if v is None:
        return ()
    nombres = {c.id: ' '.join(c.nombre.split()) for c in formato.filas}
    out = []
    for t in v.regla.valor['terminos']:
        if nombres.get(t['fila']) != ' '.join(str(t['nombre']).split()):
            res.motivos.append(f'{REGLA_RESULTANTE}: la fila {t["fila"]} «{t["nombre"]}» no es la del formato '
                               f'{formato.id} ({nombres.get(t["fila"])!r})')
            return ()
        out.append((t['fila'], float(t['signo'])))
    return tuple(out)


def _porcentajes(f: Mapping[str, float], decimales: int) -> dict[str, float]:
    out = {}
    if f.get('(16)'):
        out['MT'] = round(f['(17)'] / f['(16)'] * 100.0, decimales)
        out['total'] = round((f['(17)'] + f['(28)']) / f['(16)'] * 100.0, decimales)
    if f.get('(27)'):
        out['BT'] = round(f['(28)'] / f['(27)'] * 100.0, decimales)
    return out


def _sistema(entrada: Mapping[str, Mapping[str, float]], formato: Formato, tol: Tolerancia,
             decimales: int) -> BalanceSistema:
    b = BalanceSistema()
    for magnitud in MAGNITUDES:
        if magnitud not in entrada:
            b.huecos.append(f'falta la magnitud {magnitud}')
            continue
        filas, huecos = calcular_filas(entrada[magnitud], formato)
        b.huecos.extend(f'{magnitud}: {h}' for h in huecos)
        b.filas[magnitud] = filas
        if huecos:
            continue
        b.porcentajes[magnitud] = _porcentajes(filas, decimales)
        dif = filas['(47)']
        b.cierre_interno[magnitud] = {'diferencia': dif, 'relativa': dif / filas['(16)'] if filas['(16)'] else None,
                                      'cierra': bool(filas['(16)']) and abs(dif) <= tol.relativa * abs(filas['(16)'])}
    return b


def _total(sistemas: Mapping[str, BalanceSistema]) -> BalanceSistema:
    t = BalanceSistema()
    for magnitud in MAGNITUDES:
        suma: dict[str, float] = {}
        for b in sistemas.values():
            for k, v in b.filas.get(magnitud, {}).items():
                if k != '(48)':
                    suma[k] = suma.get(k, 0.0) + v
        if suma.get('(16)'):
            suma['(48)'] = (suma['(47)'] + suma['(17)'] + suma['(28)']) / suma['(16)']
        t.filas[magnitud] = suma
    return t


def balance_real(sistemas: Mapping[str, Mapping[str, Mapping[str, float]]], registro: RegistroNormativo,
                 formato: Formato, *, maximas_medidas: Mapping[str, float] | None = None,
                 tolerancia: Tolerancia | None = None, fecha: str | None = None) -> ResultadoBalance:
    """``sistemas``: sistema → magnitud (``energia_mwh``, ``potencia_kw``) → filas de dato del A-VI.
    ``maximas_medidas``: sistema (o «total») → potencia máxima simultánea medida, en kW."""
    res = ResultadoBalance('real')
    reglas = _reglas(registro, res, fecha)
    _cotejo_cuadro20(reglas, formato, res)
    tol = tolerancia or tolerancia_cierre(registro, fecha=fecha)
    res.tolerancia = tol
    res.avisos.append(tol.origen)
    if tol.traza.get('estado') and tol.traza['estado'] != 'vigente_comprobada':
        res.avisos.append(f'la tabla del error admisible ({tol.traza["acto"]}) está «{tol.traza["estado"]}»: se usa '
                          'como práctica decidida, no como norma que obligue')
    decimales = int(reglas['vad.perdidas_estandar.expresion'].regla.valor['decimales']) \
        if 'vad.perdidas_estandar.expresion' in reglas else 2
    medidas = dict(maximas_medidas or {})
    terminos = terminos_resultante(reglas, formato, res)
    if REGLA_RESULTANTE in reglas:
        res.avisos.append('potencia resultante = ' + ' '.join(f'{"+" if s > 0 else "−"} {f}' for f, s in terminos)
                          + f' del A-VI ({reglas[REGLA_RESULTANTE].regla.pagina}, líneas '
                          f'{reglas[REGLA_RESULTANTE].regla.lineas})')
    for nombre in sorted(sistemas):
        b = _sistema(sistemas[nombre], formato, tol, decimales)
        res.sistemas[nombre] = b
        res.huecos.extend(f'{nombre}: {h}' for h in b.huecos)
        if nombre in medidas and 'potencia_kw' in b.filas and not b.huecos and terminos:
            b.cierre_medida = _contra_medida(b.filas['potencia_kw'], float(medidas[nombre]), tol, terminos)
        elif nombre in medidas and not terminos:
            res.huecos.append(f'{nombre}: sin los términos citados de la potencia resultante ({REGLA_RESULTANTE}) no se '
                              'compara con la medida')
        elif nombre not in medidas:
            res.huecos.append(f'{nombre}: sin la potencia máxima simultánea medida no se comprueba el «coincidirá»')
    if res.sistemas:
        res.total = _total(res.sistemas)
        res.avisos.append('total de la empresa: suma de sus sistemas; en potencia es coincidente solo si los datos '
                          'son de la hora de punta de la empresa')
        if 'total' in medidas and res.total.filas.get('potencia_kw') and terminos:
            res.total.cierre_medida = _contra_medida(res.total.filas['potencia_kw'], float(medidas['total']), tol,
                                                     terminos)
    return res


def _contra_medida(filas: Mapping[str, float], medida: float, tol: Tolerancia,
                   terminos: tuple[tuple[str, float], ...]) -> dict[str, Any]:
    resultante = sum(signo * filas.get(fila, 0.0) for fila, signo in terminos)
    dif = resultante - medida
    return {'resultante_kw': resultante, 'medida_kw': medida, 'diferencia_kw': dif,
            'relativa': dif / medida if medida else None,
            'cierra': bool(medida) and abs(dif) <= tol.relativa * abs(medida), 'tolerancia': tol.origen}


def balance_adaptado(real: Mapping[str, Mapping[str, Mapping[str, float]]],
                     estandar: Mapping[str, Mapping[str, Mapping[str, float]]], registro: RegistroNormativo,
                     formato: Formato, *, fecha: str | None = None) -> ResultadoBalance:
    """El adaptado parte del real (las mismas filas de dato) y cambia SOLO las pérdidas (``FILAS_PERDIDAS``) por las
    estándar de ``estandar`` (sistema → magnitud → fila → valor). Las pérdidas no estándar (47) quedan a la vista."""
    res = ResultadoBalance('adaptado')
    reglas = _reglas(registro, res, fecha)
    _cotejo_cuadro20(reglas, formato, res)
    decimales = int(reglas['vad.perdidas_estandar.expresion'].regla.valor['decimales']) \
        if 'vad.perdidas_estandar.expresion' in reglas else 2
    cita = _cita(reglas['vad.balance.adaptado']) if 'vad.balance.adaptado' in reglas else 'vad.balance.adaptado'
    tol = Tolerancia(0.0, 'el balance adaptado no se cierra contra una medida: (47) son las pérdidas no estándar')
    for nombre in sorted(real):
        datos: dict[str, dict[str, float]] = {}
        for magnitud, filas in real[nombre].items():
            nuevas = dict(filas)
            cambio = estandar.get(nombre, {}).get(magnitud, {})
            otras = sorted(set(cambio) - set(FILAS_PERDIDAS))
            if otras:
                raise VadError(f'{nombre} {magnitud}: el balance adaptado solo cambia las pérdidas y se piden cambiar '
                               f'{otras} ({cita})')
            faltan = sorted(set(FILAS_PERDIDAS) - set(cambio))
            if faltan:
                res.huecos.append(f'{nombre} {magnitud}: sin las pérdidas estándar {faltan}; se queda la real')
            nuevas.update(cambio)
            datos[magnitud] = nuevas
        b = _sistema(datos, formato, tol, decimales)
        b.cierre_interno = {}
        for magnitud, filas in b.filas.items():
            if '(47)' in filas:
                b.cierre_interno[magnitud] = {'perdidas_no_estandar': filas['(47)'], 'cierra': True}
        pot = b.filas.get('potencia_kw', {})
        if '(16)' in pot and '(27)' in pot:
            b.demanda_maxima = {'MT': pot['(16)'], 'BT': pot['(27)']}
        res.sistemas[nombre] = b
        res.huecos.extend(f'{nombre}: {h}' for h in b.huecos)
    if res.sistemas:
        res.total = _total(res.sistemas)
    return res


# -------------------------------------------------------------------------------------- factores de incremento
@dataclass(frozen=True)
class Factor:
    valor: float
    sustento: str
    medicion: str = ''


@dataclass
class Incremento:
    suma: float
    producto: float
    aplicado: float | None
    combinacion: str | None
    avisos: list[str] = field(default_factory=list)
    huecos: list[str] = field(default_factory=list)
    reglas: dict[str, str] = field(default_factory=dict)


def factores_incremento(perdidas_tecnicas: float, factores: Mapping[str, Factor], registro: RegistroNormativo, *,
                        combinacion: str | None = None, fecha: str | None = None) -> Incremento:
    """Las pérdidas técnicas con los factores de incremento facultativos del 6.9 (decisión P-6 de 28)."""
    try:
        v = registro.regla(REGLA_INCREMENTO, fecha)
    except RegistroError as exc:
        raise VadError(f'los factores de incremento necesitan {REGLA_INCREMENTO}: {exc}') from exc
    topes = v.regla.valor
    for nombre, f in factores.items():
        if nombre not in (*FACTORES, 'armonicos'):
            raise VadError(f'factor de incremento {nombre!r} desconocido; el 6.9 trae {(*FACTORES, "armonicos")}')
        if not f.sustento.strip():
            raise VadError(f'el factor {nombre} no declara su sustento')
        if f.valor < 0:
            raise VadError(f'el factor {nombre} es negativo: {f.valor}')
        if nombre in FACTORES and f.valor > float(topes[FACTORES[nombre]]):
            raise VadError(f'el factor de {nombre} ({f.valor:.2%}) supera su tope del '
                           f'{float(topes[FACTORES[nombre]]):.0%} ({_cita(v)})')
        if nombre == 'armonicos' and not f.medicion.strip():
            raise VadError(f'el incremento por armónicos solo se admite con una medición que lo acredite ({_cita(v)})')
    suma = perdidas_tecnicas * (1.0 + sum(f.valor for f in factores.values()))
    producto = perdidas_tecnicas
    for f in factores.values():
        producto *= 1.0 + f.valor
    res = Incremento(suma, producto, None, combinacion, reglas={REGLA_INCREMENTO: v.huella()})
    res.avisos.append(f'con los factores sumados: {suma:.6g}; multiplicados: {producto:.6g} ({_cita(v)})')
    if combinacion is None:
        res.huecos.append('el TdR no dice si los factores se suman o se multiplican y el perfil no lo declara: hueco '
                          'nombrado; no se aplica ninguno')
    elif combinacion not in COMBINACIONES:
        raise VadError(f'combinación {combinacion!r}; las admitidas son {COMBINACIONES}')
    else:
        res.aplicado = suma if combinacion == 'suma' else producto
    return res
