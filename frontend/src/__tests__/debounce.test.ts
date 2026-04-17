import { afterEach, describe, expect, it, vi } from 'vitest';

import { debounce, debounceWithImmediate } from '@/utils/debounce';

describe('debounce utilities', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('debounce should only invoke the latest call after the wait window', () => {
    vi.useFakeTimers();
    const callback = vi.fn();
    const debounced = debounce(callback, 100);

    debounced('first');
    debounced('second');

    expect(callback).not.toHaveBeenCalled();

    vi.advanceTimersByTime(99);
    expect(callback).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback).toHaveBeenCalledWith('second');
  });

  it('debounceWithImmediate should support both immediate and trailing-only modes', () => {
    vi.useFakeTimers();

    const immediateCallback = vi.fn();
    const immediateDebounced = debounceWithImmediate(immediateCallback, 100);

    immediateDebounced('first');
    immediateDebounced('second');

    expect(immediateCallback).toHaveBeenCalledTimes(1);
    expect(immediateCallback).toHaveBeenCalledWith('first');

    vi.advanceTimersByTime(100);
    immediateDebounced('third');

    expect(immediateCallback).toHaveBeenCalledTimes(2);
    expect(immediateCallback).toHaveBeenLastCalledWith('third');

    const trailingCallback = vi.fn();
    const trailingDebounced = debounceWithImmediate(trailingCallback, 100, false);

    trailingDebounced('alpha');
    trailingDebounced('beta');

    expect(trailingCallback).not.toHaveBeenCalled();

    vi.advanceTimersByTime(100);
    expect(trailingCallback).toHaveBeenCalledTimes(1);
    expect(trailingCallback).toHaveBeenCalledWith('beta');
  });
});
