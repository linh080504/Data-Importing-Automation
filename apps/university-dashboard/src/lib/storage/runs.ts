import { mkdir, readFile, readdir, writeFile } from "fs/promises";
import path from "path";
import { CSV_HEADERS } from "@/lib/csv/schema";
import { rescoreRecords } from "@/lib/quality/scoring";
import type { AuditEntry, ReviewStatus, RunFile, UniversityRecord } from "@/lib/types";
import { toAsciiText } from "@/lib/text/ascii";

const DATA_DIR = path.join(process.cwd(), "data", "runs");

async function ensureDataDir() {
  await mkdir(DATA_DIR, { recursive: true });
}

function runPath(runId: string) {
  const safeId = runId.replace(/[^a-zA-Z0-9_-]/g, "");
  return path.join(DATA_DIR, `${safeId}.json`);
}

export async function saveRun(runFile: RunFile) {
  await ensureDataDir();
  await writeFile(runPath(runFile.run.id), JSON.stringify(runFile, null, 2), "utf-8");
  return runFile;
}

export async function loadRun(runId: string): Promise<RunFile> {
  const content = await readFile(runPath(runId), "utf-8");
  const runFile = JSON.parse(content) as RunFile;
  const repairableFields = ["name", "description", "financials", "campus_student_life", "contact_person"] as const;
  runFile.records = rescoreRecords(
    runFile.records.map((record) => {
      const repaired = { ...record };
      for (const field of repairableFields) {
        const source = repaired[field] || repaired.rawFields?.[field] || "";
        if (source) repaired[field] = toAsciiText(source);
      }
      return repaired;
    }),
  );
  return runFile;
}

export async function listRuns() {
  await ensureDataDir();
  const files = await readdir(DATA_DIR);
  const runs: RunFile["run"][] = [];
  for (const file of files.filter((name) => name.endsWith(".json"))) {
    try {
      const runFile = JSON.parse(await readFile(path.join(DATA_DIR, file), "utf-8")) as RunFile;
      runs.push(runFile.run);
    } catch {
      // Ignore corrupted local run files; they are not part of application state.
    }
  }
  return runs.sort((left, right) => right.startedAt.localeCompare(left.startedAt));
}

type RecordPatch = Partial<Pick<UniversityRecord, (typeof CSV_HEADERS)[number]>> & {
  reviewStatus?: ReviewStatus;
  reviewer?: string;
  reviewerNote?: string;
};

export async function patchRecord(runId: string, slug: string, patch: RecordPatch, note = "") {
  const runFile = await loadRun(runId);
  const index = runFile.records.findIndex((record) => record.slug === slug);
  if (index < 0) throw new Error(`Record not found: ${slug}`);

  const before = runFile.records[index];
  const updated: UniversityRecord = {
    ...before,
    ...CSV_HEADERS.reduce((csvPatch, header) => {
      if (patch[header] !== undefined) csvPatch[header] = String(patch[header] ?? "").trim();
      return csvPatch;
    }, {} as Partial<UniversityRecord>),
    reviewStatus: patch.reviewStatus ?? before.reviewStatus,
    reviewer: patch.reviewer ?? before.reviewer,
    reviewerNote: patch.reviewerNote ?? before.reviewerNote,
    updatedAt: new Date().toISOString(),
  };

  runFile.records[index] = updated;
  runFile.records = rescoreRecords(runFile.records);
  const rescored = runFile.records[index];
  const audit: AuditEntry = {
    id: `audit-${Date.now()}-${slug}`,
    targetSlug: slug,
    action: "record_update",
    user: patch.reviewer || "local",
    timestamp: new Date().toISOString(),
    before,
    after: rescored,
    note,
  };
  runFile.audit = [...(runFile.audit ?? []), audit];
  await saveRun(runFile);
  return runFile;
}
