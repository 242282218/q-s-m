<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { RouterLink, RouterView, useRouter } from 'vue-router';
import ToastHost from './components/ToastHost.vue';
import IconHome from '@/components/Icons/IconHome.vue';
import IconStar from '@/components/Icons/IconStar.vue';
import IconSettings from '@/components/Icons/IconSettings.vue';

const router = useRouter();
const searchQuery = ref('');
const siteHeaderRef = ref<HTMLElement | null>(null);
let headerResizeObserver: ResizeObserver | null = null;

function submitSearch() {
  const q = searchQuery.value.trim();
  if (!q) {
    void router.push('/search');
    return;
  }
  void router.push({
    path: '/search',
    query: {
      q,
    },
  });
}

function syncSiteHeaderLayoutVars() {
  const header = siteHeaderRef.value;
  if (!header) {
    return;
  }

  const computedStyle = window.getComputedStyle(header);
  const topValue = Number.parseFloat(computedStyle.top);
  const headerTop = Number.isNaN(topValue) ? 16 : Math.max(0, Math.round(topValue));
  const headerHeight = Math.max(0, Math.ceil(header.getBoundingClientRect().height));

  const rootStyle = document.documentElement.style;
  rootStyle.setProperty('--site-header-top', `${headerTop}px`);
  rootStyle.setProperty('--site-header-height', `${headerHeight}px`);
}

onMounted(() => {
  syncSiteHeaderLayoutVars();
  window.addEventListener('resize', syncSiteHeaderLayoutVars);

  if ('ResizeObserver' in window && siteHeaderRef.value) {
    headerResizeObserver = new ResizeObserver(syncSiteHeaderLayoutVars);
    headerResizeObserver.observe(siteHeaderRef.value);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', syncSiteHeaderLayoutVars);

  if (headerResizeObserver) {
    headerResizeObserver.disconnect();
    headerResizeObserver = null;
  }
});
</script>

<template>
  <div class="app-shell">
    <header ref="siteHeaderRef" class="site-header">
      <div class="shell">
        <div class="brand-area">
          <RouterLink to="/" class="home-link">
            <span class="brand-text">影视墙</span>
          </RouterLink>
        </div>

        <nav class="main-nav" role="navigation" aria-label="主导航">
          <RouterLink to="/" class="nav-link">
            <IconHome aria-hidden="true" />
            <span class="nav-text">首页</span>
          </RouterLink>
          <RouterLink to="/collections" class="nav-link">
            <IconStar aria-hidden="true" />
            <span class="nav-text">收藏</span>
          </RouterLink>
          <RouterLink to="/settings" class="nav-link">
            <IconSettings aria-hidden="true" />
            <span class="nav-text">设置</span>
          </RouterLink>
        </nav>

        <form
          class="search"
          role="search"
          aria-label="搜索电影或剧集"
          @submit.prevent="submitSearch"
        >
          <input
            v-model.trim="searchQuery"
            type="text"
            name="q"
            placeholder="搜索电影或剧集..."
            aria-label="搜索关键字"
            autocomplete="off"
          />
          <button type="submit" aria-label="执行搜索">搜索</button>
        </form>
      </div>
    </header>

    <main class="main-area" role="main">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <ToastHost />
  </div>
</template>
