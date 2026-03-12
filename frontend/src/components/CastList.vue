<script setup lang="ts">
import type { DetailCastMember } from '@/types/api';
import IconUsers from '@/components/Icons/IconUsers.vue';
import IconUser from '@/components/Icons/IconUser.vue';
import ScrollableRow from '@/components/ScrollableRow.vue';
import { useSimpleImageLoader } from '@/composables/useImageLoader';

defineProps<{
  cast: DetailCastMember[];
}>();

const { handleImageLoad, handleImageError, isLoaded, hasError } = useSimpleImageLoader();
</script>

<template>
  <section class="section detail-section" aria-labelledby="cast-title">
    <div class="section-header">
      <IconUsers class="section-icon" aria-hidden="true" />
      <h2 class="section-title" id="cast-title">演员阵容</h2>
    </div>
    <div class="section-body">
      <div v-if="cast.length" class="cast-scroll-wrapper" role="list">
        <ScrollableRow>
          <a
            v-for="castMember in cast"
            :key="castMember.id"
            class="cast-card"
            :href="`/person/${castMember.id}`"
            role="listitem"
          >
            <div class="cast-avatar">
              <img
                v-if="castMember.profile_url"
                :src="castMember.profile_url"
                :alt="castMember.name"
                loading="lazy"
                decoding="async"
                @load="handleImageLoad"
                @error="handleImageError"
                :class="{ 'fade-in': isLoaded, 'hidden': hasError }"
              />
              <div v-else class="poster-skeleton" aria-hidden="true" />
            </div>
            <div class="cast-name">{{ castMember.name }}</div>
            <div v-if="castMember.character" class="cast-role">{{ castMember.character }}</div>
          </a>
        </ScrollableRow>
      </div>
      <div v-else class="empty" role="status">
        <IconUser class="empty-icon" aria-hidden="true" />
        <div class="empty-text">暂无演员信息</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* ============================================
   演员阵容横向滚动布局
   ============================================ */
.cast-scroll-wrapper {
  width: 100%;
}

/* 演员卡片 */
.cast-card {
  flex-shrink: 0;
  width: 140px;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.05) 0%,
    rgba(255, 255, 255, 0.02) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-xl);
  overflow: hidden;
  transition: all var(--transition-fast);
  text-decoration: none;
  color: inherit;
}

.cast-card:hover {
  transform: translateY(-4px);
  border-color: rgba(255, 255, 255, 0.15);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.cast-avatar {
  position: relative;
  aspect-ratio: 2/3;
  overflow: hidden;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.03) 0%,
    rgba(255, 255, 255, 0.01) 100%
  );
}

.cast-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--transition-normal);
}

.cast-card:hover .cast-avatar img {
  transform: scale(1.05);
}

.cast-name {
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cast-role {
  padding: 0 var(--spacing-3) var(--spacing-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.poster-skeleton {
  width: 100%;
  height: 100%;
  background: linear-gradient(
    110deg,
    rgba(255, 255, 255, 0.05) 0%,
    rgba(255, 255, 255, 0.08) 50%,
    rgba(255, 255, 255, 0.05) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.fade-in {
  animation: fadeIn 0.3s ease-in;
}

.hidden {
  opacity: 0;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
</style>
