import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/lib/api.js";
import { FAILED, MemoryStore, SENDING, WAITING, createOutbox, isRetryable, sizeText } from "../src/lib/outbox.js";

vi.mock("../src/lib/api.js", async (importOriginal) => {
  const real = await importOriginal();
  return { ...real, api: { media: { upload: vi.fn() }, activity: { post: vi.fn() }, tasks: { report: vi.fn() } } };
});

const offline = () => new ApiError("Không kết nối được máy chủ.");
const refused = (message = "Nội dung dài quá") => new ApiError(message, { status: 417, excType: "ValidationError" });

function setup(senders, user = "a@x") {
  const store = new MemoryStore();
  const sent = [];
  const queue = createOutbox({ store, senders, user, onSent: (item, answer) => sent.push([item.id, answer]) });
  return { store, queue, sent };
}

describe("outbox", () => {
  it("sends oldest first and forgets what arrived", async () => {
    const order = [];
    const { queue, store, sent } = setup({ note: async (item) => { order.push(item.payload.n); return `ok-${item.payload.n}`; } });
    await queue.add("note", { n: 1 });
    await queue.add("note", { n: 2 });
    const result = await queue.flush();
    expect(order).toEqual([1, 2]);
    expect(result).toEqual({ sent: 2, failed: 0, waiting: 0 });
    expect(await store.all()).toEqual([]);
    expect(sent.map(([, answer]) => answer)).toEqual(["ok-1", "ok-2"]);
  });

  it("stops at a lost connection and keeps the order for next time", async () => {
    const tried = [];
    let online = false;
    const { queue } = setup({ note: async (item) => { tried.push(item.payload.n); if (!online) throw offline(); return true; } });
    await queue.add("note", { n: 1 });
    await queue.add("note", { n: 2 });
    expect((await queue.flush()).waiting).toBe(2);
    expect(tried).toEqual([1]);  // the second one was not tried before the first
    expect(queue.items.map((item) => item.state)).toEqual([WAITING, WAITING]);
    expect(queue.items[0].error).toMatch(/kết nối/);
    online = true;
    expect((await queue.flush()).sent).toBe(2);
    expect(tried).toEqual([1, 1, 2]);
  });

  it("marks what the server refuses and goes on with the rest", async () => {
    const { queue } = setup({ note: async (item) => { if (item.payload.n === 1) throw refused(); return true; } });
    await queue.add("note", { n: 1 });
    await queue.add("note", { n: 2 });
    expect(await queue.flush()).toEqual({ sent: 1, failed: 1, waiting: 0 });
    expect(queue.items).toHaveLength(1);
    expect(queue.items[0].state).toBe(FAILED);
    expect(queue.items[0].error).toBe("Nội dung dài quá");
    expect((await queue.flush()).sent).toBe(0);  // a failed item waits for the user
  });

  it("tries a failed item again when asked, or drops it", async () => {
    let fixed = false;
    const { queue, store } = setup({ note: async () => { if (!fixed) throw refused(); return true; } });
    const item = await queue.add("note", {});
    await queue.flush();
    fixed = true;
    await queue.retry(item.id);
    expect(queue.items).toHaveLength(0);
    const other = await queue.add("note", {});
    await queue.remove(other.id);
    expect(await store.all()).toEqual([]);
  });

  it("leaves another account's items alone", async () => {
    const store = new MemoryStore();
    const first = createOutbox({ store, senders: { note: async () => { throw offline(); } }, user: "a@x" });
    await first.add("note", {});
    const send = vi.fn(async () => true);
    const second = createOutbox({ store, senders: { note: send }, user: "b@x" });
    expect((await second.flush()).sent).toBe(0);
    expect(send).not.toHaveBeenCalled();
    expect(second.items).toHaveLength(1);
  });

  it("joins a round that is already running", async () => {
    let release;
    const send = vi.fn(() => new Promise((resolve) => { release = resolve; }));
    const { queue } = setup({ note: send });
    await queue.add("note", {});
    const one = queue.flush();
    const two = queue.flush();
    await vi.waitFor(() => expect(send).toHaveBeenCalled());
    release(true);
    await Promise.all([one, two]);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("picks up an item that was being sent when the app closed", async () => {
    const store = new MemoryStore();
    await store.put({ id: "x", kind: "note", user: "a@x", state: SENDING, tries: 1, photos: [], created: 1, payload: {} });
    const { queue } = { queue: createOutbox({ store, senders: { note: async () => true }, user: "a@x" }) };
    await queue.load();
    expect(queue.items[0].state).toBe(WAITING);
  });

  it("knows which errors may pass by themselves", () => {
    expect(isRetryable(offline())).toBe(true);
    expect(isRetryable(new ApiError("x", { status: 502 }))).toBe(true);
    expect(isRetryable(new ApiError("x", { status: 400, excType: "CSRFTokenError" }))).toBe(true);
    expect(isRetryable(new ApiError("x", { status: 403, excType: "PermissionError" }))).toBe(false);
    expect(isRetryable(refused())).toBe(false);
  });

  it("writes sizes for people", () => {
    expect(sizeText(0)).toBe("0 KB");
    expect(sizeText(300)).toBe("1 KB");
    expect(sizeText(512 * 1024)).toBe("512 KB");
    expect(sizeText(3.5 * 1024 * 1024)).toBe("3,5 MB");
  });
});

describe("sending a queued comment", () => {
  it("uploads each photo once, then posts the comment with the same ids", async () => {
    const { api } = await import("../src/lib/api.js");
    const { SENDERS } = await import("../src/lib/sync.js");
    api.media.upload.mockReset();
    api.activity.post.mockReset();
    api.media.upload.mockResolvedValueOnce({ name: 1 }).mockRejectedValueOnce(offline()).mockResolvedValue({ name: 2 });
    api.activity.post.mockResolvedValue({ name: 99 });
    const item = {
      id: "comment-1", kind: "comment", reference: { doctype: "Task", name: "TASK-1" }, payload: { content: "Ảnh cốp pha" },
      photos: [
        { uuid: "p1", name: "a.jpg", type: "image/jpeg", data: new Uint8Array([1, 2]).buffer, takenAt: "2026-11-09 08:00:00", lat: 10.7, lng: 106.6, done: false },
        { uuid: "p2", name: "b.jpg", type: "image/jpeg", data: new Uint8Array([3]).buffer, takenAt: null, lat: null, lng: null, done: false },
      ],
    };
    const saved = vi.fn();
    await expect(SENDERS.comment(item, saved)).rejects.toThrow();  // the second photo lost its connection
    expect(item.photos.map((photo) => photo.done)).toEqual([true, false]);
    expect(saved).toHaveBeenCalledTimes(1);
    expect(await SENDERS.comment(item, saved)).toEqual({ name: 99 });
    expect(api.media.upload).toHaveBeenCalledTimes(3);  // p1 once, p2 twice: never p1 again
    const sentIds = api.media.upload.mock.calls.map(([form]) => form.get("client_uuid"));
    expect(sentIds).toEqual(["p1", "p2", "p2"]);
    expect(api.media.upload.mock.calls[0][0].get("lat")).toBe("10.7");
    expect(api.media.upload.mock.calls[1][0].get("taken_at")).toBeNull();
    expect(api.activity.post).toHaveBeenCalledWith("Task", "TASK-1", { content: "Ảnh cốp pha", media: ["p1", "p2"], client_uuid: "comment-1" });
  });
});
