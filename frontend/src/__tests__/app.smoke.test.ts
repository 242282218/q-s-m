// @vitest-environment happy-dom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory } from 'vue-router';
import { nextTick } from 'vue';

const apiMocks = vi.hoisted(() => ({
  getCollections: vi.fn(),
  getDetailPageData: vi.fn(),
  getHomeFeed: vi.fn(),
  searchByTitle: vi.fn(),
  searchByTmdb: vi.fn(),
  searchTmdbPosters: vi.fn(),
}));

vi.mock('@/api', () => ({
  addCollection: vi.fn(),
  checkLinks: vi.fn(),
  deleteCollection: vi.fn(),
  getCollections: apiMocks.getCollections,
  getDetailPageData: apiMocks.getDetailPageData,
  getHomeFeed: apiMocks.getHomeFeed,
  getTmdbDetails: vi.fn(),
  saveResource: vi.fn(),
  searchByTitle: apiMocks.searchByTitle,
  searchByTmdb: apiMocks.searchByTmdb,
  searchTmdbPosters: apiMocks.searchTmdbPosters,
  startRenameSse: vi.fn(),
  startVerifySse: vi.fn(),
  transferCollection: vi.fn(),
  verifySingleCollection: vi.fn(),
}));

import { createQsmApp } from '@/app/bootstrap';

class ResizeObserverStub {
  observe() {}

  disconnect() {}
}

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

describe('App browser smoke', () => {
  let host: HTMLDivElement | null = null;
  let cleanup: (() => void) | null = null;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  let consoleLogSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    document.title = '影视墙';
    globalThis.ResizeObserver = ResizeObserverStub as typeof ResizeObserver;

    apiMocks.getHomeFeed.mockResolvedValue(
      ok({
        hero_items: [],
        sections: {},
        section_order: [],
        generated_at: '2026-04-17T00:00:00Z',
      })
    );
    apiMocks.getCollections.mockResolvedValue(
      ok({
        items: [],
        pagination: {
          page: 1,
          page_size: 20,
          total: 0,
          total_pages: 0,
        },
      })
    );
    apiMocks.getDetailPageData.mockResolvedValue(
      ok({
        item: {
          id: 42,
          media_type: 'movie',
          title: 'Alien',
          year: 1979,
          genres: ['科幻'],
          runtime: 117,
          vote: 8.5,
          tagline: '',
          overview: 'In space no one can hear you scream.',
          poster_url: null,
          backdrop_url: null,
          poster_path: null,
          backdrop_path: null,
          cast: [],
          videos: [],
        },
        recommendations: [],
      })
    );
    apiMocks.searchByTmdb.mockResolvedValue(
      ok({
        media: null,
        resources: [],
        total: 0,
        query_time: 0,
      })
    );
    apiMocks.searchByTitle.mockResolvedValue(
      ok({
        media: null,
        resources: [],
        total: 0,
        query_time: 0,
      })
    );
    apiMocks.searchTmdbPosters.mockResolvedValue(
      ok({
        query: 'Alien',
        posters: [],
      })
    );

    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup?.();
    cleanup = null;
    host?.remove();
    host = null;
    document.body.innerHTML = '';
    localStorage.clear();
    vi.clearAllMocks();
    consoleLogSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  it('mounts the real bootstrap, follows redirects, loads a lazy route, and submits search', async () => {
    const { app, router } = createQsmApp(createMemoryHistory());

    await router.push('/collection');
    await router.isReady();
    app.mount(host!);
    cleanup = () => app.unmount();

    await flushUi();
    await flushUi();

    expect(router.currentRoute.value.path).toBe('/collections');
    expect(document.title).toBe('收藏 - 影视墙');
    expect(host!.textContent).toContain('我的收藏');

    await router.push('/missing');
    await flushUi();
    await flushUi();

    expect(router.currentRoute.value.path).toBe('/');
    expect(document.title).toBe('首页 - 影视墙');
    expect(apiMocks.getHomeFeed).toHaveBeenCalled();

    await router.push('/movie/42');
    await flushUi();
    await flushUi();
    await flushUi();

    expect(router.currentRoute.value.path).toBe('/movie/42');
    expect(document.title).toBe('电影详情 - 影视墙');
    expect(host!.textContent).toContain('Alien');
    expect(apiMocks.getDetailPageData).toHaveBeenCalledWith('movie', 42);
    expect(consoleLogSpy).toHaveBeenCalledWith('Navigated to: /movie/42');

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
    expect(document.title).toBe('搜索 - 影视墙');
    expect(host!.textContent).toContain('"Alien" 的搜索结果');
    expect(apiMocks.searchTmdbPosters).toHaveBeenCalledWith('Alien');
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });
});
