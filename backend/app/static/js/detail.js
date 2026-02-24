/**
 * 详情页 JavaScript
 * 处理夸克资源搜索、收藏、转存等功能
 * 
 * @module detail
 * @description 提供影视详情页的资源搜索、收藏管理、视频播放等功能
 */

/** API 配置常量 */
const API_CONFIG = {
    timeout: 10000,
    maxRetries: 2,
    retryDelay: 1000
};

/** 防止重复请求的请求标识集合 */
const pendingRequests = new Set();

/**
 * 带超时和重试的 fetch 封装
 * 
 * @param {string} url - 请求地址
 * @param {RequestInit} options - fetch 选项
 * @param {number} retryCount - 当前重试次数
 * @returns {Promise<Response>} 响应对象
 * @throws {Error} 超时或网络错误
 */
async function fetchWithRetry(url, options = {}, retryCount = 0) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.timeout);
    
    try {
        const response = await fetch(url, { ...options, signal: controller.signal });
        clearTimeout(timeoutId);
        return response;
    } catch (error) {
        clearTimeout(timeoutId);
        if (retryCount < API_CONFIG.maxRetries && error.name !== 'AbortError') {
            console.warn(`[fetchWithRetry] 请求失败，正在重试 (${retryCount + 1}/${API_CONFIG.maxRetries}):`, error.message);
            await new Promise(resolve => setTimeout(resolve, API_CONFIG.retryDelay));
            return fetchWithRetry(url, options, retryCount + 1);
        }
        console.error('[fetchWithRetry] 请求最终失败:', error.message);
        throw error;
    }
}

/**
 * 播放 YouTube 视频
 * 
 * @param {HTMLElement} thumbnail - 缩略图容器元素
 * @param {string} videoKey - YouTube 视频 ID
 */
function playVideo(thumbnail, videoKey) {
    if (!thumbnail || !videoKey) {
        console.error('[playVideo] 参数无效: thumbnail 或 videoKey 为空');
        return;
    }
    
    const card = thumbnail.closest('.video-card');
    if (!card) {
        console.error('[playVideo] 未找到父级 video-card 元素');
        return;
    }
    
    const thumbnailDiv = card.querySelector('.video-thumbnail');
    if (!thumbnailDiv) {
        console.error('[playVideo] 未找到 video-thumbnail 元素');
        return;
    }

    const iframe = document.createElement('iframe');
    iframe.src = `https://www.youtube.com/embed/${videoKey}?autoplay=1&rel=0&modestbranding=1&playsinline=1`;
    iframe.setAttribute('allow', 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture');
    iframe.setAttribute('allowfullscreen', '');
    iframe.setAttribute('frameborder', '0');
    iframe.setAttribute('title', '视频播放器');

    thumbnailDiv.innerHTML = '';
    thumbnailDiv.appendChild(iframe);
    thumbnailDiv.classList.add('video-playing');
}

/**
 * 搜索夸克资源
 * 
 * @param {number} retryCount - 当前重试次数
 * @returns {Promise<void>}
 */
async function searchQuarkResources(retryCount = 0) {
    const container = document.getElementById('quark-resources-container');
    const empty = document.getElementById('quark-empty');
    const list = document.getElementById('quark-resources-list');

    if (!container || !empty || !list) {
        console.error('[searchQuarkResources] 未找到必要的 DOM 元素');
        return;
    }

    empty.style.display = 'none';
    list.style.display = 'none';
    list.innerHTML = '';

    try {
        let response = await fetchWithRetry(`/api/quark/search/tmdb/${window.itemId}?media_type=${window.mediaType}&max_results=100`);
        
        if (!response.ok) {
            throw new Error(`HTTP 错误: ${response.status}`);
        }
        
        let data = await response.json();

        if (!data.success && (data.message === '媒体不存在' || data.message === 'Media does not exist')) {
            response = await fetchWithRetry(`/api/quark/search/title?title=${encodeURIComponent(window.itemTitle)}&year=${window.itemYear || ''}&max_results=100`);
            
            if (!response.ok) {
                throw new Error(`HTTP 错误: ${response.status}`);
            }
            
            data = await response.json();
        }

        if (data.success && data.resources && data.resources.length > 0) {
            empty.style.display = 'none';
            list.style.display = 'block';

            let html = '<div class="quark-resources-scroll">';

            data.resources.forEach((resource, index) => {
                const isBest = resource.is_best ? '<span class="badge-best">最佳</span>' : '';
                const qualityBadge = resource.quality_level ? `<span class="badge-quality">${resource.resolution || resource.quality_level}</span>` : '';

                const tags = resource.tags || [];
                const tagsHtml = tags.length > 0 ? `
                    <div class="resource-tags">
                        ${tags.map(tag => `<span class="resource-tag">${tag.toUpperCase()}</span>`).join('')}
                    </div>
                ` : '';

                html += `
                    <div class="quark-resource-card">
                        <div class="resource-header">
                            <h4 class="resource-title">${index + 1}. ${escapeHtml(resource.name)}</h4>
                            <div class="resource-badges">
                                ${isBest}
                                ${qualityBadge}
                            </div>
                        </div>
                        ${tagsHtml}
                        <div class="resource-score">
                            <span class="score-label">资源评分:</span>
                            <span class="score-value">${(resource.overall_score * 10).toFixed(1)}</span>
                        </div>
                        <div class="resource-actions">
                            <a href="${resource.link}" target="_blank" rel="noopener noreferrer" class="btn btn-primary">打开链接</a>
                            <button onclick="collectResource('${escapeJs(resource.link)}', '${escapeJs(resource.name)}', this)" id="collect-btn-${index}" class="btn btn-collect">⭐ 收藏</button>
                        </div>
                        <div class="resource-actions">
                            <button onclick="saveResource('${resource.link}', this)" class="btn btn-transfer">保存到网盘</button>
                        </div>
                        <div id="save-status-${index}" class="resource-status"></div>
                    </div>
                `;
            });

            html += '</div>';
            list.innerHTML = html;
        } else {
            empty.style.display = 'block';
            empty.textContent = data.message || '未找到相关资源';
            list.style.display = 'none';
        }
    } catch (error) {
        console.error('[searchQuarkResources] 搜索失败:', error);
        if (retryCount < API_CONFIG.maxRetries) {
            empty.style.display = 'block';
            empty.innerHTML = '<span class="warning-text">加载失败，正在重试...</span>';
            setTimeout(() => searchQuarkResources(retryCount + 1), API_CONFIG.retryDelay);
            return;
        }
        empty.style.display = 'block';
        empty.innerHTML = `
            <span class="error-text">搜索失败: ${escapeHtml(error.message)}</span>
            <button onclick="searchQuarkResources()" class="btn btn-retry">重试</button>
        `;
        list.style.display = 'none';
    }
}

/**
 * 标准化文件夹名称
 * 移除序号前缀和非法字符
 * 
 * @param {string} rawName - 原始名称
 * @returns {string} 标准化后的名称
 */
function normalizeFolderName(rawName) {
    if (!rawName) return '';
    
    let name = rawName.trim();
    name = name.replace(/^\d+\.\s*/, '');
    name = name.replace(/[\\/:*?"<>|]/g, ' ');
    name = name.replace(/\s+/g, ' ').trim();
    return name;
}

/**
 * 获取卡片标题
 * 
 * @param {HTMLElement} card - 卡片元素
 * @returns {string} 标题文本
 */
function getCardTitle(card) {
    if (!card) {
        return '';
    }
    const titleEl = card.querySelector('h4');
    return titleEl ? (titleEl.textContent || '') : '';
}

/**
 * 保存资源到网盘
 * 
 * @param {string} link - 资源链接
 * @param {HTMLButtonElement} button - 触发按钮
 * @returns {Promise<void>}
 */
async function saveResource(link, button) {
    if (!link || !button) {
        console.error('[saveResource] 参数无效');
        return;
    }
    
    button.disabled = true;
    button.innerHTML = '保存中...';
    button.classList.add('btn-loading');

    const card = button.closest('.quark-resource-card');
    if (!card) {
        console.error('[saveResource] 未找到父级卡片元素');
        button.disabled = false;
        button.innerHTML = '保存到网盘';
        return;
    }
    
    const folderName = normalizeFolderName(getCardTitle(card));
    const statusDiv = card.querySelector('[id^="save-status-"]');
    
    if (statusDiv) {
        statusDiv.innerHTML = '<span class="warning-text">正在保存...</span>';
    }

    try {
        const payload = {
            link: link,
            to_dir_fid: '0',
            media_type: window.mediaType,
            title: window.itemTitle,
            year: window.itemYear || null
        };
        if (folderName) {
            payload.to_dir_name = folderName;
        }
        
        const response = await fetch('/api/quark/transfer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`HTTP 错误: ${response.status}`);
        }

        const result = await response.json();

        if (result.success) {
            button.innerHTML = '保存成功';
            button.classList.remove('btn-loading');
            button.classList.add('btn-success');
            if (statusDiv) {
                statusDiv.innerHTML = `<span class="success-text">${result.message || '保存成功'}</span>`;
            }
        } else {
            button.innerHTML = '保存失败';
            button.classList.remove('btn-loading');
            button.classList.add('btn-error');
            if (statusDiv) {
                statusDiv.innerHTML = `<span class="error-text">${result.message || '保存失败'}</span>`;
            }
        }
    } catch (error) {
        console.error('[saveResource] 保存失败:', error);
        button.innerHTML = '保存失败';
        button.classList.remove('btn-loading');
        button.classList.add('btn-error');
        if (statusDiv) {
            statusDiv.innerHTML = `<span class="error-text">保存失败: ${escapeHtml(error.message)}</span>`;
        }
    } finally {
        setTimeout(() => {
            button.disabled = false;
            button.innerHTML = '保存到网盘';
            button.classList.remove('btn-success', 'btn-error');
            setTimeout(() => {
                if (statusDiv) {
                    statusDiv.innerHTML = '';
                }
            }, 3000);
        }, 3000);
    }
}

/**
 * 检查当前影片是否已收藏
 * 
 * @returns {Promise<void>}
 */
async function checkCollectionStatus() {
    try {
        const response = await fetch(`/api/collection/check/${window.itemId}?media_type=${window.mediaType}`);
        
        if (!response.ok) {
            throw new Error(`HTTP 错误: ${response.status}`);
        }
        
        const data = await response.json();
        window.isCollected = data.collected;
        window.collectionId = data.id;
    } catch (error) {
        console.error('[checkCollectionStatus] 检查收藏状态失败:', error);
    }
}

/**
 * 收藏资源
 * 
 * @param {string} shareUrl - 分享链接
 * @param {string} resourceName - 资源名称
 * @param {HTMLButtonElement} button - 触发按钮
 * @returns {Promise<void>}
 */
async function collectResource(shareUrl, resourceName, button) {
    if (!shareUrl || !button) {
        console.error('[collectResource] 参数无效');
        return;
    }
    
    const requestKey = `collect-${shareUrl}`;
    if (pendingRequests.has(requestKey)) {
        console.warn('[collectResource] 请求已在处理中，跳过重复请求');
        return;
    }
    pendingRequests.add(requestKey);
    
    button.disabled = true;
    button.innerHTML = '收藏中...';
    button.classList.add('btn-loading');

    try {
        const response = await fetch('/api/collection/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                tmdb_id: window.itemId,
                media_type: window.mediaType,
                title: resourceName,
                year: window.itemYear || null,
                poster_path: window.itemPosterPath,
                backdrop_path: window.itemBackdropPath,
                share_url: shareUrl
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP 错误: ${response.status}`);
        }

        const result = await response.json();

        if (result.success) {
            window.collectionId = result.id;
            button.innerHTML = '✅ 已收藏';
            button.classList.remove('btn-loading');
            button.classList.add('btn-success');
        } else {
            button.innerHTML = result.message || '收藏失败';
            button.classList.remove('btn-loading');
            button.classList.add('btn-error');
            setTimeout(() => {
                button.disabled = false;
                button.innerHTML = '⭐ 收藏';
                button.classList.remove('btn-error');
            }, 2000);
        }
    } catch (error) {
        console.error('[collectResource] 收藏失败:', error);
        button.innerHTML = '收藏失败';
        button.classList.remove('btn-loading');
        button.classList.add('btn-error');
        setTimeout(() => {
            button.disabled = false;
            button.innerHTML = '⭐ 收藏';
            button.classList.remove('btn-error');
        }, 2000);
    } finally {
        pendingRequests.delete(requestKey);
    }
}

/**
 * 更新所有收藏按钮状态
 */
function updateAllCollectButtons() {
    const buttons = document.querySelectorAll('[id^="collect-btn-"]');
    buttons.forEach(btn => {
        if (window.isCollected) {
            btn.innerHTML = '✅ 已收藏';
            btn.classList.add('btn-success');
            btn.disabled = true;
        }
    });
}

/**
 * HTML 转义
 * 防止 XSS 攻击
 * 
 * @param {string} text - 原始文本
 * @returns {string} 转义后的文本
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * JavaScript 字符串转义
 * 
 * @param {string} text - 原始文本
 * @returns {string} 转义后的文本
 */
function escapeJs(text) {
    if (!text) return '';
    return text.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

/**
 * 初始化
 * 页面加载完成后执行
 */
document.addEventListener('DOMContentLoaded', function () {
    searchQuarkResources();
});
