<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { getHomeFeed } from "@/api";
import { useToast } from "@/composables/useToast";
import type { HomeData, HomeHeroItem } from "@/types/api";

const { push } = useToast();

const loading = ref(false);
const feed = ref<HomeData | null>(null);
const activeHeroIndex = ref(0);
let autoplayTimer: number | null = null;

const activeHero = computed<HomeHeroItem | null>(() => {
  const list = feed.value?.hero_items || [];
  if (list.length === 0) {
    return null;
  }
  return list[activeHeroIndex.value] || null;
});

function mediaLink(mediaType: string, id: number) {
  return `/${mediaType}/${id}`;
}

function stopAutoplay() {
  if (autoplayTimer !== null) {
    window.clearInterval(autoplayTimer);
    autoplayTimer = null;
  }
}

function goTo(index: number) {
  const total = feed.value?.hero_items.length || 0;
  if (total === 0) {
    return;
  }
  if (index < 0 || index >= total) {
    return;
  }
  activeHeroIndex.value = index;
}

function nextHero() {
  const total = feed.value?.hero_items.length || 0;
  if (total <= 1) {
    return;
  }
  activeHeroIndex.value = (activeHeroIndex.value + 1) % total;
}

function prevHero() {
  const total = feed.value?.hero_items.length || 0;
  if (total <= 1) {
    return;
  }
  activeHeroIndex.value = (activeHeroIndex.value - 1 + total) % total;
}

function startAutoplay() {
  stopAutoplay();
  const total = feed.value?.hero_items.length || 0;
  if (total <= 1) {
    return;
  }
  autoplayTimer = window.setInterval(() => {
    nextHero();
  }, 3500);
}

async function loadHomeFeed() {
  loading.value = true;
  try {
    const res = await getHomeFeed();
    if (res.code !== 0) {
      push(res.message || "加载首页数据失败", "error");
      return;
    }
    feed.value = res.data;
    activeHeroIndex.value = 0;
    startAutoplay();
  } catch (error) {
    push(error instanceof Error ? error.message : "加载首页数据失败", "error");
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void loadHomeFeed();
});

onBeforeUnmount(() => {
  stopAutoplay();
});
</script>

<template>
  <div class="page">
    <section v-if="activeHero" class="hero-section" @mouseenter="stopAutoplay" @mouseleave="startAutoplay">
      <div class="hero-carousel">
        <div
          v-for="(hero, index) in feed?.hero_items || []"
          :key="`${hero.media_type}-${hero.id}`"
          class="hero-slide"
          :class="{ active: index === activeHeroIndex }"
        >
          <div class="hero-background">
            <img
              v-if="hero.backdrop_url || hero.poster_url"
              :src="hero.backdrop_url || hero.poster_url || ''"
              :alt="hero.title"
              :loading="index === 0 ? 'eager' : 'lazy'"
            />
            <div class="hero-gradient" aria-hidden="true" />
            <div class="hero-vignette" aria-hidden="true" />
          </div>

          <div class="hero-content">
            <span v-if="hero.vote && hero.vote >= 7" class="hero-badge">98% 匹配</span>
            <h1 class="hero-title">{{ hero.title }}</h1>
            <div class="hero-meta">
              <span v-if="hero.year" class="hero-meta-item">{{ hero.year }}</span>
              <span v-if="hero.vote" class="hero-meta-divider" aria-hidden="true" />
              <span v-if="hero.vote" class="hero-meta-item rating">⭐ {{ hero.vote.toFixed(1) }}</span>
              <span v-if="hero.runtime" class="hero-meta-divider" aria-hidden="true" />
              <span v-if="hero.runtime" class="hero-meta-item">{{ hero.runtime }} 分钟</span>
            </div>
            <div v-if="hero.genres.length" class="hero-tags">
              <span v-for="genre in hero.genres.slice(0, 4)" :key="genre" class="hero-tag">{{ genre }}</span>
            </div>
            <p v-if="hero.overview" class="hero-overview">{{ hero.overview }}</p>
            <div class="hero-actions">
              <a :href="mediaLink(hero.media_type, hero.id)" class="hero-btn hero-btn-primary">
                <span class="hero-btn-icon">▶</span>
                <span>查看详情</span>
              </a>
              <a :href="mediaLink(hero.media_type, hero.id)" class="hero-btn hero-btn-secondary">
                <span class="hero-btn-icon">ⓘ</span>
                <span>更多信息</span>
              </a>
            </div>
          </div>
        </div>
      </div>

      <div class="hero-carousel-controls">
        <button class="hero-carousel-btn hero-carousel-prev" aria-label="上一张" @click="prevHero">‹</button>
        <button class="hero-carousel-btn hero-carousel-next" aria-label="下一张" @click="nextHero">›</button>
      </div>

      <div class="hero-carousel-indicators" role="tablist" aria-label="轮播指示器">
        <button
          v-for="(_, index) in feed?.hero_items || []"
          :key="`indicator-${index}`"
          class="hero-indicator"
          :class="{ active: index === activeHeroIndex }"
          :aria-selected="index === activeHeroIndex"
          :aria-label="`切换到第 ${index + 1} 张`"
          @click="goTo(index)"
        >
          <span class="hero-indicator-progress" />
        </button>
      </div>
    </section>

    <div v-if="loading" class="loading">
      <div class="loading-spinner" />
      <span>加载中...</span>
    </div>
    <div v-else-if="!feed" class="empty" role="status">
      <div class="empty-icon">📺</div>
      <div class="empty-text">首页数据加载失败</div>
      <div class="empty-hint">请检查后端 TMDB 配置后重试</div>
      <button class="btn btn-primary" @click="loadHomeFeed">重新加载</button>
    </div>

    <template v-else>
      <template v-for="section in feed?.section_order || []" :key="section.key">
        <section class="content-row section" :aria-labelledby="`section-${section.key}`">
          <div class="row-header">
            <h2 class="row-title" :id="`section-${section.key}`">
              {{ section.title }}
              <span v-if="section.tag" class="row-tag">{{ section.tag }}</span>
            </h2>
          </div>

          <div class="posters-row" role="list">
            <template v-if="(feed?.sections?.[section.key] || []).length > 0">
              <a
                v-for="poster in feed?.sections?.[section.key] || []"
                :key="`${section.key}-${poster.media_type}-${poster.id}`"
                class="poster-card"
                :class="`tone-${poster.tone}`"
                :href="mediaLink(poster.media_type, poster.id)"
              >
                <div class="poster-media">
                  <img v-if="poster.poster_url" :src="poster.poster_url" :alt="`${poster.title} 海报`" loading="lazy" />
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
              <div class="empty-icon">😥</div>
              <div class="empty-text">暂无数据</div>
            </div>
          </div>
        </section>
      </template>
    </template>
  </div>
</template>
