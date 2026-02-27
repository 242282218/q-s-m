<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { searchTmdbPosters } from "@/api";
import { useToast } from "@/composables/useToast";
import type { PosterCard } from "@/types/api";
import IconSearch from "@/components/Icons/IconSearch.vue";
import IconClock from "@/components/Icons/IconClock.vue";
import IconConfused from "@/components/Icons/IconConfused.vue";

const router = useRouter();
const route = useRoute();
const { push } = useToast();

const loading = ref(false);
const posters = ref<PosterCard[]>([]);
const searchHistory = ref<string[]>([]);

const query = computed(() => String(route.query.q || "").trim());
const titleText = computed(() => (query.value ? `"${query.value}" 的搜索结果` : "搜索影视"));

function mediaLink(mediaType: string, id: number) {
  return `/${mediaType}/${id}`;
}

function loadSearchHistory() {
  try {
    const history = localStorage.getItem("searchHistory");
    if (history) {
      searchHistory.value = JSON.parse(history);
    }
  } catch {
    searchHistory.value = [];
  }
}

function saveToHistory(query: string) {
  if (!query) return;
  const normalized = query.trim();
  searchHistory.value = [normalized, ...searchHistory.value.filter(q => q !== normalized)].slice(0, 10);
  try {
    localStorage.setItem("searchHistory", JSON.stringify(searchHistory.value));
  } catch {
    // ignore
  }
}

function clearHistory() {
  searchHistory.value = [];
  try {
    localStorage.removeItem("searchHistory");
  } catch {
    // ignore
  }
}

function useHistory(query: string) {
  void router.push({
    path: "/search",
    query: { q: query },
  });
}

async function runSearch() {
  if (!query.value) {
    posters.value = [];
    return;
  }
  loading.value = true;
  try {
    const res = await searchTmdbPosters(query.value);
    if (res.code !== 0) {
      push(res.message || "搜索失败", "error");
      return;
    }
    posters.value = res.data.posters || [];
    saveToHistory(query.value);
  } catch (error) {
    push(error instanceof Error ? error.message : "搜索失败", "error");
  } finally {
    loading.value = false;
  }
}

watch(
  () => route.fullPath,
  () => {
    void runSearch();
  },
);

onMounted(() => {
  void runSearch();
  loadSearchHistory();
});

onUnmounted(() => {
  // cleanup if needed
});
</script>

<template>
  <div class="page">
    <section class="section" aria-labelledby="search-results-title">
      <div class="section-header">
        <IconSearch class="section-icon" aria-hidden="true" />
        <h2 class="section-title" id="search-results-title">
          {{ titleText }}
        </h2>
      </div>

      <div v-if="loading" class="loading" role="status">
        <div class="loading-spinner" aria-hidden="true" />
        <span>搜索中...</span>
      </div>

      <template v-else-if="!query">
        <div class="empty" role="status">
          <IconSearch class="empty-icon" aria-hidden="true" />
          <div class="empty-text">请输入关键字开始搜索</div>
          <div class="empty-hint">支持搜索电影名称、演员、导演等</div>
          
          <div v-if="searchHistory.length > 0" class="search-history" role="region" aria-label="搜索历史">
            <div class="history-header">
              <span>历史记录</span>
              <button class="clear-btn" @click="clearHistory">清除</button>
            </div>
            <div class="history-list">
              <button
                v-for="(item, index) in searchHistory"
                :key="index"
                class="history-item"
                @click="useHistory(item)"
              >
                <IconClock class="history-icon" aria-hidden="true" />
                <span class="history-text">{{ item }}</span>
              </button>
            </div>
          </div>
          
          <div class="quick-tags" role="region" aria-label="快捷标签">
            <span class="tags-label">热门搜索：</span>
            <div class="tags-list">
              <button class="tag-item" @click="useHistory('电影')">电影</button>
              <button class="tag-item" @click="useHistory('剧集')">剧集</button>
              <button class="tag-item" @click="useHistory('科幻')">科幻</button>
              <button class="tag-item" @click="useHistory('动作')">动作</button>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="posters-grid" role="list">
          <template v-if="posters.length > 0">
            <a
              v-for="poster in posters"
              :key="`${poster.media_type}-${poster.id}`"
              class="poster-card"
              :class="`tone-${poster.tone}`"
              :href="mediaLink(poster.media_type, poster.id)"
              :aria-label="poster.subtitle ? `${poster.title} - ${poster.subtitle}` : poster.title"
              role="listitem"
            >
              <div class="poster-media">
                <img
                  v-if="poster.poster_url"
                  :src="poster.poster_url"
                  :alt="`${poster.title} 海报`"
                  loading="lazy"
                  decoding="async"
                />
                <div v-else class="poster-skeleton" aria-hidden="true" />
                <div class="poster-gradient" aria-hidden="true" />
              </div>
              <div class="poster-text">
                <div class="poster-title">{{ poster.title }}</div>
                <div v-if="poster.subtitle" class="poster-subtitle">{{ poster.subtitle }}</div>
              </div>
            </a>
          </template>

          <div v-else class="empty" role="status">
            <IconConfused class="empty-icon" aria-hidden="true" />
            <div class="empty-text">未找到相关结果</div>
            <div class="empty-hint">试试其他关键词，或检查拼写是否正确</div>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

