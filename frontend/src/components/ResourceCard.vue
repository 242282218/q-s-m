<script setup lang="ts">
import type { ResourceDto } from '@/types/api';

defineProps<{
  resource: ResourceDto;
  index: number;
  isCollected?: boolean;
  isSaving?: boolean;
  status?: { level: 'success' | 'error' | 'info'; text: string } | null;
}>();

const emit = defineEmits<{
  collect: [resource: ResourceDto];
  save: [resource: ResourceDto];
}>();
</script>

<template>
  <div class="quark-resource-card" role="listitem">
    <!-- 卡片主体 -->
    <div class="card-body">
      <!-- 头部：序号 + 标题 + 徽章 -->
      <div class="card-header">
        <div class="resource-index">
          {{ index + 1 }}
        </div>
        <h4 class="resource-title" :title="resource.name">
          {{ resource.name }}
        </h4>
        <div class="resource-badges">
          <span
            v-if="resource.is_best"
            class="badge-best"
            title="最佳资源"
          >
            <span class="badge-icon">🏆</span>
            最佳
          </span>
          <span
            v-if="resource.resolution || resource.quality_level"
            class="badge-quality"
          >
            {{ resource.resolution || resource.quality_level }}
          </span>
        </div>
      </div>

      <!-- 标签区域 -->
      <div v-if="resource.tags?.length" class="resource-tags">
        <span
          v-for="tag in resource.tags.slice(0, 5)"
          :key="tag"
          class="resource-tag"
        >
          {{ tag.toUpperCase() }}
        </span>
      </div>

      <!-- 评分区域 -->
      <div class="resource-score-section">
        <div class="score-main">
          <span class="score-label">综合评分</span>
          <div class="score-value-wrapper">
            <span class="score-value">
              {{ (resource.overall_score * 10).toFixed(1) }}
            </span>
            <span class="score-max">/10</span>
          </div>
        </div>
        
        <!-- 评分进度条 -->
        <div class="score-progress">
          <div
            class="score-progress-bar"
            :style="{ width: `${Math.min(resource.overall_score * 100, 100)}%` }"
            :class="{
              'score-excellent': resource.overall_score >= 0.8,
              'score-good': resource.overall_score >= 0.6 && resource.overall_score < 0.8,
              'score-average': resource.overall_score < 0.6
            }"
          />
        </div>
      </div>

      <!-- 详细信息（可选展开） -->
      <div class="resource-details">
        <div v-if="resource.codec" class="detail-item">
          <span class="detail-icon">🎬</span>
          <span class="detail-text">{{ resource.codec }}</span>
        </div>
        <div v-if="resource.size_gb" class="detail-item">
          <span class="detail-icon">💾</span>
          <span class="detail-text">{{ resource.size_gb.toFixed(1) }} GB</span>
        </div>
      </div>
    </div>

    <!-- 操作区域 -->
    <div class="card-actions">
      <!-- 第一行：打开链接 + 收藏 -->
      <div class="action-row">
        <a
          :href="resource.link"
          target="_blank"
          rel="noopener noreferrer"
          class="btn btn-primary btn-open-link"
        >
          <span class="btn-icon">🔗</span>
          打开链接
        </a>
        <button
          :class="['btn', 'btn-primary', 'btn-collect-resource', { 'btn-success': isCollected }]"
          :disabled="isCollected || isSaving"
          @click="emit('collect', resource)"
        >
          <span v-if="isSaving" class="btn-icon loading-spinner">⏳</span>
          <span v-else class="btn-icon">{{ isCollected ? '✅' : '⭐' }}</span>
          {{ isCollected ? '已收藏' : '收藏' }}
        </button>
      </div>

      <!-- 第二行：保存到网盘 -->
      <div class="action-row">
        <button
          :class="['btn', 'btn-primary', 'btn-save-transfer']"
          :disabled="isSaving"
          @click="emit('save', resource)"
        >
          <span v-if="isSaving" class="btn-icon loading-spinner">⏳</span>
          <span v-else class="btn-icon">📦</span>
          {{ isSaving ? '保存中...' : '保存到网盘' }}
        </button>
      </div>

      <!-- 状态提示 -->
      <div v-if="status" class="resource-status" role="status">
        <span
          :class="{
            'success-text': status.level === 'success',
            'error-text': status.level === 'error',
            'warning-text': status.level === 'info',
          }"
          class="status-text"
        >
          {{ status.text }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ============================================
   资源卡片容器
   ============================================ */
.quark-resource-card {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.05) 0%,
    rgba(255, 255, 255, 0.02) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-2xl);
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  transition: all var(--transition-fast);
}

.quark-resource-card:hover {
  transform: translateY(-4px);
  border-color: rgba(255, 255, 255, 0.15);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

/* ============================================
   卡片主体
   ============================================ */
.card-body {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  flex: 1;
  padding: var(--spacing-4);
}

/* 头部区域 */
.card-header {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
}

.resource-index {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
}

.resource-title {
  flex: 1;
  margin: 0;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  line-height: var(--line-height-snug);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
}

.resource-badges {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  flex-shrink: 0;
}

/* 徽章样式 */
.badge-best {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px var(--spacing-2);
  background: var(--color-warning);
  border-radius: var(--radius-full);
  font-size: 10px;
  font-weight: var(--font-weight-bold);
  color: var(--color-bg-primary);
  white-space: nowrap;
}

.badge-icon {
  font-size: 10px;
}

.badge-quality {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px var(--spacing-2);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  font-size: 10px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  white-space: nowrap;
}

/* 标签区域 */
.resource-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
}

.resource-tag {
  padding: 2px var(--spacing-2);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  font-size: 9px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* 评分区域 */
.resource-score-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
}

.score-main {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.score-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.score-value-wrapper {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.score-value {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  line-height: 1;
}

.score-max {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-weight: var(--font-weight-medium);
}

/* 评分进度条 */
.score-progress {
  position: relative;
  height: 4px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.score-progress-bar {
  height: 100%;
  border-radius: var(--radius-full);
}

.score-excellent {
  background: var(--color-success);
}

.score-good {
  background: var(--color-info);
}

.score-average {
  background: var(--color-warning);
}

/* ============================================
   详细信息
   ============================================ */
.resource-details {
  display: flex;
  gap: var(--spacing-3);
  padding-top: var(--spacing-1);
}

.detail-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.detail-icon {
  font-size: var(--font-size-xs);
  opacity: 0.7;
}

.detail-text {
  font-weight: var(--font-weight-medium);
}

/* ============================================
   操作区域
   ============================================ */
.card-actions {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4) var(--spacing-4);
  border-top: 1px solid var(--color-border-subtle);
}

.action-row {
  display: flex;
  gap: var(--spacing-2);
}

/* 按钮样式 */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-1);
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-md);
  border: none;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-decoration: none;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: linear-gradient(135deg, var(--color-brand-primary) 0%, var(--color-accent-cyan) 100%);
  color: var(--color-bg-primary);
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
  transform: translateY(-1px);
}

.btn-success {
  background: var(--color-success);
}

.btn-open-link,
.btn-collect-resource,
.btn-save-transfer {
  flex: 1;
}

.btn-icon {
  font-size: var(--font-size-sm);
}

.loading-spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* 状态提示 */
.resource-status {
  text-align: center;
  padding: var(--spacing-2);
  border-radius: var(--radius-md);
  background: var(--color-bg-tertiary);
}

.status-text {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
}

.success-text {
  color: var(--color-success);
}

.error-text {
  color: var(--color-error);
}

.warning-text {
  color: var(--color-warning);
}

/* ============================================
   响应式优化
   ============================================ */
@media (max-width: 639px) {
  .card-body {
    padding: var(--spacing-3);
  }
  
  .card-actions {
    padding: var(--spacing-3);
  }
  
  .action-row {
    flex-direction: column;
  }
  
  .resource-title {
    font-size: var(--font-size-xs);
    -webkit-line-clamp: 1;
  }
  
  .score-value {
    font-size: var(--font-size-lg);
  }
}
</style>
