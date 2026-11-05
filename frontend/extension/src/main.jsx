import React from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/poppins/400.css';
import '@fontsource/poppins/500.css';
import '@fontsource/poppins/600.css';
import '@fontsource/poppins/700.css';
import '@fontsource/ibm-plex-mono/400.css';
import '../../src/styles.css';
import './popup.css';
import PopupApp from './PopupApp.jsx';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PopupApp />
  </React.StrictMode>,
);
