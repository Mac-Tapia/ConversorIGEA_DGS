"""Unión de todos los alimentadores en una sola red.

Las tres reglas que estas pruebas fijan, por orden de gravedad si se rompen:

1. **Nunca se fusionan dos tensiones.** Un nodo con el mismo identificador a 10 kV y a
   22,9 kV son dos nodos. Fusionarlos pondría un cortocircuito franco entre niveles y
   el flujo de potencia daría cualquier cosa sin avisar.
2. **Las áreas sin fuente salen de servicio, no se borran.** PowerFactory resuelve
   todas las áreas aisladas en un mismo sistema de Newton; un área sin referencia de
   tensión estanca el solver de toda la red. Medido: con 13 alimentadores «Newton
   algorithm stagnated → No convergence». Pero los elementos siguen en el modelo,
   porque se pidió que todo se dibuje.
3. **La identidad de cada alimentador sobrevive a la unión.** Una fuente y un
   ``ElmFeeder`` por alimentador; si se pierden, deja de poder distinguirse quién
   alimenta qué dentro de la red común.
"""

from __future__ import annotations

import pytest

from igea_dgs.combine import (
    CombinedInfo,
    combine_models,
    type_key_for,
    unsupplied_nodes,
)
from igea_dgs.model import FeederModel, Line, LineType, Load, Node, Sed


def _tipo(code: str = 'AA12003D', tabla: str = 'LINE') -> LineType:
    return LineType(f'{tabla}:{code}', code, tabla, 0.28, 0.7, 0.43, 1.3, 3.7, 3.7, 340.0)


def _alimentador(
    nombre: str, kv: float, nodos: list[str], *, fuente: str | None = None,
    con_carga: str | None = None, sueltos: tuple[str, str] | None = None,
) -> FeederModel:
    """Cadena de nodos; ``sueltos`` añade un tramo desconectado de la fuente."""
    tipo = _tipo()
    todos = list(nodos) + (list(sueltos) if sueltos else [])
    nodes = {n: Node(n, float(i) * 100.0, 0.0) for i, n in enumerate(todos)}
    lines = [
        Line(f'{nombre}_SEC{i}', a, b, 'ABC', tipo.key, tipo.code, 100.0, True)
        for i, (a, b) in enumerate(zip(nodos, nodos[1:]))
    ]
    if sueltos:
        lines.append(Line(f'{nombre}_ISLA', sueltos[0], sueltos[1], 'ABC',
                          tipo.key, tipo.code, 100.0, True))
    loads, seds = [], []
    if con_carga:
        loads.append(Load(f'{nombre}_SECL', 'D1', 'C', '1', con_carga, 0.05, 0.01,
                          0.95, 50.0, 0.0, 'ABC', sed_code=f'SE_{nombre}',
                          display_name=f'SE_{nombre}'))
        seds.append(Sed(f'SE_{nombre}', f'SE_{nombre}', con_carga, 100.0,
                        f'{nombre}_SECL', 'D1', (f'{nombre}_SECL', 'D1')))
    return FeederModel(
        name=nombre, network_id=f'NET_{nombre}', nominal_kv=kv,
        source_node=fuente or nodos[0], nodes=nodes, lines=lines, loads=loads,
        devices=[], line_types={tipo.key: tipo}, seds=seds,
    )


class TestNoSeFusionanTensiones:
    """Lo más grave que podría hacer mal esta función."""

    def test_un_nodo_a_dos_tensiones_se_separa(self):
        a = _alimentador('A', 10.0, ['N1', 'COMPARTIDO'])
        b = _alimentador('B', 22.9, ['N9', 'COMPARTIDO'])
        modelo, informe = combine_models([a, b])
        assert informe.voltage_conflicts == 1
        assert 'COMPARTIDO' not in modelo.nodes, 'no debe quedar el nombre ambiguo'
        separados = [n for n in modelo.nodes if n.startswith('COMPARTIDO')]
        assert len(separados) == 2, separados

    def test_cada_separado_conserva_su_tension(self):
        a = _alimentador('A', 10.0, ['N1', 'COMPARTIDO'])
        b = _alimentador('B', 22.9, ['N9', 'COMPARTIDO'])
        modelo, _ = combine_models([a, b])
        info: CombinedInfo = modelo.combined
        tensiones = {info.node_kv[n] for n in modelo.nodes if n.startswith('COMPARTIDO')}
        assert tensiones == {10.0, 22.9}

    def test_el_aviso_explica_por_que_no_se_fusiona(self):
        a = _alimentador('A', 10.0, ['N1', 'X'])
        b = _alimentador('B', 22.9, ['N9', 'X'])
        _modelo, informe = combine_models([a, b])
        aviso = next(w for w in informe.warnings if 'X' in w)
        assert 'cortocircuito' in aviso
        assert '10 kV' in aviso and '22.9 kV' in aviso

    def test_un_nodo_compartido_a_la_MISMA_tension_si_se_fusiona(self):
        """Ese es el punto de enlace, y es justo lo que la unión aporta."""
        a = _alimentador('A', 10.0, ['N1', 'ENLACE'])
        b = _alimentador('B', 10.0, ['N9', 'ENLACE'])
        modelo, informe = combine_models([a, b])
        assert 'ENLACE' in modelo.nodes
        assert informe.tie_nodes == 1
        assert modelo.combined.tie_nodes['ENLACE'] == ['A', 'B']


class TestAreasSinFuente:
    def test_lo_no_alcanzable_se_marca_fuera_de_servicio(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        modelo, informe = combine_models([a])
        assert modelo.combined.de_energised == {'S1', 'S2'}
        assert informe.de_energised_nodes == 2
        assert informe.de_energised_lines == 1

    def test_no_se_borra_nada(self):
        """Se pidió que todo se dibuje: fuera de servicio no es borrado."""
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        modelo, _ = combine_models([a])
        assert {'S1', 'S2'} <= set(modelo.nodes)
        assert any(l.section_id == 'A_ISLA' for l in modelo.lines)

    def test_se_puede_desactivar(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        modelo, informe = combine_models([a], de_energise_islands=False)
        assert modelo.combined.de_energised == set()
        assert informe.de_energised_nodes == 0

    def test_la_busqueda_parte_de_TODAS_las_fuentes(self):
        """Con una sola fuente, 95 alimentadores parecerían islas."""
        a = _alimentador('A', 10.0, ['A1', 'A2'])
        b = _alimentador('B', 10.0, ['B1', 'B2'])
        modelo, informe = combine_models([a, b])
        assert informe.de_energised_nodes == 0, 'ningún alimentador está aislado'
        assert unsupplied_nodes(modelo, ['A1']) == {'B1', 'B2'}, (
            'partiendo de una sola fuente, el otro alimentador sí sale aislado'
        )

    def test_el_aviso_cita_el_manual_y_dice_que_no_se_borra(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        _modelo, informe = combine_models([a])
        aviso = next(w for w in informe.warnings if 'fuera de servicio' in w.lower()
                     or 'FUERA DE SERVICIO' in w)
        assert '24.6.3' in aviso
        assert 'dibuj' in aviso

    def test_cuenta_la_potencia_atrapada(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        # Una carga colgada del tramo suelto.
        a.loads.append(Load('A_SECI', 'D9', 'C', '1', 'S2', 0.02, 0.005, 0.95,
                            20.0, 0.0, 'ABC'))
        _modelo, informe = combine_models([a])
        assert informe.de_energised_loads == 1
        assert informe.de_energised_kw == pytest.approx(20.0)


class TestTiposPorTension:
    def test_el_mismo_conductor_a_dos_tensiones_da_dos_tipos(self):
        """TypLne lleva uline, así que son dos tipos distintos en PowerFactory."""
        a = _alimentador('A', 10.0, ['N1', 'N2'])
        b = _alimentador('B', 22.9, ['M1', 'M2'])
        modelo, informe = combine_models([a, b])
        assert informe.line_types_in == 1
        assert informe.line_types_out == 2
        assert set(modelo.combined.type_kv.values()) == {10.0, 22.9}

    def test_cada_tramo_apunta_a_un_tipo_que_existe(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'])
        b = _alimentador('B', 22.9, ['M1', 'M2'])
        modelo, _ = combine_models([a, b])
        for linea in modelo.lines:
            assert linea.type_key in modelo.line_types, linea.section_id

    def test_la_clave_conserva_el_prefijo_que_distingue_aereo_de_cable(self):
        """El escritor usa LINE:/CABLE: para cohl_; perderlo cambiaría el tipo."""
        assert type_key_for('LINE:AA12003D', 22.9).startswith('LINE:')
        assert type_key_for('CABLE:N212003D', 10.0).startswith('CABLE:')

    def test_el_tipo_conserva_su_codigo_original(self):
        a = _alimentador('A', 10.0, ['N1', 'N2'])
        modelo, _ = combine_models([a])
        assert {t.code for t in modelo.line_types.values()} == {'AA12003D'}


class TestIdentidadDeCadaAlimentador:
    def test_hay_una_fuente_por_alimentador(self):
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', f'{i}b']) for i in range(5)]
        modelo, _ = combine_models(modelos)
        assert len(modelo.combined.feeders) == 5
        assert {f.name for f in modelo.combined.feeders} == {f'F{i}' for i in range(5)}

    def test_la_fuente_apunta_a_un_nodo_que_existe(self):
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', f'{i}b']) for i in range(4)]
        modelo, _ = combine_models(modelos)
        for ref in modelo.combined.feeders:
            assert ref.source_node in modelo.nodes, ref.name

    def test_la_fuente_sigue_al_nodo_renombrado_por_conflicto(self):
        a = _alimentador('A', 10.0, ['CHOQUE', 'N2'])
        b = _alimentador('B', 22.9, ['CHOQUE', 'M2'])
        modelo, _ = combine_models([a, b])
        for ref in modelo.combined.feeders:
            assert ref.source_node in modelo.nodes, ref.name

    def test_no_se_pierde_ni_se_duplica_ningun_tramo(self):
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', f'{i}b', f'{i}c'])
                   for i in range(6)]
        modelo, informe = combine_models(modelos)
        ids = [l.section_id for l in modelo.lines]
        assert len(ids) == len(set(ids)), 'tramos duplicados'
        assert informe.lines == sum(len(m.lines) for m in modelos)

    def test_un_nodo_sin_coordenadas_toma_las_del_otro_alimentador(self):
        a = _alimentador('A', 10.0, ['N1', 'ENLACE'])
        b = _alimentador('B', 10.0, ['M1', 'ENLACE'])
        a.nodes['ENLACE'] = Node('ENLACE', None, None)
        modelo, _ = combine_models([a, b])
        assert modelo.nodes['ENLACE'].x is not None


class TestEscrituraDelDgs:
    def _escribir(self, modelos, tmp_path):
        from igea_dgs.dgs import write_dgs

        modelo, informe = combine_models(modelos)
        destino = tmp_path / 'sistema.dgs'
        write_dgs(modelo, destino)
        return modelo, informe, destino.read_text(encoding='latin-1')

    def _filas(self, texto: str, tabla: str) -> list[tuple[list[str], list[str]]]:
        """Filas de una tabla del DGS, con su cabecera ya alineada.

        La cabecera empieza por ``$$ElmTerm;FID;...`` y las filas por ``FID;...``, así
        que los índices están desplazados en uno. Alinearlos aquí evita leer la columna
        de al lado y creerse el resultado.
        """
        filas: list[tuple[list[str], list[str]]] = []
        actual, cab = None, []
        for linea in texto.splitlines():
            if linea.startswith('$$'):
                actual = linea[2:].split(';')[0]
                cab = [c.strip() for c in linea.split(';')][1:]
            elif actual == tabla and linea.strip():
                filas.append(([c.strip() for c in linea.split(';')], cab))
        return filas

    def test_una_sola_red(self, tmp_path):
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', f'{i}b']) for i in range(4)]
        _m, _i, texto = self._escribir(modelos, tmp_path)
        assert len(self._filas(texto, 'ElmNet')) == 1, 'debe ser UNA sola grid'

    def test_una_fuente_y_un_elmfeeder_por_alimentador(self, tmp_path):
        modelos = [_alimentador(f'F{i}', 10.0, [f'{i}a', f'{i}b']) for i in range(4)]
        _m, _i, texto = self._escribir(modelos, tmp_path)
        assert len(self._filas(texto, 'ElmXnet')) == 4
        assert len(self._filas(texto, 'ElmFeeder')) == 4

    def test_cada_nodo_lleva_SU_tension(self, tmp_path):
        a = _alimentador('A', 10.0, ['N1', 'N2'])
        b = _alimentador('B', 22.9, ['M1', 'M2'])
        _m, _i, texto = self._escribir([a, b], tmp_path)
        tensiones = {}
        for campos, cab in self._filas(texto, 'ElmTerm'):
            i_n, i_u = cab.index('loc_name(a:40)'), cab.index('uknom(r)')
            tensiones[campos[i_n]] = float(campos[i_u])
        assert tensiones['N1'] == pytest.approx(10.0)
        assert tensiones['M1'] == pytest.approx(22.9)

    def test_los_nodos_sin_fuente_salen_fuera_de_servicio(self, tmp_path):
        a = _alimentador('A', 10.0, ['N1', 'N2'], sueltos=('S1', 'S2'))
        _m, _i, texto = self._escribir([a], tmp_path)
        estado = {}
        for campos, cab in self._filas(texto, 'ElmTerm'):
            i_n, i_o = cab.index('loc_name(a:40)'), cab.index('outserv(i)')
            estado[campos[i_n]] = campos[i_o]
        assert estado['S1'] == '1' and estado['S2'] == '1'
        assert estado['N1'] == '0' and estado['N2'] == '0'

    def test_los_tipos_por_tension_tienen_nombres_distintos(self, tmp_path):
        a = _alimentador('A', 10.0, ['N1', 'N2'])
        b = _alimentador('B', 22.9, ['M1', 'M2'])
        _m, _i, texto = self._escribir([a, b], tmp_path)
        nombres = []
        for campos, cab in self._filas(texto, 'TypLne'):
            nombres.append(campos[cab.index('loc_name(a:40)')])
        assert len(nombres) == len(set(nombres)), f'nombres repetidos: {nombres}'
        assert len(nombres) == 2

    def test_un_solo_alimentador_escribe_igual_que_antes(self, tmp_path):
        """La unión no debe cambiar el DGS de un alimentador suelto."""
        from igea_dgs.dgs import write_dgs

        suelto = _alimentador('A', 10.0, ['N1', 'N2'], con_carga='N2')
        directo = tmp_path / 'directo.dgs'
        write_dgs(suelto, directo)
        filas_directo = self._filas(directo.read_text(encoding='latin-1'), 'ElmTerm')

        combinado, _ = combine_models([_alimentador('A', 10.0, ['N1', 'N2'],
                                                    con_carga='N2')])
        unido = tmp_path / 'unido.dgs'
        write_dgs(combinado, unido)
        filas_unido = self._filas(unido.read_text(encoding='latin-1'), 'ElmTerm')
        assert len(filas_directo) == len(filas_unido)


class TestExportReal:
    def test_los_96_alimentadores_se_unen(self, ds):
        from igea_dgs.combine import build_combined

        modelo, informe = build_combined(ds, include_geography=False)
        assert informe.feeders > 1
        assert informe.nodes_out <= informe.nodes_in
        # Cada tramo apunta a un tipo y a nodos que existen: si esto falla, el DGS
        # sale con referencias colgando y PowerFactory lo rechaza en la importación.
        for linea in modelo.lines:
            assert linea.type_key in modelo.line_types
            assert linea.from_node in modelo.nodes
            assert linea.to_node in modelo.nodes
        for ref in modelo.combined.feeders:
            assert ref.source_node in modelo.nodes

    def test_ninguna_carga_activa_queda_sin_camino_a_una_fuente(self, ds):
        """Lo que hacía estancar el Newton de toda la red."""
        from igea_dgs.combine import build_combined

        modelo, _ = build_combined(ds, include_geography=False)
        apagados = modelo.combined.de_energised
        vivas = [c for c in modelo.loads if c.node_id not in apagados]
        sin_camino = unsupplied_nodes(modelo, (f.source_node for f in modelo.combined.feeders))
        assert not [c for c in vivas if c.node_id in sin_camino]
