import { Component, type ErrorInfo, type ReactNode } from 'react';

/**
 * 042:RF-79: sin esto, un dato que no llega deja toda la página en blanco, y otra vez al recargar si
 * el trabajo que lo causó sigue entre los últimos. El detalle va a la consola, no al operador.
 */
export class SinPantallaEnBlanco extends Component<{ children: ReactNode }, { fallo: boolean }> {
  state = { fallo: false };

  static getDerivedStateFromError() {
    return { fallo: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Fallo al dibujar la pantalla', error, info.componentStack);
  }

  render() {
    if (!this.state.fallo) return this.props.children;
    return (
      <div className="alert alert-error" role="alert">
        <strong>Esta parte de la pantalla no se pudo mostrar.</strong> Sus datos y sus trabajos no se han perdido.{' '}
        <button className="btn btn-sm" onClick={() => window.location.reload()}>Recargar</button>
      </div>
    );
  }
}
