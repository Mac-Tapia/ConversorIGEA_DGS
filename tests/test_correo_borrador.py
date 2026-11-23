"""Spec 110: borrador del correo de un informe, su firma, adjuntos admitidos, validez y contactos habituales."""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from correo_simulado import ProveedorSimulado, sin_red  # noqa: F401  (fixture)

from convertersmartgrid.adaptadores.correo import borrador as b


@pytest.fixture(autouse=True)
def _sin_red(sin_red):  # noqa: F811
    yield


#: Sello fijo de cada entrada del ZIP. Con ``writestr(nombre, ...)`` cada entrada lleva la hora de escritura (2 s de
#: resolución), y dos llamadas al mismo auxiliar a ambos lados de ese límite daban otros bytes, otra huella y, como
#: tiene que ser (110:RF-4), otra firma: la prueba de «el mismo borrador da la misma firma» fallaba según el reloj.
_SELLO_ZIP = (2026, 1, 1, 0, 0, 0)


def _ooxml(parte: str, texto: str = 'informe sintetico', extra: dict | None = None) -> bytes:
    """Un Word (``word``) o un Excel (``xl``) mínimos: un ZIP con su ``[Content_Types].xml`` y su parte principal.

    Los mismos argumentos dan siempre los mismos bytes (``_SELLO_ZIP``).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        def escribir(nombre, datos):
            z.writestr(zipfile.ZipInfo(nombre, date_time=_SELLO_ZIP), datos)
        escribir('[Content_Types].xml', '<Types/>')
        escribir(f'{parte}/{"document" if parte == "word" else "workbook"}.xml', f'<x>{texto}</x>')
        for nombre, datos in (extra or {}).items():
            escribir(nombre, datos)
    return buf.getvalue()


def _adjunto(tmp_path, nombre='informe.docx', contenido=None):
    ruta = tmp_path / nombre
    ruta.write_bytes(_ooxml('word') if contenido is None else contenido)
    return ruta


def _borrador(tmp_path, **cambios):
    datos = dict(cuenta='operador@empresa-a.test', proveedor='google', para=['cliente@otra.test'],
                 cc=['jefe@empresa-a.test'], cco=[], asunto='Informe de factibilidad', cuerpo='Adjunto el informe.',
                 adjuntos=[_adjunto(tmp_path)], enlace=None)
    datos.update(cambios)
    return b.crear_borrador(**datos)


def test_la_firma_cubre_todo_lo_que_ve_el_operador(tmp_path):
    """110:RF-1, RF-5 — la firma cambia si cambia la cuenta, un destinatario, el asunto, el cuerpo o el enlace."""
    base = _borrador(tmp_path)
    firma = base.firma()
    assert len(firma) == 64
    assert _borrador(tmp_path).firma() == firma, 'el mismo borrador da la misma firma'
    for cambio in (dict(cuenta='otra@empresa-a.test'), dict(para=['cliente2@otra.test']), dict(cc=[]),
                   dict(cco=['oculto@otra.test']), dict(asunto='Otro asunto'), dict(cuerpo='Otro cuerpo'),
                   dict(enlace='https://expediente.test/x', adjuntos=[]), dict(proveedor='microsoft')):
        assert _borrador(tmp_path, **cambio).firma() != firma, cambio


def test_la_firma_cubre_ruta_tamano_y_huella_de_cada_adjunto(tmp_path):
    """110:RF-1, RF-4 — cada adjunto entra con su ruta, su tamaño y su SHA-256 leídos del disco."""
    borr = _borrador(tmp_path)
    (adj,) = borr.adjuntos
    assert adj.tamano == len(_ooxml('word'))
    assert len(adj.sha256) == 64 and adj.nombre == 'informe.docx'
    otro = tmp_path / 'otro'
    otro.mkdir()
    assert _borrador(tmp_path, adjuntos=[_adjunto(otro)]).firma() != borr.firma(), 'otra ruta, otra firma'


def test_un_byte_cambiado_tras_la_vista_previa_pide_revisarlo_sin_llamar_al_proveedor(tmp_path):
    """110:RF-4 — un adjunto que cambia entre la vista previa y la confirmación anula la confirmación."""
    proveedor = ProveedorSimulado()
    borr = _borrador(tmp_path)
    firma = borr.firma()
    b.comprobar_firma(borr, firma)  # sin cambios, pasa
    ruta = tmp_path / 'informe.docx'
    datos = bytearray(ruta.read_bytes())
    datos[-1] ^= 1
    ruta.write_bytes(bytes(datos))
    with pytest.raises(b.ConfirmacionAnulada, match='revise'):
        b.comprobar_firma(borr, firma)
    assert proveedor.llamadas == []


def test_un_adjunto_borrado_tambien_anula(tmp_path):
    """110:RF-4 — si el adjunto ya no está, la confirmación tampoco vale."""
    borr = _borrador(tmp_path)
    firma = borr.firma()
    (tmp_path / 'informe.docx').unlink()
    with pytest.raises(b.ConfirmacionAnulada):
        b.comprobar_firma(borr, firma)


def test_otro_destinatario_con_la_misma_firma_se_rechaza(tmp_path):
    """110:RF-5 — la confirmación está unida a esos destinatarios exactos: cambiar uno con la firma vieja no vale."""
    borr = _borrador(tmp_path)
    firma = borr.firma()
    cambiado = _borrador(tmp_path, para=['intruso@otra.test'])
    with pytest.raises(b.ConfirmacionAnulada):
        b.comprobar_firma(cambiado, firma)
    with pytest.raises(b.ConfirmacionAnulada):
        b.comprobar_firma(borr, '0' * 64)


def test_el_borrador_va_y_vuelve_por_json_con_la_misma_firma(tmp_path):
    """110:RF-5 — el borrador se guarda en el servidor y se relee igual para confirmarlo."""
    borr = _borrador(tmp_path)
    assert b.Borrador.desde_dict(borr.como_dict()).firma() == borr.firma()


@pytest.mark.parametrize('mal', ['sin-arroba', 'a@b@c.test', 'con espacio@x.test', 'a@x.test\r\nBcc: z@y.test',
                                 'a@', '@x.test', 'a,b@x.test'])
def test_direcciones_imposibles_se_rechazan(tmp_path, mal):
    """110:RF-1 — una dirección imposible (o una cabecera inyectada) no llega al borrador."""
    with pytest.raises(b.BorradorInvalido):
        _borrador(tmp_path, para=[mal])


def test_asunto_con_salto_de_linea_se_rechaza_y_sin_destinatario_tambien(tmp_path):
    """110:RF-1 — el asunto no puede llevar cabeceras escondidas, y un correo sin destinatario no se prepara."""
    with pytest.raises(b.BorradorInvalido):
        _borrador(tmp_path, asunto='Hola\r\nBcc: z@y.test')
    with pytest.raises(b.BorradorInvalido):
        _borrador(tmp_path, para=[])
    with pytest.raises(b.BorradorInvalido):
        _borrador(tmp_path, proveedor='smtp')


def test_direcciones_se_normalizan_y_no_se_repiten(tmp_path):
    """110:RF-1 — espacios y mayúsculas no cambian a quién va; una dirección repetida va una vez."""
    borr = _borrador(tmp_path, para=['  Cliente@Otra.TEST ', 'cliente@otra.test'], cc=['cliente@otra.test'])
    assert borr.para == ('cliente@otra.test',)
    assert borr.cc == ()


# ------------------------------------------------------------------ T2: adjuntos admitidos y prohibidos (RF-3, RF-11)
from test_informe_docx import _config, _factibilidad  # noqa: E402  (informes reales sobre datos sintéticos)

from convertersmartgrid.adaptadores.informe_docx import escribir_informe_factibilidad  # noqa: E402

#: Dos perfiles de empresa distintos (P13): otra norma, otro regulador y otros rótulos de cabecera.
PERFILES = ({}, {'norma': 'NORMA-B', 'regulador': 'Regulador B',
                 'cabecera': {'numero': 'DOC N°', 'referencia': 'ASUNTO'}})


def _informe_cerrado(tmp_path, perfil, nombre='informe_factibilidad_AL02_X.docx'):
    out = tmp_path / 'salida'
    out.mkdir(exist_ok=True)
    destino = out / nombre
    escribir_informe_factibilidad(_config(tmp_path, **perfil), destino, _factibilidad(tmp_path))
    return out, destino


@pytest.mark.parametrize('perfil', PERFILES)
def test_un_informe_cerrado_da_sus_adjuntos_con_huella(tmp_path, perfil):
    """110:RF-3 — el Word publicado con su resumen .json, y su PDF y su libro al lado, se adjuntan con su huella."""
    out, destino = _informe_cerrado(tmp_path, perfil)
    destino.with_suffix('.pdf').write_bytes(b'%PDF-1.7\n% informe sintetico\n%%EOF\n')
    destino.with_suffix('.xlsx').write_bytes(_ooxml('xl'))
    rutas = b.adjuntos_del_informe(out, destino.name)
    assert [r.suffix for r in rutas] == ['.docx', '.pdf', '.xlsx']
    borr = _borrador(tmp_path, adjuntos=rutas)
    assert all(len(a.sha256) == 64 and a.tamano > 0 for a in borr.adjuntos)
    assert [r.suffix for r in b.adjuntos_del_informe(out, destino.name, elegidos=('docx',))] == ['.docx']


def test_un_informe_sin_su_resumen_no_esta_cerrado(tmp_path):
    """110:RF-3 — un Word sin su .json (un informe antiguo o a medio escribir) no se adjunta como cerrado."""
    out, destino = _informe_cerrado(tmp_path, {})
    destino.with_suffix('.json').unlink()
    with pytest.raises(b.BorradorInvalido, match='cerrado'):
        b.adjuntos_del_informe(out, destino.name)


@pytest.mark.parametrize('nombre', ['../fuera.docx', 'sub/informe.docx', 'no_existe.docx', 'informe.json'])
def test_solo_informes_de_la_salida_del_espacio(tmp_path, nombre):
    """110:RF-3 — solo un informe publicado en la salida del espacio: ni rutas fuera de ella ni otros ficheros."""
    out, _ = _informe_cerrado(tmp_path, {})
    (tmp_path / 'fuera.docx').write_bytes(_ooxml('word'))
    with pytest.raises(b.BorradorInvalido):
        b.adjuntos_del_informe(out, nombre)


def test_el_proyecto_o_el_escenario_de_otro_informe_se_rechaza(tmp_path):
    """110:RF-3 — el resumen dice su proyecto y su escenario; si no son los de la ventana, no se adjunta."""
    out, destino = _informe_cerrado(tmp_path, {})
    resumen = json.loads(destino.with_suffix('.json').read_text(encoding='utf-8'))
    resumen.update(project='PROY-1', escenario='2026')
    destino.with_suffix('.json').write_text(json.dumps(resumen), encoding='utf-8')
    assert b.adjuntos_del_informe(out, destino.name, proyecto='PROY-1', escenario='2026')
    with pytest.raises(b.BorradorInvalido, match='proyecto'):
        b.adjuntos_del_informe(out, destino.name, proyecto='PROY-2')
    with pytest.raises(b.BorradorInvalido, match='escenario'):
        b.adjuntos_del_informe(out, destino.name, proyecto='PROY-1', escenario='2030')


def test_con_un_trabajo_de_informes_en_curso_no_se_adjunta(tmp_path):
    """110:RF-3 — mientras un trabajo de informes corre en el espacio, el informe puede cambiar: se espera."""
    out, destino = _informe_cerrado(tmp_path, {})
    with pytest.raises(b.BorradorInvalido, match='en curso'):
        b.adjuntos_del_informe(out, destino.name, informes_en_curso=True)


def _txt_red() -> bytes:
    return b'[SECTION]\nFORMAT_SECTION=SectionID,FromNodeID\nS1,N1\n[CUSTOMER LOADS]\nX\n'


def _mdb() -> bytes:
    return b'\x00\x01\x00\x00Standard Jet DB\x00' + b'\x00' * 64


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('RED.txt', _txt_red())
    return buf.getvalue()


PROHIBIDOS = {
    'txt_red': _txt_red(),
    'mdb': _mdb(),
    'vnr_bak': b'TAPE' + b'\x00' * 64,
    'zip': _zip(),
    'env': b'CLIENT_SECRET=abc\nREFRESH_TOKEN=xyz\n',
    'json_token': json.dumps({'refresh_token': 'x', 'client_secret': 'y'}).encode(),
}


@pytest.mark.parametrize('clave', sorted(PROHIBIDOS))
@pytest.mark.parametrize('extension', ['.pdf', '.docx', '.xlsx'])
def test_datos_crudos_y_credenciales_renombrados_se_rechazan_por_contenido(tmp_path, clave, extension):
    """110:RF-11 — un TXT, una MDB, un paquete VNR, un ZIP o un .env renombrados a .pdf/.docx/.xlsx no se adjuntan."""
    ruta = _adjunto(tmp_path, f'prohibido{extension}', PROHIBIDOS[clave])
    with pytest.raises(b.AdjuntoProhibido):
        b.comprobar_adjunto(ruta)
    with pytest.raises(b.AdjuntoProhibido):
        _borrador(tmp_path, adjuntos=[ruta])


@pytest.mark.parametrize('nombre', ['RED.txt', 'base.mdb', 'red.zip', 'credenciales.env', 'paquete.bak', 'x.json'])
def test_solo_word_pdf_y_excel(tmp_path, nombre):
    """110:RF-11 — cualquier otra extensión se rechaza, aunque el contenido fuera inofensivo."""
    with pytest.raises(b.AdjuntoProhibido):
        b.comprobar_adjunto(_adjunto(tmp_path, nombre, b'%PDF-1.7\n'))


def test_un_word_que_lleva_otro_fichero_dentro_o_una_credencial_se_rechaza(tmp_path):
    """110:RF-11 — un Word con un objeto incrustado (podría ser la MDB) o con un token escrito no se adjunta."""
    incrustado = _adjunto(tmp_path, 'a.docx', _ooxml('word', extra={'word/embeddings/oleObject1.bin': _mdb()}))
    with pytest.raises(b.AdjuntoProhibido, match='incrustado'):
        b.comprobar_adjunto(incrustado)
    con_token = _adjunto(tmp_path, 'b.docx', _ooxml('word', texto='refresh_token=abc'))
    with pytest.raises(b.AdjuntoProhibido, match='credencial'):
        b.comprobar_adjunto(con_token)
    excel_como_word = _adjunto(tmp_path, 'c.docx', _ooxml('xl'))
    with pytest.raises(b.AdjuntoProhibido):
        b.comprobar_adjunto(excel_como_word)


def test_un_informe_real_y_un_pdf_real_pasan(tmp_path):
    """110:RF-11 — lo que sí es un informe pasa: el Word que escribe el conversor y un PDF."""
    _, destino = _informe_cerrado(tmp_path, {})
    b.comprobar_adjunto(destino)
    b.comprobar_adjunto(_adjunto(tmp_path, 'x.pdf', b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'))




# ------------------------------------------------------------------ T4: validez del estudio (RF-12)
def test_validez_un_informe_valido(tmp_path):
    """110:RF-12 — un informe de factibilidad con su dictamen es válido y el cuerpo no lo pone en duda."""
    _, destino = _informe_cerrado(tmp_path, {})
    _, resumen = b.resumen_del_informe(destino.parent, destino.name)
    v = b.validez_del_estudio(resumen)
    assert v == {'valido': True, 'motivo': ''}
    assert b.AVISO_NO_VALIDO not in b.cuerpo_propuesto('Informe', v)


@pytest.mark.parametrize('cambio,motivo', [
    ({'error': 'DIgSILENT no respondió'}, 'error'),
    ({'no_terminado': True}, 'no terminó'),
    ({'estado': 'bloqueado'}, 'bloqueado'),
    ({'actual': {'fuera_de_dominio': True}}, 'fuera del dominio'),
    ({'factible': None}, 'dictamen'),
])
def test_validez_estudios_que_no_valen(tmp_path, cambio, motivo):
    """110:RF-12 — con error, sin terminar, bloqueado, fuera de dominio o sin dictamen: «no válido como estudio»."""
    _, destino = _informe_cerrado(tmp_path, {})
    _, resumen = b.resumen_del_informe(destino.parent, destino.name)
    resumen.update(cambio)
    v = b.validez_del_estudio(resumen)
    assert v['valido'] is False and motivo in v['motivo']
    cuerpo = b.cuerpo_propuesto('Informe', v)
    assert cuerpo.startswith(b.AVISO_NO_VALIDO) and motivo in cuerpo


def test_validez_sin_json(tmp_path):
    """110:RF-12 — un informe sin su resumen no se presenta como estudio válido."""
    v = b.validez_del_estudio(None)
    assert v['valido'] is False and 'resumen' in v['motivo']


def test_validez_de_un_tipo_que_no_se_conoce(tmp_path):
    """110:RF-12 — un resumen de otro tipo sin dictamen legible tampoco se presenta como válido."""
    assert b.validez_del_estudio({'tipo': 'otro'})['valido'] is False
    assert b.validez_del_estudio({'tipo': 'resumen_estudios', 'conclusiones': ['ok']})['valido'] is True




# ------------------------------------------------------------------ T6: contactos habituales (RF-14)
from convertersmartgrid.adaptadores.correo import envios as e  # noqa: E402
from correo_simulado import CredencialesSimuladas  # noqa: E402


def _envio_aceptado(raiz, tmp_path, para, bid):
    diario = e.DiarioEnvios(raiz)
    borr = _borrador(tmp_path, para=para)
    return e.enviar(diario, borr, borr.firma(), espacio='w', borrador_id=bid, proveedor=ProveedorSimulado(),
                    credenciales=CredencialesSimuladas(), construir=lambda x, c: b'M')


def test_habituales_son_los_aceptados_y_la_cuenta(tmp_path):
    """110:RF-14 — direcciones con un envío aceptado desde el espacio, más la cuenta del operador."""
    raiz = tmp_path / 'ws'
    _envio_aceptado(raiz, tmp_path, ['cliente@otra.test'], 'b1')
    diario = e.DiarioEnvios(raiz)
    borr = _borrador(tmp_path, para=['nadie@otra.test'])
    diario_r = e.enviar(diario, borr, borr.firma(), espacio='w', borrador_id='b2',
                        proveedor=ProveedorSimulado(modo='400'), credenciales=CredencialesSimuladas(),
                        construir=lambda x, c: b'M')
    assert diario_r['estado'] == 'rechazado'
    habituales = diario.contactos_habituales('operador@empresa-a.test')
    assert habituales == {'cliente@otra.test', 'jefe@empresa-a.test', 'operador@empresa-a.test'}


def test_habituales_avisos_nueva_mal_escrita_y_habitual(tmp_path):
    """110:RF-14 — una nueva lleva aviso; una mal escrita, aviso con la sugerencia; una habitual, nada."""
    habituales = {'cliente@otra.test', 'operador@empresa-a.test'}
    borr = _borrador(tmp_path, para=['cliente@otra.test', 'clinete@otra.test', 'nueva@lejos.test'],
                     cc=['cliente@otar.test'])
    avisos = b.avisos_de_contactos(borr, habituales)
    assert 'cliente@otra.test' not in avisos
    assert avisos['clinete@otra.test']['sugerencia'] == 'cliente@otra.test'
    assert avisos['cliente@otar.test']['sugerencia'] == 'cliente@otra.test'
    assert avisos['nueva@lejos.test']['sugerencia'] is None
    assert all('habitual' in a['aviso'] for a in avisos.values())


def test_habituales_el_aviso_no_impide_el_envio(tmp_path):
    """110:RF-14 — tras el aviso, el envío sale igual con la confirmación."""
    recibo = _envio_aceptado(tmp_path / 'ws', tmp_path, ['nueva@lejos.test'], 'b1')
    assert recibo['estado'] == 'aceptado'


def test_habituales_dos_espacios_no_comparten(tmp_path):
    """110:RF-14 — los contactos de un espacio no son los de otro."""
    _envio_aceptado(tmp_path / 'ws1', tmp_path, ['cliente@otra.test'], 'b1')
    assert 'cliente@otra.test' not in e.DiarioEnvios(tmp_path / 'ws2').contactos_habituales('operador@empresa-a.test')


# ------------------------------------------------------------------ enlace: forma y exclusión con los adjuntos (RF-10)
@pytest.mark.parametrize('mal', ['http://expediente.test/x', 'ftp://expediente.test/x', 'https://exp.test/a b',
                                 'https://exp.test/x\r\nBcc: z@y.test', 'javascript:alert(1)',
                                 'https://exp.test/' + 'x' * 2048])
def test_un_enlace_que_no_es_https_limpio_se_rechaza(tmp_path, mal):
    """110:RF-10 — el enlace al expediente es una dirección https:// sin espacios ni saltos de línea."""
    with pytest.raises(b.BorradorInvalido, match='https'):
        _borrador(tmp_path, adjuntos=[], enlace=mal)


def test_adjuntos_y_enlace_a_la_vez_no(tmp_path):
    """110:RF-1, RF-10 — la ventana elige adjuntos o enlace; los dos a la vez no se preparan."""
    with pytest.raises(b.BorradorInvalido, match='no los dos'):
        _borrador(tmp_path, enlace='https://expediente.test/x')
    borr = _borrador(tmp_path, adjuntos=[], enlace='  https://expediente.test/x  ')
    assert borr.enlace == 'https://expediente.test/x' and borr.adjuntos == ()
    assert _borrador(tmp_path, enlace='   ').enlace is None
