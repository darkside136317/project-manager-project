<script setup>
import { inject, ref, watch } from "vue";
import { useRouter } from "vue-router";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import MarkedText from "../../components/search/MarkedText.vue";
import Lightbox from "../../components/timeline/Lightbox.vue";
import PhotoGrid from "../../components/timeline/PhotoGrid.vue";
import Timeline from "../../components/timeline/Timeline.vue";
import { api } from "../../lib/api.js";
import { formatDateTime } from "../../lib/format.js";
import { toast } from "../../lib/toast.js";

// Trao đổi of a project: the project's own discussion and every task's, a photo wall, and search over comments and
// documents (Meilisearch, limited to what this person may see).
const { name: project, overview, openTask } = inject("project");
const router = useRouter();
const view = ref("timeline");
const query = ref("");
const hits = ref(null);
const searching = ref(false);
const photos = ref([]);
const morePhotos = ref(false);
const nextPhoto = ref(null);
const loadingPhotos = ref(false);
const lightbox = ref(-1);

async function search() {
  const text = query.value.trim();
  if (text.length < 2) {
    hits.value = null;
    return;
  }
  searching.value = true;
  try {
    hits.value = (await api.activity.search(text, { project: project.value })).hits;
  } catch (e) {
    toast(e.message, "error");
  } finally {
    searching.value = false;
  }
}

function openHit(hit) {
  if (hit.kind === "document") router.push(`/du-an/${project.value}/tai-lieu?tai-lieu=${encodeURIComponent(hit.ref)}`);
  else if (hit.task) openTask(hit.task);
}

async function loadPhotos(reset = true) {
  loadingPhotos.value = true;
  try {
    const page = await api.media.gallery(project.value, { before: reset ? null : nextPhoto.value });
    photos.value = reset ? page.photos : [...photos.value, ...page.photos];
    morePhotos.value = page.more;
    nextPhoto.value = page.next;
  } catch (e) {
    toast(e.message, "error");
  } finally {
    loadingPhotos.value = false;
  }
}

watch(view, (value) => { if (value === "photos" && !photos.value.length) loadPhotos(); });
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex rounded-md border border-line p-0.5" role="group" aria-label="Cách xem">
        <button type="button" class="inline-flex items-center gap-1.5 rounded px-3 py-1 text-sm" :class="view === 'timeline' ? 'bg-primary text-white' : 'text-ink-soft'" :aria-pressed="view === 'timeline'" @click="view = 'timeline'">
          <Icon name="message-square" :size="14" /> <span class="sm:hidden">Trao đổi</span><span class="hidden sm:inline">Dòng thời gian</span>
        </button>
        <button type="button" class="inline-flex items-center gap-1.5 rounded px-3 py-1 text-sm" :class="view === 'photos' ? 'bg-primary text-white' : 'text-ink-soft'" :aria-pressed="view === 'photos'" @click="view = 'photos'">
          <Icon name="images" :size="14" /> <span class="sm:hidden">Ảnh</span><span class="hidden sm:inline">Ảnh hiện trường</span>
        </button>
      </div>
      <form class="ml-auto flex min-w-0 flex-1 gap-2 sm:max-w-sm" role="search" @submit.prevent="search">
        <label class="sr-only" for="discussion-search">Tìm trong trao đổi và tài liệu</label>
        <input id="discussion-search" v-model="query" class="input" type="search" placeholder="Tìm trong trao đổi, tài liệu…" @search="search" />
        <button class="btn" type="submit" :disabled="searching"><Icon :name="searching ? 'loader' : 'search'" :size="16" :spin="searching" /></button>
      </form>
    </div>

    <section v-if="hits" class="card p-3" aria-label="Kết quả tìm kiếm">
      <div class="mb-2 flex items-center">
        <h3 class="m-0 text-sm font-semibold">{{ hits.length ? `${hits.length} kết quả` : "Không tìm thấy" }}</h3>
        <button type="button" class="btn btn-ghost ml-auto px-2 text-xs" @click="hits = null; query = ''"><Icon name="x" :size="14" /> Đóng</button>
      </div>
      <ul class="m-0 list-none space-y-1 p-0">
        <li v-for="hit in hits" :key="hit.id">
          <button type="button" class="block w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-muted" @click="openHit(hit)">
            <span class="flex items-center gap-1.5 text-xs text-ink-muted">
              <Icon :name="hit.kind === 'document' ? 'file-text' : 'message-square'" :size="12" />
              {{ hit.kind === "document" ? "Tài liệu" : hit.who }}<span v-if="hit.task_label"> · {{ hit.task_label }}</span>
              <span v-if="hit.ts"> · {{ formatDateTime(new Date(hit.ts * 1000).toISOString()) }}</span>
            </span>
            <MarkedText v-if="hit.kind === 'document'" class="font-medium" :text="hit.title" />
            <MarkedText class="block text-ink-soft" :text="hit.text" />
          </button>
        </li>
      </ul>
    </section>

    <Timeline v-if="view === 'timeline'" doctype="Project" :name="project" :label="overview?.project?.project_name || project" show-task filters @open-task="openTask">
      <template #title><h3 class="m-0 text-sm font-semibold">Trao đổi chung và theo công việc</h3></template>
    </Timeline>

    <section v-else aria-label="Ảnh hiện trường">
      <EmptyState v-if="!loadingPhotos && !photos.length" icon="images" title="Chưa có ảnh nào" text="Ảnh gửi kèm trao đổi ở các công việc sẽ hiện ở đây." />
      <PhotoGrid :photos="photos" size="lg" @open="(index) => (lightbox = index)">
        <template #badge="{ photo }">
          <span v-if="photo.task_label" class="pointer-events-none absolute bottom-0 left-0 right-0 truncate bg-black/55 px-1 text-[10px] text-white">{{ photo.task_label }}</span>
        </template>
      </PhotoGrid>
      <div v-if="morePhotos" class="mt-3 flex justify-center">
        <button type="button" class="btn" :disabled="loadingPhotos" @click="loadPhotos(false)">Xem thêm ảnh</button>
      </div>
      <Lightbox :photos="photos" :index="lightbox" @close="lightbox = -1" />
    </section>
  </div>
</template>
