<script setup lang="ts">
import { ref } from "vue";
import { RouterLink, RouterView, useRouter } from "vue-router";
import ToastHost from "./components/ToastHost.vue";
import IconHome from "@/components/Icons/IconHome.vue";
import IconStar from "@/components/Icons/IconStar.vue";
import IconSettings from "@/components/Icons/IconSettings.vue";

const router = useRouter();
const searchQuery = ref("");

function submitSearch() {
  const q = searchQuery.value.trim();
  if (!q) {
    void router.push("/search");
    return;
  }
  void router.push({
    path: "/search",
    query: {
      q,
    },
  });
}
</script>

<template>
  <div class="app-shell">
    <header class="site-header">
      <div class="shell">
        <div class="brand-area">
          <RouterLink to="/" class="home-link">
            <span class="brand-text">影视墙</span>
          </RouterLink>
        </div>

        <form class="search" role="search" aria-label="搜索电影或剧集" @submit.prevent="submitSearch">
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
      </div>
    </header>

    <main class="main-area" role="main">
      <RouterView />
    </main>

    <ToastHost />
  </div>
</template>
