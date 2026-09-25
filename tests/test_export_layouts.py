"""Las dos disposiciones de export de CYMDIST tienen que dar el mismo modelo.

El conversor se había afinado contra un export concreto. Cuando llegó el otro —el largo,
de 21 MB, con las mismas 96 alimentadores— el resultado medido fue:

* **0 tramos leídos de 38.657**, y *sin una sola excepción*: 96 alimentadores vacíos.
  El motivo es que ese export declara ``FORMAT_SECTION`` una sola vez, **antes** del
  primer ``FEEDER=``, y el lector descartaba las columnas al llegar la cabecera.
* el conductor de cada tramo no viene en ``[LINE CONFIGURATION]`` sino partido en
  ``[OVERHEADLINE SETTING]`` y ``[UNDERGROUNDLINE SETTING]``;
* el catálogo de cables se llama ``[CABLE]``, no ``[CONCENTRIC NEUTRAL CABLE]``, así que
  los 8.729 tramos subterráneos habrían caído a ``DEFAULT``;
* la tensión de fuente viene entre **fase y neutro** (``5.773503`` para 10 kV), y
  tomarla sin multiplicar por √3 habría construido la red entera a 5,77 kV —
  convergiendo, que es lo peligroso;
* las cargas se declaran en el **punto medio** del tramo (``Location='2'``).

De los cinco, tres son de la clase que no falla: producen un modelo que se importa en
PowerFactory y converge dando números creíbles y equivocados. De ahí que esto se pruebe
sobre las dos disposiciones y no sobre una.
"""

from __future__ import annotations

import math

import pytest

from igea_dgs.dataset import CymdistDataset
from igea_dgs.model import (LARGO_MAXIMO_CARGA_CENTRAL_M, Line, ModelBuildError,
                            _load_node, build_feeder_model)
from synthetic_export import ExportSpec, load_export, write_export

LAYOUTS = ('reducido', 'completo')


def _spec(layout: str, **kw) -> ExportSpec:
    return ExportSpec(feeders=3, sections_per_feeder=4, loads_per_feeder=2,
                      layout=layout, **kw)


class TestLaLecturaEsEquivalente:
    """Lo que el lector saca de un export no debe depender de su disposición."""

    @pytest.mark.parametrize('layout', LAYOUTS)
    def test_se_leen_todos_los_tramos(self, tmp_path, layout):
        ds = load_export(_spec(layout), tmp_path / layout)
        de_red = {f'SEC_{f}_{s}' for f in (1, 2, 3) for s in range(4)}
        assert de_red <= set(ds.sections), (
            'la disposición completa perdía los 12 tramos en silencio, porque su '
            'FORMAT_SECTION va antes del primer FEEDER= y el lector lo descartaba al '
            f'llegar la cabecera. Faltan: {sorted(de_red - set(ds.sections))}')
        assert len(ds.line_configurations) == len(ds.sections), (
            'todo tramo leído tiene que traer su conductor, venga de [LINE '
            'CONFIGURATION] o de las tablas de ajuste')

    @pytest.mark.parametrize('layout', LAYOUTS)
    def test_se_leen_todos_los_alimentadores(self, tmp_path, layout):
        ds = load_export(_spec(layout), tmp_path / layout)
        assert len(ds.feeder_ids()) == 3
        for nid in ds.feeder_ids():
            assert ds.feeder_section_ids(nid), f'{nid} se quedó sin tramos'

    def test_las_dos_dan_la_misma_topologia(self, tmp_path):
        a = load_export(_spec('reducido'), tmp_path / 'a')
        b = load_export(_spec('completo'), tmp_path / 'b')
        # La completa añade además una derivación de 0,3 m por carga, que la reducida
        # no modela: se compara la red que las dos describen.
        assert set(a.sections) <= set(b.sections)
        assert set(a.nodes) <= set(b.nodes)
        for sid in a.sections:
            ca, cb = a.line_configurations[sid], b.line_configurations[sid]
            assert ca['LineCableID'] == cb['LineCableID'], sid
            assert ca['Overhead'] == cb['Overhead'], f'{sid}: aérea/subterránea'
            assert float(ca['Length']) == pytest.approx(float(cb['Length'])), sid


class TestLaTensionDeFuente:
    """Fase-neutro y entre fases se parecen lo bastante para pasar desapercibidas."""

    @pytest.mark.parametrize('layout', LAYOUTS)
    def test_sale_entre_fases(self, tmp_path, layout):
        ds = load_export(_spec(layout, nominal_kv=10.0), tmp_path / layout)
        for nid in ds.feeder_ids():
            m = build_feeder_model(ds, nid, strict=True)
            assert m.nominal_kv == pytest.approx(10.0, abs=1e-6), (
                'el export completo la da como 10/√3 = 5,773503; sin multiplicar, la red '
                'entera se construye a 5,77 kV y converge igual')

    def test_una_fuente_sin_tension_falla_diciendo_donde_miro(self, tmp_path):
        red, carga, equipo = write_export(
            _spec('completo', nominal_kv=10.0), tmp_path / 'x')
        fase_neutro = f'{10.0 / math.sqrt(3.0):.6f}'
        texto = red.read_text(encoding='utf-8')
        assert fase_neutro in texto
        red.write_text(texto.replace(fase_neutro, ''), encoding='utf-8')
        ds = CymdistDataset.from_files(red, carga, equipo)
        with pytest.raises(ModelBuildError) as exc:
            build_feeder_model(ds, ds.feeder_ids()[0], strict=True)
        assert 'DesiredVoltage' in str(exc.value)
        assert 'OperatingVoltage' in str(exc.value)


class TestElCatalogoDeCables:
    """``[CABLE]`` y ``[CONCENTRIC NEUTRAL CABLE]`` son la misma cosa."""

    @pytest.mark.parametrize('layout', LAYOUTS)
    def test_ningun_tramo_subterraneo_cae_a_otro_tipo(self, tmp_path, layout):
        ds = load_export(_spec(layout), tmp_path / layout)
        subterraneos = 0
        for nid in ds.feeder_ids():
            m = build_feeder_model(ds, nid, strict=True)
            for ln in m.lines:
                cfg = ds.line_configurations[ln.section_id]
                if cfg['Overhead'] == '0':
                    subterraneos += 1
                    typ = m.line_types[ln.type_key]
                    assert typ.source_table in ('CABLE', 'CONCENTRIC NEUTRAL CABLE'), (
                        f'{ln.section_id} es subterráneo y tomó el tipo de '
                        f'[{typ.source_table}]')
                    assert typ.r1_ohm_km == pytest.approx(0.25), (
                        'debe tomar la R del cable, no la de la línea aérea')
        assert subterraneos > 0, 'la prueba no ejercitó ningún tramo subterráneo'

    def test_la_lista_de_tablas_es_una_sola(self):
        """Cada módulo llevaba su propia copia, y se desincronizaron."""
        from igea_dgs import catalog_merge
        from igea_dgs.dataset import TABLAS_TIPOS_LINEA

        assert catalog_merge.TABLAS_DE_TIPOS == TABLAS_TIPOS_LINEA
        assert 'CABLE' in TABLAS_TIPOS_LINEA


class TestLaCargaEnElPuntoMedio:
    """``Location='2'``: PowerFactory no tiene nudo a mitad de línea."""

    @pytest.mark.parametrize('layout', LAYOUTS)
    def test_las_cargas_se_conectan(self, tmp_path, layout):
        ds = load_export(_spec(layout), tmp_path / layout)
        total = 0
        for nid in ds.feeder_ids():
            m = build_feeder_model(ds, nid, strict=True)
            total += len(m.loads)
            conocidos = {getattr(n, 'node_id', n) for n in m.nodes}
            for load in m.loads:
                assert load.node_id in conocidos, (
                    f'{load.node_id} no es un nudo del modelo')
        assert total == 6, f'se esperaban 6 cargas y hay {total}'

    def _tramo(self, metros: float) -> Line:
        return Line(
            section_id='SEC_X', from_node='A', to_node='B', phase='ABC',
            type_key='LINE:DEFAULT', source_type_code='DEFAULT',
            length_m=metros, overhead=True, txt_length_m=metros, length_source='txt')

    def test_en_una_derivacion_corta_se_cuelga_del_extremo(self):
        assert _load_node('2', self._tramo(0.3), strict=True) == 'B'
        assert _load_node('2', self._tramo(LARGO_MAXIMO_CARGA_CENTRAL_M),
                          strict=True) == 'B'

    def test_en_un_tramo_largo_se_niega_en_vez_de_falsear(self):
        """Colgar del extremo la carga de un tramo largo falsearía la caída."""
        largo = LARGO_MAXIMO_CARGA_CENTRAL_M * 100
        with pytest.raises(ModelBuildError) as exc:
            _load_node('2', self._tramo(largo), strict=True)
        assert 'punto medio' in str(exc.value)
        assert f'{largo:.1f} m' in str(exc.value)

    def test_en_no_estricto_se_acepta_y_no_se_pierde_la_carga(self):
        largo = LARGO_MAXIMO_CARGA_CENTRAL_M * 100
        assert _load_node('2', self._tramo(largo), strict=False) == 'B'


class TestElContratoDelConductorPorTramo:
    """Un tramo, un conductor. Lo diga la tabla que lo diga."""

    def test_dos_conductores_para_el_mismo_tramo_es_error(self, tmp_path):
        red, carga, equipo = write_export(_spec('completo'), tmp_path / 'x')
        lineas = red.read_text(encoding='utf-8').splitlines()
        # Repetir en la tabla subterránea un tramo que ya declaró la aérea, con otro
        # conductor: es un dato imposible y debe decirse, no elegirse uno.
        i = lineas.index('[UNDERGROUNDLINE SETTING]')
        lineas.insert(i + 2, 'SEC_1_0,SEC_1_0,,0,0,AA05001D,40.0')
        red.write_text('\n'.join(lineas) + '\n', encoding='utf-8')
        with pytest.raises(ValueError, match='dos conductores distintos'):
            CymdistDataset.from_files(red, carga, equipo)

    def test_una_tabla_explicita_manda_sobre_los_ajustes(self, tmp_path):
        """Si el export trae las dos cosas, [LINE CONFIGURATION] es la explícita."""
        red, carga, equipo = write_export(_spec('completo'), tmp_path / 'x')
        texto = red.read_text(encoding='utf-8')
        texto += ('[LINE CONFIGURATION]\n'
                  'FORMAT_LINECONFIGURATION=SectionID,LineCableID,Length,Overhead\n'
                  'SEC_1_0,AA05001D,999.0,1\n')
        red.write_text(texto, encoding='utf-8')
        ds = CymdistDataset.from_files(red, carga, equipo)
        assert ds.line_configurations['SEC_1_0']['LineCableID'] == 'AA05001D'
        assert float(ds.line_configurations['SEC_1_0']['Length']) == pytest.approx(999.0)
        # Y los demás siguen viniendo de las tablas de ajuste.
        assert ds.line_configurations['SEC_1_1']['LineCableID'] == 'DEFAULT'


class TestLaConversionCompletaFuncionaConLasDos:
    @pytest.mark.parametrize('layout', LAYOUTS)
    def test_se_escribe_un_dgs_por_alimentador(self, tmp_path, layout):
        from igea_dgs.batch import convert_selection

        ds = load_export(_spec(layout), tmp_path / layout)
        salida = tmp_path / f'out_{layout}'
        manifest = convert_selection(
            ds, None, str(salida), all_feeders=True, aliases={}, strict=True,
            include_geography=True, source_crs='EPSG:32718', target_crs='EPSG:4326')
        assert manifest['summary']['failed'] == 0, manifest['summary']
        assert manifest['summary']['ok'] == 3
        assert len(list(salida.glob('*.dgs'))) == 3

    def test_los_dos_dgs_describen_la_misma_red(self, tmp_path):
        """La prueba de fuego: mismos nudos, mismas líneas, misma longitud."""
        modelos = {}
        for layout in LAYOUTS:
            ds = load_export(_spec(layout, nominal_kv=10.0), tmp_path / layout)
            nid = ds.feeder_ids()[0]
            modelos[layout] = build_feeder_model(ds, nid, strict=True)
        a, b = modelos['reducido'], modelos['completo']
        nudos_b = {getattr(n, 'node_id', n) for n in b.nodes}
        assert {getattr(n, 'node_id', n) for n in a.nodes} <= nudos_b
        largo_b = {l.section_id: l.length_km for l in b.lines}
        assert {l.section_id for l in a.lines} <= set(largo_b)
        # La red, tramo a tramo, tiene que salir idéntica.
        for ln in a.lines:
            assert ln.length_km == pytest.approx(largo_b[ln.section_id]), ln.section_id
        assert sum(l.p_mw for l in a.loads) == pytest.approx(
            sum(l.p_mw for l in b.loads)), 'la demanda no puede cambiar de disposición'
        assert a.nominal_kv == pytest.approx(b.nominal_kv)


class TestLaEntregaRealLarga:
    """Sobre el export de 21 MB de la distribuidora, si está a mano."""

    @pytest.fixture
    def entrega(self):
        from pathlib import Path
        base = Path('D:/BaseDatosElectroDunas/260919BaseDatos/exportarTXT')
        trio = (base / '260922Red.txt', base / '260922Cargas.txt',
                base / '260922Equipos.txt')
        if not all(p.is_file() for p in trio):
            pytest.skip('la entrega larga no está en esta máquina')
        return CymdistDataset.from_files(*trio)

    def test_se_leen_los_tramos(self, entrega):
        assert len(entrega.sections) > 38000
        assert len(entrega.line_configurations) == len(entrega.sections), (
            'todo tramo del export largo trae conductor en las tablas de ajuste')

    def test_el_catalogo_cubre_el_cien_por_cien(self, entrega):
        from igea_dgs import catalog_merge

        informe = catalog_merge.diagnosticar(entrega)
        assert informe.cobertura_final == pytest.approx(1.0), (
            f'sin resolver: {sorted(informe.sin_resolver)}')

    def test_las_tensiones_son_las_reales_de_la_zona(self, entrega):
        tensiones = set()
        for nid in entrega.feeder_ids():
            try:
                tensiones.add(round(build_feeder_model(entrega, nid, strict=False).nominal_kv, 1))
            except ModelBuildError:
                continue
        assert tensiones <= {10.0, 22.9}, tensiones
        assert 10.0 in tensiones and 22.9 in tensiones

    def test_la_gran_mayoria_de_alimentadores_se_construye(self, entrega):
        ok = 0
        for nid in entrega.feeder_ids():
            try:
                build_feeder_model(entrega, nid, strict=True)
                ok += 1
            except ModelBuildError:
                pass
        total = len(entrega.feeder_ids())
        assert ok >= total * 0.9, (
            f'solo {ok} de {total}; antes de reconocer esta disposición eran 0 tramos '
            f'en los {total}, sin un solo error')
