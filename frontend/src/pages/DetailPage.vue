<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import {
  addCollection,
  checkLinks,
  getDetailPageData,
  saveResource,
  searchByTitle,
  searchByTmdb,
} from '@/api';
import { useToast } from '@/composables/useToast';
import type { DetailItem, PosterCard, ResourceDto } from '@/types/api';
import { debounce } from '@/utils/debounce';

import DetailHero from '@/components/DetailHero.vue';
import ResourceList from '@/components/ResourceList.vue';
import CastList from '@/components/CastList.vue';
import VideoList from '@/components/VideoList.vue';
import Recommendations from '@/components/Recommendations.vue';

const props = defineProps<{
  mediaType: 'movie' | 'tv';
  itemId: number;
}>();

const { push } = useToast();

// 页面加载状态
const loading = ref(false);
const item = ref<DetailItem | null>(null);
const recommendations = ref<PosterCard[]>([]);

// 资源相关状态
const resourceLoading = ref(false);
const resourceError = ref('');
const resources = ref<ResourceDto[]>([]);
const collectedMap = reactive<Record<string, boolean>>({});
const savingMap = reactive<Record<string, boolean>>({});
const statusMap = reactive<Record<string, { level: 'success' | 'error' | 'info'; text: string }>>(
  {}
);
const isSearching = ref(false);

// 空状态计算
const isEmptyState = computed(() => {
  return !loading.value && !item.value;
});

/**
 * 标准化文件夹名称
 */
function normalizeFolderName(rawName: string) {
  let name = (rawName || '').trim();
  name = name.replace(/^\d+\.\s*/, '');
  name = name.replace(/[\\/:*?"<>|]/g, ' ');
  name = name.replace(/\s+/g, ' ').trim();
  return name;
}

/**
 * 设置资源状态
 */
function setStatus(link: string, level: 'success' | 'error' | 'info', text: string) {
  statusMap[link] = { level, text };
}

/**
 * 清除资源状态
 */
function clearStatus(link: string) {
  delete statusMap[link];
}

/**
 * 加载链接收藏状态
 */
async function loadLinkStatus(links: string[]) {
  if (links.length === 0) {
    return;
  }
  try {
    const res = await checkLinks({ links });
    if (res.code !== 0) {
      return;
    }
    Object.keys(collectedMap).forEach((key) => delete collectedMap[key]);
    res.data.results.forEach((row) => {
      collectedMap[row.link] = row.collected;
    });
  } catch {
    // ignore
  }
}

/**
 * 搜索资源
 */
async function searchResources() {
  if (!item.value || isSearching.value) {
    return;
  }
  isSearching.value = true;
  resourceLoading.value = true;
  resourceError.value = '';
  resources.value = [];
  Object.keys(collectedMap).forEach((key) => delete collectedMap[key]);

  try {
    let res = await searchByTmdb(item.value.id, item.value.media_type, 100);
    if (res.code !== 0 || res.data.resources.length === 0) {
      res = await searchByTitle(item.value.title, item.value.year ?? undefined, 100);
    }
    if (res.code !== 0) {
      resourceError.value = res.message || '未找到相关资源';
      return;
    }
    resources.value = res.data.resources;
    if (resources.value.length === 0) {
      resourceError.value = '未找到相关资源';
      return;
    }
    await loadLinkStatus(resources.value.map((resource) => resource.link));
  } catch (error) {
    resourceError.value = error instanceof Error ? error.message : '资源搜索失败';
  } finally {
    resourceLoading.value = false;
    isSearching.value = false;
  }
}

/**
 * 加载详情页数据
 */
async function loadDetailPage() {
  if (!Number.isFinite(props.itemId) || props.itemId <= 0) {
    push('无效的详情参数', 'error');
    item.value = null;
    recommendations.value = [];
    resources.value = [];
    return;
  }
  loading.value = true;
  try {
    const res = await getDetailPageData(props.mediaType, props.itemId);
    if (res.code !== 0) {
      push(res.message || '加载详情失败', 'error');
      return;
    }
    item.value = res.data.item;
    recommendations.value = res.data.recommendations;
    await searchResources();
  } catch (error) {
    push(error instanceof Error ? error.message : '加载详情失败', 'error');
  } finally {
    loading.value = false;
  }
}

/**
 * 收藏资源（防抖）
 */
const debouncedCollect = debounce(async (resource: ResourceDto) => {
  const current = item.value;
  if (!current) {
    return;
  }
  if (collectedMap[resource.link]) {
    return;
  }
  savingMap[resource.link] = true;
  clearStatus(resource.link);
  try {
    const res = await addCollection({
      tmdb_id: current.id,
      media_type: current.media_type,
      title: resource.name,
      year: current.year ?? null,
      poster_path: current.poster_path || null,
      backdrop_path: current.backdrop_path || null,
      share_url: resource.link,
    });
    if (res.code !== 0 || !res.data.created) {
      setStatus(resource.link, 'error', res.message || '收藏失败');
      return;
    }
    collectedMap[resource.link] = true;
    setStatus(resource.link, 'success', '收藏成功');
  } catch (error) {
    setStatus(resource.link, 'error', error instanceof Error ? error.message : '收藏失败');
  } finally {
    delete savingMap[resource.link];
  }
}, 500);

/**
 * 保存到网盘（防抖）
 */
const debouncedSave = debounce(async (resource: ResourceDto) => {
  const current = item.value;
  if (!current) {
    return;
  }
  savingMap[resource.link] = true;
  setStatus(resource.link, 'info', '正在保存...');
  try {
    const res = await saveResource({
      link: resource.link,
      media_type: current.media_type,
      title: current.title,
      year: current.year ?? null,
      tmdb_id: current.id,
      poster_path: current.poster_path || null,
      backdrop_path: current.backdrop_path || null,
      resource_name: resource.name,
      to_dir_name: normalizeFolderName(resource.name),
    });
    if (res.code !== 0) {
      setStatus(resource.link, 'error', res.message || '保存失败');
      return;
    }
    if (res.data.collection_created || res.data.collection_id) {
      collectedMap[resource.link] = true;
    }
    setStatus(resource.link, 'success', '保存成功');
  } catch (error) {
    setStatus(resource.link, 'error', error instanceof Error ? error.message : '保存失败');
  } finally {
    delete savingMap[resource.link];
  }
}, 500);

/**
 * 事件处理
 */
function onCollect(resource: ResourceDto) {
  debouncedCollect(resource);
}

function onSave(resource: ResourceDto) {
  debouncedSave(resource);
}

function onRetrySearch() {
  void searchResources();
}

// 监听路由参数变化
watch(
  () => [props.mediaType, props.itemId],
  () => {
    void loadDetailPage();
  }
);

// 组件挂载时加载数据
onMounted(() => {
  void loadDetailPage();
});
</script>

<style scoped>
/* FIXED: 为详情页添加响应式 padding，确保内容不被 header/footer 遮挡 */
.detail-page {
  padding-top: var(--spacing-4);
  padding-bottom: var(--spacing-16);
  min-height: 100vh;
}

@media (min-width: 768px) {
  .detail-page {
    padding-top: var(--spacing-6);
    padding-bottom: var(--spacing-20);
  }
}

/* 资源列表区域增加底部间距，防止被遮挡 */
.detail-page :deep(.section-body) {
  margin-bottom: var(--spacing-8);
}

/* FIXED: 资源列表区块样式优化 */
.resources-section {
  margin-bottom: var(--spacing-8);
}

.resources-section .section-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: 0 var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.resources-section .section-icon {
  color: var(--color-brand-primary);
  font-size: var(--font-size-xl);
  filter: drop-shadow(0 0 8px rgba(240, 90, 40, 0.4));
  width: 24px;
  height: 24px;
}

.resources-section .section-title {
  margin: 0;
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-xl);
  letter-spacing: var(--letter-spacing-tight);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

@media (min-width: 768px) {
  .resources-section .section-header {
    padding: 0 var(--spacing-6);
  }
  
  .resources-section .section-title {
    font-size: var(--font-size-2xl);
  }
}

@media (min-width: 1280px) {
  .resources-section .section-header {
    padding: 0 var(--spacing-12);
  }
  
  .resources-section .section-title {
    font-size: var(--font-size-3xl);
  }
}
</style>

<template>
  <div class="page detail-page">
    <!-- 加载中状态 -->
    <DetailHero v-if="loading" :item="item" :loading="true" />

    <!-- 有数据时显示详情和其他区块 -->
    <template v-if="item">
      <!-- 详情介绍区块 -->
      <DetailHero :item="item" :loading="false" />
      
      <!-- 资源列表区块（在详情介绍之下） -->
      <section class="detail-section resources-section">
        <ResourceList
          :resources="resources"
          :loading="resourceLoading"
          :error="resourceError"
          :collected-map="collectedMap"
          :saving-map="savingMap"
          :status-map="statusMap"
          @collect="onCollect"
          @save="onSave"
          @retry="onRetrySearch"
        />
      </section>
      
      <!-- 其他区块 -->
      <CastList :cast="item.cast" />
      <VideoList :videos="item.videos" />
      <Recommendations :recommendations="recommendations" />
    </template>

    <!-- 空状态 -->
    <div v-if="isEmptyState" class="empty" role="status">
      <div class="empty-icon" aria-hidden="true">📄</div>
      <div class="empty-text">详情加载失败</div>
    </div>
  </div>
</template>
