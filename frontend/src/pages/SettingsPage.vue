<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { getHealth, getMetrics, updateSettings } from "@/api";
import type { SettingsUpdate } from "@/types/api";
import { useToast } from "@/composables/useToast";

const { push } = useToast();

const loading = ref(false);
const health = ref("unknown");
const metricsSummary = ref("");

const form = reactive({
  LOG_LEVEL: "",
  TMDB_API_KEY: "",
  HTTP_PROXY: "",
  QUARK_TRANSFER_COOKIE: "",
  TRANSFER_KEEP_EXTRAS: "",
  TRANSFER_KEEP_SUBTITLES: "",
  TRANSFER_DRY_RUN: "",
  TRANSFER_CLEANUP_ENABLED: "",
  TRANSFER_CLEANUP_DELETE_NON_VIDEO: "",
  TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO: "",
  TRANSFER_CLEANUP_DELETE_EMPTY_DIRS: "",
});

type TextSettingKey = "LOG_LEVEL" | "TMDB_API_KEY" | "HTTP_PROXY" | "QUARK_TRANSFER_COOKIE";

function toBool(value: string): boolean | undefined {
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

async function submit() {
  const payload: SettingsUpdate = {};
  const textKeys: TextSettingKey[] = [
    "LOG_LEVEL",
    "TMDB_API_KEY",
    "HTTP_PROXY",
    "QUARK_TRANSFER_COOKIE",
  ];
  textKeys.forEach((key) => {
    const value = String(form[key] || "").trim();
    if (value) payload[key] = value;
  });

  payload.TRANSFER_KEEP_EXTRAS = toBool(form.TRANSFER_KEEP_EXTRAS);
  payload.TRANSFER_KEEP_SUBTITLES = toBool(form.TRANSFER_KEEP_SUBTITLES);
  payload.TRANSFER_DRY_RUN = toBool(form.TRANSFER_DRY_RUN);
  payload.TRANSFER_CLEANUP_ENABLED = toBool(form.TRANSFER_CLEANUP_ENABLED);
  payload.TRANSFER_CLEANUP_DELETE_NON_VIDEO = toBool(form.TRANSFER_CLEANUP_DELETE_NON_VIDEO);
  payload.TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO = toBool(form.TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO);
  payload.TRANSFER_CLEANUP_DELETE_EMPTY_DIRS = toBool(form.TRANSFER_CLEANUP_DELETE_EMPTY_DIRS);

  Object.keys(payload).forEach((key) => {
    const typedKey = key as keyof SettingsUpdate;
    if (payload[typedKey] === undefined) {
      delete payload[typedKey];
    }
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
      <span class="section-icon" aria-hidden="true">⚙️</span>
      <div>
        <h2 class="section-title" id="settings-title">系统设置</h2>
        <p>只提交你需要修改的字段，留空项不会被更新。</p>
      </div>
      <button class="btn btn-secondary" @click="refreshSystem">刷新系统状态</button>
    </div>

    <div class="status-strip">
      <span class="badge" :class="{ ok: health === 'ok', danger: health !== 'ok' }">服务状态: {{ health }}</span>
      <span>{{ metricsSummary }}</span>
    </div>

    <div class="settings-container">
      <p class="settings-desc">已配置的信息会以掩码显示。修改后保存才会更新。</p>
      <form class="settings-form" @submit.prevent="submit">
        <div class="settings-section">
          <h3 class="settings-section-title">基础配置</h3>
          <div class="form-group">
            <label>
              <span>LOG_LEVEL</span>
              <select v-model="form.LOG_LEVEL">
                <option value="">不修改</option>
                <option value="DEBUG">DEBUG</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>
            </label>
          </div>
          <div class="form-group">
            <label>
              <span>TMDB_API_KEY</span>
              <input v-model="form.TMDB_API_KEY" type="text" placeholder="留空则不修改" />
            </label>
          </div>
          <div class="form-group">
            <label>
              <span>HTTP_PROXY</span>
              <input v-model="form.HTTP_PROXY" type="text" placeholder="http://127.0.0.1:7890" />
            </label>
          </div>
          <div class="form-group">
            <label>
              <span>QUARK_TRANSFER_COOKIE</span>
              <textarea v-model="form.QUARK_TRANSFER_COOKIE" rows="3" placeholder="留空则不修改" />
            </label>
          </div>
        </div>

        <div class="settings-section">
          <h3 class="settings-section-title">转存与清理策略</h3>
          <div class="form-group">
            <label>
              <span>TRANSFER_KEEP_EXTRAS</span>
              <select v-model="form.TRANSFER_KEEP_EXTRAS">
                <option value="">不修改</option>
                <option value="true">开启</option>
                <option value="false">关闭</option>
              </select>
            </label>
          </div>
          <div class="form-group">
            <label>
              <span>TRANSFER_KEEP_SUBTITLES</span>
              <select v-model="form.TRANSFER_KEEP_SUBTITLES">
                <option value="">不修改</option>
                <option value="true">开启</option>
                <option value="false">关闭</option>
              </select>
            </label>
          </div>
          <div class="form-group">
            <label>
              <span>TRANSFER_DRY_RUN</span>
              <select v-model="form.TRANSFER_DRY_RUN">
                <option value="">不修改</option>
                <option value="true">开启</option>
                <option value="false">关闭</option>
              </select>
            </label>
          </div>
          <div class="form-group">
            <label>
              <span>TRANSFER_CLEANUP_ENABLED</span>
              <select v-model="form.TRANSFER_CLEANUP_ENABLED">
                <option value="">不修改</option>
                <option value="true">开启</option>
                <option value="false">关闭</option>
              </select>
            </label>
          </div>
          <div class="form-group">
            <label>
              <span>TRANSFER_CLEANUP_DELETE_NON_VIDEO</span>
              <select v-model="form.TRANSFER_CLEANUP_DELETE_NON_VIDEO">
                <option value="">不修改</option>
                <option value="true">开启</option>
                <option value="false">关闭</option>
              </select>
            </label>
          </div>
          <div class="form-group">
            <label>
              <span>TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO</span>
              <select v-model="form.TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO">
                <option value="">不修改</option>
                <option value="true">开启</option>
                <option value="false">关闭</option>
              </select>
            </label>
          </div>
          <div class="form-group">
            <label>
              <span>TRANSFER_CLEANUP_DELETE_EMPTY_DIRS</span>
              <select v-model="form.TRANSFER_CLEANUP_DELETE_EMPTY_DIRS">
                <option value="">不修改</option>
                <option value="true">开启</option>
                <option value="false">关闭</option>
              </select>
            </label>
          </div>
        </div>

        <div class="settings-actions form-actions">
          <button class="btn btn-primary" :disabled="loading" type="submit">
            {{ loading ? "保存中..." : "保存配置" }}
          </button>
        </div>
      </form>
    </div>
  </section>
  </div>
</template>
