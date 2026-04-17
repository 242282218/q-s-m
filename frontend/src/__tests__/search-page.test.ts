// @vitest-environment happy-dom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp, defineComponent, h, nextTick } from 'vue';
import { createMemoryHistory, createRouter, RouterView } from 'vue-router';

const apiMocks = vi.hoisted(() => ({
  searchTmdbPosters: vi.fn(),
}));

vi.mock('@/api', () => ({
  searchTmdbPosters: apiMocks.searchTmdbPosters,
}));

import SearchPage from '@/pages/SearchPage.vue';

function ok<T>(data: T) {
  return {
    code: 0,
    message: '',
    data,
  };
}

async function flushUi() {
  await nextTick();
  await Promise.resolve();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
}

describe('SearchPage', () => {
  let host: HTMLDivElement | null = null;
  let cleanup: (() => void) | null = null;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    apiMocks.searchTmdbPosters.mockImplementation((query: string) =>
      Promise.resolve(
        ok({
          query,
          posters: [],
        })
      )
    );
  });

  afterEach(() => {
    cleanup?.();
    cleanup = null;
    host?.remove();
    host = null;
    document.body.innerHTML = '';
    localStorage.clear();
    vi.clearAllMocks();
  });

  async function mountSearchPage(initialPath: string) {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/search', component: SearchPage },
        { path: '/:pathMatch(.*)*', redirect: '/search' },
      ],
    });
    const app = createApp(
      defineComponent({
        name: 'SearchPageTestHost',
        setup: () => () => h(RouterView),
      })
    );

    app.use(router);
    await router.push(initialPath);
    await router.isReady();
    app.mount(host!);
    cleanup = () => app.unmount();
    await flushUi();
    await flushUi();

    return router;
  }

  it('renders the empty state and ignores broken stored history payloads', async () => {
    localStorage.setItem('searchHistory', '{bad-json');

    await mountSearchPage('/search');

    expect(host!.textContent).toContain('请输入关键字开始搜索');
    expect(host!.textContent).not.toContain('历史记录');
    expect(apiMocks.searchTmdbPosters).not.toHaveBeenCalled();
  });

  it('saves search history, clears it, and uses quick tags to navigate', async () => {
    const router = await mountSearchPage('/search?q=Alien');

    expect(apiMocks.searchTmdbPosters).toHaveBeenCalledWith('Alien');
    expect(localStorage.getItem('searchHistory')).toBe('["Alien"]');
    expect(host!.textContent).toContain('"Alien" 的搜索结果');

    await router.push('/search');
    await flushUi();
    await flushUi();

    expect(host!.textContent).toContain('历史记录');
    expect(host!.textContent).toContain('Alien');

    const clearButton = Array.from(host!.querySelectorAll('button')).find(
      (button) => button.textContent === '清除'
    );
    expect(clearButton).toBeTruthy();

    clearButton!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushUi();

    expect(localStorage.getItem('searchHistory')).toBeNull();
    expect(host!.textContent).not.toContain('历史记录');

    const tagButton = Array.from(host!.querySelectorAll('button')).find(
      (button) => button.textContent === '科幻'
    );
    expect(tagButton).toBeTruthy();

    tagButton!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await flushUi();
    await flushUi();

    expect(router.currentRoute.value.query.q).toBe('科幻');
    expect(apiMocks.searchTmdbPosters).toHaveBeenCalledWith('科幻');
    expect(localStorage.getItem('searchHistory')).toBe('["科幻"]');
    expect(host!.textContent).toContain('"科幻" 的搜索结果');
  });
});
