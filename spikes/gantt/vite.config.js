import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    // frappe-gantt's "exports" map has no subpath for its stylesheet
    alias: { "frappe-gantt-css": fileURLToPath(new URL("./node_modules/frappe-gantt/dist/frappe-gantt.css", import.meta.url)) },
  },
});
