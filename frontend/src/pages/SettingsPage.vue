<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { getHealth, getMetrics, updateSettings } from "@/api";
import ToggleSwitch from "@/components/ToggleSwitch.vue";
import type { SettingsUpdate } from "@/types/api";
import { useToast } from "@/composables/useToast";

const { push } = useToast();

const loading = ref(false);
const health = ref("unknown");
const metricsSummary = ref("");
const metricsData = ref<{
  requests: { total: number; avg_time: number };
  database: { total_queries: number; avg_time: number };
} | null>(null);

const form = reactive({
  LOG_LEVEL: "",
  TMDB_API_KEY: "",
  HTTP_PROXY: "",
  QUARK_TRANSFER_COOKIE: "",
  TRANSFER_KEEP_EXTRAS: false,
  TRANSFER_KEEP_SUBTITLES: false,
  TRANSFER_DRY_RUN: false,
  TRANSFER_CLEANUP_ENABLED: false,
  TRANSFER_CLEANUP_DELETE_NON_VIDEO: false,
  TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO: false,
  TRANSFER_CLEANUP_DELETE_EMPTY_DIRS: false,
});

const boolFields = [
  "TRANSFER_KEEP_EXTRAS",
  "TRANSFER_KEEP_SUBTITLES",
  "TRANSFER_DRY_RUN",
  "TRANSFER_CLEANUP_ENABLED",
  "TRANSFER_CLEANUP_DELETE_NON_VIDEO",
  "TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO",
  "TRANSFER_CLEANUP_DELETE_EMPTY_DIRS",
] as const;

type BoolField = (typeof boolFields)[number];

function validateSettings(): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  
  if (form.TMDB_API_KEY && form.TMDB_API_KEY.length < 10) {
    errors.push("TMDB API Key 长度不足");
  }
  
  if (form.HTTP_PROXY && !/^https?:\/\/.+/.test(form.HTTP_PROXY)) {
    errors.push("HTTP Proxy 格式不正确，应以 http:// 或 https:// 开头");
  }
  
  if (form.LOG_LEVEL && !["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].includes(form.LOG_LEVEL.toUpperCase())) {
    errors.push("LOG_LEVEL 必须是 DEBUG, INFO, WARNING, ERROR 或 CRITICAL 之一");
  }
  
  return { valid: errors.length === 0, errors };
}

async function submit() {
  const validation = validateSettings();
  if (!validation.valid) {
    validation.errors.forEach(err => push(err, "error"));
    return;
  }
  
  const payload: SettingsUpdate = {};

  const textKeys = ["LOG_LEVEL", "TMDB_API_KEY", "HTTP_PROXY", "QUARK_TRANSFER_COOKIE"] as const;
  textKeys.forEach((key) => {
    const value = String(form[key] || "").trim();
    if (value) payload[key] = value;
  });

  boolFields.forEach((key) => {
    payload[key] = form[key];
  });

  loading.value = true;
  try {
    const res = await updateSettings(payload);
    if (res.code !== 0) {
      push(res.message || "保存失败", "error");
      return;
    }
    push("配置已保存，请按提示重启后端服务", "success", 3200);
  } catch (error) {
    push(error instanceof Error ? error.message : "保存失败", "error");
  } finally {
    loading.value = false;
  }
}

async function refreshSystem() {
  try {
    const [healthRes, metricsRes] = await Promise.all([getHealth(), getMetrics()]);
    health.value = healthRes.code === 0 ? healthRes.data.status : "error";
    if (metricsRes.code === 0) {
      metricsData.value = metricsRes.data;
      metricsSummary.value = `请求 ${metricsRes.data.requests.total} 次，平均 ${metricsRes.data.requests.avg_time}s`;
    } else {
      metricsSummary.value = metricsRes.message;
    }
  } catch {
    health.value = "error";
    metricsSummary.value = "无法读取系统状态";
  }
}

onMounted(() => {
  void refreshSystem();
});
</script>

<template>
  <div class="page">
    <section class="section" aria-labelledby="settings-title">
      <div class="section-header">
        <div>
          <h2 class="section-title" id="settings-title">系统设置</h2>
          <p class="section-desc">配置系统参数，修改后保存生效</p>
        </div>
        <button class="btn btn-secondary" :disabled="loading" @click="refreshSystem">
          刷新状态
        </button>
      </div>

      <!-- 系统状态卡片 -->
      <div class="settings-card status-card">
        <div class="card-header">
          <h3 class="card-title">系统状态</h3>
        </div>
        <div class="card-body">
          <div class="status-grid">
            <div class="status-item">
              <span class="status-label">服务状态</span>
              <span class="status-value">
                <span class="status-badge" :class="{ ok: health === 'ok', danger: health !== 'ok' }">
                  {{ health === 'ok' ? '运行中' : '异常' }}
                </span>
              </span>
            </div>
            <div class="status-item">
              <span class="status-label">API 请求</span>
              <span class="status-value">{{ metricsData?.requests.total ?? 0 }} 次</span>
            </div>
            <div class="status-item">
              <span class="status-label">平均响应</span>
              <span class="status-value">{{ metricsData?.requests.avg_time ?? 0 }}s</span>
            </div>
            <div class="status-item">
              <span class="status-label">数据库查询</span>
              <span class="status-value">{{ metricsData?.database.total_queries ?? 0 }} 次</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 基础配置卡片 -->
      <div class="settings-card">
        <div class="card-header">
          <h3 class="card-title">基础配置</h3>
          <p class="card-desc">API 密钥和网络代理设置</p>
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
              <span class="label-text">TMDB API Key</span>
              <span class="label-desc">The Movie Database API 密钥，用于获取影片信息</span>
            </label>
            <input
              v-model="form.TMDB_API_KEY"
              type="text"
              class="form-input"
              placeholder="留空则不修改"
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
              <span class="label-desc">用于访问夸克网盘 API，从浏览器开发者工具获取</span>
            </label>
            <textarea
              v-model="form.QUARK_TRANSFER_COOKIE"
              class="form-textarea"
              rows="3"
              placeholder="留空则不修改"
            />
          </div>
        </div>
      </div>

      <!-- 转存策略卡片 -->
      <div class="settings-card">
        <div class="card-header">
          <h3 class="card-title">转存策略</h3>
          <p class="card-desc">控制转存时的文件处理方式</p>
        </div>
        <div class="card-body">
          <div class="form-group toggle-group">
            <label class="form-label">
              <span class="label-text">保留额外文件</span>
              <span class="label-desc">保留 NFO、JPG 等元数据文件</span>
            </label>
            <ToggleSwitch v-model="form.TRANSFER_KEEP_EXTRAS" label="保留额外文件" />
          </div>

          <div class="form-group toggle-group">
            <label class="form-label">
              <span class="label-text">保留字幕文件</span>
              <span class="label-desc">保留 SRT、ASS 等字幕文件</span>
            </label>
            <ToggleSwitch v-model="form.TRANSFER_KEEP_SUBTITLES" label="保留字幕文件" />
          </div>

          <div class="form-group toggle-group">
            <label class="form-label">
              <span class="label-text">试运行模式</span>
              <span class="label-desc">只模拟操作，不实际执行转存</span>
            </label>
            <ToggleSwitch v-model="form.TRANSFER_DRY_RUN" label="试运行模式" />
          </div>
        </div>
      </div>

      <!-- 清理策略卡片 -->
      <div class="settings-card">
        <div class="card-header">
          <h3 class="card-title">清理策略</h3>
          <p class="card-desc">控制转存后的文件清理行为</p>
        </div>
        <div class="card-body">
          <div class="form-group toggle-group">
            <label class="form-label">
              <span class="label-text">启用清理</span>
              <span class="label-desc">转存完成后自动清理不需要的文件</span>
            </label>
            <ToggleSwitch v-model="form.TRANSFER_CLEANUP_ENABLED" label="启用清理" />
          </div>

          <div class="form-group toggle-group">
            <label class="form-label">
              <span class="label-text">删除非视频文件</span>
              <span class="label-desc">删除图片、文档等非视频文件</span>
            </label>
            <ToggleSwitch v-model="form.TRANSFER_CLEANUP_DELETE_NON_VIDEO" label="删除非视频文件" />
          </div>

          <div class="form-group toggle-group">
            <label class="form-label">
              <span class="label-text">删除未选视频</span>
              <span class="label-desc">删除未选择的高清/低清版本</span>
            </label>
            <ToggleSwitch v-model="form.TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO" label="删除未选视频" />
          </div>

          <div class="form-group toggle-group">
            <label class="form-label">
              <span class="label-text">删除空目录</span>
              <span class="label-desc">删除清理后产生的空文件夹</span>
            </label>
            <ToggleSwitch v-model="form.TRANSFER_CLEANUP_DELETE_EMPTY_DIRS" label="删除空目录" />
          </div>
        </div>
      </div>

      <!-- 保存按钮 -->
      <div class="settings-actions">
        <button class="btn btn-primary btn-lg" :disabled="loading" @click="submit">
          {{ loading ? "保存中..." : "保存配置" }}
        </button>
        <p class="actions-hint">保存后需要重启后端服务才能生效</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.section-desc {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.settings-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-xl);
  margin-bottom: var(--spacing-6);
  overflow: hidden;
}

.card-header {
  padding: var(--spacing-5) var(--spacing-6);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-tertiary);
}

.card-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.card-desc {
  margin: var(--spacing-2) 0 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.card-body {
  padding: var(--spacing-6);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

/* 状态卡片 */
.status-card .card-body {
  padding: var(--spacing-4) var(--spacing-5);
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--spacing-4);
}

.status-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.status-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: var(--letter-spacing-wide);
}

.status-value {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.status-badge.ok {
  background: var(--color-success);
  color: var(--color-text-primary);
}

.status-badge.danger {
  background: var(--color-error);
  color: var(--color-text-primary);
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
  gap: var(--spacing-1);
}

.label-text {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
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
  font-size: var(--font-size-base);
  transition: all var(--transition-fast);
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-brand-primary);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1);
}

.form-input::placeholder,
.form-textarea::placeholder {
  color: var(--color-text-muted);
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
}

/* 开关组 */
.toggle-group {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3) 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.toggle-group:last-child {
  border-bottom: none;
}

/* 操作按钮 */
.settings-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-6) 0;
}

.btn-lg {
  padding: var(--spacing-4) var(--spacing-8);
  font-size: var(--font-size-lg);
}

.actions-hint {
  margin: 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

/* 响应式 */
@media (max-width: 767px) {
  .status-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .toggle-group {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-3);
  }
}
</style>
