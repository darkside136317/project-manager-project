// Screens of the construction layer, switched on by the core when this app is installed (boot.modules has
// "construction"; the core's src/modules.js finds this file when the SPA is built).
import { registerKind, uploadPhotos } from "@pm/lib/sync.js";
import AcceptanceTab from "./src/AcceptanceTab.vue";
import BoqTab from "./src/BoqTab.vue";
import { construction } from "./src/construction.js";
import DiaryTab from "./src/DiaryTab.vue";

// A site diary written without a connection: saved, its photos sent, then submitted (each step resendable).
registerKind("diary", async (item, saveProgress) => {
  const { project, day, values, rows } = item.payload;
  const saved = await construction.diarySave(project, day, values, rows, item.id);
  await uploadPhotos(item, "PMC Site Diary", saved.name, saveProgress);
  return construction.diarySubmit(saved.name, item.photos.map((photo) => photo.uuid), item.id);
}, {
  label: "Nhật ký thi công",
  summary: (item) => `${item.payload.rows.length} công tác${item.photos.length ? ` · ${item.photos.length} ảnh` : ""}`,
});

export default {
  name: "construction",
  projectTabs: [
    { slug: "boq", label: "BOQ", icon: "sheet", component: BoqTab, after: "cong-viec" },
    { slug: "nhat-ky", label: "Nhật ký", icon: "notebook-pen", component: DiaryTab, after: "trao-doi" },
    { slug: "nghiem-thu", label: "Nghiệm thu", icon: "clipboard-check", component: AcceptanceTab, after: "tai-lieu" },
  ],
};
