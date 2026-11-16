"""Benchmarks de referencia anonimizados y reproducibles (spec 112).

Se generan en local desde los datos reales y no revelan nada de la empresa: identificadores seudonimizados,
coordenadas de un trazado sintético por el grafo, longitudes perturbadas y solo las columnas de una lista cerrada.
Ningún módulo de aquí abre la red.

:func:`generar_benchmark` es la única vía de emisión (P6): escribe en una carpeta temporal junto al destino, reproduce el
estudio (RF-3, RF-11), pasa el control de reidentificación (RF-4) con el manifiesto ya escrito (RF-5) y solo entonces
publica con ``os.replace``. Si algo falla no queda nada a medias. La semilla de los seudónimos se guarda en el equipo,
nunca en el destino (RF-12).

Lo que deriva de una red real es de **uso local**: su huella de longitudes la identifica aunque se perturbe (aclaración
de RF-13 y RF-14). :func:`publicar` lo rechaza; lo publicable es la red sintética de
:func:`publicable.generar_publicable`.
"""
from __future__ import annotations

import os
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ..perfil_empresa import PerfilEmpresa


class NoPublicable(ValueError):
    """Un benchmark de uso local (derivado de una red real) no sale por la vía de publicación (112:RF-14)."""


def generar_benchmark(red: Path | str, carga: Path | str, equipo: Path | str, destino: Path | str, *,
                      semilla: int | None = None, dataset_089: Path | str | None = None,
                      perfil: PerfilEmpresa | None = None, ruta_perfil: Path | str | None = None,
                      tolerancia: Mapping[str, Any] | None = None, textos: Iterable[str] = (),
                      raiz: Path | None = None,
                      geometria_publica: Iterable[Path | str] | None = None) -> dict[str, Any]:
    """Genera en ``destino`` el benchmark del trío (y de las series del 089, si se da su carpeta). Devuelve el manifiesto.

    ``semilla`` es la secreta de los seudónimos (sin ella se sortea una); ``ruta_perfil`` da los términos de la empresa
    que el control busca; ``textos`` son otros textos del origen (libros, informes) que no pueden aparecer.

    La red sale con el trazado sintético y las longitudes perturbadas ±5 %; si el estudio no se reproduce, la amplitud
    se recorta a la mitad (hasta :data:`geometria.INTENTOS_RECORTE` veces) y, si aun así no, no se emite (RF-14).
    Con ``geometria_publica`` (el trío de la red que la empresa publica en el VNR-GIS, ver
    :mod:`geometria_publica`), el manifiesto declara cuántos alimentadores cuadran con ella por ICP (T14).
    """
    from . import geometria as G
    from . import manifiesto as M
    from . import redes as R
    from . import reidentificacion, reproduccion
    from . import series as S
    from .semilla import guardar_secreta, nueva_semilla, semilla_publica, validar_secreta
    from .seudonimos import Mapa

    destino = Path(destino)
    if destino.exists():
        raise FileExistsError(f'{destino.name} ya existe: un benchmark emitido no se sobrescribe')
    semilla = validar_secreta(semilla) if semilla is not None else nueva_semilla()
    trio = (Path(red), Path(carga), Path(equipo))
    huella = M.huella_ficheros(trio)
    ficheros = [R.leer_fichero(r, n) for r, n in zip(trio, R.NOMBRES)]
    completados = R.resolver_tipos(ficheros)
    ds089, huella_089 = S.abrir_089(dataset_089) if dataset_089 is not None else (None, None)

    mapa = Mapa(semilla)
    R.registrar(ficheros, mapa, perfil)
    if ds089 is not None:
        S.registrar(ds089, mapa)
    mapa.congelar()
    alimentadores, largos0, recuadro = R.geometria_del_trio(ficheros)

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.parent / f'.csg-stage-benchmark-{destino.name}'
    if temporal.exists():
        shutil.rmtree(temporal)
    try:
        neutro = R.perfil_neutro(perfil)
        amplitud = G.AMPLITUD_POR_DEFECTO
        for _intento in range(G.INTENTOS_RECORTE):
            if temporal.exists():
                shutil.rmtree(temporal)
            temporal.mkdir()
            nuevos = G.perturbar(largos0, semilla=semilla, amplitud=amplitud)
            efectivos = {t: float(nuevos.get(t, largo)) for t, (largo, _tipo) in largos0.items()}
            coords, inter = G.trazar(alimentadores, efectivos, recuadro)
            omitidas, fuera = R.escribir(ficheros, temporal, mapa, semilla=semilla, perfil=perfil,
                                         coordenadas=coords, intermedios=inter, largos=nuevos)
            rep = reproduccion.reproducir_red(trio, temporal, mapa=mapa, perfil=perfil, perfil_neutro=neutro,
                                              tolerancia=tolerancia)
            if rep.reproduce:
                break
            amplitud /= 2
        else:
            raise reproduccion.ReproduccionFallida(
                'la perturbación de longitudes saca el estudio de la tolerancia aun recortada '
                f'{G.INTENTOS_RECORTE} veces, en ' + ', '.join(sorted({m.elemento for m in rep.motivos})[:20]))
        bench = G.largos_por_alimentador([R.leer_fichero(temporal / n, n) for n in R.NOMBRES])
        pares = {red_id: str(mapa('alimentador', red_id)) for red_id, _c, _t in alimentadores}
        pillados = G.identificados(G.largos_por_alimentador(ficheros), bench, amplitud, pares=pares)
        geometria = {'trazado': 'sintetico', 'amplitud': amplitud, 'margen': amplitud,
                     'identificados': len(pillados), 'alimentadores': len(alimentadores)}
        if geometria_publica is not None:
            from .geometria_publica import vertices_por_alimentador
            publica = vertices_por_alimentador(list(geometria_publica))
            geometria['identificados_publica'] = len(G.cuadre_publico(
                vertices_por_alimentador([temporal / n for n in R.NOMBRES]), publica))
        metricas: dict[str, Any] = {'red': {'original': rep.metricas_original, 'benchmark': rep.metricas_benchmark}}
        if ds089 is not None:
            S.escribir(ds089, temporal, mapa, semilla=semilla)
            rs = reproduccion.exigir(reproduccion.reproducir_series(ds089, temporal, mapa=mapa, tolerancia=tolerancia))
            metricas['series'] = {'original': rs.metricas_original, 'benchmark': rs.metricas_benchmark}
        manifiesto = M.construir(huella_origen=huella, huella_089=huella_089, semilla_publica=semilla_publica(semilla),
                                 columnas_omitidas=omitidas, secciones_omitidas=fuera,
                                 tipos_completados=len(completados), tolerancia=rep.tolerancia, perfil_neutro=neutro,
                                 metricas=metricas, carpeta=temporal, con_series=ds089 is not None,
                                 geometria=geometria)
        M.escribir(temporal, manifiesto)
        origen = reidentificacion.Origen.desde(red=ficheros, series=ds089, perfil=ruta_perfil, textos=textos,
                                               semilla=semilla)
        reidentificacion.exigir_limpio(reidentificacion.revisar(temporal, origen))
        guardar_secreta(huella, semilla, raiz=raiz)
        os.replace(temporal, destino)
    except BaseException:
        shutil.rmtree(temporal, ignore_errors=True)
        raise
    return manifiesto


def publicar(carpeta: Path | str, destino: Path | str) -> Path:
    """Copia un benchmark publicable a ``destino``. Lo de uso local se rechaza: su huella de longitudes lo delata."""
    import json

    from .manifiesto import NOMBRE
    carpeta, destino = Path(carpeta), Path(destino)
    manifiesto = json.loads((carpeta / NOMBRE).read_text(encoding='utf-8'))
    if manifiesto.get('uso_local', True):
        raise NoPublicable('este benchmark es de uso local: deriva de una red real y su huella de longitudes la '
                           'identifica; publique el sintético de generar_publicable')
    if destino.exists():
        raise FileExistsError(f'{destino.name} ya existe')
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.parent / f'.csg-stage-publicar-{destino.name}'
    if temporal.exists():
        shutil.rmtree(temporal)
    try:
        shutil.copytree(carpeta, temporal)
        os.replace(temporal, destino)
    except BaseException:
        shutil.rmtree(temporal, ignore_errors=True)
        raise
    return destino
