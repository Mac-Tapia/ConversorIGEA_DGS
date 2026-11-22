"""045:RF-8, RF-9 — ablaciones del gemelo y dominio antes de inferir.

Las ablaciones dicen qué aporta cada parte: la física sola, la red sin término físico, el híbrido
vigente y PowerFlowNet, con los mismos ejemplos, semillas y presupuesto. Si un brazo no se puede
ejecutar queda como no disponible, con su motivo: nunca se sustituye por otro ni cae a la CPU.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
import time
from typing import Any

import numpy as np

from ...aplicacion.evaluacion_modelos import Particiones, alcance_de, evaluar_candidato, huella
from ...aplicacion.experimentos import ExperimentoSpec
from .buffer import BuferEpisodios
from .contratos_fisicos import VERSION_GRAFO
from .oraculo import (
    Entrenamiento,
    ModeloMallado,
    Muestra,
    OraculoPINN,
    Puertas,
    SinGPU,
    denominadores,
    elegir_exponente,
    entrenar_miembro,
    guardar_y_reabrir,
    mae,
    metricas_de_prueba,
    motivos_de_dominio,
    particiones_del_bufer,
    muestra,
    muestra_de_episodio,
    politica_pinn,
    red_de,
)
from ...dominio.util import cuenta

#: Parte de ``evaluacion_modelos.Particiones`` → la del entrenamiento del gemelo.
PARTE_DEL_GEMELO = {'entrenamiento': 'entrenamiento', 'seleccion': 'validacion',
                    'calibracion': 'calibracion', 'prueba': 'prueba'}


def comprobar_dominio(grafo: Mapping[str, Any], model_manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Si un modelo puede opinar de esta red, antes de inferir (045:RF-9).

    Estar dentro permite ordenar candidatos, no aceptar un diseño: eso sigue siendo de DIgSILENT.
    """
    dominio = model_manifest.get('dominio')
    m = muestra(grafo)
    bloqueos = motivos_de_dominio(m, dominio) if dominio else [*m.bloqueos, 'el modelo no declara su dominio']
    return {'dentro': not bloqueos, 'bloqueos': bloqueos, 'confirmar_en_pf': True}


def _powerflownet_disponible() -> str | None:
    """Por qué no se puede ejecutar el brazo PowerFlowNet; ``None`` si se puede. Su ausencia no rompe nada."""
    try:
        import torch_geometric  # noqa: F401

        from ..upstream_ia import verificar_repositorio

        verificar_repositorio('powerflownet')
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        return f'PowerFlowNet no disponible: {exc}'
    return None


def _ajustar_conjunto(grupos: Mapping[str, Sequence[Muestra]], cfg: Entrenamiento, semillas: Sequence[int],
                      dominio: Mapping[str, Any], log: Callable[[str], None]) -> tuple[OraculoPINN, list]:
    estados, terminos = [], []
    for semilla in semillas:
        terminos.append([])
        estados.append(entrenar_miembro(grupos['entrenamiento'], Entrenamiento(**{**cfg.__dict__, 'semilla': semilla}),
                                        None, log, validacion=grupos['validacion'], terminos=terminos[-1]))
    return OraculoPINN(estados, cfg, dict(dominio)), terminos


def _vram_mb() -> float | None:
    """El pico de memoria de la GPU desde el último brazo; ``None`` sin ella."""
    try:
        import torch

        return float(torch.cuda.max_memory_allocated() / 1024 ** 2) if torch.cuda.is_available() else None
    except ImportError:
        return None


def _vaciar_vram() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except ImportError:
        pass


def particiones_del_contrato(experimento: ExperimentoSpec, bufer: BuferEpisodios) -> Particiones:
    """Las particiones de la ablación: las de siempre o, si el contrato declara ``politica.redes_de_prueba`` (prefijos
    de la huella de red), esas redes enteras a prueba (045:RF-18). Va en el contrato, que entra en su huella, y no en el
    perfil de la empresa: es una decisión del experimento."""
    redes = (experimento.politica or {}).get('redes_de_prueba')
    if redes is None:
        return particiones_del_bufer(bufer)
    if isinstance(redes, str) or not all(isinstance(r, str) and r for r in redes):
        raise ValueError('politica.redes_de_prueba debe ser una lista de prefijos de huella de red')
    return particiones_del_bufer(bufer, redes_de_prueba=list(redes))


def comparar_fisicas(experimento: ExperimentoSpec, particiones: Particiones, *, bufer: BuferEpisodios | None = None,
                     cfg: Entrenamiento | None = None, puertas: Puertas | None = None, ajustar: Callable | None = None,
                     log: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """Los cuatro brazos con los mismos identificadores, semillas y presupuesto (045:RF-8).

    ``ajustar(grupos, cfg, semillas, dominio, log) -> (modelo, terminos)`` entrena un brazo con red; por
    defecto, en la GPU. No promueve: el informe compara, y cada brazo pasa las puertas de 044 sin bajarlas.
    """
    bufer = bufer or BuferEpisodios()
    ajustar = ajustar or _ajustar_conjunto
    puertas = puertas or Puertas()
    grupos: dict[str, list[Muestra]] = {}
    ids_por_parte: dict[str, list[str]] = {}
    fuera: list[str] = []
    for parte, destino in PARTE_DEL_GEMELO.items():
        ids = list(getattr(particiones, parte))
        ids_por_parte[destino] = ids
        grupos[destino] = []
        for i in ids:
            m = muestra_de_episodio(bufer.leer(i))
            if m is None:
                fuera.append(i)
            else:
                grupos[destino].append(m)
    if fuera:
        # Comparar con menos ejemplos que los declarados no sería comparar sobre las mismas particiones.
        return {'completo': False, 'status': 'BLOQUEADO_POR_DATOS', 'evaluation_completed': False,
                'motivo': f'{cuenta(len(fuera), "episodio de las particiones no enseña", "episodios de las particiones no enseñan")}', 'episodios_fuera': fuera}
    base = cfg or Entrenamiento()
    prueba = grupos['prueba']
    exponente = elegir_exponente(grupos['entrenamiento'], fisica=base.fisica)
    # 045:RF-15, RF-16: el mismo tope de residuo que la puerta, en la selección por validación y en la predicción.
    base = Entrenamiento(**{**base.__dict__, 'exponente_carga': exponente, 'residuo_tope': puertas.residuo_max})
    x_all = np.concatenate([m.x for m in grupos['entrenamiento']])
    dominio = {'x_min': x_all.min(axis=0).tolist(), 'x_max': x_all.max(axis=0).tolist(),
               'nodos': [min(len(m.ids) for m in grupos['entrenamiento']), max(len(m.ids) for m in grupos['entrenamiento'])],
               'redes': sorted({red_de(m) for ms in grupos.values() for m in ms}), 'version_grafo': VERSION_GRAFO}
    fisica = ModeloMallado(exponente=exponente)
    politica = politica_pinn(puertas, base, None if alcance_general(grupos) else 'por_sistema')
    semillas = tuple(experimento.semillas)
    presupuesto = {'epocas': base.epocas, 'paciencia': base.paciencia, 'cada': base.cada, 'ocultas': base.ocultas,
                   'pasos': base.pasos, 'lr': base.lr, 'semillas': list(semillas)}

    def medir(modelo, nombre: str, terminos: list, inicio: float) -> dict[str, Any]:
        metricas, latencia = metricas_de_prueba(modelo, prueba, fisica)
        # 045:RF-9: el brazo se mide como se usa (fuera de dominio, la física); se dice cuántos ejemplos quedaron fuera y
        # lo que la red habría dicho en ellos, para que el respaldo no esconda nada (T6 del 2026-11-21).
        dominio_del_modelo = getattr(modelo, 'dominio', None)
        fuera = [m for m in prueba if isinstance(dominio_del_modelo, Mapping) and motivos_de_dominio(m, dominio_del_modelo)]
        # Solo el oráculo con su ``predecir`` sabe dar la predicción cruda; un doble o una física dan la que miden.
        con_respaldo = isinstance(modelo, OraculoPINN) and type(modelo).predecir is OraculoPINN.predecir
        crudo = mae(_Crudo(modelo), prueba) if con_respaldo else metricas['global']['mae_v']
        return {'estado': 'evaluado', 'brazo': nombre, 'mae_v': metricas['global']['mae_v'],
                'ejemplos_fuera_de_dominio': len(fuera), 'mae_v_sin_respaldo': crudo,
                'residuo': metricas['global']['residuo'],
                'por_familia': metricas['familias'], 'veredicto': evaluar_candidato(metricas, politica),
                'latencia_s_por_red': latencia, 'tiempo_s': time.perf_counter() - inicio, 'vram_mb': _vram_mb(),
                'terminos_por_epoca': terminos, 'ids_evaluados': [ids_por_parte['prueba']]}

    brazos: dict[str, Any] = {}
    brazos['fisica_pura'] = medir(fisica, 'fisica_pura', [], time.perf_counter())
    configuraciones = {'red_sin_fisica': Entrenamiento(**{**base.__dict__, 'peso_fisico': 0.0}), 'hibrido_vigente': base,
                       'powerflownet': Entrenamiento(**{**base.__dict__, 'arquitectura': 'powerflownet'})}
    for nombre, c in configuraciones.items():
        motivo = _powerflownet_disponible() if nombre == 'powerflownet' else None
        if motivo:
            brazos[nombre] = {'estado': 'no_disponible', 'brazo': nombre, 'motivo': motivo}
            continue
        _vaciar_vram()
        inicio = time.perf_counter()
        try:
            log(f'Ablación {nombre}: {cuenta(len(semillas), "semilla", "semillas")} sobre las mismas particiones')
            modelo, terminos = ajustar(grupos, c, semillas, dominio, log)
            brazos[nombre] = medir(modelo, nombre, terminos, inicio)
            if isinstance(modelo, OraculoPINN):
                # Sin promover: el artefacto queda con su informe y el puntero en uso no se toca.
                brazos[nombre]['reapertura'] = guardar_y_reabrir(
                    modelo, bufer, {'ablacion': nombre, 'experimento': experimento.huella}, prueba[0])
        except SinGPU as exc:
            # Nunca a la CPU: el brazo queda sin medir y el informe, incompleto.
            brazos[nombre] = {'estado': 'no_disponible', 'brazo': nombre, 'motivo': str(exc)}
    obligatorios = ('fisica_pura', 'red_sin_fisica', 'hibrido_vigente')
    return {'schema_version': 1, 'status': 'EVALUADO', 'evaluation_completed': True,
            'completo': all(brazos[b]['estado'] == 'evaluado'
                            and brazos[b].get('reapertura', {'ok': True}).get('ok') is True for b in obligatorios),
            'experimento': experimento.huella, 'politica_particiones': particiones.politica_hash,
            'politica': asdict(politica), 'alcance': alcance_de(politica), 'presupuesto': presupuesto,
            'version_grafo': VERSION_GRAFO, 'particiones_ids': ids_por_parte,
            'huella_particiones': huella(ids_por_parte), 'unidades': {'mae_v': 'p.u.', 'residuo': 'p.u.',
                                                                       'latencia_s_por_red': 's', 'vram_mb': 'MB'},
            'denominadores': denominadores(grupos), 'brazos': brazos, 'eleccion': eleccion_en_uso(brazos),
            'redes_de_prueba_declaradas': list((experimento.politica or {}).get('redes_de_prueba') or [])}


def eleccion_en_uso(brazos: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Qué brazo quedaría en uso con este informe (045:RF-17): el de menor error entre los que pasan las puertas de
    044, y la física si ninguno con red las pasa. Lo que decide en uso es la promoción; esto lo dice con la misma regla.

    En la ablación del 2026-11-21 solo la física pasaba: el híbrido quedaba a 5,25·10⁻⁴ p.u. frente a 2,07·10⁻⁴.
    """
    aprobados = [(float(b['mae_v']), k != 'fisica_pura', k) for k, b in brazos.items()
                 if b.get('estado') == 'evaluado' and (b.get('veredicto') or {}).get('approved') is True
                 and b.get('mae_v') is not None]
    if not aprobados:
        return {'brazo': 'fisica_pura', 'motivo': 'ningún brazo pasa las puertas de 044: decide el flujo físico'}
    _error, _con_red, elegido = min(aprobados)
    rechazados = sorted(k for k, b in brazos.items() if b.get('estado') == 'evaluado'
                        and (b.get('veredicto') or {}).get('approved') is not True)
    motivo = ('solo la física pasa las puertas de 044' if elegido == 'fisica_pura' and not any(c for _e, c, _k in aprobados)
              else 'menor error de tensión entre los que pasan las puertas de 044')
    return {'brazo': elegido, 'motivo': motivo, 'rechazados': rechazados}


class _Crudo:
    """El oráculo sin el respaldo físico fuera de dominio: lo que la red habría dicho (045:RF-9)."""

    def __init__(self, modelo: OraculoPINN):
        self.modelo = modelo

    def predecir(self, grafo: Mapping[str, Any]) -> dict[str, Any]:
        return self.modelo.predecir(grafo, respaldo_fisico=False)


def alcance_general(grupos: Mapping[str, Sequence[Muestra]]) -> bool:
    """Si la prueba es de redes que no se ajustaron: solo entonces se habla de generalizar (027:RF-68)."""
    ajustadas = {red_de(m) for parte in ('entrenamiento', 'validacion', 'calibracion') for m in grupos[parte]}
    return not ajustadas & {red_de(m) for m in grupos['prueba']}
