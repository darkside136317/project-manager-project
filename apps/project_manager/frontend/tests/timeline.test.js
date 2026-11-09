import { describe, expect, it } from "vitest";
import { fitWithin, localStamp, readExif } from "../src/lib/images.js";
import {
  MARK_END,
  MARK_START,
  byDay,
  dayLabel,
  insertMention,
  mapLink,
  marked,
  mentionAt,
  plainText,
  queuedState,
  segments,
} from "../src/lib/timeline.js";

/** A JPEG holding only an EXIF block: DateTimeOriginal and a GPS position (little or big endian). */
function jpegWithExif({ little = true, date = "2026:11:08 07:45:12", lat = [10, 46, 36.84], latRef = "N", lng = [106, 42, 3.24], lngRef = "E" } = {}) {
  const tiff = [];
  const u16 = (v) => (little ? [v & 255, v >> 8] : [v >> 8, v & 255]);
  const u32 = (v) => (little ? [v & 255, (v >> 8) & 255, (v >> 16) & 255, (v >>> 24) & 255] : [(v >>> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255]);
  const entry = (tag, type, count, value) => [...u16(tag), ...u16(type), ...u32(count), ...value];
  // layout: header(8) | IFD0 @8 (2 entries) | Exif IFD @38 (1 entry) | GPS IFD @56 (4 entries) | data @110
  const dataStart = 110;
  const dateBytes = [...date].map((c) => c.charCodeAt(0)).concat(0);
  const rational = (parts) => parts.flatMap((v) => [...u32(Math.round(v * 100)), ...u32(100)]);
  const latAt = dataStart + dateBytes.length;
  const lngAt = latAt + 24;
  tiff.push(...(little ? [0x49, 0x49] : [0x4d, 0x4d]), ...u16(42), ...u32(8));
  tiff.push(...u16(2), ...entry(0x8769, 4, 1, u32(38)), ...entry(0x8825, 4, 1, u32(56)), ...u32(0));
  tiff.push(...u16(1), ...entry(0x9003, 2, dateBytes.length, u32(dataStart)), ...u32(0));
  tiff.push(...u16(4),
    ...entry(1, 2, 2, [latRef.charCodeAt(0), 0, 0, 0]), ...entry(2, 5, 3, u32(latAt)),
    ...entry(3, 2, 2, [lngRef.charCodeAt(0), 0, 0, 0]), ...entry(4, 5, 3, u32(lngAt)), ...u32(0));
  while (tiff.length < dataStart) tiff.push(0);
  tiff.push(...dateBytes, ...rational(lat), ...rational(lng));
  const app1 = [0x45, 0x78, 0x69, 0x66, 0, 0, ...tiff];
  const bytes = [0xff, 0xd8, 0xff, 0xe1, (app1.length + 2) >> 8, (app1.length + 2) & 255, ...app1, 0xff, 0xda, 0, 2, 0xff, 0xd9];
  return new Uint8Array(bytes).buffer;
}

describe("EXIF of a photo", () => {
  it("reads when and where, in either byte order", () => {
    for (const little of [true, false]) {
      const found = readExif(jpegWithExif({ little }));
      expect(found.takenAt).toBe("2026-11-08 07:45:12");
      expect(found.lat).toBeCloseTo(10.7769, 4);
      expect(found.lng).toBeCloseTo(106.7009, 4);
    }
  });

  it("puts the south and the west below zero", () => {
    const found = readExif(jpegWithExif({ latRef: "S", lngRef: "W" }));
    expect(found.lat).toBeLessThan(0);
    expect(found.lng).toBeLessThan(0);
  });

  it("gives nothing for a picture without EXIF or a broken one", () => {
    expect(readExif(new Uint8Array([0xff, 0xd8, 0xff, 0xda, 0, 2]).buffer)).toEqual({ takenAt: null, lat: null, lng: null });
    expect(readExif(new Uint8Array([1, 2, 3]).buffer)).toEqual({ takenAt: null, lat: null, lng: null });
    expect(readExif(jpegWithExif({ date: "0000:00:00 00:00:00" })).takenAt).toBeNull();
    const cut = jpegWithExif().slice(0, 60);
    expect(() => readExif(cut)).not.toThrow();
  });

  it("shrinks to fit, never grows", () => {
    expect(fitWithin(4000, 3000)).toEqual({ width: 1600, height: 1200 });
    expect(fitWithin(3000, 4000)).toEqual({ width: 1200, height: 1600 });
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600 });
  });

  it("writes local time the way the server reads it", () => {
    expect(localStamp(new Date(2026, 10, 9, 7, 5, 3))).toBe("2026-11-09 07:05:03");
    expect(localStamp(new Date("nonsense"))).toBeNull();
  });
});

describe("discussion text", () => {
  it("cuts mentions out of the text", () => {
    expect(segments("Nhờ @[Lê Văn An](an@x.vn) xem\nnhé")).toEqual([
      { type: "text", text: "Nhờ " }, { type: "mention", name: "Lê Văn An", user: "an@x.vn" }, { type: "text", text: " xem\nnhé" },
    ]);
    expect(plainText("@[An](an@x.vn) ok")).toBe("@An ok");
    expect(segments("<b>không phải HTML</b>")).toEqual([{ type: "text", text: "<b>không phải HTML</b>" }]);
  });

  it("finds the @ being typed and replaces it with a mention", () => {
    expect(mentionAt("Gửi @lê", 7)).toEqual({ query: "lê", start: 4 });
    expect(mentionAt("@", 1)).toEqual({ query: "", start: 0 });
    expect(mentionAt("mail an@x.vn", 12)).toBeNull();  // an address is not a mention
    expect(mentionAt("Gửi @lê van", 11)).toBeNull();
    const result = insertMention("Gửi @lê nhé", 4, 7, { user: "le@x.vn", full_name: "Lê Bình" });
    expect(result.text).toBe("Gửi @[Lê Bình](le@x.vn)  nhé");
    expect(result.caret).toBe(4 + "@[Lê Bình](le@x.vn) ".length);
  });

  it("splits search marks without HTML", () => {
    expect(marked(`Thiếu ${MARK_START}gông${MARK_END} cột`)).toEqual([
      { text: "Thiếu ", marked: false }, { text: "gông", marked: true }, { text: " cột", marked: false },
    ]);
    expect(marked("không có")).toEqual([{ text: "không có", marked: false }]);
  });

  it("groups entries by day", () => {
    const today = new Date(2026, 10, 9, 12);
    expect(dayLabel("2026-11-09 08:00:00", today)).toBe("Hôm nay");
    expect(dayLabel("2026-11-08 23:00:00", today)).toBe("Hôm qua");
    expect(dayLabel("2026-10-31 09:00:00", today)).toBe("31/10/2026");
    const groups = byDay([{ creation: "2026-11-09 09:00" }, { creation: "2026-11-09 08:00" }, { creation: "2026-11-07 10:00" }], today);
    expect(groups.map((group) => [group.label, group.entries.length])).toEqual([["Hôm nay", 2], ["07/11/2026", 1]]);
  });

  it("links a photo to the map only when it has a position", () => {
    expect(mapLink(10.7, 106.6)).toContain("mlat=10.7&mlon=106.6");
    expect(mapLink(null, 106.6)).toBe("");
  });

  it("says where a queued item stands", () => {
    expect(queuedState({ state: "waiting" }, false).text).toBe("Chờ có mạng");
    expect(queuedState({ state: "sending" }, true).text).toBe("Đang gửi…");
    expect(queuedState({ state: "failed", error: "Dài quá" }, true)).toEqual({ text: "Không gửi được: Dài quá", tone: "danger" });
    expect(queuedState({ state: "waiting", error: "Máy chủ bận" }, true).text).toBe("Sẽ thử lại: Máy chủ bận");
  });
});
