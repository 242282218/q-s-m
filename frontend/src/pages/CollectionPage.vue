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
import CollectionDetailModal from "@/components/CollectionDetailModal.vue";
import EventLogModal from "@/components/EventLogModal.vue";
import PaginationBar from "@/components/PaginationBar.vue";
import { useToast } from "@/composables/useToast";
import type { CollectionItem, Pagination, SseEventData } from "@/types/api";

const { push } = useToast();

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

// 详情弹窗状态
const detailModalVisible = ref(false);
const selectedItem = ref<CollectionItem | null>(null);

// 任务日志弹窗状态
const modalVisible = ref(false);
const modalTitle = ref("任务日志");
const modalProgress = ref(0);
const modalCounter = ref("0/0");
const modalSummary = ref("");
const modalLines = ref<Array<{ level: string; text: string }>>([]);
const taskBusy = ref(false);
const currentController = ref<AbortController | null>(null);

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

  const queue = [...missing];
  const concurrency = Math.min(4, queue.length);

  const workers = Array.from({ length: concurrency }, async () => {
    while (queue.length > 0) {
      const item = queue.shift();
      if (!item) break;
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
    // 后台静默填充缺失的海报，不阻塞渲染
    void fillMissingPosters(items.value);
  } catch (error) {
    push(error instanceof Error ? error.message : "加载收藏失败", "error");
  } finally {
    loading.value = false;
  }
}

// 打开详情弹窗
function openDetailModal(item: CollectionItem) {
  selectedItem.value = item;
  detailModalVisible.value = true;
}

// 关闭详情弹窗
function closeDetailModal() {
  detailModalVisible.value = false;
  selectedItem.value = null;
}

function removeItemFromList(collectionId: number) {
  const index = items.value.findIndex((it) => it.id === collectionId);
  if (index !== -1) {
    items.value.splice(index, 1);
    pagination.value.total = Math.max(0, pagination.value.total - 1);
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
    closeDetailModal();
    removeItemFromList(item.id);
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
    closeDetailModal();
    patchItemStatus(item.id, 1);
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

  closeDetailModal();
  resetModal(`重命名任务 - ${item.title}`);
  appendLine("info", `开始重命名: ${item.title}`);
  taskBusy.value = true;
  setBusy(item.id, "rename");
  currentController.value = new AbortController();

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
      currentController.value.signal,
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
    currentController.value = null;
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
  currentController.value = new AbortController();

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
      currentController.value.signal,
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
    currentController.value = null;
  }
}

function closeModal() {
  if (taskBusy.value && currentController.value) {
    const shouldStop = window.confirm("任务仍在执行，确认中断并关闭？");
    if (!shouldStop) {
      return;
    }
    currentController.value.abort();
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
        <div class="empty-hint">在影片详情页点击"收藏"按钮添加收藏</div>
        <a href="/" class="btn btn-primary">浏览影片</a>
      </div>

      <div v-else class="posters-grid" role="list">
        <article
          v-for="item in items"
          :key="item.id"
          class="poster-card collection-card"
          role="listitem"
          @click="openDetailModal(item)"
        >
          <div class="poster-media">
            <img v-if="posterUrl(item)" :src="posterUrl(item)" :alt="item.title" loading="lazy" decoding="async" />
            <div v-else class="poster-skeleton" aria-hidden="true" />
            <div class="poster-gradient" aria-hidden="true" />

            <!-- 状态标签 -->
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

            <!-- 悬停操作栏 -->
            <div class="card-actions-overlay">
              <div class="card-actions">
                <button
                  class="card-action-btn"
                  :class="{ 'is-busy': busyAction[item.id] === 'transfer' }"
                  :disabled="!!busyAction[item.id] || taskBusy"
                  @click.stop="onTransfer(item)"
                  title="转存"
                >
                  <span v-if="busyAction[item.id] === 'transfer'" class="action-spinner" />
                  <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 5v14M19 12l-7 7-7-7" />
                  </svg>
                </button>

                <button
                  class="card-action-btn"
                  :class="{ 'is-disabled': item.status !== 1, 'is-busy': busyAction[item.id] === 'rename' }"
                  :disabled="!!busyAction[item.id] || taskBusy || item.status !== 1"
                  @click.stop="onRename(item)"
                  title="重命名"
                >
                  <span v-if="busyAction[item.id] === 'rename'" class="action-spinner" />
                  <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>

                <button
                  class="card-action-btn"
                  :class="{ 'is-busy': busyAction[item.id] === 'verify' }"
                  :disabled="!!busyAction[item.id] || taskBusy"
                  @click.stop="onVerifySingle(item)"
                  title="验证"
                >
                  <span v-if="busyAction[item.id] === 'verify'" class="action-spinner" />
                  <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M9 12l2 2 4-4" />
                    <circle cx="12" cy="12" r="10" />
                  </svg>
                </button>

                <button
                  class="card-action-btn danger"
                  :class="{ 'is-busy': busyAction[item.id] === 'delete' }"
                  :disabled="!!busyAction[item.id] || taskBusy"
                  @click.stop="onDelete(item)"
                  title="删除"
                >
                  <span v-if="busyAction[item.id] === 'delete'" class="action-spinner" />
                  <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <div class="poster-text">
            <div class="poster-title">{{ item.title }}</div>
            <div class="poster-subtitle">{{ item.year || "未知年份" }}</div>
          </div>
        </article>
      </div>

      <PaginationBar :pagination="pagination" :loading="loading" @change="loadCollections" />
    </section>

    <!-- 详情弹窗 -->
    <CollectionDetailModal
      :visible="detailModalVisible"
      :item="selectedItem"
      :busy-action="selectedItem ? busyAction[selectedItem.id] || null : null"
      :task-busy="taskBusy"
      @close="closeDetailModal"
      @delete="onDelete"
      @transfer="onTransfer"
      @verify="onVerifySingle"
      @rename="onRename"
    />

    <!-- 任务日志弹窗 -->
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

<style scoped>
/* 收藏卡片特殊样式 */
.collection-card {
  cursor: pointer;
}

/* 悬停操作栏遮罩 */
.card-actions-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  opacity: 0;
  transition: opacity var(--transition-base);
  border-radius: var(--radius-xl);
}

.collection-card:hover .card-actions-overlay {
  opacity: 1;
}

/* 操作按钮组 */
.card-actions {
  display: flex;
  gap: var(--spacing-2);
  transform: translateY(10px);
  transition: transform var(--transition-slow);
  padding: var(--spacing-2);
}

.collection-card:hover .card-actions {
  transform: translateY(0);
}

/* 操作按钮 */
.card-action-btn {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  backdrop-filter: blur(4px);
  flex-shrink: 0;
}

.card-action-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.4);
  transform: scale(1.05);
}

.card-action-btn:active:not(:disabled) {
  transform: scale(0.95);
}

.card-action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.card-action-btn.is-disabled {
  background: rgba(115, 115, 115, 0.3);
  color: var(--color-text-muted);
}

.card-action-btn.danger {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.4);
  color: var(--color-error);
}

.card-action-btn.danger:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.3);
  border-color: var(--color-error);
}

/* 加载动画 */
.action-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: currentColor;
  border-radius: var(--radius-full);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 移动端适配 */
@media (max-width: 767px) {
  .card-actions-overlay {
    opacity: 1;
    background: linear-gradient(180deg, transparent 50%, rgba(0, 0, 0, 0.8) 100%);
    backdrop-filter: none;
    align-items: flex-end;
    padding-bottom: var(--spacing-3);
  }

  .card-actions {
    transform: translateY(0);
    gap: var(--spacing-1);
    padding: var(--spacing-1);
  }

  .card-action-btn {
    width: 36px;
    height: 36px;
    background: rgba(0, 0, 0, 0.6);
  }
}

/* 触摸设备优化 */
@media (hover: none) {
  .collection-card:hover .card-actions-overlay {
    opacity: 0;
  }

  .collection-card:active .card-actions-overlay {
    opacity: 1;
  }
}
</style>
