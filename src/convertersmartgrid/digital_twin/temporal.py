"""Gemelo temporal: la demanda del mes, hora a hora o cada 15 minutos (spec 024, T12).

Una red recurrente (GRU) aprende la curva de cada cabecera y la reproduce un paso por
delante (RF-20, RF-37); comparada con lo medido, dice cuándo y en qué alimentador el
gemelo se aparta y cuánto aporta cada uno a la desviación (RF-21). Con la medida de la
barra de la SET, reparte lo que falta entre los alimentadores sin medidor por su potencia
instalada, descontando clientes fijos y pérdidas, con su intervalo y siempre marcado como
estimado (RF-22). El instante crítico es el de máxima coincidente: ahí se evalúan las
alternativas, no solo en la máxima de cada uno (RF-37).

Sin PyTorch, ``ModeloEstacional`` (el mismo instante del día anterior) cumple el contrato.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

#: Puntos por día con medidas cada 15 minutos.
PUNTOS_DIA = 96
_AVISO_SIN_GRU = ('Se siguió sin el modelo temporal, porque {motivo}: la curva se reprodujo con el mismo instante '
                  'del día anterior.')


@dataclass
class ModeloEstacional:
    """Predice cada punto con el mismo instante del día anterior."""

    periodo: int = PUNTOS_DIA
    nombre: str = 'estacional'
    #: 086:RF-27: por qué se usa este y no la GRU, cuando alguien la quería; lo lee el operador.
    aviso: str | None = None

    def reproducir(self, serie: Sequence[float]) -> np.ndarray:
        s = np.asarray(serie, dtype=float)
        out = np.full_like(s, np.nan)
        out[self.periodo:] = s[:-self.periodo]
        return out


class GemeloGRU:
    """GRU que predice el punto siguiente a partir de la ventana anterior (RF-20, RF-37)."""

    nombre = 'gru'

    def __init__(self, ventana: int = PUNTOS_DIA, ocultas: int = 32, epocas: int = 40, semilla: int = 0,
                 paciencia: int = 8, recorte: float = 1.0, fraccion_validacion: float = 0.2):
        import torch

        self.torch = torch
        self.ventana, self.ocultas, self.epocas, self.semilla = ventana, ocultas, epocas, semilla
        self.paciencia, self.recorte, self.fraccion_validacion = paciencia, recorte, fraccion_validacion
        self.escala = 1.0
        self.validacion: dict[str, Any] = {}
        from .oraculo import dispositivo

        self.disp = dispositivo()          # solo en la GPU, como la PINN
        torch.manual_seed(semilla)
        nn = torch.nn

        class Red(nn.Module):
            def __init__(self):
                super().__init__()
                self.gru = nn.GRU(2, ocultas, batch_first=True)
                self.salida = nn.Linear(ocultas, 1)

            def forward(self, x):
                h, _ = self.gru(x)
                return self.salida(h[:, -1, :]).squeeze(-1)

        self.red = Red().to(self.disp)

    def _entradas(self, s: np.ndarray, inicio: int) -> np.ndarray:
        """Ventana con el valor y la hora del día (seno), para que aprenda la forma diaria."""
        idx = np.arange(inicio, inicio + self.ventana)
        hora = np.sin(2 * np.pi * (idx % PUNTOS_DIA) / PUNTOS_DIA)
        return np.stack([s[inicio:inicio + self.ventana], hora], axis=1)

    def configuracion(self) -> dict:
        """060:RF-6: parámetros completos necesarios para reabrir el mismo alumno."""
        return {k: getattr(self, k) for k in ('ventana', 'ocultas', 'epocas', 'semilla',
                                             'paciencia', 'recorte', 'fraccion_validacion')}

    def entrenar(self, serie: Sequence[float]) -> float:
        """Entrena con la primera parte de la serie y valida con la última (027:RF-11): una
        partición al azar dejaba ver a la red el día siguiente al que predecía. Para tras
        ``paciencia`` épocas sin mejorar, con coseno y recorte del gradiente (027:RF-5, RF-6),
        y deja en ``validacion`` su error y el del estacional en esa misma parte."""
        torch = self.torch
        s = np.asarray(serie, dtype=float)
        if s.ndim != 1 or not np.isfinite(s).all():
            raise ValueError('la serie de entrenamiento debe ser un vector finito sin huecos')
        if not 0 <= self.fraccion_validacion < 1:
            raise ValueError('fraccion_validacion debe estar entre 0 y 1, sin incluir 1')
        n = len(s) - self.ventana
        if n <= 0:
            raise ValueError(f'hacen falta más de {self.ventana} puntos para entrenar')
        n_val = int(n * self.fraccion_validacion) if n * self.fraccion_validacion >= 1 else 0
        n_ent = n - n_val
        # 046:RF-1: la primera etiqueta de validación está en ventana+n_ent.
        # Un pico posterior no debe alterar la representación de los datos anteriores.
        corte = self.ventana + n_ent
        self.escala = float(np.max(np.abs(s[:corte]))) or 1.0
        s = s / self.escala
        x = torch.tensor(np.stack([self._entradas(s, i) for i in range(n)]), dtype=torch.float32, device=self.disp)
        y = torch.tensor(s[self.ventana:], dtype=torch.float32, device=self.disp)
        opt = torch.optim.Adam(self.red.parameters(), lr=1e-2)
        plan = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(self.epocas, 1), eta_min=1e-4)
        perdida = torch.tensor(0.0)
        mejor, mejor_estado, mejor_epoca, epoca = np.inf, None, -1, -1
        self.historial = []
        self.optimizer_updates = 0
        for epoca in range(self.epocas):
            for lote in torch.split(torch.randperm(n_ent, device=self.disp), 256):
                perdida = ((self.red(x[lote]) - y[lote]) ** 2).mean()
                opt.zero_grad()
                perdida.backward()
                torch.nn.utils.clip_grad_norm_(self.red.parameters(), self.recorte)
                opt.step()
                self.optimizer_updates += 1
            plan.step()
            fila = {'epoca': epoca + 1, 'perdida_mse_normalizada': float(perdida.detach()),
                    'lr_siguiente': opt.param_groups[0]['lr'], 'optimizer_updates': self.optimizer_updates}
            self.historial.append(fila)
            if not n_val:
                continue
            with torch.no_grad():
                err = float((self.red(x[n_ent:]) - y[n_ent:]).abs().mean())
            fila['mae_validacion_kw'] = err * self.escala
            if err < mejor - 1e-12:
                mejor, mejor_epoca = err, epoca
                mejor_estado = {k: v.detach().clone() for k, v in self.red.state_dict().items()}
            elif epoca - mejor_epoca >= self.paciencia:
                break
        if mejor_estado is not None:
            self.red.load_state_dict(mejor_estado)
        if n_val:
            cola = slice(self.ventana + n_ent, len(s))
            est = ModeloEstacional().reproducir(s)[cola]
            ok = ~np.isnan(est)
            mae_est = float(np.abs(est[ok] - s[cola][ok]).mean()) * self.escala if ok.any() else np.inf
            self.validacion = {'mae_kw': mejor * self.escala, 'mae_estacional_kw': mae_est,
                               'mejor_epoca': mejor_epoca, 'epocas': epoca + 1,
                               'supera_estacional': bool(mejor * self.escala < mae_est)}
        return float(perdida.detach()) * self.escala ** 2

    def reproducir(self, serie: Sequence[float]) -> np.ndarray:
        torch = self.torch
        s = np.asarray(serie, dtype=float) / self.escala
        out = np.full(len(s), np.nan)
        n = len(s) - self.ventana
        if n <= 0:
            return out
        x = torch.tensor(np.stack([self._entradas(s, i) for i in range(n)]), dtype=torch.float32, device=self.disp)
        with torch.no_grad():
            out[self.ventana:] = self.red(x).cpu().numpy() * self.escala
        return out


class GemeloGRUMultihorizonte:
    """GRU global que da q05, q50 y q95 de cada paso del horizonte, solo en CUDA (046:RF-13, RF-15).

    ``GemeloGRU`` reconstruye un paso adelante con la curva medida a la vista: no pronostica. Esta
    emite toda la trayectoria desde lo conocido al emitir, y por eso compite con los demás. La
    escala de cada objetivo sale solo de lo anterior al corte (046:RF-1).
    """

    algoritmo = 'gru'
    requiere_gpu = True

    def __init__(self, *, horizonte: int, cadencia_min: int, contexto_pasos: int | None = None, ocultas: int = 64,
                 pasos: int = 1500, lote: int = 128, semilla: int = 0, paciencia: int = 8):
        import torch

        from .oraculo import dispositivo

        self.torch, self.disp = torch, dispositivo()
        self.horizonte, self.cadencia_min, self.ocultas = horizonte, cadencia_min, ocultas
        self.contexto_pasos = contexto_pasos or 2 * 1440 // cadencia_min
        self.pasos, self.lote, self.semilla, self.paciencia = pasos, lote, semilla, paciencia
        self.escalas: dict[str, float] = {}
        self.red = self._crear_red()

    def _crear_red(self):
        torch, horizonte, ocultas = self.torch, self.horizonte, self.ocultas
        torch.manual_seed(self.semilla)

        class Red(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.gru = torch.nn.GRU(5, ocultas, batch_first=True)
                self.salida = torch.nn.Linear(ocultas, horizonte * 3)

            def forward(self, x):
                h, _ = self.gru(x)
                return self.salida(h[:, -1, :]).view(-1, horizonte, 3)

        return Red().to(self.disp)

    def _perdida(self, salida, y):
        q = self.torch.tensor((.05, .5, .95), device=self.disp)
        error = y.unsqueeze(-1) - salida
        return self.torch.maximum(q * error, (q - 1) * error).mean()

    def _tensor(self, contextos: np.ndarray, calendario: np.ndarray):
        x = np.concatenate((contextos[:, :, None], calendario), axis=2)
        return self.torch.tensor(x, dtype=self.torch.float32, device=self.disp)

    def ajustar(self, conjunto, fin_entrenamiento: int, horizonte: int, semilla: int) -> dict:
        """Ventanas al azar de los tramos anteriores al corte; las últimas de cada tramo vigilan
        la parada, para no gastar la partición de selección en ello."""
        from .series_causales import tramos_observados

        torch = self.torch
        if horizonte != self.horizonte:
            raise ValueError('el horizonte de ajuste no es el de la red')
        self.semilla = semilla
        self.red = self._crear_red()
        rng = np.random.default_rng(semilla)
        tam = self.contexto_pasos + horizonte
        series, entrena, vigila = {}, [], []
        for nombre in conjunto.nombres:
            v = conjunto.valores[nombre][:fin_entrenamiento]
            observado = v[np.isfinite(v)]
            if not observado.size:
                continue
            self.escalas[nombre] = float(np.abs(observado).max()) or 1.0
            series[nombre] = v / self.escalas[nombre]
            for a, b in tramos_observados(v, fin_entrenamiento, minimo=tam):
                inicios = [(nombre, i) for i in range(a, b - tam + 1)]
                corte = max(len(inicios) - max(1, len(inicios) // 10), 1)
                entrena += inicios[:corte]
                vigila += inicios[corte:]
        if not entrena:
            raise ValueError('ningún tramo de entrenamiento llega al contexto más el horizonte')
        calendario = conjunto.calendario

        def tanda(muestras):
            filas = [(series[n], i) for n, i in muestras]
            ctx = np.stack([s[i:i + self.contexto_pasos] for s, i in filas])
            cal = np.stack([calendario[i:i + self.contexto_pasos] for _s, i in filas])
            y = np.stack([s[i + self.contexto_pasos:i + tam] for s, i in filas])
            return self._tensor(ctx, cal), torch.tensor(y, dtype=torch.float32, device=self.disp)

        if len(vigila) > 512:
            vigila = [vigila[i] for i in rng.choice(len(vigila), 512, replace=False)]
        xv, yv = tanda(vigila) if vigila else (None, None)
        opt = torch.optim.Adam(self.red.parameters(), lr=1e-3)
        mejor, mejor_estado, sin_mejora, hechos = float('inf'), None, 0, 0
        for paso in range(self.pasos):
            x, y = tanda([entrena[i] for i in rng.integers(0, len(entrena), self.lote)])
            perdida = self._perdida(self.red(x), y)
            opt.zero_grad()
            perdida.backward()
            torch.nn.utils.clip_grad_norm_(self.red.parameters(), 1.0)
            opt.step()
            hechos = paso + 1
            if xv is None or (paso + 1) % 50:
                continue
            with torch.no_grad():
                error = float(self._perdida(self.red(xv), yv))
            if error < mejor - 1e-6:
                mejor, sin_mejora = error, 0
                mejor_estado = {k: t.detach().clone() for k, t in self.red.state_dict().items()}
            else:
                sin_mejora += 1
                if sin_mejora >= self.paciencia:
                    break
        if mejor_estado is not None:
            self.red.load_state_dict(mejor_estado)
        self.red.eval()
        return {'pasos': hechos, 'perdida_vigilancia': None if mejor == float('inf') else mejor}

    def predecir(self, lote) -> np.ndarray:
        torch = self.torch
        contextos, calendario = lote.recorte(self.contexto_pasos)
        escalas = np.array([self.escalas[o] for o in lote.objetivos]) if lote.n else np.zeros(0)
        salida = np.zeros((lote.n, self.horizonte, 3))
        for a in range(0, lote.n, 256):
            b = min(a + 256, lote.n)
            x = self._tensor(contextos[a:b] / escalas[a:b, None], calendario[a:b])
            with torch.no_grad():
                salida[a:b] = self.red(x).cpu().numpy() * escalas[a:b, None, None]
        return np.sort(salida[:, :lote.horizonte], axis=-1)

    def guardar(self, carpeta) -> None:
        import json

        carpeta.mkdir(parents=True, exist_ok=True)
        self.torch.save({k: t.detach().cpu() for k, t in self.red.state_dict().items()}, carpeta / 'pesos.pt')
        (carpeta / 'gru.json').write_text(json.dumps({
            'cfg': {'horizonte': self.horizonte, 'cadencia_min': self.cadencia_min, 'contexto_pasos': self.contexto_pasos,
                    'ocultas': self.ocultas, 'pasos': self.pasos, 'lote': self.lote, 'semilla': self.semilla,
                    'paciencia': self.paciencia},
            'escalas': self.escalas}), encoding='utf-8')

    @classmethod
    def reabrir(cls, carpeta) -> GemeloGRUMultihorizonte:
        import json

        datos = json.loads((carpeta / 'gru.json').read_text(encoding='utf-8'))
        m = cls(**datos['cfg'])
        m.escalas = datos['escalas']
        m.red.load_state_dict(m.torch.load(carpeta / 'pesos.pt', weights_only=True, map_location=m.disp))
        m.red.eval()
        return m


def metricas(medida: Sequence[float], reproducida: Sequence[float]) -> dict[str, float | None]:
    """Error del gemelo frente a lo medido, donde hay las dos (RF-20).

    Sin dato o con todo lo medido en cero el error porcentual no existe y va como ``None``: un NaN no se puede
    guardar en JSON y tiraba el informe entero al acabar de entrenar (GRU de Pisco, 2026-11-08).
    """
    m, r = np.asarray(medida, dtype=float), np.asarray(reproducida, dtype=float)
    ok = ~np.isnan(r)
    if not ok.any():
        return {'mae_kw': None, 'mape_pct': None, 'puntos': 0}
    err = np.abs(m[ok] - r[ok])
    con_base = np.abs(m[ok]) > 1e-9
    mape = float(np.mean(100 * err[con_base] / np.abs(m[ok][con_base]))) if con_base.any() else None
    return {'mae_kw': float(err.mean()), 'mape_pct': mape, 'puntos': int(ok.sum())}


def desviaciones(medidas: Mapping[str, Sequence[float]], reproducidas: Mapping[str, Sequence[float]],
                 instantes: Sequence[datetime], umbral_pct: float) -> list[dict[str, Any]]:
    """Instantes en que el total se aparta más del umbral, con el alimentador que más aporta
    y la contribución de cada uno (RF-21). Cada uno se confirma después en DIgSILENT."""
    nombres = sorted(medidas)
    m = np.array([np.asarray(medidas[a], dtype=float) for a in nombres])
    r = np.array([np.asarray(reproducidas[a], dtype=float) for a in nombres])
    res = np.where(np.isnan(r), 0.0, m - r)
    total_m = m.sum(axis=0)
    out = []
    for t in range(m.shape[1]):
        if np.isnan(r[:, t]).all() or abs(total_m[t]) < 1e-9:
            continue
        dev = abs(res[:, t].sum()) / abs(total_m[t]) * 100
        if dev > umbral_pct:
            aporte = np.abs(res[:, t])
            k = int(np.argmax(aporte))
            out.append({'instante': instantes[t].isoformat(), 'desviacion_pct': float(dev),
                        'alimentador': nombres[k],
                        'contribucion_pct': {a: float(100 * aporte[i] / aporte.sum()) for i, a in enumerate(nombres)},
                        'confirmar_en_pf': True})
    return out


def pseudo_medidas(barra: Sequence[float], medidas: Mapping[str, Sequence[float]],
                   kva: Mapping[str, float], *, fijas_kw: Mapping[str, float] | None = None,
                   perdidas_pct: float = 0.0, sigma_pct: float = 10.0) -> dict[str, dict[str, Any]]:
    """La demanda estimada de cada alimentador sin medidor (RF-22).

    Lo que mide la barra, menos lo medido, menos las pérdidas y los clientes fijos, se
    reparte por potencia instalada; cada estimado lleva su intervalo y nunca pierde la marca
    de estimado. Si lo que queda es negativo, el estimado es 0 y se dice.
    """
    b = np.asarray(barra, dtype=float)
    medido = sum((np.asarray(s, dtype=float) for s in medidas.values()), np.zeros_like(b))
    fijas = dict(fijas_kw or {})
    resto = b * (1 - perdidas_pct / 100) - medido - sum(fijas.values())
    negativos = int((resto < 0).sum())
    resto = np.maximum(resto, 0.0)
    total_kva = sum(kva.values()) or 1.0
    out = {}
    for a, s in sorted(kva.items()):
        serie = resto * s / total_kva + fijas.get(a, 0.0)
        out[a] = {'kw': serie.tolist(), 'inferior': (serie * (1 - sigma_pct / 100)).tolist(),
                  'superior': (serie * (1 + sigma_pct / 100)).tolist(), 'estimada': True,
                  'aviso': (f'{negativos} instante(s) en que lo medido supera a la barra: estimado 0'
                            if negativos else None)}
    return out


def instante_critico(curvas: Mapping[str, Sequence[float]], instantes: Sequence[datetime]) -> dict[str, Any]:
    """El instante de máxima coincidente del conjunto y lo de cada uno en él (RF-37)."""
    total = sum((np.asarray(c, dtype=float) for c in curvas.values()), np.zeros(len(instantes)))
    t = int(np.argmax(total))
    return {'instante': instantes[t].isoformat(), 'total_kw': float(total[t]),
            'por_alimentador': {a: float(np.asarray(c, dtype=float)[t]) for a, c in curvas.items()}}


def elegido(modelo, serie: Sequence[float]):
    """El modelo que se usa para la serie: la GRU entrenada solo si mejora al estacional en la
    última parte de la serie (027:RF-11); si no, el estacional. Con la GPU ocupada falla aquí y no al crearla:
    es lo mismo que no tenerla (086:RF-27)."""
    if hasattr(modelo, 'entrenar'):
        try:
            modelo.entrenar(serie)
        except RuntimeError as exc:
            if 'CUDA' not in str(exc):
                raise
            return ModeloEstacional(aviso=_AVISO_SIN_GRU.format(motivo='la GPU no tuvo memoria libre para entrenarla'))
        if not (getattr(modelo, 'validacion', {}) or {}).get('supera_estacional', False):
            return ModeloEstacional()
    return modelo


def modelo_temporal(**kw):
    """La GRU si hay PyTorch y GPU; si no, el estacional (mismo contrato ``reproducir``), y lo dice (086:RF-27).

    Sin CUDA, ``SinGPU`` hacía fallar el trabajo entero. La GRU no se entrena en la CPU, regla del proyecto
    (024:RF-44): lo que sigue es el estacional, que no entrena nada.
    """
    from .oraculo import SinGPU

    try:
        return GemeloGRU(**kw)
    except ImportError:
        return ModeloEstacional(aviso=_AVISO_SIN_GRU.format(motivo='este equipo no tiene el complemento de IA'))
    except SinGPU:
        return ModeloEstacional(aviso=_AVISO_SIN_GRU.format(motivo='este equipo no tiene una GPU disponible'))
