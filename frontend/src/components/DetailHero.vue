<script setup lang="ts">
import type { DetailItem } from '@/types/api';
import { useImageLoader } from '@/composables/useImageLoader';

interface DetailHeroProps {
  item?: DetailItem | null;
  loading?: boolean;
}

const props = defineProps<DetailHeroProps>();

const { src: backdropSrc, loaded: backdropLoaded } = useImageLoader({
  src: props.item?.backdrop_url || undefined,
  lazy: false,
});

const heroStyle = (item: DetailItem | null) => {
  const url = item?.backdrop_url;
  if (url && backdropLoaded.value) {
    return {
      backgroundImage: `linear-gradient(180deg, rgba(10,10,10,0.7), rgba(10,10,10,0.9)), url('${url}')`,
    };
  }
  return {
    background:
      'linear-gradient(135deg, var(--color-bg-secondary) 0%, var(--color-bg-primary) 100%)',
  };
};
</script>

<template>
  <!-- 详情模式 -->
  <section
    v-if="item && !loading"
    class="detail-hero"
    aria-labelledby="detail-title"
    :style="heroStyle(item)"
  >
    <div class="detail-shell">
      <div class="detail-poster">
        <img
          v-if="item.poster_url"
          :src="item.poster_url"
          :alt="`${item.title} 海报`"
          loading="eager"
        />
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
          <span v-for="genre in item.genres" :key="genre" class="tag" role="listitem">{{
            genre
          }}</span>
        </div>
        <p v-if="item.tagline" class="detail-tagline">"{{ item.tagline }}"</p>
        <p v-if="item.overview" class="detail-overview">{{ item.overview }}</p>
      </div>
    </div>
  </section>

  <!-- 加载状态 -->
  <section
    v-if="loading || !item"
    class="detail-hero"
    aria-labelledby="loading-hero"
    :style="{
      background:
        'linear-gradient(135deg, var(--color-bg-secondary) 0%, var(--color-bg-primary) 100%)',
    }"
  >
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
</template>
