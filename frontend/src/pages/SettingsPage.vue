<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import {
  getHealth,
  getMetrics,
  getSettings,
  getSettingsWithApiKey,
  updateSettings,
  updateSettingsWithApiKey,
} from '@/api';
import ToggleSwitch from '@/components/ToggleSwitch.vue';
import type { HealthCheck, SettingsCurrentData, SettingsUpdate } from '@/types/api';
import { useToast } from '@/composables/useToast';
import { getApiKeyCandidates, setConfiguredApiKey } from '@/lib/api-key';
import { ApiError } from '@/lib/http';
import { getHealthIssues, getHealthStatusLabel, getHealthTone } from '@/utils/healthStatus';

const { push } = useToast();

const loading = ref(false);
const health = ref('unknown');
const healthChecks = ref<Record<string, HealthCheck>>({});
const metricsSummary = ref('');
const metricsData = ref<{
  requests: { total: number; avg_time: number };
  database: { total_queries: number; avg_time: number };
} | null>(null);
const healthTone = computed(() => getHealthTone(health.value));
const healthStatusLabel = computed(() => getHealthStatusLabel(health.value));
const healthIssues = computed(() => getHealthIssues(healthChecks.value));

const form = reactive({
  LOG_LEVEL: '',
  API_KEY: '',
  TMDB_API_KEY: '',
  HTTP_PROXY: '',
  QUARK_TRANSFER_COOKIE: '',
  TRANSFER_KEEP_EXTRAS: false,
  TRANSFER_KEEP_SUBTITLES: false,
  TRANSFER_DRY_RUN: false,
  TRANSFER_CLEANUP_ENABLED: false,
  TRANSFER_CLEANUP_DELETE_NON_VIDEO: false,
  TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO: false,
  TRANSFER_CLEANUP_DELETE_EMPTY_DIRS: false,
});

const secretFieldHints = reactive({
  API_KEY: '留空则不修改',
  TMDB_API_KEY: '留空则不修改',
  QUARK_TRANSFER_COOKIE: '留空则不修改',
});

const boolFields = [
  'TRANSFER_KEEP_EXTRAS',
  'TRANSFER_KEEP_SUBTITLES',
  'TRANSFER_DRY_RUN',
  'TRANSFER_CLEANUP_ENABLED',
  'TRANSFER_CLEANUP_DELETE_NON_VIDEO',
  'TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO',
  'TRANSFER_CLEANUP_DELETE_EMPTY_DIRS',
] as const;

type BoolField = (typeof boolFields)[number];

function applySettingsSnapshot(snapshot: SettingsCurrentData) {
  form.LOG_LEVEL = snapshot.LOG_LEVEL || '';
  form.HTTP_PROXY = snapshot.HTTP_PROXY || '';

  boolFields.forEach((key) => {
    form[key] = snapshot[key];
  });

  form.API_KEY = '';
  form.TMDB_API_KEY = '';
  form.QUARK_TRANSFER_COOKIE = '';

  secretFieldHints.API_KEY = snapshot.API_KEY_CONFIGURED
    ? `当前已配置：${snapshot.API_KEY_MASKED ?? '***'}，留空则不修改`
    : '未配置，留空则不修改';
  secretFieldHints.TMDB_API_KEY = snapshot.TMDB_API_KEY_CONFIGURED
    ? `当前已配置：${snapshot.TMDB_API_KEY_MASKED ?? '***'}，留空则不修改`
    : '未配置，留空则不修改';
  secretFieldHints.QUARK_TRANSFER_COOKIE = snapshot.QUARK_TRANSFER_COOKIE_CONFIGURED
    ? `当前已配置：${snapshot.QUARK_TRANSFER_COOKIE_MASKED ?? '***'}，留空则不修改`
    : '未配置，留空则不修改';
}

async function loadSettingsSnapshot() {
  const candidates = getApiKeyCandidates(String(form.API_KEY || '').trim());
  let lastError: unknown;

  if (candidates.length === 0) {
    const res = await getSettings();
    if (res.code !== 0) {
      throw new Error(res.message || '无法读取当前配置');
    }
    applySettingsSnapshot(res.data);
    return;
  }

  for (const apiKey of candidates) {
    try {
      const res = await getSettingsWithApiKey(apiKey);
      if (res.code !== 0) {
        throw new Error(res.message || '无法读取当前配置');
      }
      applySettingsSnapshot(res.data);
      return;
    } catch (error) {
      lastError = error;
      if (!(error instanceof ApiError) || error.status !== 401) {
        throw error;
      }
    }
  }

  if (lastError instanceof Error) {
    throw lastError;
  }

  throw new Error('无法读取当前配置');
}

function validateSettings(): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (form.TMDB_API_KEY && form.TMDB_API_KEY.length < 10) {
    errors.push('TMDB API Key 长度不足');
  }

  if (form.HTTP_PROXY && !/^https?:\/\/.+/.test(form.HTTP_PROXY)) {
    errors.push('HTTP Proxy 格式不正确，应以 http:// 或 https:// 开头');
  }

  if (
    form.LOG_LEVEL &&
    !['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'].includes(form.LOG_LEVEL.toUpperCase())
  ) {
    errors.push('LOG_LEVEL 必须是 DEBUG, INFO, WARNING, ERROR 或 CRITICAL 之一');
  }

  return { valid: errors.length === 0, errors };
}

async function submit() {
  const validation = validateSettings();
  if (!validation.valid) {
    validation.errors.forEach((err) => push(err, 'error'));
    return;
  }

  const payload: SettingsUpdate = {};

  const textKeys = [
    'LOG_LEVEL',
    'API_KEY',
    'TMDB_API_KEY',
    'HTTP_PROXY',
    'QUARK_TRANSFER_COOKIE',
  ] as const;
  textKeys.forEach((key) => {
    const value = String(form[key] || '').trim();
    if (value) payload[key] = value;
  });

  boolFields.forEach((key) => {
    payload[key] = form[key];
  });

  loading.value = true;
  try {
    const candidates = getApiKeyCandidates(String(form.API_KEY || '').trim());
    let res;

    if (candidates.length === 0) {
      res = await updateSettings(payload);
    } else {
      let lastError: unknown;

      for (const apiKey of candidates) {
        try {
          res = await updateSettingsWithApiKey(payload, apiKey);
          break;
        } catch (error) {
          lastError = error;
          if (!(error instanceof ApiError) || error.status !== 401) {
            throw error;
          }
        }
      }

      if (!res) {
        throw lastError instanceof Error ? lastError : new Error('保存失败');
      }
    }

    if (res.code !== 0) {
      push(res.message || '保存失败', 'error');
      return;
    }
    if (payload.API_KEY) {
      setConfiguredApiKey(payload.API_KEY);
    }
    const reloadResults = await Promise.allSettled([loadSettingsSnapshot(), refreshSystem()]);
    if (reloadResults.some((result) => result.status === 'rejected')) {
      push('配置已保存，但当前页面未能刷新最新状态', 'info');
    }
    push('配置已保存，请按提示重启后端服务', 'success', 3200);
  } catch (error) {
    push(error instanceof Error ? error.message : '保存失败', 'error');
  } finally {
    loading.value = false;
  }
}

async function refreshSystem() {
  const [healthResult, metricsResult] = await Promise.allSettled([getHealth(), getMetrics()]);

  if (healthResult.status === 'fulfilled') {
    const healthRes = healthResult.value;
    if (healthRes.code === 0) {
      health.value = healthRes.data.status;
      healthChecks.value = healthRes.data.checks ?? {};
    } else {
      health.value = 'error';
      healthChecks.value = {
        api: {
          status: 'error',
          message: healthRes.message || '健康检查失败',
        },
      };
    }
  } else {
    const message =
      healthResult.reason instanceof Error ? healthResult.reason.message : '无法读取系统健康状态';
    health.value = 'error';
    healthChecks.value = {
      service: {
        status: 'error',
        message,
      },
    };
  }

  if (metricsResult.status === 'fulfilled') {
    const metricsRes = metricsResult.value;
    if (metricsRes.code === 0) {
      metricsData.value = metricsRes.data;
      metricsSummary.value = `请求 ${metricsRes.data.requests.total} 次，平均 ${metricsRes.data.requests.avg_time}s`;
    } else {
      metricsData.value = null;
      metricsSummary.value = metricsRes.message || '无法读取系统指标';
    }
  } else {
    metricsData.value = null;
    metricsSummary.value =
      metricsResult.reason instanceof Error ? metricsResult.reason.message : '无法读取系统指标';
  }
}

async function initializePage() {
  const results = await Promise.allSettled([refreshSystem(), loadSettingsSnapshot()]);
  const settingsResult = results[1];
  if (settingsResult.status === 'rejected') {
    push(
      settingsResult.reason instanceof Error ? settingsResult.reason.message : '无法读取当前配置',
      'error'
    );
  }
}

onMounted(() => {
  void initializePage();
});
</script>

<template>
  <div class="settings-page">
    <!-- 页面头部 -->
    <header class="settings-header">
      <div class="header-content">
        <div class="header-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
            <path
              d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"
            />
          </svg>
        </div>
        <div class="header-text">
          <h1 class="header-title">系统设置</h1>
          <p class="header-subtitle">配置系统参数，优化您的使用体验</p>
        </div>
      </div>
      <button class="refresh-btn" :disabled="loading" @click="refreshSystem">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M23 4v6h-6M1 20v-6h6" />
          <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
        </svg>
        <span>刷新状态</span>
      </button>
    </header>

    <!-- 系统状态卡片 -->
    <section class="status-section">
      <div class="status-card">
        <div class="status-glow" :class="healthTone"></div>
        <div class="status-content">
          <div class="status-main">
            <div class="status-overview">
              <div class="status-indicator" :class="healthTone">
                <div class="indicator-dot"></div>
                <span class="indicator-text">{{ healthStatusLabel }}</span>
              </div>
              <p class="status-summary">{{ metricsSummary || '正在读取系统状态' }}</p>
              <ul v-if="healthIssues.length" class="status-issues">
                <li
                  v-for="issue in healthIssues"
                  :key="issue.key"
                  class="status-issue"
                  :class="issue.status"
                >
                  <span class="issue-label">{{ issue.label }}</span>
                  <span class="issue-message">{{ issue.message }}</span>
                </li>
              </ul>
              <p v-else class="status-details">
                {{ health === 'unknown' ? '正在读取健康检查结果' : '当前未发现异常检查项' }}
              </p>
            </div>
            <div class="status-metrics">
              <div class="metric-item">
                <div class="metric-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                  </svg>
                </div>
                <div class="metric-info">
                  <span class="metric-value">{{ metricsData?.requests.total ?? 0 }}</span>
                  <span class="metric-label">API 请求</span>
                </div>
              </div>
              <div class="metric-item">
                <div class="metric-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M12 6v6l4 2" />
                  </svg>
                </div>
                <div class="metric-info">
                  <span class="metric-value">{{ metricsData?.requests.avg_time ?? 0 }}s</span>
                  <span class="metric-label">平均响应</span>
                </div>
              </div>
              <div class="metric-item">
                <div class="metric-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <ellipse cx="12" cy="5" rx="9" ry="3" />
                    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
                    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
                  </svg>
                </div>
                <div class="metric-info">
                  <span class="metric-value">{{ metricsData?.database.total_queries ?? 0 }}</span>
                  <span class="metric-label">数据库查询</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 设置卡片组 -->
    <div class="settings-grid">
      <!-- 基础配置卡片 -->
      <section class="settings-card">
        <div class="card-header">
          <div class="card-icon api-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path
                d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"
              />
            </svg>
          </div>
          <div class="card-header-text">
            <h2 class="card-title">基础配置</h2>
            <p class="card-desc">API 密钥和网络代理设置</p>
          </div>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label class="form-label">
              <span class="label-text">日志级别</span>
              <span class="label-desc">控制日志输出详细程度</span>
            </label>
            <select v-model="form.LOG_LEVEL" class="form-select">
              <option value="">不修改</option>
              <option value="DEBUG">DEBUG - 调试</option>
              <option value="INFO">INFO - 信息</option>
              <option value="WARNING">WARNING - 警告</option>
              <option value="ERROR">ERROR - 错误</option>
            </select>
          </div>

          <div class="form-group">
            <label class="form-label">
              <span class="label-text">API 访问 Key</span>
              <span class="label-desc">{{ secretFieldHints.API_KEY }}</span>
            </label>
            <input
              v-model="form.API_KEY"
              type="text"
              class="form-input"
              :placeholder="secretFieldHints.API_KEY"
            />
          </div>

          <div class="form-group">
            <label class="form-label">
              <span class="label-text">TMDB API Key</span>
              <span class="label-desc">{{ secretFieldHints.TMDB_API_KEY }}</span>
            </label>
            <input
              v-model="form.TMDB_API_KEY"
              type="text"
              class="form-input"
              :placeholder="secretFieldHints.TMDB_API_KEY"
            />
          </div>

          <div class="form-group">
            <label class="form-label">
              <span class="label-text">HTTP 代理</span>
              <span class="label-desc">用于访问 TMDB 等国外服务</span>
            </label>
            <input
              v-model="form.HTTP_PROXY"
              type="text"
              class="form-input"
              placeholder="http://127.0.0.1:7890"
            />
          </div>

          <div class="form-group">
            <label class="form-label">
              <span class="label-text">夸克网盘 Cookie</span>
              <span class="label-desc">{{ secretFieldHints.QUARK_TRANSFER_COOKIE }}</span>
            </label>
            <textarea
              v-model="form.QUARK_TRANSFER_COOKIE"
              class="form-textarea"
              rows="3"
              :placeholder="secretFieldHints.QUARK_TRANSFER_COOKIE"
            />
          </div>
        </div>
      </section>

      <!-- 转存策略卡片 -->
      <section class="settings-card">
        <div class="card-header">
          <div class="card-icon transfer-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
            </svg>
          </div>
          <div class="card-header-text">
            <h2 class="card-title">转存策略</h2>
            <p class="card-desc">控制转存时的文件处理方式</p>
          </div>
        </div>
        <div class="card-body">
          <div class="toggle-item">
            <div class="toggle-info">
              <span class="toggle-title">保留额外文件</span>
              <span class="toggle-desc">保留 NFO、JPG 等元数据文件</span>
            </div>
            <ToggleSwitch v-model="form.TRANSFER_KEEP_EXTRAS" label="保留额外文件" />
          </div>

          <div class="toggle-item">
            <div class="toggle-info">
              <span class="toggle-title">保留字幕文件</span>
              <span class="toggle-desc">保留 SRT、ASS 等字幕文件</span>
            </div>
            <ToggleSwitch v-model="form.TRANSFER_KEEP_SUBTITLES" label="保留字幕文件" />
          </div>

          <div class="toggle-item">
            <div class="toggle-info">
              <span class="toggle-title">试运行模式</span>
              <span class="toggle-desc">只模拟操作，不实际执行转存</span>
            </div>
            <ToggleSwitch v-model="form.TRANSFER_DRY_RUN" label="试运行模式" />
          </div>
        </div>
      </section>

      <!-- 清理策略卡片 -->
      <section class="settings-card">
        <div class="card-header">
          <div class="card-icon cleanup-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path
                d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"
              />
              <line x1="10" y1="11" x2="10" y2="17" />
              <line x1="14" y1="11" x2="14" y2="17" />
            </svg>
          </div>
          <div class="card-header-text">
            <h2 class="card-title">清理策略</h2>
            <p class="card-desc">控制转存后的文件清理行为</p>
          </div>
        </div>
        <div class="card-body">
          <div class="toggle-item">
            <div class="toggle-info">
              <span class="toggle-title">启用清理</span>
              <span class="toggle-desc">转存完成后自动清理不需要的文件</span>
            </div>
            <ToggleSwitch v-model="form.TRANSFER_CLEANUP_ENABLED" label="启用清理" />
          </div>

          <div class="toggle-item">
            <div class="toggle-info">
              <span class="toggle-title">删除非视频文件</span>
              <span class="toggle-desc">删除图片、文档等非视频文件</span>
            </div>
            <ToggleSwitch v-model="form.TRANSFER_CLEANUP_DELETE_NON_VIDEO" label="删除非视频文件" />
          </div>

          <div class="toggle-item">
            <div class="toggle-info">
              <span class="toggle-title">删除未选视频</span>
              <span class="toggle-desc">删除未选择的高清/低清版本</span>
            </div>
            <ToggleSwitch
              v-model="form.TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO"
              label="删除未选视频"
            />
          </div>

          <div class="toggle-item">
            <div class="toggle-info">
              <span class="toggle-title">删除空目录</span>
              <span class="toggle-desc">删除清理后产生的空文件夹</span>
            </div>
            <ToggleSwitch v-model="form.TRANSFER_CLEANUP_DELETE_EMPTY_DIRS" label="删除空目录" />
          </div>
        </div>
      </section>
    </div>

    <!-- 保存按钮 -->
    <div class="settings-actions">
      <button class="save-btn" :disabled="loading" @click="submit">
        <svg v-if="!loading" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" />
          <polyline points="17 21 17 13 7 13 7 21" />
          <polyline points="7 3 7 8 15 8" />
        </svg>
        <div v-else class="loading-spinner"></div>
        <span>{{ loading ? '保存中...' : '保存配置' }}</span>
      </button>
      <p class="actions-hint">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
        保存后需要重启后端服务才能生效
      </p>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  min-height: 100vh;
  padding: calc(var(--site-header-height, 72px) + var(--spacing-12)) var(--spacing-6)
    var(--spacing-16);
  max-width: var(--container-2xl);
  margin: 0 auto;
}

/* 页面头部 */
.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-10);
  padding-bottom: var(--spacing-8);
  border-bottom: 1px solid var(--color-border-subtle);
}

.header-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-brand-gradient);
  border-radius: var(--radius-2xl);
  box-shadow: 0 var(--spacing-2) var(--spacing-6) var(--color-glow-brand);
}

.header-icon svg {
  width: 28px;
  height: 28px;
  color: white;
}

.header-title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-extrabold);
  background: var(--color-brand-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: var(--letter-spacing-tight);
}

.header-subtitle {
  margin: 4px 0 0;
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-full);
  color: var(--color-text-primary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.refresh-btn svg {
  width: 16px;
  height: 16px;
}

.refresh-btn:hover {
  background: var(--color-bg-elevated);
  border-color: var(--color-border-strong);
  transform: translateY(-1px);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

/* 系统状态卡片 */
.status-section {
  margin-bottom: var(--spacing-10);
}

.status-card {
  position: relative;
  background: linear-gradient(135deg, var(--color-bg-secondary) 0%, var(--color-bg-tertiary) 100%);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-6) var(--spacing-8);
  overflow: hidden;
}

.status-glow {
  position: absolute;
  top: -50%;
  right: -10%;
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, var(--color-glow-brand) 0%, transparent 70%);
  pointer-events: none;
  transition: background var(--transition-slow);
}

.status-glow.ok {
  background: radial-gradient(circle, rgba(34, 197, 94, 0.2) 0%, transparent 70%);
}

.status-glow.warning {
  background: radial-gradient(circle, rgba(245, 158, 11, 0.18) 0%, transparent 70%);
}

.status-content {
  position: relative;
  z-index: var(--z-index-base);
}

.status-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-6);
}

.status-overview {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--spacing-3);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-6);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-full);
  transition: all var(--transition-base);
}

.status-indicator.ok {
  background: rgba(34, 197, 94, 0.1);
  border-color: rgba(34, 197, 94, 0.3);
}

.status-indicator.warning {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.3);
}

.indicator-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-error);
  animation: pulse-dot 2s ease-in-out infinite;
}

.status-indicator.ok .indicator-dot {
  background: var(--color-success);
}

.status-indicator.warning .indicator-dot {
  background: var(--color-warning);
}

@keyframes pulse-dot {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.2);
    opacity: 0.7;
  }
}

.indicator-text {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.status-summary {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.status-details {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.status-issues {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.status-issue {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-default);
  background: rgba(255, 255, 255, 0.03);
}

.status-issue.error {
  border-color: rgba(239, 68, 68, 0.35);
  background: rgba(239, 68, 68, 0.08);
}

.status-issue.warning {
  border-color: rgba(245, 158, 11, 0.35);
  background: rgba(245, 158, 11, 0.08);
}

.issue-label {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
}

.issue-message {
  flex: 1;
  min-width: 220px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.status-metrics {
  display: flex;
  gap: var(--spacing-8);
}

.metric-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.metric-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-lg);
}

.metric-icon svg {
  width: 20px;
  height: 20px;
  color: var(--color-brand-primary);
}

.metric-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
}

.metric-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: var(--letter-spacing-wide);
}

/* 设置卡片网格 */
.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: var(--spacing-8);
  margin-bottom: var(--spacing-10);
}

/* 设置卡片 */
.settings-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-2xl);
  overflow: hidden;
  transition: all var(--transition-base);
  box-shadow: var(--shadow-md);
}

.settings-card:hover {
  border-color: var(--color-border-default);
  box-shadow: var(--shadow-lg);
  transform: translateY(-4px);
  background: var(--color-bg-tertiary);
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-5) var(--spacing-6);
  background: linear-gradient(135deg, var(--color-bg-tertiary) 0%, var(--color-bg-secondary) 100%);
  border-bottom: 1px solid var(--color-border-subtle);
}

.card-icon {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-xl);
  flex-shrink: 0;
}

.card-icon svg {
  width: 22px;
  height: 22px;
}

.api-icon {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(59, 130, 246, 0.1) 100%);
}

.api-icon svg {
  color: var(--color-info);
}

.transfer-icon {
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.2) 0%, rgba(34, 197, 94, 0.1) 100%);
}

.transfer-icon svg {
  color: var(--color-success);
}

.cleanup-icon {
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(245, 158, 11, 0.1) 100%);
}

.cleanup-icon svg {
  color: var(--color-warning);
}

.card-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
}

.card-desc {
  margin: 4px 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.card-body {
  padding: var(--spacing-6);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

/* 表单样式 */
.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.form-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.label-text {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.label-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.form-input,
.form-select,
.form-textarea {
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  transition: all var(--transition-fast);
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-brand-primary);
  box-shadow: 0 0 0 3px rgba(240, 90, 40, 0.15);
}

.form-input::placeholder,
.form-textarea::placeholder {
  color: var(--color-text-muted);
}

.form-select {
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23737373' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 36px;
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
  font-family: var(--font-family-mono);
}

/* 开关项 */
.toggle-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-4) 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.toggle-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.toggle-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.toggle-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.toggle-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

/* 保存按钮 */
.settings-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-8) 0;
}

.save-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-8);
  background: var(--color-brand-gradient);
  border: none;
  border-radius: var(--radius-full);
  color: white;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: all var(--transition-base);
  box-shadow: 0 var(--spacing-2) var(--spacing-6) var(--color-glow-brand);
}

.save-btn svg {
  width: 18px;
  height: 18px;
}

.save-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 var(--spacing-3) var(--spacing-8) var(--color-glow-brand);
}

.save-btn:active:not(:disabled) {
  transform: translateY(0);
}

.save-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.loading-spinner {
  width: 22px;
  height: 22px;
  border: 3px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.actions-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.actions-hint svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* 响应式 */
@media (max-width: 768px) {
  .settings-page {
    padding: calc(var(--site-header-height, 64px) + var(--spacing-4)) var(--spacing-4)
      var(--spacing-8);
  }

  .settings-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-4);
  }

  .header-title {
    font-size: var(--font-size-2xl);
  }

  .status-main {
    flex-direction: column;
    align-items: flex-start;
  }

  .status-metrics {
    flex-wrap: wrap;
    gap: var(--spacing-4);
  }

  .settings-grid {
    grid-template-columns: 1fr;
  }

  .toggle-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-3);
  }
}
</style>
