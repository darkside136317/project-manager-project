import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/lib/api.js", () => ({
  api: {
    forms: {
      detail: vi.fn(), save: vi.fn(), submit: vi.fn(), approve: vi.fn(), sendBack: vi.fn(), attach: vi.fn(), discard: vi.fn(),
      forTask: vi.fn(), start: vi.fn(), gateAdd: vi.fn(), gateRemove: vi.fn(), pdfUrl: (name) => `/pdf/${name}`,
      template: vi.fn(), templateSave: vi.fn(), templateActivate: vi.fn(), templateNewVersion: vi.fn(),
    },
    tasks: {},
    projects: {},
    wbs: {},
  },
  call: vi.fn(),
}));

import { api } from "../src/lib/api.js";
import DynamicForm from "../src/components/forms/DynamicForm.vue";
import FormTable from "../src/components/forms/FormTable.vue";
import SignaturePad from "../src/components/forms/SignaturePad.vue";
import TaskForms from "../src/components/forms/TaskForms.vue";
import { F, fieldNeeds, fitSize, formStateBadge, missingFields, tableRows } from "../src/lib/forms.js";
import FormSubmissionPage from "../src/pages/FormSubmissionPage.vue";
import FormTemplatePage from "../src/pages/FormTemplatePage.vue";
import { routes } from "../src/router.js";

beforeEach(() => vi.clearAllMocks());

const text = (extra = {}) => ({ fieldname: "ghi_chu", label: "Ghi chú", fieldtype: F.TEXT, reqd: 0, choices: [], columns: [], preset_rows: [], ...extra });
const CHECKLIST = text({
  fieldname: "danh_muc", label: "Danh mục", fieldtype: F.TABLE, reqd: 1,
  columns: [{ key: "noi_dung", label: "Nội dung", type: F.TEXT, choices: [] }, { key: "ket_qua", label: "Kết quả", type: F.SELECT, choices: ["Đạt", "Không đạt"] }],
  preset_rows: ["Đúng bản vẽ", "Đủ hồ sơ"],
});
const MATERIALS = text({
  fieldname: "vat_tu", label: "Vật tư", fieldtype: F.TABLE, reqd: 1,
  columns: [{ key: "ten", label: "Tên", type: F.TEXT, choices: [] }, { key: "sl", label: "Số lượng", type: F.NUMBER, choices: [] }],
});

describe("what is still missing", () => {
  it("finds required answers", () => {
    const spec = { fields: [text({ reqd: 1 }), text({ fieldname: "tuy_chon" }), text({ fieldname: "muc", fieldtype: F.SECTION, reqd: 1 }),
      text({ fieldname: "dong_y", fieldtype: F.CHECK, reqd: 1 }), text({ fieldname: "so", fieldtype: F.NUMBER, reqd: 1 }), text({ fieldname: "anh", fieldtype: F.IMAGE, reqd: 1 })] };
    expect(missingFields(spec, {})).toEqual(["ghi_chu", "dong_y", "so", "anh"]);
    expect(missingFields(spec, { ghi_chu: "x", dong_y: 1, so: 0, anh: [{ file: "/a" }] })).toEqual([]);  // 0 is an answer
  });

  it("asks every row of a checklist, and one row of an open table", () => {
    const spec = { fields: [CHECKLIST, MATERIALS] };
    expect(missingFields(spec, {})).toEqual(["danh_muc", "vat_tu"]);
    expect(missingFields(spec, { danh_muc: [{ ket_qua: "Đạt" }], vat_tu: [{ ten: "Thép" }] })).toEqual(["danh_muc"]);
    expect(missingFields(spec, { danh_muc: [{ ket_qua: "Đạt" }, { ket_qua: "Không đạt" }], vat_tu: [{ ten: "Thép" }] })).toEqual([]);
  });

  it("gives a checklist its fixed rows", () => {
    expect(tableRows(CHECKLIST, [{ ket_qua: "Đạt" }]).map((r) => r.noi_dung)).toEqual(["Đúng bản vẽ", "Đủ hồ sơ"]);
    expect(tableRows(MATERIALS, undefined)).toEqual([]);
  });
});

describe("helpers", () => {
  it("reduces big pictures only", () => {
    expect(fitSize(3200, 2400)).toEqual({ width: 1600, height: 1200 });
    expect(fitSize(800, 600)).toEqual({ width: 800, height: 600 });
  });

  it("colours states and knows what a designer needs", () => {
    expect(formStateBadge("Đã duyệt")).toBe("badge badge-success");
    expect(fieldNeeds(F.TABLE)).toMatchObject({ options: true, preset: true, required: true });
    expect(fieldNeeds(F.SECTION).required).toBe(false);
  });
});

describe("FormTable", () => {
  it("keeps a checklist's rows and first column", () => {
    const wrapper = mount(FormTable, { props: { field: CHECKLIST, modelValue: [] } });
    expect(wrapper.text()).toContain("Đúng bản vẽ");
    expect(wrapper.findAll("input")).toHaveLength(0);
    expect(wrapper.text()).not.toContain("Thêm hàng");
    expect(wrapper.findAll("select")).toHaveLength(2);
  });

  it("adds, edits and removes rows of an open table", async () => {
    const wrapper = mount(FormTable, { props: { field: MATERIALS, modelValue: [{ ten: "Thép" }] } });
    await wrapper.find("input").setValue("Xi măng");
    expect(wrapper.emitted("update:modelValue")[0][0]).toEqual([{ ten: "Xi măng" }]);
    await wrapper.findAll("button").find((b) => b.text().includes("Thêm hàng")).trigger("click");
    expect(wrapper.emitted("update:modelValue")[1][0]).toHaveLength(2);
    await wrapper.find("button[aria-label='Xóa hàng']").trigger("click");
    expect(wrapper.emitted("update:modelValue")[2][0]).toEqual([]);
  });

  it("only shows when read-only", () => {
    const wrapper = mount(FormTable, { props: { field: MATERIALS, modelValue: [{ ten: "Thép", sl: 3 }], readonly: true } });
    expect(wrapper.text()).toContain("Thép");
    expect(wrapper.find("input").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Thêm hàng");
  });
});

describe("DynamicForm", () => {
  const spec = { fields: [
    text({ fieldname: "muc", label: "Thông tin", fieldtype: F.SECTION }), text({ reqd: 1 }),
    text({ fieldname: "kl", label: "Khối lượng", fieldtype: F.NUMBER, unit: "m3" }),
    text({ fieldname: "kq", label: "Kết luận", fieldtype: F.SELECT, choices: ["Đạt", "Không đạt"] }),
    text({ fieldname: "nhieu", label: "Nhiều lựa chọn", fieldtype: F.SELECT, choices: ["a", "b", "c", "d", "e"] }),
    text({ fieldname: "ok", label: "Đã kiểm tra", fieldtype: F.CHECK }),
  ] };

  it("emits every kind of answer", async () => {
    const wrapper = mount(DynamicForm, { props: { spec, modelValue: {} } });
    await wrapper.find("#f-ghi_chu").setValue("xin chào");
    expect(wrapper.emitted("update:modelValue").at(-1)[0]).toEqual({ ghi_chu: "xin chào" });
    await wrapper.find("#f-kl").setValue("12");
    expect(wrapper.emitted("update:modelValue").at(-1)[0]).toEqual({ kl: "12" });
    await wrapper.findAll("[role=radio]")[1].trigger("click");  // few choices: buttons that a thumb can reach
    expect(wrapper.emitted("update:modelValue").at(-1)[0]).toEqual({ kq: "Không đạt" });
    await wrapper.find("select#f-nhieu").setValue("c");
    expect(wrapper.emitted("update:modelValue").at(-1)[0]).toEqual({ nhieu: "c" });
    await wrapper.find("input[type=checkbox]").setValue(true);
    expect(wrapper.emitted("update:modelValue").at(-1)[0]).toEqual({ ok: 1 });
  });

  it("marks what is missing", () => {
    const wrapper = mount(DynamicForm, { props: { spec, modelValue: {}, missing: ["ghi_chu"] } });
    expect(wrapper.find("#f-ghi_chu").classes()).toContain("is-invalid");
    expect(wrapper.text()).toContain("Cần điền mục này");
  });

  it("is plain text when read-only, and never renders an answer as HTML", () => {
    const wrapper = mount(DynamicForm, { props: { spec, readonly: true, modelValue: { ghi_chu: "<img src=x onerror=alert(1)>", kl: 7 } } });
    expect(wrapper.find("input:not([type=checkbox])").exists()).toBe(false);
    expect(wrapper.find("img").exists()).toBe(false);
    expect(wrapper.text()).toContain("<img src=x");
    expect(wrapper.text()).toContain("7 m3");
  });
});

describe("SignaturePad", () => {
  it("offers to sign again once signed", async () => {
    const wrapper = mount(SignaturePad, { props: { modelValue: [{ file: "/private/files/k.png" }] } });
    expect(wrapper.find("img").attributes("src")).toBe("/private/files/k.png");
    await wrapper.findAll("button").find((b) => b.text().includes("Ký lại")).trigger("click");
    expect(wrapper.emitted("update:modelValue")[0][0]).toEqual([]);
  });

  it("cannot be confirmed before anything is drawn", () => {
    const wrapper = mount(SignaturePad, { props: { modelValue: [], uploader: vi.fn() } });
    expect(wrapper.findAll("button").find((b) => b.text().includes("Dùng chữ ký")).attributes("disabled")).toBeDefined();
  });

  it("says when a read-only form was not signed", () => {
    expect(mount(SignaturePad, { props: { modelValue: [], readonly: true } }).text()).toContain("Chưa ký");
  });
});

function router() {
  return createRouter({ history: createMemoryHistory(), routes });
}

describe("TaskForms", () => {
  const view = (extra = {}) => ({
    gates: [{ name: 1, form_code: "NT", form_title: "Nghiệm thu", state: null, submission: null, met: false }],
    forms: [], can_fill: true, can_gate: true,
    templates: [{ code: "NT", title: "Nghiệm thu" }, { code: "CL", title: "Kiểm tra" }], ...extra,
  });

  it("shows what is required, and starts it", async () => {
    api.forms.forTask.mockResolvedValue(view());
    api.forms.start.mockResolvedValue({ name: 9 });
    const wrapper = mount(TaskForms, { props: { task: "T-1", project: "P-1" }, global: { plugins: [router()] } });
    await flushPromises();
    expect(wrapper.text()).toContain("Bắt buộc: Nghiệm thu");
    expect(wrapper.text()).toContain("Chưa điền");
    await wrapper.findAll("button").find((b) => b.text() === "Điền").trigger("click");
    await flushPromises();
    expect(api.forms.start).toHaveBeenCalledWith("NT", "P-1", "T-1");
  });

  it("does not offer again what is already required, nor anything to those who may not", async () => {
    api.forms.forTask.mockResolvedValue(view());
    let wrapper = mount(TaskForms, { props: { task: "T-1" }, global: { plugins: [router()] } });
    await flushPromises();
    const options = wrapper.findAll("select")[1].findAll("option").map((o) => o.text());
    expect(options).toContain("Kiểm tra");
    expect(options).not.toContain("Nghiệm thu");

    api.forms.forTask.mockResolvedValue(view({ can_fill: false, can_gate: false }));
    wrapper = mount(TaskForms, { props: { task: "T-1" }, global: { plugins: [router()] } });
    await flushPromises();
    expect(wrapper.find("select").exists()).toBe(false);
    expect(wrapper.find("button[aria-label='Bỏ điều kiện']").exists()).toBe(false);
  });
});

const SPEC = { fields: [text({ reqd: 1 })], title: "Phiếu" };
const form = (extra = {}) => ({
  name: 5, state: "Nháp", title: "Phiếu", template_code: "CL", version: 1, project: "P-1", project_name: "Nhà A", task: "T-1", task_label: "1.1 Móng",
  data: {}, spec: SPEC, history: [], can: { edit: true, approve: false, send_back: false, discard: true, self_submitted: false }, ...extra,
});

async function page(data) {
  api.forms.detail.mockResolvedValue(data);
  const r = router();
  await r.push("/bieu-mau/5");
  const wrapper = mount(FormSubmissionPage, { global: { plugins: [r], stubs: { ReasonDialog: true, ConfirmDialog: true } } });
  await flushPromises();
  return wrapper;
}

describe("FormSubmissionPage", () => {
  it("will not send a form with required answers missing", async () => {
    const wrapper = await page(form());
    await wrapper.findAll("button").find((b) => b.text().includes("Nộp")).trigger("click");
    await flushPromises();
    expect(api.forms.submit).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Còn 1 mục bắt buộc");
    expect(wrapper.text()).toContain("Cần điền mục này");
  });

  it("sends the answers and shows what the server decided", async () => {
    const wrapper = await page(form());
    await wrapper.find("#f-ghi_chu").setValue("đã làm");
    api.forms.submit.mockResolvedValue(form({ state: "Đã nộp", data: { ghi_chu: "đã làm" }, can: { edit: false, send_back: false } }));
    await wrapper.findAll("button").find((b) => b.text().includes("Nộp")).trigger("click");
    await flushPromises();
    expect(api.forms.submit).toHaveBeenCalledWith("5", { ghi_chu: "đã làm" });
    expect(wrapper.text()).toContain("Đã nộp");
    expect(wrapper.find("#f-ghi_chu").exists()).toBe(false);
  });

  it("keeps what is typed while filling in", async () => {
    vi.useFakeTimers();
    try {
      api.forms.save.mockResolvedValue({});
      const wrapper = await page(form());
      await wrapper.find("#f-ghi_chu").setValue("đang gõ");
      expect(api.forms.save).not.toHaveBeenCalled();
      vi.advanceTimersByTime(1600);
      expect(api.forms.save).toHaveBeenCalledWith("5", { ghi_chu: "đang gõ" });
    } finally {
      vi.useRealTimers();
    }
  });

  it("offers the decision to the approver, and explains itself to the one who submitted", async () => {
    let wrapper = await page(form({ state: "Đã nộp", can: { edit: false, approve: true, send_back: true } }));
    expect(wrapper.findAll("button").some((b) => b.text().includes("Duyệt"))).toBe(true);
    api.forms.approve.mockResolvedValue(form({ state: "Đã duyệt", can: {} }));
    await wrapper.findAll("button").find((b) => b.text().includes("Duyệt")).trigger("click");
    await flushPromises();
    expect(api.forms.approve).toHaveBeenCalledWith("5");
    expect(wrapper.text()).toContain("Tải PDF");

    wrapper = await page(form({ state: "Đã nộp", can: { edit: false, approve: false, send_back: true, self_submitted: true } }));
    expect(wrapper.findAll("button").some((b) => b.text().includes("Duyệt"))).toBe(false);
    expect(wrapper.text()).toContain("cần người khác duyệt");
  });

  it("shows why a form came back", async () => {
    const wrapper = await page(form({ state: "Trả lại", review_note: "Thiếu ảnh", reviewed_by_name: "An" }));
    expect(wrapper.text()).toContain("Thiếu ảnh");
  });
});

describe("FormTemplatePage", () => {
  const template = (extra = {}) => ({
    name: "CL-v01", code: "CL", title: "Phiếu", version: 1, status: "Nháp", submissions: 0, can_edit: true, can_manage: true,
    field_types: Object.values(F), rows: [{ label: "Ghi chú", fieldname: "ghi_chu", fieldtype: F.TEXT, reqd: 0 }], spec: SPEC, ...extra,
  });

  async function designer(data) {
    api.forms.template.mockResolvedValue(data);
    const r = router();
    await r.push("/bieu-mau-mau/CL-v01");
    const wrapper = mount(FormTemplatePage, { global: { plugins: [r], stubs: { ConfirmDialog: true } } });
    await flushPromises();
    return wrapper;
  }

  it("saves a draft with its fields before putting it in use", async () => {
    const wrapper = await designer(template());
    await wrapper.findAll("button").find((b) => b.text().includes("Thêm trường")).trigger("click");
    const labels = wrapper.findAll("input[aria-label='Nhãn trường']");
    await labels[1].setValue("Ngày");
    api.forms.templateSave.mockResolvedValue(template());
    api.forms.templateActivate.mockResolvedValue(template({ status: "Đang dùng", can_edit: false }));
    await wrapper.findAll("button").find((b) => b.text().includes("Đưa vào dùng")).trigger("click");
    await flushPromises();
    expect(api.forms.templateSave.mock.calls[0][2].map((r) => r.label)).toEqual(["Ghi chú", "Ngày"]);
    expect(api.forms.templateActivate).toHaveBeenCalledWith("CL-v01");
    expect(wrapper.text()).toContain("không sửa được");
  });

  it("shows the options a field type needs", async () => {
    const wrapper = await designer(template());
    await wrapper.find("button[aria-label='Chi tiết']").trigger("click");
    expect(wrapper.text()).not.toContain("Các cột");
    await wrapper.find("select[aria-label='Kiểu trường']").setValue(F.TABLE);
    expect(wrapper.text()).toContain("Các cột");
    expect(wrapper.text()).toContain("Các hàng có sẵn");
  });

  it("offers only a new version once in use", async () => {
    const wrapper = await designer(template({ status: "Đang dùng", can_edit: false }));
    expect(wrapper.find("input[aria-label='Nhãn trường']").exists()).toBe(false);
    expect(wrapper.findAll("button").some((b) => b.text().includes("Tạo phiên bản mới"))).toBe(true);
    expect(wrapper.findAll("button").some((b) => b.text().includes("Lưu"))).toBe(false);
  });
});
