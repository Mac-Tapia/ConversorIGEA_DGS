"""079 — afinado real del intérprete: las últimas capas del codificador junto con sus cabezas.

Con el codificador congelado solo aprendían dos cabezas: 0,721 en las órdenes confirmadas y 0,03 de `calibrar` en selección
(2026-11-03). Aquí las últimas capas aprenden también, con una tasa mucho menor, y una pérdida contrastiva separa las tareas que
se confunden. Lo congelado se guarda una vez por frase; lo que cambia se recorre en cada paso, porque guardar su salida sería
entrenar con rasgos de pesos que ya no existen. Cada entrenamiento parte de los pesos de la revisión: una vuelta de la validación
cruzada que heredara el tramo de otra ya habría leído las órdenes que examina.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict
import random
import time

from . import codificador_ordenes as co
from .datos_por_palabra import ETIQUETAS
from .maestro_real import NINGUNA
from .sinteticos import Ejemplo

#: 079:RF-26: las tareas que se parecen, declaradas antes de medir; mirando solo selección y calibración, nunca una prueba.
GRUPOS_PARECIDOS: tuple[tuple[str, ...], ...] = (
    ('calibrar', 'recalibrar', 'simular_calibracion', 'sistema_completo'),
    ('escanear', 'verificar_caso_base', 'verificar_convergencia'),
    ('convertir', 'unir', 'convertir_sistema', 'convertir_set'),
    ('no_disponible', 'estudios'),
)
MOTIVO_MEMORIA = 'baje --afinar-lote o --afinar-capas, o libere la GPU que ocupa la web'


def _torch():
    import torch

    return torch


class CachePrefijo:
    """Por frase, una vez por ejecución y en la CPU, solo la salida de las capas congeladas (079:RF-15, RF-16).

    Trae también con qué parar: las filas de selección y la medida que elige al candidato, para que una vuelta de la validación
    cruzada, que solo conoce ``co.entrenar``, pare igual que un candidato (079:RF-49).
    """

    def __init__(self, codificador, capas: int, seleccion: Sequence[dict], medir: Callable, *, lote: int = 64):
        self.codificador, self.capas, self.seleccion, self.medir, self.lote, self.filas = codificador, capas, seleccion, medir, lote, {}

    def entrenar(self, ejemplos: Sequence[Ejemplo], cfg: co.Configuracion, log: Callable[[str], None], dispositivo):
        return entrenar_afinado(ejemplos, cfg, log, cache=self, dispositivo=dispositivo)

    def asegurar(self, textos: Sequence[str], log: Callable[[str], None] = lambda _m: None) -> None:
        pendientes = sorted({t for t in textos if t not in self.filas}, key=len)
        for inicio in range(0, len(pendientes), self.lote):
            trozo = pendientes[inicio:inicio + self.lote]
            p = self.codificador.prefijo(trozo, self.capas)
            for i, t in enumerate(trozo):
                largo = int(p.atencion[i].sum())
                # float16 sin el relleno: son decenas de miles de frases, medidas en 1,2 GB, y al equipo le falta memoria.
                self.filas[t] = (p.estados[i, :largo].half().cpu(), p.indices[i], p.tramos[i])
        if pendientes:
            log(f'  congeladas: {len(pendientes)} frases nuevas, {len(self.filas)} en total')


def fraccion_de_gpu(tope_gb: float, total_bytes: int) -> float:
    """079:RF-7: la parte de la GPU que este proceso puede reservar. Comparte 8 GB con la web."""
    return min(1., tope_gb * 2 ** 30 / total_bytes)


def _limitar_memoria(cfg: co.Configuracion, disp) -> None:
    if disp.type == 'cuda':
        # Sin pasar ``disp``: ``dispositivo()`` da ``cuda`` sin índice, y esta función de torch lo exige (ValueError, leído en su fuente).
        torch = _torch()
        torch.cuda.set_per_process_memory_fraction(fraccion_de_gpu(cfg.tope_gpu_gb, torch.cuda.get_device_properties(torch.cuda.current_device()).total_memory))
        torch.cuda.reset_peak_memory_stats()


def con_precision_mixta(disp) -> bool:
    """079:RF-9: solo en CUDA; en la CPU de las pruebas no hay nada que ahorrar."""
    return disp.type == 'cuda'


def plan_de_tasas(total_pasos: int, capas: int) -> list[Callable[[int], float]]:
    """Factor de la tasa por paso: las cabezas bajan desde el principio y el tramo sube en el primer 10 %.

    El tramo arranca sobre cabezas al azar: con su tasa entera recibiría gradientes sin sentido y estropearía lo que trae la revisión.
    """
    calentar = max(1, total_pasos // 10)

    def baja(paso: int) -> float:
        return max(.1, (total_pasos - paso) / total_pasos)

    def sube(paso: int) -> float:
        return min((paso + 1) / calentar, baja(paso))

    return [baja, *[sube] * capas]


def grupos_de_parametros(red, cfg: co.Configuracion) -> list[dict]:
    """Cabezas a su tasa y, en el tramo, cada capa a una tasa menor que la siguiente (079:RF-3, RF-4)."""
    capas = list(red.tramo)
    grupos = [{'params': [p for n, p in red.named_parameters() if not n.startswith('tramo.')], 'lr': cfg.lr_cabezas}]
    for i, capa in enumerate(capas):
        grupos.append({'params': list(capa.parameters()), 'lr': cfg.lr_tramo * cfg.decaimiento_capa ** (len(capas) - 1 - i)})
    return grupos


def tareas_parecidas(tareas: Sequence[str]):
    """Qué pares se contrastan: los de un mismo grupo y ``ninguna`` con todas (079:RF-26, RF-27)."""
    torch = _torch()
    indice = {t: i for i, t in enumerate(tareas)}
    parecidas = torch.zeros(len(tareas), len(tareas), dtype=torch.bool)
    for grupo in GRUPOS_PARECIDOS:
        presentes = [indice[t] for t in grupo if t in indice]
        for a in presentes:
            for b in presentes:
                if a != b:
                    parecidas[a, b] = True
    if NINGUNA in indice:
        parecidas[indice[NINGUNA], :] = True
        parecidas[:, indice[NINGUNA]] = True
        parecidas[indice[NINGUNA], indice[NINGUNA]] = False
    return parecidas


def perdida_contrastiva(oraciones, objetivo, parecidas, temperatura: float):
    """Contrastiva supervisada, solo frente a las tareas parecidas (079:RF-25).

    Contra todo el catálogo gastaría su fuerza en separar `flujo` de `pide`, que ya no se confunden. Una frase sin otra de su tarea
    o sin ninguna parecida en el lote no aporta.
    """
    torch = _torch()
    similitud = oraciones @ oraciones.T / temperatura
    misma = objetivo.unsqueeze(0) == objetivo.unsqueeze(1)
    diagonal = torch.eye(len(objetivo), dtype=torch.bool, device=objetivo.device)
    positivas = misma & ~diagonal
    negativas = parecidas.to(objetivo.device)[objetivo][:, objetivo]
    validas = positivas.any(1) & negativas.any(1)
    if not validas.any():
        return oraciones.sum() * 0.
    denominador = positivas | negativas
    # Lo que no cuenta se aparta con un valor finito: multiplicar un -inf por el cero de la máscara daría NaN.
    logaritmos = similitud.masked_fill(~denominador, -1e4)
    logaritmos = logaritmos - torch.logsumexp(logaritmos, dim=1, keepdim=True)
    por_frase = -(logaritmos * positivas).sum(1) / positivas.sum(1).clamp_min(1)
    return por_frase[validas].mean()


def lotes_de_epoca(tareas_filas: Sequence[str], largos: Sequence[int], cfg: co.Configuracion, rnd: random.Random) -> list[list[int]]:
    """Los lotes de una época: cada uno con filas de un grupo y de ``ninguna``, y sin pasar del presupuesto de piezas (079:RF-6, RF-28).

    Barajar sin más casi no junta dos frases de `calibrar` y `recalibrar` en 32 de entre 44 298 filas: la contrastiva no tendría con
    qué trabajar. El presupuesto cuenta el relleno, que es lo que ocupa la GPU; una frase sola siempre cabe.
    """
    por_tarea: dict[str, list[int]] = {}
    for i, t in enumerate(tareas_filas):
        por_tarea.setdefault(t, []).append(i)
    orden = list(range(len(tareas_filas)))
    rnd.shuffle(orden)
    lotes, cursor, turno = [], 0, 0

    def cabe(lote: list[int], fila: int) -> bool:
        return len(lote) < cfg.afinar_lote and (len(lote) + 1) * max(largos[fila], *(largos[j] for j in lote)) <= cfg.afinar_piezas

    while cursor < len(orden) and len(lotes) < cfg.pasos_por_epoca:
        lote = [orden[cursor]]
        cursor += 1
        for tarea in (*GRUPOS_PARECIDOS[turno % len(GRUPOS_PARECIDOS)], NINGUNA):
            filas = por_tarea.get(tarea) or []
            for fila in rnd.sample(filas, min(cfg.filas_de_grupo, len(filas))):
                if cabe(lote, fila):
                    lote.append(fila)
        turno += 1
        while cursor < len(orden) and cabe(lote, orden[cursor]):
            lote.append(orden[cursor])
            cursor += 1
        lotes.append(lote)
    return lotes


def medir_seleccion(modelo, cache: CachePrefijo) -> tuple[float, float]:
    """Lo que elige la época, con la misma medida y el mismo orden que elige al candidato."""
    m = cache.medir(modelo, cache.seleccion)
    return float(m['macro_tarea']), float(m['f1_datos'])


def entrenar_afinado(ejemplos: Sequence[Ejemplo], cfg: co.Configuracion, log: Callable[[str], None] = lambda _m: None,
                     *, cache: CachePrefijo, dispositivo) -> co.ModeloCodificador:
    """Tramo y cabezas juntos, con parada por selección. El dispositivo lo da quien llama: sin GPU, su error de siempre (079:RF-10)."""
    torch = _torch()
    if not cache.seleccion:
        raise ValueError('afinar sin filas de selección: no habría con qué parar (079:RF-13)')
    disp, base, inicio = dispositivo, cache.codificador, time.monotonic()
    _limitar_memoria(cfg, disp)
    textos = [e.texto for e in ejemplos]
    cache.asegurar(textos, log)
    torch.manual_seed(cfg.semilla)
    rnd = random.Random(cfg.semilla)
    tareas = co.tareas_del_modelo()
    red = co.construir_cabezas(int(base.dim), len(tareas), len(ETIQUETAS), cfg)
    red.tramo = base.tramo_original(cfg.afinar_capas)                               # 079:RF-14
    red.to(disp)
    modelo = co.ModeloCodificador(red, co.CodificadorAfinado(base, red.tramo, cfg.afinar_capas), tareas, cfg)
    opt = torch.optim.AdamW(grupos_de_parametros(red, cfg), weight_decay=.01)
    plan = torch.optim.lr_scheduler.LambdaLR(opt, plan_de_tasas(cfg.afinar_epocas * cfg.pasos_por_epoca, cfg.afinar_capas))
    mixta = con_precision_mixta(disp)
    escala = torch.amp.GradScaler(disp.type, enabled=mixta)
    objetivo = torch.tensor([tareas.index(e.tarea) for e in ejemplos], device=disp)
    cuentas = torch.bincount(objetivo, minlength=len(tareas)).float().clamp_min(1)
    pesos = (cuentas.sum() / (len(tareas) * cuentas)).clamp(max=cfg.peso_maximo)
    peso_etiqueta = torch.ones(len(ETIQUETAS), device=disp)
    peso_etiqueta[1:] = 4.
    ce_datos = torch.nn.CrossEntropyLoss(weight=peso_etiqueta, ignore_index=-100)
    parecidas = tareas_parecidas(tareas)
    largos = [len(cache.filas[t][0]) for t in textos]
    formas = {t: torch.tensor([co.rasgos_de_forma(t[a:b]) for a, b in cache.filas[t][2]], dtype=torch.float32) for t in set(textos)
              if cache.filas[t][2]}
    historial, mejor, mejor_puntaje, mejor_epoca, sin_mejorar = [], None, None, -1, 0
    for epoca in range(cfg.afinar_epocas):
        comienzo, total, n = time.monotonic(), 0., 0
        lotes = lotes_de_epoca([e.tarea for e in ejemplos], largos, cfg, rnd)
        for lote in lotes:
            red.train()
            filas = [cache.filas[textos[i]] for i in lote]
            estados = torch.nn.utils.rnn.pad_sequence([f[0] for f in filas], batch_first=True).float().to(disp)
            atencion = torch.zeros(estados.shape[:2], dtype=torch.long, device=disp)
            for k, f in enumerate(filas):
                atencion[k, :len(f[0])] = 1
            try:
                with torch.amp.autocast(disp.type, dtype=torch.float16, enabled=mixta):         # 079:RF-9
                    h = base.aplicar_tramo(red.tramo, estados, atencion)                        # 079:RF-15
                # Las cabezas, fuera: la GRU y la contrastiva en float32 no cuestan memoria y no arriesgan desbordes.
                oraciones, tokens = co.piezas_del_tramo(h.float(), atencion, [f[1] for f in filas])
                y = objetivo[torch.tensor(lote, device=disp)]
                perdida = torch.nn.functional.cross_entropy(red.tarea(oraciones), y, weight=pesos, label_smoothing=cfg.suavizado)
                perdida = perdida + cfg.peso_contrastiva * perdida_contrastiva(oraciones, y, parecidas, cfg.temperatura_contrastiva)
                con_piezas = [k for k, f in enumerate(filas) if f[2]]
                if con_piezas:
                    largo = torch.tensor([len(filas[k][2]) for k in con_piezas])
                    t_lote = torch.nn.utils.rnn.pad_sequence([tokens[k] for k in con_piezas], batch_first=True)
                    forma = torch.nn.utils.rnn.pad_sequence([formas[textos[lote[k]]] for k in con_piezas], batch_first=True).to(disp)
                    etiquetas = torch.full((len(con_piezas), int(largo.max())), -100, dtype=torch.long)
                    for fila, k in enumerate(con_piezas):
                        etq = co.etiquetas_por_token(ejemplos[lote[k]], filas[k][2])
                        etiquetas[fila, :len(etq)] = torch.tensor(etq)
                    z = red(t_lote, forma, largo)
                    perdida = perdida + ce_datos(z.reshape(-1, z.shape[-1]), etiquetas.to(disp).reshape(-1))
                opt.zero_grad(set_to_none=True)
                escala.scale(perdida).backward()
                escala.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(red.parameters(), 1.)
                escala.step(opt)
                escala.update()
                plan.step()
            except torch.cuda.OutOfMemoryError as exc:
                raise RuntimeError(f'Sin memoria de GPU al afinar con {cfg.tope_gpu_gb} GB de tope: {MOTIVO_MEMORIA}') from exc       # 079:RF-8
            total, n = total + float(perdida.detach()), n + 1
        puntaje = medir_seleccion(modelo, cache)                                      # 079:RF-11
        fila = {'epoca': epoca, 'perdida': total / max(n, 1), 'pasos': n, 'macro_tarea': puntaje[0], 'f1_datos': puntaje[1],
                'tiempo_s': time.monotonic() - comienzo,
                'memoria_pico_gb': torch.cuda.max_memory_allocated() / 2 ** 30 if disp.type == 'cuda' else None}
        historial.append(fila)
        log(f"  época {epoca} de afinado: pérdida {fila['perdida']:.4f}, selección {puntaje[0]:.4f} y {puntaje[1]:.4f}, "
            f"{fila['tiempo_s']:.0f} s, GPU {fila['memoria_pico_gb']}")
        if mejor_puntaje is None or puntaje > mejor_puntaje:
            mejor, mejor_puntaje, mejor_epoca, sin_mejorar = {k: v.detach().cpu().clone() for k, v in red.state_dict().items()}, puntaje, epoca, 0
        else:
            sin_mejorar += 1
            if sin_mejorar >= cfg.paciencia:                                                    # 079:RF-12
                break
    red.load_state_dict(mejor)
    red.eval()
    modelo.afinado = {'epocas': historial, 'mejor_epoca': mejor_epoca, 'seleccion_mejor': list(mejor_puntaje),
                      'parada_temprana': sin_mejorar >= cfg.paciencia, 'duracion_s': time.monotonic() - inicio}
    return modelo


def confusiones(modelo, filas: Sequence[dict], tope: int = 15) -> list[dict]:
    """Solo cuentas de pares de tareas; quien llama da selección o calibración, nunca una prueba (079:RF-29, RF-30, RF-64)."""
    cuenta = Counter()
    for r in filas:
        predicha = modelo.predecir(r['texto'])['tarea']
        if predicha != r['tarea']:
            cuenta[(r['tarea'], predicha)] += 1
    return [{'esperada': a, 'predicha': b, 'filas': n} for (a, b), n in sorted(cuenta.items(), key=lambda x: (-x[1], x[0]))[:tope]]


def protocolo(cfg: co.Configuracion) -> dict:
    """Lo que el afinado fija antes de entrenar ningún candidato (079:RF-63)."""
    return {**{k: v for k, v in asdict(cfg).items() if k.startswith(('afinar', 'lr_', 'decaimiento', 'paciencia', 'peso_contrastiva', 'temperatura_', 'filas_de', 'pasos', 'tope'))},
            'grupos_parecidos': [list(g) for g in GRUPOS_PARECIDOS], 'pasos_totales_maximos': cfg.afinar_epocas * cfg.pasos_por_epoca}
