"""069 — intérprete de órdenes sobre un codificador preentrenado congelado, con clase «ninguna».

El Transformer letra a letra aprendía su alfabeto desde cero y no conocía sinónimos: «transforma la red X en dgs»
le salía ``transferencia`` con confianza 1,0, y el 62,6 % de la conversación real pasaba su umbral (2026-11-02). Aquí
solo se aprenden dos cabezas sobre un codificador que ya sabe español, y una de sus clases es «esto no es una orden».

Los artefactos son las cabezas y sus metadatos; el codificador se nombra con su revisión y se lee de la caché local,
sin red. El contrato de ``predecir`` es el de ``transformer.ModeloOrdenes``, y el intérprete, el registro y
``modelos_en_uso`` no distinguen uno de otro.

079: con ``afinar_capas`` las últimas capas aprenden junto con las cabezas (``afinado_ordenes``), y el artefacto las lleva.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
import copy
from dataclasses import dataclass, field
import hashlib
import random
from typing import Any

from .datos_por_palabra import ETIQUETAS, marcar_datos
from .maestro_real import NINGUNA
from .sinteticos import Ejemplo
from .tareas import TAREAS

ARQUITECTURA = 'codificador_preentrenado_v1'
ARQUITECTURA_AFINADA = 'codificador_afinado_v1'
NOMBRE_CODIFICADOR = 'intfloat/multilingual-e5-base'
#: La revisión se fija: otra revisión del codificador daría otras representaciones para las mismas cabezas.
REVISION_CODIFICADOR = 'd128750597153bb5987e10b1c3493a34e5a4502a'
#: 069:RF-33: el codificador se elige al entrenar, cada uno con su revisión fija (docs/MODELOS_IA_LOCK.json). Con el base y
#: 6 capas afinadas el candidato del 2026-11-11 llegó a 0,995 en selección y a 0,875 en la sellada: no generalizaba.
CODIFICADORES = {'base': (NOMBRE_CODIFICADOR, REVISION_CODIFICADOR),
                 'large': ('intfloat/multilingual-e5-large', '3d7cfbdacd47fdda877c5cd8a79fbcc4f2a574f3')}
PREFIJO = 'query: '
LARGO_TOKENS = 96
RASGOS_FORMA = 6
UMBRAL_HEREDADO = .85
#: 079:RF-59: la orden que deja el codificador en la caché que lee este proceso.
ORDEN_PREPARAR = f'python tools/preparar_modelos_ia.py --descargar --backend huggingface --id {NOMBRE_CODIFICADOR} --output-json preparar.json'


def orden_preparar(nombre: str) -> str:
    return ORDEN_PREPARAR.replace(NOMBRE_CODIFICADOR, nombre)


def _torch():
    import torch

    return torch


@dataclass
class Configuracion:
    epocas: int = 24
    lote_tarea: int = 512
    lote_etiquetas: int = 128
    lr: float = 2e-3
    oculta_tarea: int = 512
    oculta_etiquetas: int = 192
    abandono: float = .2
    suavizado: float = .05
    peso_maximo: float = 20.
    semilla: int = 0
    # 079: 0 es solo las cabezas (RF-2). Con 2 capas: 14,2 M de los 278 M parámetros, 58 MB en `pesos.pt` con las cabezas (medido el 2026-11-03).
    afinar_capas: int = 0
    afinar_epocas: int = 8
    codificador: str = 'base'                                                          # 069:RF-33
    #: Una época aquí es este tope de pasos: con 44 298 filas, medir selección solo al recorrerlas todas pararía tarde.
    pasos_por_epoca: int = 800
    afinar_lote: int = 32
    #: Relleno incluido: la media es de 18 piezas, el 95 % bajo 29 y el máximo 55 en lo sintético (medido el 2026-11-03).
    afinar_piezas: int = 1536
    lr_cabezas: float = 1e-3
    lr_tramo: float = 2e-5
    decaimiento_capa: float = .8
    paciencia: int = 2
    peso_contrastiva: float = .2
    temperatura_contrastiva: float = .1
    filas_de_grupo: int = 2
    tope_gpu_gb: float = 5.


@dataclass
class Codificado:
    """Lo que el codificador da de cada frase: su vector, un vector por pieza y dónde está cada pieza."""
    oraciones: Any
    tokens: list
    tramos: list[list[tuple[int, int]]]


@dataclass
class Prefijo:
    """Lo que dan las capas congeladas de unas frases: lo único que el afinado puede guardar (079:RF-16)."""
    estados: Any
    atencion: Any
    indices: list[list[int]]
    tramos: list[list[tuple[int, int]]]


class CodificadorPreentrenado:
    """El codificador congelado, en la GPU, leído solo de la caché local."""

    def __init__(self, nombre: str, revision: str, dispositivo):
        try:
            from transformers import AutoModel, AutoTokenizer
            self.tokenizador = AutoTokenizer.from_pretrained(nombre, revision=revision, local_files_only=True)
            self.red = AutoModel.from_pretrained(nombre, revision=revision, local_files_only=True)
        except (ImportError, OSError, ValueError) as exc:
            raise RuntimeError(f'El codificador {nombre} (revisión {revision}) no está en la caché local de '
                               f'Hugging Face que usa este proceso, o faltan sus librerías; se prepara con: {orden_preparar(nombre)}: {exc}') from exc
        self.red.to(dispositivo).eval()
        for p in self.red.parameters():
            p.requires_grad_(False)
        self.dispositivo = dispositivo
        self.nombre, self.revision = nombre, revision
        self.dim = int(self.red.config.hidden_size)
        self._huellas: dict[int, str] = {}

    def _tokenizar(self, textos: Sequence[str]) -> tuple[dict, list[list[int]], list[list[tuple[int, int]]]]:
        lote = self.tokenizador([PREFIJO + t for t in textos], padding=True, truncation=True, max_length=LARGO_TOKENS,
                                return_offsets_mapping=True, return_tensors='pt')
        posiciones = lote.pop('offset_mapping').tolist()
        indices, tramos = [], []
        for pos in posiciones:
            # Las piezas del prefijo y las especiales no son de la orden; lo demás se mide desde su inicio.
            propios = [i for i, (a, b) in enumerate(pos) if b > len(PREFIJO) and b > a]
            indices.append(propios)
            tramos.append([(max(0, pos[i][0] - len(PREFIJO)), pos[i][1] - len(PREFIJO)) for i in propios])
        return {k: v.to(self.dispositivo) for k, v in lote.items()}, indices, tramos

    def __call__(self, textos: Sequence[str]) -> Codificado:
        torch = _torch()
        lote, indices, tramos = self._tokenizar(textos)
        with torch.no_grad():
            h = self.red(**lote).last_hidden_state
        mascara = lote['attention_mask'].unsqueeze(-1).to(h.dtype)
        oraciones = torch.nn.functional.normalize((h * mascara).sum(1) / mascara.sum(1), dim=-1)
        return Codificado(oraciones, [h[fila, propios] for fila, propios in enumerate(indices)], tramos)

    def _mascara(self, atencion, estados):
        from transformers.masking_utils import create_bidirectional_mask

        return create_bidirectional_mask(config=self.red.config, inputs_embeds=estados, attention_mask=atencion)

    def prefijo(self, textos: Sequence[str], capas: int) -> Prefijo:
        """Hasta justo antes de las ``capas`` que se afinan; con ellas da lo mismo que ``red`` entera (079:RF-16)."""
        torch = _torch()
        lote, indices, tramos = self._tokenizar(textos)
        with torch.no_grad():
            h = self.red.embeddings(input_ids=lote['input_ids'])
            mascara = self._mascara(lote['attention_mask'], h)
            for capa in self.red.encoder.layer[:-capas]:
                h = capa(h, mascara)
        return Prefijo(h, lote['attention_mask'], indices, tramos)

    def tramo_original(self, capas: int):
        """Una copia, con gradiente, de las últimas capas tal como vienen en la revisión: lo compartido no se toca (079:RF-14)."""
        tramo = copy.deepcopy(self.red.encoder.layer[-capas:])
        for p in tramo.parameters():
            p.requires_grad_(True)
        return tramo

    def aplicar_tramo(self, tramo, estados, atencion):
        mascara = self._mascara(atencion, estados)
        h = estados
        for capa in tramo:
            h = capa(h, mascara)
        return h

    def huella_congelada(self, capas: int) -> str:
        """De embeddings y capas congeladas; se calcula una vez por proceso: es 1 GB de pesos (079:RF-19)."""
        if capas not in self._huellas:
            self._huellas[capas] = huella_tensores([
                *self.red.embeddings.state_dict(prefix='embeddings.').items(),
                *((f'capa.{i}.{n}', v) for i, c in enumerate(self.red.encoder.layer[:-capas]) for n, v in c.state_dict().items())])
        return self._huellas[capas]


def huella_tensores(pares: Sequence[tuple[str, Any]]) -> str:
    """De unos pesos, en un orden fijo y sin depender del dispositivo: dice si son exactamente los mismos (079:RF-19)."""
    h = hashlib.blake2b(digest_size=16)
    for nombre, tensor in sorted(pares, key=lambda p: p[0]):
        h.update(nombre.encode('utf-8'))
        h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def piezas_del_tramo(estados, atencion, indices):
    """Del paso por el tramo a lo que leen las cabezas: el vector de la frase y un vector por pieza de la orden."""
    torch = _torch()
    mascara = atencion.unsqueeze(-1).to(estados.dtype)
    oraciones = torch.nn.functional.normalize((estados * mascara).sum(1) / mascara.sum(1).clamp_min(1), dim=-1)
    return oraciones, [estados[fila, idx] for fila, idx in enumerate(indices)]


class CodificadorAfinado:
    """Lo congelado, compartido en el proceso, más el tramo afinado de este modelo. Se llama como el congelado (079:RF-22)."""

    def __init__(self, base, tramo, capas: int):
        self.base, self.tramo, self.capas = base, tramo, capas

    @property
    def dim(self) -> int:
        return int(self.base.dim)

    def __call__(self, textos: Sequence[str]) -> Codificado:
        with _torch().no_grad():
            p = self.base.prefijo(textos, self.capas)
            h = self.base.aplicar_tramo(self.tramo, p.estados, p.atencion)
            oraciones, tokens = piezas_del_tramo(h, p.atencion, p.indices)
        return Codificado(oraciones, tokens, p.tramos)

    def meta_tramo(self) -> dict[str, Any]:
        return {'capas': self.capas, 'parametros': sum(int(p.numel()) for p in self.tramo.parameters()),
                'huella': huella_tensores(list(self.tramo.state_dict().items())),
                'huella_congelada': self.base.huella_congelada(self.capas)}


#: Se cambia en las pruebas para inyectar un codificador falso, sin descargar nada.
FABRICA: Callable = CodificadorPreentrenado
_abiertos: dict[tuple, Any] = {}


def obtener_codificador(nombre: str, revision: str, dispositivo):
    """Uno por proceso: 1,4 GB de GPU no se repiten por cada candidato ni por cada reapertura."""
    clave = (FABRICA, nombre, revision, str(dispositivo))
    if clave not in _abiertos:
        _abiertos[clave] = FABRICA(nombre, revision, dispositivo)
    return _abiertos[clave]


def rasgos_de_forma(pieza: str) -> list[float]:
    """Lo que delata un código de red, que para el codificador no significa nada: AB101, 2026-07, D:/datos."""
    limpia = pieza.strip()
    return [float(any(c.isdigit() for c in limpia)), float(any(c.isupper() for c in limpia)),
            float(bool(limpia) and limpia.isdigit()), float(any(c in '_-/\\.:' for c in limpia)),
            float(pieza[:1].isspace()), min(len(limpia), 12) / 12]


def tareas_del_modelo() -> list[str]:
    return [*sorted(TAREAS), NINGUNA]


def construir_cabezas(dim: int, n_tareas: int, n_etiquetas: int, cfg: Configuracion):
    torch = _torch()
    nn = torch.nn

    class Cabezas(nn.Module):
        def __init__(self):
            super().__init__()
            self.tarea = nn.Sequential(nn.Linear(dim, cfg.oculta_tarea), nn.GELU(), nn.Dropout(cfg.abandono),
                                       nn.Linear(cfg.oculta_tarea, n_tareas))
            self.reduce = nn.Sequential(nn.Dropout(cfg.abandono), nn.Linear(dim, cfg.oculta_etiquetas), nn.GELU())
            self.secuencia = nn.GRU(cfg.oculta_etiquetas + RASGOS_FORMA, cfg.oculta_etiquetas, batch_first=True,
                                    bidirectional=True)
            self.etiquetas = nn.Linear(2 * cfg.oculta_etiquetas, n_etiquetas)

        def forward(self, tokens, rasgos, largos):
            x = torch.cat([self.reduce(tokens), rasgos], -1)
            empaquetado = nn.utils.rnn.pack_padded_sequence(x, largos.cpu(), batch_first=True, enforce_sorted=False)
            h, _ = self.secuencia(empaquetado)
            h, _ = nn.utils.rnn.pad_packed_sequence(h, batch_first=True, total_length=x.shape[1])
            return self.etiquetas(h)

    return Cabezas()


@dataclass
class ModeloCodificador:
    """Las cabezas entrenadas, con el mismo contrato que ``transformer.ModeloOrdenes``."""

    red: Any
    codificador: Any
    tareas: list[str]
    cfg: Configuracion
    version: str = ''
    temperatura: float = 1.
    umbral: float = UMBRAL_HEREDADO
    simbolos: dict = field(default_factory=dict)
    afinado: dict | None = None
    #: 079:RF-54: la regla de Ollama elegida para este modelo; sin ella, la fija de 075:RF-37 (RF-56).
    puesto_charla: int | None = None
    piso_charla: float = 0.

    @property
    def meta_extra(self) -> dict[str, Any]:
        tramo = getattr(self.codificador, 'meta_tramo', None)
        # 069:RF-33: el que se usó, no el de por defecto: al reabrir se carga ese (RF-4).
        datos = {'nombre': getattr(self.codificador, 'nombre', NOMBRE_CODIFICADOR),
                 'revision': getattr(self.codificador, 'revision', REVISION_CODIFICADOR), 'prefijo': PREFIJO,
                 'largo_tokens': LARGO_TOKENS, 'dim': int(self.codificador.dim)}
        extra = {'arquitectura': ARQUITECTURA_AFINADA if tramo else ARQUITECTURA, 'umbral': self.umbral,
                 'codificador': {**datos, 'tramo': tramo()} if tramo else datos}
        if self.puesto_charla is not None:
            extra['regla_charla'] = {'puesto': self.puesto_charla, 'piso': self.piso_charla}
        return extra

    def logits_tarea(self, textos: Sequence[str]):
        self.red.eval()
        torch = _torch()
        with torch.no_grad():
            return self.red.tarea(self.codificador(textos).oraciones.float())

    def puesto_ninguna(self, texto: str) -> int | None:
        """075:RF-37: en qué lugar ve el modelo «esto no es una orden», 1 el primero. Va aparte de ``predecir``,
        cuyos campos fija 069:RF-2 y cuyas alternativas no la nombran (069:RF-16); la temperatura no cambia el orden."""
        if NINGUNA not in self.tareas:
            return None
        z = self.logits_tarea([texto])[0]
        return 1 + int((z > z[self.tareas.index(NINGUNA)]).sum())

    def predecir(self, texto: str) -> dict[str, Any]:
        torch = _torch()
        self.red.eval()
        cod = self.codificador([texto])
        with torch.no_grad():
            p = torch.softmax(self.red.tarea(cod.oraciones.float())[0] / self.temperatura, -1).cpu()
        orden = torch.argsort(p, descending=True).tolist()
        tarea = self.tareas[orden[0]]
        # «ninguna» dice que no hay orden: como alternativa no le serviría de nada al operador (069:RF-16).
        alternativas = [(self.tareas[i], float(p[i])) for i in orden[1:] if self.tareas[i] != NINGUNA][:2]
        return {'tarea': tarea, 'confianza': float(p[orden[0]]), 'alternativas': alternativas,
                'datos': self._datos(texto, tarea, cod), 'modelo': 'transformer', 'version': self.version}

    def _datos(self, texto: str, tarea: str, cod: Codificado) -> dict[str, list[dict]]:
        tramos = cod.tramos[0]
        if tarea == NINGUNA or not tramos:
            return {}
        torch = _torch()
        tokens = cod.tokens[0].unsqueeze(0).float()
        rasgos = torch.tensor([[rasgos_de_forma(texto[a:b]) for a, b in tramos]], dtype=tokens.dtype, device=tokens.device)
        with torch.no_grad():
            p = torch.softmax(self.red(tokens, rasgos, torch.tensor([len(tramos)]))[0], -1).cpu().numpy()
        # A caracteres: así el voto por palabra de ``_spans`` da el dato entero, como en el modelo heredado.
        import numpy as np
        por_caracter = np.zeros((len(texto), len(ETIQUETAS)), dtype='float32')
        por_caracter[:, 0] = 1.
        for (a, b), fila in zip(tramos, p, strict=True):
            por_caracter[a:b] = fila
        admitidos = {d.tipo for d in TAREAS[tarea].datos}
        if tarea == 'pregunta':
            # 069:RF-30: la pregunta es el mensaje entero (``plan`` y la web lo toman así); marcar un trozo
            # le quitaba contexto y era un dato falso en cada frase sin datos (F1 de 0 en calibración).
            admitidos.discard('texto')
        return {k: v for k, v in marcar_datos(texto, por_caracter, _sin_signos).items() if k in admitidos}     # 069:RF-3


def _sin_signos(valor: str) -> str:
    """069:RF-31: aquí no se recortan palabras de unión. Las arrastraba el modelo letra a letra; este marca
    piezas, y el recorte partía datos buenos: «todos los alimentadores» salía «todos» y «el año 2027», «año 2027»."""
    return valor.strip(' ,.;:¿?¡!"\'')


class CacheCodificada:
    """Cada frase, codificada una vez por ejecución y guardada en la CPU: los candidatos comparten frases."""

    def __init__(self, codificador, *, lote: int = 64):
        self.codificador, self.lote, self.filas = codificador, lote, {}

    def asegurar(self, textos: Sequence[str], log: Callable[[str], None] = lambda _m: None) -> None:
        pendientes = sorted({t for t in textos if t not in self.filas}, key=len)
        for inicio in range(0, len(pendientes), self.lote):
            trozo = pendientes[inicio:inicio + self.lote]
            cod = self.codificador(trozo)
            for i, t in enumerate(trozo):
                # float16: son decenas de miles de frases, y al equipo le falta memoria (2026-11-02).
                self.filas[t] = (cod.oraciones[i].float().cpu(), cod.tokens[i].half().cpu(), cod.tramos[i])
        if pendientes:
            log(f'  codificador: {len(pendientes)} frases nuevas, {len(self.filas)} en total')


def etiquetas_por_token(e: Ejemplo, tramos: Sequence[tuple[int, int]]) -> list[int]:
    """B- en la primera pieza que toca cada dato e I- en las siguientes."""
    indice = {t: i for i, t in enumerate(ETIQUETAS)}
    salida = [0] * len(tramos)
    for a, b, tipo in e.datos:
        primero = True
        for i, (x, y) in enumerate(tramos):
            if x < b and a < y:
                salida[i] = indice[f'{"B" if primero else "I"}-{tipo}']
                primero = False
    return salida


def entrenar(ejemplos: Sequence[Ejemplo], cfg: Configuracion | None = None, log: Callable[[str], None] = lambda _m: None,
             *, cache: CacheCodificada, dispositivo) -> ModeloCodificador:
    """Las dos cabezas sobre el codificador congelado; las semillas no cambian lo que él da.

    El dispositivo lo da quien llama, con ``transformer.dispositivo_de_calculo``: sin GPU, su error de siempre, sin caer a la
    CPU (069:RF-6). Aquí no hay ningún valor por defecto que permita caer.
    """
    torch = _torch()
    cfg = cfg or Configuracion()
    if cfg.afinar_capas:                                                             # 079:RF-1, RF-2
        return cache.entrenar(ejemplos, cfg, log, dispositivo)
    disp = dispositivo
    codificador = cache.codificador
    cache.asegurar([e.texto for e in ejemplos], log)
    torch.manual_seed(cfg.semilla)
    rnd = random.Random(cfg.semilla)
    tareas = tareas_del_modelo()
    red = construir_cabezas(int(codificador.dim), len(tareas), len(ETIQUETAS), cfg).to(disp)
    opt = torch.optim.AdamW(red.parameters(), lr=cfg.lr, weight_decay=.01)
    oraciones = torch.stack([cache.filas[e.texto][0] for e in ejemplos]).to(disp)
    objetivo = torch.tensor([tareas.index(e.tarea) for e in ejemplos], device=disp)
    # Las tareas no tienen las mismas filas: las que llevan códigos se multiplican y las demás no (068).
    cuentas = torch.bincount(objetivo, minlength=len(tareas)).float().clamp_min(1)
    pesos = (cuentas.sum() / (len(tareas) * cuentas)).clamp(max=cfg.peso_maximo)
    for epoca in range(cfg.epocas):
        red.train()
        orden = torch.randperm(len(ejemplos), device=disp)
        total, n = 0., 0
        for i in range(0, len(ejemplos), cfg.lote_tarea):
            b = orden[i:i + cfg.lote_tarea]
            perdida = torch.nn.functional.cross_entropy(red.tarea(oraciones[b]), objetivo[b], weight=pesos,
                                                        label_smoothing=cfg.suavizado)
            opt.zero_grad()
            perdida.backward()
            opt.step()
            total, n = total + float(perdida.detach()), n + 1
        log(f'  época {epoca} de tarea: pérdida {total / max(n, 1):.4f}')
    _entrenar_etiquetas(red, ejemplos, cache, cfg, rnd, disp, log)
    return ModeloCodificador(red, codificador, tareas, cfg)


def _entrenar_etiquetas(red, ejemplos, cache, cfg: Configuracion, rnd: random.Random, disp, log) -> None:
    torch = _torch()
    # Los caracteres de un dato son pocos: pesan más, igual que en el modelo heredado.
    peso = torch.ones(len(ETIQUETAS), device=disp)
    peso[1:] = 4.
    ce = torch.nn.CrossEntropyLoss(weight=peso, ignore_index=-100)
    parametros = [*red.reduce.parameters(), *red.secuencia.parameters(), *red.etiquetas.parameters()]
    opt = torch.optim.AdamW(parametros, lr=cfg.lr / 2, weight_decay=.01)
    filas = [i for i, e in enumerate(ejemplos) if cache.filas[e.texto][2]]
    # Tensores y no listas de floats: con listas, el proceso subía de 1,5 a 2,9 GB (medido el 2026-11-02).
    rasgos = {e.texto: torch.tensor([rasgos_de_forma(e.texto[a:b]) for a, b in cache.filas[e.texto][2]], dtype=torch.float16)
              for e in ejemplos if cache.filas[e.texto][2]}
    # Menos épocas que la tarea: cada una recorre una GRU sobre todas las piezas de todas las frases.
    for epoca in range(max(1, cfg.epocas // 2)):
        red.train()
        rnd.shuffle(filas)
        total, n = 0., 0
        for i in range(0, len(filas), cfg.lote_etiquetas):
            lote = [ejemplos[j] for j in filas[i:i + cfg.lote_etiquetas]]
            largos = torch.tensor([len(cache.filas[e.texto][2]) for e in lote])
            maximo = int(largos.max())
            tokens = torch.nn.utils.rnn.pad_sequence([cache.filas[e.texto][1] for e in lote], batch_first=True).float().to(disp)
            forma = torch.nn.utils.rnn.pad_sequence(
                [rasgos[e.texto] for e in lote], batch_first=True).float().to(disp)
            y = torch.full((len(lote), maximo), -100, dtype=torch.long)
            for k, e in enumerate(lote):
                etq = etiquetas_por_token(e, cache.filas[e.texto][2])
                y[k, :len(etq)] = torch.tensor(etq)
            z = red(tokens, forma, largos)
            perdida = ce(z.reshape(-1, z.shape[-1]), y.to(disp).reshape(-1))
            opt.zero_grad()
            perdida.backward()
            torch.nn.utils.clip_grad_norm_(parametros, 1.)
            opt.step()
            total, n = total + float(perdida.detach()), n + 1
        log(f'  época {epoca} de datos: pérdida {total / max(n, 1):.4f}')


def _abrir_tramo(meta: dict, pesos: dict, cfg: Configuracion, base, disp) -> tuple[Any, CodificadorAfinado]:
    """Las cabezas y el tramo de un modelo guardado, comprobando que son los que se guardaron (079:RF-19, RF-20)."""
    datos = meta['codificador']
    tramo_meta = datos['tramo']
    capas = int(tramo_meta['capas'])
    red = construir_cabezas(int(datos['dim']), len(meta['tareas']), len(meta['etiquetas']), cfg)
    red.tramo = base.tramo_original(capas)
    red.load_state_dict(pesos)
    red.to(disp).eval()
    if huella_tensores(list(red.tramo.state_dict().items())) != tramo_meta['huella']:
        raise ValueError('la huella del tramo afinado no coincide con la guardada')
    if base.huella_congelada(capas) != tramo_meta['huella_congelada']:
        raise ValueError(f"la huella de las capas congeladas no coincide: ¿es la revisión {datos['revision']} del codificador?")
    return red, CodificadorAfinado(base, red.tramo, capas)


def modelo_desde(meta: dict, pesos: dict, version: str, dispositivo) -> ModeloCodificador:
    """Reabre un modelo guardado: sus cabezas, y el codificador de su nombre y su revisión, sin red (069:RF-4, RF-5)."""
    if meta.get('etiquetas') != list(ETIQUETAS) or meta.get('tareas') != tareas_del_modelo():
        raise ValueError('contrato de tareas o entidades incompatible')
    datos = meta['codificador']
    disp = dispositivo
    codificador = obtener_codificador(datos['nombre'], datos['revision'], disp)
    cfg = Configuracion(**meta['cfg'])
    if datos.get('tramo'):                                                           # 079:RF-18 a RF-21
        red, codificador = _abrir_tramo(meta, pesos, cfg, codificador, disp)
    else:
        red = construir_cabezas(int(datos['dim']), len(meta['tareas']), len(meta['etiquetas']), cfg)
        red.load_state_dict(pesos)
        red.to(disp).eval()
    regla = meta.get('regla_charla') or {}
    return ModeloCodificador(red, codificador, list(meta['tareas']), cfg, version or meta.get('version', ''),
                             float(meta.get('temperatura', 1.)), float(meta.get('umbral', UMBRAL_HEREDADO)),
                             puesto_charla=regla.get('puesto'), piso_charla=float(regla.get('piso', 0.)))
