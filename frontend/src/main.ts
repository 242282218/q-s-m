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
    { path: "/", component: HomePage },
    { path: "/collections", component: CollectionPage },
    { path: "/collection", redirect: "/collections" },
    { path: "/search", component: SearchPage },
    { path: "/settings", component: SettingsPage },
    {
      path: "/movie/:item_id",
      component: DetailPage,
      props: (to) => ({
        mediaType: "movie",
        itemId: Number(to.params.item_id),
      }),
    },
    {
      path: "/tv/:item_id",
      component: DetailPage,
      props: (to) => ({
        mediaType: "tv",
        itemId: Number(to.params.item_id),
      }),
    },
    {
      path: "/person/:person_id",
      component: PersonPage,
      props: (to) => ({
        personId: Number(to.params.person_id),
      }),
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

createApp(App).use(router).mount("#app");
