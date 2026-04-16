// @vitest-environment happy-dom

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createApp, defineComponent, h, nextTick } from 'vue';
import { createMemoryHistory, createRouter, useRoute } from 'vue-router';

import App from '@/App.vue';

const SearchProbe = defineComponent({
  name: 'SearchProbe',
  setup() {
    const route = useRoute();
    return () =>
      h('div', { 'data-testid': 'search-probe' }, `search:${String(route.query.q || '')}`);
  },
});

const routes = [
  { path: '/', component: defineComponent(() => () => h('div', 'home page')) },
  { path: '/collections', component: defineComponent(() => () => h('div', 'collections page')) },
  { path: '/settings', component: defineComponent(() => () => h('div', 'settings page')) },
  { path: '/search', component: SearchProbe },
];

class ResizeObserverStub {
  observe() {}

  disconnect() {}
}

async function flushUi() {
  await nextTick();
  await Promise.resolve();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
}

describe('App browser smoke', () => {
  let host: HTMLDivElement | null = null;
  let cleanup: (() => void) | null = null;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    document.title = '影视墙';
    globalThis.ResizeObserver = ResizeObserverStub as typeof ResizeObserver;
  });

  afterEach(() => {
    cleanup?.();
    cleanup = null;
    host?.remove();
    host = null;
    document.body.innerHTML = '';
    localStorage.clear();
  });

  it('mounts the shell, switches routes, and submits search through the router', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes,
    });
    const app = createApp(App);

    app.use(router);
    await router.push('/');
    await router.isReady();
    app.mount(host!);
    cleanup = () => app.unmount();

    await flushUi();

    expect(host!.textContent).toContain('影视墙');
    expect(host!.textContent).toContain('首页');
    expect(host!.textContent).toContain('home page');

    const settingsLink = host!.querySelector('a[href="/settings"]');
    expect(settingsLink).toBeTruthy();
    await router.push('/settings');

    await flushUi();

    expect(router.currentRoute.value.path).toBe('/settings');
    expect(host!.textContent).toContain('settings page');

    const searchInput = host!.querySelector<HTMLInputElement>('input[name="q"]');
    const searchForm = host!.querySelector<HTMLFormElement>('form[role="search"]');

    expect(searchInput).toBeTruthy();
    expect(searchForm).toBeTruthy();

    searchInput!.value = 'Alien';
    searchInput!.dispatchEvent(new Event('input', { bubbles: true }));
    await nextTick();
    searchForm!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));

    await flushUi();
    await flushUi();

    expect(router.currentRoute.value.fullPath).toBe('/search?q=Alien');
    expect(host!.querySelector('[data-testid="search-probe"]')?.textContent).toBe('search:Alien');
  });
});
