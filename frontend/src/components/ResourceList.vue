<script setup lang="ts">
import type { ResourceDto } from '@/types/api';
import ResourceCard from './ResourceCard.vue';
import ScrollableRow from '@/components/ScrollableRow.vue';
import IconPackage from './Icons/IconPackage.vue';
import { ref, computed } from 'vue';

interface ResourceListProps {
  resources: ResourceDto[];
  loading: boolean;
  error: string;
  collectedMap: Record<string, boolean>;
  savingMap: Record<string, boolean>;
  statusMap: Record<string, { level: 'success' | 'error' | 'info'; text: string }>;
}

const props = defineProps<ResourceListProps>();

const emit = defineEmits<{
  collect: [resource: ResourceDto];
  save: [resource: ResourceDto];
  retry: [];
}>();

// 排序和筛选状态
const sortBy = ref<'score' | 'quality' | 'name'>('score');
const showOnlyBest = ref(false);

// 过滤和排序后的资源列表
const filteredResources = computed(() => {
  let result = [...props.resources];

  // 筛选最佳资源
  if (showOnlyBest.value) {
    result = result.filter(r => r.is_best);
  }

  // 排序
  result.sort((a, b) => {
    switch (sortBy.value) {
      case 'score':
        return b.overall_score - a.overall_score;
      case 'quality':
        const qualityOrder: Record<string, number> = { '4K': 4, '1080p': 3, '720p': 2, '480p': 1 };
        const aQuality = qualityOrder[a.resolution] || qualityOrder[a.quality_level] || 0;
        const bQuality = qualityOrder[b.resolution] || qualityOrder[b.quality_level] || 0;
        return bQuality - aQuality;
      case 'name':
        return a.name.localeCompare(b.name, 'zh-CN');
      default:
        return 0;
    }
  });

  return result;
});

// 排序选项
const sortOptions = [
  { value: 'score', label: '评分最高' },
  { value: 'quality', label: '质量最好' },
  { value: 'name', label: '名称 A-Z' },
];
</script>

<template>
  <section class="section detail-section resource-list-section" aria-labelledby="resource-list-title">
    <div class="section-header">
      <IconPackage class="section-icon" aria-hidden="true" />
      <h2 class="section-title" id="resource-list-title">
        资源列表
      </h2>
    </div>
    <div class="section-body">
      <!-- 加载中 - 骨架屏 -->
      <div v-if="loading" class="loading-skeleton" role="status" aria-label="加载中">
        <!-- 工具栏骨架 -->
        <div class="skeleton-toolbar">
          <div class="skeleton-left">
            <div class="skeleton-icon" />
            <div class="skeleton-count skeleton-block" />
          </div>
          <div class="skeleton-controls">
            <div class="skeleton-filter skeleton-block" />
            <div class="skeleton-select skeleton-block" />
          </div>
        </div>

        <!-- 横向滚动骨架 -->
        <div class="resource-scroll-container">
          <div v-for="i in 6" :key="i" class="skeleton-resource-card">
            <div class="skeleton-card-body">
              <div class="skeleton-header">
                <div class="skeleton-index skeleton-circle" />
                <div class="skeleton-title skeleton-text" />
                <div class="skeleton-badges">
                  <div class="skeleton-badge skeleton-block" />
                  <div class="skeleton-badge skeleton-block" />
                </div>
              </div>
              <div class="skeleton-tags">
                <div class="skeleton-tag skeleton-block" />
                <div class="skeleton-tag skeleton-block" />
                <div class="skeleton-tag skeleton-block" />
              </div>
              <div class="skeleton-score">
                <div class="skeleton-score-label skeleton-text" />
                <div class="skeleton-score-value skeleton-text" />
                <div class="skeleton-progress" />
              </div>
              <div class="skeleton-details">
                <div class="skeleton-detail-item skeleton-text" />
                <div class="skeleton-detail-item skeleton-text" />
              </div>
            </div>
            <div class="skeleton-actions">
              <div class="skeleton-btn skeleton-block" />
              <div class="skeleton-btn skeleton-block" />
            </div>
          </div>
        </div>
      </div>

      <!-- 错误状态 -->
      <div v-else-if="error" class="empty" role="status">
        <IconPackage class="empty-icon" aria-hidden="true" />
        <div class="empty-text">{{ error }}</div>
        <button class="retry-btn" @click="emit('retry')">重试</button>
      </div>

      <!-- 资源列表 -->
      <div v-else class="resource-list-container">
        <!-- 工具栏 -->
        <div class="resource-toolbar">
          <div class="toolbar-left">
            <span class="resource-count">
              <span class="count-number">{{ filteredResources.length }}</span>
              <span class="count-label">个资源</span>
            </span>
          </div>
          <div class="toolbar-right">
            <!-- 最佳资源筛选 -->
            <label class="filter-toggle">
              <input
                type="checkbox"
                v-model="showOnlyBest"
                class="filter-checkbox"
              />
              <span class="filter-label">
                <span class="filter-icon">⭐</span>
                仅显示最佳
              </span>
            </label>

            <!-- 排序下拉框 -->
            <div class="sort-control">
              <label for="sort-select" class="sort-label">排序:</label>
              <select
                id="sort-select"
                v-model="sortBy"
                class="sort-select"
              >
                <option
                  v-for="option in sortOptions"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
          </div>
        </div>

        <!-- 横向滚动布局 -->
        <div v-if="filteredResources.length > 0" class="resource-scroll-wrapper">
          <ScrollableRow>
            <ResourceCard
              v-for="(resource, index) in filteredResources"
              :key="resource.link"
              v-memo="[resource.link, collectedMap[resource.link], savingMap[resource.link], statusMap[resource.link]]"
              :resource="resource"
              :index="index"
              :is-collected="collectedMap[resource.link]"
              :is-saving="savingMap[resource.link]"
              :status="statusMap[resource.link] || null"
              @collect="emit('collect', resource)"
              @save="emit('save', resource)"
            />
          </ScrollableRow>
        </div>

        <!-- 空状态 -->
        <div v-else-if="resources.length > 0" class="empty" role="status">
          <div class="empty-icon" aria-hidden="true">🔍</div>
          <div class="empty-text">没有符合条件的资源</div>
          <div class="empty-hint">尝试调整筛选或排序条件</div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* ============================================
   资源列表容器
   ============================================ */
.resource-list-section {
  margin-bottom: var(--spacing-8);
}

.resource-list-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

/* ============================================
   横向滚动包装器
   ============================================ */
.resource-scroll-wrapper {
  width: 100%;
}

/* 骨架屏滚动容器 */
.resource-scroll-container {
  display: flex;
  gap: var(--spacing-4);
  overflow-x: auto;
  padding: var(--spacing-4);
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.resource-scroll-container::-webkit-scrollbar {
  display: none;
}

/* 骨架屏资源卡片 */
.skeleton-resource-card {
  flex-shrink: 0;
  width: 300px;
  max-width: 320px;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.05) 0%,
    rgba(255, 255, 255, 0.02) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-2xl);
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

/* ============================================
   工具栏样式
   ============================================ */
.resource-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.03) 0%,
    rgba(255, 255, 255, 0.01) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-xl);
  backdrop-filter: blur(8px);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

/* 资源计数 */
.resource-count {
  display: inline-flex;
  align-items: baseline;
  gap: var(--spacing-1);
}

.count-number {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  background: linear-gradient(135deg, var(--color-brand-primary) 0%, var(--color-accent-cyan) 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: var(--color-brand-primary);
}

.count-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

/* 筛选开关 */
.filter-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
  user-select: none;
}

.filter-checkbox {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.filter-label {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-3);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-full);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  transition: all var(--transition-fast);
}

.filter-checkbox:checked + .filter-label {
  background: linear-gradient(135deg, var(--color-warning) 0%, var(--color-warning-dark) 100%);
  border-color: transparent;
  color: var(--color-bg-primary);
  box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3);
}

.filter-label:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.12);
}

.filter-checkbox:checked + .filter-label:hover {
  background: linear-gradient(135deg, var(--color-warning) 0%, var(--color-warning-dark) 100%);
}

.filter-icon {
  font-size: var(--font-size-xs);
}

/* 排序控件 */
.sort-control {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.sort-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

.sort-select {
  padding: var(--spacing-1) var(--spacing-3);
  padding-right: var(--spacing-8);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-full);
  color: var(--color-text-primary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-fast);
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23a3a3a3' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
}

.sort-select:hover {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.12);
}

.sort-select:focus {
  outline: none;
  border-color: var(--color-accent-cyan);
  box-shadow: 0 0 0 2px rgba(34, 211, 238, 0.2);
}

/* ============================================
   ScrollableRow 集成样式
   ============================================ */
.resource-scroll-wrapper :deep(.scrollable-row-container) {
  padding: var(--spacing-4);
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.02) 0%,
    rgba(255, 255, 255, 0.01) 100%
  );
  border-radius: var(--radius-xl);
}

/* 资源卡片宽度 - 固定 300px */
.resource-scroll-wrapper :deep(.quark-resource-card) {
  flex-shrink: 0;
  width: 300px;
  max-width: 320px;
}

/* ============================================
   响应式优化
   ============================================ */
@media (max-width: 639px) {
  .resource-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-left,
  .toolbar-right {
    justify-content: center;
  }

  .toolbar-right {
    flex-direction: column;
    gap: var(--spacing-2);
  }

  .sort-control {
    justify-content: center;
  }

  /* 移动端滚动按钮优化 */
  .resource-scroll-wrapper :deep(.scroll-btn) {
    opacity: 0.9;
    pointer-events: auto;
  }
}

/* ============================================
   骨架屏加载状态
   ============================================ */
.loading-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.skeleton-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-3) var(--spacing-4);
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.03) 0%,
    rgba(255, 255, 255, 0.01) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-xl);
}

.skeleton-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.skeleton-icon {
  width: 20px;
  height: 20px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.skeleton-count {
  width: 100px;
  height: 24px;
  border-radius: var(--radius-md);
}

.skeleton-controls {
  display: flex;
  gap: var(--spacing-3);
}

.skeleton-filter {
  width: 80px;
  height: 28px;
  border-radius: var(--radius-full);
}

.skeleton-select {
  width: 120px;
  height: 28px;
  border-radius: var(--radius-full);
}

/* 骨架卡片 */
.skeleton-card {
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.05) 0%,
    rgba(255, 255, 255, 0.02) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-2xl);
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.skeleton-card-body {
  padding: var(--spacing-4);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.skeleton-header {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
}

.skeleton-index {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}

.skeleton-circle {
  border-radius: var(--radius-full);
}

.skeleton-title {
  flex: 1;
  height: 20px;
  border-radius: var(--radius-md);
}

.skeleton-badges {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.skeleton-badge {
  width: 40px;
  height: 16px;
  border-radius: var(--radius-md);
}

.skeleton-tags {
  display: flex;
  gap: var(--spacing-1);
  flex-wrap: wrap;
}

.skeleton-tag {
  width: 50px;
  height: 16px;
  border-radius: var(--radius-md);
}

.skeleton-score {
  padding: var(--spacing-3);
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.03) 0%,
    rgba(255, 255, 255, 0.01) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.skeleton-score-label {
  width: 60px;
  height: 12px;
}

.skeleton-score-value {
  width: 80px;
  height: 24px;
}

.skeleton-progress {
  height: 6px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.skeleton-details {
  display: flex;
  gap: var(--spacing-3);
}

.skeleton-detail-item {
  width: 80px;
  height: 14px;
}

.skeleton-actions {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  padding-top: var(--spacing-3);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.skeleton-btn {
  height: 32px;
  border-radius: var(--radius-md);
}

/* 骨架屏动画 */
.skeleton-block {
  background: linear-gradient(
    110deg,
    rgba(255, 255, 255, 0.08) 0%,
    rgba(255, 255, 255, 0.12) 40%,
    rgba(255, 255, 255, 0.16) 50%,
    rgba(255, 255, 255, 0.12) 60%,
    rgba(255, 255, 255, 0.08) 100%
  );
  background-size: 300% 100%;
  animation: skeleton-shimmer 1.8s ease-in-out infinite;
}

.skeleton-text {
  background: linear-gradient(
    110deg,
    rgba(255, 255, 255, 0.06) 0%,
    rgba(255, 255, 255, 0.1) 40%,
    rgba(255, 255, 255, 0.14) 50%,
    rgba(255, 255, 255, 0.1) 60%,
    rgba(255, 255, 255, 0.06) 100%
  );
  background-size: 300% 100%;
  animation: skeleton-shimmer 1.8s ease-in-out infinite;
}

@keyframes skeleton-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@media (max-width: 639px) {
  .skeleton-toolbar {
    flex-direction: column;
    gap: var(--spacing-2);
  }

  .skeleton-controls {
    width: 100%;
    justify-content: center;
  }
}

/* 重试按钮样式 */
.retry-btn {
  margin-top: var(--spacing-4);
  padding: var(--spacing-2) var(--spacing-4);
  background: linear-gradient(135deg, var(--color-brand-primary) 0%, var(--color-accent-cyan) 100%);
  border: none;
  border-radius: var(--radius-md);
  color: var(--color-bg-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.retry-btn:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}
</style>
