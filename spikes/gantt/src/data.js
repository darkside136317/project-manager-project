// The same plan for every candidate: phases > groups of 10 tasks, finish-to-start links between consecutive tasks of a
// group, and a few start-to-start / finish-to-finish links across groups (the four link types appear).
const DAY = 86400000;

export function makePlan(count, start = new Date(2026, 0, 5)) {
  const tasks = [];
  const links = [];
  let id = 0;
  let cursor = start.getTime();
  const phases = Math.max(1, Math.round(count / 1000));
  const groupsPerPhase = Math.max(1, Math.floor((count / phases - 1) / 11));
  for (let p = 1; p <= phases && tasks.length < count; p++) {
    const phaseId = ++id;
    tasks.push({ id: phaseId, parent: 0, text: `Giai đoạn ${p}`, wbs: `${p}`, group: true, start: cursor, end: cursor, progress: 0 });
    for (let g = 1; g <= groupsPerPhase && tasks.length < count; g++) {
      const groupId = ++id;
      const group = { id: groupId, parent: phaseId, text: `Hạng mục ${p}.${g}`, wbs: `${p}.${g}`, group: true, start: cursor, end: cursor, progress: 0 };
      tasks.push(group);
      let previous = null;
      for (let t = 1; t <= 10 && tasks.length < count; t++) {
        const taskId = ++id;
        const length = 2 + ((taskId * 7) % 9);
        const begin = previous ? previous.end : cursor;
        const task = { id: taskId, parent: groupId, text: `Công tác ${p}.${g}.${t}`, wbs: `${p}.${g}.${t}`, group: false,
          start: begin, end: begin + length * DAY, progress: (taskId * 13) % 101 };
        tasks.push(task);
        if (previous) links.push({ id: links.length + 1, source: previous.id, target: taskId, type: "FS" });
        previous = task;
      }
      group.end = previous ? previous.end : group.start;
      if (g > 1 && g % 5 === 0) links.push({ id: links.length + 1, source: groupId - 11, target: groupId, type: g % 10 ? "SS" : "FF" });
      cursor += 3 * DAY;
    }
  }
  for (const task of tasks) {
    if (!task.group) continue;
    const kids = tasks.filter((t) => t.parent === task.id);
    if (kids.length) {
      task.start = Math.min(...kids.map((k) => k.start));
      task.end = Math.max(...kids.map((k) => k.end));
    }
  }
  return { tasks, links };
}

export const toDate = (ms) => new Date(ms);
export const isoDay = (ms) => new Date(ms).toISOString().slice(0, 10);
