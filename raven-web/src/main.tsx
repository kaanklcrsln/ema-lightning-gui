import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/nunito/500.css'
import '@fontsource/nunito/600.css'
import '@fontsource/nunito/700.css'
import './theme.css'
import { App } from './App'

const root = document.getElementById('root')
if (!root) throw new Error('#root bulunamadı')
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
