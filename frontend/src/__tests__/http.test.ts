import { describe, it, expect, vi, beforeEach } from 'vitest';
import { request } from '@/lib/http';

vi.mock('@/lib/http', () => ({
  request: vi.fn(),
}));

describe('HTTP Layer Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should handle successful GET request', async () => {
    const mockData = { success: true, data: { items: [] } };
    vi.mocked(request).mockResolvedValue(mockData);

    const result = await request('/api/collections');
    expect(result).toEqual(mockData);
    expect(request).toHaveBeenCalledWith('/api/collections');
  });

  it('should handle POST request with body', async () => {
    const mockData = { success: true, data: { created: true } };
    vi.mocked(request).mockResolvedValue(mockData);

    const body = { title: 'Test' };
    const result = await request('/api/collections', { method: 'POST', body });
    expect(result).toEqual(mockData);
  });

  it('should handle network errors', async () => {
    vi.mocked(request).mockRejectedValue(new Error('Network error'));

    await expect(request('/api/test')).rejects.toThrow('Network error');
  });
});
