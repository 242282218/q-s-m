import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import "./styles.css";
import CollectionPage from "./pages/CollectionPage.vue";
import DetailPage from "./pages/DetailPage.vue";
import HomePage from "./pages/HomePage.vue";
import PersonPage from "./pages/PersonPage.vue";
import SearchPage from "./pages/SearchPage.vue";
import SettingsPage from "./pages/SettingsPage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: HomePage, meta: { title: "首页" } },
    { path: "/collections", component: CollectionPage, meta: { title: "收藏" } },
    { path: "/collection", redirect: "/collections" },
    { path: "/search", component: SearchPage, meta: { title: "搜索" } },
    { path: "/settings", component: SettingsPage, meta: { title: "设置" } },
    {
      path: "/movie/:item_id",
      component: () => import("./pages/DetailPage.vue"),
      props: (to) => ({
        mediaType: "movie",
        itemId: Number(to.params.item_id),
      }),
      meta: { title: "电影详情" },
    },
    {
      path: "/tv/:item_id",
      component: () => import("./pages/DetailPage.vue"),
      props: (to) => ({
        mediaType: "tv",
        itemId: Number(to.params.item_id),
      }),
      meta: { title: "剧集详情" },
    },
    {
      path: "/person/:person_id",
      component: () => import("./pages/PersonPage.vue"),
      props: (to) => ({
        personId: Number(to.params.person_id),
      }),
      meta: { title: "人物详情" },
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach((to, from, next) => {
  const title = to.meta.title as string;
  if (title) {
    document.title = `${title} - 影视墙`;
  } else {
    document.title = "影视墙";
  }
  next();
});

router.afterEach((to) => {
  console.log(`Navigated to: ${to.path}`);
});

const app = createApp(App);
app.use(router).mount("#app");

app.config.errorHandler = (err, vm, info) => {
  console.error("Global error:", err, info);
  console.error("Component:", vm);
};
