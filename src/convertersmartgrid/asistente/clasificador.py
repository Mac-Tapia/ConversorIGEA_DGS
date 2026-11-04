"""Clasificador de informes en dos niveles (spec 026, RF-14 a RF-16).

Primer nivel, el informe: estudio eléctrico o factibilidad (spec 017). Segundo nivel, el
subtipo de estudio: alimentación de carga nueva, mejora de tensión, refuerzo de red,
migración de tensión, transferencia o PIDE; la lista sale del perfil
(``asistente.subtipos_estudio``) y puede crecer sin tocar el código.

Usa el mismo codificador Transformer que las órdenes, con dos cabezas. Aprende de
descripciones sintéticas de cada subtipo, de los informes que genera la web y de cada
corrección del operador (RF-15), y se promueve con las mismas puertas.
"""
from __future__ import annotations

import json
import random
import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import almacen
from .sinteticos import SUBTIPOS_ESTUDIO, normalizar
from .transformer import (
    LARGO_MAX,
    Configuracion,
    _dispositivo,
    _torch,
    alfabeto,
    cargar_pesos,
    codificar,
    construir_red,
    guardar_pesos,
    liberar_gpu,
    lotes,
    promover,
    rellenar,
    version_promovida,
)

TIPOS_INFORME = ('estudio', 'factibilidad')
SEMILLA_PRUEBA = 7919

#: Una carga nueva puede ser una factibilidad o un estudio eléctrico; cada tipo con sus frases.
#: Con las mismas frases y el tipo solo en un prefijo (a veces vacío), el clasificador decía
#: «estudio» de «informe de factibilidad: solicitud de suministro…» (2026-10-24).
_FACTIBILIDAD = (
    'solicitud de factibilidad de suministro para {kw} kW en {lugar}',
    'factibilidad de suministro de una carga nueva en la SED {sed}',
    'punto de diseño para la carga de {kw} kW solicitada por {cliente}',
    'carta de factibilidad de suministro eléctrico a {cliente} por {kw} kW')
_PLANTILLAS = {
    'alimentación de carga nueva': (
        'atención de la nueva carga de {kw} kW del cliente {cliente} desde {a}',
        'estudio eléctrico para alimentar la carga nueva de {kw} kW desde {a}',
        'alimentación de la carga nueva de {kw} kW: flujo de potencia de {a}'),
    'mejora de tensión': (
        'mejora del nivel de tensión en el extremo del alimentador {a}',
        'subtensión de {v} p.u. en {a}: bancos de condensadores',
        'regulación de tensión con reguladores en la troncal de {a}',
        'caída de tensión fuera de la norma en la SED {sed}'),
    'refuerzo de red': (
        'refuerzo de la red con una nueva terna en el alimentador {a}',
        'cambio de sección del conductor del tramo troncal de {a}',
        'sobrecarga del conductor del tramo {sed}: reforzamiento',
        'cargabilidad de {v} % en la troncal de {a}, se propone refuerzo'),
    'migración de tensión': (
        'migración del alimentador {a} de 10 kV a 22,9 kV',
        'cambio de nivel de tensión de la red de {a}',
        'migración de tensión aguas abajo del nodo {sed}'),
    'transferencia': (
        'transferencia de carga entre {a} y {b}',
        'enlace entre los alimentadores {a} y {b} para transferir carga',
        'maniobra de transferencia de {kw} kW de {a} a {b}'),
    'PIDE': (
        'plan de inversiones en distribución eléctrica del sistema {s}',
        'formatos del PIDE y priorización de obras del sistema {s}',
        'diagnóstico y alternativas del PIDE para {a}'),
}
#: «informe» va en los dos: con «informe de estudio» solo en uno, «informe solicitud de
#: factibilidad…» salía estudio (2026-10-24); el tipo lo dice el contenido, no la primera palabra.
_PREFIJO = {'estudio': ('estudio eléctrico: ', 'informe de estudio: ', 'informe ', 'este informe ', ''),
            'factibilidad': ('informe de factibilidad: ', 'factibilidad: ', 'informe ', 'este informe ', '')}


def _rellenar_plantilla(p: str, rnd: random.Random) -> str:
    codigo = f"{''.join(rnd.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(2))}{rnd.randint(100, 299)}"
    return p.format(kw=rnd.choice((150, 300, 500, 1200, 2500)),
                    lugar=rnd.choice(('la zona industrial', 'el fundo', 'la urbanización')),
                    cliente=rnd.choice(('Agrícola Norte', 'Minera Sur', 'Condominio Los Pinos')), a=codigo,
                    b=f'{codigo[:2]}{rnd.randint(100, 299)}', sed=f'SE{rnd.randint(10000, 99999)}',
                    v=rnd.choice(('0,91', '0,88', '112', '135')), s=rnd.choice(('Norte', 'Costa', 'Valle')))


def generar(subtipos: Sequence[str] = SUBTIPOS_ESTUDIO, *, por_subtipo: int = 120, semilla: int = 0
            ) -> list[tuple[str, str, str]]:
    """``(texto, tipo, subtipo)`` sintéticos; un subtipo sin plantillas usa su propio nombre."""
    rnd = random.Random(semilla)
    out = []
    for sub in subtipos:
        plantillas = _PLANTILLAS.get(sub) or (f'{sub} en {{a}}', f'estudio de {sub} del sistema {{s}}')
        for _ in range(por_subtipo):
            tipo = 'factibilidad' if sub == 'alimentación de carga nueva' and rnd.random() < 0.6 else 'estudio'
            frases = _FACTIBILIDAD if tipo == 'factibilidad' else plantillas
            texto = rnd.choice(_PREFIJO[tipo]) + _rellenar_plantilla(rnd.choice(frases), rnd)
            out.append((texto, tipo, sub))
    rnd.shuffle(out)
    return out


def trozos(texto: str, maximo: int = 8) -> list[str]:
    """Un informe largo en trozos del tamaño del modelo; se promedian (los primeros dicen el asunto)."""
    t = re.sub(r'\s+', ' ', texto).strip()
    return [t[i:i + LARGO_MAX] for i in range(0, min(len(t), LARGO_MAX * maximo), LARGO_MAX)] or ['']


@dataclass
class ClasificadorInformes:
    red: Any
    simbolos: dict[str, int]
    subtipos: list[str]
    cfg: Configuracion
    version: str = ''

    def clasificar(self, texto: str) -> dict[str, Any]:
        torch = _torch()
        disp = next(self.red.parameters()).device
        self.red.eval()
        with torch.no_grad():
            clases, _ = self.red(rellenar(codificar(trozos(texto), self.simbolos)).to(disp))
        pt = torch.softmax(clases['tipo'], -1).mean(0).cpu()
        ps = torch.softmax(clases['subtipo'], -1).mean(0).cpu()
        orden = torch.argsort(ps, descending=True).tolist()
        return {'tipo': TIPOS_INFORME[int(pt.argmax())], 'confianza_tipo': float(pt.max()),
                'subtipo': self.subtipos[orden[0]], 'confianza_subtipo': float(ps[orden[0]]),
                'alternativas': [(self.subtipos[i], float(ps[i])) for i in orden[1:3]], 'version': self.version}


def entrenar(ejemplos: Sequence[tuple[str, str, str]], subtipos: Sequence[str], cfg: Configuracion | None = None,
             log: Callable[[str], None] = lambda _m: None) -> ClasificadorInformes:
    torch = _torch()
    cfg = cfg or Configuracion(epocas=12)
    liberar_gpu()
    torch.manual_seed(cfg.semilla)
    rnd = random.Random(cfg.semilla)
    disp = _dispositivo()
    subtipos = list(subtipos)
    simbolos = {c: i + 3 for i, c in enumerate(alfabeto([t for t, _, _ in ejemplos]))}
    red = construir_red(len(simbolos) + 3, {'tipo': len(TIPOS_INFORME), 'subtipo': len(subtipos)}, cfg).to(disp)
    opt = torch.optim.AdamW(red.parameters(), lr=cfg.lr, weight_decay=0.01)
    ids = codificar([trozos(t)[0] for t, _, _ in ejemplos], simbolos)
    yt = [TIPOS_INFORME.index(tp) for _, tp, _ in ejemplos]
    ys = [subtipos.index(s) for _, _, s in ejemplos]
    ce = torch.nn.CrossEntropyLoss()
    for epoca in range(cfg.epocas):
        red.train()
        total, n = 0.0, 0
        for lote in lotes(len(ejemplos), cfg.lote, rnd):
            clases, _ = red(rellenar([ids[i] for i in lote]).to(disp))
            perdida = ce(clases['tipo'], torch.tensor([yt[i] for i in lote], device=disp)) + \
                ce(clases['subtipo'], torch.tensor([ys[i] for i in lote], device=disp))
            opt.zero_grad()
            perdida.backward()
            opt.step()
            total, n = total + float(perdida.detach()), n + 1
        log(f'  época {epoca}: pérdida {total / max(n, 1):.4f}')
    return ClasificadorInformes(red, simbolos, subtipos, cfg)


def evaluar(modelo: ClasificadorInformes, ejemplos: Sequence[tuple[str, str, str]]) -> dict[str, float]:
    t = s = 0
    for texto, tipo, sub in ejemplos:
        r = modelo.clasificar(texto)
        t += r['tipo'] == tipo
        s += normalizar(r['subtipo']) == normalizar(sub)
    n = max(len(ejemplos), 1)
    return {'acierto_tipo': t / n, 'acierto_subtipo': s / n, 'ejemplos': len(ejemplos)}


def subtipos_del_perfil() -> list[str]:
    """Los subtipos del perfil, con los de la spec si el perfil no dice otros (RF-16)."""
    try:
        from ..perfil_empresa import datos_perfil

        lista = ((datos_perfil() or {}).get('asistente') or {}).get('subtipos_estudio')
    except Exception:  # noqa: BLE001 - sin perfil, los de la spec
        lista = None
    return list(lista or SUBTIPOS_ESTUDIO)


def registrar(texto: str, tipo: str, subtipo: str, origen: str) -> None:
    """Un informe o una corrección como ejemplo del próximo entrenamiento (RF-15)."""
    almacen.anotar('informes', {'texto': texto[:LARGO_MAX * 8], 'tipo': tipo, 'subtipo': subtipo, 'origen': origen})


def origenes_de_informes() -> dict[str, dict[str, int]]:
    """085:RF-25: cuántos informes de entrenamiento y de prueba trae cada origen; los del maestro no son del operador."""
    salida: dict[str, dict[str, int]] = {'entrenamiento': {}, 'prueba': {}}
    for i, f in enumerate(almacen.leer('informes')):
        if f.get('tipo') in TIPOS_INFORME and f.get('subtipo'):
            parte = salida['prueba' if i % 5 == 4 else 'entrenamiento']
            origen = str(f.get('origen') or 'sin_origen')
            parte[origen] = parte.get(origen, 0) + 1
    return salida


def reales() -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    entrenar_, prueba = [], []
    for i, f in enumerate(almacen.leer('informes')):
        if f.get('tipo') in TIPOS_INFORME and f.get('subtipo'):
            (prueba if i % 5 == 4 else entrenar_).append((f['texto'], f['tipo'], f['subtipo']))
    return entrenar_, prueba


_cache: dict[str, tuple[str, ClasificadorInformes]] = {}


def cargar() -> ClasificadorInformes | None:
    version = version_promovida('informes')
    if version is None:
        return None
    if 'informes' in _cache and _cache['informes'][0] == version:
        return _cache['informes'][1]
    meta, pesos = cargar_pesos('informes', version)
    cfg = Configuracion(**meta['cfg'])
    red = construir_red(len(meta['simbolos']) + 3, {'tipo': len(TIPOS_INFORME), 'subtipo': len(meta['subtipos'])},
                        cfg)
    red.load_state_dict(pesos)
    red.to(_dispositivo()).eval()
    m = ClasificadorInformes(red, meta['simbolos'], meta['subtipos'], cfg, version)
    _cache['informes'] = (version, m)
    return m


def _sin_textos_de_prueba(datos: Sequence[tuple[str, str, str]], prueba: Sequence[tuple[str, str, str]]
                          ) -> tuple[list[tuple[str, str, str]], int]:
    """070:RF-65: un informe repetido en la prueba se acierta de memoria."""
    vistos = {' '.join(t.lower().split()) for t, _tp, _s in prueba}
    limpio = [f for f in datos if ' '.join(f[0].lower().split()) not in vistos]
    return limpio, len(datos) - len(limpio)


def entrenar_y_promover(*, cfg: Configuracion | None = None, minimo_subtipo: float = 0.9,
                        log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """Entrena con sintéticos y reales; promueve si acierta el subtipo y no peor que el en uso."""
    cfg = cfg or Configuracion(epocas=12)
    ent, prueba_real = reales()
    subtipos = subtipos_del_perfil()
    subtipos += sorted({s for _t, _tp, s in ent + prueba_real} - set(subtipos))
    prueba = generar(subtipos, por_subtipo=25, semilla=SEMILLA_PRUEBA) + prueba_real
    datos, _quitados = _sin_textos_de_prueba(generar(subtipos, semilla=cfg.semilla) + ent * 5, prueba)
    candidato = entrenar(datos, subtipos, cfg, log)
    m = evaluar(candidato, prueba)
    actual = cargar()
    del_actual = evaluar(actual, prueba) if actual is not None and actual.subtipos == subtipos else None
    fallos = []
    if m['acierto_subtipo'] < minimo_subtipo:
        fallos.append(f"acierto de subtipo {m['acierto_subtipo']:.3f} bajo {minimo_subtipo}")
    if del_actual and m['acierto_subtipo'] < del_actual['acierto_subtipo'] - 1e-9:
        fallos.append('acierta menos que el clasificador en uso')
    version = guardar_pesos(candidato.red, {'metricas': m, 'cfg': asdict(candidato.cfg), 'simbolos': candidato.simbolos,
                                            'subtipos': subtipos, 'tipos': list(TIPOS_INFORME)}, 'informes')
    candidato.version = version
    if not fallos:
        promover(version, f"subtipo {m['acierto_subtipo']:.3f}", 'informes')
    log(f"Clasificador: candidato {version}: {'promovido' if not fallos else 'no promovido: ' + '; '.join(fallos)}")
    return {'version': version, 'promovido': not fallos, 'fallos': fallos, **m}


def guardar_candidato(modelo: ClasificadorInformes, carpeta: Path) -> None:
    """Pesos, metadatos y predicciones de reapertura de un candidato, fuera de los modelos en uso."""
    carpeta.mkdir(parents=True, exist_ok=False)
    _torch().save({k: v.detach().cpu() for k, v in modelo.red.state_dict().items()}, carpeta / 'pesos.pt')
    (carpeta / 'modelo.json').write_text(json.dumps({
        'version': carpeta.name, 'cfg': asdict(modelo.cfg), 'simbolos': modelo.simbolos,
        'subtipos': modelo.subtipos, 'tipos': list(TIPOS_INFORME)}, ensure_ascii=False), encoding='utf-8')
    textos = ['estudio de refuerzo de red', 'factibilidad de una carga nueva']
    (carpeta / 'readback.json').write_text(json.dumps({
        'textos': textos, 'predicciones': [modelo.clasificar(t) for t in textos]}, ensure_ascii=False), encoding='utf-8')


def verificar_reapertura(carpeta: Path) -> dict[str, Any]:
    """El candidato reabierto en un proceso nuevo da lo mismo que al guardarlo."""
    carpeta = Path(carpeta)
    meta = json.loads((carpeta / 'modelo.json').read_text(encoding='utf-8'))
    prueba = json.loads((carpeta / 'readback.json').read_text(encoding='utf-8'))
    cfg = Configuracion(**meta['cfg'])
    red = construir_red(len(meta['simbolos']) + 3, {'tipo': len(TIPOS_INFORME), 'subtipo': len(meta['subtipos'])}, cfg)
    red.load_state_dict(_torch().load(carpeta / 'pesos.pt', weights_only=True, map_location='cpu'))
    red.to(_dispositivo()).eval()
    modelo = ClasificadorInformes(red, meta['simbolos'], meta['subtipos'], cfg, meta.get('version', ''))
    obtenidas = [modelo.clasificar(t) for t in prueba['textos']]
    iguales = all(a['tipo'] == b['tipo'] and a['subtipo'] == b['subtipo']
                  and abs(a['confianza_subtipo'] - b['confianza_subtipo']) < 1e-6
                  for a, b in zip(obtenidas, prueba['predicciones'], strict=True))
    return {'ok': iguales, 'ejemplos': len(obtenidas), 'proceso_nuevo': True}


def entrenar_gobernado(registro, destino: Path, *, cfg: Configuracion | None = None, minimo_subtipo: float = 0.9,
                       log: Callable[[str], None] = lambda _m: None, reabrir=None) -> dict[str, Any]:
    """El clasificador por el registro y la misma puesta en uso que las órdenes (067:RF-26, RF-27).

    Las mismas puertas que ``entrenar_y_promover``. La tarea decía que se reentrenaba y no se hacía; sin
    informes reales en la prueba solo mediría sus propias plantillas, y eso no es evidencia de nada.
    """
    from .modelos_en_uso import aplicar_decision

    ent, prueba_real = reales()
    if not prueba_real:
        motivo = (f'sin informes reales en la prueba ({len(ent)} para entrenar): el clasificador no se entrena '
                  'y sigue el que está en uso')
        log(f'Clasificador: {motivo}')
        c = registro.registrar_candidato(
            'clasificador', model_manifest={'algorithm': 'transformer_informes', 'training_completed': False},
            dataset_manifest={'informes_reales': len(ent)}, metrics={},
            decision={'status': 'BLOQUEADO_POR_DATOS', 'gates': {'approved': False}, 'fallos': [motivo]},
            smoke_reload={'ok': False, 'motivo': 'no entrenado'})
        return {'entrenado': False, 'status': 'BLOQUEADO_POR_DATOS', 'motivo': motivo, 'candidato': c,
                **aplicar_decision('clasificador', c)}
    cfg = cfg or Configuracion(epocas=12)
    subtipos = subtipos_del_perfil()
    subtipos += sorted({s for _t, _tp, s in ent + prueba_real} - set(subtipos))
    prueba = generar(subtipos, por_subtipo=25, semilla=SEMILLA_PRUEBA) + prueba_real
    datos, quitados = _sin_textos_de_prueba(generar(subtipos, semilla=cfg.semilla) + ent * 5, prueba)
    candidato = entrenar(datos, subtipos, cfg, log)
    m = evaluar(candidato, prueba)
    actual = cargar()
    del_actual = evaluar(actual, prueba) if actual is not None and actual.subtipos == subtipos else None
    fallos = []
    if m['acierto_subtipo'] < minimo_subtipo:
        fallos.append(f"acierto de subtipo {m['acierto_subtipo']:.3f} bajo {minimo_subtipo}")
    if del_actual and m['acierto_subtipo'] < del_actual['acierto_subtipo'] - 1e-9:
        fallos.append('acierta menos que el clasificador en uso')
    final = Path(destino) / 'clasificador'
    guardar_candidato(candidato, final)
    if reabrir is None:
        import sys

        from ..model_registry import reabrir_en_subproceso
        herramienta = Path(__file__).resolve().parents[3] / 'tools/asistente_destilar.py'
        reabrir = lambda c: reabrir_en_subproceso([sys.executable, str(herramienta), 'verificar', '--familia',  # noqa: E731
                                                   'clasificador', '--modelo', str(c)])
    smoke = reabrir(final)
    if not smoke.get('ok'):
        fallos.append('falló la reapertura en un proceso nuevo')
    aprobado = not fallos
    c = registro.registrar_candidato(
        'clasificador', model_manifest={'algorithm': 'transformer_informes', 'cfg': asdict(cfg),
                                        'subtipos': subtipos, 'training_completed': True},
        dataset_manifest={'informes_reales': len(ent) + len(prueba_real), 'prueba_real': len(prueba_real),
                          'origenes': origenes_de_informes(),                                                     # 085:RF-25
                          'calidades': {'plantillas': 'silver_deterministic', 'informes': 'gold_generado_o_corregido'},   # 070:RF-66
                          'textos_de_prueba_quitados': quitados},
        metrics={'candidato': m, 'en_uso': del_actual},
        decision={'status': 'PROMOVIDO' if aprobado else 'RECHAZADO', 'gates': {'approved': aprobado}, 'fallos': fallos},
        smoke_reload=smoke,
        artifacts=[p for p in (final / n for n in ('pesos.pt', 'modelo.json', 'readback.json')) if p.is_file()])
    uso = aplicar_decision('clasificador', c)
    log(f"Clasificador: {'en uso ' + str(uso['version']) if uso['promovido'] else 'no pasa: ' + uso['motivo']}")
    return {'entrenado': True, 'status': c['status'], 'candidato': c, 'fallos': fallos, **m, **uso}


def texto_de_docx(ruta: Path) -> str:
    """El texto de un informe Word, para clasificarlo; vacío si falta python-docx."""
    try:
        import docx
    except ImportError:
        return ''
    return '\n'.join(p.text for p in docx.Document(str(ruta)).paragraphs if p.text.strip())
