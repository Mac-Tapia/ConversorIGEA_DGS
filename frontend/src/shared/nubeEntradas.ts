import { createContext, useContext, type ComponentType } from 'react';
import type { Origen } from './origenes';

/**
 * 109:RF-21, RF-22, RF-24: lo que el campo único de cada entrada y el «Guardar» de cada salida saben de la nube. Sin
 * proveedor (sin cuenta, sin red, o fuera de la aplicación), solo el equipo: los dos funcionan igual.
 */
export interface NubeEntradas {
  origenes: Origen[];
  /** Abre el selector del proveedor, guarda la copia fija y la devuelve como ficheros del navegador. */
  traer: (proveedor: Exclude<Origen, 'equipo'>, entrada: string, varios: boolean) => Promise<File[]>;
  /** 109:RF-24: el botón que publica una salida (su ruta en la salida del espacio) por RF-9; sin cuenta, no hay. */
  Publicar?: ComponentType<{ seleccion: string[]; nombre: string }>;
}

export const SOLO_EQUIPO: NubeEntradas = { origenes: ['equipo'], traer: async () => [] };

export const NubeEntradasCtx = createContext<NubeEntradas>(SOLO_EQUIPO);

export const useNubeEntradas = () => useContext(NubeEntradasCtx);
