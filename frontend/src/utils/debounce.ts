/**
 * 防抖函数
 * 延迟执行函数，在等待期间再次调用会重新计时
 * 
 * @example
 * const debouncedSearch = debounce((query: string) => {
 *   fetchResults(query);
 * }, 300);
 * 
 * debouncedSearch('test'); // 300ms 后执行
 * debouncedSearch('test2'); // 重新计时，300ms 后执行
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number,
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null;

  return (...args: Parameters<T>) => {
    if (timeout) {
      clearTimeout(timeout);
    }
    timeout = setTimeout(() => {
      func(...args);
    }, wait);
  };
}

/**
 * 带立即执行的防抖函数
 * 第一次调用立即执行，之后的调用防抖
 */
export function debounceWithImmediate<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number,
  immediate = true,
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null;

  return (...args: Parameters<T>) => {
    const shouldCallNow = immediate && !timeout;

    if (timeout) {
      clearTimeout(timeout);
    }

    timeout = setTimeout(() => {
      timeout = null;
      if (!immediate) {
        func(...args);
      }
    }, wait);

    if (shouldCallNow) {
      func(...args);
    }
  };
}