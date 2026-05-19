import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';

window.addEventListener('error', (event) => {
  const root = document.getElementById('root');
  if (root) {
    root.innerHTML = `<div style="padding:20px;color:#fff;background:#111;font-size:13px;font-family:monospace;word-break:break-all">
      <b>JS Error:</b><br>${event.message}<br><br>
      <b>File:</b> ${event.filename}<br>
      <b>Line:</b> ${event.lineno}:${event.colno}<br><br>
      <b>Stack:</b><br>${event.error?.stack ?? 'no stack'}
    </div>`;
  }
});

window.addEventListener('unhandledrejection', (event) => {
  const root = document.getElementById('root');
  if (root) {
    root.innerHTML = `<div style="padding:20px;color:#fff;background:#111;font-size:13px;font-family:monospace;word-break:break-all">
      <b>Unhandled Promise:</b><br>${String(event.reason)}
    </div>`;
  }
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
