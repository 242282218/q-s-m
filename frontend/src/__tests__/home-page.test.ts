// @vitest-environment happy-dom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp, nextTick } from 'vue';

const apiMocks = vi.hoisted(() => ({
  getHomeFeed: vi.fn(),
}));

const preloadSpy = vi.hoisted(() => vi.fn());
const toastPush = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  getHomeFeed: apiMocks.getHomeFeed,
}));

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    push: toastPush,
  }),
}));

vi.mock('@/utils/imagePreloader', () => ({
  imagePreloader: {
    preload: preloadSpy,
  },
}));

import HomePage from '@/pages/HomePage.vue';
import type { HomeData } from '@/types/api';

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

function createHomeFeed(overrides: Partial<HomeData> = {}): HomeData {
  return {
    hero_items: [
      {
        id: 1,
        media_type: 'movie',
        title: 'Alien',
        year: 1979,
        genres: ['科幻', '惊悚'],
        runtime: 117,
        vote: 8.5,
        tagline: 'In space no one can hear you scream.',
        overview: 'A terrifying encounter in deep space.',
        poster_url: 'https://image.example/poster-alien.jpg',
        backdrop_url: 'https://image.example/backdrop-alien.jpg',
      },
      {
        id: 2,
        media_type: 'movie',
        title: 'Blade Runner',
        year: 1982,
        genres: ['科幻'],
        runtime: 118,
        vote: 8.2,
        tagline: 'More human than human.',
        overview: 'A blade runner hunts replicants.',
        poster_url: 'https://image.example/poster-blade-runner.jpg',
        backdrop_url: 'https://image.example/backdrop-blade-runner.jpg',
      },
    ],
    sections: {
      trending: [
        {
          id: 10,
          media_type: 'movie',
          title: 'Arrival',
          subtitle: '2016',
          overview: 'Linguists decipher an alien language.',
          genres: [878],
          tone: 'cool',
          poster_url: 'https://image.example/poster-arrival.jpg',
          backdrop_url: null,
        },
      ],
    },
    section_order: [
      {
        key: 'trending',
        title: '趋势推荐',
        tag: 'TMDB',
      },
    ],
    generated_at: '2026-04-17T00:00:00Z',
    ...overrides,
  };
}

async function flushUi() {
  await nextTick();
  await Promise.resolve();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
}

describe('HomePage', () => {
  let host: HTMLDivElement | null = null;
  let cleanup: (() => void) | null = null;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    globalThis.ResizeObserver = ResizeObserverStub as typeof ResizeObserver;
    preloadSpy.mockReset();
    toastPush.mockReset();
    apiMocks.getHomeFeed.mockReset();
    apiMocks.getHomeFeed.mockResolvedValue(ok(createHomeFeed()));
  });

  afterEach(() => {
    cleanup?.();
    cleanup = null;
    host?.remove();
    host = null;
    document.body.innerHTML = '';
    vi.clearAllMocks();
  });

  async function mountHomePage() {
    const app = createApp(HomePage);
    app.mount(host!);
    cleanup = () => app.unmount();
    await flushUi();
    await flushUi();
  }

  function activeHeroTitle(): string | null {
    return host!.querySelector('.hero-slide.active .hero-title')?.textContent?.trim() ?? null;
  }

  it('loads the home feed, preloads hero images, and supports hero navigation', async () => {
    await mountHomePage();

    expect(apiMocks.getHomeFeed).toHaveBeenCalledTimes(1);
    expect(preloadSpy).toHaveBeenCalledWith([
      'https://image.example/backdrop-alien.jpg',
      'https://image.example/backdrop-blade-runner.jpg',
    ]);
    expect(activeHeroTitle()).toBe('Alien');
    expect(host!.textContent).toContain('趋势推荐');
    expect(host!.textContent).toContain('Arrival');

    const nextButton = host!.querySelector<HTMLButtonElement>('button[aria-label="下一张"]');
    expect(nextButton).toBeTruthy();

    nextButton!.click();
    await flushUi();

    expect(activeHeroTitle()).toBe('Blade Runner');
  });

  it('shows the empty state on failed load and retries successfully', async () => {
    apiMocks.getHomeFeed
      .mockResolvedValueOnce({
        code: 1,
        message: 'TMDB 暂时不可用',
        data: createHomeFeed({
          hero_items: [],
          sections: {},
          section_order: [],
        }),
      })
      .mockResolvedValueOnce(ok(createHomeFeed()));

    await mountHomePage();

    expect(host!.textContent).toContain('首页数据加载失败');
    expect(host!.textContent).toContain('请检查后端 TMDB 配置后重试');
    expect(toastPush).toHaveBeenCalledWith('TMDB 暂时不可用', 'error');

    const retryButton = Array.from(host!.querySelectorAll<HTMLButtonElement>('button')).find(
      (node) => node.textContent?.includes('重新加载')
    );
    expect(retryButton).toBeTruthy();

    retryButton!.click();
    await flushUi();
    await flushUi();

    expect(apiMocks.getHomeFeed).toHaveBeenCalledTimes(2);
    expect(activeHeroTitle()).toBe('Alien');
    expect(host!.textContent).toContain('趋势推荐');
  });

  it('replaces failed hero images with the built-in fallback view', async () => {
    await mountHomePage();

    const heroImage = host!.querySelector<HTMLImageElement>(
      '.hero-slide.active .hero-background img'
    );
    expect(heroImage).toBeTruthy();

    heroImage!.dispatchEvent(new Event('error'));
    await flushUi();

    expect(host!.querySelector('.hero-slide.active .hero-background img')).toBeNull();
    expect(host!.querySelector('.hero-slide.active .hero-image-fallback')).toBeTruthy();
  });
});
