import {
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
  type Router,
  type RouterHistory,
} from 'vue-router';

import CollectionPage from '@/pages/CollectionPage.vue';
import HomePage from '@/pages/HomePage.vue';
import SearchPage from '@/pages/SearchPage.vue';
import SettingsPage from '@/pages/SettingsPage.vue';

export const appRoutes: RouteRecordRaw[] = [
  { path: '/', component: HomePage, meta: { title: '首页' } },
  { path: '/collections', component: CollectionPage, meta: { title: '收藏' } },
  { path: '/collection', redirect: '/collections' },
  { path: '/search', component: SearchPage, meta: { title: '搜索' } },
  { path: '/settings', component: SettingsPage, meta: { title: '设置' } },
  {
    path: '/movie/:item_id',
    component: () => import('@/pages/DetailPage.vue'),
    props: (to) => ({
      mediaType: 'movie',
      itemId: Number(to.params.item_id),
    }),
    meta: { title: '电影详情' },
  },
  {
    path: '/tv/:item_id',
    component: () => import('@/pages/DetailPage.vue'),
    props: (to) => ({
      mediaType: 'tv',
      itemId: Number(to.params.item_id),
    }),
    meta: { title: '剧集详情' },
  },
  {
    path: '/person/:person_id',
    component: () => import('@/pages/PersonPage.vue'),
    props: (to) => ({
      personId: Number(to.params.person_id),
    }),
    meta: { title: '人物详情' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
];

export function syncDocumentTitle(title: unknown) {
  if (typeof title === 'string' && title) {
    document.title = `${title} - 影视墙`;
    return;
  }
  document.title = '影视墙';
}

export function createAppRouter(history: RouterHistory = createWebHistory()): Router {
  const router = createRouter({
    history,
    routes: appRoutes,
  });

  router.beforeEach((to, _from, next) => {
    syncDocumentTitle(to.meta.title);
    next();
  });

  router.afterEach((to) => {
    console.log(`Navigated to: ${to.path}`);
  });

  return router;
}
