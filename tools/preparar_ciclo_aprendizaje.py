#!/usr/bin/env python
"""Manifiestos reales del ciclo común de aprendizaje (spec 050, T6): procedencia, contexto y cuarentena.

Lee el dataset v2, las observaciones originales, el búfer del gemelo, el libro de cabeceras, el
corpus sellado y los casos evolutivos, sin escribir en ellos, y deja en una carpeta nueva lo que
``aprendizaje_continuo.py`` exige en la instantánea. Lo que no tiene procedencia demostrable va a
cuarentena con su motivo: aquí no se le fabrica una.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))

ESQUEMA_COMPLEMENTO = 'convertersmartgrid-learning-context-complement-v1'
SEMILLAS = '11,23,37,53,71'
MODELO_EMBEDDINGS = 'intfloat/multilingual-e5-base'
#: Lo que deja sin preparar la falta de cada ruta (050:RF-21).
FAMILIAS_DE_FUENTE = {'dataset': ['transformer', 'clasificador', 'embeddings'],
                      'twin': ['pinn', 'evolutivos'], 'cabeceras': ['gru'],
                      'llm_dataset': ['qlora'], 'evolutivos_casos': ['evolutivos']}
#: Los campos del contexto 043 que el episodio no garantiza y puede aportar un complemento.
CAMPOS_COMPLEMENTO = ('year', 'period', 'criterio_fijas', 'profile_hash')


def _sha(ruta: Path) -> str:
    with ruta.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _sellado(manifiesto: Path) -> str:
    """050:RF-17: la fecha de sellado, con zona; un corpus redactado no tiene otra."""
    return datetime.fromtimestamp(manifiesto.stat().st_mtime, timezone.utc).isoformat()


def _referencia(contexto: str, fuente_hash: str, registro_id: str, instante: str, contenido: Any) -> dict:
    from convertersmartgrid.contratos_aprendizaje import huella
    return {'contexto': contexto, 'fuente_hash': fuente_hash, 'registro_id': registro_id,
            'instante': instante, 'contenido_hash': huella(contenido)}


class Preparacion:
    """Lo que se va reuniendo; cada fuente añade sus referencias y sus motivos."""

    def __init__(self, salida: Path, complemento: dict):
        self.salida = salida
        self.complemento = complemento
        self.referencias: dict[str, dict] = {}
        self.cuarentena: list[dict] = []
        self.proyectos: dict[str, str] = {}
        self.documentos: dict[str, str] = {}
        self.fuentes: dict[str, str] = {}
        self.pendientes: dict[str, dict] = {}
        self.informe: dict[str, Any] = {}

    def apartar(self, fuente: str, registro: str, motivo: str) -> None:
        self.cuarentena.append({'fuente': fuente, 'registro': registro, 'motivo': motivo})

    def pendiente(self, fuente: str, motivo: str) -> None:
        self.pendientes[fuente] = {'motivo': motivo, 'familias': FAMILIAS_DE_FUENTE.get(fuente, [])}


# ------------------------------------------------------------------ identidad 043

def leer_complemento(ruta: Path | None) -> dict:
    """050:RF-13: lo que el episodio no trae solo lo declara su responsable, y se valida."""
    if ruta is None:
        return {'proyectos': {}, 'series': {}}
    dato = json.loads(ruta.read_text(encoding='utf-8'))
    if (not isinstance(dato, dict) or dato.get('schema') != ESQUEMA_COMPLEMENTO
            or not isinstance(dato.get('proyectos', {}), dict) or not isinstance(dato.get('series', {}), dict)):
        raise ValueError(f'{ruta.name}: complemento sin el esquema {ESQUEMA_COMPLEMENTO}')
    if not str(dato.get('declarado_por') or '').strip():
        raise ValueError(f'{ruta.name}: complemento sin declarado_por; lo declarado tiene responsable (050:RF-25)')
    for proyecto, campos in dato.get('proyectos', {}).items():
        if not isinstance(campos, dict) or set(campos) - {*CAMPOS_COMPLEMENTO, 'origen'}:
            raise ValueError(f'{proyecto}: el complemento solo admite {", ".join(CAMPOS_COMPLEMENTO)} y origen')
    return dato


def _informes_de_calibracion(espacios: list[Path]) -> dict[str, list[tuple[float, Path, dict]]]:
    """Por proyecto, los informes de calibración aplicados que traen objetivo y criterio de fijas."""
    por_proyecto: dict[str, list] = {}
    for raiz in espacios:
        for espacio in sorted(p for p in raiz.iterdir() if p.is_dir() and not p.name.startswith('_')):
            for ruta in (*espacio.glob('runs/*/salida/ajuste_cabecera_aplicacion_*.json'),
                         *espacio.glob('salida/ajuste_cabecera_aplicacion_*.json')):
                try:
                    d = json.loads(ruta.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                fecha = (d.get('objetivo') or {}).get('fecha')
                if d.get('project') and fecha and d.get('criterio_fijas'):
                    por_proyecto.setdefault(d['project'], []).append(
                        (ruta.stat().st_mtime, ruta, {'period': str(fecha)[:7], 'criterio_fijas': d['criterio_fijas']}))
    return por_proyecto


def generar_complemento(proyectos, espacios: list[Path], perfil: Path, declarado_por: str) -> tuple[dict, dict]:
    """050:RF-25: mes y criterio de la última calibración de cada proyecto, y la huella del perfil vigente."""
    from convertersmartgrid.evaluacion_modelos import huella
    from convertersmartgrid.perfil_empresa import datos_perfil
    informes = _informes_de_calibracion(espacios)
    sha_perfil = huella(datos_perfil(perfil))
    salida, sin_informe = {}, {}
    for proyecto in sorted(proyectos):
        filas = informes.get(proyecto)
        if not filas:
            sin_informe[proyecto] = 'sin informe de calibración aplicado con objetivo y criterio de fijas'
            continue
        _, ruta, campos = max(filas, key=lambda f: f[0])
        salida[proyecto] = {**campos, 'profile_hash': sha_perfil, 'origen': {'calibracion': str(ruta)}}
    return ({'schema': ESQUEMA_COMPLEMENTO, 'declarado_por': declarado_por,
             'profile_hash_nota': (f'huella de {perfil} vigente, declarada al preparar el ciclo; '
                                   'los episodios anteriores a 050:RF-23 no la capturaron'),
             'proyectos': salida, 'series': {}}, sin_informe)


def _periodo(valor: Any) -> Any:
    """La lectura nativa guarda el periodo como ``{clientes, maxima, status}``; el contexto usa el de la cabecera."""
    return valor.get('maxima') if isinstance(valor, dict) else valor


def contexto_de_episodio(e, complemento: dict):
    """050:RF-13/14: ``(ContextoExperimento, None)`` con los 14 campos, o ``(None, motivo)``."""
    from convertersmartgrid.experimentos import ContextoExperimento
    fisico = e.contexto_fisico
    if fisico is None:
        return None, 'identidad 043 incompleta: el episodio no trae contexto_fisico'
    if 'ausente' in fisico:
        return None, f'identidad 043 incompleta: {fisico["ausente"]}'
    proyecto = str(e.nativo.get('project') or '')
    declarados = complemento['proyectos'].get(proyecto, {})
    leidos = {'year': fisico.get('year'), 'period': _periodo(fisico.get('period')),
              'criterio_fijas': fisico.get('criterio_fijas'), 'profile_hash': fisico.get('profile_hash')}
    valores = {}
    for campo in CAMPOS_COMPLEMENTO:
        leido, declarado = leidos[campo], declarados.get(campo)
        if leido is not None and declarado is not None and leido != declarado:
            return None, (f'complemento contradice al episodio en {campo}: '
                          f'episodio {leido!r}, declarado {declarado!r}')
        valores[campo] = leido if leido is not None else declarado
    faltan = [c for c in CAMPOS_COMPLEMENTO if c != 'year' and valores[c] is None]
    if faltan:
        return None, f'identidad 043 incompleta: faltan {", ".join(faltan)}'
    try:
        return ContextoExperimento(source_run_id=e.fuente.get('source_run_id'), source_mode=e.fuente.get('source_mode'),
            source_fingerprint=e.fuente.get('source_fingerprint'), project=proyecto,
            feeders=tuple(e.nativo.get('feeders') or ()), case_id=fisico.get('case_id'),
            case_role=fisico.get('case_role'), topology_hash=fisico.get('topology_hash'),
            controls_hash=fisico.get('controls_hash'), scenario_hash=fisico.get('scenario_hash'), **valores), None
    except (TypeError, ValueError) as exc:
        return None, f'identidad 043 inválida: {exc}'


def _anotar_contexto(p: Preparacion, contexto) -> str:
    from convertersmartgrid.experimentos import clave_contexto
    clave = clave_contexto(contexto)
    # Un proyecto tiene varios casos y escenarios, cada uno con su contexto.
    p.proyectos[f'{contexto.project}#{clave[:12]}'] = clave
    return clave


# ------------------------------------------------------------------ dataset v2

def _observaciones(rutas: list[Path]) -> tuple[dict, dict]:
    """``(texto, fecha) → (fichero, huella de la línea)`` de las observaciones originales."""
    indice, ficheros = {}, {}
    for ruta in rutas:
        sha = _sha(ruta)
        ficheros[ruta] = sha
        for linea in ruta.read_text(encoding='utf-8').splitlines():
            if not linea.strip():
                continue
            fila = json.loads(linea)
            if isinstance(fila, dict) and fila.get('texto') and fila.get('fecha'):
                clave = (fila['texto'].strip(), fila['fecha'])
                indice.setdefault(clave, (ruta, hashlib.sha256(linea.encode('utf-8')).hexdigest()))
    return indice, ficheros


def preparar_dataset(p: Preparacion, dataset: Path, observaciones: list[Path]) -> None:
    """050:RF-11/15/17: órdenes e informes contra su observación; consultas contra el dataset sellado."""
    from convertersmartgrid.asistente.dataset_entrenamiento import consultas_recuperacion
    from convertersmartgrid.trabajadores_ml import leer_dataset_v2
    partes, _ = leer_dataset_v2(dataset)
    p.fuentes['dataset'] = str(dataset)
    tabla = p.referencias.setdefault('dataset', {})
    indice, ficheros = _observaciones(observaciones)
    usados = set()
    cuenta = Counter()
    for filas in partes.values():
        for fila in filas:
            if fila.get('tipo') not in ('orden', 'informe'):
                continue
            cuenta[fila['tipo']] += 1
            fecha = (fila.get('provenance') or {}).get('fecha')
            if fila.get('quality') != 'gold_human':
                # 050:RF-26: una plantilla no observa nada: su fuente es la parte del dataset, y sigue siendo maestro.
                continue
            hallada = indice.get((fila['texto'].strip(), fecha)) if fecha else None
            if hallada is None:
                p.apartar('dataset', fila['record_id'],
                          f'{fila["tipo"]} sin observación original con el mismo texto y fecha ({fecha})')
                continue
            ruta, linea = hallada
            usados.add(ruta)
            tabla[fila['record_id']] = _referencia(ficheros[ruta], ficheros[ruta], linea, fecha, fila)
    for i, ruta in enumerate(sorted(usados)):
        p.documentos[f'observaciones_{i}_{ruta.stem}'] = ficheros[ruta]
        p.fuentes[f'observaciones_{i}'] = str(ruta)
    p.informe['dataset'] = {'consumidos': dict(cuenta), 'con_referencia': len(tabla)}
    if not cuenta['informe']:
        p.informe['dataset']['sin_informes'] = 'el dataset no trae registros de informe: clasificador sin muestras'
    manifiesto = _sha(dataset / 'manifest.json')
    instante = _sellado(dataset / 'manifest.json')
    p.documentos['dataset'] = manifiesto
    generados = 0
    for parte, filas in partes.items():
        fuente = _sha(dataset / f'{parte}.jsonl')
        for fila in filas:
            if fila.get('tipo') in ('orden', 'informe') and fila.get('quality') != 'gold_human':
                tabla[fila['record_id']] = _referencia(manifiesto, fuente, fila['record_id'], instante, fila)
                generados += 1
    p.informe['dataset']['generados_con_referencia'] = generados
    for entrenamiento, nombre in ((True, 'retrieval_train'), (False, 'retrieval_test')):
        fichero = dataset / f'{nombre}.jsonl'
        fuente = _sha(fichero) if fichero.is_file() else _sha(dataset / 'train.jsonl')
        try:
            consultas = consultas_recuperacion(dataset, partes, entrenamiento=entrenamiento)
        except ValueError as exc:
            p.apartar('dataset', nombre, f'embeddings: {exc}')
            continue
        for clave, r in consultas:
            tabla[clave] = _referencia(manifiesto, fuente, clave, instante, r)
        p.informe['dataset'][nombre] = len(consultas)
    p.informe['dataset']['instante_consultas'] = {'valor': instante, 'origen': 'fecha de sellado de manifest.json (050:RF-17)'}


# ------------------------------------------------------------------ búfer del gemelo

def preparar_twin(p: Preparacion, twin: Path) -> dict:
    """050:RF-13/15/16: identidad de todo episodio; solo los que enseñan y la tienen van a la vista."""
    from convertersmartgrid.digital_twin.episode import episodio_a_dict, leer_episodio
    from convertersmartgrid.digital_twin.oraculo import por_que_no_ensena
    from convertersmartgrid.experimentos import clave_contexto
    objetos = twin / 'objetos'
    if not objetos.is_dir():
        raise ValueError(f'{twin}: no tiene objetos/ de episodios')
    tabla = p.referencias.setdefault('twin', {})
    no_ensenan, rutas, contextos, creados, ensenan = Counter(), {}, [], {}, {}
    total = 0
    for ruta in sorted(objetos.glob('*/*.json')):
        total += 1
        try:
            e = leer_episodio(json.loads(ruta.read_text(encoding='utf-8')))
        except ValueError as exc:
            p.apartar('twin', ruta.stem, f'episodio inválido: {exc}')
            continue
        contexto, motivo = contexto_de_episodio(e, p.complemento)
        ensena = por_que_no_ensena(e)
        if contexto is not None and e.nativo.get('reopen_verified') is True:
            contextos.append(contexto)
            creados[clave_contexto(contexto)] = e.creado
        if ensena is not None:
            no_ensenan[ensena] += 1
            continue
        if contexto is None:
            p.apartar('twin', e.episode_id, motivo)
            continue
        if e.nativo.get('reopen_verified') is not True:
            p.apartar('twin', e.episode_id, 'episodio que enseña sin reapertura nativa comprobada')
            continue
        # La huella de la fuente combina varios TXT: la fuente custodiable es el objeto inmutable.
        fuente = _sha(ruta)
        tabla[e.episode_id] = _referencia(_anotar_contexto(p, contexto), fuente, e.episode_id,
                                          e.creado, episodio_a_dict(e))
        rutas[e.episode_id] = ruta
        ensenan[e.episode_id] = (e, contexto)
    p.informe['twin'] = {'episodios': total, 'no_ensenan': dict(no_ensenan), 'con_referencia': len(tabla)}
    return {'rutas': rutas, 'contextos': contextos, 'creados': creados, 'ensenan': ensenan}


def escribir_vista(p: Preparacion, rutas: dict[str, Path]) -> None:
    """050:RF-16: copia, no enlace: la vista no puede dar acceso de escritura a los objetos reales."""
    if not rutas:
        p.pendiente('twin', 'ningún episodio que enseña tiene identidad 043 completa; ver cuarentena')
        return
    vista = p.salida / 'vista_twin'
    for eid, ruta in sorted(rutas.items()):
        destino = vista / 'objetos' / ruta.parent.name / ruta.name
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ruta, destino)
    p.fuentes['twin'] = str(vista)


# ------------------------------------------------------------------ cabeceras

def _proyectos_de_twin(twin: Path) -> set[str]:
    """Los proyectos de los episodios que pueden enseñar, para declarar solo lo que se consume."""
    from convertersmartgrid.digital_twin.episode import leer_episodio
    from convertersmartgrid.digital_twin.oraculo import por_que_no_ensena
    proyectos = set()
    for ruta in sorted((twin / 'objetos').glob('*/*.json')):
        try:
            e = leer_episodio(json.loads(ruta.read_text(encoding='utf-8')))
        except ValueError:
            continue
        if por_que_no_ensena(e) is None:
            proyectos.add(str(e.nativo.get('project') or ''))
    return proyectos - {''}


def declarar_series(p: Preparacion, idents, proyecto: str, contextos: list, creados: dict) -> None:
    """050:RF-20/27: el libro de un sistema con el caso base más reciente de su proyecto; sin huellas nuevas."""
    from convertersmartgrid.experimentos import clave_contexto
    propios = [c for c in contextos if c.project == proyecto and c.case_role == 'caso_base']
    if not propios:
        p.apartar('cabeceras', proyecto, 'el proyecto declarado para las series no tiene caso base con identidad 043 completa')
        return
    elegido = max(propios, key=lambda c: creados[clave_contexto(c)])
    for ident in idents:
        p.complemento.setdefault('series', {}).setdefault(ident, clave_contexto(elegido))
    p.informe['series_declaradas'] = {'proyecto': proyecto, 'caso': elegido.case_id, 'contexto': clave_contexto(elegido),
                                      'series': len(idents)}


def _contexto_de_serie(p: Preparacion, ident: str, contextos: list):
    """050:RF-20: la serie se vincula a una identidad 043 única, o se dice por qué no."""
    from convertersmartgrid.demanda_medida import hojas_del_alimentador
    from convertersmartgrid.experimentos import clave_contexto
    declarado = p.complemento['series'].get(ident)
    if declarado is not None:
        candidatos = {clave_contexto(c): c for c in contextos if clave_contexto(c) == declarado}
        if not candidatos:
            return None, f'el complemento declara un contexto que no es de ningún episodio: {declarado}'
    else:
        # La medición es de la red como está: se compara con su caso base, no con un estudio.
        candidatos = {clave_contexto(c): c for c in contextos if c.case_role == 'caso_base'
                      and any(hojas_del_alimentador([ident], f) for f in c.feeders)}
    if len(candidatos) != 1:
        return None, (f'{len(candidatos)} identidades 043 de caso base para la serie; '
                      'se exige una, o declararla en el complemento')
    return next(iter(candidatos.values())), None


def preparar_cabeceras(p: Preparacion, libro: Path, contextos: list, *, zona_horaria: str | None,
                       cadencia_min: int | None, horizontes: str | None, proyecto_series: str | None = None,
                       creados: dict | None = None) -> None:
    """050:RF-11/19/20: una referencia por ventana; lo apartado se reporta con su motivo textual."""
    from convertersmartgrid.digital_twin.temporal_entrenamiento import (
        contenido_de_ventana, series_de_aprendizaje, ventanas_de_aprendizaje)
    p.fuentes['cabeceras'] = str(libro)
    tabla = p.referencias.setdefault('cabeceras', {})
    try:
        series = series_de_aprendizaje(libro, zona_horaria=zona_horaria, cadencia_min=cadencia_min,
                                       horizontes=horizontes)
    except ValueError as exc:
        p.apartar('cabeceras', libro.name, str(exc))
        return
    for apartado in series['apartados']:
        p.apartar('cabeceras', apartado['objetivo'], f'objetivo apartado: {apartado["motivo"]}')
    conjunto = series['conjunto']
    informe = p.informe['cabeceras'] = {
        'series': sorted(conjunto.valores), 'apartados': series['apartados'],
        'guarda_gru': 'muestras_aprendizaje bloquea mientras haya objetivos apartados (050:RF-19)' if series['apartados'] else None}
    if not conjunto.valores:
        return
    informe['por_objetivo'] = cifras_de_ventanas(series, cadencia_min)
    try:
        ventanas = ventanas_de_aprendizaje(series, cadencia_min)
    except ValueError as exc:
        p.apartar('cabeceras', libro.name, str(exc))
        return
    if proyecto_series:
        declarar_series(p, sorted({o.ident for o in conjunto.objetivos.values()}), proyecto_series, contextos, creados or {})
    fuente = _sha(libro)
    sin_contexto = Counter()
    for objetivos in ventanas['partes'].values():
        for nombre, emisiones in objetivos.items():
            contexto, motivo = _contexto_de_serie(p, conjunto.objetivos[nombre].ident, contextos)
            if contexto is None:
                if not sin_contexto[nombre]:
                    p.apartar('cabeceras', nombre, motivo)
                sin_contexto[nombre] += len(emisiones)
                continue
            clave = _anotar_contexto(p, contexto)
            for emision in emisiones:
                registro, contenido = contenido_de_ventana(conjunto, nombre, int(emision),
                    contexto_pasos=series['contexto_pasos'], horizonte_max=series['horizonte_max'])
                tabla[registro] = _referencia(clave, fuente, registro, conjunto.instantes[int(emision)].isoformat(), contenido)
    informe.update(ventanas_con_referencia=len(tabla), ventanas_sin_contexto=dict(sin_contexto))


def cifras_de_ventanas(series: dict, cadencia_min: int) -> dict:
    """Por qué una partición se queda sin ventanas, con cifras: días y emisiones por parte."""
    from convertersmartgrid.digital_twin.evaluacion_temporal import POLITICA_TEMPORAL
    conjunto = series['conjunto']
    try:
        ventanas = conjunto.ventanas_comunes(POLITICA_TEMPORAL, contexto_pasos=series['contexto_pasos'],
            horizonte_max=series['horizonte_max'], paso=60 // cadencia_min)
    except ValueError as exc:
        return {'error': str(exc), 'instantes': len(conjunto.instantes)}
    return {'instantes': len(conjunto.instantes),
            'desde': conjunto.instantes[0].isoformat() if conjunto.instantes else None,
            'hasta': conjunto.instantes[-1].isoformat() if conjunto.instantes else None,
            'emisiones_por_parte': {parte: {n: len(ms) for n, ms in objetivos.items()}
                                    for parte, objetivos in ventanas['partes'].items()},
            'politica_minimos_dias': list(POLITICA_TEMPORAL.minimos)}


# ------------------------------------------------------------------ corpus sellado y evolutivos

def preparar_corpus(p: Preparacion, corpus: Path) -> None:
    """050:RF-11/15/17: cada registro sellado contra su parte; maestro sigue siendo maestro."""
    from convertersmartgrid.asistente.llm_destilacion import PARTICIONES, leer_particion_real
    manifiesto = corpus / 'dataset_manifest.json'
    if not manifiesto.is_file():
        p.pendiente('llm_dataset', f'{corpus}: sin dataset_manifest.json')
        return
    sha = _sha(manifiesto)
    instante = _sellado(manifiesto)
    tabla = p.referencias.setdefault('llm_dataset', {})
    for parte in PARTICIONES:
        try:
            registros, _ = leer_particion_real(corpus, parte)
        except (OSError, ValueError, KeyError) as exc:
            p.apartar('llm_dataset', parte, f'corpus: {exc}')
            continue
        fuente = _sha(corpus / f'{parte}.jsonl')
        for r in registros:
            tabla[r['record_id']] = _referencia(sha, fuente, r['record_id'], instante, r)
    p.documentos['llm_dataset'] = sha
    p.fuentes['llm_dataset'] = str(corpus)
    p.informe['llm_dataset'] = {'con_referencia': len(tabla),
        'instante': {'valor': instante, 'origen': 'fecha de sellado de dataset_manifest.json (050:RF-17)'}}


def preparar_casos(p: Preparacion, casos: Path, twin: Path | None, rutas: dict[str, Path]) -> None:
    """050:RF-13/15: el contexto del caso debe ser el de su episodio; no se acepta otro."""
    from convertersmartgrid.digital_twin.episode import leer_episodio
    from convertersmartgrid.experimentos import ContextoExperimento
    dato = json.loads(casos.read_text(encoding='utf-8'))
    if twin is None:
        p.pendiente('evolutivos_casos', 'los casos necesitan el búfer de sus episodios')
        return
    tabla = p.referencias.setdefault('evolutivos_casos', {})
    for caso in dato.get('casos') or ():
        rid, eid = str(caso.get('record_id')), str(caso.get('episode_id'))
        ruta = twin / 'objetos' / eid[:2] / f'{eid}.json'
        if not ruta.is_file():
            p.apartar('evolutivos_casos', rid, f'episodio {eid} ausente del búfer')
            continue
        e = leer_episodio(json.loads(ruta.read_text(encoding='utf-8')))
        try:
            contexto = ContextoExperimento(**caso['contexto_043'])
        except (KeyError, TypeError, ValueError) as exc:
            p.apartar('evolutivos_casos', rid, f'contexto_043 inválido: {exc}')
            continue
        propio = e.contexto_fisico or {}
        distintos = [c for c in ('topology_hash', 'controls_hash', 'scenario_hash', 'case_id', 'case_role')
                     if getattr(contexto, c) != propio.get(c)]
        distintos += [c for c in ('source_run_id', 'source_mode', 'source_fingerprint')
                      if getattr(contexto, c) != e.fuente.get(c)]
        if contexto.project != e.nativo.get('project') or list(contexto.feeders) != list(e.nativo.get('feeders') or ()):
            distintos.append('project/feeders')
        if distintos:
            p.apartar('evolutivos_casos', rid, f'contexto_043 distinto del episodio en {", ".join(distintos)}')
            continue
        tabla[rid] = _referencia(_anotar_contexto(p, contexto), _sha(ruta), eid, e.creado, caso)
        rutas[eid] = ruta
    p.fuentes['evolutivos_casos'] = str(casos)
    p.informe['evolutivos_casos'] = {'con_referencia': len(tabla)}


def _escaleras_de(espacios: list[Path], proyecto: str) -> list[dict]:
    """Resultados de escalera del proyecto, con el plan del mismo nombre, del más antiguo al más reciente."""
    salida = []
    for raiz in espacios:
        for espacio in sorted(p for p in raiz.iterdir() if p.is_dir() and not p.name.startswith('_')):
            for ruta in espacio.glob('runs/*/salida/escalera_datos_*.json'):
                d = json.loads(ruta.read_text(encoding='utf-8'))
                plan = espacio / 'planes' / ruta.name
                if d.get('project') == proyecto and d.get('alimentadores') and plan.is_file():
                    salida.append((ruta.stat().st_mtime, ruta, d, json.loads(plan.read_text(encoding='utf-8'))))
    return [{'ruta': r, 'datos': d, 'plan': q} for _, r, d, q in sorted(salida, key=lambda f: f[0])]


def _sufijo(identidad: str) -> str:
    """El nombre en DIgSILENT de un identificador del grafo: ``…\\17472.ElmTerm`` → ``17472``."""
    return identidad.rsplit('\\', 1)[-1].rsplit('.', 1)[0]


def _parametros_bancos(e, escalera: dict, limites, perfil: dict) -> tuple[dict | None, str | None]:
    from convertersmartgrid.perfil_empresa import bancos_kvar_por_tension
    nodos = e.topologia['grafo']['nodos']
    por_nombre = {_sufijo(n): n for n in nodos}
    nombres = {b for a in escalera['datos']['alimentadores'].values() for b in (a.get('banco_en') or {}).values()}
    candidatos = sorted(por_nombre[n] for n in nombres if n in por_nombre)
    if not candidatos:
        return None, 'ninguna barra de banco_en de la escalera está en el grafo del episodio'
    tensiones = {nodos[n].get('kv') for n in candidatos}
    modulos = bancos_kvar_por_tension(perfil) or {}
    if len(tensiones) != 1 or next(iter(tensiones)) not in modulos:
        return None, f'el perfil no da un único módulo de banco para las tensiones {sorted(map(str, tensiones))}'
    costo = ((perfil.get('escalera') or {}).get('costos_unitarios') or {}).get('bancos')
    if costo is None:
        return None, 'falta el costo por banco en el perfil (escalera.costos_unitarios.bancos): sin él no hay objetivo de inversión'
    return {'candidatos': candidatos, 'kvar_modulo': modulos[next(iter(tensiones))], 'costo_modulo': costo,
            'origen_costo': 'perfil: escalera.costos_unitarios.bancos',
            'tension_min_pu': escalera['plan']['tension_min_pu'], 'tension_max_pu': limites.tension_max_pu}, None


def _parametros_maniobras(e, escalera: dict, limites) -> tuple[dict | None, str | None]:
    por_nombre = {_sufijo(r['id']): r['id'] for r in e.topologia['grafo']['ramas'] if r.get('id')}
    nombres = {x.get('enlace') for a in escalera['datos']['alimentadores'].values() for x in a.get('enlaces') or ()}
    maniobras = sorted(por_nombre[n] for n in nombres if n in por_nombre)
    if not maniobras:
        return None, 'la escalera no trae enlaces de maniobra que estén en el grafo del episodio'
    return {'maniobras': maniobras, 'tension_min_pu': escalera['plan']['tension_min_pu'],
            'tension_max_pu': limites.tension_max_pu}, None


def _normalizacion(e, contexto, problema: str, parametros: dict) -> dict:
    """Ideal físico cero y, de nadir, lo medido en el estado actual o la inversión máxima; nunca un valor a mano."""
    from convertersmartgrid.digital_twin.evolutivo import problema_bancos, problema_maniobras
    from convertersmartgrid.digital_twin.problema_optimizacion import evaluar_vector
    factory = problema_bancos if problema == 'bancos' else problema_maniobras
    prob = factory(e.topologia['grafo'], contexto=contexto, modelo_id='normalizacion', **parametros)
    if problema == 'bancos':
        vector, nadir = {v.nombre: 0 for v in prob.variables}, {}
        nadir['inversion'] = [0, parametros['costo_modulo'] * 3 * len(prob.variables)]
    else:
        estado = {r['id']: bool(r.get('cerrada', True)) for r in e.topologia['grafo']['ramas'] if r.get('id')}
        vector, nadir = {v.nombre: int(estado[v.nombre]) for v in prob.variables}, {}
    medido = evaluar_vector(prob, vector)
    if not medido.get('convergio'):
        raise ValueError('el estado actual no converge en el flujo mallado')
    return {**nadir, 'perdidas_kw': [0, medido['objetivos']['perdidas_kw']]}


def _particion_pinn(ensenan: dict) -> dict[str, str]:
    """050:RF-2: la misma partición de la observación que la vista PINN."""
    from convertersmartgrid.digital_twin.oraculo import muestras_y_particiones
    from convertersmartgrid.digital_twin.buffer import Consulta

    class Lectura:
        def consultar(self, consulta):
            return [e for e, _ in ensenan.values()]
    muestras, ids, grupos = muestras_y_particiones(Lectura(), Consulta())
    identidad = {id(m): i for m, i in zip(muestras, ids, strict=True)}
    nombres = {'validacion': 'seleccion'}
    return {identidad[id(m)]: nombres.get(parte, parte) for parte, ms in grupos.items() for m in ms}


def generar_casos(p: Preparacion, destino: Path, proyectos: list[str], espacios: list[Path], ensenan: dict,
                  perfil_ruta: Path) -> Path | None:
    """050:RF-28: casos con los datos guardados de escalera; a lo que le falta un parámetro se le dice cuál."""
    from convertersmartgrid.digital_twin.integration import limites_combinados, normas_de
    from convertersmartgrid.perfil_empresa import datos_perfil, estructura_empresa
    perfil = datos_perfil(perfil_ruta)
    particiones = _particion_pinn(ensenan) if ensenan else {}
    casos, informe = [], {}
    for proyecto in proyectos:
        escaleras = _escaleras_de(espacios, proyecto)
        propios = sorted(((eid, e, c) for eid, (e, c) in ensenan.items() if e.nativo.get('project') == proyecto), key=lambda f: f[0])
        fila = informe[proyecto] = {'escaleras': len(escaleras), 'episodios': len(propios), 'casos': 0, 'faltan': []}
        if not escaleras or not propios:
            fila['faltan'].append('sin escaleras guardadas o sin episodios que enseñan con identidad 043')
            continue
        hechos = set()
        for eid, e, contexto in propios:
            limites = limites_combinados(perfil, normas_de(estructura_empresa(), e.nativo['feeders']))
            if limites is None:
                fila['faltan'].append(f'{eid}: el perfil no da la banda de tensión de sus normas')
                continue
            escalera = next((x for x in reversed(escaleras)
                             if set(e.nativo['feeders']) >= set(x['datos']['alimentadores'])), escaleras[-1])
            for problema, (parametros, motivo) in (('bancos', _parametros_bancos(e, escalera, limites, perfil)),
                                                   ('maniobras', _parametros_maniobras(e, escalera, limites))):
                if parametros is None:
                    if motivo and f'{problema}: {motivo}' not in fila['faltan']:
                        fila['faltan'].append(f'{problema}: {motivo}')
                    continue
                parte = particiones.get(eid)
                # Un caso por proyecto, problema y parte: los escenarios de un episodio no añaden red distinta.
                if parte is None or (problema, parte) in hechos:
                    continue
                from dataclasses import asdict
                try:
                    normalizacion = _normalizacion(e, contexto, problema, parametros)
                except ValueError as exc:
                    fila['faltan'].append(f'{problema}: {eid}: {exc}')
                    continue
                casos.append({'record_id': f'{problema}:{eid}', 'episode_id': eid, 'contexto_043': asdict(contexto),
                              'problema': problema, 'particion': parte, 'parametros': parametros, 'normalizacion': normalizacion})
                fila['casos'] += 1
                hechos.add((problema, parte))
    p.informe['casos_generados'] = informe
    if not casos:
        p.pendiente('evolutivos_casos', 'ningún problema tiene todos sus parámetros reales; ver informe.casos_generados')
        return None
    ruta = destino / 'casos_evolutivos.json'
    ruta.write_text(json.dumps({'schema': 'convertersmartgrid-optimization-learning-cases-v1', 'casos': casos},
                               ensure_ascii=False, sort_keys=True, indent=1), encoding='utf-8')
    return ruta


# ------------------------------------------------------------------ escritura

def _escribir(ruta: Path, valor: Any) -> None:
    ruta.write_text(json.dumps(valor, ensure_ascii=False, sort_keys=True, indent=1), encoding='utf-8')


def politica_del_ciclo(semillas: str) -> dict:
    """050:RF-30: la huella 044 de las políticas con que se evalúa: la del agente y la temporal, con sus valores."""
    from convertersmartgrid.digital_twin.evaluacion_temporal import POLITICA_TEMPORAL
    from convertersmartgrid.evaluacion_modelos import PoliticaEvaluacion, huella
    agente = PoliticaEvaluacion(modo='agente', semillas=tuple(int(s) for s in semillas.split(',')))
    miembros = {'agente': agente.hash, 'temporal': POLITICA_TEMPORAL.hash}
    return {'huella': huella(miembros), 'miembros': miembros}


def ordenes(p: Preparacion, args, contexto: Path) -> dict:
    """Las dos órdenes con los mismos parámetros: ``ciclo`` reutiliza la copia de ``congelar``."""
    from convertersmartgrid.aprendizaje_continuo import huella_parametros_ciclo
    fuentes = [a for n, r in sorted(p.fuentes.items()) for a in ('--fuente', f'{n}={r}')]
    parametros = {'semillas': args.semillas, 'zona_horaria': args.zona_horaria, 'cadencia_min': args.cadencia_min,
                  'horizontes': args.horizontes, 'embedding_model': args.embedding_model}
    comunes = ['--contexto', str(contexto), *fuentes]
    extra = [a for k, v in (('--zona-horaria', args.zona_horaria), ('--cadencia-min', args.cadencia_min),
                            ('--horizontes', args.horizontes), ('--semillas', args.semillas),
                            ('--embedding-model', args.embedding_model)) if v is not None for a in (k, str(v))]
    politica = politica_del_ciclo(args.semillas)['huella']
    return {'congelar': ['congelar', *comunes, '--version', f'parametros_ciclo={huella_parametros_ciclo(parametros)}'],
            'ciclo_solo_preparar': ['ciclo', *comunes, *extra, '--familias', 'transformer,clasificador,gru,pinn,evolutivos,embeddings,qlora',
                                    '--politica-hash', politica, '--tiempo-s', '<s>', '--memoria-gib', '<GiB>', '--solo-preparar']}


def preparar(args) -> dict:
    from convertersmartgrid.aprendizaje_continuo import ESQUEMA_PROCEDENCIA, crear_contexto_ciclo
    salida: Path = args.salida
    if args.espacios and args.perfil and args.complemento is None and not args.declarado_por.strip():
        raise ValueError('declare --declarado-por: lo que se completa al preparar tiene responsable (050:RF-25)')
    # 050:RF-11/12: siempre una carpeta nueva; nada se mezcla con otro ensayo ni con un almacén.
    if salida.exists() and any(salida.iterdir()):
        raise ValueError(f'{salida}: la salida debe ser una carpeta nueva o vacía')
    for ruta in (args.dataset, args.twin, args.llm_dataset, *args.espacios):
        if ruta is not None and salida.resolve().is_relative_to(Path(ruta).resolve()):
            raise ValueError(f'{salida}: la salida no puede estar dentro de la fuente {ruta}')
    salida.mkdir(parents=True, exist_ok=True)
    complemento = leer_complemento(args.complemento)
    sin_calibracion = {}
    if args.espacios and args.perfil and args.twin is not None and args.complemento is None:
        complemento, sin_calibracion = generar_complemento(_proyectos_de_twin(args.twin), list(args.espacios),
                                                           args.perfil, args.declarado_por)
    p = Preparacion(salida, complemento)
    if sin_calibracion:
        p.informe['proyectos_sin_calibracion'] = sin_calibracion
    if args.dataset is None:
        p.pendiente('dataset', 'falta --dataset')
    else:
        preparar_dataset(p, args.dataset, list(args.observaciones))
    if args.vocabulario is not None:
        p.fuentes['vocabulario'] = str(args.vocabulario)
    rutas, contextos = {}, []
    if args.twin is None:
        p.pendiente('twin', 'falta --twin')
    else:
        leido = preparar_twin(p, args.twin)
        rutas, contextos = leido['rutas'], leido['contextos']
    creados = leido['creados'] if args.twin is not None else {}
    if args.cabeceras is None:
        p.pendiente('cabeceras', 'falta --cabeceras')
    else:
        preparar_cabeceras(p, args.cabeceras, contextos, zona_horaria=args.zona_horaria,
                           cadencia_min=args.cadencia_min, horizontes=args.horizontes,
                           proyecto_series=args.proyecto_series, creados=creados)
    if args.llm_dataset is None:
        p.pendiente('llm_dataset', 'falta --llm-dataset')
    else:
        preparar_corpus(p, args.llm_dataset)
    casos = args.casos_evolutivos
    if casos is None and args.proyecto_casos and args.twin is not None:
        casos = generar_casos(p, salida, list(args.proyecto_casos), list(args.espacios), leido['ensenan'], args.perfil)
    elif casos is None:
        p.pendiente('evolutivos_casos', 'falta --casos-evolutivos o --proyecto-casos: no hay casos declarados')
    if casos is not None:
        preparar_casos(p, casos, args.twin, rutas)
    if args.referencia_pinn is not None:
        p.fuentes['referencia_pinn'] = str(args.referencia_pinn)
    if args.twin is not None:
        escribir_vista(p, rutas)
    procedencia = salida / 'procedencia.json'
    _escribir(procedencia, {'schema': ESQUEMA_PROCEDENCIA, 'referencias': p.referencias})
    p.fuentes['procedencia'] = str(procedencia)
    contexto = crear_contexto_ciclo(p.proyectos, documentos=p.documentos) if p.documentos else (
        crear_contexto_ciclo(p.proyectos) if p.proyectos else None)
    ruta_contexto = salida / 'contexto_ciclo.json'
    if contexto is not None:
        _escribir(ruta_contexto, contexto)
    _escribir(salida / 'cuarentena.json', p.cuarentena)
    if p.complemento.get('proyectos') or p.complemento.get('series'):
        # Se congela: lo declarado viaja con la instantánea, con su responsable.
        _escribir(salida / 'complemento.json', p.complemento)
        p.fuentes['complemento'] = str(salida / 'complemento.json')
    resumen = {'schema': 'convertersmartgrid-learning-preparation-v1', 'fuentes': p.fuentes,
               'pendientes': p.pendientes, 'informe': p.informe,
               'referencias': {f: len(t) for f, t in p.referencias.items()},
               'proyectos_043': len(p.proyectos), 'documentos': sorted(p.documentos),
               'cuarentena': dict(Counter(f['fuente'] for f in p.cuarentena)),
               'contexto_hash': contexto['contexto_hash'] if contexto else None,
               'politica': politica_del_ciclo(args.semillas),
               'ordenes': ordenes(p, args, ruta_contexto) if contexto else None,
               'entrenamiento_ejecutado': False}
    _escribir(salida / 'preparacion.json', resumen)
    return resumen


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument('--salida', type=Path, required=True, help='Carpeta nueva; datos de la distribuidora, fuera de git')
    a.add_argument('--dataset', type=Path, help='Dataset v2 con manifest.json')
    a.add_argument('--observaciones', type=Path, action='append', default=[],
                   help='JSONL original de órdenes o informes con texto y fecha; repetible')
    a.add_argument('--vocabulario', type=Path)
    a.add_argument('--twin', type=Path, help='Búfer del gemelo, con objetos/; solo se lee')
    a.add_argument('--cabeceras', type=Path, help='Libro de medición de cabecera')
    a.add_argument('--llm-dataset', type=Path, help='Corpus generativo sellado')
    a.add_argument('--casos-evolutivos', type=Path, help='Manifiesto de casos de optimización')
    a.add_argument('--referencia-pinn', type=Path, help='Referencia sellada del conjunto previo de la PINN')
    a.add_argument('--complemento', type=Path, help=f'JSON {ESQUEMA_COMPLEMENTO}: {", ".join(CAMPOS_COMPLEMENTO)} por proyecto y series')
    a.add_argument('--espacios', type=Path, action='append', default=[],
                   help='Raíz de espacios de la web, para leer calibraciones y escaleras; repetible; solo se lee')
    a.add_argument('--perfil', type=Path, help='Perfil vigente: huella declarada y parámetros de los casos')
    a.add_argument('--declarado-por', default='', help='Responsable del complemento que se genera con --espacios y --perfil')
    a.add_argument('--proyecto-series', help='Proyecto del sistema del libro: su último caso base da el contexto de las series')
    a.add_argument('--proyecto-casos', action='append', default=[], help='Proyecto cuyas escaleras generan casos evolutivos; repetible')
    a.add_argument('--zona-horaria')
    a.add_argument('--cadencia-min', type=int)
    a.add_argument('--horizontes', help='Horizontes en pasos, separados por coma')
    a.add_argument('--semillas', default=SEMILLAS)
    a.add_argument('--embedding-model', default=MODELO_EMBEDDINGS)
    args = a.parse_args(argv)
    try:
        resumen = preparar(args)
    except (OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
