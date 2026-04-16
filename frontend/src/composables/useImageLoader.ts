import { ref, watch, type Ref, onMounted, onUnmounted } from 'vue';

export interface UseImageLoaderOptions {
  src?: string;
  placeholder?: string;
  lazy?: boolean;
  srcset?: string;
  sizes?: string;
}

export interface UseImageLoaderReturn {
  src: Ref<string | null>;
  srcset: Ref<string | undefined>;
  loaded: Ref<boolean>;
  error: Ref<boolean>;
  loading: Ref<boolean>;
  loadImage: (src: string) => void;
  reset: () => void;
  observeElement: (element: HTMLElement) => void;
  unobserveElement: () => void;
}

// 全局图片加载队列管理器
class ImageLoadQueue {
  private static instance: ImageLoadQueue;
  private queue: Array<{
    src: string;
    resolve: () => void;
    reject: (error: Error) => void;
    abortController: AbortController;
  }> = [];
  private activeLoads = 0;
  private readonly maxConcurrent = 6;

  static getInstance(): ImageLoadQueue {
    if (!ImageLoadQueue.instance) {
      ImageLoadQueue.instance = new ImageLoadQueue();
    }
    return ImageLoadQueue.instance;
  }

  add(src: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const abortController = new AbortController();
      this.queue.push({ src, resolve, reject, abortController });
      this.processQueue();
    });
  }

  cancel(src: string): void {
    const index = this.queue.findIndex((item) => item.src === src);
    if (index > -1) {
      const item = this.queue[index];
      item.abortController.abort();
      item.reject(new Error('Cancelled'));
      this.queue.splice(index, 1);
    }
  }

  private processQueue(): void {
    if (this.activeLoads >= this.maxConcurrent || this.queue.length === 0) {
      return;
    }

    const item = this.queue.shift();
    if (!item) return;

    this.activeLoads++;

    const img = new Image();

    const cleanup = () => {
      this.activeLoads--;
      this.processQueue();
    };

    img.onload = () => {
      item.resolve();
      cleanup();
    };

    img.onerror = () => {
      item.reject(new Error(`Failed to load image: ${item.src}`));
      cleanup();
    };

    // 支持取消
    item.abortController.signal.addEventListener('abort', () => {
      img.src = '';
      cleanup();
    });

    img.src = item.src;
  }
}

const imageQueue = ImageLoadQueue.getInstance();

/**
 * 图片加载处理 Composable
 *
 * 功能：
 * - 支持懒加载（使用 Intersection Observer）
 * - 支持占位图
 * - 自动处理加载状态和错误
 * - 支持手动触发加载
 * - 支持并发加载限制（最大6个）
 * - 支持响应式图片（srcset）
 *
 * @example
 * ```ts
 * const { src, loaded, error, loading, observeElement, unobserveElement } = useImageLoader({
 *   src: 'https://example.com/image.jpg',
 *   placeholder: '/placeholder.jpg',
 *   lazy: true,
 *   srcset: '/image-400.jpg 400w, /image-800.jpg 800w',
 *   sizes: '(max-width: 600px) 400px, 800px'
 * });
 *
 * // 在模板中使用
 * // <img ref="imgRef" :src="src" :srcset="srcset" />
 * // onMounted(() => observeElement(imgRef.value))
 * ```
 */
export function useImageLoader(options: UseImageLoaderOptions = {}): UseImageLoaderReturn {
  const { src: initialSrc, placeholder, lazy = false, srcset: initialSrcset } = options;

  const src = ref<string | null>(initialSrc || null);
  const srcset = ref<string | undefined>(initialSrcset);
  const loaded = ref(false);
  const error = ref(false);
  const loading = ref(false);
  const placeholderSrc = ref(placeholder || null);

  let currentImageSrc: string | null = null;
  let observer: IntersectionObserver | null = null;
  let observedElement: HTMLElement | null = null;

  const loadImage = async (imageSrc: string) => {
    if (!imageSrc) {
      src.value = null;
      loaded.value = false;
      error.value = false;
      loading.value = false;
      return;
    }

    // 如果图片相同且已加载，跳过
    if (currentImageSrc === imageSrc && loaded.value) {
      return;
    }

    // 取消之前的加载
    if (currentImageSrc) {
      imageQueue.cancel(currentImageSrc);
    }

    loading.value = true;
    error.value = false;
    loaded.value = false;
    currentImageSrc = imageSrc;

    // 如果有占位图，先显示占位图
    if (placeholderSrc.value) {
      src.value = placeholderSrc.value;
    }

    try {
      await imageQueue.add(imageSrc);
      src.value = imageSrc;
      loaded.value = true;
      loading.value = false;
      error.value = false;
    } catch (err) {
      // 如果不是取消错误，则标记为错误
      if (!(err instanceof Error) || err.message !== 'Cancelled') {
        error.value = true;
        loading.value = false;
        loaded.value = false;
        // 加载失败时显示占位图
        if (placeholderSrc.value) {
          src.value = placeholderSrc.value;
        }
      }
    }
  };

  const reset = () => {
    if (currentImageSrc) {
      imageQueue.cancel(currentImageSrc);
      currentImageSrc = null;
    }
    unobserveElement();
    src.value = null;
    loaded.value = false;
    error.value = false;
    loading.value = false;
  };

  // 懒加载支持 - 观察指定元素
  const observeElement = (element: HTMLElement) => {
    if (!element) return;

    // 保存观察的元素
    observedElement = element;

    if (!lazy || typeof IntersectionObserver === 'undefined') {
      // 非懒加载模式，直接加载
      if (initialSrc) {
        loadImage(initialSrc);
      }
      return;
    }

    // 断开之前的观察
    if (observer) {
      observer.disconnect();
    }

    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            if (initialSrc) {
              loadImage(initialSrc);
            }
            // 加载后停止观察
            unobserveElement();
          }
        });
      },
      {
        rootMargin: '50px',
        threshold: 0,
      }
    );

    observer.observe(element);
  };

  // 停止观察元素
  const unobserveElement = () => {
    if (observer) {
      if (observedElement) {
        observer.unobserve(observedElement);
      }
      observer.disconnect();
      observer = null;
    }
    observedElement = null;
  };

  // 监听 src 变化
  watch(
    () => initialSrc,
    (newSrc) => {
      if (newSrc && !lazy) {
        loadImage(newSrc);
      }
    },
    { immediate: !lazy }
  );

  // 组件卸载时清理
  onUnmounted(() => {
    reset();
  });

  return {
    src,
    srcset,
    loaded,
    error,
    loading,
    loadImage,
    reset,
    observeElement,
    unobserveElement,
  };
}

/**
 * 简化的图片加载 Hook（适用于 template 直接使用）
 *
 * @example
 * ```vue
 * <script setup lang="ts">
 * const { handleImageLoad, handleImageError, isLoaded, hasError } = useSimpleImageLoader();
 * </script>
 *
 * <template>
 *   <img
 *     :src="imageUrl"
 *     @load="handleImageLoad"
 *     @error="handleImageError"
 *     :class="{ 'fade-in': isLoaded, 'hidden': hasError }"
 *   />
 * </template>
 * ```
 */
export function useSimpleImageLoader() {
  const isLoaded = ref(false);
  const hasError = ref(false);
  const isLoading = ref(false);

  const handleImageLoad = () => {
    isLoading.value = false;
    isLoaded.value = true;
    hasError.value = false;
  };

  const handleImageError = () => {
    isLoading.value = false;
    isLoaded.value = false;
    hasError.value = true;
  };

  const load = (src: string) => {
    if (!src) {
      hasError.value = true;
      return;
    }
    isLoading.value = true;
    isLoaded.value = false;
    hasError.value = false;
  };

  return {
    isLoaded,
    hasError,
    isLoading,
    handleImageLoad,
    handleImageError,
    load,
  };
}

/**
 * 使用 Intersection Observer 的懒加载 Hook
 *
 * @example
 * ```vue
 * <script setup lang="ts">
 * const imgRef = ref<HTMLImageElement>();
 * const { isVisible, hasIntersected } = useIntersectionObserver(imgRef, {
 *   rootMargin: '100px',
 *   threshold: 0.1
 * });
 * </script>
 *
 * <template>
 *   <img ref="imgRef" :src="hasIntersected ? actualSrc : placeholder" />
 * </template>
 * ```
 */
export interface UseIntersectionObserverOptions {
  rootMargin?: string;
  threshold?: number | number[];
  triggerOnce?: boolean;
}

export function useIntersectionObserver(
  elementRef: Ref<HTMLElement | null | undefined>,
  options: UseIntersectionObserverOptions = {}
) {
  const { rootMargin = '50px', threshold = 0, triggerOnce = true } = options;

  const isVisible = ref(false);
  const hasIntersected = ref(false);
  let observer: IntersectionObserver | null = null;

  const startObserving = () => {
    const element = elementRef.value;
    if (!element || typeof IntersectionObserver === 'undefined') {
      // 如果不支持 IntersectionObserver，默认显示
      isVisible.value = true;
      hasIntersected.value = true;
      return;
    }

    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            isVisible.value = true;
            hasIntersected.value = true;
            if (triggerOnce && observer) {
              observer.disconnect();
            }
          } else if (!triggerOnce) {
            isVisible.value = false;
          }
        });
      },
      { rootMargin, threshold }
    );

    observer.observe(element);
  };

  const stopObserving = () => {
    if (observer) {
      observer.disconnect();
      observer = null;
    }
  };

  onMounted(() => {
    startObserving();
  });

  onUnmounted(() => {
    stopObserving();
  });

  // 监听元素变化
  watch(elementRef, (newElement, oldElement) => {
    if (oldElement && observer) {
      observer.unobserve(oldElement);
    }
    if (newElement) {
      startObserving();
    }
  });

  return {
    isVisible,
    hasIntersected,
    startObserving,
    stopObserving,
  };
}
