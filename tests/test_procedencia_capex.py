"""072:RF-28; 024:RF-54/55/56: procedencia de lecturas nuevas, sin sellar historia."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from convertersmartgrid import pide_economia as ec
from test_pide_economia import CONFIG, _capex


def adaptador():
    return importlib.import_module('convertersmartgrid.adaptadores.entrada.capex')


def identidad(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest(), ruta.stat().st_mtime_ns


def test_recibo_de_los_bytes_leidos_conserva_obras_costos_y_original(tmp_path):
    """072:RF-28; 024:RF-54/56: mismo lector y resultados; recibo sin datos personales."""
    ruta = _capex(tmp_path)
    antes = identidad(ruta)
    esperado = ec.leer_capex(ruta, CONFIG)
    contexto = {'moneda': 'USD', 'escala_capex': 1000, 'tipo_cambio': 3.75}
    config = deepcopy(CONFIG)
    obras, avisos, recibo = adaptador().leer_capex_con_procedencia(ruta, config, contexto_unidades=contexto)
    assert (obras, avisos) == esperado
    assert ec.costos_por_alternativa(obras) == ec.costos_por_alternativa(esperado[0])
    assert recibo['schema_version'] == 1
    assert recibo['fuente']['ruta'] == str(ruta.resolve())
    assert recibo['fuente']['sha256'] == antes[0]
    assert recibo['fuente']['bytes'] == ruta.stat().st_size
    assert recibo['hoja'] == CONFIG['hoja'] and recibo['config'] == CONFIG
    assert recibo['contexto_unidades'] == contexto
    assert recibo['unidades'] == ['Und', 'km']
    assert recibo['lector'] == {'read_only': True, 'data_only': True}
    assert recibo['lectura_utc'].endswith('+00:00')
    assert 'Persona' not in json.dumps(recibo, ensure_ascii=False)
    config['columnas']['nombre'] = 'alterado después'
    contexto['escala_capex'] = -1
    assert recibo['config'] == CONFIG and recibo['contexto_unidades']['escala_capex'] == 1000
    assert identidad(ruta) == antes


def test_lector_recibe_descriptor_protegido_y_bloquea_escritor_y_reemplazo_hijos(tmp_path, monkeypatch, request):
    """072:RF-28: el hash identifica lo parseado; hijos propios no pueden mutar entre ambos."""
    ruta = _capex(tmp_path)
    antes = identidad(ruta)
    lector = ec.leer_capex
    intentos = []
    def interceptar(stream, config):
        assert hasattr(stream, 'read') and hasattr(stream, 'seek') and stream.seekable()
        codigo = '''
import json, os, sys
try:
    if sys.argv[1] == 'escribir':
        with open(sys.argv[2], 'r+b') as f:
            f.write(b'alterado')
    else:
        os.replace(sys.argv[2], sys.argv[3])
except PermissionError:
    print(json.dumps({'bloqueado': True, 'pid': os.getpid()}))
else:
    print(json.dumps({'bloqueado': False, 'pid': os.getpid()}))
    sys.exit(1)
'''
        for accion in ('escribir', 'reemplazar'):
            r = subprocess.run([sys.executable, '-B', '-c', codigo, accion, str(ruta), str(tmp_path / 'movido.xlsx')],
                               capture_output=True, text=True, timeout=20)
            assert r.returncode == 0, r.stdout + r.stderr
            intentos.append(json.loads(r.stdout))
        return lector(stream, config)
    monkeypatch.setattr(ec, 'leer_capex', interceptar)
    obras, _, recibo = adaptador().leer_capex_con_procedencia(ruta, CONFIG, contexto_unidades={})
    assert obras and len(intentos) == 2 and all(i['bloqueado'] for i in intentos)
    assert recibo['fuente']['sha256'] == antes[0] and identidad(ruta) == antes
    assert sorted(p.name for p in tmp_path.iterdir()) == ['capex.xlsx']
    request.node.user_properties.extend([
        ('procesos_propios', json.dumps(intentos)), ('sha256_original', antes[0]),
        ('mtime_ns_original', str(antes[1])), ('fuente_intacta', str(identidad(ruta) == antes)),
    ])
    with ruta.open('r+b'):
        pass  # La guarda se liberó, sin escribir el original.


def test_escritor_previo_impide_sellado_y_no_se_parsea(tmp_path, monkeypatch):
    """072:RF-28: no existe un recibo verificable si otra apertura permite escritura."""
    ruta = _capex(tmp_path)
    antes = identidad(ruta)
    def prohibido(*a, **k):
        pytest.fail('no debe parsear una fuente que admite escritor concurrente')
    monkeypatch.setattr(ec, 'leer_capex', prohibido)
    with ruta.open('r+b'):
        with pytest.raises(OSError):
            adaptador().leer_capex_con_procedencia(ruta, CONFIG, contexto_unidades={})
    assert identidad(ruta) == antes


def test_falta_hoja_no_deja_recibo_y_libera_lectura(tmp_path):
    """024:RF-55; 072:RF-28: fallo real del lector canónico y cierre incluso ante error."""
    ruta = _capex(tmp_path)
    antes = identidad(ruta)
    with pytest.raises(ec.EconomiaPideError, match='Otra'):
        adaptador().leer_capex_con_procedencia(ruta, {**CONFIG, 'hoja': 'Otra'}, contexto_unidades={})
    assert identidad(ruta) == antes
    with ruta.open('r+b'):
        pass


def test_dos_rutas_no_comparten_procedencia_ni_configuracion(tmp_path):
    """072:RF-17/28: cada nueva lectura conserva su fuente efectiva y su contexto declarado."""
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir(); b.mkdir()
    ruta_a, ruta_b = _capex(a), _capex(b)
    # Una segunda fuente propia distinta; no se reutiliza un recibo por nombre del libro.
    from openpyxl import load_workbook
    wb = load_workbook(ruta_b)
    wb[CONFIG['hoja']]['I3'] = 8765
    wb.save(ruta_b); wb.close()
    oa, _, ra = adaptador().leer_capex_con_procedencia(ruta_a, CONFIG, contexto_unidades={})
    ob, _, rb = adaptador().leer_capex_con_procedencia(ruta_b, CONFIG, contexto_unidades={'moneda': None})
    assert oa != ob and ra['fuente']['sha256'] != rb['fuente']['sha256']
    assert ra['fuente']['ruta'] != rb['fuente']['ruta']
    assert rb['contexto_unidades']['moneda'] is None


def test_config_y_unidades_se_fijan_antes_de_abrir_y_no_guardan_metadatos_ajenos(tmp_path, monkeypatch):
    """024:RF-56; 072:RF-28: ni ABA de mapping ni datos personales ajenos al cálculo."""
    from contextlib import contextmanager
    ruta = _capex(tmp_path)
    config = {**deepcopy(CONFIG), 'contacto_privado': 'Persona no pertinente'}
    contexto = {'moneda': 'USD', 'escala_aplicada': 1000, 'operador': 'Persona no pertinente'}
    mod = adaptador()
    abrir = mod.abrir_fuente_estable
    @contextmanager
    def durante_apertura(ruta):
        with abrir(ruta) as lectura:
            config['hoja'] = 'Otra'
            contexto['moneda'] = 'cambiado durante apertura'
            yield lectura
    monkeypatch.setattr(mod, 'abrir_fuente_estable', durante_apertura)
    obras, _, recibo = mod.leer_capex_con_procedencia(ruta, config, contexto_unidades=contexto)
    assert obras and recibo['hoja'] == CONFIG['hoja']
    assert recibo['contexto_unidades']['moneda'] == 'USD'
    assert 'Persona' not in json.dumps(recibo)
    assert 'contacto_privado' not in recibo['config'] and 'operador' not in recibo['contexto_unidades']


@pytest.mark.parametrize('guion', ['pide_pf.py', 'obras_pf.py'])
def test_guiones_conservan_recibo_en_informe_bloqueado_sin_abrir_motor(tmp_path, monkeypatch, guion):
    """072:RF-28: passthrough de metadata en fallo previo; no es aceptación nativa."""
    from apoyo import cargar_herramienta
    modulo = cargar_herramienta(guion, 'procedencia_' + guion[:-3], tools_en_path=True)
    recibo = {'fuente': {'sha256': 'recibo_de_prueba'}, 'hoja': CONFIG['hoja']}
    plan = tmp_path / 'plan.json'
    salida = tmp_path / 'informe.json'
    plan.write_text(json.dumps({'project': 'Propio', 'procedencia_capex': recibo}), encoding='utf-8')
    monkeypatch.setattr(modulo, 'native_action_block_report', lambda *a, **k: {'error': 'sin contexto propio'})
    assert modulo.main(['--plan', str(plan), '--output-json', str(salida)]) == 2
    assert json.loads(salida.read_text(encoding='utf-8'))['procedencia_capex'] == recibo


def test_documento_y_json_conservan_recibo_opcional_y_no_sellan_historico(tmp_path):
    """072:RF-14/21/28: documento real y par JSON con identidad, o hueco explícito."""
    from test_informes_planeamiento import _datos, MODULO
    from convertersmartgrid.informes_planeamiento import escribir_modulo
    from docx import Document
    recibo = {'fuente': {'ruta': 'capex_propio.xlsx', 'sha256': 'b' * 64}, 'hoja': CONFIG['hoja'],
              'contexto_unidades': {'moneda': 'USD', 'escala_aplicada': 1000}, 'lectura_utc': '2026-11-08T00:00:00+00:00'}
    ruta = tmp_path / 'con_recibo.docx'
    escribir_modulo(ruta, MODULO['evaluacion_economica'], _datos(procedencia_capex=recibo))
    par = json.loads(ruta.with_suffix('.json').read_text(encoding='utf-8'))
    texto = '\n'.join(p.text for p in Document(ruta).paragraphs)
    assert par['procedencia_capex'] == recibo
    assert recibo['fuente']['sha256'] in texto and CONFIG['hoja'] in texto
    viejo = tmp_path / 'sin_recibo.docx'
    escribir_modulo(viejo, MODULO['evaluacion_economica'], _datos())
    historico = json.loads(viejo.with_suffix('.json').read_text(encoding='utf-8'))
    assert historico['procedencia_capex'] is None
    assert 'sin lectura CAPEX vinculada' in '\n'.join(p.text for p in Document(viejo).paragraphs)
