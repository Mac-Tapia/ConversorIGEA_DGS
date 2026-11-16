/**
 * Un paquete VNR-GIS sintético para F01: dos alimentadores de una empresa y un año inventados, con su capa de
 * tramos de media tensión en GeoJSON (lon/lat), comprimido en un .zip sin dependencias (método «store»).
 * Ningún código, nombre ni coordenada es de una empresa real.
 */
import { writeFileSync } from 'node:fs';
import { crc32 } from 'node:zlib';

export const EMPRESA = 'EMPX';
export const ANIO = 2025;
export const ALIMENTADORES = ['SINT01', 'SINT02'];

function tramo(codigo, alimentador, x) {
  return {
    type: 'Feature',
    properties: { CODEMP: EMPRESA, ANIO, CODTRAMOMT: codigo, CODSALIDAMT: alimentador, CODNORMA: 'AA120', LONGITUD: 100.0 },
    geometry: { type: 'LineString', coordinates: [[x, -14.0], [x + 0.001, -14.0]] },
  };
}

export function capaTramos() {
  return {
    type: 'FeatureCollection',
    features: ALIMENTADORES.flatMap((a, i) => [tramo(`${a}-T1`, a, -75 + i * 0.01), tramo(`${a}-T2`, a, -75.001 + i * 0.01)]),
  };
}

/** Un .zip «store» (sin comprimir) con los ficheros dados; basta para que lo lea cualquier lector de zip. */
export function zip(ficheros) {
  const locales = [];
  const centrales = [];
  let desplazamiento = 0;
  for (const [nombre, contenido] of Object.entries(ficheros)) {
    const n = Buffer.from(nombre, 'utf8');
    const datos = Buffer.from(contenido, 'utf8');
    const crc = crc32(datos) >>> 0;
    const cabecera = Buffer.alloc(30);
    cabecera.writeUInt32LE(0x04034b50, 0); cabecera.writeUInt16LE(20, 4); cabecera.writeUInt16LE(0x0800, 6);
    cabecera.writeUInt16LE(0, 8); cabecera.writeUInt32LE(0, 10); cabecera.writeUInt32LE(crc, 14);
    cabecera.writeUInt32LE(datos.length, 18); cabecera.writeUInt32LE(datos.length, 22);
    cabecera.writeUInt16LE(n.length, 26); cabecera.writeUInt16LE(0, 28);
    locales.push(cabecera, n, datos);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0x0800, 8); central.writeUInt16LE(0, 10); central.writeUInt32LE(0, 12);
    central.writeUInt32LE(crc, 16); central.writeUInt32LE(datos.length, 20); central.writeUInt32LE(datos.length, 24);
    central.writeUInt16LE(n.length, 28); central.writeUInt16LE(0, 30); central.writeUInt16LE(0, 32);
    central.writeUInt16LE(0, 34); central.writeUInt16LE(0, 36); central.writeUInt32LE(0, 38);
    central.writeUInt32LE(desplazamiento, 42);
    centrales.push(central, n);
    desplazamiento += 30 + n.length + datos.length;
  }
  const directorio = Buffer.concat(centrales);
  const fin = Buffer.alloc(22);
  const total = Object.keys(ficheros).length;
  fin.writeUInt32LE(0x06054b50, 0); fin.writeUInt16LE(total, 8); fin.writeUInt16LE(total, 10);
  fin.writeUInt32LE(directorio.length, 12); fin.writeUInt32LE(desplazamiento, 16);
  return Buffer.concat([...locales, directorio, fin]);
}

/** Escribe el paquete en ``ruta`` y la devuelve. */
export function escribirPaquete(ruta) {
  writeFileSync(ruta, zip({ 'capas/Tramo_MT.geojson': JSON.stringify(capaTramos()) }));
  return ruta;
}
