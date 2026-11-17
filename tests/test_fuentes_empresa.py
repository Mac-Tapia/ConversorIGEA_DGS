"""109:RF-25 — las fuentes de la empresa del espacio: un libro se carga una vez y lo usan todos los módulos, reemplazable
por periodo sin perder las versiones (orden del usuario, 17-11). Y 109:RF-26: la red convertida del espacio queda para
los módulos, con su fuente, su empresa y sus alimentadores."""
import json
import zipfile

import pytest

from convertersmartgrid import fuentes_empresa as fe


def _libro(tmp_path, nombre, contenido):
    p = tmp_path / 'entrada' / nombre
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(contenido)
    return p


def test_109_rf24_registrar_una_vez_listar_y_tomar_la_vigente(tmp_path):
    espacio = tmp_path / 'espacio'
    a = fe.registrar(espacio, 'sicodi', _libro(tmp_path, 'SICODI 2023.xlsx', b'a'), periodo='2023-2027')
    assert a.vigente and a.clase == 'sicodi' and fe.ruta(espacio, a.id).read_bytes() == b'a'
    otra_vez = fe.registrar(espacio, 'sicodi', _libro(tmp_path, 'copia.xlsx', b'a'), periodo='2023-2027')
    assert otra_vez.id == a.id and len(fe.listar(espacio, 'sicodi')) == 1  # la misma huella no se duplica
    b = fe.registrar(espacio, 'sicodi', _libro(tmp_path, 'SICODI 2023 v2.xlsx', b'b'), periodo='2023-2027')
    assert fe.vigente(espacio, 'sicodi').id == b.id
    assert {f.id: f.vigente for f in fe.listar(espacio, 'sicodi')} == {a.id: False, b.id: True}  # la anterior queda
    assert fe.vigente(espacio, 'pit') is None


def test_109_rf24_un_zip_es_una_fuente_con_sus_miembros(tmp_path):
    z = tmp_path / 'entrada' / 'caso.zip'
    z.parent.mkdir(parents=True)
    with zipfile.ZipFile(z, 'w') as w:
        w.writestr('sistemas.json', '{}')
        w.writestr('tablas/anexo2.xlsx', b'x')
    f = fe.registrar(tmp_path / 'espacio', 'vad_caso', z)
    assert sorted(m['nombre'] for m in f.miembros) == ['sistemas.json', 'tablas/anexo2.xlsx']


def test_109_rf24_clase_desconocida_y_fuente_inexistente_se_dicen(tmp_path):
    with pytest.raises(fe.FuenteError, match='clase de fuente desconocida'):
        fe.registrar(tmp_path, 'nada', _libro(tmp_path, 'x.xlsx', b'x'))
    with pytest.raises(fe.FuenteError, match='no hay ninguna fuente'):
        fe.ruta(tmp_path, 'abc')


def test_109_rf25_la_red_convertida_queda_para_los_modulos(tmp_path):
    assert fe.red_del_espacio(tmp_path) is None
    fe.guardar_red(tmp_path, fuente='vnr', empresa='EMPA', alimentadores=['B', 'A'], canonical={'nodes': []})
    red = fe.red_del_espacio(tmp_path)
    assert red['fuente'] == 'vnr' and red['alimentadores'] == ['A', 'B'] and red['empresa'] == 'EMPA'
    assert json.loads((tmp_path / red['canonical']).read_text(encoding='utf-8')) == {'nodes': []} and red['huella']


def test_109_rf24_la_matriz_de_vinculos_cita_cada_vinculo():
    """Cada entrada compartida, propia o entregable de config/modulos/vinculos.json lleva su cita (norma y clave del
    registro, artículo) o dice que es una decisión de producto; cada clave citada existe en el registro."""
    from pathlib import Path
    from convertersmartgrid.registro_normativo import cargar_registro
    raiz = Path(__file__).resolve().parents[1]
    v = json.loads((raiz / 'config' / 'modulos' / 'vinculos.json').read_text(encoding='utf-8'))
    # El registro de las normas y el del TdR del VAD (config/vad): las citas del VAD son claves de ese.
    registro = cargar_registro(*sorted((raiz / 'config' / 'normativa').glob('*.json')), raiz / 'config' / 'vad')
    claves = {r.clave for n in registro.normas.values() for r in n.reglas}
    citas = [c['cita'] for c in v['compartidas'].values()]
    for m in v['modulos'].values():
        for grupo in ('compartidas', 'propias', 'entregables', 'consume_de'):
            citas += [x['cita'] for x in m.get(grupo, [])]
        for x in m.get('compartidas', []):
            assert x['clase'] in v['compartidas'], x
    for c in citas:
        assert c.get('clave') or c.get('articulo') or c.get('decision_de_producto'), c
        if c.get('clave'):
            assert c['clave'] in claves, c


def test_109_rf25_la_carga_de_un_paquete_vnr_gis_deja_la_red_en_el_espacio(tmp_path):
    """109:RF-26 — la carga web trabaja en <espacio>/runs/<id>; la red convertida queda en el espacio, no en la corrida."""
    from convertersmartgrid.adaptadores.entrada.vnr.models.canonical import CanonicalModel, Section
    from convertersmartgrid.sources.vnr import _guardar_red
    m = CanonicalModel()
    m.sections.append(Section('T1', 'A', 'B', feeder_id='AL01'))
    corrida = tmp_path / 'espacio' / 'runs' / 'r1'
    corrida.mkdir(parents=True)
    _guardar_red(corrida, m, 'EMPA')
    red = fe.red_del_espacio(tmp_path / 'espacio')
    assert red['fuente'] == 'vnr' and red['alimentadores'] == ['AL01'] and red['empresa'] == 'EMPA'
    assert CanonicalModel.from_dict(json.loads((tmp_path / 'espacio' / red['canonical']).read_text(encoding='utf-8')))
