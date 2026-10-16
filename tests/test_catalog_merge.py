"""Completar el catálogo cuando la entrega llega incompleta.

El fallo medido sobre una entrega real de la distribuidora: el ``Equipos.txt`` del 24 de
septiembre traía **9 tipos de línea** con otra convención de nombres (``AAAC1203``,
``ATVB1-22.9KV-050``), mientras la red usaba **43** de la convención anterior
(``AA03503D``…). Los 38.879 tramos —los 4.194,6 km, el **100 % de la red**— se
resolvieron a ``DEFAULT``, con R = 0,4 Ω/km para todo cuando los valores reales van de
0,18 a 3,38.

Lo peligroso no es que falle: es que **no falla**. El modelo se convierte, se importa en
PowerFactory y converge dando un flujo impecable con todas las impedancias equivocadas.
Salía como un aviso más entre otros dos.

Completando con el catálogo de la entrega anterior, la cobertura pasó del 2 % al 93 %, y
``DEFAULT`` del 100 % al 0,6 % —que son los ramales de acometida de 0,3 m, los únicos que
el export deja así a propósito—.
"""

from __future__ import annotations

import pytest

from igea_dgs import catalog_merge as cm


def _equipos(tmp_path, nombre: str, lineas: list[tuple[str, float]]) -> str:
    """Un BD_Equipo mínimo con los tipos indicados."""
    filas = [
        '[GENERAL]', 'DATE=01/01/2026', '',
        '[LINE]',
        'FORMAT_LINE=ID,PhaseCondID,NeutralCondID,SpacingID,R1,R0,X1,X0,B1,B0,Amps,Amps_2,LockImpedance',
    ]
    for codigo, r in lineas:
        filas.append(f'{codigo},DEFAULT,NONE,DEFAULT,{r},{r},0.45,0.45,3.7,3.7,150,150,0')
    ruta = tmp_path / nombre
    ruta.write_text('\n'.join(filas) + '\n', encoding='utf-8')
    return str(ruta)


class _DatasetFalso:
    """Lo mínimo que mira catalog_merge: qué usa la red y qué trae el catálogo."""

    def __init__(self, usados: list[str], en_catalogo: list[tuple[str, float]]):
        self.line_configurations = {
            f'S{i}': {'LineCableID': c} for i, c in enumerate(usados)
        }
        self.equipment_tables = {
            'LINE': tuple(
                {'ID': c, 'R1': str(r), 'R0': str(r), 'X1': '0.45', 'X0': '0.45',
                 'B1': '3.7', 'B0': '3.7', 'Amps': '150'}
                for c, r in en_catalogo
            )
        }


class TestDiagnostico:
    def test_mide_la_cobertura_real(self):
        ds = _DatasetFalso(['A', 'B', 'C', 'D'], [('A', 1.0)])
        informe = cm.diagnosticar(ds)
        assert len(informe.codigos_en_red) == 4
        assert informe.cobertura_final == pytest.approx(0.25)
        assert informe.sin_resolver == {'B', 'C', 'D'}

    def test_un_catalogo_completo_da_cobertura_total(self):
        ds = _DatasetFalso(['A', 'B'], [('A', 1.0), ('B', 2.0)])
        assert cm.diagnosticar(ds).cobertura_final == pytest.approx(1.0)

    def test_no_toca_nada(self):
        """Diagnosticar es mirar, no arreglar."""
        ds = _DatasetFalso(['A', 'B'], [('A', 1.0)])
        antes = len(ds.equipment_tables['LINE'])
        cm.diagnosticar(ds)
        assert len(ds.equipment_tables['LINE']) == antes

    def test_alias_explicito_cuenta_como_resuelto(self):
        ds = _DatasetFalso(['AUSENTE'], [('EXISTENTE', 1.0)])
        informe = cm.diagnosticar(ds, aliases={'AUSENTE': 'EXISTENTE'})
        assert informe.cobertura_final == pytest.approx(1.0)
        assert informe.resueltos_por_alias == {'AUSENTE'}

    def test_vecino_unico_cuenta_como_resuelto(self):
        ds = _DatasetFalso(['AA05001D'], [('AA05002D', 1.0)])
        informe = cm.diagnosticar(ds)
        assert informe.cobertura_final == pytest.approx(1.0)
        assert informe.resueltos_por_alias == {'AA05001D'}

    def test_una_red_sin_tipos_no_divide_por_cero(self):
        ds = _DatasetFalso([], [])
        assert cm.diagnosticar(ds).cobertura_final == pytest.approx(1.0)


class TestCompletar:
    def test_trae_los_codigos_que_faltan(self, tmp_path):
        ds = _DatasetFalso(['A', 'B', 'C'], [('A', 1.0)])
        otro = _equipos(tmp_path, 'anterior.txt', [('B', 2.0), ('C', 3.0)])
        informe = cm.completar(ds, [otro])
        assert informe.total_anadidos == 2
        assert informe.cobertura_final == pytest.approx(1.0)
        assert informe.sin_resolver == set()

    def test_NO_sobrescribe_lo_ya_cargado(self, tmp_path):
        """Si la entrega trae un conductor, ese manda: solo se rellenan huecos."""
        ds = _DatasetFalso(['A'], [('A', 1.0)])
        otro = _equipos(tmp_path, 'anterior.txt', [('A', 9.9)])
        cm.completar(ds, [otro])
        filas = [f for f in ds.equipment_tables['LINE'] if f['ID'] == 'A']
        assert len(filas) == 1
        assert float(filas[0]['R1']) == pytest.approx(1.0), 'el cargado debe prevalecer'

    def test_solo_trae_lo_que_la_red_usa(self, tmp_path):
        """El resto del catálogo ajeno solo añadiría ruido."""
        ds = _DatasetFalso(['A'], [])
        otro = _equipos(tmp_path, 'anterior.txt', [('A', 1.0), ('Z', 2.0)])
        cm.completar(ds, [otro])
        assert {f['ID'] for f in ds.equipment_tables['LINE']} == {'A'}

    def test_dice_de_que_fichero_vino_cada_codigo(self, tmp_path):
        ds = _DatasetFalso(['A', 'B'], [])
        uno = _equipos(tmp_path, 'uno.txt', [('A', 1.0)])
        dos = _equipos(tmp_path, 'dos.txt', [('B', 2.0)])
        informe = cm.completar(ds, [uno, dos])
        assert informe.anadidos[uno] == ['A']
        assert informe.anadidos[dos] == ['B']

    def test_el_primero_que_lo_trae_gana(self, tmp_path):
        ds = _DatasetFalso(['A'], [])
        uno = _equipos(tmp_path, 'uno.txt', [('A', 1.0)])
        dos = _equipos(tmp_path, 'dos.txt', [('A', 9.9)])
        cm.completar(ds, [uno, dos])
        fila = next(f for f in ds.equipment_tables['LINE'] if f['ID'] == 'A')
        assert float(fila['R1']) == pytest.approx(1.0)

    def test_un_fichero_que_no_existe_se_ignora(self, tmp_path):
        ds = _DatasetFalso(['A'], [])
        informe = cm.completar(ds, [tmp_path / 'no_esta.txt'])
        assert informe.total_anadidos == 0
        assert informe.sin_resolver == {'A'}

    def test_lo_que_sigue_faltando_se_declara(self, tmp_path):
        ds = _DatasetFalso(['A', 'B'], [])
        otro = _equipos(tmp_path, 'anterior.txt', [('A', 1.0)])
        informe = cm.completar(ds, [otro])
        assert informe.sin_resolver == {'B'}
        assert 'B' in informe.texto()


class TestElInformeSeEntiende:
    def test_dice_cobertura_antes_y_despues(self, tmp_path):
        ds = _DatasetFalso(['A', 'B', 'C', 'D'], [('A', 1.0)])
        otro = _equipos(tmp_path, 'anterior.txt', [('B', 2.0), ('C', 3.0)])
        texto = cm.completar(ds, [otro]).texto()
        assert '25 %' in texto, 'la cobertura inicial'
        assert '75 %' in texto, 'la final'
        assert 'anterior.txt' in texto, 'de dónde vino lo añadido'


class TestElInventarioLoEscala:
    """Que falten dos códigos es rutina; que falte casi todo es otra cosa."""

    def _inventario(self, usados, en_catalogo, tmp_path, aliases=None):
        from igea_dgs.inventory import build_dataset_inventory

        ds = _DatasetFalso(usados, en_catalogo)
        # build_dataset_inventory necesita más superficie que catalog_merge.
        ds.red_path = tmp_path / 'r.txt'
        ds.loads_path = tmp_path / 'c.txt'
        ds.equipment_path = tmp_path / 'e.txt'
        ds.nodes = {}
        ds.sources = {}
        ds.sections = {}
        ds.feeders = {}
        ds.customer_loads = {}
        ds.load_placements = {}
        ds.switch_settings = []
        ds.sectionalizer_settings = []
        ds.intermediate_nodes = []
        ds.headnodes = {}
        ds.section_owner = {}
        ds.feeder_ids = lambda: []
        ds.feeder_section_ids = lambda _n: []
        ds.resolve_feeder = lambda _n: None
        return build_dataset_inventory(ds, aliases=aliases)

    def test_faltar_casi_todo_es_ERROR(self, tmp_path):
        inv = self._inventario(['A', 'B', 'C', 'D'], [('A', 1.0)], tmp_path)
        fallo = next(i for i in inv['integrity']['issues']
                     if i['code'] == 'line_types_missing_from_bd_equipo')
        assert fallo['severity'] == 'error'
        assert 'NO corresponde' in fallo['message']

    def test_faltar_poco_sigue_siendo_aviso(self, tmp_path):
        inv = self._inventario(
            ['A', 'B', 'C', 'D'], [('A', 1.0), ('B', 2.0), ('C', 3.0)], tmp_path)
        fallo = next(i for i in inv['integrity']['issues']
                     if i['code'] == 'line_types_missing_from_bd_equipo')
        assert fallo['severity'] == 'warning'
        assert fallo['coverage'] == pytest.approx(0.75)

    def test_alias_explicito_no_genera_incidencia(self, tmp_path):
        inv = self._inventario(
            ['AUSENTE'], [('EXISTENTE', 1.0)], tmp_path,
            aliases={'AUSENTE': 'EXISTENTE'},
        )
        assert not any(
            issue['code'] == 'line_types_missing_from_bd_equipo'
            for issue in inv['integrity']['issues']
        )


class TestEntregaReal:
    def test_el_catalogo_de_referencia_cubre_la_red_del_export(self, ds):
        """Sobre el export cargado: la cobertura debe ser alta."""
        informe = cm.diagnosticar(ds)
        if not informe.codigos_en_red:
            pytest.skip('el export cargado no declara tipos de línea')
        assert informe.cobertura_final > 0.8, (
            f'solo el {informe.cobertura_final * 100:.0f} % de los tipos tiene '
            f'catálogo: faltan {sorted(informe.sin_resolver)[:10]}'
        )
