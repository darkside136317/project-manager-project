<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import DynamicForm from "../components/forms/DynamicForm.vue";
import Icon from "../components/Icon.vue";
import { api } from "../lib/api.js";
import { F, TEMPLATE, fieldNeeds, templateStateBadge } from "../lib/forms.js";
import { pageTitle } from "../lib/page.js";
import { toast } from "../lib/toast.js";

// /pm/bieu-mau-mau/:name — one version of a form. A draft is edited here, with a preview of what was last saved;
// a version in use is read-only: changing it means a new version.
const route = useRoute();
const router = useRouter();
const name = computed(() => String(route.params.name || ""));
const doc = ref(null);
const rows = ref([]);
const meta = ref({});
const error = ref("");
const problems = ref("");
const busy = ref(false);
const opened = ref(-1);
const previewData = ref({});
const removing = ref(false);
const retiring = ref(false);
const editable = computed(() => Boolean(doc.value?.can_edit));

function adopt(value) {
  doc.value = value;
  rows.value = value.rows.map((row) => ({ ...row }));
  meta.value = { title: value.title, category: value.category, description: value.description, print_note: value.print_note };
  pageTitle.value = value.title;
}

async function load() {
  error.value = "";
  try {
    adopt(await api.forms.template(name.value));
    opened.value = -1;
    previewData.value = {};
  } catch (e) {
    error.value = e.message;
  }
}

async function run(action, message) {
  busy.value = true;
  problems.value = "";
  try {
    const result = await action();
    if (message) toast(message);
    return result;
  } catch (e) {
    problems.value = e.message;
    return null;
  } finally {
    busy.value = false;
  }
}

async function save(message = "Đã lưu bản nháp") {
  const result = await run(() => api.forms.templateSave(name.value, meta.value, rows.value), message);
  if (result) adopt(result);
  return Boolean(result);
}

async function activate() {
  if (!(await save(""))) return;
  const result = await run(() => api.forms.templateActivate(name.value), "Đã đưa mẫu vào dùng");
  if (result) adopt(result);
}

async function newVersion() {
  const result = await run(() => api.forms.templateNewVersion(name.value), "Đã tạo phiên bản mới");
  if (result) router.push(`/bieu-mau-mau/${encodeURIComponent(result.name)}`);
}

async function retire() {
  const result = await run(() => api.forms.templateRetire(name.value), "Đã ngừng dùng mẫu");
  retiring.value = false;
  if (result) adopt(result);
}

async function remove() {
  const result = await run(() => api.forms.templateRemove(name.value), "Đã xóa bản nháp");
  removing.value = false;
  if (result) router.push("/bieu-mau-mau");
}

function addRow() {
  rows.value.push({ label: "", fieldtype: F.TEXT, reqd: 0 });
  opened.value = rows.value.length - 1;
}
function swap(index, other) {
  const list = rows.value;
  [list[index], list[other]] = [list[other], list[index]];
  opened.value = opened.value === index ? other : opened.value === other ? index : opened.value;
}
function drop(index) {
  rows.value.splice(index, 1);
  opened.value = -1;
}

watch(name, load, { immediate: true });
</script>

<template>
  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <template v-else-if="doc">
    <RouterLink to="/bieu-mau-mau" class="inline-flex items-center gap-1 text-xs text-ink-muted hover:underline"><Icon name="chevron-left" :size="14" /> Mẫu biểu mẫu</RouterLink>
    <header class="mb-4 mt-1 flex flex-wrap items-start gap-2">
      <div class="min-w-0">
        <h1 class="m-0 text-xl font-semibold tracking-tight">{{ doc.title }}</h1>
        <p class="m-0 text-sm text-ink-muted">{{ doc.code }}, phiên bản {{ doc.version }} · {{ doc.submissions }} bản nộp</p>
      </div>
      <span :class="templateStateBadge(doc.status)">{{ doc.status }}</span>
      <div class="ml-auto flex flex-wrap gap-2">
        <template v-if="editable">
          <button class="btn btn-ghost" type="button" :disabled="busy" @click="removing = true">Xóa nháp</button>
          <button class="btn" type="button" :disabled="busy" @click="save()"><Icon name="save" :size="16" /> Lưu</button>
          <button class="btn btn-primary" type="button" :disabled="busy" @click="activate"><Icon name="check" :size="16" /> Đưa vào dùng</button>
        </template>
        <template v-else-if="doc.can_manage">
          <button v-if="doc.status === TEMPLATE.ACTIVE" class="btn btn-ghost" type="button" :disabled="busy" @click="retiring = true">Ngừng dùng</button>
          <button class="btn btn-primary" type="button" :disabled="busy" @click="newVersion"><Icon name="copy" :size="16" /> Tạo phiên bản mới</button>
        </template>
      </div>
    </header>
    <p v-if="problems" class="mb-4 whitespace-pre-line rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ problems }}</p>
    <p v-if="!editable" class="mb-4 rounded-md bg-surface-muted px-3 py-2 text-sm text-ink-soft">Phiên bản này không sửa được. Tạo phiên bản mới để thay đổi: các bản đã nộp vẫn giữ nguyên nội dung.</p>

    <div class="grid gap-4 lg:grid-cols-2">
      <section v-if="editable" class="space-y-4" aria-label="Thiết kế">
        <div class="card grid gap-3 p-4 sm:grid-cols-2">
          <div class="sm:col-span-2"><label class="label" for="m-title">Tên biểu mẫu</label><input id="m-title" v-model="meta.title" class="input" /></div>
          <div><label class="label" for="m-category">Nhóm</label><input id="m-category" v-model="meta.category" class="input" /></div>
          <div class="sm:col-span-2"><label class="label" for="m-desc">Mô tả</label><textarea id="m-desc" v-model="meta.description" class="input" rows="2"></textarea></div>
          <div class="sm:col-span-2"><label class="label" for="m-note">Ghi chú cuối bản in</label><textarea id="m-note" v-model="meta.print_note" class="input" rows="2"></textarea></div>
        </div>

        <ol class="m-0 list-none space-y-2 p-0" aria-label="Các trường">
          <li v-for="(row, index) in rows" :key="index" class="card p-3">
            <div class="flex items-center gap-2">
              <span class="w-5 shrink-0 text-xs text-ink-muted">{{ index + 1 }}</span>
              <input v-model="row.label" class="input min-w-0 flex-1" placeholder="Nhãn trường" aria-label="Nhãn trường" />
            </div>
            <div class="mt-2 flex flex-wrap items-center gap-2 pl-7">
              <select v-model="row.fieldtype" class="input w-auto" aria-label="Kiểu trường">
                <option v-for="kind in doc.field_types" :key="kind" :value="kind">{{ kind }}</option>
              </select>
              <label v-if="fieldNeeds(row.fieldtype).required" class="flex items-center gap-1 text-xs"><input v-model="row.reqd" type="checkbox" :true-value="1" :false-value="0" /> Bắt buộc</label>
              <span class="ml-auto flex">
                <button class="btn btn-ghost btn-icon !min-h-0 !p-1" type="button" aria-label="Chi tiết" @click="opened = opened === index ? -1 : index"><Icon :name="opened === index ? 'chevron-down' : 'chevron-right'" :size="15" /></button>
                <button class="btn btn-ghost btn-icon !min-h-0 !p-1" type="button" aria-label="Lên" :disabled="index === 0" @click="swap(index, index - 1)"><Icon name="arrow-up" :size="15" /></button>
                <button class="btn btn-ghost btn-icon !min-h-0 !p-1" type="button" aria-label="Xuống" :disabled="index === rows.length - 1" @click="swap(index, index + 1)"><Icon name="arrow-down" :size="15" /></button>
                <button class="btn btn-ghost btn-icon !min-h-0 !p-1" type="button" aria-label="Xóa trường" @click="drop(index)"><Icon name="trash-2" :size="15" /></button>
              </span>
            </div>
            <div v-if="opened === index" class="mt-3 grid gap-3 border-t border-line pt-3 sm:grid-cols-2">
              <div class="sm:col-span-2"><label class="label">Gợi ý khi điền<input v-model="row.description" class="input mt-1 font-normal normal-case tracking-normal" /></label></div>
              <div v-if="fieldNeeds(row.fieldtype).options" class="sm:col-span-2">
                <label class="label">{{ row.fieldtype === F.TABLE ? "Các cột, mỗi dòng một cột" : "Các lựa chọn, mỗi dòng một lựa chọn" }}
                  <textarea v-model="row.options" class="input mt-1 font-normal normal-case tracking-normal" rows="4"></textarea></label>
                <p v-if="row.fieldtype === F.TABLE" class="m-0 mt-1 text-xs text-ink-muted">Ví dụ: <code>Nội dung</code>, <code>Số lượng | Số</code>, <code>Ngày về | Ngày</code>, <code>Kết quả | Chọn: Đạt, Không đạt</code>, <code>Đã xong | Hộp kiểm</code></p>
              </div>
              <div v-if="fieldNeeds(row.fieldtype).preset" class="sm:col-span-2">
                <label class="label">Các hàng có sẵn (danh mục kiểm tra)
                  <textarea v-model="row.preset_rows" class="input mt-1 font-normal normal-case tracking-normal" rows="4"></textarea></label>
                <p class="m-0 mt-1 text-xs text-ink-muted">Mỗi dòng là nội dung cột đầu của một hàng. Có hàng sẵn thì người điền không thêm, bớt hàng. Để trống nếu người điền tự thêm hàng.</p>
              </div>
              <template v-if="fieldNeeds(row.fieldtype).number">
                <div><label class="label">Đơn vị<input v-model="row.unit" class="input mt-1 font-normal normal-case tracking-normal" /></label></div>
                <div class="grid grid-cols-2 gap-2">
                  <label class="label">Nhỏ nhất<input v-model="row.min_value" class="input mt-1 font-normal" inputmode="decimal" /></label>
                  <label class="label">Lớn nhất<input v-model="row.max_value" class="input mt-1 font-normal" inputmode="decimal" /></label>
                </div>
              </template>
            </div>
          </li>
        </ol>
        <button class="btn" type="button" @click="addRow"><Icon name="plus" :size="16" /> Thêm trường</button>
      </section>

      <section :class="editable ? '' : 'lg:col-span-2'" aria-labelledby="t-preview">
        <h2 id="t-preview" class="m-0 mb-2 text-sm font-semibold">Xem trước<span v-if="editable" class="font-normal text-ink-muted"> (theo bản đã lưu)</span></h2>
        <div class="card p-4">
          <p v-if="!doc.spec.fields.length" class="m-0 text-sm text-ink-muted">Chưa có trường nào: thêm trường rồi bấm Lưu.</p>
          <DynamicForm v-else v-model="previewData" :spec="doc.spec" />
        </div>
      </section>
    </div>

    <ConfirmDialog :open="removing" title="Xóa bản nháp" danger confirm-text="Xóa" :busy="busy" message="Bản nháp này sẽ bị xóa." @confirm="remove" @cancel="removing = false" />
    <ConfirmDialog :open="retiring" title="Ngừng dùng mẫu" confirm-text="Ngừng dùng" :busy="busy" message="Không ai điền được mẫu này nữa cho tới khi có phiên bản mới. Các bản đã nộp vẫn giữ nguyên." @confirm="retire" @cancel="retiring = false" />
  </template>
</template>
