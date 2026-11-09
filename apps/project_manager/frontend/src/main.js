import { createApp } from "vue";
import App from "./App.vue";
import { initTheme } from "./lib/theme.js";
import { createAppRouter } from "./router.js";
import { startSync } from "./lib/sync.js";
import { registerServiceWorker } from "./lib/pwa.js";
import "./styles/tokens.css";
import "./styles/app.css";

initTheme();
createApp(App).use(createAppRouter()).mount("#app");
startSync();
registerServiceWorker();
