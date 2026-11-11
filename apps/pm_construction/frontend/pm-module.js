// Screens of the construction layer, switched on by the core when this app is installed (boot.modules has
// "construction"; the core's src/modules.js finds this file when the SPA is built).
import { registerKind, uploadPhotos } from "@pm/lib/sync.js";
import AcceptanceTab from "./src/AcceptanceTab.vue";
import BoqTab from "./src/BoqTab.vue";
import CostTab from "./src/CostTab.vue";
import { construction, site } from "./src/construction.js";
import DiaryTab from "./src/DiaryTab.vue";
import LabourTab from "./src/LabourTab.vue";
import MachinesTab from "./src/MachinesTab.vue";
import MaterialsTab from "./src/MaterialsTab.vue";

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

// Materials asked for, machine shifts and crew attendance written on site: each sent once (its id is the client_uuid).
registerKind("material-request", (item) => {
  const { project, rows, note, needed_by: neededBy } = item.payload;
  return site.request(project, rows, note, neededBy, item.id);
}, { label: "Đề xuất vật tư", summary: (item) => `${item.payload.rows.length} dòng vật tư` });

registerKind("machine-shift", (item) => site.shift(item.payload, item.id), {
  label: "Ca máy", summary: (item) => `${item.payload.shifts} ca`,
});

registerKind("attendance", (item) => {
  const { project, team, day, lines, note } = item.payload;
  return site.attendanceRecord(project, team, day, lines, note, item.id);
}, { label: "Chấm công", summary: (item) => `${item.payload.lines.length} người` });

export default {
  name: "construction",
  projectTabs: [
    { slug: "boq", label: "BOQ", icon: "sheet", component: BoqTab, after: "cong-viec" },
    { slug: "nhat-ky", label: "Nhật ký", icon: "notebook-pen", component: DiaryTab, after: "trao-doi" },
    { slug: "vat-tu", label: "Vật tư", icon: "package", component: MaterialsTab, after: "nhat-ky" },
    { slug: "may", label: "Máy", icon: "truck", component: MachinesTab, after: "vat-tu" },
    { slug: "cham-cong", label: "Chấm công", icon: "hard-hat", component: LabourTab, after: "may" },
    { slug: "nghiem-thu", label: "Nghiệm thu", icon: "clipboard-check", component: AcceptanceTab, after: "tai-lieu" },
    { slug: "chi-phi", label: "Chi phí", icon: "coins", component: CostTab, after: "nghiem-thu" },
  ],
};
