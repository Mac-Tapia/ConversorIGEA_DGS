"""Clasificador de informes por vectores de un codificador preentrenado (spec 026, RF-36 a RF-41).

La segunda arquitectura del clasificador, elegible al entrenar; la red por símbolos de ``clasificador.py`` sigue
(nada se quita). El 2026-11-11 el modelo en uso acertaba 0,7 el tipo y 0,6 el subtipo en los 10 informes reales de la
prueba: aprende de frases de plantilla y un informe real son miles de caracteres de otra forma. Un prototipo con los
vectores de ``intfloat/multilingual-e5-base`` (la revisión fija de las órdenes) y una regresión logística dio, con un
grupo fuera sobre los 50 informes, 0,96 el tipo y 0,90 el par tipo|subtipo.

Rasgos de un informe: el vector del primer trozo (dice el asunto) y la media de los trozos, de ventanas de
``TROZO`` caracteres de los primeros ``LEIDO``. El subtipo suma el vector de la línea ASUNTO: en los informes reales es la
frase que nombra el estudio («ASUNTO: estudio de mejora de tensión…»). Cada nivel tiene su regresión logística; las
plantillas entran con un peso bajo porque solo dan forma a los subtipos sin informes reales.

Se guarda sin código serializado: coeficientes e interceptos en ``pesos.npz`` (se lee con ``allow_pickle=False``) y el
nombre y la revisión del codificador en ``modelo.json``. Los vectores se recalculan al abrir con esa misma revisión.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..contratos_aprendizaje import TIPOS_INFORME
from .sinteticos import normalizar

ARQUITECTURA = 'vectores_e5_logistica_v1'
#: Ventanas del informe: 1200 caracteres caben en los 512 símbolos del codificador; los primeros 6000 bastan para el
#: asunto y la introducción, que es donde un informe dice qué estudia (los anexos repiten tablas de todos los tipos).
TROZO = 1200
LEIDO = 6000
LARGO_PASAJE = 512
LARGO_ASUNTO = 128
PREFIJO_PASAJE = 'passage: '
PREFIJO_ASUNTO = 'query: '
MAX_ITER = 3000
PLANTILLAS_POR_SUBTIPO = 40
#: Otra semilla que la de la prueba (7919): las plantillas de entrenamiento no repiten las de la prueba mezclada.
SEMILLA_PLANTILLAS = 3
SEPARADOR = '|'
_ASUNTO = re.compile(r'asunto\s*:?\s*(.{0,300})', re.IGNORECASE)
#: Lo que fija los vectores; un modelo guardado con otros valores daría otros vectores para los mismos pesos (RF-38).
RASGOS = {'trozo': TROZO, 'leido': LEIDO, 'largo_pasaje': LARGO_PASAJE, 'largo_asunto': LARGO_ASUNTO,
          'prefijo_pasaje': PREFIJO_PASAJE, 'prefijo_asunto': PREFIJO_ASUNTO}
_MATRICES = ('tipo_coef', 'tipo_intercepto', 'subtipo_coef', 'subtipo_intercepto')
_TEXTOS_REAPERTURA = ('estudio de refuerzo de red', 'factibilidad de una carga nueva',
                      'ASUNTO: estudio de mejora de tensión en el alimentador')


@dataclass(frozen=True)
class Hiper:
    """Regularización (``C``) y peso de cada plantilla frente a un informe real."""
    C: float = 50.0
    peso_plantillas: float = 0.15


#: La del prototipo del 2026-11-11, y la que gana un empate al elegir (026:RF-40); si no, la primera de la rejilla,
#: la más regularizada.
PREFERIDO = Hiper()
#: Hasta C=1000: con los 27 grupos de entrenamiento del 2026-11-11, el tipo con un grupo fuera subía de 0,975 con C=50
#: a 1,0 con C=200 y C=1000, y bajaba con C=10000 el par tipo|subtipo (0,925 a 0,875).
REJILLA = tuple(Hiper(c, p) for c in (1.0, 10.0, 50.0, 200.0, 1000.0) for p in (0.15, 0.3, 0.6))


def asunto(texto: str) -> str:
    """La línea ASUNTO del informe; sin ella, su comienzo (los pedidos cortos no la traen)."""
    t = ' '.join(texto.split())
    m = _ASUNTO.search(t)
    return m.group(1) if m else t[:300]


def trozos_de_pasaje(texto: str) -> list[str]:
    t = ' '.join(texto.split())
    return [t[i:i + TROZO] for i in range(0, min(len(t), LEIDO), TROZO)] or ['']


class Vectorizador:
    """Los vectores del codificador congelado de las órdenes, con otro prefijo y otro largo.

    Usa el mismo codificador abierto del proceso (``obtener_codificador``): 1,1 GB de GPU no se repiten. Un informe se
    vectoriza solo, nunca en lote con otros: el relleno de un lote cambiaría sus vectores en las últimas cifras y la
    reapertura no daría lo mismo.
    """

    def __init__(self, nombre: str, revision: str, dispositivo=None):
        from . import codificador_ordenes
        from .transformer import dispositivo_de_calculo

        self.base = codificador_ordenes.obtener_codificador(nombre, revision, dispositivo or dispositivo_de_calculo())
        self.nombre, self.revision = nombre, revision

    def _medias(self, textos: Sequence[str], prefijo: str, largo: int) -> np.ndarray:
        import torch

        lote = self.base.tokenizador([prefijo + t for t in textos], padding=True, truncation=True, max_length=largo,
                                     return_tensors='pt')
        lote = {k: v.to(self.base.dispositivo) for k, v in lote.items()}
        with torch.no_grad():
            h = self.base.red(**lote).last_hidden_state
        m = lote['attention_mask'].unsqueeze(-1).to(h.dtype)
        v = torch.nn.functional.normalize((h * m).sum(1) / m.sum(1), dim=-1)
        return v.double().cpu().numpy()

    def informe(self, texto: str) -> np.ndarray:
        v = self._medias(trozos_de_pasaje(texto), PREFIJO_PASAJE, LARGO_PASAJE)
        return np.concatenate([v[0], v.mean(0)])

    def asunto(self, texto: str) -> np.ndarray:
        return self._medias([asunto(texto)], PREFIJO_ASUNTO, LARGO_ASUNTO)[0]


#: Se cambia en las pruebas por uno sin GPU, como ``codificador_ordenes.FABRICA``.
FABRICA: Callable[[str, str], Any] = Vectorizador
_abiertos: dict[tuple, Any] = {}


def obtener_vectorizador(nombre: str, revision: str):
    clave = (FABRICA, nombre, revision)
    if clave not in _abiertos:
        _abiertos[clave] = FABRICA(nombre, revision)
    return _abiertos[clave]


def codificador_por_defecto() -> tuple[str, str]:
    from .codificador_ordenes import CODIFICADORES

    return CODIFICADORES['base']


def rasgos(vectorizador, textos: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    """Matrices del tipo (cuerpo) y del subtipo (cuerpo y asunto), una fila por texto."""
    cuerpo = np.stack([np.asarray(vectorizador.informe(t), dtype=np.float64) for t in textos])
    asuntos = np.stack([np.asarray(vectorizador.asunto(t), dtype=np.float64) for t in textos])
    return cuerpo, np.hstack([cuerpo, asuntos])


@dataclass
class Logistica:
    """Una regresión logística como números: se aplica sin scikit-learn y se guarda sin pickle."""
    clases: list[str]
    coef: np.ndarray
    intercepto: np.ndarray

    def probabilidades(self, x: np.ndarray) -> np.ndarray:
        x = np.atleast_2d(np.asarray(x, dtype=np.float64))
        if len(self.clases) == 1:
            return np.ones((len(x), 1))
        z = x @ self.coef.T + self.intercepto
        if self.coef.shape[0] == 1:                       # binaria: scikit-learn guarda una fila, la de la segunda clase
            p = 1.0 / (1.0 + np.exp(-z[:, 0]))
            return np.stack([1.0 - p, p], axis=1)
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)


def ajustar(x: np.ndarray, y: Sequence[str], pesos: Sequence[float], hiper: Hiper) -> Logistica:
    clases = sorted(set(y))
    if len(clases) == 1:                                  # un único tipo en los datos: no hay nada que separar
        return Logistica(clases, np.zeros((1, x.shape[1])), np.zeros(1))
    from sklearn.linear_model import LogisticRegression

    clf = LogisticRegression(max_iter=MAX_ITER, C=hiper.C).fit(x, list(y), sample_weight=np.asarray(pesos, float))
    return Logistica([str(c) for c in clf.classes_], np.array(clf.coef_, dtype=np.float64),
                     np.array(clf.intercept_, dtype=np.float64))


def _etiqueta(tipo: str, subtipo: str) -> str:
    return f'{tipo}{SEPARADOR}{subtipo}'


@dataclass
class ClasificadorVectores:
    tipo: Logistica
    subtipo: Logistica                      # clases «tipo|subtipo», como se midió el prototipo
    subtipos: list[str]
    codificador: dict[str, str]
    hiper: dict[str, dict[str, float]]
    version: str = ''
    vectorizador: Any = field(default=None, repr=False)

    def _vec(self):
        if self.vectorizador is None:
            self.vectorizador = obtener_vectorizador(self.codificador['nombre'], self.codificador['revision'])
        return self.vectorizador

    def clasificar(self, texto: str) -> dict[str, Any]:
        cuerpo, con_asunto = rasgos(self._vec(), [texto])
        pt = self.tipo.probabilidades(cuerpo)[0]
        ps = self.subtipo.probabilidades(con_asunto)[0]
        orden = [int(i) for i in np.argsort(-ps, kind='stable')]
        sub = lambda i: self.subtipo.clases[i].split(SEPARADOR, 1)[-1]  # noqa: E731
        alternativas: list[tuple[str, float]] = []
        for i in orden[1:]:
            if sub(i) != sub(orden[0]) and sub(i) not in [a for a, _ in alternativas]:
                alternativas.append((sub(i), float(ps[i])))
            if len(alternativas) == 2:
                break
        it = int(np.argmax(pt))
        return {'tipo': self.tipo.clases[it], 'confianza_tipo': float(pt[it]), 'subtipo': sub(orden[0]),
                'confianza_subtipo': float(ps[orden[0]]), 'alternativas': alternativas, 'version': self.version,
                'arquitectura': ARQUITECTURA}


def _datos(filas: Sequence[tuple[str, str, str]]) -> tuple[list[str], list[str], list[str]]:
    return [t for t, _tp, _s in filas], [tp for _t, tp, _s in filas], [_etiqueta(tp, s) for _t, tp, s in filas]


def ajustar_niveles(xc, xa, yt, ys, pesos_reales: int, xpc, xpa, ypt, yps, ht: Hiper, hs: Hiper
                    ) -> tuple[Logistica, Logistica]:
    """Las dos regresiones; las plantillas al final, con el peso de cada nivel."""
    def uno(x, xp, y, yp, h):
        if len(xp):
            x, y = np.vstack([x, xp]), list(y) + list(yp)
        return ajustar(x, y, [1.0] * pesos_reales + [h.peso_plantillas] * len(yp), h)
    return uno(xc, xpc, yt, ypt, ht), uno(xa, xpa, ys, yps, hs)


def validacion_por_grupo(x: np.ndarray, y: Sequence[str], grupos: Sequence[str], xp: np.ndarray, yp: Sequence[str],
                         hiper: Hiper) -> float:
    """026:RF-40: acierto con un grupo fuera; cada grupo se predice con un modelo que no vio ninguna de sus versiones."""
    if len(set(grupos)) < 2:
        return float('nan')
    aciertos = 0
    for g in sorted(set(grupos)):
        fuera = [i for i, gi in enumerate(grupos) if gi == g]
        dentro = [i for i, gi in enumerate(grupos) if gi != g]
        xs, ys = x[dentro], [y[i] for i in dentro]
        if len(xp):
            xs, ys = np.vstack([xs, xp]), ys + list(yp)
        modelo = ajustar(xs, ys, [1.0] * len(dentro) + [hiper.peso_plantillas] * len(yp), hiper)
        p = modelo.probabilidades(x[fuera]).argmax(axis=1)
        aciertos += sum(modelo.clases[int(k)] == y[i] for k, i in zip(p, fuera, strict=True))
    return aciertos / len(y)


def elegir(x, y, grupos, xp, yp, rejilla: Sequence[Hiper] = REJILLA, log: Callable[[str], None] = lambda _m: None
           ) -> tuple[Hiper, dict[str, float]]:
    """026:RF-40: la mejor de la rejilla con un grupo fuera sobre los grupos de entrenamiento; empate, la preferida.

    Solo recibe los de entrenamiento: la prueba fija no participa en la elección.
    """
    medidas = {f'C={h.C:g},peso={h.peso_plantillas:g}': validacion_por_grupo(x, y, grupos, xp, yp, h) for h in rejilla}
    for k, v in medidas.items():
        log(f'  grupo fuera {k}: {v:.3f}')
    valida = [(h, medidas[f'C={h.C:g},peso={h.peso_plantillas:g}']) for h in rejilla]
    valida = [(h, v) for h, v in valida if v == v]
    if not valida:
        return PREFERIDO, medidas
    mejor = max(v for _h, v in valida)
    empatados = [h for h, v in valida if abs(v - mejor) < 1e-12]
    return (PREFERIDO if PREFERIDO in empatados else empatados[0]), medidas


def entrenar(reales: Sequence[tuple[str, str, str, str]], plantillas: Sequence[tuple[str, str, str]],
             subtipos: Sequence[str], *, vectorizador=None, elegir_hiper: bool = True,
             log: Callable[[str], None] = lambda _m: None) -> tuple[ClasificadorVectores, dict[str, Any]]:
    """Entrena con los informes reales de entrenamiento ``(texto, tipo, subtipo, grupo)`` y las plantillas.

    Devuelve el modelo y lo medido al elegir: el acierto con un grupo fuera de cada nivel y la configuración elegida.
    """
    nombre, revision = codificador_por_defecto()
    if vectorizador is None:
        from .transformer import liberar_gpu

        liberar_gpu()
        vectorizador = obtener_vectorizador(nombre, revision)
    nombre, revision = getattr(vectorizador, 'nombre', nombre), getattr(vectorizador, 'revision', revision)
    textos, yt, ys = _datos([(t, tp, s) for t, tp, s, _g in reales])
    grupos = [g for *_r, g in reales]
    ptextos, ypt, yps = _datos(plantillas)
    log(f'Clasificador de vectores: {len(textos)} informes reales y {len(ptextos)} plantillas')
    if not textos and not ptextos:
        raise ValueError('sin informes ni plantillas: no hay nada con qué entrenar el clasificador')
    todos_c, todos_a = rasgos(vectorizador, textos + ptextos)
    n = len(textos)
    xc, xa, xpc, xpa = todos_c[:n], todos_a[:n], todos_c[n:], todos_a[n:]
    info: dict[str, Any] = {'grupos_entrenamiento': len(set(grupos)), 'informes_entrenamiento': len(textos),
                            'plantillas': len(ptextos)}
    ht = hs = PREFERIDO
    if elegir_hiper and len(set(grupos)) >= 2:
        ht, mt = elegir(xc, yt, grupos, xpc, ypt, log=log)
        hs, ms = elegir(xa, ys, grupos, xpa, yps, log=log)
        info['grupo_fuera'] = {'tipo': mt, 'tipo|subtipo': ms}
        info['grupo_fuera_elegido'] = {'tipo': mt[f'C={ht.C:g},peso={ht.peso_plantillas:g}'],
                                       'tipo|subtipo': ms[f'C={hs.C:g},peso={hs.peso_plantillas:g}']}
    info['hiper'] = {'tipo': asdict(ht), 'subtipo': asdict(hs)}
    lt, ls = ajustar_niveles(xc, xa, yt, ys, len(textos), xpc, xpa, ypt, yps, ht, hs)
    modelo = ClasificadorVectores(lt, ls, list(subtipos), {'nombre': nombre, 'revision': revision},
                                  info['hiper'], vectorizador=vectorizador)
    return modelo, info


def guardar(modelo: ClasificadorVectores, carpeta: Path) -> None:
    """026:RF-37: matrices en ``pesos.npz``, todo lo demás en JSON; con las predicciones para la reapertura."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=False)
    np.savez(carpeta / 'pesos.npz', tipo_coef=modelo.tipo.coef, tipo_intercepto=modelo.tipo.intercepto,
             subtipo_coef=modelo.subtipo.coef, subtipo_intercepto=modelo.subtipo.intercepto)
    (carpeta / 'modelo.json').write_text(json.dumps({
        'arquitectura': ARQUITECTURA, 'version': carpeta.name, 'codificador': modelo.codificador, 'rasgos': RASGOS,
        'hiper': modelo.hiper, 'clases_tipo': modelo.tipo.clases, 'clases_subtipo': modelo.subtipo.clases,
        'subtipos': modelo.subtipos, 'tipos': list(TIPOS_INFORME)}, ensure_ascii=False, indent=1), encoding='utf-8')
    (carpeta / 'readback.json').write_text(json.dumps({
        'textos': list(_TEXTOS_REAPERTURA), 'predicciones': [modelo.clasificar(t) for t in _TEXTOS_REAPERTURA]},
        ensure_ascii=False), encoding='utf-8')


def abrir(carpeta: Path, version: str = '', vectorizador=None) -> ClasificadorVectores:
    """026:RF-38: rechaza un modelo de otra arquitectura, con otros rasgos o con matrices que no cuadran."""
    carpeta = Path(carpeta)
    meta = json.loads((carpeta / 'modelo.json').read_text(encoding='utf-8'))
    if meta.get('arquitectura') != ARQUITECTURA:
        raise ValueError(f"el modelo es de la arquitectura {meta.get('arquitectura')!r}, no {ARQUITECTURA}")
    if meta.get('rasgos') != RASGOS:
        raise ValueError(f"el modelo se guardó con otros rasgos ({meta.get('rasgos')}); con los de ahora ({RASGOS}) "
                         'sus pesos no valen')
    cod = meta.get('codificador') or {}
    if not cod.get('nombre') or not cod.get('revision'):
        raise ValueError('el modelo no dice el nombre y la revisión de su codificador')
    with np.load(carpeta / 'pesos.npz', allow_pickle=False) as npz:
        if set(npz.files) != set(_MATRICES):
            raise ValueError(f'pesos.npz trae {sorted(npz.files)} y no {sorted(_MATRICES)}')
        m = {k: np.array(npz[k], dtype=np.float64) for k in _MATRICES}
    for nivel, clases in (('tipo', meta['clases_tipo']), ('subtipo', meta['clases_subtipo'])):
        coef, inter = m[f'{nivel}_coef'], m[f'{nivel}_intercepto']
        filas = 1 if len(clases) <= 2 else len(clases)
        if coef.ndim != 2 or coef.shape[0] != filas or inter.shape != (filas,) or not np.isfinite(coef).all():
            raise ValueError(f'las matrices del {nivel} no cuadran con sus {len(clases)} clases')
    return ClasificadorVectores(Logistica(list(meta['clases_tipo']), m['tipo_coef'], m['tipo_intercepto']),
                                Logistica(list(meta['clases_subtipo']), m['subtipo_coef'], m['subtipo_intercepto']),
                                list(meta['subtipos']), {'nombre': cod['nombre'], 'revision': cod['revision']},
                                meta.get('hiper') or {}, version or meta.get('version', ''), vectorizador)


def verificar_reapertura(carpeta: Path) -> dict[str, Any]:
    """Reabierto en un proceso nuevo, da lo mismo que al guardarlo (la tolerancia cubre el redondeo de la GPU)."""
    carpeta = Path(carpeta)
    prueba = json.loads((carpeta / 'readback.json').read_text(encoding='utf-8'))
    modelo = abrir(carpeta)
    obtenidas = [modelo.clasificar(t) for t in prueba['textos']]
    iguales = all(a['tipo'] == b['tipo'] and normalizar(a['subtipo']) == normalizar(b['subtipo'])
                  and abs(a['confianza_subtipo'] - b['confianza_subtipo']) < 1e-5
                  and abs(a['confianza_tipo'] - b['confianza_tipo']) < 1e-5
                  for a, b in zip(obtenidas, prueba['predicciones'], strict=True))
    return {'ok': iguales, 'ejemplos': len(obtenidas), 'proceso_nuevo': True, 'arquitectura': ARQUITECTURA}
