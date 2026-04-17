// @vitest-environment happy-dom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp, nextTick } from 'vue';

const apiMocks = vi.hoisted(() => ({
  deleteCollection: vi.fn(),
  getCollections: vi.fn(),
  getTmdbDetails: vi.fn(),
  startRenameSse: vi.fn(),
  startVerifySse: vi.fn(),
  transferCollection: vi.fn(),
  verifySingleCollection: vi.fn(),
}));

const toastPush = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  deleteCollection: apiMocks.deleteCollection,
  getCollections: apiMocks.getCollections,
  getTmdbDetails: apiMocks.getTmdbDetails,
  startRenameSse: apiMocks.startRenameSse,
  startVerifySse: apiMocks.startVerifySse,
  transferCollection: apiMocks.transferCollection,
  verifySingleCollection: apiMocks.verifySingleCollection,
}));

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    push: toastPush,
  }),
}));

import CollectionPage from '@/pages/CollectionPage.vue';
import type { CollectionItem, SseEnvelope } from '@/types/api';

function ok<T>(data: T) {
  return {
    code: 0,
    message: '',
    data,
  };
}

function createCollectionItem(overrides: Partial<CollectionItem> = {}): CollectionItem {
  return {
    id: 1,
    tmdb_id: 100,
    media_type: 'movie',
    title: 'Alien',
    year: 1979,
    poster_path: null,
    backdrop_path: null,
    quark_share_url: 'https://pan.quark.cn/s/example',
    category: null,
    status: 0,
    saved_at: '2026-04-17T00:00:00Z',
    ...overrides,
  };
}

async function flushUi() {
  await nextTick();
  await Promise.resolve();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
}

describe('CollectionPage', () => {
  let host: HTMLDivElement | null = null;
  let cleanup: (() => void) | null = null;
  let confirmSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    toastPush.mockReset();

    apiMocks.deleteCollection.mockReset();
    apiMocks.getCollections.mockReset();
    apiMocks.getTmdbDetails.mockReset();
    apiMocks.startRenameSse.mockReset();
    apiMocks.startVerifySse.mockReset();
    apiMocks.transferCollection.mockReset();
    apiMocks.verifySingleCollection.mockReset();

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
    apiMocks.getTmdbDetails.mockResolvedValue(
      ok({
        poster_path: '/patched-poster.jpg',
        backdrop_path: '/patched-backdrop.jpg',
        title: 'Alien',
        year: 1979,
      })
    );
    apiMocks.deleteCollection.mockResolvedValue(ok({ deleted: true }));
    apiMocks.transferCollection.mockResolvedValue(
      ok({
        success: true,
        files: [],
      })
    );
    apiMocks.verifySingleCollection.mockResolvedValue(
      ok({
        result: {
          collection_id: 1,
          title: 'Alien',
          previous_status: 0,
          current_status: 1,
          exists: true,
          checked_path: '/media',
          path_source: 'quark',
        },
      })
    );
    apiMocks.startVerifySse.mockResolvedValue(undefined);
    apiMocks.startRenameSse.mockResolvedValue(undefined);

    confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  afterEach(() => {
    cleanup?.();
    cleanup = null;
    host?.remove();
    host = null;
    document.body.innerHTML = '';
    vi.clearAllMocks();
    confirmSpy.mockRestore();
  });

  async function mountCollectionPage() {
    const app = createApp(CollectionPage);
    app.mount(host!);
    cleanup = () => app.unmount();
    await flushUi();
    await flushUi();
  }

  function collectionCard(title: string): HTMLElement {
    const card = Array.from(host!.querySelectorAll<HTMLElement>('.collection-card')).find((node) =>
      node.textContent?.includes(title)
    );
    expect(card).toBeTruthy();
    return card as HTMLElement;
  }

  function modalButton(label: string): HTMLButtonElement {
    const button = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find(
      (node) => node.textContent?.includes(label)
    );
    expect(button).toBeTruthy();
    return button as HTMLButtonElement;
  }

  it('loads collections, backfills missing posters, and keeps rendering responsive', async () => {
    apiMocks.getCollections.mockResolvedValueOnce(
      ok({
        items: [
          createCollectionItem(),
          createCollectionItem({
            id: 2,
            tmdb_id: 0,
            title: 'Blade Runner',
            poster_path: '/blade-runner.jpg',
          }),
        ],
        pagination: {
          page: 1,
          page_size: 20,
          total: 2,
          total_pages: 1,
        },
      })
    );

    await mountCollectionPage();
    await flushUi();

    expect(apiMocks.getCollections).toHaveBeenCalledWith(1, 20);
    expect(apiMocks.getTmdbDetails).toHaveBeenCalledWith('movie', 100);
    expect(host!.textContent).toContain('2 条收藏');
    expect(host!.textContent).toContain('Alien');
    expect(host!.textContent).toContain('Blade Runner');

    const alienPoster = Array.from(host!.querySelectorAll('img')).find((node) =>
      node.getAttribute('alt')?.includes('Alien')
    );

    expect(alienPoster?.getAttribute('src')).toContain('/patched-poster.jpg');
  });

  it('transfers an item and then deletes it from the list via the detail modal', async () => {
    apiMocks.getCollections.mockResolvedValueOnce(
      ok({
        items: [createCollectionItem()],
        pagination: {
          page: 1,
          page_size: 20,
          total: 1,
          total_pages: 1,
        },
      })
    );

    await mountCollectionPage();

    collectionCard('Alien').click();
    await flushUi();

    modalButton('转存').click();
    await flushUi();
    await flushUi();

    expect(apiMocks.transferCollection).toHaveBeenCalledWith({ collection_id: 1 });
    expect(host!.textContent).toContain('已转存');
    expect(toastPush).toHaveBeenCalledWith('转存成功', 'success');

    collectionCard('Alien').click();
    await flushUi();

    modalButton('删除').click();
    await flushUi();
    await flushUi();

    expect(confirmSpy).toHaveBeenCalledWith('确定删除「Alien」？');
    expect(apiMocks.deleteCollection).toHaveBeenCalledWith(1);
    expect(host!.textContent).toContain('暂无收藏');
    expect(toastPush).toHaveBeenCalledWith('删除成功', 'success');
  });

  it('streams verify-all progress into the log modal and patches item status in place', async () => {
    apiMocks.getCollections.mockResolvedValueOnce(
      ok({
        items: [
          createCollectionItem(),
          createCollectionItem({
            id: 2,
            title: 'Arrival',
            tmdb_id: 200,
          }),
        ],
        pagination: {
          page: 1,
          page_size: 20,
          total: 2,
          total_pages: 1,
        },
      })
    );

    apiMocks.startVerifySse.mockImplementationOnce(
      async (_payload: { collection_ids?: number[] | null }, onEnvelope: (event: SseEnvelope) => void) => {
        onEnvelope({
          type: 'log',
          level: 'info',
          message: null,
          timestamp: '2026-04-17T00:00:01Z',
          request_id: 'req-1',
          data: {
            type: 'log',
            current: 0,
            total: 2,
            percentage: 0,
            message: '开始验证网盘状态',
            level: 'info',
          },
        });
        onEnvelope({
          type: 'progress',
          level: 'info',
          message: null,
          timestamp: '2026-04-17T00:00:02Z',
          request_id: 'req-1',
          data: {
            type: 'progress',
            current: 1,
            total: 2,
            percentage: 50,
            message: '已检查 1/2',
            level: 'info',
            collection_id: 1,
            current_status: 2,
          },
        });
        onEnvelope({
          type: 'complete',
          level: 'info',
          message: null,
          timestamp: '2026-04-17T00:00:03Z',
          request_id: 'req-1',
          data: {
            type: 'complete',
            current: 2,
            total: 2,
            percentage: 100,
            message: '验证完成',
            level: 'info',
            exists: 1,
            deleted: 1,
            failed: 0,
            collection_id: 1,
            current_status: 2,
          },
        });
      }
    );

    await mountCollectionPage();

    const verifyAllButton = Array.from(host!.querySelectorAll<HTMLButtonElement>('button')).find(
      (node) => node.textContent?.includes('验证网盘状态')
    );
    expect(verifyAllButton).toBeTruthy();

    verifyAllButton!.click();
    await flushUi();
    await flushUi();

    expect(apiMocks.startVerifySse).toHaveBeenCalled();
    expect(document.body.textContent).toContain('网盘状态验证');
    expect(document.body.textContent).toContain('完成汇总：存在 1 个，已删除 1 个，失败 0 个');
    expect(document.body.textContent).toContain('2/2');
    expect(host!.textContent).toContain('已失效');
    expect(toastPush).toHaveBeenCalledWith('任务执行完成', 'success');
  });
});
