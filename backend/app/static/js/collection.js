/**
 * 收藏页 JavaScript
 * 处理收藏列表加载、删除、转存等功能
 * 
 * @module collection
 * @description 提供收藏列表的分页加载、删除、转存等功能
 * 
 * 优化记录:
 * - 2024-02-24: 添加图片懒加载优化、DOM批量渲染、事件委托
 */

/** API 配置常量 */
const API_CONFIG = {
    timeout: 10000,
    maxRetries: 2,
    retryDelay: 1000
};

/** 分页状态 */
let currentPage = 1;
const limit = 20;
let totalItems = 0;
let renameAbortController = null;
let renameInProgress = false;

/** 图片加载配置 */
const IMAGE_CONFIG = {
    baseUrl: 'https://image.tmdb.org/t/p/',
    sizes: {
        small: 'w200',
        medium: 'w300',
        large: 'w500'
    },
    placeholder: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxIiBoZWlnaHQ9IjEiPjxyZWN0IHdpZHRoPSIxMDAlIiBoZWlnaHQ9IjEwMCUiIGZpbGw9IiMzMzMiLz48L3N2Zz4='
};

/**
 * 获取响应式图片尺寸
 * 根据窗口宽度返回合适的图片尺寸
 * 
 * @returns {string} 图片尺寸标识
 */
function getResponsiveImageSize() {
    const width = window.innerWidth;
    if (width < 768) return IMAGE_CONFIG.sizes.small;
    if (width < 1280) return IMAGE_CONFIG.sizes.medium;
    return IMAGE_CONFIG.sizes.large;
}

/**
 * 构建响应式图片URL
 * 
 * @param {string} posterPath - 海报路径
 * @param {string|null} size - 图片尺寸，可选
 * @returns {string|null} 完整的图片URL
 */
function buildImageUrl(posterPath, size = null) {
    if (!posterPath) return null;
    const imageSize = size || getResponsiveImageSize();
    return `${IMAGE_CONFIG.baseUrl}${imageSize}${posterPath}`;
}

/**
 * 带超时的 fetch 封装
 * 
 * @param {string} url - 请求地址
 * @param {RequestInit} options - fetch 选项
 * @returns {Promise<Response>} 响应对象
 * @throws {Error} 超时或网络错误
 */
async function fetchWithTimeout(url, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.timeout);
    
    try {
        const response = await fetch(url, { ...options, signal: controller.signal });
        clearTimeout(timeoutId);
        return response;
    } catch (error) {
        clearTimeout(timeoutId);
        console.error('[fetchWithTimeout] 请求失败:', error.message);
        throw error;
    }
}

/**
 * 使用 DocumentFragment 批量渲染卡片
 * 优化: 减少重排重绘次数
 * 
 * @param {Array<Object>} items - 卡片数据数组
 * @param {HTMLElement} grid - 网格容器元素
 */
function renderCardsBatch(items, grid) {
    if (!items || !grid) {
        console.error('[renderCardsBatch] 参数无效');
        return;
    }
    
    const fragment = document.createDocumentFragment();
    const imageSize = getResponsiveImageSize();
    
    items.forEach(item => {
        const card = createCardElement(item, imageSize);
        fragment.appendChild(card);
    });
    
    grid.appendChild(fragment);
}

/**
 * 创建单个卡片元素
 * 优化: 使用 createElement 替代 innerHTML，提高安全性
 * 
 * @param {Object} item - 卡片数据
 * @param {string} imageSize - 图片尺寸
 * @returns {HTMLElement} 卡片元素
 */
function createCardElement(item, imageSize) {
    if (!item) {
        console.error('[createCardElement] item 参数为空');
        return document.createElement('div');
    }
    
    const safeTitle = escapeHtml(item.title);
    const imageUrl = item.poster_path 
        ? buildImageUrl(item.poster_path, imageSize)
        : IMAGE_CONFIG.placeholder;
    
    const card = document.createElement('div');
    card.className = 'poster-card';
    card.dataset.id = item.id;
    card.dataset.title = item.title || '';
    const statusNum = Number(item.status ?? 0);
    card.dataset.status = String(statusNum);
    
    let statusBadgeHtml = '';
    const savedBadge = '<span class="status-badge saved">已收藏</span>';
    
    let transferBadgeHtml = '';
    if (statusNum === 1) {
        transferBadgeHtml = '<span class="status-badge transferred">已转存</span>';
    } else if (statusNum === 2) {
        transferBadgeHtml = '<span class="status-badge expired">已失效</span>';
    } else {
        transferBadgeHtml = '<span class="status-badge not-transferred">未转存</span>';
    }
    
    statusBadgeHtml = `<div class="status-badges">${savedBadge}${transferBadgeHtml}</div>`;
    
    const missingPosterClass = !item.poster_path ? 'missing-poster' : '';
    const missingPosterData = !item.poster_path 
        ? `data-tmdb-id="${item.tmdb_id}" data-media-type="${item.media_type}"` 
        : '';
    const renameDisabled = statusNum !== 1;
    const renameDisabledAttr = renameDisabled ? 'disabled aria-disabled="true"' : '';
    const renameDisabledClass = renameDisabled ? ' is-disabled' : '';
    
    card.innerHTML = `
        <button class="delete-btn" data-action="delete" data-id="${item.id}" title="删除收藏" aria-label="删除收藏">×</button>
        <button class="transfer-btn" data-action="transfer" data-id="${item.id}" title="转存到网盘" aria-label="转存到网盘">📥</button>
        <button class="rename-btn${renameDisabledClass}" data-action="rename" data-id="${item.id}" title="重命名" aria-label="重命名" ${renameDisabledAttr}>✏️</button>
        <a href="/${item.media_type}/${item.tmdb_id}">
            <div class="poster-media">
                <img 
                    src="${imageUrl}" 
                    alt="${safeTitle}" 
                    loading="lazy"
                    decoding="async"
                    ${missingPosterClass ? `class="${missingPosterClass}" ${missingPosterData}` : ''}
                    onerror="this.onerror=null;this.src='${IMAGE_CONFIG.placeholder}';"
                >
                <div class="poster-gradient"></div>
                ${statusBadgeHtml}
            </div>
            <div class="poster-text">
                <div class="poster-title">${safeTitle}</div>
                ${item.year ? `<div class="poster-subtitle">${item.year}</div>` : ''}
            </div>
        </a>
    `;
    
    return card;
}

/**
 * 加载收藏列表
 * 优化: 使用 DocumentFragment 批量渲染
 * 
 * @param {number} page - 页码
 * @returns {Promise<void>}
 */
async function loadCollections(page = 1) {
    const skeleton = document.getElementById('collection-skeleton');
    const loading = document.getElementById('collection-loading');
    const empty = document.getElementById('collection-empty');
    const grid = document.getElementById('collection-grid');
    const pagination = document.getElementById('collection-pagination');
    const countEl = document.getElementById('collection-count');

    // 检查必要的 DOM 元素
    if (!skeleton || !loading || !empty || !grid || !pagination || !countEl) {
        console.error('[loadCollections] 未找到必要的 DOM 元素');
        return;
    }

    skeleton.style.display = 'grid';
    loading.style.display = 'none';
    empty.style.display = 'none';
    grid.style.display = 'none';
    pagination.style.display = 'none';
    grid.innerHTML = '';

    try {
        const response = await fetchWithTimeout(`/api/collection/list?page=${page}&limit=${limit}&sort_by=saved_at&order=desc`);

        if (!response.ok) {
            throw new Error(`HTTP 错误: ${response.status}`);
        }

        const data = await response.json();
        
        skeleton.style.display = 'none';

        if (!data.items || data.total === 0) {
            empty.style.display = 'flex';
            countEl.textContent = '';
            return;
        }

        totalItems = data.total;
        currentPage = page;
        countEl.textContent = `${totalItems} 部`;

        if (!Array.isArray(data.items)) {
            throw new Error('返回数据格式错误: items不是数组');
        }

        // 使用批量渲染优化
        renderCardsBatch(data.items, grid);
        
        fetchMissingPosters();
        grid.style.display = 'grid';

        const totalPages = Math.ceil(totalItems / limit);
        if (totalPages > 1) {
            pagination.style.display = 'flex';
            document.getElementById('page-info').textContent = `${page} / ${totalPages}`;
            document.getElementById('prev-page').disabled = page <= 1;
            document.getElementById('next-page').disabled = page >= totalPages;
        }

    } catch (error) {
        console.error('[loadCollections] 加载失败:', error);
        skeleton.style.display = 'none';
        loading.style.display = 'none';
        empty.style.display = 'flex';
        const emptyText = document.querySelector('.empty-text');
        const emptyHint = document.querySelector('.empty-hint');
        if (emptyText) emptyText.textContent = '加载失败';
        if (emptyHint) emptyHint.textContent = error.message;
    }
}

/**
 * 删除收藏
 * 
 * @param {number} id - 收藏 ID
 * @returns {Promise<void>}
 */
async function deleteCollection(id) {
    if (!id) {
        console.error('[deleteCollection] id 参数无效');
        return;
    }
    
    if (!confirm('确定要删除这个收藏吗？')) {
        return;
    }

    try {
        const response = await fetch(`/api/collection/${id}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP 错误: ${response.status}`);
        }
        
        const data = await response.json();

        if (data.success) {
            loadCollections(currentPage);
        } else {
            alert('删除失败: ' + data.message);
        }
    } catch (error) {
        console.error('[deleteCollection] 删除失败:', error);
        alert('删除失败: ' + error.message);
    }
}

/**
 * 转存收藏到网盘
 * 
 * @param {number} id - 收藏 ID
 * @param {HTMLButtonElement} button - 触发按钮
 * @returns {Promise<void>}
 */
async function transferCollection(id, button) {
    if (!id || !button) {
        console.error('[transferCollection] 参数无效');
        return;
    }
    
    const originalText = button.innerHTML;
    button.innerHTML = '<span class="loading-spinner" style="width:16px;height:16px;border-width:2px;margin:0;"></span>';
    button.disabled = true;

    try {
        const response = await fetch('/api/transfer/exec', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collection_id: id })
        });

        if (!response.ok) {
            throw new Error(`HTTP 错误: ${response.status}`);
        }

        const data = await response.json();

        if (data.success) {
            showToast('转存成功！', 'success');
            loadCollections(currentPage);
        } else {
            showToast('转存失败: ' + data.message, 'error');
        }
    } catch (error) {
        console.error('[transferCollection] 转存请求错误:', error);
        showToast('转存请求失败', 'error');
    } finally {
        button.innerHTML = originalText;
        button.disabled = false;
    }
}

function getRenameModalElements() {
    return {
        modal: document.getElementById('rename-log-modal'),
        title: document.getElementById('rename-log-title'),
        progressFill: document.getElementById('rename-progress-fill'),
        progressText: document.getElementById('rename-progress-text'),
        lines: document.getElementById('rename-log-lines'),
        summary: document.getElementById('rename-log-summary'),
        closeTop: document.getElementById('rename-log-close-top'),
        closeBottom: document.getElementById('rename-log-close-bottom')
    };
}

function openRenameModal(resourceTitle) {
    const { modal, title, progressFill, progressText, lines, summary } = getRenameModalElements();
    if (!modal || !title || !progressFill || !progressText || !lines || !summary) {
        console.error('[openRenameModal] 模态框 DOM 未就绪');
        return;
    }

    title.textContent = `✏️ 重命名进度 - ${resourceTitle || '未知资源'}`;
    progressFill.style.width = '0%';
    progressText.textContent = '0% (0/0)';
    lines.innerHTML = '';
    summary.textContent = '';
    summary.classList.remove('done', 'has-error');

    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
}

function closeRenameModal(force = false) {
    const { modal } = getRenameModalElements();
    if (!modal) return;

    if (!force && renameInProgress) {
        const shouldAbort = confirm('重命名正在进行，关闭将中断任务，确定继续吗？');
        if (!shouldAbort) return;
        renameAbortController?.abort();
    }

    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
}

function updateRenameProgress(current, total, percentage) {
    const { progressFill, progressText } = getRenameModalElements();
    if (!progressFill || !progressText) return;

    const safeCurrent = Number.isFinite(current) ? current : 0;
    const safeTotal = Number.isFinite(total) ? total : 0;
    const safePercentage = Number.isFinite(percentage)
        ? Math.max(0, Math.min(100, percentage))
        : (safeTotal > 0 ? Math.round((safeCurrent / safeTotal) * 100) : 0);

    progressFill.style.width = `${safePercentage}%`;
    progressText.textContent = `${safePercentage}% (${safeCurrent}/${safeTotal})`;
}

function appendRenameLog(message, level = 'info') {
    const { lines } = getRenameModalElements();
    if (!lines) return;

    const logLine = document.createElement('div');
    logLine.className = `rename-log-line level-${level}`;
    logLine.textContent = `[${level.toUpperCase()}] ${message || ''}`;
    lines.appendChild(logLine);
    lines.scrollTop = lines.scrollHeight;
}

function updateRenameSummary(success, skipped, failed) {
    const { summary } = getRenameModalElements();
    if (!summary) return;

    const safeSuccess = Number.isFinite(success) ? success : 0;
    const safeSkipped = Number.isFinite(skipped) ? skipped : 0;
    const safeFailed = Number.isFinite(failed) ? failed : 0;

    summary.textContent = `完成汇总：成功 ${safeSuccess} 个，跳过 ${safeSkipped} 个，失败 ${safeFailed} 个`;
    summary.classList.add('done');
    summary.classList.toggle('has-error', safeFailed > 0);
}

function parseSseData(chunk) {
    const lines = chunk.split(/\r?\n/);
    let payload = '';

    lines.forEach((line) => {
        if (line.startsWith('data:')) {
            payload += line.slice(5).trim();
        }
    });

    if (!payload) return null;

    try {
        return JSON.parse(payload);
    } catch (error) {
        console.error('[parseSseData] 解析失败:', error, payload);
        return null;
    }
}

function handleRenameEvent(eventData) {
    if (!eventData || typeof eventData !== 'object') return false;

    const type = eventData.type || 'log';
    const level = eventData.level || 'info';
    const current = Number(eventData.current ?? 0);
    const total = Number(eventData.total ?? 0);
    const percentage = Number(eventData.percentage ?? 0);
    const message = eventData.message || '';

    if (type === 'log') {
        appendRenameLog(message, level);
        if (total > 0) {
            updateRenameProgress(current, total, percentage);
        }
        return false;
    }

    if (type === 'progress') {
        updateRenameProgress(current, total, percentage);
        return false;
    }

    if (type === 'complete') {
        updateRenameProgress(total, total, 100);
        appendRenameLog(message || '重命名完成', 'info');
        updateRenameSummary(eventData.success, eventData.skipped, eventData.failed);
        showToast('重命名完成', 'success');
        return true;
    }

    if (type === 'error') {
        appendRenameLog(message || '重命名失败', 'error');
        showToast(message || '重命名失败', 'error');
        return true;
    }

    return false;
}

function initRenameModal() {
    const { modal, closeTop, closeBottom } = getRenameModalElements();
    if (!modal || !closeTop || !closeBottom) return;

    closeTop.addEventListener('click', () => closeRenameModal(false));
    closeBottom.addEventListener('click', () => closeRenameModal(false));
    modal.addEventListener('click', (event) => {
        if (event.target === modal) {
            closeRenameModal(false);
        }
    });
}

async function renameCollection(id, title, button) {
    if (!id || !button) {
        console.error('[renameCollection] 参数无效');
        return;
    }

    if (renameInProgress) {
        showToast('已有重命名任务正在执行', 'info');
        return;
    }

    const originalText = button.innerHTML;
    button.innerHTML = '<span class="loading-spinner" style="width:16px;height:16px;border-width:2px;margin:0;"></span>';
    button.disabled = true;

    renameInProgress = true;
    renameAbortController = new AbortController();
    let receivedComplete = false;

    openRenameModal(title);
    appendRenameLog(`开始重命名: ${title || '未知资源'}`, 'info');

    try {
        const response = await fetch('/api/transfer/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collection_id: id }),
            signal: renameAbortController.signal
        });

        if (!response.ok) {
            throw new Error(`HTTP 错误: ${response.status}`);
        }

        if (!response.body) {
            throw new Error('浏览器不支持流式响应');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const chunks = buffer.split(/\r?\n\r?\n/);
            buffer = chunks.pop() || '';

            chunks.forEach((chunk) => {
                const eventData = parseSseData(chunk);
                if (!eventData) return;
                if (handleRenameEvent(eventData)) {
                    receivedComplete = true;
                }
            });
        }

        const finalChunk = buffer.trim();
        if (finalChunk) {
            const eventData = parseSseData(finalChunk);
            if (eventData && handleRenameEvent(eventData)) {
                receivedComplete = true;
            }
        }

        if (!receivedComplete) {
            appendRenameLog('重命名流已结束，但未收到完成事件', 'warning');
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            appendRenameLog('重命名任务已中断', 'warning');
            showToast('重命名任务已中断', 'info');
        } else {
            console.error('[renameCollection] 请求失败:', error);
            appendRenameLog(`重命名失败: ${error.message}`, 'error');
            showToast('重命名请求失败', 'error');
        }
    } finally {
        renameInProgress = false;
        renameAbortController = null;
        button.innerHTML = originalText;
        button.disabled = false;
        loadCollections(currentPage);
    }
}

/**
 * 获取缺失的海报
 * 优化: 使用 Intersection Observer 实现按需加载
 */
function fetchMissingPosters() {
    const missingPosters = document.querySelectorAll('.missing-poster');
    if (missingPosters.length === 0) return;
    
    // 如果浏览器支持 Intersection Observer，使用它进行按需加载
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    loadPosterImage(img);
                    observer.unobserve(img);
                }
            });
        }, {
            rootMargin: '50px 0px',
            threshold: 0.01
        });
        
        missingPosters.forEach(img => imageObserver.observe(img));
    } else {
        // 降级处理：直接加载
        missingPosters.forEach(img => loadPosterImage(img));
    }
}

/**
 * 加载单个海报图片
 * 
 * @param {HTMLImageElement} img - 图片元素
 * @returns {Promise<void>}
 */
async function loadPosterImage(img) {
    if (!img) return;
    
    const tmdbId = img.dataset.tmdbId;
    const mediaType = img.dataset.mediaType;
    
    if (!tmdbId || !mediaType) return;
    
    try {
        const response = await fetchWithTimeout(`/api/tmdb/details?media_type=${mediaType}&tmdb_id=${tmdbId}`);
        
        if (!response.ok) {
            console.error(`[loadPosterImage] 获取海报失败: ${response.status}`);
            return;
        }
        
        const data = await response.json();
        
        if (data.poster_path) {
            const posterUrl = buildImageUrl(data.poster_path);
            img.src = posterUrl;
            img.classList.remove('missing-poster');
            delete img.dataset.tmdbId;
            delete img.dataset.mediaType;
        }
    } catch (error) {
        console.error(`[loadPosterImage] 获取海报时发生错误: ${error.message}`);
    }
}

/**
 * 显示 Toast 提示
 * 
 * @param {string} message - 提示消息
 * @param {string} type - 提示类型: 'success' | 'error' | 'info'
 */
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 80px;
        left: 50%;
        transform: translateX(-50%);
        padding: 12px 24px;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 600;
        z-index: 1000;
        animation: fadeInUp 0.3s ease;
    `;
    
    if (type === 'success') {
        toast.style.background = 'linear-gradient(135deg, #28a745, #1e7e34)';
        toast.style.color = '#fff';
    } else if (type === 'error') {
        toast.style.background = 'linear-gradient(135deg, #dc3545, #c82333)';
        toast.style.color = '#fff';
    } else {
        toast.style.background = 'rgba(0, 0, 0, 0.8)';
        toast.style.color = '#fff';
    }
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'fadeOutDown 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
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
 * 事件委托处理
 * 优化: 统一在 grid 上监听事件，减少事件处理器数量
 */
function initEventDelegation() {
    const grid = document.getElementById('collection-grid');
    
    if (!grid) {
        console.error('[initEventDelegation] 未找到 collection-grid 元素');
        return;
    }
    
    grid.addEventListener('click', (event) => {
        const button = event.target.closest('button[data-action]');
        if (!button) return;
        
        event.preventDefault();
        event.stopPropagation();
        
        const action = button.dataset.action;
        const id = parseInt(button.dataset.id, 10);
        
        if (isNaN(id)) {
            console.error('[initEventDelegation] 无效的 ID:', button.dataset.id);
            return;
        }
        
        if (action === 'delete') {
            deleteCollection(id);
        } else if (action === 'transfer') {
            transferCollection(id, button);
        } else if (action === 'rename') {
            const card = button.closest('.poster-card');
            const resourceTitle = card?.dataset.title || '';
            renameCollection(id, resourceTitle, button);
        }
    });
}

/**
 * 分页事件绑定
 */
document.getElementById('prev-page')?.addEventListener('click', () => {
    if (currentPage > 1) {
        loadCollections(currentPage - 1);
    }
});

document.getElementById('next-page')?.addEventListener('click', () => {
    const totalPages = Math.ceil(totalItems / limit);
    if (currentPage < totalPages) {
        loadCollections(currentPage + 1);
    }
});

/**
 * 页面加载时获取收藏
 */
document.addEventListener('DOMContentLoaded', () => {
    initEventDelegation();
    initRenameModal();
    loadCollections(1);
});

/**
 * 窗口大小改变时的防抖处理
 */
let resizeTimeout;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        // 可以在这里添加重新加载合适尺寸图片的逻辑
    }, 250);
});
