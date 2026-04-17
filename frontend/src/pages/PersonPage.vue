<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';

import { getPersonPageData } from '@/api';
import { useToast } from '@/composables/useToast';
import type { PersonData } from '@/types/api';
import IconCredits from '@/components/Icons/IconCredits.vue';
import IconDocument from '@/components/Icons/IconDocument.vue';
import IconEmptyCredits from '@/components/Icons/IconEmptyCredits.vue';

const props = defineProps<{
  personId: number;
}>();

const { push } = useToast();

const loading = ref(false);
const person = ref<PersonData | null>(null);
let activePersonLoadId = 0;

const visibleCredits = computed(() => {
  return (person.value?.all_credits || []).slice(0, 10);
});

const hiddenCredits = computed(() => {
  return (person.value?.all_credits || []).slice(10);
});

function mediaLink(mediaType: string, id: number) {
  return `/${mediaType}/${id}`;
}

function isStalePersonLoad(loadId: number) {
  return loadId !== activePersonLoadId;
}

function resetPersonState() {
  loading.value = false;
  person.value = null;
}

async function loadPersonPage() {
  const loadId = ++activePersonLoadId;
  resetPersonState();

  if (!Number.isFinite(props.personId) || props.personId <= 0) {
    push('无效的人物参数', 'error');
    return;
  }
  loading.value = true;
  try {
    const res = await getPersonPageData(props.personId);
    if (isStalePersonLoad(loadId)) {
      return;
    }
    if (res.code !== 0) {
      push(res.message || '加载人物信息失败', 'error');
      return;
    }
    person.value = res.data;
  } catch (error) {
    if (!isStalePersonLoad(loadId)) {
      push(error instanceof Error ? error.message : '加载人物信息失败', 'error');
    }
  } finally {
    if (!isStalePersonLoad(loadId)) {
      loading.value = false;
    }
  }
}

watch(
  () => props.personId,
  () => {
    void loadPersonPage();
  }
);

onMounted(() => {
  void loadPersonPage();
});
</script>

<template>
  <div class="page page-padded" style="padding-top: 104px; padding-bottom: 64px">
    <div v-if="loading" class="page" role="status" aria-label="加载中">
      <section class="person-hero" aria-labelledby="loading-person">
        <div class="person-shell">
          <div class="person-avatar">
            <div class="poster-skeleton" aria-hidden="true" />
          </div>
          <div class="person-meta">
            <h1 class="person-name skeleton-text large" id="loading-person" aria-hidden="true" />
            <div class="person-sub">
              <span class="skeleton-text short" aria-hidden="true" />
              <span class="skeleton-text short" aria-hidden="true" />
              <span class="skeleton-text short" aria-hidden="true" />
            </div>
            <p class="person-bio skeleton-text long" aria-hidden="true" />
          </div>
        </div>
      </section>

      <section class="section detail-section" aria-labelledby="loading-credits">
        <div class="section-header">
          <IconCredits class="section-icon" aria-hidden="true" />
          <h2 class="section-title" id="loading-credits">代表作</h2>
        </div>
        <div class="section-body">
          <div class="recommend-grid skeleton-grid" role="list" aria-live="polite">
            <div v-for="i in 6" :key="i" class="skeleton-card" role="listitem" aria-hidden="true" />
          </div>
        </div>
      </section>
    </div>

    <template v-else-if="person">
      <section class="person-hero" aria-labelledby="person-name">
        <div class="person-shell">
          <div class="person-avatar">
            <img
              v-if="person.profile_url"
              :src="person.profile_url"
              :alt="person.name"
              loading="eager"
            />
            <div v-else class="poster-skeleton" aria-hidden="true" />
          </div>
          <div class="person-meta">
            <h1 class="person-name" id="person-name">{{ person.name }}</h1>
            <div class="person-sub">
              <span v-if="person.known_for">{{ person.known_for }}</span>
              <span v-if="person.birthday" class="dot" aria-hidden="true">•</span>
              <span v-if="person.birthday">{{ person.birthday }}</span>
              <span v-if="person.place_of_birth" class="dot" aria-hidden="true">•</span>
              <span v-if="person.place_of_birth">{{ person.place_of_birth }}</span>
            </div>
            <p v-if="person.biography" class="person-bio">{{ person.biography }}</p>
          </div>
        </div>
      </section>

      <section class="section detail-section" aria-labelledby="top-credits-title">
        <div class="section-header">
          <IconCredits class="section-icon" aria-hidden="true" />
          <h2 class="section-title" id="top-credits-title">代表作</h2>
        </div>
        <div class="section-body">
          <div v-if="person.top_credits.length" class="recommend-grid" role="list">
            <a
              v-for="poster in person.top_credits"
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
          </div>
          <div v-else class="empty" role="status">
            <IconEmptyCredits class="empty-icon" aria-hidden="true" />
            <div class="empty-text">暂无代表作</div>
          </div>
        </div>
      </section>

      <section class="section detail-section" aria-labelledby="all-credits-title">
        <div class="section-header">
          <IconDocument class="section-icon" aria-hidden="true" />
          <h2 class="section-title" id="all-credits-title">全部作品</h2>
        </div>
        <div class="section-body">
          <template v-if="person.all_credits.length">
            <div class="credits-list" role="list">
              <div
                v-for="credit in visibleCredits"
                :key="`${credit.media_type}-${credit.id}-${credit.role}`"
                class="credit-row"
                role="listitem"
              >
                <div class="credit-title">
                  <a :href="mediaLink(credit.media_type, credit.id)">{{ credit.title }}</a>
                </div>
                <div class="credit-meta">
                  <span v-if="credit.year">{{ credit.year }}</span>
                  <span v-if="credit.role" class="dot" aria-hidden="true">•</span>
                  <span v-if="credit.role">{{ credit.role }}</span>
                </div>
              </div>
            </div>

            <details v-if="hiddenCredits.length > 0" class="credits-collapse">
              <summary>展开全部 {{ hiddenCredits.length }} 部作品</summary>
              <div class="credits-list" role="list">
                <div
                  v-for="credit in hiddenCredits"
                  :key="`${credit.media_type}-${credit.id}-${credit.role}-hidden`"
                  class="credit-row"
                  role="listitem"
                >
                  <div class="credit-title">
                    <a :href="mediaLink(credit.media_type, credit.id)">{{ credit.title }}</a>
                  </div>
                  <div class="credit-meta">
                    <span v-if="credit.year">{{ credit.year }}</span>
                    <span v-if="credit.role" class="dot" aria-hidden="true">•</span>
                    <span v-if="credit.role">{{ credit.role }}</span>
                  </div>
                </div>
              </div>
            </details>
          </template>

          <div v-else class="empty" role="status">
            <IconDocument class="empty-icon" aria-hidden="true" />
            <div class="empty-text">暂无作品记录</div>
          </div>
        </div>
      </section>
    </template>

    <div v-else class="empty" role="status">
      <IconEmptyCredits class="empty-icon" aria-hidden="true" />
      <div class="empty-text">人物信息加载失败</div>
    </div>
  </div>
</template>
