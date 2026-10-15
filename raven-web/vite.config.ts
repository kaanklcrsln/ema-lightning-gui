import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The avatar (../kirby-avatar) and the logo font (../Bagel_Fat_One) live outside this folder.
// base './' lets the same build work at any path, such as GitHub Pages' /raven/.
export default defineConfig({
  base: './',
  plugins: [react()],
  resolve: { dedupe: ['react', 'react-dom'] },
  server: { port: 5180, fs: { allow: ['..'] } },
})
