"""075 — validación cruzada con las órdenes confirmadas por el operador.

Las confirmadas solo examinaban (070:RF-76) y el modelo nunca aprendió su estilo: 0,804 en la sellada y 0,500 en ellas
(2026-11-02). Aquí se reparten en 5 vueltas: cada una se examina con cabezas entrenadas sin ella. Con «como va el
avance», «como va el avnace» y «coma va enl avance» a cada lado de una vuelta se examinaría al modelo con lo que acaba
de leer: por eso se agrupan antes por familia. Agrupar de más solo resta entrenamiento; agrupar de menos falsea la medida.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import random
from typing import Any

from ..evaluacion_modelos import huella
from . import codificador_ordenes as co
from .maestro_real import clave_texto, con_erratas
from .sinteticos import CORTESIAS, Ejemplo

VUELTAS = 5
SEMILLA = 75
#: 075:RF-3, RF-4: declarados antes de medir, y no se ajustan mirando la medida fuera de grupo.
EDICIONES_FRASE, EDICIONES_PALABRA = .25, .34
LETRAS_PARA_ERRATA, PALABRAS_MINIMAS = 4, 2
#: 075:RF-14: fijado a priori: el doble que un texto de plata, y son decenas entre decenas de miles de filas.
REPETICIONES_CONFIRMADA, VARIANTES_CONFIRMADA = 8, 8
#: Un solo carácter: «datoalimentadores» haría parecidas «flujo de X» y «obras de X» solo por lo largo de la marca.
MARCA = '#'
_SIN_CONTENIDO = frozenset(('a al con de del el en la las lo los me para por que se un una y porfa favor gracias '
                            'hola oye dale').split())


def clave_de_familia(texto: str, datos: Iterable = ()) -> str:
    """El texto sin tildes ni signos, con sus datos y sus códigos marcados y sin la cortesía inicial (075:RF-2)."""
    trozos, cursor = [], 0
    for a, b, _tipo in sorted((tuple(d) for d in datos), key=lambda d: d[0]):
        trozos += [clave_texto(texto[cursor:a]), MARCA]
        cursor = b
    trozos.append(clave_texto(texto[cursor:]))
    clave = ' '.join(MARCA if any(c.isdigit() for c in p) else p for p in ' '.join(trozos).split())
    for cortesia in CORTESIAS:
        if clave.startswith(clave_texto(cortesia) + ' '):
            return clave[len(clave_texto(cortesia)) + 1:]
    return clave


def _ediciones(a: str, b: str, tope: int) -> int:
    """Quitar, poner, cambiar o cruzar dos letras contiguas: «avnace» está a una de «avance». Para al pasar del tope."""
    if abs(len(a) - len(b)) > tope:
        return tope + 1
    previa2, previa = [], list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        fila = [i]
        for j, y in enumerate(b, 1):
            fila.append(min(previa[j] + 1, fila[j - 1] + 1, previa[j - 1] + (x != y)))
            if i > 1 and j > 1 and x == b[j - 2] and a[i - 2] == y:
                fila[j] = min(fila[j], previa2[j - 2] + 1)
        if min(fila) > tope:
            return tope + 1
        previa2, previa = previa, fila
    return previa[-1]


@lru_cache(maxsize=1 << 18)
def _palabra_parecida(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < LETRAS_PARA_ERRATA:
        return False
    tope = int(EDICIONES_PALABRA * max(len(a), len(b)))
    return _ediciones(a, b, tope) <= tope


@lru_cache(maxsize=1 << 16)
def _con_contenido(clave: str) -> tuple[str, ...]:
    return tuple(sorted({p for p in clave.split() if p not in _SIN_CONTENIDO}))


def _contenida(a: Sequence[str], b: Sequence[str]) -> bool:
    return all(any(_palabra_parecida(x, y) for y in b) for x in a)


def misma_familia(a: str, b: str) -> bool:
    """Si dos claves son la misma orden, escrita igual, con erratas o con palabras de más (075:RF-2 a RF-4)."""
    if a == b:
        return True
    tope = int(EDICIONES_FRASE * max(len(a), len(b)))
    if tope and _ediciones(a, b, tope) <= tope:
        return True
    pa, pb = _con_contenido(a), _con_contenido(b)
    corta, larga = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
    return sum(p != MARCA for p in corta) >= PALABRAS_MINIMAS and _contenida(corta, larga)


class Claves:
    """Un conjunto de claves al que preguntar si otra es de su familia; muchas filas comparten clave y se recuerda."""

    def __init__(self, claves: Iterable[str]):
        self.claves, self._vistas = sorted(set(claves)), {}

    def toca(self, clave: str) -> bool:
        if clave not in self._vistas:
            self._vistas[clave] = any(misma_familia(clave, c) for c in self.claves)
        return self._vistas[clave]


def agrupar_familias(filas: Sequence[dict]) -> list[list[dict]]:
    """Las familias de las órdenes; ser de la misma familia es transitivo (075:RF-1, RF-5)."""
    claves = [clave_de_familia(r['texto'], r.get('datos') or ()) for r in filas]
    padre = list(range(len(filas)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i in range(len(filas)):
        for j in range(i):
            if raiz(i) != raiz(j) and misma_familia(claves[i], claves[j]):
                padre[raiz(i)] = raiz(j)
    grupos: dict[int, list[dict]] = {}
    for i, r in enumerate(filas):
        grupos.setdefault(raiz(i), []).append(r)
    return list(grupos.values())


def _identidad(familia: Sequence[dict]) -> str:
    return huella(sorted(clave_de_familia(r['texto'], r.get('datos') or ()) for r in familia))


def repartir_en_vueltas(familias: Sequence[Sequence[dict]], k: int = VUELTAS, semilla: int = SEMILLA) -> list[list[list[dict]]]:
    """Cada familia a una vuelta, equilibrando sus tareas; la semilla solo desempata (075:RF-6 a RF-8).

    El desempate sale de la familia y no de su orden de llegada.
    """
    def desempate(identidad: str, vuelta: int) -> str:
        return hashlib.sha256(f'{semilla}:{identidad}:{vuelta}'.encode('utf-8')).hexdigest()

    vueltas: list[list[list[dict]]] = [[] for _ in range(k)]
    por_tarea, total = [Counter() for _ in range(k)], [0] * k
    # Primero las grandes y, en cada tamaño, las de tareas con menos familias: son las que se quedarían sin hueco.
    frecuencia = Counter(t for f in familias for t in {r['tarea'] for r in f})
    orden = sorted(familias, key=lambda f: (-len(f), min(frecuencia[r['tarea']] for r in f), _identidad(f)))
    for familia in orden:
        tareas, identidad = Counter(r['tarea'] for r in familia), _identidad(familia)
        i = min(range(k), key=lambda v: (sum(por_tarea[v][t] for t in tareas), total[v], desempate(identidad, v)))
        vueltas[i].append(list(familia))
        por_tarea[i].update(tareas)
        total[i] += len(familia)
    return vueltas


def filas_entrenables(humanas: Sequence[dict], vedadas: Claves) -> tuple[list[dict], list[dict]]:
    """Las confirmadas que pueden entrenar y las que no, por chocar con lo que mide (075:RF-28)."""
    si, no = [], []
    for r in humanas:
        (no if vedadas.toca(clave_de_familia(r['texto'], r.get('datos') or ())) else si).append(r)
    return si, no


def ejemplos_de_confirmadas(filas: Sequence[dict]) -> list[Ejemplo]:
    """Cada confirmada repetida y con variantes de erratas, con el dato intacto; deterministas por su texto (075:RF-14)."""
    salida = []
    for r in sorted(filas, key=lambda f: clave_texto(f['texto'])):
        e = Ejemplo(r['texto'], r['tarea'], [tuple(d) for d in r.get('datos') or ()])
        rnd = random.Random(int(huella({'erratas_confirmada': clave_texto(e.texto)})[:8], 16))
        salida += [e] * REPETICIONES_CONFIRMADA
        salida += [con_erratas(e, rnd) for _ in range(VARIANTES_CONFIRMADA)]
    return salida


def _ejemplos_de(filas: Sequence[dict]) -> list[Ejemplo]:
    return [Ejemplo(r['texto'], r['tarea'], [tuple(d) for d in r['datos']]) for r in filas]


def estado_por_tarea(familias: Sequence[Sequence[dict]], entrenables: Sequence[dict]) -> dict[str, dict]:
    """Por tarea, sus textos y sus familias, y por qué no puede aprender de sí misma si es el caso (075:RF-23)."""
    pueden = {id(r) for r in entrenables}
    textos, todas, utiles = Counter(), Counter(), Counter()
    for familia in familias:
        for tarea in {r['tarea'] for r in familia}:
            todas[tarea] += 1
            utiles[tarea] += any(r['tarea'] == tarea and id(r) in pueden for r in familia)
        textos.update(r['tarea'] for r in familia)
    salida = {}
    for tarea in sorted(textos):
        d = {'textos': textos[tarea], 'familias': todas[tarea], 'familias_que_entrenan': utiles[tarea], 'estado': 'medida', 'motivo': ''}
        if utiles[tarea] < 2:
            d['estado'] = 'sin_independencia'
            d['motivo'] = ('un solo texto: al examinarlo no queda ninguna orden de esta tarea para aprender' if textos[tarea] == 1 else
                           'una sola familia de textos casi iguales: se examinan todos juntos' if todas[tarea] == 1 else
                           'de sus familias, menos de dos pueden entrenar: las demás chocan con lo que mide')
        salida[tarea] = d
    return salida


@dataclass
class FueraDeGrupo:
    """Lo que dijo de cada orden el modelo entrenado sin ella: se mide con el mismo código que un modelo (075:RF-17)."""
    predicciones: dict[str, dict[str, Any]]

    def predecir(self, texto: str) -> dict[str, Any]:
        return self.predicciones[texto]


@dataclass
class Validacion:
    medida: FueraDeGrupo | None
    modelo_final: Any
    informe: dict[str, Any]
    por_tarea: dict[str, dict]


def _clave_de_fila(r: dict) -> str:
    return clave_de_familia(r['texto'], r.get('datos') or ())


def ejecutar(humanas: Sequence[dict], entrenamiento: Sequence[dict], vedadas: Iterable[str], *, cfg: co.Configuracion,
             cache: co.CacheCodificada, dispositivo, k: int = VUELTAS, semilla: int = SEMILLA,
             liberar: Callable[[], None] = lambda: None, log: Callable[[str], None] = lambda _m: None) -> Validacion:
    """Las vueltas y el modelo final; de ``entrenamiento`` y de las confirmadas solo se entrena lo que no toca lo examinado."""
    vedado = Claves(vedadas)
    entrenables, apartadas = filas_entrenables(humanas, vedado)
    familias = agrupar_familias(humanas)
    por_tarea = estado_por_tarea(familias, entrenables)
    con_variantes = {r['record_id']: ejemplos_de_confirmadas([r]) for r in entrenables}
    variantes_vedadas = 0
    for rid, ejemplos in con_variantes.items():
        fuera = [e for e in ejemplos if not vedado.toca(clave_de_familia(e.texto, e.datos))]
        variantes_vedadas += len(ejemplos) - len(fuera)
        con_variantes[rid] = fuera
    informe = {'vueltas_pedidas': k, 'semilla': semilla, 'textos': len(humanas), 'familias': len(familias),
               'confirmadas_que_entrenan': len(entrenables), 'confirmadas_que_no_entrenan': len(apartadas),
               'variantes_apartadas_por_lo_que_mide': variantes_vedadas, 'por_tarea': por_tarea,
               'familias_detalle': sorted(({'familia': _identidad(f), 'textos': len(f), 'tareas': dict(Counter(r['tarea'] for r in f))} for f in familias),
                                          key=lambda d: d['familia'])}

    def final() -> Any:
        ejemplos = [*_ejemplos_de(entrenamiento), *(e for r in entrenables for e in con_variantes[r['record_id']])]
        log(f'modelo final: {len(ejemplos)} filas, {len(entrenables)} confirmadas')
        return co.entrenar(ejemplos, cfg, log=log, cache=cache, dispositivo=dispositivo)

    if len(familias) < k:
        informe.update(medida=False, motivo=f'hay {len(familias)} familias de órdenes confirmadas para {k} vueltas')    # 075:RF-9
        return Validacion(None, final(), informe, por_tarea)
    vueltas = repartir_en_vueltas(familias, k, semilla)
    informe['reparto_huella'] = huella([sorted(_identidad(f) for f in v) for v in vueltas])
    predicciones: dict[str, dict] = {}
    claves_plata = {id(r): _clave_de_fila(r) for r in entrenamiento}
    resumen = []
    for i, vuelta in enumerate(vueltas):
        examen = [r for f in vuelta for r in f]
        tocadas = Claves(_clave_de_fila(r) for r in examen)
        filas = [r for r in entrenamiento if not tocadas.toca(claves_plata[id(r)])]             # 075:RF-12
        en_examen = {r['record_id'] for r in examen}
        otras = [r for r in entrenables if r['record_id'] not in en_examen]
        variantes = []
        for r in otras:
            variantes += [e for e in con_variantes[r['record_id']] if not tocadas.toca(clave_de_familia(e.texto, e.datos))]    # 075:RF-13
        ejemplos = [*_ejemplos_de(filas), *variantes]
        log(f'vuelta {i + 1} de {k}: examina {len(examen)} órdenes de {len(vuelta)} familias, entrena {len(ejemplos)} filas')
        modelo = co.entrenar(ejemplos, cfg, log=log, cache=cache, dispositivo=dispositivo)
        for r in examen:
            predicciones[r['texto']] = modelo.predecir(r['texto'])
        presentes = {e.tarea for e in ejemplos}
        resumen.append({'vuelta': i + 1, 'examinadas': len(examen), 'familias': len(vuelta), 'confirmadas_que_entrenan': len(otras),
                        'filas_que_entrenan': len(ejemplos), 'plata_apartada': len(entrenamiento) - len(filas),
                        'tareas_sin_filas': sorted(set(co.tareas_del_modelo()) - presentes)})
        del modelo
        liberar()
    informe.update(medida=True, vueltas=resumen)
    return Validacion(FueraDeGrupo(predicciones), final(), informe, por_tarea)


def resumen_por_tarea(medida_por_tarea: dict[str, dict], estados: dict[str, dict], *, acierto_minimo: float, f1_minimo: float) -> dict[str, dict]:
    """Por tarea, lo medido con su denominador; a la que no puede aprender de sí misma no se le da visto bueno (075:RF-19, RF-24)."""
    salida = {}
    for tarea, m in sorted(medida_por_tarea.items()):
        estado = estados[tarea]
        cumple = None if estado['estado'] == 'sin_independencia' else bool(m['acierto_tarea'] >= acierto_minimo and m['f1_datos'] >= f1_minimo)
        salida[tarea] = {**estado, 'acierto_tarea': m['acierto_tarea'], 'f1_datos': m['f1_datos'], 'ejemplos': m['ejemplos'], 'cumple': cumple}
    return salida
