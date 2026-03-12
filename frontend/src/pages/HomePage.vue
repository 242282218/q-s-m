<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { getHomeFeed } from '@/api';
import ScrollableRow from '@/components/ScrollableRow.vue';
import { useCarousel } from '@/composables/useCarousel';
import { useToast } from '@/composables/useToast';
import { imagePreloader } from '@/utils/imagePreloader';
import type { HomeData, HomeHeroItem } from '@/types/api';
import IconVideoPlayer from '@/components/Icons/IconVideoPlayer.vue';
import IconInfo from '@/components/Icons/IconInfo.vue';
import IconStarRating from '@/components/Icons/IconStarRating.vue';
import IconEmptyMovie from '@/components/Icons/IconEmptyMovie.vue';
import IconEmptySad from '@/components/Icons/IconEmptySad.vue';

const { push } = useToast();

const loading = ref(false);
const feed = ref<HomeData | null>(null);
const failedImages = ref<Map<string, number>>(new Map());
const MAX_FAILED_IMAGES = 100;
const FAILED_IMAGE_TTL = 5 * 60 * 1000; // 5分钟

const heroItems = computed(() => feed.value?.hero_items || []);

const {
  activeIndex: activeHeroIndex,
  activeItem: activeHero,
  goTo,
  next: nextHero,
  prev: prevHero,
  startAutoplay,
  stopAutoplay,
} = useCarousel<HomeHeroItem>({
  items: heroItems,
  autoplayInterval: 3500,
});

function handleImageError(event: Event) {
  const img = event.target as HTMLImageElement;
  if (img?.src) {
    const now = Date.now();

    // 清理过期的失败记录
    for (const [url, timestamp] of failedImages.value.entries()) {
      if (now - timestamp > FAILED_IMAGE_TTL) {
        failedImages.value.delete(url);
      }
    }

    // 添加新的失败记录
    failedImages.value.set(img.src, now);

    // 如果超过最大数量，删除最旧的记录
    if (failedImages.value.size > MAX_FAILED_IMAGES) {
      const oldestUrl = failedImages.value.keys().next().value;
      if (oldestUrl) {
        failedImages.value.delete(oldestUrl);
      }
    }
  }
}

function mediaLink(mediaType: string, id: number) {
  return `/${mediaType}/${id}`;
}

async function loadHomeFeed() {
  loading.value = true;
  try {
    const res = await getHomeFeed();
    if (res.code !== 0) {
      push(res.message || '加载首页数据失败', 'error');
      return;
    }
    feed.value = res.data;
    startAutoplay();
    // 预加载英雄区域图片
    preloadHeroImages();
  } catch (error) {
    push(error instanceof Error ? error.message : '加载首页数据失败', 'error');
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void loadHomeFeed();
});

// 监听 feed 变化，预加载 hero_items 图片
const preloadHeroImages = () => {
  if (feed.value?.hero_items && feed.value.hero_items.length > 0) {
    const imageUrls = feed.value.hero_items
      .map((hero) => hero.backdrop_url || hero.poster_url)
      .filter((url): url is string => url != null);
    if (imageUrls.length > 0) {
      imagePreloader.preload(imageUrls);
    }
  }
};

onBeforeUnmount(() => {
  stopAutoplay();
});
</script>

<template>
  <div class="page">
    <section
      v-if="activeHero"
      class="hero-section"
      @mouseenter="stopAutoplay"
      @mouseleave="startAutoplay"
    >
      <div class="hero-carousel">
        <div
          v-for="(hero, index) in feed?.hero_items || []"
          :key="`${hero.media_type}-${hero.id}`"
          class="hero-slide"
          :class="{ active: index === activeHeroIndex }"
        >
          <div class="hero-background">
            <img
              v-if="
                (hero.backdrop_url || hero.poster_url) &&
                !failedImages.has(hero.backdrop_url || hero.poster_url || '')
              "
              :src="hero.backdrop_url || hero.poster_url || ''"
              :alt="hero.title"
              :loading="index === 0 ? 'eager' : 'lazy'"
              @error="handleImageError"
            />
            <div v-else class="hero-image-fallback" aria-hidden="true" />
            <div class="hero-gradient" aria-hidden="true" />
            <div class="hero-vignette" aria-hidden="true" />
          </div>

          <div class="hero-content">
            <span v-if="hero.vote && hero.vote >= 7" class="hero-badge"
              >{{ Math.round(hero.vote * 10) }}% 匹配</span
            >
            <h1 class="hero-title">{{ hero.title }}</h1>
            <div class="hero-meta">
              <span v-if="hero.year" class="hero-meta-item">{{ hero.year }}</span>
              <span v-if="hero.vote" class="hero-meta-divider" aria-hidden="true" />
              <span v-if="hero.vote" class="hero-meta-item rating">
                <IconStarRating class="hero-meta-icon" aria-hidden="true" />
                {{ hero.vote.toFixed(1) }}
              </span>
              <span v-if="hero.runtime" class="hero-meta-divider" aria-hidden="true" />
              <span v-if="hero.runtime" class="hero-meta-item">{{ hero.runtime }} 分钟</span>
            </div>
            <div v-if="hero.genres.length" class="hero-tags">
              <span v-for="genre in hero.genres.slice(0, 4)" :key="genre" class="hero-tag">{{
                genre
              }}</span>
            </div>
            <p v-if="hero.overview" class="hero-overview">{{ hero.overview }}</p>
            <div class="hero-actions">
              <a :href="mediaLink(hero.media_type, hero.id)" class="hero-btn hero-btn-primary">
                <IconVideoPlayer class="hero-btn-icon" aria-hidden="true" />
                <span>查看详情</span>
              </a>
              <a :href="mediaLink(hero.media_type, hero.id)" class="hero-btn hero-btn-secondary">
                <IconInfo class="hero-btn-icon" aria-hidden="true" />
                <span>更多信息</span>
              </a>
            </div>
          </div>
        </div>
      </div>

      <div class="hero-carousel-controls">
        <button class="hero-carousel-btn hero-carousel-prev" aria-label="上一张" @click="prevHero">
          ‹
        </button>
        <button class="hero-carousel-btn hero-carousel-next" aria-label="下一张" @click="nextHero">
          ›
        </button>
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

    <div v-if="loading" class="page">
      <section class="hero-section" aria-labelledby="loading-hero">
        <div class="hero-carousel">
          <div class="hero-slide">
            <div class="hero-background">
              <div class="poster-skeleton" aria-hidden="true" />
              <div class="hero-gradient" aria-hidden="true" />
              <div class="hero-vignette" aria-hidden="true" />
            </div>
            <div class="hero-content">
              <div class="hero-badge skeleton-text short" aria-hidden="true" />
              <h1 class="hero-title skeleton-text medium" aria-hidden="true" />
              <div class="hero-meta">
                <span class="hero-meta-item skeleton-text short" aria-hidden="true" />
                <span class="hero-meta-divider" aria-hidden="true" />
                <span class="hero-meta-item skeleton-text short" aria-hidden="true" />
              </div>
              <div class="hero-tags">
                <span class="hero-tag skeleton-text short" aria-hidden="true" />
                <span class="hero-tag skeleton-text short" aria-hidden="true" />
              </div>
              <p class="hero-overview skeleton-text medium" aria-hidden="true" />
              <div class="hero-actions">
                <a class="hero-btn hero-btn-primary skeleton-text" aria-hidden="true" />
                <a class="hero-btn hero-btn-secondary skeleton-text" aria-hidden="true" />
              </div>
            </div>
          </div>
        </div>
      </section>

      <div class="posters-grid skeleton-grid" aria-hidden="true">
        <div v-for="i in 6" :key="i" class="skeleton-card" />
      </div>
    </div>

    <div v-else-if="!feed" class="empty" role="status">
      <IconEmptyMovie class="empty-icon" aria-hidden="true" />
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

          <ScrollableRow :aria-label="section.title">
            <template v-if="(feed?.sections?.[section.key] || []).length > 0">
              <a
                v-for="poster in feed?.sections?.[section.key] || []"
                :key="`${section.key}-${poster.media_type}-${poster.id}`"
                class="poster-card"
                :class="`tone-${poster.tone}`"
                :href="mediaLink(poster.media_type, poster.id)"
              >
                <div class="poster-media">
                  <img
                    v-if="poster.poster_url && !failedImages.has(poster.poster_url)"
                    :src="poster.poster_url"
                    :alt="`${poster.title} 海报`"
                    loading="lazy"
                    @error="handleImageError"
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
              <IconEmptySad class="empty-icon" aria-hidden="true" />
              <div class="empty-text">暂无数据</div>
            </div>
          </ScrollableRow>
        </section>
      </template>
    </template>
  </div>
</template>
