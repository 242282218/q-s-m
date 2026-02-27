<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";

import {
  addCollection,
  checkLinks,
  getDetailPageData,
  saveResource,
  searchByTitle,
  searchByTmdb,
} from "@/api";
import { useToast } from "@/composables/useToast";
import type { DetailItem, PosterCard, ResourceDto } from "@/types/api";
import IconRecommendations from "@/components/Icons/IconRecommendations.vue";
import { debounce } from "@/utils/debounce";

const props = defineProps<{
  mediaType: "movie" | "tv";
  itemId: number;
}>();

const { push } = useToast();

const loading = ref(false);
const item = ref<DetailItem | null>(null);
const recommendations = ref<PosterCard[]>([]);

const resourceLoading = ref(false);
const resourceError = ref("");
const resources = ref<ResourceDto[]>([]);
const collectedMap = reactive<Record<string, boolean>>({});
const savingMap = reactive<Record<string, boolean>>({});
const statusMap = reactive<Record<string, { level: "success" | "error" | "info"; text: string }>>({});
const isSearching = ref(false);

const playingVideos = reactive<Record<string, boolean>>({});

const heroStyle = computed(() => {
  const url = item.value?.backdrop_url;
  if (url) {
    return {
      backgroundImage: `linear-gradient(180deg, rgba(10,10,10,0.7), rgba(10,10,10,0.9)), url('${url}')`,
    };
  }
  return {
    background: "linear-gradient(135deg, var(--color-bg-secondary) 0%, var(--color-bg-primary) 100%)",
  };
});

function mediaLink(mediaType: string, id: number) {
  return `/${mediaType}/${id}`;
}

function normalizeFolderName(rawName: string) {
  let name = (rawName || "").trim();
  name = name.replace(/^\d+\.\s*/, "");
  name = name.replace(/[\\/:*?"<>|]/g, " ");
  name = name.replace(/\s+/g, " ").trim();
  return name;
}

function setStatus(link: string, level: "success" | "error" | "info", text: string) {
  statusMap[link] = { level, text };
}

function clearStatus(link: string) {
  delete statusMap[link];
}

function onPlayVideo(videoKey: string) {
  playingVideos[videoKey] = true;
}

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

async function searchResources() {
  if (!item.value || isSearching.value) {
    return;
  }
  isSearching.value = true;
  resourceLoading.value = true;
  resourceError.value = "";
  resources.value = [];
  Object.keys(collectedMap).forEach((key) => delete collectedMap[key]);

  try {
    let res = await searchByTmdb(item.value.id, item.value.media_type, 100);
    if (res.code !== 0 || res.data.resources.length === 0) {
      res = await searchByTitle(item.value.title, item.value.year ?? undefined, 100);
    }
    if (res.code !== 0) {
      resourceError.value = res.message || "未找到相关资源";
      return;
    }
    resources.value = res.data.resources;
    if (resources.value.length === 0) {
      resourceError.value = "未找到相关资源";
      return;
    }
    await loadLinkStatus(resources.value.map((resource) => resource.link));
  } catch (error) {
    resourceError.value = error instanceof Error ? error.message : "资源搜索失败";
  } finally {
    resourceLoading.value = false;
    isSearching.value = false;
  }
}

async function loadDetailPage() {
  if (!Number.isFinite(props.itemId) || props.itemId <= 0) {
    push("无效的详情参数", "error");
    item.value = null;
    recommendations.value = [];
    resources.value = [];
    return;
  }
  loading.value = true;
  try {
    const res = await getDetailPageData(props.mediaType, props.itemId);
    if (res.code !== 0) {
      push(res.message || "加载详情失败", "error");
      return;
    }
    item.value = res.data.item;
    recommendations.value = res.data.recommendations;
    Object.keys(playingVideos).forEach((key) => delete playingVideos[key]);
    await searchResources();
  } catch (error) {
    push(error instanceof Error ? error.message : "加载详情失败", "error");
  } finally {
    loading.value = false;
  }
}

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
      setStatus(resource.link, "error", res.message || "收藏失败");
      return;
    }
    collectedMap[resource.link] = true;
    setStatus(resource.link, "success", "收藏成功");
  } catch (error) {
    setStatus(resource.link, "error", error instanceof Error ? error.message : "收藏失败");
  } finally {
    delete savingMap[resource.link];
  }
}, 500);

const debouncedSave = debounce(async (resource: ResourceDto) => {
  const current = item.value;
  if (!current) {
    return;
  }
  savingMap[resource.link] = true;
  setStatus(resource.link, "info", "正在保存...");
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
      setStatus(resource.link, "error", res.message || "保存失败");
      return;
    }
    if (res.data.collection_created || res.data.collection_id) {
      collectedMap[resource.link] = true;
    }
    setStatus(resource.link, "success", "保存成功");
  } catch (error) {
    setStatus(resource.link, "error", error instanceof Error ? error.message : "保存失败");
  } finally {
    delete savingMap[resource.link];
  }
}, 500);

async function onCollect(resource: ResourceDto) {
  debouncedCollect(resource);
}

async function onSave(resource: ResourceDto) {
  debouncedSave(resource);
}

watch(
  () => [props.mediaType, props.itemId],
  () => {
    void loadDetailPage();
  },
);

onMounted(() => {
  void loadDetailPage();
});
</script>

<template>
  <div class="page">
    <div v-if="loading" class="page" role="status" aria-label="加载中">
      <section class="detail-hero" aria-labelledby="loading-hero" :style="heroStyle">
        <div class="detail-shell">
          <div class="detail-poster">
            <div class="poster-skeleton" aria-hidden="true" />
          </div>
          <div class="detail-meta">
            <h1 class="detail-title skeleton-text large" id="loading-hero" aria-hidden="true" />
            <div class="detail-subtitle">
              <span class="skeleton-text short" aria-hidden="true" />
              <span class="skeleton-text short" aria-hidden="true" />
              <span class="skeleton-text short" aria-hidden="true" />
            </div>
            <div class="detail-tags" role="list" aria-label="类型标签">
              <span class="tag skeleton-text short" role="listitem" aria-hidden="true" />
              <span class="tag skeleton-text short" role="listitem" aria-hidden="true" />
            </div>
            <p class="detail-tagline skeleton-text medium" aria-hidden="true" />
            <p class="detail-overview skeleton-text long" aria-hidden="true" />
          </div>
        </div>
      </section>

      <section class="section detail-section" aria-labelledby="loading-resources">
        <div class="section-header">
          <span class="section-icon" aria-hidden="true">📦</span>
          <h2 class="section-title" id="loading-resources">夸克网盘资源</h2>
        </div>
        <div class="section-body">
          <div class="quark-resources-scroll" role="list" aria-live="polite">
            <article v-for="i in 3" :key="i" class="quark-resource-card skeleton-card" role="listitem" aria-hidden="true">
              <div class="resource-header">
                <h4 class="resource-title skeleton-text medium" />
                <div class="resource-badges">
                  <span class="badge-best skeleton-text short" />
                  <span class="badge-quality skeleton-text short" />
                </div>
              </div>
              <div class="resource-tags">
                <span class="resource-tag skeleton-text short" />
              </div>
              <div class="resource-score">
                <span class="score-label skeleton-text short" />
                <span class="score-value skeleton-text short" />
              </div>
              <div class="resource-actions">
                <a class="btn btn-primary skeleton-text" />
                <button class="btn btn-collect skeleton-text" />
              </div>
            </article>
          </div>
        </div>
      </section>
    </div>

    <template v-else-if="item">
      <section class="detail-hero" aria-labelledby="detail-title" :style="heroStyle">
        <div class="detail-shell">
          <div class="detail-poster">
            <img v-if="item.poster_url" :src="item.poster_url" :alt="`${item.title} 海报`" loading="eager" />
            <div v-else class="poster-skeleton" aria-hidden="true" />
          </div>
          <div class="detail-meta">
            <h1 class="detail-title" id="detail-title">{{ item.title }}</h1>
            <div class="detail-subtitle">
              <span v-if="item.year">{{ item.year }}</span>
              <span v-if="item.vote" class="dot" aria-hidden="true">•</span>
              <span v-if="item.vote">⭐ {{ item.vote.toFixed(1) }}</span>
              <span v-if="item.runtime" class="dot" aria-hidden="true">•</span>
              <span v-if="item.runtime">{{ item.runtime }} 分钟</span>
            </div>
            <div v-if="item.genres.length" class="detail-tags" role="list" aria-label="类型标签">
              <span v-for="genre in item.genres" :key="genre" class="tag" role="listitem">{{ genre }}</span>
            </div>
            <p v-if="item.tagline" class="detail-tagline">"{{ item.tagline }}"</p>
            <p v-if="item.overview" class="detail-overview">{{ item.overview }}</p>
          </div>
        </div>
      </section>

      <section class="section detail-section" aria-labelledby="quark-title">
        <div class="section-header">
          <span class="section-icon" aria-hidden="true">📦</span>
          <h2 class="section-title" id="quark-title">夸克网盘资源</h2>
        </div>
        <div class="section-body">
          <div v-if="resourceLoading" class="loading" role="status">
            <div class="loading-spinner" />
            <span>搜索资源中...</span>
          </div>
          <div v-else-if="resourceError" class="empty" role="status">
            <div class="empty-icon">🔍</div>
            <div class="empty-text">{{ resourceError }}</div>
            <button class="btn btn-secondary" @click="searchResources">重试</button>
          </div>
          <div v-else class="quark-resources-scroll" role="list" aria-live="polite">
            <article v-for="(resource, index) in resources" :key="resource.link" class="quark-resource-card" role="listitem">
              <div class="resource-header">
                <h4 class="resource-title">{{ index + 1 }}. {{ resource.name }}</h4>
                <div class="resource-badges">
                  <span v-if="resource.is_best" class="badge-best">最佳</span>
                  <span class="badge-quality">{{ resource.resolution || resource.quality_level || "未知" }}</span>
                </div>
              </div>

              <div v-if="resource.tags?.length" class="resource-tags">
                <span v-for="tag in resource.tags" :key="tag" class="resource-tag">{{ tag.toUpperCase() }}</span>
              </div>

              <div class="resource-score">
                <span class="score-label">资源评分:</span>
                <span class="score-value">{{ (resource.overall_score * 10).toFixed(1) }}</span>
              </div>

              <div class="resource-actions">
                <a :href="resource.link" target="_blank" rel="noopener noreferrer" class="btn btn-primary">打开链接</a>
                <button
                  class="btn btn-collect"
                  :class="{ 'btn-success': collectedMap[resource.link] }"
                  :disabled="savingMap[resource.link] || collectedMap[resource.link]"
                  @click="onCollect(resource)"
                >
                  {{ collectedMap[resource.link] ? "✅ 已收藏" : "⭐ 收藏" }}
                </button>
              </div>

              <div class="resource-actions">
                <button class="btn btn-transfer" :disabled="savingMap[resource.link]" @click="onSave(resource)">
                  {{ savingMap[resource.link] ? "保存中..." : "保存到网盘" }}
                </button>
              </div>

              <div class="resource-status">
                <span
                  v-if="statusMap[resource.link]"
                  :class="{
                    'success-text': statusMap[resource.link].level === 'success',
                    'error-text': statusMap[resource.link].level === 'error',
                    'warning-text': statusMap[resource.link].level === 'info',
                  }"
                >
                  {{ statusMap[resource.link].text }}
                </span>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section class="section detail-section" aria-labelledby="cast-title">
        <div class="section-header">
          <span class="section-icon" aria-hidden="true">👥</span>
          <h2 class="section-title" id="cast-title">演员阵容</h2>
        </div>
        <div class="section-body">
          <div v-if="item.cast.length" class="cast-grid" role="list">
            <a v-for="cast in item.cast" :key="cast.id" class="cast-link" :href="`/person/${cast.id}`" role="listitem">
              <div class="cast-card">
                <div class="cast-avatar">
                  <img v-if="cast.profile_url" :src="cast.profile_url" :alt="cast.name" loading="lazy" decoding="async" />
                  <div v-else class="poster-skeleton" aria-hidden="true" />
                </div>
                <div class="cast-name">{{ cast.name }}</div>
                <div v-if="cast.character" class="cast-role">{{ cast.character }}</div>
              </div>
            </a>
          </div>
          <div v-else class="empty" role="status">
            <div class="empty-icon">👤</div>
            <div class="empty-text">暂无演员信息</div>
          </div>
        </div>
      </section>

      <section class="section detail-section" aria-labelledby="recommend-title">
        <div class="section-header">
          <IconRecommendations class="section-icon" aria-hidden="true" />
          <h2 class="section-title" id="recommend-title">相关推荐</h2>
        </div>
        <div class="section-body">
          <div v-if="recommendations.length" class="recommend-grid" role="list">
            <a
              v-for="poster in recommendations"
              :key="`${poster.media_type}-${poster.id}`"
              class="poster-card"
              :class="`tone-${poster.tone}`"
              :href="mediaLink(poster.media_type, poster.id)"
              role="listitem"
            >
              <div class="poster-media">
                <img v-if="poster.poster_url" :src="poster.poster_url" :alt="`${poster.title} 海报`" loading="lazy" decoding="async" />
                <div v-else class="poster-skeleton" aria-hidden="true" />
                <div class="poster-gradient" aria-hidden="true" />
              </div>
              <div class="poster-text">
                <div class="poster-title">{{ poster.title }}</div>
                <div v-if="poster.subtitle" class="poster-subtitle">{{ poster.subtitle }}</div>
              </div>
            </a>
          </div>
          <div v-else class="empty" role="status">
            <IconRecommendations class="empty-icon" aria-hidden="true" />
            <div class="empty-text">暂无相关推荐</div>
          </div>
        </div>
      </section>

      <section class="section detail-section" aria-labelledby="video-title">
        <div class="section-header">
          <span class="section-icon" aria-hidden="true">🎥</span>
          <h2 class="section-title" id="video-title">视频预览</h2>
        </div>
        <div class="section-body">
          <div v-if="item.videos.length" class="video-grid" role="list">
            <div v-for="video in item.videos.slice(0, 2)" :key="video.key" class="video-card" role="listitem">
              <div class="video-thumbnail" role="button" tabindex="0" :aria-label="`播放视频: ${video.name}`" @click="onPlayVideo(video.key)">
                <iframe
                  v-if="playingVideos[video.key]"
                  :src="`https://www.youtube.com/embed/${video.key}?autoplay=1&rel=0&modestbranding=1&playsinline=1`"
                  title="视频播放器"
                  frameborder="0"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowfullscreen
                />
                <template v-else>
                  <img :src="`https://img.youtube.com/vi/${video.key}/mqdefault.jpg`" :alt="video.name" loading="lazy" decoding="async" />
                  <div class="video-play-button" aria-hidden="true">
                    <svg viewBox="0 0 68 48" width="68" height="48">
                      <path
                        d="M66.52,7.74c-0.78-2.93-2.49-5.41-5.42-6.19C55.79,.13,34,0,34,0S12.21,.13,6.9,1.55 C3.97,2.33,2.27,4.81,1.48,7.74C0.06,13.05,0,24,0,24s0.06,10.95,1.48,16.26c0.78,2.93,2.49,5.41,5.42,6.19 C12.21,47.87,34,48,34,48s21.79-0.13,27.1-1.55c2.93-0.78,4.64-3.26,5.42-6.19C67.94,34.95,68,24,68,24S67.94,13.05,66.52,7.74z"
                        fill="#f00"
                      />
                      <path d="M 45,24 27,14 27,34" fill="#fff" />
                    </svg>
                  </div>
                </template>
              </div>
              <div class="video-content">
                <div class="video-title">{{ video.name }}</div>
                <div v-if="video.type" class="video-meta">{{ video.type }}<span v-if="video.official"> · 官方</span></div>
              </div>
            </div>
          </div>
          <div v-else class="empty" role="status">
            <div class="empty-icon">🎞️</div>
            <div class="empty-text">暂无视频资源</div>
          </div>
        </div>
      </section>
    </template>

    <div v-else class="empty" role="status">
      <div class="empty-icon">📄</div>
      <div class="empty-text">详情加载失败</div>
    </div>
  </div>
</template>
