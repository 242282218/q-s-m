/**
 * 图片预加载器
 * 实现图片懒加载和预加载优化
 * 包含错误处理和统计功能
 */
interface ImageLoaderStats {
  loaded: number;
  errors: number;
  cached: number;
  currentQueue: number;
}

class ImagePreloader {
  private cache = new Map<string, HTMLImageElement>();
  private readonly concurrentLimit = 6; // 限制并发请求数
  private queue: string[] = [];
  private activeCount = 0;
  private stats: ImageLoaderStats = {
    loaded: 0,
    errors: 0,
    cached: 0,
    currentQueue: 0
  };

  /**
   * 预加载图片
   * @param urls 图片URL数组
   */
  preload(urls: string[]): void {
    urls.forEach(url => {
      if (!this.cache.has(url) && !this.queue.includes(url)) {
        this.queue.push(url);
      }
    });
    this.stats.currentQueue = this.queue.length;
    this.processQueue();
  }

  private processQueue(): void {
    while (this.activeCount < this.concurrentLimit && this.queue.length > 0) {
      const url = this.queue.shift();
      if (url) {
        this.loadImage(url);
      }
    }
    this.stats.currentQueue = this.queue.length;
  }

  private loadImage(url: string): void {
    this.activeCount++;
    
    const img = new Image();
    
    img.onload = () => {
      try {
        this.cache.set(url, img);
        this.stats.loaded++;
        this.activeCount--;
        this.processQueue(); // 处理队列中的下一个
      } catch (error) {
        console.error('Error caching image:', url, error);
        this.stats.errors++;
        this.activeCount--;
        this.processQueue();
      }
    };
    
    img.onerror = () => {
      try {
        // 即使加载失败也缓存，避免重复请求
        this.cache.set(url, img);
        this.stats.errors++;
        this.activeCount--;
        this.processQueue(); // 处理队列中的下一个
      } catch (error) {
        console.error('Error caching failed image:', url, error);
        this.activeCount--;
        this.processQueue();
      }
    };
    
    img.src = url;
  }

  /**
   * 检查图片是否已缓存
   * @param url 图片URL
   * @returns 是否已缓存
   */
  isCached(url: string): boolean {
    const isCached = this.cache.has(url);
    if (isCached) {
      this.stats.cached++;
    }
    return isCached;
  }
  
  /**
   * 获取已缓存的图片
   * @param url 图片URL
   * @returns HTMLImageElement 或 undefined
   */
  getCached(url: string): HTMLImageElement | undefined {
    return this.cache.get(url);
  }
  
  /**
   * 清除缓存
   */
  clearCache(): void {
    try {
      this.cache.clear();
      this.queue = [];
      // 重置统计，但保留计数
      this.stats.currentQueue = 0;
    } catch (error) {
      console.error('Error clearing image cache:', error);
    }
  }
  
  /**
   * 获取统计信息
   * @returns 图片加载统计信息
   */
  getStats(): ImageLoaderStats {
    return { ...this.stats };
  }
}

export const imagePreloader = new ImagePreloader();

/**
 * 获取图片预加载器统计信息
 * @returns 统计信息
 */
export function getImageLoaderStats() {
  return imagePreloader.getStats();
}