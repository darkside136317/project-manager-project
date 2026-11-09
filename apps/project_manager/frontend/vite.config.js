import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// The SPA is served by Frappe (www/pm): the build lands in the app's public folder, where
// nginx exposes it under /assets/project_manager/spa/, and pm.py reads its manifest.
const outDir = fileURLToPath(new URL("../project_manager/public/spa", import.meta.url));
// Industry layers keep their screens in <app>/frontend (src/modules.js finds them); they import the core as "@pm" and
// their tests are named *.layer.test.js.
const core = fileURLToPath(new URL("./src", import.meta.url));
const apps = fileURLToPath(new URL("../..", import.meta.url)).replaceAll("\\", "/").replace(/\/$/, "");

// Windows/Docker bind mounts do not deliver file-system events: poll when asked to.
const polling = process.env.PM_WATCH_POLL === "1";

export default defineConfig({
  base: "/assets/project_manager/spa/",
  plugins: [vue()],
  // a layer's files sit outside this folder: their bare imports resolve from here, as one copy
  resolve: { alias: { "@pm": core }, dedupe: ["vue", "vue-router", "lucide-vue-next", "socket.io-client"] },
  server: { fs: { allow: [".", apps || "/"] } },  // the layers' files (and tests) live beside this folder
  build: {
    outDir,
    emptyOutDir: true,
    manifest: true,
    sourcemap: false,
    rollupOptions: { input: "src/main.js" },
    watch: process.argv.includes("--watch")
      ? { chokidar: polling ? { usePolling: true, interval: 500 } : {} }
      : null,
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/**/*.test.js", `${apps}/*/frontend/tests/**/*.layer.test.js`],
  },
});
