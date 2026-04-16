<script setup lang="ts">
import { computed } from 'vue';
import type { CollectionItem } from '@/types/api';

const props = defineProps<{
  visible: boolean;
  item: CollectionItem | null;
  busyAction: string | null;
  taskBusy: boolean;
}>();

const emit = defineEmits<{
  close: [];
  delete: [item: CollectionItem];
  transfer: [item: CollectionItem];
  verify: [item: CollectionItem];
  rename: [item: CollectionItem];
}>();

const statusLabel = computed(() => {
  if (!props.item) return '';
  const status = props.item.status;
  if (status === 1) return '已转存';
  if (status === 2) return '已失效';
  if (status === 3) return '网盘已删除';
  return '未转存';
});

const statusClass = computed(() => {
  if (!props.item) return '';
  const status = props.item.status;
  if (status === 1) return 'transferred';
  if (status === 2) return 'expired';
  if (status === 3) return 'deleted';
  return 'not-transferred';
});

const posterUrl = computed(() => {
  if (!props.item?.poster_path) return '';
  return `https://image.tmdb.org/t/p/w500${props.item.poster_path}`;
});

const canRename = computed(() => {
  return props.item?.status === 1;
});

const isBusy = computed(() => {
  return !!props.busyAction || props.taskBusy;
});

function handleClose() {
  if (!isBusy.value) {
    emit('close');
  }
}

function handleBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) {
    handleClose();
  }
}

function handleDelete() {
  if (props.item && !isBusy.value) {
    emit('delete', props.item);
  }
}

function handleTransfer() {
  if (props.item && !isBusy.value) {
    emit('transfer', props.item);
  }
}

function handleVerify() {
  if (props.item && !isBusy.value) {
    emit('verify', props.item);
  }
}

function handleRename() {
  if (props.item && !isBusy.value && canRename.value) {
    emit('rename', props.item);
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible && item" class="collection-modal-backdrop" @click="handleBackdropClick">
        <div class="collection-modal-dialog">
          <!-- 头部海报区 -->
          <div class="modal-hero">
            <div class="modal-poster">
              <img v-if="posterUrl" :src="posterUrl" :alt="item.title" />
              <div v-else class="poster-skeleton" />
            </div>
            <button class="modal-close" :disabled="isBusy" @click="handleClose">
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- 内容区 -->
          <div class="modal-content">
            <div class="modal-header">
              <h3 class="modal-title">{{ item.title }}</h3>
              <div class="modal-meta">
                <span class="modal-year">{{ item.year || '未知年份' }}</span>
                <span class="modal-divider">•</span>
                <span class="modal-type">{{ item.media_type === 'movie' ? '电影' : '剧集' }}</span>
              </div>
            </div>

            <!-- 状态标签 -->
            <div class="modal-status">
              <span class="status-badge" :class="statusClass">
                {{ statusLabel }}
              </span>
            </div>

            <!-- 操作按钮组 -->
            <div class="modal-actions">
              <button class="action-btn primary" :disabled="isBusy" @click="handleTransfer">
                <span class="action-icon">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </span>
                <span class="action-text">转存</span>
              </button>

              <button
                :class="['action-btn', { disabled: !canRename }]"
                :disabled="isBusy || !canRename"
                @click="handleRename"
              >
                <span class="action-icon">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </span>
                <span class="action-text">重命名</span>
              </button>

              <button class="action-btn" :disabled="isBusy" @click="handleVerify">
                <span class="action-icon">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M9 12l2 2 4-4" />
                    <circle cx="12" cy="12" r="10" />
                  </svg>
                </span>
                <span class="action-text">验证</span>
              </button>

              <button class="action-btn danger" :disabled="isBusy" @click="handleDelete">
                <span class="action-icon">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path
                      d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"
                    />
                  </svg>
                </span>
                <span class="action-text">删除</span>
              </button>
            </div>

            <!-- 链接信息 -->
            <div class="modal-info">
              <div class="info-item">
                <span class="info-label">分享链接</span>
                <a
                  :href="item.quark_share_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="info-link"
                >
                  {{ item.quark_share_url }}
                </a>
              </div>
              <div class="info-item">
                <span class="info-label">收藏时间</span>
                <span class="info-value">{{ new Date(item.saved_at).toLocaleString() }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.collection-modal-backdrop {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-4);
  background: rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(8px);
  z-index: var(--z-index-modal);
}

.collection-modal-dialog {
  width: min(480px, 100%);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(160deg, var(--color-bg-secondary) 0%, var(--color-bg-primary) 100%);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-2xl);
  overflow: hidden;
}

.modal-hero {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--color-bg-tertiary);
  overflow: hidden;
}

.modal-poster {
  width: 100%;
  height: 100%;
}

.modal-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.modal-close {
  position: absolute;
  top: var(--spacing-3);
  right: var(--spacing-3);
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.modal-close:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.8);
  transform: scale(1.05);
}

.modal-close:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-content {
  padding: var(--spacing-5);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  overflow-y: auto;
}

.modal-header {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.modal-title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  line-height: var(--line-height-tight);
}

.modal-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.modal-divider {
  color: var(--color-text-muted);
}

.modal-status {
  display: flex;
}

.status-badge {
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  text-transform: uppercase;
  letter-spacing: var(--letter-spacing-wide);
}

.status-badge.transferred {
  background: linear-gradient(135deg, var(--color-success) 0%, var(--color-success-dark) 100%);
  color: var(--color-text-primary);
}

.status-badge.expired {
  background: linear-gradient(135deg, var(--color-error) 0%, var(--color-error-dark) 100%);
  color: var(--color-text-primary);
}

.status-badge.deleted {
  background: linear-gradient(135deg, #fd7e14 0%, #e65100 100%);
  color: var(--color-text-primary);
}

.status-badge.not-transferred {
  background: linear-gradient(135deg, rgba(255, 193, 7, 0.9) 0%, rgba(255, 152, 0, 0.9) 100%);
  color: #1a1a1a;
}

.modal-actions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-3);
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-lg);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border-default);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.action-btn:hover:not(:disabled) {
  background: var(--color-bg-elevated);
  border-color: var(--color-border-strong);
  transform: translateY(-1px);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.disabled {
  background: var(--color-bg-secondary);
  color: var(--color-text-muted);
}

.action-btn.primary {
  background: var(--color-brand-gradient);
  border-color: transparent;
  color: var(--color-text-primary);
}

.action-btn.primary:hover:not(:disabled) {
  box-shadow: var(--shadow-glow-red);
}

.action-btn.danger {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
  color: var(--color-error);
}

.action-btn.danger:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2);
  border-color: var(--color-error);
}

.action-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  padding-top: var(--spacing-4);
  border-top: 1px solid var(--color-border-subtle);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.info-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: var(--letter-spacing-wide);
}

.info-link {
  font-size: var(--font-size-sm);
  color: var(--color-brand-primary);
  word-break: break-all;
  transition: color var(--transition-fast);
}

.info-link:hover {
  color: var(--color-brand-light);
  text-decoration: underline;
}

.info-value {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

/* 动画 */
.modal-enter-active,
.modal-leave-active {
  transition:
    opacity var(--transition-base),
    transform var(--transition-base);
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

@media (max-width: 480px) {
  .collection-modal-backdrop {
    padding: 0;
    align-items: flex-end;
  }

  .collection-modal-dialog {
    width: 100%;
    max-height: 85vh;
    border-radius: var(--radius-2xl) var(--radius-2xl) 0 0;
  }

  .modal-content {
    padding: var(--spacing-4);
  }

  .modal-actions {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
