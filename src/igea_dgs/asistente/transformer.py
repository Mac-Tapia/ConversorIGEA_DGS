"""Transformer propio del asistente: entiende las órdenes escritas (spec 026, RF-2, RF-19, RF-20).

Un codificador Transformer pequeño sobre caracteres, no sobre palabras: las órdenes
llegan con erratas y los nombres de la red (IN111, 20261015-170359_IGEA_IN111_TA225,
SE41154) no están en ningún vocabulario, pero tienen forma. Dos salidas: la tarea, sobre
el primer símbolo, y una etiqueta por carácter (B-tipo, I-tipo, O) que marca cada dato.

Se entrena en la GPU con los ejemplos sintéticos (RF-21) y las órdenes que el operador
confirmó o corrigió (RF-19); se registra con lo que lo hizo y solo se promueve si acierta
más que el modelo en uso en un conjunto de prueba fijo (RF-20), como el oráculo de la 024.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import almacen
from .sinteticos import Ejemplo, normalizar
from .tareas import TAREAS, TIPOS_DATO

LARGO_MAX = 192
ETIQUETAS = ('O',) + tuple(f'{p}-{t}' for t in TIPOS_DATO for p in ('B', 'I'))
PAD, DESCONOCIDO, INICIO = 0, 1, 2
#: Semilla del conjunto de prueba fijo: el mismo para el candidato y el modelo en uso (RF-20).
SEMILLA_PRUEBA = 9973


@dataclass
class Configuracion:
    dim: int = 128
    capas: int = 4
    cabezas: int = 4
    epocas: int = 24
    lote: int = 64
    lr: float = 1e-3
    semilla: int = 0
    por_tarea: int = 150


@dataclass
class Puertas:
    acierto_tarea: float = 0.95
    f1_datos: float = 0.85
    #: 027:RF-18: en las órdenes reales de la prueba fija, aparte de las sintéticas.
    acierto_real: float = 0.98
    f1_real: float = 0.95


def _torch():
    import torch

    return torch


def _dispositivo():
    from ..digital_twin.oraculo import dispositivo

    return dispositivo()


def liberar_gpu() -> None:
    """Antes de entrenar, que Ollama suelte la GPU que comparte con este modelo y la PINN."""
    from .ollama import liberar_gpu_para_entrenar

    liberar_gpu_para_entrenar()


def alfabeto(textos: Sequence[str]) -> list[str]:
    """Los caracteres de los textos normalizados, en orden fijo (determinista)."""
    return sorted({c for t in textos for c in normalizar(t)})


def construir_red(n_simbolos: int, salidas: dict[str, int], cfg: Configuracion, etiquetas: int = 0):
    """Codificador Transformer con una cabeza por salida de clase y, si ``etiquetas``, otra por carácter."""
    torch = _torch()
    nn = torch.nn

    class Red(nn.Module):
        def __init__(self):
            super().__init__()
            self.simbolos = nn.Embedding(n_simbolos, cfg.dim, padding_idx=PAD)
            self.posicion = nn.Embedding(LARGO_MAX + 1, cfg.dim)
            capa = nn.TransformerEncoderLayer(cfg.dim, cfg.cabezas, 2 * cfg.dim, dropout=0.1,
                                              batch_first=True, norm_first=True)
            self.codificador = nn.TransformerEncoder(capa, cfg.capas, enable_nested_tensor=False)
            self.cabezas = nn.ModuleDict({k: nn.Linear(cfg.dim, n) for k, n in salidas.items()})
            self.etiquetas = nn.Linear(cfg.dim, etiquetas) if etiquetas else None

        def forward(self, ids):
            pos = torch.arange(ids.shape[1], device=ids.device).unsqueeze(0)
            h = self.codificador(self.simbolos(ids) + self.posicion(pos), src_key_padding_mask=ids == PAD)
            clases = {k: c(h[:, 0]) for k, c in self.cabezas.items()}
            return clases, (self.etiquetas(h[:, 1:]) if self.etiquetas is not None else None)

    return Red()


def codificar(textos: Sequence[str], simbolos: dict[str, int]) -> list[list[int]]:
    return [[INICIO] + [simbolos.get(c, DESCONOCIDO) for c in normalizar(t)[:LARGO_MAX]] for t in textos]


def lotes(n: int, tam: int, rnd: random.Random) -> list[list[int]]:
    orden = list(range(n))
    rnd.shuffle(orden)
    return [orden[i:i + tam] for i in range(0, n, tam)]


def rellenar(filas: Sequence[Sequence[int]], valor: int = PAD):
    torch = _torch()
    largo = max(len(f) for f in filas)
    return torch.tensor([list(f) + [valor] * (largo - len(f)) for f in filas], dtype=torch.long)


def _etiquetas_de(e: Ejemplo) -> list[int]:
    idx = {t: i for i, t in enumerate(ETIQUETAS)}
    out = [0] * min(len(e.texto), LARGO_MAX)
    for a, b, tipo in e.datos:
        for i in range(a, min(b, LARGO_MAX)):
            out[i] = idx[f'{"B" if i == a else "I"}-{tipo}']
    return out


@dataclass
class ModeloOrdenes:
    """El Transformer entrenado con su alfabeto y sus tareas."""

    red: Any
    simbolos: dict[str, int]
    tareas: list[str]
    cfg: Configuracion
    version: str = ''

    def predecir(self, texto: str) -> dict[str, Any]:
        """Tarea con su confianza y los datos marcados, cada uno con la suya."""
        torch = _torch()
        disp = next(self.red.parameters()).device
        ids = rellenar(codificar([texto], self.simbolos)).to(disp)
        self.red.eval()
        with torch.no_grad():
            clases, etq = self.red(ids)
        p = torch.softmax(clases['tarea'][0], -1).cpu()
        orden = torch.argsort(p, descending=True)[:3].tolist()
        datos = _spans(texto, torch.softmax(etq[0], -1).cpu().numpy())
        return {'tarea': self.tareas[orden[0]], 'confianza': float(p[orden[0]]),
                'alternativas': [(self.tareas[i], float(p[i])) for i in orden[1:]],
                'datos': datos, 'modelo': 'transformer', 'version': self.version}


#: Palabras de unión que el etiquetado arrastra a los bordes de un dato («pisco con»,
#: «en IN111 del proyecto», 2026-10-24); dentro de una lista («IN111 y TA225») se quedan.
_UNION = {'de', 'del', 'en', 'con', 'para', 'la', 'el', 'los', 'las', 'y', 'a', 'al', 'proyecto',
          'alimentador', 'alimentadores', 'sistema', 'sed', 'desde', 'entre', 'por'}


def _recortar(valor: str) -> str:
    palabras = valor.strip(' ,.;:¿?¡!"\'').split()
    while palabras and normalizar(palabras[0]).strip(',.') in _UNION:
        palabras.pop(0)
    while palabras and normalizar(palabras[-1]).strip(',.') in _UNION:
        palabras.pop()
    return ' '.join(palabras).strip(' ,.;:¿?¡!"\'')


def _spans(texto: str, probabilidades) -> dict[str, list[dict]]:
    """Los datos, decididos por palabra: cada palabra toma el tipo que votan sus caracteres.

    Los datos son palabras enteras (IN111, «CA101 13», «julio de 2026»). Etiquetando
    carácter a carácter salían trozos como «C» y «101» de CA101 (F1 de 0,13 en la prueba
    fija, 2026-10-24); con el voto por palabra, el dato sale entero o no sale.
    """
    palabras = []
    for m in re.finditer(r'\S+', texto[:LARGO_MAX]):
        a, b = m.span()
        votos = probabilidades[a:b].sum(0)
        k = int(votos.argmax())
        nombre = ETIQUETAS[k]
        tipo = None if nombre == 'O' else nombre[2:]
        if tipo is not None:
            # El voto del tipo junta B e I; la confianza es la media de lo que no es O.
            idx = [i for i, e in enumerate(ETIQUETAS) if e[2:] == tipo]
            por_tipo = float(probabilidades[a:b][:, idx].sum(-1).mean())
            if por_tipo < 0.5:
                tipo = None
        palabras.append((a, b, tipo, float(1 - probabilidades[a:b][:, 0].mean()), nombre.startswith('B-')))
    out: dict[str, list[dict]] = {}
    actual = None
    for a, b, tipo, conf, empieza in palabras + [(len(texto), len(texto), None, 0.0, False)]:
        if actual is not None and (tipo != actual[2] or empieza):
            valor = _recortar(texto[actual[0]:actual[1]])
            if valor:
                ini = texto.find(valor, actual[0])
                out.setdefault(actual[2], []).append({'valor': valor, 'inicio': ini, 'fin': ini + len(valor),
                                                      'confianza': sum(actual[3]) / len(actual[3])})
            actual = None
        if tipo is None:
            continue
        if actual is None:
            actual = [a, b, tipo, [conf]]
        else:
            actual[1] = b
            actual[3].append(conf)
    return out


def entrenar(ejemplos: Sequence[Ejemplo], cfg: Configuracion | None = None,
             log: Callable[[str], None] = lambda _m: None, *, blandos: Sequence = (),
             alfa: float = 1.0, T: float = 1.0) -> ModeloOrdenes:
    """Un modelo nuevo con estos ejemplos, en la GPU.

    ``blandos`` (027:RF-58): órdenes con la distribución del maestro (``destilacion``). En
    ellas la pérdida de tarea es α·CE con su tarea más votada + (1 − α)·T²·KL(maestro ‖
    alumno a temperatura T); en las demás, la CE de siempre.
    """
    torch = _torch()
    cfg = cfg or Configuracion()
    liberar_gpu()
    torch.manual_seed(cfg.semilla)
    rnd = random.Random(cfg.semilla)
    disp = _dispositivo()
    tareas = sorted(TAREAS)
    duros = len(ejemplos)
    ejemplos = [*ejemplos, *(Ejemplo(b.texto, b.tarea, list(b.datos)) for b in blandos)]
    simbolos = {c: i + 3 for i, c in enumerate(alfabeto([e.texto for e in ejemplos]))}
    red = construir_red(len(simbolos) + 3, {'tarea': len(tareas)}, cfg, len(ETIQUETAS)).to(disp)
    opt = torch.optim.AdamW(red.parameters(), lr=cfg.lr, weight_decay=0.01)
    ids = codificar([e.texto for e in ejemplos], simbolos)
    objetivo = [tareas.index(e.tarea) for e in ejemplos]
    etiquetas = [_etiquetas_de(e) for e in ejemplos]
    # La distribución del maestro de cada ejemplo blando; en los duros no se usa.
    maestro = torch.zeros(len(ejemplos), len(tareas), device=disp)
    for i, b in enumerate(blandos):
        for tarea, prob in b.distribucion.items():
            maestro[duros + i, tareas.index(tarea)] = prob
    es_blando = torch.zeros(len(ejemplos), dtype=torch.bool, device=disp)
    es_blando[duros:] = True
    pasos = cfg.epocas * ((len(ejemplos) + cfg.lote - 1) // cfg.lote)
    plan = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=max(pasos, 1))
    ce = torch.nn.CrossEntropyLoss(reduction='none')
    # Los caracteres de un dato son pocos frente a los demás: pesan más, o el modelo aprende
    # que todo es «O» y acierta casi siempre.
    peso = torch.ones(len(ETIQUETAS), device=disp)
    peso[1:] = 4.0
    ce_etq = torch.nn.CrossEntropyLoss(weight=peso, ignore_index=-100)
    for epoca in range(cfg.epocas):
        red.train()
        total, n = 0.0, 0
        for lote in lotes(len(ejemplos), cfg.lote, rnd):
            x = rellenar([ids[i] for i in lote]).to(disp)
            y = torch.tensor([objetivo[i] for i in lote], device=disp)
            e = rellenar([etiquetas[i] for i in lote], -100).to(disp)
            clases, etq = red(x)
            etq = etq[:, :e.shape[1]]
            z = clases['tarea']
            blando = es_blando[lote]
            peso_ce = torch.where(blando, torch.full_like(z[:, 0], alfa), torch.ones_like(z[:, 0]))
            perdida_tarea = (peso_ce * ce(z, y)).mean()
            if bool(blando.any()):
                p = maestro[lote][blando]
                log_q = torch.log_softmax(z[blando] / T, -1)
                kl = (p * (torch.log(p.clamp_min(1e-9)) - log_q)).sum(-1)
                perdida_tarea = perdida_tarea + (1 - alfa) * T * T * kl.sum() / len(lote)
            perdida = perdida_tarea + ce_etq(etq.reshape(-1, etq.shape[-1]), e.reshape(-1))
            opt.zero_grad()
            perdida.backward()
            torch.nn.utils.clip_grad_norm_(red.parameters(), 1.0)
            opt.step()
            plan.step()
            total, n = total + float(perdida.detach()), n + 1
        log(f'  época {epoca}: pérdida {total / max(n, 1):.4f}')
    return ModeloOrdenes(red, simbolos, tareas, cfg)


def evaluar(modelo: ModeloOrdenes, ejemplos: Sequence[Ejemplo]) -> dict[str, float]:
    """Acierto de tarea y F1 de los datos (por trozo exacto, sin mayúsculas ni tildes)."""
    aciertos, vp, fp, fn = 0, 0, 0, 0
    for e in ejemplos:
        p = modelo.predecir(e.texto)
        aciertos += p['tarea'] == e.tarea
        real = {(normalizar(e.texto[a:b]).strip(), t) for a, b, t in e.datos}
        visto = {(normalizar(d['valor']), t) for t, ds in p['datos'].items() for d in ds}
        vp += len(real & visto)
        fp += len(visto - real)
        fn += len(real - visto)
    f1 = 2 * vp / (2 * vp + fp + fn) if vp + fp + fn else 1.0
    return {'acierto_tarea': aciertos / max(len(ejemplos), 1), 'f1_datos': f1, 'ejemplos': len(ejemplos)}


# ------------------------------------------------------------------ registro y promoción
def raiz_modelos(nombre: str = 'ordenes') -> Path:
    return almacen.raiz() / 'modelos' / nombre


def guardar_pesos(red, meta: dict, nombre: str) -> str:
    """Pesos y metadatos de un modelo en su carpeta de versión; devuelve la versión."""
    torch = _torch()
    version = time.strftime('%Y%m%d-%H%M%S') + f'-{random.getrandbits(16):04x}'
    carpeta = raiz_modelos(nombre) / version
    carpeta.mkdir(parents=True)
    torch.save({k: v.detach().cpu() for k, v in red.state_dict().items()}, carpeta / 'pesos.pt')
    (carpeta / 'modelo.json').write_text(json.dumps({**meta, 'version': version, 'torch': torch.__version__},
                                                    ensure_ascii=False, indent=2), encoding='utf-8')
    return version


def promover(version: str, motivo: str, nombre: str = 'ordenes') -> None:
    raiz = raiz_modelos(nombre)
    puntero = raiz / 'promovido.json'
    anterior = json.loads(puntero.read_text(encoding='utf-8'))['version'] if puntero.is_file() else None
    fila = {'version': version, 'anterior': anterior, 'motivo': motivo, 'fecha': almacen.ahora()}
    tmp = raiz / 'promovido.json.tmp'
    tmp.write_text(json.dumps(fila, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, puntero)
    with open(raiz / 'historial.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(fila, ensure_ascii=False) + '\n')


def volver_al_anterior(nombre: str = 'ordenes') -> str | None:
    puntero = raiz_modelos(nombre) / 'promovido.json'
    if not puntero.is_file():
        return None
    anterior = json.loads(puntero.read_text(encoding='utf-8')).get('anterior')
    if anterior:
        promover(anterior, 'vuelta al anterior', nombre)
    return anterior


def version_promovida(nombre: str = 'ordenes') -> str | None:
    puntero = raiz_modelos(nombre) / 'promovido.json'
    return json.loads(puntero.read_text(encoding='utf-8'))['version'] if puntero.is_file() else None


def cargar_pesos(nombre: str, version: str | None = None) -> tuple[dict, Any] | None:
    """Metadatos y pesos de la versión pedida o de la promovida."""
    torch = _torch()
    version = version or version_promovida(nombre)
    if version is None:
        return None
    carpeta = raiz_modelos(nombre) / version
    meta = json.loads((carpeta / 'modelo.json').read_text(encoding='utf-8'))
    return meta, torch.load(carpeta / 'pesos.pt', weights_only=True)


def guardar(modelo: ModeloOrdenes, meta: dict) -> str:
    modelo.version = guardar_pesos(modelo.red, {**meta, 'cfg': asdict(modelo.cfg), 'simbolos': modelo.simbolos,
                                                'tareas': modelo.tareas, 'etiquetas': list(ETIQUETAS)}, 'ordenes')
    return modelo.version


_cache: dict[str, tuple[str, ModeloOrdenes]] = {}


def cargar(version: str | None = None) -> ModeloOrdenes | None:
    """El modelo promovido (o la versión pedida), en memoria tras la primera vez."""
    version = version or version_promovida()
    if version is None:
        return None
    clave = str(raiz_modelos())
    if clave in _cache and _cache[clave][0] == version:
        return _cache[clave][1]
    meta, pesos = cargar_pesos('ordenes', version)
    cfg = Configuracion(**meta['cfg'])
    red = construir_red(len(meta['simbolos']) + 3, {'tarea': len(meta['tareas'])}, cfg, len(meta['etiquetas']))
    red.load_state_dict(pesos)
    red.to(_dispositivo()).eval()
    modelo = ModeloOrdenes(red, meta['simbolos'], meta['tareas'], cfg, version)
    _cache[clave] = (version, modelo)
    return modelo


def ejemplos_reales() -> tuple[list[Ejemplo], list[Ejemplo]]:
    """Las órdenes confirmadas o corregidas por el operador (RF-19), repartidas siempre igual:
    una de cada cinco va a la prueba fija y el resto a entrenar."""
    entrenar_, prueba = [], []
    for i, f in enumerate(almacen.leer('ejemplos')):
        if f.get('tarea') not in TAREAS:
            continue
        e = Ejemplo(f['texto'], f['tarea'], [tuple(d) for d in f.get('datos') or []])
        (prueba if i % 5 == 4 else entrenar_).append(e)
    return entrenar_, prueba


def entrenar_y_promover(vocab: dict, *, cfg: Configuracion | None = None, puertas: Puertas | None = None,
                        log: Callable[[str], None] = lambda _m: None, destilar=None,
                        maestro=None) -> dict[str, Any]:
    """Entrena un candidato con sintéticos y reales, lo evalúa en la prueba fija y lo promueve
    si pasa las puertas y no acierta menos que el modelo en uso (RF-20).

    Con ``destilar`` (una ``destilacion.Destilacion``) y ``maestro``, entrena también el alumno
    con las órdenes sin etiqueta que interpreta el maestro y se queda con él solo si acierta
    al menos lo mismo que sin destilar (027:RF-56 a RF-62).
    """
    from .sinteticos import generar

    cfg = cfg or Configuracion()
    puertas = puertas or Puertas()
    reales, prueba_real = ejemplos_reales()
    datos = generar(vocab, por_tarea=cfg.por_tarea, semilla=cfg.semilla) + reales * 5
    prueba = generar(vocab, por_tarea=20, semilla=SEMILLA_PRUEBA) + prueba_real
    log(f'Asistente: {len(datos)} ejemplos ({len(reales)} reales), prueba fija de {len(prueba)}')
    # 027:RF-29, RF-33, RF-34: el dataset se audita antes y el informe va al registro.
    from ..digital_twin.auditoria import auditar_ordenes

    auditoria = auditar_ordenes(reales=len(reales), sinteticas=len(datos) - 5 * len(reales),
                                prueba_real=len(prueba_real))
    for aviso in auditoria['avisos']:
        log(f'Asistente: {aviso}')
    destilado, r = None, None
    if destilar is not None:
        from .destilacion import etiquetar, registro, sin_etiqueta

        textos = sin_etiqueta(excluir=[e.texto for e in prueba])
        r = etiquetar(textos, maestro, destilar) if maestro is not None and textos else None
        destilado = {**registro(destilar, maestro, r), 'sin_etiqueta': len(textos), 'usado': False}
        if r is None or not r['respondio']:
            log('Asistente: el maestro no respondió o no hay órdenes sin etiqueta; se entrena sin '
                'destilar (027:RF-61)')
            r = None
        else:
            log(f"Asistente: destilación con {destilado['maestro']}: {destilado['etiquetadas']} órdenes "
                f"etiquetadas, {destilado['descartadas']} descartadas por acuerdo (027:RF-56, RF-57)")
    candidato = entrenar(datos, cfg, log)
    metricas = evaluar(candidato, prueba)
    if r is not None and r['blandos']:
        alumno = entrenar(datos, cfg, log, blandos=r['blandos'], alfa=destilar.alfa, T=destilar.T)
        m_alumno = evaluar(alumno, prueba)
        destilado.update(metricas_sin_destilar=metricas, metricas_destilado=m_alumno,
                         usado=m_alumno['acierto_tarea'] >= metricas['acierto_tarea'] - 1e-9)   # RF-60
        log(f"Asistente: con destilación acierto {m_alumno['acierto_tarea']:.3f}, sin ella "
            f"{metricas['acierto_tarea']:.3f}: "
            f"{'se usa el destilado' if destilado['usado'] else 'se queda sin destilar'} (027:RF-60)")
        if destilado['usado']:
            candidato, metricas = alumno, m_alumno
    actual = cargar()
    del_actual = evaluar(actual, prueba) if actual is not None else None
    fallos = []
    if metricas['acierto_tarea'] < puertas.acierto_tarea:
        fallos.append(f"acierto de tarea {metricas['acierto_tarea']:.3f} bajo {puertas.acierto_tarea}")
    if metricas['f1_datos'] < puertas.f1_datos:
        fallos.append(f"F1 de los datos {metricas['f1_datos']:.3f} bajo {puertas.f1_datos}")
    reales_prueba = evaluar(candidato, prueba_real) if prueba_real else None
    if reales_prueba is not None:                                        # 027:RF-18
        if reales_prueba['acierto_tarea'] < puertas.acierto_real:
            fallos.append(f"acierto en las órdenes reales {reales_prueba['acierto_tarea']:.3f} bajo {puertas.acierto_real}")
        if reales_prueba['f1_datos'] < puertas.f1_real:
            fallos.append(f"F1 de los datos reales {reales_prueba['f1_datos']:.3f} bajo {puertas.f1_real}")
    if del_actual and metricas['acierto_tarea'] < del_actual['acierto_tarea'] - 1e-9:
        fallos.append(f"acierta menos que el modelo en uso ({del_actual['acierto_tarea']:.3f})")
    version = guardar(candidato, {'metricas': metricas, 'metricas_en_uso': del_actual,
                                  'ejemplos': len(datos), 'reales': len(reales), 'prueba': len(prueba),
                                  'auditoria': auditoria, 'destilacion': destilado,
                                  'metricas_reales': reales_prueba})
    if not fallos:
        promover(version, f"acierto {metricas['acierto_tarea']:.3f}, F1 {metricas['f1_datos']:.3f}")
    log(f"Asistente: candidato {version}: {'promovido' if not fallos else 'no promovido: ' + '; '.join(fallos)}")
    return {'version': version, 'promovido': not fallos, 'fallos': fallos, **metricas, 'en_uso': del_actual,
            'destilacion': destilado, 'reales': reales_prueba}
