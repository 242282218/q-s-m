<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import {
  deleteCollection,
  getCollections,
  getTmdbDetails,
  startRenameSse,
  startVerifySse,
  transferCollection,
  verifySingleCollection,
} from "@/api";
import EventLogModal from "@/components/EventLogModal.vue";
import PaginationBar from "@/components/PaginationBar.vue";
import { useToast } from "@/composables/useToast";
import type { CollectionItem, Pagination, SseEventData } from "@/types/api";

const { push } = useToast();

const SILENT_VERIFY_COOLDOWN_MS = 10 * 60 * 1000;

const items = ref<CollectionItem[]>([]);
const loading = ref(false);
const busyAction = reactive<Record<number, string>>({});
const pageSize = 20;
const pagination = ref<Pagination>({
  page: 1,
  page_size: pageSize,
  total: 0,
  total_pages: 0,
});

const modalVisible = ref(false);
const modalTitle = ref("任务日志");
const modalProgress = ref(0);
const modalCounter = ref("0/0");
const modalSummary = ref("");
const modalLines = ref<Array<{ level: string; text: string }>>([]);
const taskBusy = ref(false);
let currentController: AbortController | null = null;
let lastSilentVerifyAt = 0;

const totalText = computed(() => `${pagination.value.total} 条收藏`);

function numberOrNull(value: unknown): number | null {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function resetModal(title: string) {
  modalTitle.value = title;
  modalProgress.value = 0;
  modalCounter.value = "0/0";
  modalSummary.value = "";
  modalLines.value = [];
  modalVisible.value = true;
}

function appendLine(level: string, text: string) {
  modalLines.value.push({ level, text });
}

function applyProgress(event: SseEventData) {
  const current = numberOrNull(event.current) ?? 0;
  const total = numberOrNull(event.total) ?? 0;
  const percentage = numberOrNull(event.percentage);
  const safePercentage =
    percentage !== null ? Math.max(0, Math.min(100, percentage)) : total > 0 ? Math.round((current / total) * 100) : 0;
  modalProgress.value = safePercentage;
  modalCounter.value = `${current}/${total}`;
}

function finishProgress(event: SseEventData) {
  const total = numberOrNull(event.total) ?? numberOrNull(event.current) ?? 0;
  modalProgress.value = 100;
  modalCounter.value = `${total}/${total}`;
}

function patchItemStatus(collectionId: number, status: number) {
  const found = items.value.find((it) => it.id === collectionId);
  if (found) {
    found.status = status;
  }
}

function patchItemPoster(
  collectionId: number,
  patch: { poster_path?: string | null; backdrop_path?: string | null },
) {
  const found = items.value.find((it) => it.id === collectionId);
  if (!found) {
    return;
  }
  if (patch.poster_path) {
    found.poster_path = patch.poster_path;
  }
  if (patch.backdrop_path && !found.backdrop_path) {
    found.backdrop_path = patch.backdrop_path;
  }
}

function setSummaryByStats(event: SseEventData) {
  const renameSuccess = numberOrNull(event.success);
  const renameSkipped = numberOrNull(event.skipped);
  const renameFailed = numberOrNull(event.failed);
  if (renameSkipped !== null && renameFailed !== null) {
    modalSummary.value = `完成汇总：成功 ${renameSuccess ?? 0} 个，跳过 ${renameSkipped} 个，失败 ${renameFailed} 个`;
    return;
  }

  const exists = numberOrNull(event.exists);
  const deleted = numberOrNull(event.deleted);
  const verifyFailed = numberOrNull(event.failed);
  if (exists !== null && deleted !== null && verifyFailed !== null) {
    modalSummary.value = `完成汇总：存在 ${exists} 个，已删除 ${deleted} 个，失败 ${verifyFailed} 个`;
    return;
  }

  modalSummary.value = String(event.message || "任务完成");
}

function onSseEvent(event: SseEventData) {
  if (!event || typeof event !== "object") {
    return;
  }

  const type = String(event.type || "log");
  const level = String(event.level || "info");
  applyProgress(event);

  const collectionId = numberOrNull(event.collection_id);
  const currentStatus = numberOrNull(event.current_status);
  if (collectionId !== null && currentStatus !== null) {
    patchItemStatus(collectionId, currentStatus);
  }

  if (type === "log") {
    appendLine(level, String(event.message || ""));
    return;
  }

  if (type === "progress") {
    return;
  }

  if (type === "complete") {
    finishProgress(event);
    appendLine("info", String(event.message || "任务完成"));
    setSummaryByStats(event);
    push("任务执行完成", "success");
    return;
  }

  if (type === "error") {
    const message = String(event.message || "任务失败");
    appendLine("error", message);
    modalSummary.value = message;
    push(message, "error");
  }
}

function statusLabel(status: number) {
  if (status === 1) return "已转存";
  if (status === 2) return "已失效";
  if (status === 3) return "网盘已删除";
  return "未转存";
}

function posterUrl(item: CollectionItem) {
  if (!item.poster_path) return "";
  return `https://image.tmdb.org/t/p/w300${item.poster_path}`;
}

function setBusy(id: number, value: string | null) {
  if (value) {
    busyAction[id] = value;
  } else {
    delete busyAction[id];
  }
}

async function fillMissingPosters(targetItems: CollectionItem[]) {
  const missing = targetItems.filter((item) => !item.poster_path && item.tmdb_id > 0);
  if (missing.length === 0) {
    return;
  }

  let cursor = 0;
  const workers = Array.from({ length: Math.min(4, missing.length) }, async () => {
    while (cursor < missing.length) {
      const index = cursor;
      cursor += 1;
      const item = missing[index];
      try {
        const res = await getTmdbDetails(item.media_type, item.tmdb_id);
        if (res.code === 0 && (res.data.poster_path || res.data.backdrop_path)) {
          patchItemPoster(item.id, {
            poster_path: res.data.poster_path,
            backdrop_path: res.data.backdrop_path,
          });
        }
      } catch {
        // Ignore per-item failures.
      }
    }
  });

  await Promise.all(workers);
}

function shouldRunSilentVerify() {
  if (taskBusy.value) {
    return false;
  }
  return Date.now() - lastSilentVerifyAt >= SILENT_VERIFY_COOLDOWN_MS;
}

async function silentVerifyCollections(targetItems: CollectionItem[]) {
  if (!shouldRunSilentVerify()) {
    return;
  }

  const ids = targetItems
    .filter((item) => item.status === 1)
    .map((item) => item.id)
    .filter((id) => Number.isFinite(id));
  if (ids.length === 0) {
    return;
  }
  lastSilentVerifyAt = Date.now();

  let cursor = 0;
  const workers = Array.from({ length: Math.min(3, ids.length) }, async () => {
    while (cursor < ids.length) {
      const index = cursor;
      cursor += 1;
      const id = ids[index];
      try {
        const res = await verifySingleCollection(id);
        if (res.code === 0) {
          patchItemStatus(res.data.result.collection_id, res.data.result.current_status);
        }
      } catch {
        // Ignore per-item failures.
      }
    }
  });

  await Promise.all(workers);
}

async function loadCollections(page = 1) {
  loading.value = true;
  try {
    const res = await getCollections(page, pageSize);
    if (res.code !== 0) {
      push(res.message || "加载收藏失败", "error");
      return;
    }
    items.value = res.data.items;
    pagination.value = res.data.pagination;
    await fillMissingPosters(items.value);
    void silentVerifyCollections(items.value);
  } catch (error) {
    push(error instanceof Error ? error.message : "加载收藏失败", "error");
  } finally {
    loading.value = false;
  }
}

async function onDelete(item: CollectionItem) {
  if (!window.confirm(`确定删除「${item.title}」？`)) {
    return;
  }
  setBusy(item.id, "delete");
  try {
    const res = await deleteCollection(item.id);
    if (res.code !== 0 || !res.data.deleted) {
      push(res.message || "删除失败", "error");
      return;
    }
    push("删除成功", "success");
    await loadCollections(pagination.value.page);
  } catch (error) {
    push(error instanceof Error ? error.message : "删除失败", "error");
  } finally {
    setBusy(item.id, null);
  }
}

async function onTransfer(item: CollectionItem) {
  setBusy(item.id, "transfer");
  try {
    const res = await transferCollection({ collection_id: item.id });
    if (res.code !== 0 || !res.data.success) {
      push(res.message || "转存失败", "error");
      return;
    }
    push("转存成功", "success");
    await loadCollections(pagination.value.page);
  } catch (error) {
    push(error instanceof Error ? error.message : "转存失败", "error");
  } finally {
    setBusy(item.id, null);
  }
}

async function onVerifySingle(item: CollectionItem) {
  setBusy(item.id, "verify");
  try {
    const res = await verifySingleCollection(item.id);
    if (res.code !== 0) {
      push(res.message || "验证失败", "error");
      return;
    }
    patchItemStatus(res.data.result.collection_id, res.data.result.current_status);
    push("单条验证完成", "info");
  } catch (error) {
    push(error instanceof Error ? error.message : "验证失败", "error");
  } finally {
    setBusy(item.id, null);
  }
}

async function onRename(item: CollectionItem) {
  if (taskBusy.value) {
    push("已有任务进行中", "info");
    return;
  }

  resetModal(`重命名任务 - ${item.title}`);
  appendLine("info", `开始重命名: ${item.title}`);
  taskBusy.value = true;
  setBusy(item.id, "rename");
  currentController = new AbortController();

  try {
    await startRenameSse(
      { collection_id: item.id },
      (envelope) => {
        if (envelope.code !== 0) {
          const message = envelope.message || "任务失败";
          appendLine("error", message);
          modalSummary.value = message;
          push(message, "error");
          return;
        }
        onSseEvent(envelope.data);
      },
      currentController.signal,
    );
  } catch (error) {
    const message =
      error instanceof DOMException && error.name === "AbortError"
        ? "任务已中断"
        : error instanceof Error
          ? error.message
          : "任务中断";
    appendLine("error", message);
    modalSummary.value = message;
  } finally {
    taskBusy.value = false;
    setBusy(item.id, null);
    currentController = null;
    await loadCollections(pagination.value.page);
  }
}

async function onVerifyAll() {
  if (taskBusy.value) {
    push("已有任务进行中", "info");
    return;
  }

  resetModal("网盘状态验证");
  appendLine("info", "开始验证网盘状态");
  taskBusy.value = true;
  currentController = new AbortController();

  try {
    await startVerifySse(
      {},
      (envelope) => {
        if (envelope.code !== 0) {
          const message = envelope.message || "任务失败";
          appendLine("error", message);
          modalSummary.value = message;
          push(message, "error");
          return;
        }
        onSseEvent(envelope.data);
      },
      currentController.signal,
    );
  } catch (error) {
    const message =
      error instanceof DOMException && error.name === "AbortError"
        ? "任务已中断"
        : error instanceof Error
          ? error.message
          : "任务中断";
    appendLine("error", message);
    modalSummary.value = message;
  } finally {
    taskBusy.value = false;
    currentController = null;
    await loadCollections(pagination.value.page);
  }
}

function closeModal() {
  if (taskBusy.value && currentController) {
    const shouldStop = window.confirm("任务仍在执行，确认中断并关闭？");
    if (!shouldStop) {
      return;
    }
    currentController.abort();
  }
  modalVisible.value = false;
}

onMounted(() => {
  void loadCollections(1);
});
</script>

<template>
  <div class="page">
    <section class="section" aria-labelledby="collection-title">
      <div class="section-header collection-header">
        <span class="section-icon" aria-hidden="true">⭐</span>
        <h2 class="section-title" id="collection-title">我的收藏</h2>
        <div class="collection-actions">
          <button class="btn btn-secondary" :disabled="loading || taskBusy" @click="loadCollections(pagination.page)">
            刷新
          </button>
          <button class="btn btn-primary collection-verify-btn" :disabled="loading || taskBusy" @click="onVerifyAll">
            验证网盘状态
          </button>
        </div>
        <span class="collection-count" aria-live="polite">{{ totalText }}</span>
      </div>

      <div v-if="loading" class="loading" role="status" aria-label="加载中">
        <div class="loading-spinner" aria-hidden="true" />
        <span>加载中...</span>
      </div>

      <div v-else-if="items.length === 0" class="empty" role="status">
        <div class="empty-icon">📌</div>
        <div class="empty-text">暂无收藏</div>
        <div class="empty-hint">在影片详情页点击“收藏”按钮添加收藏</div>
        <a href="/" class="btn btn-primary">浏览影片</a>
      </div>

      <div v-else class="posters-grid" role="list">
        <article v-for="item in items" :key="item.id" class="poster-card" role="listitem">
          <button class="delete-btn" :disabled="!!busyAction[item.id] || taskBusy" @click.stop="onDelete(item)">×</button>
          <button class="transfer-btn" :disabled="!!busyAction[item.id] || taskBusy" @click.stop="onTransfer(item)">📜</button>
          <button
            class="rename-btn"
            :class="{ 'is-disabled': item.status !== 1 }"
            :disabled="!!busyAction[item.id] || taskBusy || item.status !== 1"
            @click.stop="onRename(item)"
          >
            <span
              v-if="busyAction[item.id] === 'rename'"
              class="loading-spinner"
              style="width: 16px; height: 16px; border-width: 2px; margin: 0"
            />
            <template v-else>✏️</template>
          </button>
          <a :href="`/${item.media_type}/${item.tmdb_id}`" :aria-label="`${item.title} - ${item.year || '未知年份'}`">
            <div class="poster-media">
              <img v-if="posterUrl(item)" :src="posterUrl(item)" :alt="item.title" loading="lazy" decoding="async" />
              <div v-else class="poster-skeleton" aria-hidden="true" />
              <div class="poster-gradient" aria-hidden="true" />
              <div class="status-badges">
                <span class="status-badge saved">已收藏</span>
                <span
                  class="status-badge transfer-status"
                  :class="{
                    transferred: item.status === 1,
                    expired: item.status === 2,
                    deleted: item.status === 3,
                    'not-transferred': item.status === 0,
                  }"
                >
                  {{ statusLabel(item.status) }}
                </span>
              </div>
            </div>
            <div class="poster-text">
              <div class="poster-title">{{ item.title }}</div>
              <div class="poster-subtitle">{{ item.year || "未知年份" }}</div>
            </div>
          </a>
          <div class="collection-inline-actions">
            <button class="btn btn-secondary" :disabled="!!busyAction[item.id] || taskBusy" @click.stop="onVerifySingle(item)">
              验证
            </button>
          </div>
        </article>
      </div>

      <PaginationBar :pagination="pagination" :loading="loading" @change="loadCollections" />
    </section>

    <EventLogModal
      :visible="modalVisible"
      :title="modalTitle"
      :progress="modalProgress"
      :counter="modalCounter"
      :summary="modalSummary"
      :lines="modalLines"
      :busy="taskBusy"
      @close="closeModal"
    />
  </div>
</template>
