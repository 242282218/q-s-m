<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from "vue";
import IconChevronLeft from "@/components/Icons/IconChevronLeft.vue";
import IconChevronRight from "@/components/Icons/IconChevronRight.vue";

interface Props {
  ariaLabel?: string;
}

const props = defineProps<Props>();

const scrollContainer = ref<HTMLDivElement | null>(null);
const scrollLeft = ref(0);
const maxScrollLeft = ref(0);
const canScrollLeft = computed(() => scrollLeft.value > 0);
const canScrollRight = computed(() => scrollLeft.value < maxScrollLeft.value - 1);
const animationFrameId = ref<number | null>(null);

function getComputedStyleValue(property: string): number {
  const value = getComputedStyle(document.documentElement).getPropertyValue(property);
  return parseFloat(value) || 0;
}

// 使用 requestAnimationFrame 优化性能
function smoothScrollTo(targetScrollLeft: number) {
  const container = scrollContainer.value;
  if (!container) return;

  // 取消之前的动画
  if (animationFrameId.value !== null) {
    cancelAnimationFrame(animationFrameId.value);
    animationFrameId.value = null;
  }

  const startScrollLeft = container.scrollLeft;
  const distance = targetScrollLeft - startScrollLeft;
  const duration = 400; // 动画持续时间 ms
  const startTime = performance.now();

  // 自定义贝塞尔曲线 cubic-bezier(0.25, 0.1, 0.25, 1) - ease-out 变体
  function easeOutCubic(t: number): number {
    return 1 - Math.pow(1 - t, 3);
  }

  function animate(currentTime: number) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const easedProgress = easeOutCubic(progress);

    if (container) {
      container.scrollLeft = startScrollLeft + distance * easedProgress;
    }

    if (progress < 1) {
      animationFrameId.value = requestAnimationFrame(animate);
    } else {
      animationFrameId.value = null;
    }
  }

  animationFrameId.value = requestAnimationFrame(animate);
}

function scrollRight() {
  const container = scrollContainer.value;
  if (!container) return;

  const cardWidth = container.querySelector(".poster-card")?.getBoundingClientRect().width || 200;
  const gap = getComputedStyleValue("--spacing-3") || 12;
  const scrollAmount = Math.floor(container.clientWidth / (cardWidth + gap)) * (cardWidth + gap);
  const targetScrollLeft = Math.min(scrollLeft.value + scrollAmount, maxScrollLeft.value);
  
  smoothScrollTo(targetScrollLeft);
}

function scrollToLeft() {
  const container = scrollContainer.value;
  if (!container) return;

  const cardWidth = container.querySelector(".poster-card")?.getBoundingClientRect().width || 200;
  const gap = getComputedStyleValue("--spacing-3") || 12;
  const scrollAmount = Math.floor(container.clientWidth / (cardWidth + gap)) * (cardWidth + gap);
  const targetScrollLeft = Math.max(scrollLeft.value - scrollAmount, 0);
  
  smoothScrollTo(targetScrollLeft);
}

function updateScrollState() {
  const container = scrollContainer.value;
  if (!container) return;
  
  scrollLeft.value = container.scrollLeft;
  maxScrollLeft.value = container.scrollWidth - container.clientWidth;
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    scrollToLeft();
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    scrollRight();
  }
}

let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  const container = scrollContainer.value;
  if (!container) return;

  // 初始状态更新
  updateScrollState();

  // 监听滚动事件
  container.addEventListener("scroll", updateScrollState, { passive: true });

  // 监听容器尺寸变化
  resizeObserver = new ResizeObserver(() => {
    updateScrollState();
  });
  resizeObserver.observe(container);

  // 监听键盘事件
  container.addEventListener("keydown", handleKeydown);
});

onUnmounted(() => {
  const container = scrollContainer.value;
  if (container) {
    container.removeEventListener("scroll", updateScrollState);
    container.removeEventListener("keydown", handleKeydown);
  }
  resizeObserver?.disconnect();
  
  // 清理动画帧
  if (animationFrameId.value !== null) {
    cancelAnimationFrame(animationFrameId.value);
    animationFrameId.value = null;
  }
});
</script>

<template>
  <div class="scrollable-row-wrapper">
    <!-- 左滑动按钮 -->
    <button
      v-show="canScrollLeft"
      class="scroll-btn scroll-btn-left"
      :class="{ 'is-disabled': !canScrollLeft }"
      :disabled="!canScrollLeft"
      :aria-label="`向左滑动${ariaLabel ? ' ' + ariaLabel : ''}`"
      @click="scrollToLeft"
    >
      <IconChevronLeft />
    </button>

    <!-- 内容区域 -->
    <div ref="scrollContainer" class="scrollable-row-container" tabindex="0" role="region" :aria-label="ariaLabel || '可滚动内容区域'">
      <slot />
    </div>

    <!-- 右滑动按钮 -->
    <button
      v-show="canScrollRight"
      class="scroll-btn scroll-btn-right"
      :class="{ 'is-disabled': !canScrollRight }"
      :disabled="!canScrollRight"
      :aria-label="`向右滑动${ariaLabel ? ' ' + ariaLabel : ''}`"
      @click="scrollRight"
    >
      <IconChevronRight />
    </button>
  </div>
</template>

<style scoped>
.scrollable-row-wrapper {
  position: relative;
  width: 100%;
}

.scrollable-row-container {
  display: flex;
  overflow-x: auto;
  gap: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-4);
  scroll-behavior: auto; /* 禁用原生平滑滚动，使用自定义动画 */
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.scrollable-row-container::-webkit-scrollbar {
  display: none;
}

/* 海报卡片样式 - 确保正确显示 */
.scrollable-row-container :slotted(*) {
  flex-shrink: 0;
}

.scrollable-row-container :slotted(.poster-card) {
  width: calc(50% - var(--spacing-2));
}

/* 滑动按钮基础样式 */
.scroll-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 44px;
  height: 44px;
  border-radius: var(--radius-full);
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: var(--color-text-primary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.25s cubic-bezier(0.25, 0.1, 0.25, 1);
  z-index: 10;
  box-shadow: 
    0 4px 12px rgba(0, 0, 0, 0.3),
    0 0 0 1px rgba(255, 255, 255, 0.05);
  opacity: 0;
  pointer-events: none;
}

.scrollable-row-wrapper:hover .scroll-btn {
  opacity: 1;
  pointer-events: auto;
}

.scroll-btn-left {
  left: var(--spacing-2);
}

.scroll-btn-right {
  right: var(--spacing-2);
}

/* 按钮悬停效果 */
.scroll-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.18);
  border-color: rgba(255, 255, 255, 0.35);
  transform: translateY(-50%) scale(1.08);
  box-shadow: 
    0 6px 20px rgba(0, 0, 0, 0.4),
    0 0 0 1px rgba(255, 255, 255, 0.1);
}

.scroll-btn:active:not(:disabled) {
  transform: translateY(-50%) scale(0.96);
  background: rgba(255, 255, 255, 0.12);
}

/* 禁用状态 */
.scroll-btn:disabled,
.scroll-btn.is-disabled {
  opacity: 0.3 !important;
  cursor: not-allowed;
  pointer-events: none;
}

/* 响应式卡片宽度 */
@media (min-width: 480px) {
  .scrollable-row-container :slotted(.poster-card) {
    width: calc(33.333% - var(--spacing-2));
  }
}

@media (min-width: 768px) {
  .scrollable-row-container :slotted(.poster-card) {
    width: calc(25% - var(--spacing-2));
  }
}

@media (min-width: 1024px) {
  .scrollable-row-container :slotted(.poster-card) {
    width: calc(20% - var(--spacing-2));
  }
}

@media (min-width: 1280px) {
  .scrollable-row-container :slotted(.poster-card) {
    width: calc(16.666% - var(--spacing-2));
  }
}

/* 移动端适配 */
@media (max-width: 767px) {
  .scroll-btn {
    width: 36px;
    height: 36px;
    opacity: 0.9;
    pointer-events: auto;
    background: rgba(0, 0, 0, 0.5);
  }

  .scroll-btn-left {
    left: var(--spacing-1);
  }

  .scroll-btn-right {
    right: var(--spacing-1);
  }

  .scrollable-row-wrapper:hover .scroll-btn {
    opacity: 0.9;
  }
}

/* 触摸设备优化 - 始终显示按钮 */
@media (hover: none) {
  .scroll-btn {
    opacity: 0.85;
    pointer-events: auto;
  }
}

/* 减少动画偏好 */
@media (prefers-reduced-motion: reduce) {
  .scroll-btn {
    transition: none;
  }
  
  .scrollable-row-container {
    scroll-behavior: auto;
  }
}
</style>
