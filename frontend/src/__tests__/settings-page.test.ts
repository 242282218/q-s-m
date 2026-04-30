// @vitest-environment happy-dom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp, nextTick } from 'vue';

const apiMocks = vi.hoisted(() => ({
  getHealth: vi.fn(),
  getMetrics: vi.fn(),
  getSettings: vi.fn(),
  getSettingsWithApiKey: vi.fn(),
  updateSettings: vi.fn(),
  updateSettingsWithApiKey: vi.fn(),
}));

const toastPush = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({
  getHealth: apiMocks.getHealth,
  getMetrics: apiMocks.getMetrics,
  getSettings: apiMocks.getSettings,
  getSettingsWithApiKey: apiMocks.getSettingsWithApiKey,
  updateSettings: apiMocks.updateSettings,
  updateSettingsWithApiKey: apiMocks.updateSettingsWithApiKey,
}));

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    push: toastPush,
  }),
}));

import { ApiError } from '@/shared/lib/http';
import SettingsPage from '@/pages/SettingsPage.vue';
import type { HealthData, MetricsData, SettingsCurrentData } from '@/types/api';

function ok<T>(data: T) {
  return {
    code: 0,
    message: '',
    data,
  };
}

function createSettingsSnapshot(overrides: Partial<SettingsCurrentData> = {}): SettingsCurrentData {
  return {
    LOG_LEVEL: 'INFO',
    HTTP_PROXY: '',
    CORS_ORIGINS: '["http://localhost:5173","http://127.0.0.1:5173"]',
    QUARK_SEARCH_BASE_URL: 'http://107.172.8.60:11380',
    TRANSFER_KEEP_EXTRAS: false,
    TRANSFER_KEEP_SUBTITLES: false,
    TRANSFER_DRY_RUN: false,
    TRANSFER_CLEANUP_ENABLED: false,
    TRANSFER_CLEANUP_DELETE_NON_VIDEO: false,
    TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO: false,
    TRANSFER_CLEANUP_DELETE_EMPTY_DIRS: false,
    API_KEY_CONFIGURED: false,
    API_KEY_MASKED: null,
    TMDB_API_KEY_CONFIGURED: false,
    TMDB_API_KEY_MASKED: null,
    QUARK_TRANSFER_COOKIE_CONFIGURED: false,
    QUARK_TRANSFER_COOKIE_MASKED: null,
    ...overrides,
  };
}

function createHealthSnapshot(overrides: Partial<HealthData> = {}): HealthData {
  return {
    status: 'ok',
    service: 'qsm',
    timestamp: '2026-04-17T00:00:00Z',
    checks: {
      api: { status: 'ok', message: '接口正常' },
    },
    ...overrides,
  };
}

function createMetricsSnapshot(overrides: Partial<MetricsData> = {}): MetricsData {
  return {
    requests: {
      total: 12,
      avg_time: 0.23,
      slow_requests_count: 0,
    },
    database: {
      total_queries: 5,
      total_time: 0.9,
      avg_time: 0.18,
      slow_queries_count: 0,
      recent_slow_queries: [],
    },
    timestamp: '2026-04-17T00:00:00Z',
    ...overrides,
  };
}

async function flushUi() {
  await nextTick();
  await Promise.resolve();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
}

describe('SettingsPage', () => {
  let host: HTMLDivElement | null = null;
  let cleanup: (() => void) | null = null;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    localStorage.clear();
    toastPush.mockReset();

    apiMocks.getHealth.mockReset();
    apiMocks.getMetrics.mockReset();
    apiMocks.getSettings.mockReset();
    apiMocks.getSettingsWithApiKey.mockReset();
    apiMocks.updateSettings.mockReset();
    apiMocks.updateSettingsWithApiKey.mockReset();

    apiMocks.getHealth.mockResolvedValue(ok(createHealthSnapshot()));
    apiMocks.getMetrics.mockResolvedValue(ok(createMetricsSnapshot()));
    apiMocks.getSettings.mockResolvedValue(ok(createSettingsSnapshot()));
    apiMocks.getSettingsWithApiKey.mockResolvedValue(ok(createSettingsSnapshot()));
    apiMocks.updateSettings.mockResolvedValue(
      ok({
        updated_keys: ['LOG_LEVEL'],
        restart_required: true,
      })
    );
    apiMocks.updateSettingsWithApiKey.mockResolvedValue(
      ok({
        updated_keys: ['LOG_LEVEL'],
        restart_required: true,
      })
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

  async function mountSettingsPage() {
    const app = createApp(SettingsPage);
    app.mount(host!);
    cleanup = () => app.unmount();
    await flushUi();
    await flushUi();
  }

  function findButtonByText(text: string): HTMLButtonElement {
    const button = Array.from(host!.querySelectorAll('button')).find((candidate) =>
      candidate.textContent?.includes(text)
    );
    expect(button).toBeTruthy();
    return button as HTMLButtonElement;
  }

  function findField<T extends HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(
    labelText: string
  ): T {
    const group = Array.from(host!.querySelectorAll('.form-group')).find(
      (candidate) => candidate.querySelector('.label-text')?.textContent?.trim() === labelText
    );
    expect(group).toBeTruthy();
    const field = group!.querySelector('input, textarea, select');
    expect(field).toBeTruthy();
    return field as T;
  }

  function setFieldValue(
    field: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
    value: string
  ) {
    field.value = value;
    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new Event('change', { bubbles: true }));
  }

  it('prefers the stored API key, renders sorted health issues, and surfaces metrics failures', async () => {
    localStorage.setItem('qsm_api_key', 'stored-key');

    apiMocks.getHealth.mockResolvedValueOnce(
      ok(
        createHealthSnapshot({
          status: 'degraded',
          checks: {
            tmdb: { status: 'warning', message: 'TMDB 未配置' },
            database: { status: 'error', message: '数据库连接失败' },
            cache: { status: 'ok', message: '缓存正常' },
          },
        })
      )
    );
    apiMocks.getMetrics.mockRejectedValueOnce(new Error('metrics unavailable'));
    apiMocks.getSettingsWithApiKey.mockResolvedValueOnce(
      ok(
        createSettingsSnapshot({
          API_KEY_CONFIGURED: true,
          API_KEY_MASKED: 'sto***key',
          TMDB_API_KEY_CONFIGURED: true,
          TMDB_API_KEY_MASKED: 'tmd***key',
          QUARK_TRANSFER_COOKIE_CONFIGURED: true,
          QUARK_TRANSFER_COOKIE_MASKED: 'qua***ie',
        })
      )
    );

    await mountSettingsPage();

    expect(apiMocks.getSettingsWithApiKey).toHaveBeenCalledWith('stored-key');
    expect(apiMocks.getSettings).not.toHaveBeenCalled();
    expect(host!.textContent).toContain('服务降级');
    expect(host!.textContent).toContain('metrics unavailable');
    expect(host!.textContent).toContain('当前已配置：sto***key');
    expect(host!.textContent).toContain('当前已配置：tmd***key');
    expect(host!.textContent).toContain('当前已配置：qua***ie');

    const labels = Array.from(host!.querySelectorAll('.status-issue .issue-label')).map((node) =>
      node.textContent?.trim()
    );

    expect(labels).toEqual(['数据库', 'TMDB']);
    expect(host!.textContent).toContain('数据库连接失败');
    expect(host!.textContent).toContain('TMDB 未配置');
  });

  it('blocks invalid settings before submitting', async () => {
    await mountSettingsPage();

    const tmdbApiKeyInput = findField<HTMLInputElement>('TMDB API Key');
    const pansouUrlInput = findField<HTMLInputElement>('PanSou API 地址');
    setFieldValue(tmdbApiKeyInput, 'short');
    setFieldValue(pansouUrlInput, '107.172.8.60:11380');

    findButtonByText('保存配置').click();
    await flushUi();

    expect(apiMocks.updateSettings).not.toHaveBeenCalled();
    expect(apiMocks.updateSettingsWithApiKey).not.toHaveBeenCalled();
    expect(toastPush).toHaveBeenCalledWith('TMDB API Key 长度不足', 'error');
    expect(toastPush).toHaveBeenCalledWith(
      'PanSou API 地址格式不正确，应以 http:// 或 https:// 开头',
      'error'
    );
  });

  it('blocks invalid CORS origins before submitting', async () => {
    await mountSettingsPage();

    const corsOriginsInput = findField<HTMLInputElement>('CORS 允许来源');
    setFieldValue(corsOriginsInput, '[]');

    findButtonByText('保存配置').click();
    await flushUi();

    expect(apiMocks.updateSettings).not.toHaveBeenCalled();
    expect(apiMocks.updateSettingsWithApiKey).not.toHaveBeenCalled();
    expect(toastPush).toHaveBeenCalledWith(
      'CORS_ORIGINS 必须是字符串数组，例如 ["https://example.com"]',
      'error'
    );
  });

  it('shows that runtime settings save without backend restart', async () => {
    localStorage.setItem('qsm_api_key', 'stored-key');
    apiMocks.updateSettingsWithApiKey.mockResolvedValueOnce(
      ok({
        updated_keys: ['CORS_ORIGINS', 'QUARK_SEARCH_BASE_URL'],
        restart_required: false,
      })
    );

    await mountSettingsPage();

    const corsOriginsInput = findField<HTMLInputElement>('CORS 允许来源');
    const pansouUrlInput = findField<HTMLInputElement>('PanSou API 地址');
    setFieldValue(corsOriginsInput, '["https://example.com"]');
    setFieldValue(pansouUrlInput, 'http://127.0.0.1:8888');

    findButtonByText('保存配置').click();
    await flushUi();
    await flushUi();

    expect(apiMocks.updateSettingsWithApiKey).toHaveBeenCalledWith(
      expect.objectContaining({
        CORS_ORIGINS: '["https://example.com"]',
        QUARK_SEARCH_BASE_URL: 'http://127.0.0.1:8888',
      }),
      'stored-key'
    );
    expect(toastPush).toHaveBeenCalledWith('配置已保存，运行时配置已即时生效', 'success', 3200);
  });

  it('clears the locally stored API key from the current browser', async () => {
    localStorage.setItem('qsm_api_key', 'stored-key');

    await mountSettingsPage();

    expect(host!.textContent).toContain('当前浏览器已保存一个本地 API Key');

    findButtonByText('清除本机已保存 Key').click();
    await flushUi();

    expect(localStorage.getItem('qsm_api_key')).toBeNull();
    expect(host!.textContent).toContain('当前浏览器未保存本地 API Key');
    expect(toastPush).toHaveBeenCalledWith('已清除本机保存的 API Key', 'success');
  });

  it('retries save with the next API key candidate, persists the new key, and refreshes page state', async () => {
    localStorage.setItem('qsm_api_key', 'old-key');

    apiMocks.getSettingsWithApiKey
      .mockResolvedValueOnce(
        ok(
          createSettingsSnapshot({
            API_KEY_CONFIGURED: true,
            API_KEY_MASKED: 'old***key',
          })
        )
      )
      .mockResolvedValueOnce(
        ok(
          createSettingsSnapshot({
            API_KEY_CONFIGURED: true,
            API_KEY_MASKED: 'new***key',
            HTTP_PROXY: 'http://127.0.0.1:7890',
            TRANSFER_KEEP_EXTRAS: true,
          })
        )
      );

    apiMocks.updateSettingsWithApiKey
      .mockRejectedValueOnce(new ApiError('无效或缺失 API Key', 401, 401))
      .mockResolvedValueOnce(
        ok({
          updated_keys: ['API_KEY', 'HTTP_PROXY', 'TRANSFER_KEEP_EXTRAS'],
          restart_required: true,
        })
      );

    await mountSettingsPage();

    const apiKeyInput = findField<HTMLInputElement>('API 访问 Key');
    const proxyInput = findField<HTMLInputElement>('HTTP 代理');
    const keepExtrasToggle = host!.querySelector<HTMLButtonElement>(
      'button[aria-label="保留额外文件"]'
    );

    expect(keepExtrasToggle).toBeTruthy();

    setFieldValue(apiKeyInput, 'new-current-key');
    setFieldValue(proxyInput, 'http://127.0.0.1:7890');
    keepExtrasToggle!.click();

    findButtonByText('保存配置').click();
    await flushUi();
    await flushUi();
    await flushUi();

    const expectedPayload = {
      LOG_LEVEL: 'INFO',
      API_KEY: 'new-current-key',
      HTTP_PROXY: 'http://127.0.0.1:7890',
      CORS_ORIGINS: '["http://localhost:5173","http://127.0.0.1:5173"]',
      QUARK_SEARCH_BASE_URL: 'http://107.172.8.60:11380',
      TRANSFER_KEEP_EXTRAS: true,
      TRANSFER_KEEP_SUBTITLES: false,
      TRANSFER_DRY_RUN: false,
      TRANSFER_CLEANUP_ENABLED: false,
      TRANSFER_CLEANUP_DELETE_NON_VIDEO: false,
      TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO: false,
      TRANSFER_CLEANUP_DELETE_EMPTY_DIRS: false,
    };

    expect(apiMocks.updateSettingsWithApiKey).toHaveBeenNthCalledWith(
      1,
      expectedPayload,
      'old-key'
    );
    expect(apiMocks.updateSettingsWithApiKey).toHaveBeenNthCalledWith(
      2,
      expectedPayload,
      'new-current-key'
    );
    expect(localStorage.getItem('qsm_api_key')).toBe('new-current-key');
    expect(apiMocks.getSettingsWithApiKey.mock.calls.map(([apiKey]) => apiKey)).toEqual([
      'old-key',
      'new-current-key',
    ]);
    expect(apiMocks.getHealth).toHaveBeenCalledTimes(2);
    expect(apiMocks.getMetrics).toHaveBeenCalledTimes(2);
    expect(toastPush).toHaveBeenCalledWith('配置已保存，请按提示重启后端服务', 'success', 3200);
  });
});
