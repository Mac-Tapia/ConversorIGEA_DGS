"""044:RF-1 a RF-8 — particiones declaradas, política sellada y medición nativa completa."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import unicodedata

from .experimentos import ContextoExperimento

PARTES = ('entrenamiento', 'seleccion', 'calibracion', 'prueba')


def huella(valor) -> str:
    return hashlib.sha256(json.dumps(valor, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def texto_canonico(texto: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', texto).casefold().split())


@dataclass(frozen=True)
class PoliticaEvaluacion:
    modo: str = 'por_sistema'
    schema_version: int = 1
    min_calibracion_grupos: int = 1
    cobertura_objetivo: float = .9
    puertas_por_familia: tuple = (('acierto_tarea', .95), ('f1_datos', .85))
    semillas: tuple[int, ...] = (11, 23, 37)
    minimos: tuple[int, int, int, int] = (1, 1, 1, 1)

    def __post_init__(self):
        if self.modo not in {'por_sistema', 'generalizacion', 'agente'} or self.schema_version != 1:
            raise ValueError('política no soportada')
        if not 0 < self.cobertura_objetivo < 1:
            raise ValueError('cobertura inválida')
        if (type(self.min_calibracion_grupos) is not int or self.min_calibracion_grupos < 1
                or len(self.minimos) != 4 or any(type(n) is not int or n < 1 for n in self.minimos)):
            # 044:RF-2: no declararlo es lo mismo que no tenerlo, no un mínimo de uno por omisión.
            raise ValueError('BLOQUEADO_POR_DATOS: mínimos positivos obligatorios')
        if not self.semillas or len(set(self.semillas)) != len(self.semillas) or any(type(s) is not int for s in self.semillas):
            raise ValueError('semillas únicas y explícitas obligatorias')
        puertas = self.puertas_por_familia
        if isinstance(puertas, Mapping):
            puertas = tuple(sorted(puertas.items()))
        if (not puertas and self._exige_puertas_minimas()) or any(not isinstance(k, str) or not math.isfinite(v) or not 0 <= v <= 1 for k, v in puertas):
            raise ValueError('puertas inválidas')
        object.__setattr__(self, 'puertas_por_familia', tuple(tuple(p) for p in puertas))
        object.__setattr__(self, 'semillas', tuple(self.semillas))
        object.__setattr__(self, 'minimos', tuple(self.minimos))

    def _exige_puertas_minimas(self) -> bool:
        return True

    @property
    def hash(self) -> str:
        return huella(asdict(self))


@dataclass(frozen=True)
class PoliticaDeError(PoliticaEvaluacion):
    """Puertas de un modelo cuyo error se quiere bajo, como la tensión de la PINN (044:RF-5).

    Es una clase aparte para no tocar la huella de las políticas ya selladas del asistente y del
    pronóstico, cuyas puertas son mínimos entre 0 y 1: ni un tope ni 1,05 caben en ese campo.
    """

    puertas_por_familia: tuple = ()
    metrica_error: str = 'mae_v'
    topes: tuple = ()
    tolerancia_regresion: float = 1.05
    #: Referencia y si es obligatoria: sin el flujo físico no se demuestra mejora; sin modelo en uso no hay con quién.
    referencias: tuple = (('mae_fisica', True), ('mae_activo', False))

    def __post_init__(self):
        super().__post_init__()
        topes = self.topes
        if isinstance(topes, Mapping):
            topes = tuple(sorted(topes.items()))
        if not topes or any(not isinstance(k, str) or not _finito(v) or v < 0 for k, v in topes):
            raise ValueError('topes inválidos')
        if not _finito(self.tolerancia_regresion) or self.tolerancia_regresion < 1:
            raise ValueError('tolerancia de regresión inválida')
        object.__setattr__(self, 'topes', tuple(tuple(t) for t in topes))
        object.__setattr__(self, 'referencias', tuple(tuple(r) for r in self.referencias))

    def _exige_puertas_minimas(self) -> bool:
        return False


def _finito(valor) -> bool:
    return type(valor) in (float, int) and math.isfinite(valor)


@dataclass(frozen=True)
class Particiones:
    entrenamiento: tuple[str, ...]
    seleccion: tuple[str, ...]
    calibracion: tuple[str, ...]
    prueba: tuple[str, ...]
    politica_hash: str


def particionar_registros(registros: Sequence[Mapping], politica: PoliticaEvaluacion) -> Particiones:
    """Valida asignaciones previas; nunca divide al azar filas hermanas ni rellena huecos."""
    partes = {p: [] for p in PARTES}
    grupos = {p: set() for p in PARTES}
    sistemas = defaultdict(lambda: {p: set() for p in PARTES})
    vistos, por_grupo, por_texto = set(), {}, {}
    for r in registros:
        parte, identidad, grupo = r.get('particion'), r.get('record_id'), r.get('group_id')
        if parte not in partes or not isinstance(identidad, str) or not identidad or not isinstance(grupo, str) or not grupo:
            raise ValueError('registro sin identidad, grupo o partición declarada')
        if identidad in vistos:
            raise ValueError('identidad de registro duplicada')
        vistos.add(identidad)
        texto = texto_canonico(str(r.get('texto') or ''))
        for indice, clave in ((por_grupo, grupo), (por_texto, texto)):
            if clave and clave in indice and indice[clave] != parte:
                raise ValueError('solapamiento de texto o grupo entre particiones')
            indice[clave] = parte
        partes[parte].append(identidad)
        grupos[parte].add(grupo)
        sistemas[str(r.get('sistema') or '')][parte].add(grupo)
    if politica.modo == 'generalizacion':
        for sistema, p in sistemas.items():
            if not sistema or (p['prueba'] and any(p[n] for n in PARTES[:-1])):
                raise ValueError('generalización requiere un sistema independiente para prueba')
    minimos = dict(zip(PARTES, politica.minimos, strict=True))
    minimos['calibracion'] = max(minimos['calibracion'], politica.min_calibracion_grupos)
    if any(len(grupos[p]) < n for p, n in minimos.items()):
        raise ValueError('BLOQUEADO_POR_DATOS: mínimo de grupos por partición incumplido')
    if politica.modo == 'por_sistema':
        for sistema, p in sistemas.items():
            if not sistema or any(len(p[n]) < k for n, k in
                    (('entrenamiento', 30), ('seleccion', 10), ('prueba', 10),
                     ('calibracion', politica.min_calibracion_grupos))):
                raise ValueError('BLOQUEADO_POR_DATOS: cuotas por sistema incumplidas')
    return Particiones(**{p: tuple(sorted(ids)) for p, ids in partes.items()}, politica_hash=politica.hash)


def alcance_de(politica: PoliticaEvaluacion) -> dict:
    """A qué se puede extender el resultado (044:RF-1, 027:RF-68): por sistema no dice nada de otra red."""
    generaliza = politica.modo == 'generalizacion'
    return {'modo': politica.modo, 'generaliza_a_otros_sistemas': generaliza,
            'descripcion': {'por_sistema': 'solo el sistema evaluado: la prueba son episodios suyos no vistos',
                            'generalizacion': 'sistemas enteros retenidos fuera del ajuste',
                            'agente': 'órdenes del asistente: no dice nada de una red eléctrica'}[politica.modo]}


def verificar_familias(metricas: Mapping, referencia: Mapping | None,
                       politica: PoliticaEvaluacion, *, esperadas: Sequence[str] | None = None) -> list[str]:
    """044:RF-5 — toda familia debe pasar; una buena media no compensa otra regresión."""
    fallos = []
    esperadas = set(esperadas) if esperadas is not None else set(metricas) | set(referencia or {})
    if set(metricas) != esperadas:
        fallos.append('cobertura incompleta de familias esperadas')
    if referencia is not None and set(referencia) != esperadas:
        fallos.append('referencia incompleta para las familias esperadas')
    for familia, valores in metricas.items():
        if type(valores.get('ejemplos')) is not int or valores['ejemplos'] < 1:
            fallos.append(f'{familia}: sin denominador positivo')
        for nombre, minimo in politica.puertas_por_familia:
            valor = valores.get(nombre)
            valido = type(valor) in (float, int) and math.isfinite(valor)
            if not valido or valor < minimo:
                fallos.append(f'{familia}: {nombre} bajo puerta o ausente')
            previo = (referencia or {}).get(familia, {}).get(nombre)
            if previo is not None and (type(previo) not in (float, int) or not math.isfinite(previo)
                                      or not valido or valor + 1e-9 < previo):
                fallos.append(f'{familia}: regresión frente a referencia en {nombre}')
    if not metricas:
        fallos.append('sin familias evaluadas')
    return fallos


def _fallos_de_error(ambito: str, valores: Mapping, politica: PoliticaDeError) -> list[str]:
    """Topes y comparación con las referencias en un ámbito; lo que falta no se da por bueno."""
    fallos = []
    if type(valores.get('ejemplos')) is not int or valores['ejemplos'] < 1:
        fallos.append(f'{ambito}: sin denominador positivo')
    for nombre, tope in politica.topes:
        valor = valores.get(nombre)
        if not _finito(valor):
            fallos.append(f'{ambito}: {nombre} ausente o no finito')
        elif valor > tope:
            fallos.append(f'{ambito}: {nombre} {valor:.4g} sobre el tope {tope:g}')
    error = valores.get(politica.metrica_error)
    for referencia, obligatoria in politica.referencias:
        medida = valores.get(referencia)
        if medida is None and not obligatoria:
            continue
        if not _finito(medida):
            fallos.append(f'{ambito}: sin medida de {referencia} con que comparar')
        elif _finito(error) and error > politica.tolerancia_regresion * medida + 1e-6:
            fallos.append(f'{ambito}: {politica.metrica_error} {error:.4g} peor que {referencia} {medida:.4g}')
    return fallos


def evaluar_candidato(metricas: Mapping, politica: PoliticaEvaluacion) -> dict:
    """044:RF-5 — el veredicto del candidato en conjunto y familia por familia.

    Una familia pequeña que empeora no sale en la media global: por eso cada una pasa sus puertas.
    ``metricas`` trae ``global`` y ``familias`` y, si se conocen, ``esperadas`` y ``referencia``.
    """
    familias = metricas.get('familias') or {}
    globales = metricas.get('global') or {}
    esperadas = metricas.get('esperadas')
    gates: dict = {'familias': {}}
    if isinstance(politica, PoliticaDeError):
        bloqueos = _fallos_de_error('global', globales, politica)
        gates['global'] = not bloqueos
        if not familias:
            bloqueos.append('sin familias evaluadas')
        if esperadas is not None and set(familias) != set(esperadas):
            bloqueos.append('cobertura incompleta de familias esperadas')
        for familia, valores in sorted(familias.items()):
            fallos = _fallos_de_error(f'familia {familia}', valores, politica)
            gates['familias'][familia] = not fallos
            bloqueos += fallos
    else:
        bloqueos = verificar_familias(familias, metricas.get('referencia'), politica, esperadas=esperadas)
        for familia in familias:
            gates['familias'][familia] = not any(b.startswith(f'{familia}:') for b in bloqueos)
    return {'approved': not bloqueos, 'gates': gates, 'bloqueos': bloqueos, 'global': dict(globales),
            'familias': {f: dict(v) for f, v in familias.items()}, 'politica_hash': politica.hash,
            'alcance': alcance_de(politica)}


#: Unidades con que se comparan el gemelo y DIgSILENT: otra unidad daría una diferencia sin sentido.
UNIDADES_NATIVAS = {'v_min': 'p.u.', 'perdidas_kw': 'kW'}
#: Lo que tiene que traer el flujo para poder juzgarlo por la norma, no solo saber que convergió.
BLOQUES_DE_FLUJO = ('tensiones', 'perdidas', 'cargabilidad')
#: Holgura entre el resumen y su flujo: es el mismo dato, y solo cabe el redondeo.
HOLGURA_RESUMEN = {'v_min': 1e-4, 'perdidas_kw': 1e-2}
#: Lo que debe coincidir con la referencia: la obra cambia topología, controles y caso; la red de partida, no.
CAMPOS_DE_REFERENCIA = ('source_mode', 'source_fingerprint', 'project', 'feeders', 'year', 'period',
                        'criterio_fijas', 'profile_hash')
#: Casos que se juzgan contra una referencia; un «Caso base» es la red tal como está.
ROLES_CON_REFERENCIA = ('con_proyecto', 'cargas_nuevas')


def metrica_invalida(valores: Mapping, origen: str) -> list[str]:
    """044:RF-6: una ausencia o NaN no puede aparentar diferencia cero."""
    motivos = []
    for clave in UNIDADES_NATIVAS:
        valor = valores.get(clave)
        try:
            numero = float(valor) if not isinstance(valor, bool) else float('nan')
        except (ValueError, TypeError, OverflowError):
            numero = float('nan')
        if not math.isfinite(numero) or (clave == 'perdidas_kw' and numero < 0):
            motivos.append(f'{origen}: métrica {clave} ausente o inválida')
    return motivos


def _numeros_del_bloque(valor) -> list:
    if isinstance(valor, Mapping):
        return [n for v in valor.values() for n in _numeros_del_bloque(v)]
    return [valor]


def _flujo_incompleto(flujo, origen: str) -> list[str]:
    """Falta o no es finito algún bloque del flujo: juzgar con él sería juzgar a medias."""
    if not isinstance(flujo, Mapping):
        return [f'{origen}: sin el flujo completo']
    motivos = []
    for bloque in BLOQUES_DE_FLUJO:
        datos = flujo.get(bloque)
        valores = datos.get('valores') if isinstance(datos, Mapping) else None
        numeros = _numeros_del_bloque(valores) if isinstance(valores, Mapping) else []
        if not numeros:
            motivos.append(f'{origen}: flujo sin {bloque}')
        elif not all(_finito(n) for n in numeros):
            motivos.append(f'{origen}: {bloque} con valores no finitos')
    return motivos


def _contexto_de(valor) -> ContextoExperimento | None:
    if isinstance(valor, ContextoExperimento):
        return valor
    try:
        return ContextoExperimento(**valor) if isinstance(valor, Mapping) else None
    except (TypeError, ValueError):
        return None


def _distintos(a: ContextoExperimento, b: ContextoExperimento, campos: Sequence[str]) -> list[str]:
    return [c for c in campos if getattr(a, c) != getattr(b, c)]


def _motivos_de_referencia(medicion: Mapping, contexto: ContextoExperimento) -> list[str]:
    referencia = medicion.get('referencia')
    if referencia is None and contexto.case_role not in ROLES_CON_REFERENCIA:
        return []
    if not isinstance(referencia, Mapping):
        return ['falta la evaluación nativa de la referencia vinculada']
    motivos = _flujo_incompleto(referencia.get('flujo'), 'referencia')
    propio = _contexto_de(referencia.get('contexto'))
    if propio is None:
        motivos.append('referencia sin contexto válido')
    else:
        distintos = _distintos(propio, contexto, CAMPOS_DE_REFERENCIA)
        if distintos:
            motivos.append('la referencia es de otro contexto: ' + ', '.join(distintos))
        if propio.case_role != 'sin_proyecto' and contexto.case_role in ROLES_CON_REFERENCIA:
            motivos.append(f'la referencia es del caso {propio.case_role}, no de «sin_proyecto»')
    if referencia.get('reabierto') is not True:
        motivos.append('referencia sin reabrir y releer en una sesión nueva')
    return motivos


def comprobar_tolerancias(politica: Mapping) -> None:
    """Una tolerancia NaN convertiría cualquier diferencia en aceptación (044:RF-6)."""
    for nombre in ('tolerancia_v_pu', 'tolerancia_perdidas', 'tolerancia_perdidas_kw'):
        valor = politica.get(nombre)
        if valor is None and nombre == 'tolerancia_perdidas_kw':
            continue
        if not _finito(valor) or valor < 0:
            raise ValueError(f'{nombre}: tolerancia no finita o negativa')


def validar_medicion_nativa(prediccion: Mapping, medicion: Mapping, contexto: ContextoExperimento | None, *,
                            politica: Mapping) -> dict:
    """044:RF-6, RF-7 — esquema, contexto, unidades y completitud, antes de comparar nada.

    Convergir solo dice que hay flujo. Para aceptar una alternativa hacen falta su flujo completo, reabierto, en el
    mismo caso que se predijo, y el de su referencia: una medida de otro año es una medida correcta de otra cosa.
    Devuelve ``valida``, ``motivos`` (todos, no el primero) y las ``diferencias`` si se pudieron calcular.
    """
    comprobar_tolerancias(politica)
    motivos = metrica_invalida(prediccion, 'predicción') + metrica_invalida(medicion, 'DIgSILENT')
    completas = not motivos
    if not isinstance(contexto, ContextoExperimento):
        motivos.append('sin contexto del experimento con que comprobar la medición')
    else:
        medido = _contexto_de(medicion.get('contexto'))
        if medido is None:
            motivos.append('medición sin contexto válido')
        else:
            distintos = _distintos(medido, contexto, tuple(asdict(contexto)))
            if distintos:
                motivos.append('la medición es de otro contexto: ' + ', '.join(distintos))
        motivos += _motivos_de_referencia(medicion, contexto)
    if medicion.get('unidades') != UNIDADES_NATIVAS:
        motivos.append(f'unidades no declaradas o distintas de {UNIDADES_NATIVAS}')
    flujo = medicion.get('flujo')
    faltan = _flujo_incompleto(flujo, 'DIgSILENT')
    motivos += faltan
    if medicion.get('reabierto') is not True:
        motivos.append('sin reabrir y releer el proyecto en una sesión nueva')
    if medicion.get('revertido') is not False:
        motivos.append('sin constancia de que la acción siga aplicada')
    diferencias = None
    if completas:
        v_gemelo, v_medida = float(prediccion['v_min']), float(medicion['v_min'])
        p_gemelo, p_medida = float(prediccion['perdidas_kw']), float(medicion['perdidas_kw'])
        if not faltan:
            tensiones = _numeros_del_bloque(flujo['tensiones']['valores'])
            total = flujo['perdidas']['valores'].get('total')
            if abs(min(tensiones) - v_medida) > HOLGURA_RESUMEN['v_min']:
                motivos.append(f'v_min {v_medida:.4f} p.u. no es el mínimo de su flujo, {min(tensiones):.4f}')
            if not _finito(total) or abs(total - p_medida) > HOLGURA_RESUMEN['perdidas_kw']:
                motivos.append(f'perdidas_kw {p_medida:.1f} no son el total de su flujo, {total}')
        diferencias = {'v_min_pu': abs(v_medida - v_gemelo), 'perdidas_kw': abs(p_medida - p_gemelo)}
        if diferencias['v_min_pu'] > politica['tolerancia_v_pu']:
            motivos.append(f'tensión mínima {v_medida:.4f} p.u. frente a {v_gemelo:.4f} del gemelo')
        if p_gemelo:
            diferencias['perdidas_fraccion'] = diferencias['perdidas_kw'] / p_gemelo
            if diferencias['perdidas_fraccion'] > politica['tolerancia_perdidas']:
                motivos.append(f'pérdidas {p_medida:.1f} kW frente a {p_gemelo:.1f} del gemelo')
        else:
            # 044:RF-6: dividir por cero escondía el error; con referencia cero, la diferencia absoluta declarada.
            absoluta = politica.get('tolerancia_perdidas_kw')
            if absoluta is None and p_medida != 0:
                motivos.append('pérdidas predichas en cero sin tolerancia absoluta declarada')
            elif absoluta is not None and diferencias['perdidas_kw'] > absoluta:
                motivos.append(f'pérdidas {p_medida:.1f} kW frente a {p_gemelo:.1f} del gemelo, '
                               f'más de {absoluta:g} kW')
    return {'valida': not motivos, 'motivos': motivos, 'diferencias': diferencias, 'unidades': dict(UNIDADES_NATIVAS),
            'politica': {k: politica.get(k) for k in ('tolerancia_v_pu', 'tolerancia_perdidas', 'tolerancia_perdidas_kw')}}
