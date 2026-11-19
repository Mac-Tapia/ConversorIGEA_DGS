"""086:RF-117 (T87): varias aperturas a la vez del búfer de episodios sin índice no chocan al rehacerlo.

CI del 19-11 (48e082e7): la e2e F03 cayó con «PermissionError: [WinError 32] … _digital_twin\\episodios.nuevo»: dos
aperturas del búfer rehacían el índice con el mismo temporal, y una lo borraba o reemplazaba mientras la otra lo tenía
abierto. Ninguna debe fallar y el índice debe quedar válido con todos los episodios.
"""
from __future__ import annotations

import threading

from test_digital_twin_episode import _payload

from convertersmartgrid.adaptadores.digital_twin import buffer as bf
from convertersmartgrid.dominio.digital_twin import episode as ep


def _abrir_a_la_vez(raiz, n: int = 8) -> list[BaseException]:
    errores: list[BaseException] = []
    salida = threading.Barrier(n)

    def abrir():
        try:
            salida.wait()
            bf.BuferEpisodios(raiz)
        except BaseException as exc:  # noqa: BLE001 - se aseveran todos
            errores.append(exc)

    hilos = [threading.Thread(target=abrir) for _ in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(30)
    return errores


def test_aperturas_simultaneas_sin_indice_no_fallan(tmp_path):
    raiz = tmp_path / 'twin'
    bufer = bf.BuferEpisodios(raiz)
    for i in range(12):
        bufer.guardar(ep.leer_episodio(_payload(creado=f'2026-11-19T00:00:{i:02d}+00:00')))
    for vuelta in range(6):
        bufer.indice.unlink()
        errores = _abrir_a_la_vez(raiz)
        assert errores == [], f'vuelta {vuelta}: {errores[:2]}'
        assert bf.BuferEpisodios(raiz)._indice_valido()
        with bf.closing(bf.sqlite3.connect(bufer.indice)) as con:
            assert con.execute('SELECT count(*) FROM episodios').fetchone()[0] == 12
    assert not list(raiz.glob('episodios*.nuevo*')), 'no quedan temporales'
