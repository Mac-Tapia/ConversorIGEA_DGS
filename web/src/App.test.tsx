import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('cockpit shell', () => {
  it('renders the six project modules', () => {
    render(<App />)
    for (const label of [
      'Proyecto',
      'Diagnóstico G1–G4',
      'Unifilar',
      'Mapa',
      'PowerFactory G5–G6',
      'Evidencias',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })
})
