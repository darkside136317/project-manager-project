<script setup>
import { nextTick, onMounted, ref, watch } from "vue";
import { blobToBase64 } from "../../lib/forms.js";
import { toast } from "../../lib/toast.js";
import Icon from "../Icon.vue";

// A signature drawn with a finger, a pen or the mouse. It is sent as a PNG when the person confirms it.
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
  uploader: { type: Function, default: null },
  label: { type: String, default: "Chữ ký" },
});
const emit = defineEmits(["update:modelValue"]);
const canvas = ref(null);
const hasInk = ref(false);
const busy = ref(false);
let drawing = false;
let context = null;

function prepare() {
  const element = canvas.value;
  context = element?.getContext?.("2d") || null;
  if (!context) return;
  const ratio = window.devicePixelRatio || 1;
  element.width = element.clientWidth * ratio;
  element.height = element.clientHeight * ratio;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.lineWidth = 2.2;
  context.lineCap = "round";
  context.lineJoin = "round";
  context.strokeStyle = "#111827";
  hasInk.value = false;
}

function at(event) {
  const box = canvas.value.getBoundingClientRect();
  return [event.clientX - box.left, event.clientY - box.top];
}
function down(event) {
  if (!context) return;
  drawing = true;
  canvas.value.setPointerCapture?.(event.pointerId);
  context.beginPath();
  context.moveTo(...at(event));
}
function move(event) {
  if (!drawing || !context) return;
  context.lineTo(...at(event));
  context.stroke();
  hasInk.value = true;
}
const up = () => { drawing = false; };

async function confirm() {
  if (!hasInk.value || !props.uploader) return;
  busy.value = true;
  try {
    const blob = await new Promise((resolve) => canvas.value.toBlob(resolve, "image/png"));
    const item = await props.uploader(await blobToBase64(blob), "chu-ky.png");
    emit("update:modelValue", [item]);
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    busy.value = false;
  }
}
async function again() {
  emit("update:modelValue", []);
  await nextTick();
  prepare();
}

onMounted(prepare);
watch(() => props.modelValue.length, async (count) => {
  if (!count) {
    await nextTick();
    prepare();
  }
});
</script>

<template>
  <div>
    <div v-if="modelValue.length" class="flex flex-wrap items-center gap-3">
      <img :src="modelValue[0].file" :alt="label" class="h-20 max-w-full rounded-lg border border-line bg-white p-1" />
      <button v-if="!readonly" class="btn btn-ghost" type="button" @click="again"><Icon name="undo" :size="16" /> Ký lại</button>
    </div>
    <p v-else-if="readonly" class="m-0 text-sm text-ink-muted">Chưa ký.</p>
    <div v-else>
      <canvas ref="canvas" class="block h-36 w-full touch-none rounded-lg border border-line-strong bg-white" :aria-label="`Ô ký: ${label}`"
        @pointerdown.prevent="down" @pointermove.prevent="move" @pointerup="up" @pointercancel="up" @pointerleave="up"></canvas>
      <div class="mt-2 flex gap-2">
        <button class="btn" type="button" :disabled="!hasInk || busy" @click="prepare">Xóa</button>
        <button class="btn btn-primary" type="button" :disabled="!hasInk || busy" @click="confirm"><Icon :name="busy ? 'loader' : 'check'" :size="16" :spin="busy" /> Dùng chữ ký này</button>
      </div>
    </div>
  </div>
</template>
