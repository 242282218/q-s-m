<script setup lang="ts">
import type { PosterCard } from '@/types/api';
import IconRecommendations from '@/components/Icons/IconRecommendations.vue';
import ScrollableRow from '@/components/ScrollableRow.vue';

defineProps<{
  recommendations: PosterCard[];
}>();

function mediaLink(mediaType: string, id: number) {
  return `/${mediaType}/${id}`;
}
</script>

<template>
  <section class="section detail-section" aria-labelledby="recommend-title">
    <div class="section-header">
      <IconRecommendations class="section-icon" aria-hidden="true" />
      <h2 class="section-title" id="recommend-title">相关推荐</h2>
    </div>
    <div class="section-body">
      <div v-if="recommendations.length" class="recommend-scroll-wrapper" role="list">
        <ScrollableRow>
          <a
            v-for="poster in recommendations"
            :key="`${poster.media_type}-${poster.id}`"
            class="poster-card"
            :class="`tone-${poster.tone}`"
            :href="mediaLink(poster.media_type, poster.id)"
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
        </ScrollableRow>
      </div>
      <div v-else class="empty" role="status">
        <IconRecommendations class="empty-icon" aria-hidden="true" />
        <div class="empty-text">暂无相关推荐</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* ============================================
   相关推荐横向滚动布局
   ============================================ */
.recommend-scroll-wrapper {
  width: 100%;
}

/* 推荐卡片宽度 - 固定 220px */
.recommend-scroll-wrapper :deep(.poster-card) {
  flex-shrink: 0;
  width: 220px;
}

/* 保持原有样式 */
</style>
