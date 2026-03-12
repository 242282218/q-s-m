<script setup lang="ts">
import { reactive } from 'vue';
import type { DetailVideo } from '@/types/api';
import IconVideo from '@/components/Icons/IconVideo.vue';
import IconFilm from '@/components/Icons/IconFilm.vue';

defineProps<{
  videos: DetailVideo[];
}>();

const playingVideos = reactive<Record<string, boolean>>({});

function onPlayVideo(videoKey: string) {
  playingVideos[videoKey] = true;
}
</script>

<template>
  <section class="section detail-section" aria-labelledby="video-title">
    <div class="section-header">
      <IconVideo class="section-icon" aria-hidden="true" />
      <h2 class="section-title" id="video-title">视频预览</h2>
    </div>
    <div class="section-body">
      <div v-if="videos.length" class="video-grid" role="list">
        <div
          v-for="video in videos.slice(0, 2)"
          :key="video.key"
          class="video-card"
          role="listitem"
        >
          <div
            class="video-thumbnail"
            role="button"
            tabindex="0"
            :aria-label="`播放视频：${video.name}`"
            @click="onPlayVideo(video.key)"
            @keydown.enter="onPlayVideo(video.key)"
            @keydown.space.prevent="onPlayVideo(video.key)"
          >
            <iframe
              v-if="playingVideos[video.key]"
              :src="`https://www.youtube.com/embed/${video.key}?autoplay=1&rel=0&modestbranding=1&playsinline=1`"
              title="视频播放器"
              frameborder="0"
              allow="
                accelerometer;
                autoplay;
                clipboard-write;
                encrypted-media;
                gyroscope;
                picture-in-picture;
              "
              allowfullscreen
              sandbox="allow-scripts allow-same-origin allow-presentation"
            />
            <template v-else>
              <img
                :src="`https://img.youtube.com/vi/${video.key}/mqdefault.jpg`"
                :alt="video.name"
                loading="lazy"
                decoding="async"
              />
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
            <div v-if="video.type" class="video-meta">
              {{ video.type }}<span v-if="video.official"> · 官方</span>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty" role="status">
        <IconFilm class="empty-icon" aria-hidden="true" />
        <div class="empty-text">暂无视频资源</div>
      </div>
    </div>
  </section>
</template>
