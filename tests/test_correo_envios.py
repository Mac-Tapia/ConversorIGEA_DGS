"""Spec 110: diario de envíos por espacio, idempotencia, estado desconocido sin reenvío y enlace al expediente."""
from __future__ import annotations

import io
import os
import threading
import time
import zipfile

import pytest

from correo_simulado import CompartidorSimulado, CredencialesSimuladas, ProveedorSimulado, sin_red  # noqa: F401

from convertersmartgrid.adaptadores.correo import borrador as b
from convertersmartgrid.adaptadores.correo import envios as e


@pytest.fixture(autouse=True)
def _sin_red(sin_red):  # noqa: F811
    yield


def _docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', '<x>informe</x>')
    return buf.getvalue()


def _borrador(tmp_path, **cambios):
    ruta = tmp_path / 'informe.docx'
    if not ruta.exists():
        ruta.write_bytes(_docx())
    datos = dict(cuenta='operador@empresa-a.test', proveedor='google', para=['cliente@otra.test'],
                 asunto='Informe', cuerpo='Adjunto.', adjuntos=[ruta], extra={'informe': 'informe.docx'})
    datos.update(cambios)
    return b.crear_borrador(**datos)


def _construir(borrador, clave):
    return f'Message-ID: {e.message_id(clave)}\r\n\r\ncuerpo'.encode()


def _enviar(diario, borr, firma=None, *, proveedor, credenciales=None, borrador_id='b1', espacio='w1'):
    return e.enviar(diario, borr, borr.firma() if firma is None else firma, espacio=espacio, borrador_id=borrador_id,
                    proveedor=proveedor, credenciales=credenciales or CredencialesSimuladas(), construir=_construir)


def test_el_recibo_guarda_clave_id_estado_hora_destinatarios_y_huella(tmp_path):
    """110:RF-8 — el recibo de un envío aceptado tiene todo lo que pide la spec."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado()
    borr = _borrador(tmp_path)
    recibo = _enviar(diario, borr, proveedor=prov)
    assert recibo['estado'] == 'aceptado' and recibo['id_proveedor'] == 'sim-1'
    assert len(recibo['clave']) == 64 and recibo['message_id'] == e.message_id(recibo['clave'])
    assert recibo['destinatarios'] == {'para': ['cliente@otra.test'], 'cc': [], 'cco': []}
    assert recibo['huella_informe'] == borr.adjuntos[0].sha256 and recibo['informe'] == 'informe.docx'
    assert isinstance(recibo['hora'], str) and recibo['hora_resultado']
    assert (tmp_path / 'ws' / 'envios' / f'{recibo["clave"]}.json').is_file()
    assert diario.recibo(recibo['clave']) == recibo


def test_la_clave_se_reserva_antes_de_llamar_al_proveedor(tmp_path):
    """110:RF-7 — cuando el proveedor recibe la llamada, la reserva ya está en el disco."""
    diario = e.DiarioEnvios(tmp_path / 'ws')
    vistos = []

    class Mira(ProveedorSimulado):
        def enviar(self, mensaje, *, token):
            vistos.extend(p.name for p in (tmp_path / 'ws' / 'envios').glob('*.json'))
            estados = [diario.recibo(p.stem)['estado'] for p in (tmp_path / 'ws' / 'envios').glob('*.json')]
            assert estados == ['enviando']
            return super().enviar(mensaje, token=token)

    recibo = _enviar(diario, _borrador(tmp_path), proveedor=Mira())
    assert vistos == [f'{recibo["clave"]}.json']


def test_dos_confirmaciones_de_la_misma_firma_una_sola_llamada(tmp_path):
    """110:RF-7 — un doble POST con la misma firma encuentra la clave y devuelve el mismo recibo."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado()
    borr = _borrador(tmp_path)
    primero = _enviar(diario, borr, proveedor=prov)
    segundo = _enviar(diario, borr, proveedor=prov)
    assert len(prov.llamadas) == 1 and segundo == primero


def test_doble_clic_a_la_vez_una_sola_llamada(tmp_path):
    """110:RF-7 — dos confirmaciones simultáneas: la reserva exclusiva deja pasar solo una al proveedor."""
    diario = e.DiarioEnvios(tmp_path / 'ws')
    prov = ProveedorSimulado(esperar=threading.Event())
    borr = _borrador(tmp_path)
    resultados = []
    hilos = [threading.Thread(target=lambda: resultados.append(_enviar(diario, borr, proveedor=prov)))
             for _ in range(4)]
    for h in hilos:
        h.start()
    time.sleep(0.3)
    prov.esperar.set()
    for h in hilos:
        h.join(5)
    assert len(prov.llamadas) == 1
    assert len({r['clave'] for r in resultados}) == 1


def test_un_adjunto_cambiado_no_reserva_ni_llama(tmp_path):
    """110:RF-4 — si la firma no vale, ni reserva ni llamada."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado()
    borr = _borrador(tmp_path)
    firma = borr.firma()
    (tmp_path / 'informe.docx').write_bytes(_docx() + b'x')
    with pytest.raises(b.ConfirmacionAnulada):
        _enviar(diario, borr, firma, proveedor=prov)
    assert prov.llamadas == [] and not list((tmp_path / 'ws').rglob('*.json'))


def test_timeout_tras_aceptar_queda_desconocido_y_no_se_reenvia(tmp_path):
    """110:RF-9 — el proveedor acepta y no responde: desconocido, y ni otra confirmación ni el arranque lo reenvían."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado(modo='acepta_y_no_responde')
    borr = _borrador(tmp_path)
    recibo = _enviar(diario, borr, proveedor=prov)
    assert recibo['estado'] == 'desconocido' and 'Enviados' in recibo['motivo']
    prov.modo = 'acepta'
    assert _enviar(diario, borr, proveedor=prov)['estado'] == 'desconocido'
    otro = e.DiarioEnvios(tmp_path / 'ws')
    otro.reconciliar_al_arrancar()
    assert _enviar(otro, borr, proveedor=prov)['estado'] == 'desconocido'
    assert len(prov.llamadas) == 1


@pytest.mark.parametrize('modo', ['500'])
def test_un_5xx_tambien_es_desconocido(tmp_path, modo):
    """110:RF-9 — un 5xx no dice si salió: desconocido, sin reenvío."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado(modo=modo)
    assert _enviar(diario, _borrador(tmp_path), proveedor=prov)['estado'] == 'desconocido'


def test_solo_no_llego_abre_otro_intento_con_otra_clave(tmp_path):
    """110:RF-9 — «Llegó» lo cierra; «No llegó» permite un intento nuevo, con otra clave y una sola llamada más."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado(modo='acepta_y_no_responde')
    borr = _borrador(tmp_path)
    primero = _enviar(diario, borr, proveedor=prov)
    resuelto = diario.resolver(primero['clave'], llego=False)
    assert resuelto['estado'] == 'rechazado' and resuelto['resolucion'] == 'no_llego'
    prov.modo = 'acepta'
    segundo = _enviar(diario, borr, proveedor=prov)
    assert segundo['clave'] != primero['clave'] and segundo['intento'] == 2 and segundo['estado'] == 'aceptado'
    assert len(prov.llamadas) == 2
    assert _enviar(diario, borr, proveedor=prov) == segundo and len(prov.llamadas) == 2


def test_llego_cierra_el_desconocido_sin_reenviar(tmp_path):
    """110:RF-9 — el operador dice que llegó: queda aceptado y no hay intento nuevo."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado(modo='acepta_y_no_responde')
    borr = _borrador(tmp_path)
    primero = _enviar(diario, borr, proveedor=prov)
    assert diario.resolver(primero['clave'], llego=True)['estado'] == 'aceptado'
    assert _enviar(diario, borr, proveedor=prov)['clave'] == primero['clave'] and len(prov.llamadas) == 1
    with pytest.raises(e.EnvioError):
        diario.resolver(primero['clave'], llego=False)


def test_un_rechazo_admite_otra_confirmacion(tmp_path):
    """110:RF-9 — un rechazado no salió: otra confirmación es otro intento."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado(modo='429')
    borr = _borrador(tmp_path)
    assert _enviar(diario, borr, proveedor=prov)['estado'] == 'rechazado'
    prov.modo = 'acepta'
    assert _enviar(diario, borr, proveedor=prov)['intento'] == 2 and len(prov.llamadas) == 2


def test_cuenta_revocada_rechaza_sin_llamar(tmp_path):
    """110:RF-9 — sin token (cuenta revocada) el correo no sale y se pide volver a conectar la cuenta."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado()
    recibo = _enviar(diario, _borrador(tmp_path), proveedor=prov, credenciales=CredencialesSimuladas(revocada=True))
    assert recibo['estado'] == 'rechazado' and 'conectar' in recibo['motivo'] and prov.llamadas == []


def test_el_401_del_proveedor_pide_volver_a_conectar(tmp_path):
    """110:RF-9 — el proveedor dice 401: rechazado, «vuelva a conectar la cuenta»."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado(modo='401')
    recibo = _enviar(diario, _borrador(tmp_path), proveedor=prov)
    assert recibo['estado'] == 'rechazado' and 'conectar' in recibo['motivo']


def test_un_trabajo_interrumpido_queda_desconocido_al_arrancar(tmp_path):
    """110:RF-9 — una reserva en «reservado» o «enviando» sin resultado pasa a desconocido, nunca a reenviarse."""
    diario = e.DiarioEnvios(tmp_path / 'ws')
    borr = _borrador(tmp_path)
    clave = e.clave_envio('w1', 'b1', borr.firma(), 1)
    diario.reservar(clave, borr, espacio='w1', borrador_id='b1', intento=1)
    diario.marcar(clave, 'enviando')
    clave2 = e.clave_envio('w1', 'b2', borr.firma(), 1)
    diario.reservar(clave2, borr, espacio='w1', borrador_id='b2', intento=1)
    cambiados = e.DiarioEnvios(tmp_path / 'ws').reconciliar_al_arrancar()
    assert sorted(cambiados) == sorted([clave, clave2])
    assert {diario.recibo(c)['estado'] for c in (clave, clave2)} == {'desconocido'}


def test_cancelar_antes_de_llamar_libera_la_reserva(tmp_path):
    """110:RF-7 — cancelar con la reserva hecha y sin llamada la deja cancelada; un envío en curso no se cancela."""
    diario = e.DiarioEnvios(tmp_path / 'ws')
    borr = _borrador(tmp_path)
    clave = e.clave_envio('w1', 'b1', borr.firma(), 1)
    diario.reservar(clave, borr, espacio='w1', borrador_id='b1', intento=1)
    assert diario.cancelar(clave)['estado'] == 'cancelado'
    clave2 = e.clave_envio('w1', 'b2', borr.firma(), 1)
    diario.reservar(clave2, borr, espacio='w1', borrador_id='b2', intento=1)
    diario.marcar(clave2, 'enviando')
    with pytest.raises(e.EnvioError):
        diario.cancelar(clave2)


def test_historial_por_informe(tmp_path):
    """110:RF-13 — el historial de un informe lista sus envíos, del más antiguo al más reciente, y no los de otro."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado()
    borr = _borrador(tmp_path)
    uno = _enviar(diario, borr, proveedor=prov, borrador_id='b1')
    dos = _enviar(diario, _borrador(tmp_path, para=['otro@otra.test']), proveedor=prov, borrador_id='b2')
    otro_dir = tmp_path / 'otro'
    otro_dir.mkdir()
    (otro_dir / 'informe2.docx').write_bytes(_docx())
    _enviar(diario, b.crear_borrador(cuenta='operador@empresa-a.test', proveedor='google', para=['x@otra.test'],
                                     adjuntos=[otro_dir / 'informe2.docx'], extra={'informe': 'informe2.docx'}),
            proveedor=prov, borrador_id='b3')
    assert [r['clave'] for r in diario.historial('informe.docx')] == [uno['clave'], dos['clave']]
    assert diario.historial('nada.docx') == []


def test_un_recibo_roto_no_tumba_el_historial(tmp_path):
    """110:RF-13 — un fichero ilegible en envios/ se salta y el resto se lista."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado()
    uno = _enviar(diario, _borrador(tmp_path), proveedor=prov)
    (tmp_path / 'ws' / 'envios' / ('f' * 64 + '.json')).write_text('{roto', encoding='utf-8')
    assert [r['clave'] for r in diario.historial('informe.docx')] == [uno['clave']]


def test_los_recibos_viajan_en_la_copia_y_la_retencion_no_los_borra(tmp_path):
    """110:RF-8 — <espacio>/envios/ va en la copia de datos (086) y la limpieza diaria (062) no lo toca."""
    from convertersmartgrid.presentacion.web.copia_datos import crear_copia
    from convertersmartgrid.presentacion.web.jobs import JobManager
    from convertersmartgrid.presentacion.web.retencion import RetencionDiaria
    from convertersmartgrid.presentacion.web.workspace import WorkspaceStore

    raiz = tmp_path / 'web'
    store = WorkspaceStore(raiz)
    ws = store.create()
    diario = e.DiarioEnvios(ws.root)
    recibo = _enviar(diario, _borrador(tmp_path), proveedor=ProveedorSimulado(), espacio=ws.id)
    ruta = ws.root / 'envios' / f'{recibo["clave"]}.json'
    viejo = time.time() - 30 * 86400
    os.utime(ruta, (viejo, viejo))
    RetencionDiaria(store, JobManager(lambda *a: None)).revisar_si_vence()
    assert ruta.is_file()
    m = crear_copia(tmp_path / 'copias', raices={'datos': raiz})
    assert f'{ws.id}/envios/{recibo["clave"]}.json' in {f['ruta'] for f in m['ficheros']}
    assert not (ws.out_dir / 'envios').exists(), 'los recibos no van en la salida del espacio'




# ------------------------------------------------------------------ T7: enviar un enlace (RF-10)
def _borrador_enlace(tmp_path, **cambios):
    datos = dict(cuenta='operador@empresa-a.test', proveedor='microsoft', para=['cliente@otra.test'],
                 cc=['copia@otra.test'], asunto='Expediente', cuerpo='Aquí tiene el expediente.',
                 enlace='https://expediente.test/abc',
                 extra={'informe': 'informe.docx', 'expediente': 'EXP-1', 'huella_informe': 'f' * 64})
    datos.update(cambios)
    return b.crear_borrador(**datos)


def test_enlace_primero_el_permiso_y_luego_el_correo_con_dos_recibos(tmp_path):
    """110:RF-10 — se concede la lectura a esos destinatarios exactos y solo después sale el correo."""
    orden = []
    compartidor = CompartidorSimulado(orden=orden)

    class Anota(ProveedorSimulado):
        def enviar(self, mensaje, *, token):
            orden.append('correo')
            return super().enviar(mensaje, token=token)

    prov = Anota(nombre='microsoft')
    borr = _borrador_enlace(tmp_path)
    recibo = e.enviar(e.DiarioEnvios(tmp_path / 'ws'), borr, borr.firma(), espacio='w1', borrador_id='b1',
                      proveedor=prov, credenciales=CredencialesSimuladas(), construir=_construir,
                      compartidor=compartidor)
    assert orden == ['permiso', 'correo']
    assert compartidor.concesiones == [('EXP-1', ('cliente@otra.test', 'copia@otra.test'))]
    assert [p['paso'] for p in recibo['pasos']] == ['permiso', 'correo']
    assert recibo['pasos'][0]['estado'] == 'concedido' and recibo['pasos'][0]['id'] == 'perm-1'
    assert recibo['pasos'][1]['id'] == 'sim-1' and recibo['estado'] == 'aceptado'
    assert recibo['huella_informe'] == 'f' * 64 and recibo['enlace'] == 'https://expediente.test/abc'


def test_enlace_si_el_permiso_falla_no_sale_el_correo(tmp_path):
    """110:RF-10 — sin el permiso concedido, cero correos y el recibo dice por qué."""
    prov = ProveedorSimulado(nombre='microsoft')
    borr = _borrador_enlace(tmp_path)
    recibo = e.enviar(e.DiarioEnvios(tmp_path / 'ws'), borr, borr.firma(), espacio='w1', borrador_id='b1',
                      proveedor=prov, credenciales=CredencialesSimuladas(), construir=_construir,
                      compartidor=CompartidorSimulado(falla=True))
    assert prov.llamadas == [] and recibo['estado'] == 'rechazado' and 'acceso' in recibo['motivo']
    assert recibo['pasos'][0]['estado'] == 'rechazado'


def test_enlace_sin_compartidor_o_sin_expediente_no_envia(tmp_path):
    """110:RF-10 — sin la interfaz de la 109 o sin expediente, el enlace no se envía."""
    prov = ProveedorSimulado(nombre='microsoft')
    for compartidor, extra in ((None, None), (CompartidorSimulado(), {'informe': 'informe.docx'})):
        borr = _borrador_enlace(tmp_path, **({'extra': extra} if extra else {}))
        recibo = e.enviar(e.DiarioEnvios(tmp_path / f'ws{id(extra)}'), borr, borr.firma(), espacio='w1',
                          borrador_id='b1', proveedor=prov, credenciales=CredencialesSimuladas(),
                          construir=_construir, compartidor=compartidor)
        assert recibo['estado'] == 'rechazado'
    assert prov.llamadas == []


def test_enlace_se_ofrece_si_los_adjuntos_pasan_del_limite(tmp_path):
    """110:RF-10 — por encima del límite del proveedor, la vista previa ofrece el enlace."""
    borr = _borrador(tmp_path)
    assert e.excede_limite(borr, ProveedorSimulado(limite_adjuntos=10)) is True
    assert e.excede_limite(borr, ProveedorSimulado()) is False


# ------------------------------------------------------------------ salida apagada y reserva hecha por la ruta (RF-7, RF-9)
def test_salida_apagada_es_rechazado_y_no_desconocido(tmp_path):
    """110:RF-9 — con la salida a la red apagada (086:RF-22) nada salió: rechazado, y admite otro intento."""
    from convertersmartgrid.dominio.salidas_red import SalidaApagada

    class Apagado(ProveedorSimulado):
        def enviar(self, mensaje, *, token):
            self.llamadas.append({'mensaje': mensaje})
            raise SalidaApagada('La salida del correo está apagada (CSG_SALIDA_CORREO_GOOGLE).')

    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), Apagado()
    borr = _borrador(tmp_path)
    recibo = _enviar(diario, borr, proveedor=prov)
    assert recibo['estado'] == 'rechazado' and 'apagada' in recibo['motivo']
    assert diario.intento_para('w1', 'b1', borr.firma()) == 2


def _reservar(diario, borr, *, espacio='w1', borrador_id='b1'):
    intento = diario.intento_para(espacio, borrador_id, borr.firma())
    clave = e.clave_envio(espacio, borrador_id, borr.firma(), intento)
    recibo, nuevo = diario.reservar(clave, borr, espacio=espacio, borrador_id=borrador_id, intento=intento)
    assert nuevo and recibo['estado'] == 'reservado'
    return clave


def _enviar_reservada(diario, borr, clave, prov):
    return e.enviar(diario, borr, borr.firma(), espacio='w1', borrador_id='b1', proveedor=prov,
                    credenciales=CredencialesSimuladas(), construir=_construir, reservada=clave)


def test_reserva_de_la_ruta_un_solo_envio_aunque_corran_dos_trabajos(tmp_path):
    """110:RF-7 — la ruta reserva al encolar; el trabajo envía esa reserva, y otro con la misma clave no llama."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado()
    borr = _borrador(tmp_path)
    clave = _reservar(diario, borr)
    primero = _enviar_reservada(diario, borr, clave, prov)
    segundo = _enviar_reservada(diario, borr, clave, prov)
    assert primero['estado'] == 'aceptado' and segundo == primero and len(prov.llamadas) == 1


def test_reserva_de_la_ruta_sin_recibo_es_un_error(tmp_path):
    """110:RF-7 — un trabajo con una clave que no está reservada no envía nada."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado()
    with pytest.raises(e.EnvioError):
        _enviar_reservada(diario, _borrador(tmp_path), 'a' * 64, prov)
    assert prov.llamadas == []


def test_reserva_de_la_ruta_con_un_adjunto_cambiado_se_cancela_y_admite_otro(tmp_path):
    """110:RF-4 — entre encolar y enviar cambió un adjunto: cancelado, sin llamar, y el siguiente intento es otro."""
    diario, prov = e.DiarioEnvios(tmp_path / 'ws'), ProveedorSimulado()
    borr = _borrador(tmp_path)
    clave = _reservar(diario, borr)
    (tmp_path / 'informe.docx').write_bytes(_docx() + b'x')
    with pytest.raises(b.ConfirmacionAnulada):
        _enviar_reservada(diario, borr, clave, prov)
    assert diario.recibo(clave)['estado'] == 'cancelado' and prov.llamadas == []
    assert diario.intento_para('w1', 'b1', borr.firma()) == 2
