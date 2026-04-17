// @vitest-environment happy-dom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp, defineComponent, nextTick, ref } from 'vue';

const apiMocks = vi.hoisted(() => ({
  addCollection: vi.fn(),
  checkLinks: vi.fn(),
  getDetailPageData: vi.fn(),
  saveResource: vi.fn(),
  searchByTitle: vi.fn(),
  searchByTmdb: vi.fn(),
}));

const toastPush = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  addCollection: apiMocks.addCollection,
  checkLinks: apiMocks.checkLinks,
  getDetailPageData: apiMocks.getDetailPageData,
  saveResource: apiMocks.saveResource,
  searchByTitle: apiMocks.searchByTitle,
  searchByTmdb: apiMocks.searchByTmdb,
}));

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    push: toastPush,
  }),
}));

import DetailPage from '@/pages/DetailPage.vue';
import type { DetailItem, DetailPageData, ResourceDto } from '@/types/api';

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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function createDetailItem(overrides: Partial<DetailItem> = {}): DetailItem {
  return {
    id: 42,
    media_type: 'movie',
    title: 'Alien',
    year: 1979,
    genres: ['科幻', '惊悚'],
    runtime: 117,
    vote: 8.5,
    tagline: 'In space no one can hear you scream.',
    overview: 'A terrifying encounter in deep space.',
    poster_url: null,
    backdrop_url: null,
    poster_path: null,
    backdrop_path: null,
    cast: [],
    videos: [],
    ...overrides,
  };
}

function createDetailPageData(overrides: Partial<DetailPageData> = {}): DetailPageData {
  return {
    item: createDetailItem(),
    recommendations: [],
    ...overrides,
  };
}

function createResource(overrides: Partial<ResourceDto> = {}): ResourceDto {
  return {
    name: 'Alien 1979 4K',
    link: 'https://pan.quark.cn/s/alien',
    overall_score: 0.94,
    quality_level: '4K',
    resolution: '4K',
    codec: 'HEVC',
    is_best: true,
    normalized_name: 'Alien 1979 4K',
    conf: 0.9,
    qual: 0.9,
    alpha: 0.9,
    tags: ['4k', 'hdr'],
    size_gb: 12.5,
    c_text: 0.9,
    c_intent: 0.9,
    c_plaus: 0.9,
    p: 0.9,
    r: 0.9,
    ...overrides,
  };
}

async function flushUi() {
  await nextTick();
  await Promise.resolve();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
}

async function flushPromisesOnly() {
  await nextTick();
  await Promise.resolve();
  await nextTick();
}

describe('DetailPage', () => {
  let host: HTMLDivElement | null = null;
  let cleanup: (() => void) | null = null;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    globalThis.ResizeObserver = ResizeObserverStub as typeof ResizeObserver;

    toastPush.mockReset();
    apiMocks.addCollection.mockReset();
    apiMocks.checkLinks.mockReset();
    apiMocks.getDetailPageData.mockReset();
    apiMocks.saveResource.mockReset();
    apiMocks.searchByTitle.mockReset();
    apiMocks.searchByTmdb.mockReset();

    apiMocks.getDetailPageData.mockResolvedValue(ok(createDetailPageData()));
    apiMocks.searchByTmdb.mockResolvedValue(
      ok({
        media: null,
        resources: [createResource()],
        total: 1,
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
    apiMocks.checkLinks.mockResolvedValue(
      ok({
        results: [],
      })
    );
    apiMocks.addCollection.mockResolvedValue(
      ok({
        created: true,
        id: 11,
      })
    );
    apiMocks.saveResource.mockResolvedValue(
      ok({
        saved_files: ['Alien.mkv'],
        task_id: 'task-1',
        collection_id: 11,
        collection_created: true,
      })
    );
  });

  afterEach(() => {
    cleanup?.();
    cleanup = null;
    host?.remove();
    host = null;
    document.body.innerHTML = '';
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  async function mountDetailPage(initial: { mediaType?: 'movie' | 'tv'; itemId?: number } = {}) {
    const mediaType = ref<'movie' | 'tv'>(initial.mediaType ?? 'movie');
    const itemId = ref(initial.itemId ?? 42);

    const Root = defineComponent({
      components: { DetailPage },
      setup() {
        return {
          mediaType,
          itemId,
        };
      },
      template: '<DetailPage :media-type="mediaType" :item-id="itemId" />',
    });

    const app = createApp(Root);
    app.mount(host!);
    cleanup = () => app.unmount();
    await flushUi();
    await flushUi();

    return { mediaType, itemId };
  }

  function resourceCard(name: string) {
    const card = Array.from(host!.querySelectorAll<HTMLElement>('.quark-resource-card')).find((node) =>
      node.textContent?.includes(name)
    );
    expect(card).toBeTruthy();
    return card as HTMLElement;
  }

  function clickButtonWithin(scope: HTMLElement, selector: string) {
    const button = scope.querySelector<HTMLButtonElement>(selector);
    expect(button).toBeTruthy();
    button!.click();
    return button as HTMLButtonElement;
  }

  it('falls back to title search and restores collected state for returned resources', async () => {
    const collected = createResource({
      name: 'Alien Directors Cut',
      link: 'https://pan.quark.cn/s/alien-collected',
      is_best: true,
    });
    const fresh = createResource({
      name: 'Alien Theatrical',
      link: 'https://pan.quark.cn/s/alien-fresh',
      is_best: false,
      overall_score: 0.71,
      resolution: '1080p',
      quality_level: '1080p',
    });

    apiMocks.searchByTmdb.mockResolvedValueOnce(
      ok({
        media: null,
        resources: [],
        total: 0,
        query_time: 0,
      })
    );
    apiMocks.searchByTitle.mockResolvedValueOnce(
      ok({
        media: null,
        resources: [collected, fresh],
        total: 2,
        query_time: 0.08,
      })
    );
    apiMocks.checkLinks.mockResolvedValueOnce(
      ok({
        results: [
          { link: collected.link, collected: true, id: 1, status: 1 },
          { link: fresh.link, collected: false, id: null, status: null },
        ],
      })
    );

    await mountDetailPage();

    expect(apiMocks.searchByTmdb).toHaveBeenCalledWith(42, 'movie', 100);
    expect(apiMocks.searchByTitle).toHaveBeenCalledWith('Alien', 1979, 100);
    expect(apiMocks.checkLinks).toHaveBeenCalledWith({
      links: [collected.link, fresh.link],
    });
    expect(host!.textContent).toContain('Alien');
    expect(host!.textContent).toContain('2个资源');

    const collectedCard = resourceCard('Alien Directors Cut');
    const freshCard = resourceCard('Alien Theatrical');

    expect(
      collectedCard.querySelector<HTMLButtonElement>('button.btn-collect-resource')?.textContent
    ).toContain('已收藏');
    expect(
      collectedCard.querySelector<HTMLButtonElement>('button.btn-collect-resource')?.disabled
    ).toBe(true);
    expect(
      freshCard.querySelector<HTMLButtonElement>('button.btn-collect-resource')?.textContent
    ).toContain('收藏');
  });

  it('shows resource search errors and retries the current detail item', async () => {
    apiMocks.searchByTmdb
      .mockRejectedValueOnce(new Error('tmdb search failed'))
      .mockResolvedValueOnce(
        ok({
          media: null,
          resources: [createResource({ name: 'Alien Retry Result' })],
          total: 1,
          query_time: 0.02,
        })
      );
    apiMocks.checkLinks.mockResolvedValueOnce(
      ok({
        results: [{ link: 'https://pan.quark.cn/s/alien', collected: false, id: null, status: null }],
      })
    );

    await mountDetailPage();

    expect(host!.textContent).toContain('tmdb search failed');

    const retryButton = Array.from(host!.querySelectorAll<HTMLButtonElement>('button')).find((node) =>
      node.textContent?.includes('重试')
    );
    expect(retryButton).toBeTruthy();

    retryButton!.click();
    await flushUi();
    await flushUi();

    expect(apiMocks.searchByTmdb).toHaveBeenCalledTimes(2);
    expect(host!.textContent).toContain('Alien Retry Result');
    expect(host!.textContent).not.toContain('tmdb search failed');
  });

  it('debounces collect/save actions and normalizes the target folder name', async () => {
    const resource = createResource({
      name: '01. Alien: Director\'s Cut / 4K',
      link: 'https://pan.quark.cn/s/alien-special',
    });

    apiMocks.searchByTmdb.mockResolvedValueOnce(
      ok({
        media: null,
        resources: [resource],
        total: 1,
        query_time: 0.01,
      })
    );
    apiMocks.checkLinks.mockResolvedValueOnce(
      ok({
        results: [{ link: resource.link, collected: false, id: null, status: null }],
      })
    );

    await mountDetailPage();

    const card = resourceCard(resource.name);

    vi.useFakeTimers();
    clickButtonWithin(card, 'button.btn-collect-resource');
    clickButtonWithin(card, 'button.btn-collect-resource');

    expect(apiMocks.addCollection).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(500);
    await flushPromisesOnly();

    expect(apiMocks.addCollection).toHaveBeenCalledTimes(1);
    expect(apiMocks.addCollection).toHaveBeenCalledWith(
      expect.objectContaining({
        tmdb_id: 42,
        media_type: 'movie',
        title: resource.name,
        share_url: resource.link,
      })
    );
    expect(card.textContent).toContain('收藏成功');
    expect(card.textContent).toContain('已收藏');

    clickButtonWithin(card, 'button.btn-save-transfer');
    clickButtonWithin(card, 'button.btn-save-transfer');

    expect(apiMocks.saveResource).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(500);
    await flushPromisesOnly();

    expect(apiMocks.saveResource).toHaveBeenCalledTimes(1);
    expect(apiMocks.saveResource).toHaveBeenCalledWith(
      expect.objectContaining({
        link: resource.link,
        media_type: 'movie',
        title: 'Alien',
        resource_name: resource.name,
        to_dir_name: 'Alien Director\'s Cut 4K',
      })
    );
    expect(card.textContent).toContain('保存成功');
  });

  it('ignores late detail responses after the route params change', async () => {
    const firstLoad = deferred<ReturnType<typeof ok<DetailPageData>>>();

    apiMocks.getDetailPageData
      .mockImplementationOnce(() => firstLoad.promise)
      .mockResolvedValueOnce(
        ok(
          createDetailPageData({
            item: createDetailItem({
              id: 43,
              title: 'Blade Runner',
              year: 1982,
            }),
          })
        )
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

    const state = await mountDetailPage();

    state.itemId.value = 43;
    await flushUi();
    await flushUi();

    expect(host!.textContent).toContain('Blade Runner');
    expect(host!.textContent).not.toContain('Alien');

    firstLoad.resolve(ok(createDetailPageData()));
    await flushUi();
    await flushUi();

    expect(host!.textContent).toContain('Blade Runner');
    expect(host!.textContent).not.toContain('Alien');
  });
});
