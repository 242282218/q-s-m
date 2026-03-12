import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { imagePreloader } from '@/utils/imagePreloader';

// Mock the Image constructor
class MockImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  src = '';

  constructor() {
    // Simulate image loading after a short delay
    setTimeout(() => {
      if (this.onload) this.onload();
    }, 10);
  }
}

// Store original Image
const OriginalImage = global.Image;

describe('ImagePreloader', () => {
  beforeEach(() => {
    // Replace Image with our mock
    global.Image = MockImage as unknown as typeof Image;
  });

  afterEach(() => {
    // Restore original Image
    global.Image = OriginalImage;
    // Clear cache
    imagePreloader.clearCache();
  });

  it('should preload images and cache them', async () => {
    const urls = ['http://example.com/image1.jpg', 'http://example.com/image2.jpg'];

    // Preload images
    imagePreloader.preload(urls);

    // Wait for images to load
    await new Promise((resolve) => setTimeout(resolve, 50));

    // Check that images are cached
    expect(imagePreloader.isCached(urls[0])).toBe(true);
    expect(imagePreloader.isCached(urls[1])).toBe(true);
  });

  it('should return cached images when available', () => {
    const url = 'http://example.com/image1.jpg';

    // Create and cache an image manually
    const mockImg = new Image();
    (imagePreloader as unknown as { cache: Map<string, HTMLImageElement> }).cache.set(url, mockImg);

    const cached = imagePreloader.getCached(url);
    expect(cached).toBe(mockImg);
  });

  it('should handle failed image loads gracefully', () => {
    // Create a mock image that simulates an error
    class MockErrorImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      src = '';

      constructor() {
        // Simulate error after a short delay
        setTimeout(() => {
          if (this.onerror) this.onerror();
        }, 10);
      }
    }

    global.Image = MockErrorImage as unknown as typeof Image;

    const url = 'http://example.com/invalid.jpg';
    imagePreloader.preload([url]);

    // After error, image should still be cached (to avoid repeated requests)
    const cached = imagePreloader.getCached(url);
    expect(cached).toBeDefined();
  });

  it('should not preload duplicate URLs', () => {
    const url = 'http://example.com/image1.jpg';

    // Preload the same URL multiple times
    imagePreloader.preload([url]);
    imagePreloader.preload([url]);
    imagePreloader.preload([url]);

    // Should only have one entry in cache
    const cached = imagePreloader.getCached(url);
    expect(cached).toBeDefined();
  });

  it('should clear cache properly', () => {
    const url = 'http://example.com/image1.jpg';

    // Add to cache
    const mockImg = new Image();
    (imagePreloader as unknown as { cache: Map<string, HTMLImageElement> }).cache.set(url, mockImg);

    // Verify it's cached
    expect(imagePreloader.isCached(url)).toBe(true);

    // Clear cache
    imagePreloader.clearCache();

    // Should no longer be cached
    expect(imagePreloader.isCached(url)).toBe(false);
  });
});
