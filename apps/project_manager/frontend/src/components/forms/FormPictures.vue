<script setup>
import { ref } from "vue";
import { compressImage } from "../../lib/forms.js";
import { toast } from "../../lib/toast.js";
import Icon from "../Icon.vue";

// Photos of a form: thumbnails, and a button that opens the camera or the gallery on a phone. Pictures are reduced
// before sending; `uploader` keeps them with the form on the server and returns what goes into the answers.
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
  uploader: { type: Function, default: null },
  label: { type: String, default: "Ảnh" },
});
const emit = defineEmits(["update:modelValue"]);
const busy = ref(false);

async function pick(event) {
  const files = [...(event.target.files || [])];
  event.target.value = "";
  if (!files.length || !props.uploader) return;
  busy.value = true;
  try {
    let list = [...props.modelValue];
    for (const file of files) {
      const content = await compressImage(file);
      list = [...list, await props.uploader(content, file.name)];
      emit("update:modelValue", list);
    }
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    busy.value = false;
  }
}
const remove = (index) => emit("update:modelValue", props.modelValue.filter((_item, i) => i !== index));
</script>

<template>
  <div>
    <ul class="m-0 flex list-none flex-wrap gap-2 p-0">
      <li v-for="(item, index) in modelValue" :key="item.file" class="relative">
        <a :href="item.file" target="_blank" rel="noopener"><img :src="item.file" :alt="item.name || label" class="h-24 w-24 rounded-lg border border-line object-cover" /></a>
        <button v-if="!readonly" class="absolute -right-1.5 -top-1.5 grid h-6 w-6 place-items-center rounded-full bg-danger text-white" type="button" aria-label="Bỏ ảnh" @click="remove(index)"><Icon name="x" :size="13" /></button>
      </li>
      <li v-if="!readonly">
        <label class="grid h-24 w-24 cursor-pointer place-items-center rounded-lg border border-dashed border-line-strong text-ink-muted hover:bg-surface-muted">
          <span class="flex flex-col items-center gap-1 text-xs"><Icon :name="busy ? 'loader' : 'camera'" :size="20" :spin="busy" /> {{ busy ? "Đang gửi" : "Thêm ảnh" }}</span>
          <input class="sr-only" type="file" accept="image/*" multiple :disabled="busy" :aria-label="`Thêm ảnh: ${label}`" @change="pick" />
        </label>
      </li>
    </ul>
    <p v-if="readonly && !modelValue.length" class="m-0 text-sm text-ink-muted">Không có ảnh.</p>
  </div>
</template>
