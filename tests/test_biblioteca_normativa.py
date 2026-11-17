"""107:RF-21 — la biblioteca normativa general: la base del programa más una capa del usuario, actualizable, para
cualquier empresa, estudio y módulo; su huella cambia con cualquier fichero de las dos capas."""
import json

import pytest

from convertersmartgrid import biblioteca_normativa as bn


def _norma(acto, valor, desde='2020-01-01'):
    return {'acto': acto, 'titulo': f'Norma {acto}', 'estado_juridico': 'vigente_comprobada', 'sha256': 'a' * 64,
            'vigencia_desde': desde,
            'reglas': [{'clave': 'prueba.valor', 'valor': valor, 'unidad': '-', 'articulo_o_anexo': 'art. 1',
                        'pagina': 1, 'lineas': '1', 'cita_literal': f'El valor es {valor}.'}]}


def _capa(carpeta, *normas):
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / 'mias.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': list(normas)}),
                                       encoding='utf-8')


def test_107_rf21_la_base_del_programa_carga_entera():
    r = bn.cargar_biblioteca(capa_usuario=bn.Path('no-existe'))
    assert len(r.normas) >= 50 and 'RCD 232-2017-OS/CD' in r.normas and 'RCD 217-2013-OS/CD' in r.normas


def test_107_rf21_la_capa_del_usuario_anade_y_actualiza_sin_borrar(tmp_path):
    capa = tmp_path / 'normativa_usuario'
    _capa(capa, _norma('RM 999-2026-MINEM/DM', 3), {**_norma('RCD 232-2017-OS/CD', 1), 'titulo': 'Guía, versión nueva'})
    r = bn.cargar_biblioteca(capa_usuario=capa)
    assert 'RM 999-2026-MINEM/DM' in r.normas
    assert r.normas['RCD 232-2017-OS/CD'].titulo == 'Guía, versión nueva'
    assert r.sustituidas == {'RCD 232-2017-OS/CD': 'mias.json'}  # lo sustituido se dice


def test_107_rf21_la_huella_cambia_con_cualquier_fichero(tmp_path):
    capa = tmp_path / 'normativa_usuario'
    h0 = bn.huella_biblioteca(capa_usuario=capa)
    _capa(capa, _norma('RM 999-2026-MINEM/DM', 3))
    h1 = bn.huella_biblioteca(capa_usuario=capa)
    _capa(capa, _norma('RM 999-2026-MINEM/DM', 4))
    assert h0 != h1 != bn.huella_biblioteca(capa_usuario=capa)


def test_107_rf21_la_capa_del_usuario_vive_fuera_del_paquete(monkeypatch, tmp_path):
    monkeypatch.setenv(bn.VARIABLE_CAPA, str(tmp_path / 'otra'))
    assert bn.ruta_capa_usuario() == tmp_path / 'otra'
    monkeypatch.delenv(bn.VARIABLE_CAPA)
    assert bn.ruta_capa_usuario().name == 'normativa_usuario'


def test_107_rf21_los_vinculos_entre_modulos_vienen_citados_de_la_norma():
    """107:RF-21 y 109:RF-26 — el VAD sobre la empresa modelo y el PIDE detrás de la fijación del VAD, con su cita."""
    r = bn.cargar_biblioteca(capa_usuario=bn.Path('no-existe'))
    ds = r.norma('DS 028-2021-EM')
    claves = {x.clave: x for x in ds.reglas}
    assert {'vinculo.vad.empresa_modelo', 'vinculo.pide.objeto_dl_1208', 'vinculo.pide.criterios_tras_vad'} <= set(claves)
    assert all(x.citada for x in ds.reglas) and ds.obligatoria_en('2026-11-17')
    assert 'empresa modelo eficiente' in claves['vinculo.vad.empresa_modelo'].cita_literal


def test_107_rf21_agregar_valida_y_copia_a_la_capa_del_usuario(tmp_path):
    capa, f = tmp_path / 'capa', tmp_path / 'nueva.json'
    f.write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [_norma('RM 998-2026-MINEM/DM', 2)]}),
                 encoding='utf-8')
    assert bn.agregar_norma(f, capa_usuario=capa) == ['RM 998-2026-MINEM/DM']
    assert 'RM 998-2026-MINEM/DM' in bn.cargar_biblioteca(capa_usuario=capa).normas


def test_107_rf21_agregar_rechaza_lo_que_no_valida_y_no_deja_nada(tmp_path):
    capa, f = tmp_path / 'capa', tmp_path / 'mala.json'
    f.write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': [{'acto': 'X', 'titulo': 'X',
                                                                            'estado_juridico': 'inventado'}]}),
                 encoding='utf-8')
    with pytest.raises(bn.RegistroError):
        bn.agregar_norma(f, capa_usuario=capa)
    assert not (capa / 'mala.json').exists()


def test_107_rf21_el_dataset_lleva_cada_regla_con_su_cita_y_solo_se_rehace_si_cambia(tmp_path):
    capa, destino = tmp_path / 'capa', tmp_path / 'dataset'
    primero = bn.exportar_dataset(destino, capa_usuario=capa)
    reglas = [json.loads(x) for x in (destino / 'reglas.jsonl').read_text(encoding='utf-8').splitlines()]
    assert primero['regenerado'] and primero['reglas'] == len(reglas) > 100
    assert all({'acto', 'clave', 'valor', 'cita_literal', 'citada'} <= set(r) for r in reglas)
    assert not bn.exportar_dataset(destino, capa_usuario=capa)['regenerado']
    _capa(capa, _norma('RM 999-2026-MINEM/DM', 3))
    assert bn.exportar_dataset(destino, capa_usuario=capa)['regenerado']


def test_107_rf21_la_orden_de_consola_lista_y_exporta(tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path
    ruta = Path(__file__).resolve().parents[1] / 'tools' / 'normativa' / 'biblioteca.py'
    spec = importlib.util.spec_from_file_location('biblioteca_cli', ruta)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setenv(bn.VARIABLE_CAPA, str(tmp_path / 'capa'))
    assert cli.main(['listar', '--fecha', '2026-11-17']) == 0 and 'DS 028-2021-EM' in capsys.readouterr().out
    assert cli.main(['exportar', str(tmp_path / 'ds')]) == 0 and (tmp_path / 'ds' / 'normas.jsonl').is_file()


def test_109_rf26_el_vnr_entra_al_vad_por_la_tir_de_la_lce():
    """109:RF-26 y 107:RF-21 — el VNR se vincula al VAD por la ley: TIR de 25 años con el VNR y residual cero (art. 70,
    DL 1221), banda de 4 puntos (art. 71) y VNR cada 4 años (art. 77), cada uno con su cita."""
    r = bn.cargar_biblioteca(capa_usuario=bn.Path('no-existe'))
    tir = {x.clave: x for x in r.norma('DL 1221').reglas}['vinculo.vnr_vad.tir']
    assert 'Valor Nuevo de Reemplazo' in tir.cita_literal and '25' in tir.cita_literal and tir.citada
    lce = {x.clave: x for x in r.norma('DL 25844').reglas}
    assert lce['vinculo.vnr_vad.banda_tir'].valor == 4 and lce['vinculo.vnr_vad.periodo_vnr'].valor == 4
    assert all(lce[k].citada for k in ('vinculo.vnr_vad.banda_tir', 'vinculo.vnr_vad.periodo_vnr'))


def test_107_rf21_las_normas_tecnicas_estan_y_no_obligan_sin_su_texto():
    """107:RF-21 — el catálogo nacional e internacional (CNE, NTP, IEC, IEEE) está en la biblioteca, solo de referencia
    y sin verificar: dice quién la usa y no da ni impone ninguna regla hasta que se registre su texto leído."""
    r = bn.cargar_biblioteca(capa_usuario=bn.Path('no-existe'))
    for acto in ('RM 214-2011-MEM/DM', 'NTP 370.400', 'IEC 60909', 'IEEE 1366'):
        n = r.norma(acto)
        assert n.solo_referencia and not n.obligatoria_en('2026-11-17') and not n.reglas and 'La usan' in n.nota


def test_107_rf21_109_rf26_la_base_del_pide_viene_citada_de_su_norma():
    """107:RF-21 y 109:RF-26 — el PIDE se ata al VAD por su norma, citada: el DL 1208 (distribuidoras de FONAFE, estudio
    antes de cada fijación del VAD y PIDE en sus anualidades) y su reglamento, el DS 023-2016-EM (estudio de 20 años,
    anualidad con 30 años de vida útil y la tasa del art. 79 de la LCE, y criterios que aprueba el MINEM). El DS
    027-2018-EM, que daba los criterios a Osinergmin, no rige (DS 028-2018-EM y DS 029-2018-EM), y la RM 428-2017-MEM/DM
    solo prepublica los criterios: ninguna de las dos obliga."""
    r = bn.cargar_biblioteca(capa_usuario=bn.Path('no-existe'))
    actos = ('DL 1208', 'DS 023-2016-EM', 'DS 027-2018-EM', 'DS 028-2018-EM', 'DS 029-2018-EM', 'RM 428-2017-MEM/DM')
    assert set(actos) <= set(r.normas), 'falta la base normativa del PIDE en la biblioteca (107 T39)'
    dl = {x.clave: x for x in r.norma('DL 1208').reglas}
    assert 'antes del inicio de cada fijación tarifaria del Valor Agregado de Distribución' in dl[
        'vinculo.pide.estudio_antes_del_vad'].cita_literal
    assert 'anualidades de inversión' in dl['vinculo.pide.anualidades_en_el_vad'].cita_literal
    ds = {x.clave: x for x in r.norma('DS 023-2016-EM').reglas}
    assert ds['vinculo.pide.horizonte_estudio_anios'].valor == 20
    assert ds['vinculo.pide.anualidad'].valor['vida_util_anios'] == 30 and 'artículo 79' in ds['vinculo.pide.anualidad'].cita_literal
    assert 'serán aprobados por el MINEM' in ds['vinculo.pide.criterios_aprueba_minem'].cita_literal
    for acto in ('DL 1208', 'DS 023-2016-EM', 'DS 028-2018-EM', 'DS 029-2018-EM', 'RM 428-2017-MEM/DM'):
        n = r.norma(acto)
        assert n.reglas and all(x.citada and x.clave.startswith('vinculo.pide.') for x in n.reglas), acto
        assert n.sha256 and n.sha256_texto and n.fichero_local and ':' not in n.fichero_local, acto
    derogada, prepublicada = r.norma('DS 027-2018-EM'), r.norma('RM 428-2017-MEM/DM')
    assert derogada.estado_juridico == 'derogada' and not derogada.reglas and not derogada.obligatoria_en('2026-11-17')
    assert prepublicada.estado_juridico == 'prepublicada' and not prepublicada.obligatoria_en('2026-11-17')
    assert r.regla('vinculo.pide.criterios_aprueba_minem', '2026-11-17').obligatoria
