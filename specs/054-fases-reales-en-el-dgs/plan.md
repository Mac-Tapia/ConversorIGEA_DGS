# Plan — Spec 054

1. Modelo: fases por tramo y por SED desde la fuente (VNR-GIS: cifras de fases de la norma y
   fase del tramo; TXT/MDB: fase de la sección), con «ABC» cuando no se sabe (RF-5).
2. `dgs.py`: tipo de línea por conductor y fases (`nlnph`, `nneutral`); `phtech` de cada barra
   por el elemento de más fases; `nphase` e `it2p1..3` de cada cubículo; trafo monofásico
   (`nt2ph` = 1) y carga monofásica en las SED monofásicas. Sin fases distintas de ABC, el DGS
   igual que antes (RF-6).
3. Sonda de DIgSILENT en NJA202: flujo con `iopt_net` 0 y 1; tensión mínima, pérdidas y
   cabecera en el informe (RF-7).
