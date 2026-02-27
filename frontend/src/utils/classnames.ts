/**
 * 条件类名合并工具函数
 * 用于合并多个类名，过滤掉 falsy 值
 * 
 * @example
 * cn('btn', 'btn-primary', isActive && 'active', isDisabled && 'disabled')
 * // => 'btn btn-primary active'
 */
export function cn(...classes: (string | boolean | undefined | null | number)[]): string {
  return classes
    .filter((cls) => {
      if (typeof cls === 'string' && cls.trim()) return true;
      if (typeof cls === 'number') return true;
      return false;
    })
    .join(' ')
    .trim();
}