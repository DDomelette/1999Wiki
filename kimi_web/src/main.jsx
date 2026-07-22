import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
// 字体本地化（构建期内联，替代原 Google Fonts 外链）
import '@fontsource/libre-caslon-text/400.css'
import '@fontsource/libre-caslon-text/700.css'
import '@fontsource/libre-caslon-text/400-italic.css'
import '@fontsource-variable/jetbrains-mono'
import '@fontsource-variable/material-symbols-outlined'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
