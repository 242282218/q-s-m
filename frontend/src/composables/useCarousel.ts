import { computed, ref, type ComputedRef, type Ref } from "vue";

export interface CarouselItem {
  id: number | string;
}

export interface UseCarouselOptions<T extends CarouselItem> {
  items: Ref<T[]>;
  autoplayInterval?: number;
}

export interface UseCarouselReturn<T extends CarouselItem> {
  activeIndex: Ref<number>;
  activeItem: ComputedRef<T | null>;
  goTo: (index: number) => void;
  next: () => void;
  prev: () => void;
  startAutoplay: () => void;
  stopAutoplay: () => void;
}

export function useCarousel<T extends CarouselItem>({
  items,
  autoplayInterval = 3500,
}: UseCarouselOptions<T>): UseCarouselReturn<T> {
  const activeIndex = ref(0);
  let autoplayTimer: number | null = null;

  const activeItem = computed<T | null>(() => {
    const list = items.value || [];
    if (list.length === 0) {
      return null;
    }
    return list[activeIndex.value] || null;
  });

  function stopAutoplay() {
    if (autoplayTimer !== null) {
      window.clearInterval(autoplayTimer);
      autoplayTimer = null;
    }
  }

  function goTo(index: number) {
    const total = items.value?.length || 0;
    if (total === 0) {
      return;
    }
    if (index < 0 || index >= total) {
      return;
    }
    activeIndex.value = index;
  }

  function next() {
    const total = items.value?.length || 0;
    if (total <= 1) {
      return;
    }
    activeIndex.value = (activeIndex.value + 1) % total;
  }

  function prev() {
    const total = items.value?.length || 0;
    if (total <= 1) {
      return;
    }
    activeIndex.value = (activeIndex.value - 1 + total) % total;
  }

  function startAutoplay() {
    stopAutoplay();
    const total = items.value?.length || 0;
    if (total <= 1) {
      return;
    }
    autoplayTimer = window.setInterval(() => {
      next();
    }, autoplayInterval);
  }

  return {
    activeIndex,
    activeItem,
    goTo,
    next,
    prev,
    startAutoplay,
    stopAutoplay,
  };
}
