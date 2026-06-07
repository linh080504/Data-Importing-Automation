import { mkdir, readFile, writeFile } from "fs/promises";
import path from "path";
import type { CrawlJob, MajorCrawlMode } from "@/lib/types";

const JOB_DIR = path.join(process.cwd(), "data", "jobs");

async function ensureJobDir() {
  await mkdir(JOB_DIR, { recursive: true });
}

function safeId(runId: string) {
  return runId.replace(/[^a-zA-Z0-9_-]/g, "");
}

function jobPath(runId: string) {
  return path.join(JOB_DIR, `${safeId(runId)}.json`);
}

export async function saveJob(job: CrawlJob) {
  await ensureJobDir();
  await writeFile(jobPath(job.runId), JSON.stringify(job, null, 2), "utf-8");
  return job;
}

export async function loadJob(runId: string): Promise<CrawlJob> {
  const content = await readFile(jobPath(runId), "utf-8");
  return JSON.parse(content) as CrawlJob;
}

export async function updateJob(runId: string, updater: (job: CrawlJob) => CrawlJob | void | Promise<CrawlJob | void>) {
  const job = await loadJob(runId);
  const updated = (await updater(job)) ?? job;
  await saveJob(updated);
  return updated;
}

export function createJob(input: {
  runId: string;
  country: string;
  countryCode: number;
  limit: number;
  listPage?: string;
  config?: CrawlJob["config"];
  requestedMajors?: string[];
  majorMode?: MajorCrawlMode;
}): CrawlJob {
  return {
    runId: input.runId,
    status: "queued",
    country: input.country,
    countryCode: input.countryCode,
    limit: input.limit,
    listPage: input.listPage,
    config: input.config,
    requestedMajors: input.requestedMajors,
    majorMode: input.majorMode,
    startedAt: new Date().toISOString(),
    discoveredCount: 0,
    successCount: 0,
    failureCount: 0,
    logs: ["Job queued"],
    errors: [],
  };
}
