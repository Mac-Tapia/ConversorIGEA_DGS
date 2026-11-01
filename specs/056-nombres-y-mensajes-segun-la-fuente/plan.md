# Plan — Spec 056

1. Fuente en el dataset y en el modelo (todas las RF): `CymdistDataset.fuente` («TXT» por
   defecto, «MDB» desde `access.py`, «VNR-GIS» desde el puente de `vnr_etl`), copiada a
   `FeederModel.fuente` en `build_feeder_model`. Un TXT y una .mdb son de CYMDIST: sus textos
   y su DGS quedan como estaban, byte a byte.
2. Textos (RF-3, RF-4): una sola función, `palabras_de(fuente)`, da cómo se nombra cada cosa
   en esa fuente (su longitud, su fichero, sus bancos y reguladores); `model.py`, `validate.py`,
   `geography.py`, `inventory.py` y la cabecera de `dgs.py` la usan en lugar de «TXT»,
   «CYMDIST», «BD_Equipo» o «RED export» fijos.
3. Proyecto (RF-1, RF-2): `tools/powerfactory_acceptance.py` lee la fuente de la cabecera del
   DGS y la pone en el nombre (`<sello>_CSG_<fuente>_<red>`, con la sigla de la spec 058);
   nada reconoce los proyectos por ese nombre, así que los antiguos siguen valiendo (028:RF-7).
4. Prueba (RF-6): un VNR-GIS sintético convertido de punta a punta; ninguna salida dice
   «TXT», «CYMDIST», «BD_Equipo» ni «RED export».
