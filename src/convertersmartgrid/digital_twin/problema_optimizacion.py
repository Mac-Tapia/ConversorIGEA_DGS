"""Contrato común de una búsqueda de obras y consignas (spec 048, T1: RF-1, RF-2, RF-5).

Los optimizadores de ``evolutivo.py`` recibían una función y unas cotas: nada decía qué era
cada gen, en qué unidad, de dónde salía su dominio ni qué red evaluaba. Así un genoma
continuo podía proponer 1,4 módulos de banco, una maniobra que deja carga sin fuente «perdía
menos» porque ya no la alimentaba, y la memoria de evaluaciones, indexada solo por el
genoma, habría devuelto el resultado de otro año o de otro modelo si se compartía.

Aquí el problema se declara una vez (variables tipadas con unidad y origen, restricciones,
objetivos, contexto y modelo) y toda evaluación pasa por ``evaluar_vector``, que:

- rechaza el vector que no es del dominio (no lo redondea: la reparación de los genes de un
  algoritmo es ``reparar``, una sola regla igual para todos);
- exige al evaluador la demanda del flujo de referencia y la atendida, y no da por factible
  la solución que deja demanda sin servicio;
- calcula el coste con los costes trazables de las variables y, sin ellos, deja el objetivo
  sin valor en vez de inventar un cero.

``clave_evaluacion`` reúne las huellas del contexto, del modelo, de la política y del
problema con el vector normalizado; ``CacheEvaluaciones`` solo reutiliza con esa clave.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from numbers import Integral, Real
from typing import Any

import numpy as np

from ..experimentos import ContextoExperimento, clave_contexto

TIPOS = ('continua', 'entera', 'binaria', 'categorica')
DISCRETAS = ('entera', 'binaria', 'categorica')
#: Fracción de la demanda de referencia que puede faltar por redondeo numérico del flujo.
TOLERANCIA_DEMANDA = 1e-6
CRITERIO_REPARACION = ('discretas al entero más cercano (medio entero hacia arriba) y recortadas a sus cotas; '
                       'categóricas por índice del catálogo; continuas recortadas a sus cotas')


def huella(valor: Any) -> str:
    """SHA-256 del JSON canónico de ``valor`` (claves ordenadas, sin NaN)."""
    texto = json.dumps(valor, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def _texto(valor: Any, que: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f'falta {que}')
    return valor


def _finito(valor: Any) -> bool:
    return isinstance(valor, Real) and not isinstance(valor, bool) and math.isfinite(float(valor))


def _entero(valor: Any) -> int | None:
    """El entero que es ``valor`` (2 o 2.0), o ``None`` si es una fracción, un booleano o no es un número."""
    if isinstance(valor, bool) or not _finito(valor):
        return None
    if isinstance(valor, Integral):
        return int(valor)
    return int(valor) if float(valor).is_integer() else None


@dataclass(frozen=True)
class Variable:
    """Una decisión del problema, con su dominio, su unidad y de dónde sale ese dominio (RF-1).

    ``coste`` es el coste por unidad de la variable (o, si es categórica, el de cada equipo del
    catálogo) y exige ``origen_coste``: un coste sin fuente es un número inventado.
    """
    nombre: str
    tipo: str
    unidad: str
    origen: str
    inferior: float | None = None
    superior: float | None = None
    catalogo: tuple[str, ...] = ()
    coste: float | Mapping[str, float] | None = None
    origen_coste: str | None = None

    def __post_init__(self):
        _texto(self.nombre, 'nombre de la variable')
        if self.tipo not in TIPOS:
            raise ValueError(f'{self.nombre}: tipo {self.tipo!r} desconocido (admitidos: {", ".join(TIPOS)})')
        _texto(self.unidad, f'unidad de {self.nombre}')
        _texto(self.origen, f'origen del dominio de {self.nombre}')
        if self.tipo == 'categorica':
            catalogo = tuple(self.catalogo)
            if not catalogo or any(not isinstance(c, str) or not c.strip() for c in catalogo):
                raise ValueError(f'{self.nombre}: una variable categórica necesita su catálogo de equipos')
            if len(set(catalogo)) != len(catalogo):
                raise ValueError(f'{self.nombre}: el catálogo tiene equipos repetidos')
            if self.inferior is not None or self.superior is not None:
                raise ValueError(f'{self.nombre}: una variable categórica no tiene cotas, tiene catálogo')
            object.__setattr__(self, 'catalogo', catalogo)
        else:
            if self.catalogo:
                raise ValueError(f'{self.nombre}: solo una variable categórica tiene catálogo')
            if self.tipo == 'binaria' and self.inferior is None and self.superior is None:
                object.__setattr__(self, 'inferior', 0)
                object.__setattr__(self, 'superior', 1)
            if not (_finito(self.inferior) and _finito(self.superior)) or self.inferior > self.superior:
                raise ValueError(f'{self.nombre}: cotas inferior y superior finitas y ordenadas')
            if self.tipo in ('entera', 'binaria'):
                inf, sup = _entero(self.inferior), _entero(self.superior)
                if inf is None or sup is None:
                    raise ValueError(f'{self.nombre}: una variable entera tiene cotas enteras')
                if self.tipo == 'binaria' and (inf, sup) != (0, 1):
                    raise ValueError(f'{self.nombre}: una variable binaria va de 0 a 1')
                object.__setattr__(self, 'inferior', inf)
                object.__setattr__(self, 'superior', sup)
            else:
                object.__setattr__(self, 'inferior', float(self.inferior))
                object.__setattr__(self, 'superior', float(self.superior))
        if self.coste is not None:
            _texto(self.origen_coste, f'origen_coste de {self.nombre}')
            if self.tipo == 'categorica':
                if not isinstance(self.coste, Mapping) or set(self.coste) != set(self.catalogo) or not all(
                        _finito(c) and c >= 0 for c in self.coste.values()):
                    raise ValueError(f'{self.nombre}: el coste de una categórica es uno no negativo por equipo')
                object.__setattr__(self, 'coste', {k: float(self.coste[k]) for k in self.catalogo})
            elif not _finito(self.coste) or self.coste < 0:
                raise ValueError(f'{self.nombre}: coste por unidad finito y no negativo')
        elif self.origen_coste is not None:
            raise ValueError(f'{self.nombre}: origen_coste sin coste')

    @property
    def discreta(self) -> bool:
        return self.tipo in DISCRETAS

    def publico(self) -> dict[str, Any]:
        d: dict[str, Any] = {'nombre': self.nombre, 'tipo': self.tipo, 'unidad': self.unidad, 'origen': self.origen}
        if self.tipo == 'categorica':
            d['catalogo'] = list(self.catalogo)
        else:
            d['inferior'], d['superior'] = self.inferior, self.superior
        if self.coste is not None:
            d['coste'] = dict(self.coste) if isinstance(self.coste, Mapping) else self.coste
            d['origen_coste'] = self.origen_coste
        return d


@dataclass(frozen=True)
class Restriccion:
    """Una restricción que el evaluador mide como violación no negativa (0 = cumple)."""
    nombre: str
    unidad: str
    descripcion: str

    def __post_init__(self):
        _texto(self.nombre, 'nombre de la restricción')
        _texto(self.unidad, f'unidad de la restricción {self.nombre}')
        _texto(self.descripcion, f'descripción de la restricción {self.nombre}')


@dataclass(frozen=True)
class Objetivo:
    """Un objetivo a minimizar: lo calcula el evaluador o, con ``origen='coste'``, los costes declarados."""
    nombre: str
    unidad: str
    origen: str = 'evaluador'

    def __post_init__(self):
        _texto(self.nombre, 'nombre del objetivo')
        _texto(self.unidad, f'unidad del objetivo {self.nombre}')
        if self.origen not in ('evaluador', 'coste'):
            raise ValueError(f'objetivo {self.nombre}: origen evaluador o coste')


@dataclass(frozen=True)
class ContextoSintetico:
    """El contexto de un problema analítico de benchmark, que no es ninguna red.

    Un ``ContextoExperimento`` exige fuente, proyecto y caso reales; inventarlos para una función
    de prueba sería falsear su procedencia. Este lo dice abiertamente con su ``dominio``.
    """
    dominio: str
    descripcion: str

    def __post_init__(self):
        _texto(self.dominio, 'dominio del contexto sintético')
        _texto(self.descripcion, 'descripción del contexto sintético')


def _clave_de_contexto(contexto: ContextoExperimento | ContextoSintetico) -> str:
    if isinstance(contexto, ContextoExperimento):
        return clave_contexto(contexto)
    return huella({'sintetico': {'dominio': contexto.dominio, 'descripcion': contexto.descripcion}})


@dataclass(frozen=True)
class ProblemaOptimizacion:
    """Una búsqueda declarada: qué se decide, qué se exige, qué se minimiza, sobre qué red y con qué modelo.

    ``evaluador(vector)`` devuelve ``convergio``, ``objetivos`` (los de origen evaluador),
    ``violaciones`` (una por restricción declarada) y la demanda del flujo de referencia y la
    atendida (``demanda_referencia_kw``, ``demanda_atendida_kw``). ``modelo_pnl`` es opcional: lo
    usa ``adaptador_pnl`` para el tramo continuo. ``normalizacion`` (ideal y nadir de cada
    objetivo) se declara antes de comparar algoritmos por hipervolumen.
    """
    nombre: str
    variables: tuple[Variable, ...]
    restricciones: tuple[Restriccion, ...]
    objetivos: tuple[Objetivo, ...]
    contexto: ContextoExperimento | ContextoSintetico
    modelo_id: str
    evaluador: Callable[[Mapping[str, Any]], Mapping[str, Any]] = field(compare=False, repr=False)
    modelo_pnl: Callable[..., Mapping[str, Any]] | None = field(default=None, compare=False, repr=False)
    normalizacion: Mapping[str, tuple[float, float]] | None = None
    tolerancia_demanda: float = TOLERANCIA_DEMANDA

    def __post_init__(self):
        _texto(self.nombre, 'nombre del problema')
        _texto(self.modelo_id, 'modelo_id del problema')
        if not isinstance(self.contexto, (ContextoExperimento, ContextoSintetico)):
            raise ValueError('el contexto debe ser un ContextoExperimento o un ContextoSintetico declarado')
        for nombre, tipo in (('variables', Variable), ('restricciones', Restriccion), ('objetivos', Objetivo)):
            lista = tuple(getattr(self, nombre))
            if any(not isinstance(x, tipo) for x in lista):
                raise ValueError(f'{nombre} del problema mal formadas')
            if len({x.nombre for x in lista}) != len(lista):
                raise ValueError(f'{nombre} con nombres repetidos')
            object.__setattr__(self, nombre, lista)
        if not self.variables or not self.objetivos:
            raise ValueError('un problema necesita al menos una variable y un objetivo')
        if not callable(self.evaluador):
            raise ValueError('falta el evaluador del problema')
        if not _finito(self.tolerancia_demanda) or not 0 <= self.tolerancia_demanda < 1:
            raise ValueError('tolerancia_demanda es una fracción en [0, 1)')
        if self.normalizacion is not None:
            nombres = {o.nombre for o in self.objetivos}
            if set(self.normalizacion) != nombres or not all(
                    len(par) == 2 and _finito(par[0]) and _finito(par[1]) and par[1] > par[0]
                    for par in self.normalizacion.values()):
                raise ValueError('normalizacion: ideal < nadir, finitos, para cada objetivo')
            object.__setattr__(self, 'normalizacion',
                               {k: (float(a), float(b)) for k, (a, b) in self.normalizacion.items()})

    def declaracion(self) -> dict[str, Any]:
        """Lo que define el problema, en JSON: es lo que firma ``huella_problema``."""
        if isinstance(self.contexto, ContextoExperimento):
            contexto = {'clave': clave_contexto(self.contexto), 'case_role': self.contexto.case_role,
                        'year': self.contexto.year, 'criterio_fijas': self.contexto.criterio_fijas}
        else:
            contexto = {'clave': _clave_de_contexto(self.contexto), 'dominio': self.contexto.dominio,
                        'descripcion': self.contexto.descripcion}
        return {'nombre': self.nombre, 'modelo_id': self.modelo_id, 'contexto': contexto,
                'variables': [v.publico() for v in self.variables],
                'restricciones': [{'nombre': r.nombre, 'unidad': r.unidad, 'descripcion': r.descripcion}
                                  for r in self.restricciones],
                'objetivos': [{'nombre': o.nombre, 'unidad': o.unidad, 'origen': o.origen} for o in self.objetivos],
                'normalizacion': ({k: list(v) for k, v in self.normalizacion.items()}
                                  if self.normalizacion else None),
                'tolerancia_demanda': self.tolerancia_demanda}


def huella_problema(problema: ProblemaOptimizacion) -> str:
    return huella(problema.declaracion())


# ------------------------------------------------------------------ dominio del vector
def validar_vector(problema: ProblemaOptimizacion, vector: Mapping[str, Any]) -> dict[str, Any]:
    """El vector en su forma canónica, o ``ValueError`` que nombra la variable fuera de su dominio.

    No redondea: un 1,4 que llega aquí es un error del que lo propone, no algo que arreglar
    en silencio (RF-2).
    """
    if not isinstance(vector, Mapping):
        raise ValueError('el vector de decisión es un mapa variable → valor')
    nombres = [v.nombre for v in problema.variables]
    if faltan := [n for n in nombres if n not in vector]:
        raise ValueError(f'falta en el vector: {", ".join(faltan)}')
    if sobran := sorted(str(k) for k in vector if k not in set(nombres)):
        raise ValueError(f'variable desconocida en el vector: {", ".join(sobran)}')
    canonico: dict[str, Any] = {}
    for v in problema.variables:
        x = vector[v.nombre]
        if v.tipo == 'categorica':
            if not isinstance(x, str) or x not in v.catalogo:
                raise ValueError(f'{v.nombre}: {x!r} no está en su catálogo ({", ".join(v.catalogo)})')
            canonico[v.nombre] = x
        elif v.tipo in ('entera', 'binaria'):
            k = _entero(x)
            if k is None:
                raise ValueError(f'{v.nombre}: {x!r} no es un número entero de {v.unidad}')
            if not v.inferior <= k <= v.superior:
                raise ValueError(f'{v.nombre}: {k} fuera de [{v.inferior}, {v.superior}] {v.unidad}')
            canonico[v.nombre] = k
        else:
            if not _finito(x):
                raise ValueError(f'{v.nombre}: {x!r} no es un número finito')
            if not v.inferior <= float(x) <= v.superior:
                raise ValueError(f'{v.nombre}: {x} fuera de [{v.inferior}, {v.superior}] {v.unidad}')
            canonico[v.nombre] = float(x)
    return canonico


def cotas_geneticas(problema: ProblemaOptimizacion) -> tuple[np.ndarray, np.ndarray]:
    """Cotas de los genes reales con que trabajan los algoritmos; una categórica va por su índice."""
    inf = [0.0 if v.tipo == 'categorica' else float(v.inferior) for v in problema.variables]
    sup = [float(len(v.catalogo) - 1) if v.tipo == 'categorica' else float(v.superior) for v in problema.variables]
    return np.array(inf), np.array(sup)


def reparar(problema: ProblemaOptimizacion, genes: Sequence[float]) -> dict[str, Any]:
    """Los genes de cualquier algoritmo como un vector admisible, con la misma regla para todos.

    Comparar algoritmos con reparaciones distintas compararía las reparaciones: el que redondea
    hacia abajo encuentra otras soluciones que el que trunca (spec 048, T2).
    """
    g = np.asarray(genes, dtype=float)
    if g.shape != (len(problema.variables),) or not np.all(np.isfinite(g)):
        raise ValueError('genes con otra longitud que las variables, o no finitos')
    inf, sup = cotas_geneticas(problema)
    g = np.clip(g, inf, sup)
    vector: dict[str, Any] = {}
    for i, (v, x) in enumerate(zip(problema.variables, g, strict=True)):
        if v.discreta:
            k = int(min(max(math.floor(x + 0.5), inf[i]), sup[i]))
            vector[v.nombre] = v.catalogo[k] if v.tipo == 'categorica' else k
        else:
            vector[v.nombre] = float(x)
    return vector


# ------------------------------------------------------------------ evaluación
def _coste(problema: ProblemaOptimizacion, vector: Mapping[str, Any]) -> tuple[float | None, list[str]]:
    total, sin = 0.0, []
    for v in problema.variables:
        x = vector[v.nombre]
        if v.tipo == 'categorica':
            if v.coste is None:
                sin.append(v.nombre)
            else:
                total += v.coste[x]
        elif x != 0:
            if v.coste is None:
                sin.append(v.nombre)
            else:
                total += float(x) * v.coste
    if sin:
        return None, [f'sin coste trazable para {", ".join(sin)}: la inversión queda sin valor, no en cero']
    return total, []


def evaluar_vector(problema: ProblemaOptimizacion, vector: Mapping[str, Any]) -> dict[str, Any]:
    """Factibilidad, objetivos y violaciones de un vector, con la demanda de referencia y la atendida.

    Es factible si el flujo converge, cada restricción declarada se mide y cumple, y la demanda
    atendida no baja de la del flujo de referencia: desconectar cargas no es una mejora (RF-2).
    """
    canonico = validar_vector(problema, vector)
    crudo = problema.evaluador(dict(canonico))
    crudo = crudo if isinstance(crudo, Mapping) else {}
    avisos: list[str] = []
    violaciones: dict[str, float] = {}
    convergio = crudo.get('convergio') is True
    if not convergio:
        avisos.append('el flujo no converge con este vector')
    medidas = crudo.get('violaciones') if isinstance(crudo.get('violaciones'), Mapping) else {}
    for r in problema.restricciones:
        x = medidas.get(r.nombre)
        if not _finito(x) or x < 0:
            avisos.append(f'el evaluador no mide la restricción {r.nombre} ({r.unidad})')
            violaciones[r.nombre] = math.inf
        else:
            violaciones[r.nombre] = float(x)
    referencia, atendida = crudo.get('demanda_referencia_kw'), crudo.get('demanda_atendida_kw')
    demanda: dict[str, float | None] = {'referencia_kw': float(referencia) if _finito(referencia) else None,
                                        'atendida_kw': float(atendida) if _finito(atendida) else None}
    if demanda['referencia_kw'] is None or demanda['atendida_kw'] is None or demanda['referencia_kw'] < 0:
        avisos.append('el evaluador no da demanda_referencia_kw y demanda_atendida_kw: '
                      'no se puede probar que ninguna carga quedó sin servicio')
        violaciones['demanda_no_atendida_kw'] = math.inf
    else:
        deficit = demanda['referencia_kw'] - demanda['atendida_kw']
        if deficit > problema.tolerancia_demanda * max(demanda['referencia_kw'], 1e-9):
            violaciones['demanda_no_atendida_kw'] = deficit
            avisos.append(f'deja {deficit:.3f} kW sin servicio respecto del flujo de referencia')
    medidos = crudo.get('objetivos') if isinstance(crudo.get('objetivos'), Mapping) else {}
    objetivos: dict[str, float | None] = {}
    for o in problema.objetivos:
        if o.origen == 'coste':
            objetivos[o.nombre], aviso = _coste(problema, canonico)
            avisos.extend(aviso)
        else:
            x = medidos.get(o.nombre)
            objetivos[o.nombre] = float(x) if _finito(x) else None
            if objetivos[o.nombre] is None:
                avisos.append(f'el evaluador no da el objetivo {o.nombre}')
    total = sum(violaciones.values())
    return {'vector': canonico, 'factible': bool(convergio and total == 0), 'convergio': convergio,
            'objetivos': objetivos, 'comparable': all(x is not None for x in objetivos.values()),
            'violaciones': violaciones, 'violacion_total': total, 'demanda': demanda,
            'referencia': crudo.get('referencia'), 'avisos': avisos}


def clave_evaluacion(problema: ProblemaOptimizacion, vector: Mapping[str, Any], politica_hash: str) -> str:
    """Huella que solo coincide con el mismo contexto, modelo, política, problema y vector (RF-5)."""
    if not isinstance(politica_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', politica_hash):
        raise ValueError('politica_hash debe ser la huella SHA-256 de la política de evaluación')
    canonico = validar_vector(problema, vector)
    return huella({'contexto': _clave_de_contexto(problema.contexto), 'modelo_id': problema.modelo_id,
                    'politica': politica_hash, 'problema': huella_problema(problema),
                    # repr conserva la cifra exacta del real: 1.0 y 1.0+1e-12 no comparten evaluación.
                    'vector': {k: (repr(x) if isinstance(x, float) else x) for k, x in sorted(canonico.items())}})


class CacheEvaluaciones:
    """Memoria de evaluaciones que solo reutiliza con ``clave_evaluacion``; cuenta reales y reutilizadas."""

    def __init__(self) -> None:
        self._guardadas: dict[str, dict[str, Any]] = {}
        self.reales = 0
        self.cacheadas = 0

    def __len__(self) -> int:
        return len(self._guardadas)

    def consultar(self, problema: ProblemaOptimizacion, vector: Mapping[str, Any], politica_hash: str) -> dict | None:
        """Lo guardado con esa clave, sin evaluar ni contarlo; ``None`` si no se evaluó."""
        return self._guardadas.get(clave_evaluacion(problema, vector, politica_hash))

    def evaluar(self, problema: ProblemaOptimizacion, vector: Mapping[str, Any], politica_hash: str) -> dict:
        clave = clave_evaluacion(problema, vector, politica_hash)
        if clave in self._guardadas:
            self.cacheadas += 1
            return self._guardadas[clave]
        resultado = evaluar_vector(problema, vector)
        self.reales += 1
        self._guardadas[clave] = resultado
        return resultado
