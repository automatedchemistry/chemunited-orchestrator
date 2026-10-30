import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { installApiTokenFetchInterceptor } from './composables/useApiToken'
import { bootstrapCustomizations } from './extensions/bootstrap'

installApiTokenFetchInterceptor()

async function start() {
  // The project's custom pages must be routes before the router's first navigation.
  await bootstrapCustomizations(router)
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.mount('#app')
}

void start()
