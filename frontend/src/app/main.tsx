import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { SinPantallaEnBlanco } from '../shared/SinPantallaEnBlanco';
import { ConfirmProvider, ToastProvider } from '../shared/ui';
import '../shared/styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider>
      <ConfirmProvider>
        <SinPantallaEnBlanco><App /></SinPantallaEnBlanco>
      </ConfirmProvider>
    </ToastProvider>
  </StrictMode>,
);
