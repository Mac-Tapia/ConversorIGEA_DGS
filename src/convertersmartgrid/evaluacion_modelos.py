"""044:RF-1 a RF-5 y RF-8 — particiones declaradas y política sellada antes del ajuste."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import unicodedata

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
            raise ValueError('mínimos positivos obligatorios')
        if not self.semillas or len(set(self.semillas)) != len(self.semillas) or any(type(s) is not int for s in self.semillas):
            raise ValueError('semillas únicas y explícitas obligatorias')
        puertas = self.puertas_por_familia
        if isinstance(puertas, Mapping):
            puertas = tuple(sorted(puertas.items()))
        if not puertas or any(not isinstance(k, str) or not math.isfinite(v) or not 0 <= v <= 1 for k, v in puertas):
            raise ValueError('puertas inválidas')
        object.__setattr__(self, 'puertas_por_familia', tuple(tuple(p) for p in puertas))
        object.__setattr__(self, 'semillas', tuple(self.semillas))
        object.__setattr__(self, 'minimos', tuple(self.minimos))

    @property
    def hash(self) -> str:
        return huella(asdict(self))


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
