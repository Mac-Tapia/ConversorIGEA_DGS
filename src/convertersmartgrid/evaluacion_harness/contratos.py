"""Contratos sellados, sin dependencias opcionales ni cambios de política heredada."""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from copy import deepcopy
from pathlib import Path

PARTES = ('entrenamiento', 'seleccion', 'calibracion', 'prueba')
MINIMAS = {
    'asistente': ('clasificacion', 'entidades', 'guardas', 'recarga', 'dominio'),
    'recuperador': ('recuperacion', 'fundamentacion', 'recarga', 'dominio'),
    'cadena': ('clasificacion', 'entidades', 'guardas', 'recuperacion', 'fundamentacion', 'recarga', 'dominio'),
    'pronostico': ('pronostico', 'recarga', 'dominio'),
    'gemelo': ('gemelo', 'violaciones', 'nativo', 'recarga', 'dominio'),
    'optimizador': ('optimizacion', 'nativo', 'recarga', 'dominio'),
}
TIPOS = frozenset(t for tipos in MINIMAS.values() for t in tipos)


def canonico(valor) -> bytes:
    try:
        return json.dumps(valor, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise ValueError('contenido no representable como JSON finito') from exc


def huella(valor) -> str:
    return hashlib.sha256(canonico(valor)).hexdigest()


def _identidad(valor, n=64):
    return isinstance(valor, str) and re.fullmatch('[0-9a-f]{'+str(n)+'}', valor) is not None


def _numero(valor):
    return type(valor) in (int, float) and math.isfinite(valor)


def _contenido(cfg):
    canonico(cfg)
    if type(cfg.get('schema_version')) is not int or cfg['schema_version'] != 1:
        raise ValueError('schema_version no soportado')
    if cfg.get('familia') not in MINIMAS:
        raise ValueError('familia desconocida')
    if not isinstance(cfg.get('run_id'), str) or not cfg['run_id'] or not _identidad(cfg.get('revision'), 40):
        raise ValueError('identidad de ejecución ausente')
    modelos = cfg.get('modelos', {})
    if not isinstance(modelos, dict) or set(modelos) != {'referencia', 'candidato'}:
        raise ValueError('comparación exige referencia y candidato')
    for m in modelos.values():
        if (not isinstance(m, dict) or not isinstance(m.get('id'), str) or not m['id']
                or not _identidad(m.get('digest')) or not _identidad(m.get('config_hash'))):
            raise ValueError('modelo sin digest/configuración identificable')
        if 'artifacts' in m and (not isinstance(m['artifacts'], dict) or not m['artifacts'] or any(
                not isinstance(n, str) or not n or '/' in n or '\\' in n or n in {'.', '..'}
                or not _identidad(sha) for n, sha in m['artifacts'].items())):
            raise ValueError('artefactos del modelo sin identidades válidas')
    if 'integracion' in cfg:
        v = cfg['integracion']
        if (not isinstance(v, dict) or not isinstance(v.get('registro_raiz'), str)
                or not Path(v['registro_raiz']).is_absolute()
                or 'activo_esperado' not in v or type(v.get('uses_gpu')) is not bool
                or not isinstance(v.get('modelo'), str) or not isinstance(v.get('etapa'), str)):
            raise ValueError('integración exige destino absoluto, activo y recursos sellados')
        activo = v['activo_esperado']
        if activo is not None and (not isinstance(activo, dict)
                or not _identidad(activo.get('candidate_id')) or activo.get('status') != 'PROMOVIDO'):
            raise ValueError('activo esperado inválido')
    custodia = cfg.get('custodia', {})
    if not isinstance(custodia, dict) or not custodia.get('localizador') or not _identidad(custodia.get('sha256')):
        raise ValueError('custodia ausente')
    minimos = cfg.get('minimos', {})
    if (not isinstance(minimos, dict) or set(minimos) != set(PARTES)
            or any(type(v) is not int or v < 1 for v in minimos.values())):
        raise ValueError('mínimos explícitos positivos por partición obligatorios')
    suites = cfg.get('suites')
    if not isinstance(suites, list) or not suites:
        raise TypeError('sin suites obligatorias')
    ids_suites, ids_casos, grupos, textos, obligatorias = set(), set(), {}, {}, set()
    for suite in suites:
        if not isinstance(suite, dict) or suite.get('tipo') not in TIPOS:
            raise ValueError('tipo de suite no soportado')
        sid = suite.get('id')
        if not isinstance(sid, str) or not sid or sid in ids_suites:
            raise ValueError('suite sin identidad única')
        ids_suites.add(sid)
        if type(suite.get('obligatoria')) is not bool:
            raise ValueError('declarar suite obligatoria o auxiliar')
        if suite['obligatoria']:
            obligatorias.add(suite['tipo'])
        if not isinstance(suite.get('parametros', {}), dict) or not isinstance(suite.get('puertas', {}), dict):
            raise TypeError('parámetros/puertas deben ser mapas')
        for nombre, puerta in suite.get('puertas', {}).items():
            if (not isinstance(nombre, str) or not nombre or not isinstance(puerta, dict) or not puerta
                    or not set(puerta) <= {'minimo', 'maximo'}
                    or any(not _numero(v) for v in puerta.values())
                    or puerta.get('minimo', -math.inf) > puerta.get('maximo', math.inf)):
                raise ValueError('puerta inválida')
        por_parte = {p: set() for p in PARTES}
        if not isinstance(suite.get('casos'), list):
            raise TypeError('casos no declarados')
        for caso in suite['casos']:
            if not isinstance(caso, dict):
                raise TypeError('caso inválido')
            rid, grupo, parte = (caso.get(k) for k in ('record_id', 'group_id', 'particion'))
            if (not isinstance(rid, str) or not rid or rid in ids_casos
                    or not isinstance(grupo, str) or not grupo or parte not in PARTES):
                raise ValueError('id/grupo/partición inválido o id duplicado')
            ids_casos.add(rid)
            if (not isinstance(caso.get('entrada'), dict) or not isinstance(caso.get('esperado'), dict)
                    or not isinstance(caso.get('origen'), str) or not caso['origen']):
                raise ValueError('entrada, referencia independiente u origen ausentes')
            # La entrada completa impide que omitir "texto" esconda duplicados.
            texto = unicodedata.normalize('NFKC', str(caso.get('texto', ''))).casefold()
            claves = [(grupos, grupo), (textos, 'entrada:'+huella(caso['entrada']))]
            if texto.strip():
                claves.append((textos, 'texto:'+' '.join(texto.split())))
            for indice, clave in claves:
                if clave in indice and indice[clave] != parte:
                    raise ValueError('solapamiento de grupo/texto entre particiones')
                indice[clave] = parte
            por_parte[parte].add(grupo)
        if any(len(por_parte[p]) < minimos[p] for p in PARTES):
            raise ValueError('mínimo de grupos incumplido en '+sid)
    if not set(MINIMAS[cfg['familia']]) <= obligatorias:
        raise ValueError('suite obligatoria omitida o reclasificada como auxiliar')
    politica = cfg.get('politica')
    if (not isinstance(politica, dict) or type(politica.get('version')) is not int
            or politica['version'] < 1 or not isinstance(politica.get('comparaciones'), list)):
        raise ValueError('política versionada y comparaciones explícitas obligatorias')
    # La unidad es la media de grupos, nunca un ratio global ni barras correlacionadas.
    for comp in politica['comparaciones']:
        if (not isinstance(comp, dict) or comp.get('suite_id') not in ids_suites
                or not isinstance(comp.get('metrica'), str) or not comp['metrica']
                or comp.get('direccion', 'mayor_mejor') not in {'mayor_mejor', 'menor_mejor'}
                or comp.get('estimando') != 'media_grupos'
                or not _numero(comp.get('margen')) or comp['margen'] < 0
                or type(comp.get('min_grupos')) is not int or comp['min_grupos'] < 2
                or type(comp.get('semilla')) is not int
                or type(comp.get('remuestras')) is not int or comp['remuestras'] < 100
                or not _numero(comp.get('confianza')) or not 0 < comp['confianza'] < 1):
            raise ValueError('comparación sin protocolo completo')


def sellar(config: dict) -> dict:
    if not isinstance(config, dict):
        raise TypeError('configuración debe ser objeto JSON')
    cfg = deepcopy(config)
    cfg.pop('sello', None)
    cfg.pop('dataset_hash', None)
    _contenido(cfg)
    cfg['dataset_hash'] = huella([s['casos'] for s in cfg['suites']])
    return {**cfg, 'sello': huella(cfg)}


def validar(config: dict) -> None:
    if not isinstance(config, dict):
        raise TypeError('configuración debe ser objeto')
    esperado = sellar(config)
    if esperado != config:
        raise ValueError('sello o dataset_hash modificado/ausente')
