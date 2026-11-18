"""Spec 108, tarjeta VAD-REQ — los requisitos de V11 (numeral 6.11) y V12 (6.8.3, 6.13, 6.14 y 6.15) del TdR vigente
quedan en el registro normativo con su cita, y las dos normas que lo rigen, comprobadas (108:RF-9, RF-10, RF-18,
RF-19).

Las pruebas leen el registro real de ``config/vad`` (el anexo del TdR modificado por la RCD 033-2026-OS/CD) y, para el
contrato del registro, un registro sintético sin ninguna empresa. Cada prueba falla por su aserción si falta lo que
comprueba: se lee con ``.get`` y ``getattr``, sin dejar que un ``KeyError`` o un ``AttributeError`` hable por ella.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from convertersmartgrid.dominio.registro_normativo import RegistroError, cargar_registro

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_VAD = RAIZ / 'config' / 'vad'
ANEXO = 'tdr-vad-2026-anexo-r033'
CARACTERES = {'obligatoria', 'criterio', 'referencia'}

#: Las 36 reglas de VAD-REQ, por apartado: 6.8.3 (6), 6.11 (11), 6.13 (9), 6.14 (7) y 6.15 (3).
CLAVES_REQ = {
    '6_8_3': ('metodologia_dimensionamiento', 'ley_29783', 'valor_mercado_y_respaldo', 'reparto_mt_bt_sed',
              'cuadro_18', 'lista_detallada'),
    '6_11': ('diseno_cumple_ntcse', 'aspectos_minimos', 'calidad_producto', 'pautas_suministro',
             'saifi_saidi_curvas_porcentaje', 'circuitos_representativos', 'cuadro_21_presentacion', 'cuadro_21',
             'previsiones_adicionales', 'cuadro_22', 'cuadro_23'),
    '6_13': ('alcance_operacion_comercial', 'indicadores_estandar', 'lectura_remota_smi',
             'costos_asociados_usuario_y_cargos', 'cobranza_externa', 'moneda_y_decimales', 'cuadro_24', 'cuadro_25',
             'gestion_comercial_y_exclusiones'),
    '6_14': ('organizacion_optima', 'costos_unitarios_personal', 'exclusiones_y_funcionamiento',
             'referencias_y_superposicion', 'asignacion_indirectos', 'cuadro_26', 'formatos_vii_ix'),
    '6_15': ('componentes', 'capital_de_trabajo', 'cuadro_27'),
}
CLAVES = [f'vad.req.{apartado}.{nombre}' for apartado, nombres in CLAVES_REQ.items() for nombre in nombres]
#: Las reglas cuyo texto llama «referencia» a lo de regulaciones anteriores.
CON_REFERENCIA = {'vad.req.6_8_3.metodologia_dimensionamiento', 'vad.req.6_13.indicadores_estandar',
                  'vad.req.6_14.referencias_y_superposicion'}


def _reglas_del_anexo(registro) -> dict:
    norma = registro.normas.get(ANEXO)
    assert norma is not None, f'el registro de config/vad no trae la norma {ANEXO}'
    return {r.clave: r for r in norma.reglas}


def _claves_de_los_ficheros(excluir: str) -> set[str]:
    """Las claves que ya traía config/ (VAD y normativa) fuera del fichero ``excluir``."""
    claves: set[str] = set()
    for f in sorted((RAIZ / 'config').rglob('*.json')):
        if f.name == excluir:
            continue
        try:
            datos = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(datos, dict) or datos.get('esquema') != 'registro_normativo_v1':
            continue
        reglas = list(datos.get('reglas') or [])
        for n in datos.get('normas') or []:
            reglas += list(n.get('reglas') or [])
        claves |= {r.get('clave') for r in reglas if isinstance(r, dict)}
    return claves


def test_las_36_reglas_de_v11_y_v12_cargan_con_su_cita_su_pagina_y_sus_lineas():
    """108:RF-9 — las 36 reglas de V11 y V12 están en el anexo registrado, cada una con su cita literal, su página, sus
    líneas, su carácter y su entregable; 108:RF-18 y RF-19 — el 6.11 va a V11 y el resto a V12."""
    assert len(CLAVES) == len(set(CLAVES)) == 36
    reglas = _reglas_del_anexo(cargar_registro(CONFIG_VAD))
    faltan = [c for c in CLAVES if c not in reglas]
    assert not faltan, f'faltan {len(faltan)} de 36 reglas de VAD-REQ: {faltan[:5]}…'
    for clave in CLAVES:
        r = reglas[clave]
        assert r.citada and r.cita_literal.strip() and r.pagina.strip() and r.lineas.strip(), clave
        assert getattr(r, 'caracter', None) in CARACTERES, (clave, getattr(r, 'caracter', None))
        assert str(getattr(r, 'aplicacion', '') or '').strip(), f'{clave} sin «aplicacion»'
        esperado = 'V11' if clave.startswith('vad.req.6_11.') else 'V12'
        assert getattr(r, 'entregable', None) == esperado, (clave, getattr(r, 'entregable', None))


def test_ninguna_regla_nueva_duplica_una_que_ya_existia():
    """108:RF-9 — las 36 claves son nuevas: ninguna estaba en otro fichero del registro (config/vad ni
    config/normativa), y el 6.11.1 amplía «vad.calidad.indicadores» en lugar de repetirla."""
    reglas = _reglas_del_anexo(cargar_registro(CONFIG_VAD))
    assert all(c in reglas for c in CLAVES), 'faltan reglas de VAD-REQ en el registro'
    previas = _claves_de_los_ficheros(excluir='tdr_vad_2026_requisitos.json')
    repetidas = sorted(previas & set(CLAVES))
    assert not repetidas, f'claves de VAD-REQ ya registradas en otro fichero: {repetidas}'
    indicadores = reglas.get('vad.calidad.indicadores')
    assert indicadores is not None, 'vad.calidad.indicadores desapareció del registro'
    assert getattr(indicadores, 'entregable', None) == 'V11'
    assert getattr(indicadores, 'caracter', None) == 'obligatoria'
    assert 'vad.req.6_11.diseno_cumple_ntcse' in indicadores.interpretacion, \
        'vad.calidad.indicadores no cita la regla del 6.11.1 que la amplía'


def test_cada_referencia_del_tdr_lleva_no_tope():
    """108:RF-19 — lo que el TdR llama «referencia» (las regulaciones anteriores) se rotula «referencia, no tope»:
    orienta el dimensionamiento, no lo limita. «Preferencia» no cuenta."""
    reglas = _reglas_del_anexo(cargar_registro(CONFIG_VAD))
    con_referencia = {c for c in CLAVES
                      if c in reglas and re.search(r'\breferencia\b', reglas[c].cita_literal.lower())}
    assert con_referencia == CON_REFERENCIA, sorted(con_referencia ^ CON_REFERENCIA)
    sin_rotulo = sorted(c for c in con_referencia if 'referencia, no tope' not in reglas[c].interpretacion)
    assert not sin_rotulo, f'«referencia» sin «no tope»: {sin_rotulo}'


def test_el_cuadro_18_vigente_y_la_lectura_remota_segun_el_smi_estan_con_su_cita():
    """108:RF-19 — el Cuadro 18 del texto vigente trae la fila de sistemas informáticos con ciberseguridad y nube, y el
    6.13 trae la lectura remota según el Plan de Despliegue del SMI; los dos con su cita literal."""
    reglas = _reglas_del_anexo(cargar_registro(CONFIG_VAD))
    cuadro = reglas.get('vad.req.6_8_3.cuadro_18')
    assert cuadro is not None, 'falta la regla del Cuadro 18 (vad.req.6_8_3.cuadro_18)'
    assert 'Cuadro N° 18' in cuadro.cita_literal and cuadro.pagina == '44', cuadro.cita_literal
    filas = [f[0] if isinstance(f, list) else f for f in (cuadro.valor or {}).get('filas', [])]
    informaticos = [f for f in filas if f.startswith('Sistemas informáticos')]
    assert informaticos and 'ciberseguridad' in informaticos[0] and 'nube' in informaticos[0], informaticos
    assert len(filas) == 10 and filas[-1] == 'Total Empresa', filas
    smi = reglas.get('vad.req.6_13.lectura_remota_smi')
    assert smi is not None, 'falta la regla de la lectura remota (vad.req.6_13.lectura_remota_smi)'
    assert 'Plan de Despliegue de su SMI' in smi.cita_literal and smi.lineas == '2487-2496', smi.lineas
    assert getattr(smi, 'caracter', None) == 'criterio'


def test_las_dos_normas_del_tdr_estan_comprobadas_con_su_huella_y_sus_dos_fechas():
    """108:RF-10 — la RCD 174-2025 y la RCD 033-2026 pasan a «vigente_comprobada» con su SHA-256, su URL y su
    consulta; la 174-2025 se emitió el 2025-12-18 y se publicó el 2025-12-19 (según la 033-2026), fechas separadas."""
    registro = cargar_registro(CONFIG_VAD)
    huellas = {'rcd-174-2025-os-cd': '87dc452e9f5a121d0f5aadfe64c6b275a562e9721502d33fdc1aaa100e504070',
               'rcd-033-2026-os-cd': 'bfd05eabd86a4d4e3cccdb76dce2ab601b4c900f8c3b38f9ab160f34b85145c4'}
    for acto, sha in huellas.items():
        norma = registro.normas.get(acto)
        assert norma is not None, f'falta la norma {acto}'
        assert norma.estado_juridico == 'vigente_comprobada', (acto, norma.estado_juridico)
        assert norma.sha256 == sha, (acto, norma.sha256)
        assert norma.url.startswith('https://www.osinergmin.gob.pe/') and norma.fecha_consulta, acto
        assert norma.fichero_local and not norma.fichero_local.startswith('/') and ':' not in norma.fichero_local
    r174 = registro.normas.get('rcd-174-2025-os-cd')
    assert (getattr(r174, 'fecha_emision', None), r174.fecha_publicacion) == ('2025-12-18', '2025-12-19')
    assert getattr(registro.normas.get('rcd-033-2026-os-cd'), 'fecha_emision', None) == '2026-02-26'


def _sintetico(tmp_path, nombre, regla, **norma):
    datos = {'esquema': 'registro_normativo_v1', 'normas': [{
        'acto': 'tdr-sintetico', 'titulo': 'TdR sintético', 'estado_juridico': 'vigente_comprobada',
        'sha256': 'c' * 64, **norma, 'reglas': [regla]}]}
    ruta = tmp_path / f'{nombre}.json'
    ruta.write_text(json.dumps(datos), encoding='utf-8')
    return ruta


def _cargar(ruta):
    try:
        return cargar_registro(ruta), ''
    except RegistroError as exc:
        return None, str(exc)


def test_el_registro_admite_caracter_entregable_y_fecha_de_emision_y_rechaza_lo_invalido(tmp_path):
    """108:RF-9 — una regla guarda su carácter, su aplicación, su entregable y las líneas de su cita; una norma, su
    emisión aparte de su publicación. Un carácter fuera de la lista o una emisión posterior a la publicación se
    rechazan nombrando el campo, y una regla sin los campos nuevos conserva la huella que tenía."""
    base = {'clave': 'vad.req.sintetica', 'valor': 1, 'cita_literal': '«uno»', 'lineas': '1-2'}
    nueva = {**base, 'caracter': 'criterio', 'aplicacion': 'comprobar uno', 'entregable': 'V99', 'cita_lineas': '1'}
    registro, error = _cargar(_sintetico(tmp_path, 'nueva', nueva, fecha_emision='2001-01-01',
                                         fecha_publicacion='2001-01-02'))
    assert registro is not None, f'el registro no admite los campos nuevos: {error}'
    regla = registro.regla('vad.req.sintetica').regla
    assert (getattr(regla, 'caracter', None), getattr(regla, 'entregable', None),
            getattr(regla, 'cita_lineas', None)) == ('criterio', 'V99', '1')
    assert getattr(registro.norma('tdr-sintetico'), 'fecha_emision', None) == '2001-01-01'

    _, error = _cargar(_sintetico(tmp_path, 'caracter', {**nueva, 'caracter': 'tope'}))
    assert 'caracter' in error and 'tope' in error, error
    _, error = _cargar(_sintetico(tmp_path, 'fechas', base, fecha_emision='2001-01-03',
                                  fecha_publicacion='2001-01-02'))
    assert 'fecha_emision' in error, error

    # Compatibilidad: la huella de una regla sin los campos nuevos es la que daba el registro antes de VAD-REQ.
    vieja, _ = _cargar(_sintetico(tmp_path, 'vieja', base))
    rv = vieja.regla('vad.req.sintetica')
    previos = {k: v for k, v in asdict(rv.regla).items()
               if k not in ('caracter', 'aplicacion', 'entregable', 'cita_lineas')}
    datos = {'regla': previos, 'acto': rv.norma.acto, 'estado': rv.norma.estado_juridico,
             'version': rv.norma.version, 'sha256': rv.norma.sha256}
    esperada = hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
                              .encode('utf-8')).hexdigest()
    assert rv.huella() == esperada
