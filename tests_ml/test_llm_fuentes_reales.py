"""047:RF-20: aceptación de procedencia con el corpus local real, sin sustituirlo por fixtures.

CSG_LLM_CORPUS permite señalar otra preparación sellada. La ausencia falla, no omite.
No carga un LLM ni acredita entrenamiento, inferencia o aceptación eléctrica.
"""
import os
from pathlib import Path


def test_entidades_del_corpus_contrastan_con_referencia_real():
    """047:RF-20: comprobar valores y huellas reales, humanas reservadas y ninguna operación ficticia."""
    from convertersmartgrid.asistente.llm_destilacion import auditar_fuentes_corpus
    defecto=Path(__file__).resolve().parents[1]/'output/alumno_llm_referencias_20261101/corpus_sellado_v4'
    corpus=Path(os.environ.get('CSG_LLM_CORPUS') or defecto)
    assert corpus.is_dir(),'Prepare y selle primero el corpus real con tools/llm_destilar.py'
    r=auditar_fuentes_corpus(corpus)
    assert r['ok'] and r['contextos_reales']>0 and r['archivos_fuente_verificados']>0
    assert r['por_particion']['prueba']>=200
    assert all(r['entidades_contrastadas'][tipo]>0 for tipo in ('alimentadores','sed','proyecto','periodo','sistema','ruta'))
    assert r['observaciones_humanas_en_train']==r['resultados_electricos']==r['escrituras_nativas']==0
