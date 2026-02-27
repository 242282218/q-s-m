<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, type PropType } from 'vue';

interface Item {
  id: number | string;
  [key: string]: any;
}

const props = defineProps({
  items: {
    type: Array as PropType<Item[]>,
    required: true
  },
  itemHeight: {
    type: Number,
    default: 100
  },
  containerHeight: {
    type: Number,
    default: 400
  }
});

const emit = defineEmits(['itemRendered']);

const scrollTop = ref(0);
const containerRef = ref<HTMLDivElement>();

// 计算可视区域的起始和结束索引
const visibleRange = computed(() => {
  const startIndex = Math.floor(scrollTop.value / props.itemHeight);
  const endIndex = Math.min(
    startIndex + Math.ceil(props.containerHeight / props.itemHeight) + 5, // 多渲染5个项目作为缓冲
    props.items.length
  );
  return { startIndex, endIndex };
});

// 计算偏移高度
const offsetHeight = computed(() => visibleRange.value.startIndex * props.itemHeight);

// 计算可见项
const visibleItems = computed(() => {
  return props.items.slice(
    visibleRange.value.startIndex,
    visibleRange.value.endIndex
  ).map((item, index) => ({
    item,
    index: visibleRange.value.startIndex + index
  }));
});

const handleScroll = (e: Event) => {
  scrollTop.value = (e.target as HTMLElement).scrollTop;
  emit('itemRendered', visibleItems.value);
};

onMounted(() => {
  containerRef.value?.addEventListener('scroll', handleScroll);
});

onUnmounted(() => {
  containerRef.value?.removeEventListener('scroll', handleScroll);
});
</script>

<template>
  <div 
    ref="containerRef"
    class="virtual-scroll-container"
    :style="{ height: `${containerHeight}px`, overflow: 'auto' }"
  >
    <div :style="{ height: `${offsetHeight}px` }" class="scroll-offset" />
    <div 
      v-for="visibleItem in visibleItems" 
      :key="visibleItem.index"
      :style="{ height: `${itemHeight}px` }"
      class="virtual-item"
    >
      <slot :item="visibleItem.item" :index="visibleItem.index" />
    </div>
  </div>
</template>

<style scoped>
.virtual-scroll-container {
  position: relative;
}

.scroll-offset {
  position: relative;
}

.virtual-item {
  position: absolute;
  left: 0;
  right: 0;
  width: 100%;
}
</style>