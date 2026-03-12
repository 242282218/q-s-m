<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { useImageLoader, useIntersectionObserver } from '@/composables/useImageLoader';

interface Props {
  src: string;
  alt: string;
  placeholder?: string;
  srcset?: string;
  sizes?: string;
  loading?: 'eager' | 'lazy';
  rootMargin?: string;
  threshold?: number;
  objectFit?: 'cover' | 'contain' | 'fill' | 'none' | 'scale-down';
  objectPosition?: string;
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '/placeholder.svg',
  loading: 'lazy',
  rootMargin: '50px',
  threshold: 0,
  objectFit: 'cover',
  objectPosition: 'center',
});

const emit = defineEmits<{
  load: [];
  error: [error: Error];
}>();

const imgRef = ref<HTMLImageElement>();
const isInViewport = ref(false);

// 使用 Intersection Observer 检测元素是否进入视口
const { hasIntersected } = useIntersectionObserver(imgRef, {
  rootMargin: props.rootMargin,
  threshold: props.threshold,
  triggerOnce: true,
});

// 使用图片加载器
const { src, srcset, loaded, error, loading, observeElement, unobserveElement } = useImageLoader({
  src: props.src,
  placeholder: props.placeholder,
  srcset: props.srcset,
  lazy: props.loading === 'lazy',
});

// 当元素进入视口时开始加载图片
watch(hasIntersected, (intersected) => {
  if (intersected && props.loading === 'lazy') {
    isInViewport.value = true;
    if (imgRef.value) {
      observeElement(imgRef.value);
    }
  }
}, { immediate: true });

// 非懒加载模式直接加载
onMounted(() => {
  if (props.loading === 'eager' && imgRef.value) {
    observeElement(imgRef.value);
  }
});

onUnmounted(() => {
  unobserveElement();
});

// 监听加载状态变化
watch(loaded, (isLoaded) => {
  if (isLoaded) {
    emit('load');
  }
});

watch(error, (hasError) => {
  if (hasError) {
    emit('error', new Error(`Failed to load image: ${props.src}`));
  }
});
</script>

<template>
  <div
    class="lazy-image-wrapper"
    :class="{
      'is-loading': loading,
      'is-loaded': loaded,
      'has-error': error,
    }"
  >
    <img
      ref="imgRef"
      :src="src || placeholder"
      :alt="alt"
      :srcset="srcset"
      :sizes="sizes"
      :style="{
        objectFit,
        objectPosition,
      }"
      class="lazy-image"
      decoding="async"
    />
    <div v-if="loading" class="lazy-image-placeholder" aria-hidden="true">
      <slot name="placeholder">
        <div class="placeholder-skeleton" />
      </slot>
    </div>
    <div v-if="error" class="lazy-image-error" role="img" :aria-label="`加载失败: ${alt}`">
      <slot name="error">
        <div class="error-fallback">
          <span class="error-icon">🖼️</span>
          <span class="error-text">加载失败</span>
        </div>
      </slot>
    </div>
  </div>
</template>

<style scoped>
.lazy-image-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--color-bg-tertiary);
}

.lazy-image {
  width: 100%;
  height: 100%;
  display: block;
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.lazy-image-wrapper.is-loading .lazy-image {
  opacity: 0;
}

.lazy-image-wrapper.is-loaded .lazy-image {
  opacity: 1;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.lazy-image-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-tertiary);
}

.placeholder-skeleton {
  width: 100%;
  height: 100%;
  background: linear-gradient(
    110deg,
    rgba(255, 255, 255, 0.05) 0%,
    rgba(255, 255, 255, 0.1) 40%,
    rgba(255, 255, 255, 0.15) 50%,
    rgba(255, 255, 255, 0.1) 60%,
    rgba(255, 255, 255, 0.05) 100%
  );
  background-size: 300% 100%;
  animation: shimmer 1.8s ease-in-out infinite;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.lazy-image-error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-tertiary);
}

.error-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--color-text-secondary);
}

.error-icon {
  font-size: var(--font-size-2xl);
  opacity: 0.5;
}

.error-text {
  font-size: var(--font-size-xs);
  opacity: 0.7;
}
</style>
