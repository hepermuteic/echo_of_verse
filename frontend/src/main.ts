import { createApp } from 'vue'
import './fonts'
import './style.css'
import App from './App.vue'

createApp(App).mount('#app')

if (location.search.includes('audit')) {
  document.fonts.ready.then(() => setTimeout(() => import('./audit').then((m) => m.runAudit()), 2500))
}
