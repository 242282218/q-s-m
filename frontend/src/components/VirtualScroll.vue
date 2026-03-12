<script setup lang="ts" generic="T extends { id: string | number }">
import { ref, computed, onMounted, onUnmounted, watch, nextTick, shallowRef } from 'vue';

// ============ 类型定义 ============
export interface VirtualScrollProps<T> {
  items: T[];
  itemHeight?: number | ((item: T, index: number) => number);
  containerHeight?: number;
  bufferSize?: number;
  estimatedItemHeight?: number;
  /** 是否启用虚拟滚动 */
  enabled?: boolean;
}

export interface VirtualScrollExpose {
  scrollTo: (position: number) => void;
  scrollToIndex: (index: number) => void;
  getScrollPosition: () => number;
  refresh: () => void;
}

// ============ Props 定义 ============
const props = withDefaults(defineProps<VirtualScrollProps<T>>(), {
  containerHeight: 400,
  bufferSize: 5,
  estimatedItemHeight: 100,
  enabled: true,
});

const emit = defineEmits<{
  itemRendered: [items: { item: T; index: number }[]];
  scroll: [position: number];
}>();

// ============ 状态管理 ============
const containerRef = ref<HTMLDivElement | null>(null);
const scrollTop = ref(0);
const measuredHeight = ref(0);

// 使用 shallowRef 优化性能，避免深度响应式
const itemHeights = shallowRef<Map<number, number>>(new Map());
const positionCache = ref<number[]>([]);

// ============ 计算属性 ============

// 判断是否为动态高度模式
const isDynamicHeight = computed(() => typeof props.itemHeight === 'function');

// 获取单个 item 的高度
const getItemHeight = (item: T, index: number): number => {
  if (typeof props.itemHeight === 'function') {
    return props.itemHeight(item, index);
  }
  return props.itemHeight ?? props.estimatedItemHeight;
};

// 计算总高度
const totalHeight = computed(() => {
  if (props.items.length === 0) return 0;

  if (!isDynamicHeight.value) {
    return props.items.length * (props.itemHeight ?? props.estimatedItemHeight);
  }

  // 动态高度：使用缓存的位置信息
  if (positionCache.value.length === props.items.length) {
    const lastIndex = props.items.length - 1;
    const lastPosition = positionCache.value[lastIndex];
    const lastHeight = itemHeights.value.get(lastIndex) ?? props.estimatedItemHeight;
    return lastPosition + lastHeight;
  }

  // 未计算时使用估算值
  return props.items.length * props.estimatedItemHeight;
});

// 计算可见范围
const visibleRange = computed(() => {
  if (!props.enabled) {
    return { startIndex: 0, endIndex: props.items.length };
  }
  return calculateVisibleRange(scrollTop.value);
});

// 计算可见 items - 使用 computed 缓存
const visibleItems = computed(() => {
  const { startIndex, endIndex } = visibleRange.value;

  if (startIndex >= endIndex || props.items.length === 0) {
    return [];
  }

  const items: { item: T; index: number; style: Record<string, string> }[] = [];

  for (let i = startIndex; i < endIndex && i < props.items.length; i++) {
    const item = props.items[i];
    const offset = getItemOffset(i);
    const height = getItemHeight(item, i);

    items.push({
      item,
      index: i,
      style: {
        position: 'absolute',
        top: `${offset}px`,
        left: '0',
        right: '0',
        height: isDynamicHeight.value ? 'auto' : `${height}px`,
        willChange: 'transform',
      },
    });
  }

  // 触发事件（使用 nextTick 避免阻塞渲染）
  if (items.length > 0) {
    nextTick(() => {
      emit(
        'itemRendered',
        items.map(({ item, index }) => ({ item, index }))
      );
    });
  }

  return items;
});

// ============ 核心算法 ============

// 获取 item 的偏移量
const getItemOffset = (index: number): number => {
  if (!isDynamicHeight.value) {
    return index * (props.itemHeight ?? props.estimatedItemHeight);
  }

  // 使用缓存的位置
  if (positionCache.value.length > index) {
    return positionCache.value[index];
  }

  // 计算位置
  let offset = 0;
  for (let i = 0; i < index && i < props.items.length; i++) {
    offset += itemHeights.value.get(i) ?? props.estimatedItemHeight;
  }
  return offset;
};

// 计算可见范围（支持动态高度）
const calculateVisibleRange = (scrollPos: number): { startIndex: number; endIndex: number } => {
  if (props.items.length === 0) {
    return { startIndex: 0, endIndex: 0 };
  }

  const containerHeight = measuredHeight.value || props.containerHeight;

  if (!isDynamicHeight.value) {
    // 固定高度模式
    const itemHeight = props.itemHeight ?? props.estimatedItemHeight;
    const startIndex = Math.floor(scrollPos / itemHeight);
    const visibleCount = Math.ceil(containerHeight / itemHeight);
    const endIndex = Math.min(startIndex + visibleCount + props.bufferSize * 2, props.items.length);
    return {
      startIndex: Math.max(0, startIndex - props.bufferSize),
      endIndex,
    };
  }

  // 动态高度模式：二分查找
  const offsets = positionCache.value;

  // 查找第一个可见的 item（startIndex）
  let startIndex = 0;
  let low = 0;
  let high = offsets.length - 1;
  const bufferHeight = props.estimatedItemHeight * props.bufferSize;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const itemTop = offsets[mid];
    const itemBottom = itemTop + (itemHeights.value.get(mid) ?? props.estimatedItemHeight);

    if (itemBottom < scrollPos - bufferHeight) {
      low = mid + 1;
    } else if (itemTop > scrollPos + containerHeight + bufferHeight) {
      high = mid - 1;
    } else {
      startIndex = Math.max(0, mid - props.bufferSize);
      break;
    }
  }

  // 查找最后一个可见的 item（endIndex）
  let endIndex = props.items.length;
  low = startIndex;
  high = offsets.length - 1;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const itemTop = offsets[mid];

    if (itemTop > scrollPos + containerHeight + bufferHeight) {
      endIndex = mid + props.bufferSize;
      high = mid - 1;
    } else {
      low = mid + 1;
    }
  }

  return {
    startIndex: Math.max(0, startIndex),
    endIndex: Math.min(props.items.length, endIndex),
  };
};

// 更新 item 高度（动态高度模式）
const updateItemHeight = (index: number, element: HTMLElement | null) => {
  if (!isDynamicHeight.value || !element) return;

  const actualHeight = element.getBoundingClientRect().height;
  const oldHeight = itemHeights.value.get(index);

  if (actualHeight !== oldHeight) {
    const newHeights = new Map(itemHeights.value);
    newHeights.set(index, actualHeight);
    itemHeights.value = newHeights;
    recalculatePositions();
  }
};

// 重新计算位置缓存
const recalculatePositions = () => {
  const offsets: number[] = [];
  let currentOffset = 0;

  for (let i = 0; i < props.items.length; i++) {
    offsets[i] = currentOffset;
    const height = itemHeights.value.get(i) ?? props.estimatedItemHeight;
    currentOffset += height;
  }

  positionCache.value = offsets;
};

// ============ 暴露的方法 ============

// 滚动到指定位置
const scrollTo = (position: number) => {
  if (containerRef.value) {
    containerRef.value.scrollTop = Math.max(
      0,
      Math.min(position, totalHeight.value - measuredHeight.value)
    );
  }
};

// 滚动到指定索引
const scrollToIndex = (index: number) => {
  if (index < 0 || index >= props.items.length) return;

  const position = getItemOffset(index);
  scrollTo(position);
};

// 获取当前滚动位置
const getScrollPosition = (): number => {
  return scrollTop.value;
};

// 刷新（重新计算高度等）
const refresh = () => {
  if (containerRef.value) {
    measuredHeight.value = containerRef.value.clientHeight;
  }

  if (isDynamicHeight.value) {
    itemHeights.value = new Map();
    recalculatePositions();
  }

  // 强制重新计算可见范围
  scrollTop.value = containerRef.value?.scrollTop ?? 0;
};

// ============ 事件处理 ============

// 使用 requestAnimationFrame 节流滚动事件
let rafId: number | null = null;
let lastScrollTop = 0;

const handleScroll = (e: Event) => {
  const target = e.target as HTMLElement;
  lastScrollTop = target.scrollTop;

  if (rafId !== null) return;

  rafId = requestAnimationFrame(() => {
    scrollTop.value = lastScrollTop;
    emit('scroll', lastScrollTop);
    rafId = null;
  });
};

// 监听 items 变化
watch(
  () => props.items.length,
  (newLength, oldLength) => {
    if (isDynamicHeight.value && newLength !== oldLength) {
      // items 数量变化时，重新计算位置
      recalculatePositions();
    }
  }
);

// 监听 items 内容变化（深度监听）
watch(
  () => props.items,
  () => {
    if (isDynamicHeight.value) {
      // 清理不存在 item 的高度缓存
      const newHeights = new Map<number, number>();
      itemHeights.value.forEach((height, index) => {
        if (index < props.items.length) {
          newHeights.set(index, height);
        }
      });
      itemHeights.value = newHeights;
      recalculatePositions();
    }
  },
  { deep: false }
);

// ============ 生命周期 ============

// ResizeObserver 监听容器高度变化
let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  if (containerRef.value) {
    measuredHeight.value = containerRef.value.clientHeight;
    containerRef.value.addEventListener('scroll', handleScroll, { passive: true });

    // 监听容器尺寸变化
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        measuredHeight.value = entry.contentRect.height;
      }
    });
    resizeObserver.observe(containerRef.value);
  }

  // 初始化位置缓存
  if (isDynamicHeight.value) {
    recalculatePositions();
  }
});

onUnmounted(() => {
  if (rafId !== null) {
    cancelAnimationFrame(rafId);
  }

  if (containerRef.value) {
    containerRef.value.removeEventListener('scroll', handleScroll);
  }

  resizeObserver?.disconnect();
  itemHeights.value = new Map();
  positionCache.value = [];
});

// ============ 暴露 API ============
defineExpose<VirtualScrollExpose>({
  scrollTo,
  scrollToIndex,
  getScrollPosition,
  refresh,
});
</script>

<template>
  <div
    v-if="enabled"
    ref="containerRef"
    class="virtual-scroll-container"
    :style="{ height: `${containerHeight}px`, overflow: 'auto' }"
  >
    <div
      class="virtual-scroll-content"
      :style="{
        height: `${totalHeight}px`,
        position: 'relative',
        width: '100%',
      }"
    >
      <div
        v-for="{ item, index, style } in visibleItems"
        :key="item.id"
        class="virtual-item"
        :style="style"
        @vue:mounted="updateItemHeight(index, $el as HTMLElement)"
        @vue:updated="updateItemHeight(index, $el as HTMLElement)"
      >
        <slot :item="item" :index="index" />
      </div>
    </div>
  </div>

  <!-- 禁用虚拟滚动时直接渲染所有 items -->
  <div
    v-else
    ref="containerRef"
    class="virtual-scroll-disabled"
    :style="{ height: `${containerHeight}px`, overflow: 'auto' }"
    @scroll="handleScroll"
  >
    <slot
      v-for="(item, index) in items"
      :key="item.id"
      :item="item"
      :index="index"
    />
  </div>
</template>

<style scoped>
.virtual-scroll-container {
  position: relative;
  width: 100%;
  contain: strict;
  will-change: scroll-position;
  overflow-anchor: none;
}

.virtual-scroll-content {
  will-change: height;
  position: relative;
}

.virtual-item {
  box-sizing: border-box;
  contain: layout style paint;
  overflow: hidden;
}

.virtual-scroll-disabled {
  position: relative;
  width: 100%;
}

/* 减少动画偏好 */
@media (prefers-reduced-motion: reduce) {
  .virtual-scroll-container {
    scroll-behavior: auto;
  }
}
</style>
