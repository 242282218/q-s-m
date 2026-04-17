import { createApp, type App as VueApplication } from 'vue';
import type { RouterHistory } from 'vue-router';

import App from '@/App.vue';

import { createAppRouter } from './router';

export function installGlobalErrorHandler(app: VueApplication<Element>) {
  app.config.errorHandler = (err, vm, info) => {
    console.error('Global error:', err, info);
    console.error('Component:', vm);
  };
}

export function createQsmApp(history?: RouterHistory) {
  const app = createApp(App);
  const router = createAppRouter(history);

  app.use(router);
  installGlobalErrorHandler(app);

  return { app, router };
}
