"""La interfaz recuerda los ficheros de la última sesión, y los nuevos sustituyen.

Cada entrega de la distribuidora trae ficheros distintos, en otra carpeta y con otro
nombre. Si la ventana vuelve siempre a los TXT de ejemplo, hay que buscar los tres a
mano cada vez, y es fácil convertir sin darse cuenta con la entrega del mes pasado.

Esto ya existió y se quitó «para no arrastrar sesiones». El modo de fallo de guardar
rutas es conocido: se guarda una, luego el fichero se mueve o se borra, la ventana
arranca con un campo que apunta a la nada, y el problema no aparece hasta que alguien
pulsa convertir. Estas pruebas fijan las dos reglas que lo evitan:

1. Una ruta **solo se restaura si sigue existiendo**.
2. Se guarda **en cada cambio**, así que lo último elegido siempre gana.
"""

from __future__ import annotations

import json

import pytest

from igea_dgs import settings


@pytest.fixture
def ajustes(tmp_path):
    return tmp_path / 'interfaz.json'


def _txt(tmp_path, nombre: str) -> str:
    ruta = tmp_path / nombre
    ruta.write_text('[GENERAL]\n', encoding='utf-8')
    return str(ruta)


class TestLoUltimoGana:
    def test_lo_guardado_se_recupera(self, tmp_path, ajustes):
        red = _txt(tmp_path, '260924red.txt')
        settings.guardar({'red': red, 'source_crs': 'EPSG:32718'}, path=ajustes)
        recuperado = settings.cargar(path=ajustes)
        assert recuperado['red'] == red
        assert recuperado['source_crs'] == 'EPSG:32718'

    def test_una_seleccion_nueva_sustituye_a_la_anterior(self, tmp_path, ajustes):
        """El caso que se pidió: la entrega nueva desplaza a la vieja."""
        viejo = _txt(tmp_path, 'RED_030826.txt')
        settings.guardar({'red': viejo}, path=ajustes)

        nuevo = _txt(tmp_path, '260924red.txt')
        settings.guardar({'red': nuevo}, path=ajustes)

        assert settings.cargar(path=ajustes)['red'] == nuevo

    def test_las_casillas_de_preferencia_se_recuerdan(self, tmp_path, ajustes):
        settings.guardar({'include_geography': False, 'strict': False}, path=ajustes)
        recuperado = settings.cargar(path=ajustes)
        assert recuperado['include_geography'] is False
        assert recuperado['strict'] is False


class TestRutasQueYaNoEstan:
    def test_una_ruta_borrada_NO_se_restaura(self, tmp_path, ajustes):
        """Arrancar con un campo que apunta a la nada es peor que arrancar vacío."""
        red = _txt(tmp_path, 'red.txt')
        settings.guardar({'red': red, 'loads': _txt(tmp_path, 'carga.txt')}, path=ajustes)
        (tmp_path / 'red.txt').unlink()

        recuperado = settings.cargar(path=ajustes)
        assert 'red' not in recuperado
        assert 'loads' in recuperado, 'lo que sigue existiendo sí se restaura'

    def test_se_puede_saber_QUE_rutas_se_perdieron(self, tmp_path, ajustes):
        """Para poder decirlo, en vez de dejar el campo vacío sin explicación."""
        red = _txt(tmp_path, 'red.txt')
        settings.guardar({'red': red}, path=ajustes)
        (tmp_path / 'red.txt').unlink()

        perdidas = settings.olvidadas(settings.leer_crudo(path=ajustes))
        assert perdidas == [red]

    def test_la_carpeta_de_salida_se_restaura_aunque_no_exista(self, tmp_path, ajustes):
        """Se crea al convertir; exigir que exista obligaría a elegirla cada vez."""
        destino = str(tmp_path / 'todavia' / 'no' / 'existe')
        settings.guardar({'out_dir': destino}, path=ajustes)
        assert settings.cargar(path=ajustes)['out_dir'] == destino


class TestNoEstorbaNunca:
    def test_un_fichero_corrupto_no_revienta(self, ajustes):
        ajustes.write_text('{ esto no es json', encoding='utf-8')
        assert settings.cargar(path=ajustes) == {}

    def test_un_json_que_no_es_un_objeto_no_revienta(self, ajustes):
        ajustes.write_text('[1, 2, 3]', encoding='utf-8')
        assert settings.cargar(path=ajustes) == {}

    def test_sin_fichero_no_hay_nada_y_no_falla(self, tmp_path):
        assert settings.cargar(path=tmp_path / 'no_existe.json') == {}

    def test_no_se_puede_escribir_y_no_interrumpe(self, tmp_path):
        """Un perfil sin permisos no es motivo para dejar de trabajar."""
        imposible = tmp_path / 'fichero.txt'
        imposible.write_text('x', encoding='utf-8')
        assert settings.guardar({'red': 'x'}, path=imposible / 'dentro' / 'a.json') is None

    def test_los_valores_vacios_no_se_guardan(self, tmp_path, ajustes):
        settings.guardar({'red': '', 'loads': '   '}, path=ajustes)
        datos = json.loads(ajustes.read_text(encoding='utf-8'))
        assert 'red' not in datos and 'loads' not in datos


class TestLoQueNoSeGuarda:
    def test_convertir_todos_queda_fuera_a_proposito(self, tmp_path, ajustes):
        """Restaurarlo en silencio convertiría 101 alimentadores a quien esperaba uno."""
        assert 'convert_all' in settings.NO_SE_GUARDAN
        assert 'convert_all' not in settings.CAMPOS_BOOL
        settings.guardar({'convert_all': True}, path=ajustes)
        assert 'convert_all' not in json.loads(ajustes.read_text(encoding='utf-8'))

    def test_el_fichero_vive_fuera_del_repositorio(self):
        """Es preferencia de quien usa el programa, no del proyecto."""
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[1]
        assert raiz not in settings.ruta_ajustes().parents


class TestEnLaInterfaz:
    def test_la_ventana_guarda_al_elegir_un_fichero(self):
        from pathlib import Path

        fuente = (Path(__file__).resolve().parents[1]
                  / 'src' / 'igea_dgs' / 'gui.py').read_text(encoding='utf-8')
        for metodo in ('_browse_red', '_browse_loads', '_browse_equipment'):
            cuerpo = fuente.split('def ' + metodo)[1].split('\n    def ')[0]
            assert '_guardar_ajustes()' in cuerpo, metodo

    def test_lo_recordado_manda_sobre_los_txt_de_ejemplo(self):
        """Si ya se trabajó con una entrega, esa gana a los de referencia/."""
        from pathlib import Path

        fuente = (Path(__file__).resolve().parents[1]
                  / 'src' / 'igea_dgs' / 'gui.py').read_text(encoding='utf-8')
        assert 'if not self._restaurar_ajustes():' in fuente
        i = fuente.index('if not self._restaurar_ajustes():')
        j = fuente.index('_default_referencia_inputs()', i)
        assert j > i, 'el relleno de ejemplo debe ir DENTRO del caso «no había nada»'

    def test_la_ventana_guarda_tambien_al_cerrar(self):
        from pathlib import Path

        fuente = (Path(__file__).resolve().parents[1]
                  / 'src' / 'igea_dgs' / 'gui.py').read_text(encoding='utf-8')
        cuerpo = fuente.split('def _on_close')[1].split('\n    def ')[0]
        assert '_guardar_ajustes()' in cuerpo
