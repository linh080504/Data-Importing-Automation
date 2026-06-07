import { spawn } from "child_process";
import path from "path";
import { getCountryByCode } from "@/lib/countries";
import { createJob, saveJob, updateJob } from "@/lib/jobs/storage";
import { rescoreRecords } from "@/lib/quality/scoring";
import { saveRun } from "@/lib/storage/runs";
import type { CrawlJob, MajorCrawlMode, RunFile, ScraplingCrawlConfig, UniversityRecord } from "@/lib/types";

function scraplingPath() {
  return process.env.SCRAPLING_PATH || String.raw`D:\work\New folder\beyond\Scrapling`;
}

function crawlerScript() {
  return (
    process.env.SCRAPLING_CRAWLER_SCRIPT ||
    String.raw`D:\work\New folder\beyond\apps\university-dashboard\scraper\university_scrapling_crawler.py`
  );
}

function pythonCommand() {
  return process.env.PYTHON || "python";
}

function appendLog(job: CrawlJob, message: string) {
  job.logs = [...job.logs.slice(-199), `${new Date().toISOString()} ${message}`];
}

async function handleEvent(job: CrawlJob, event: Record<string, unknown>) {
  if (event.event === "started") {
    job.status = "running";
    job.listPage = String(event.listPage ?? job.listPage ?? "");
    appendLog(job, `Started ${job.listPage ?? ""}`.trim());
  } else if (event.event === "discovered") {
    job.discoveredCount = Number(event.count ?? 0);
    appendLog(job, `Discovered ${job.discoveredCount} institution links`);
  } else if (event.event === "config") {
    const config = event.config as ScraplingCrawlConfig | undefined;
    if (config) job.config = config;
    job.crawlerVersion = Number(event.crawlerVersion ?? job.crawlerVersion ?? 0);
    const features = Array.isArray(event.features) ? event.features.join(", ") : "";
    appendLog(job, `Scrapling config loaded${features ? ` (${features})` : ""}`);
  } else if (event.event === "progress") {
    job.current = String(event.current ?? "");
    job.successCount = Number(event.success ?? job.successCount);
    job.failureCount = Number(event.failed ?? job.failureCount);
    appendLog(job, `Crawling ${event.index}/${event.total}: ${job.current}`);
  } else if (event.event === "record_error") {
    job.failureCount = Number(event.failed ?? job.failureCount + 1);
    const message = `${event.current ?? "record"}: ${event.error ?? "unknown error"}`;
    job.errors = [...job.errors.slice(-99), message];
    appendLog(job, `Failed ${message}`);
  } else if (event.event === "country_rejected") {
    job.rejectedCount = Number(event.rejected ?? (job.rejectedCount ?? 0) + 1);
    appendLog(job, `Country rejected ${event.current ?? "candidate"}: ${event.reason ?? "country mismatch"}`);
  } else if (event.event === "enriched") {
    const current = String(event.current ?? "record");
    const fields = Array.isArray(event.fields) ? event.fields.join(", ") : String(event.fields ?? "");
    appendLog(job, `Enriched missing fields from official site for ${current}: ${fields}`);
  } else if (event.event === "fetch_mode") {
    appendLog(job, `Scrapling ${event.mode ?? "fetch"} used for ${event.purpose ?? "page"}: ${event.url ?? ""}`);
  } else if (event.event === "official_summary") {
    const failures = Array.isArray(event.failures) ? event.failures : [];
    appendLog(
      job,
      `Official checked for ${event.current ?? "record"}: ${event.checked ?? 0}, skipped: ${event.skipped ?? 0}, browser fallback: ${event.browserFallbacks ?? 0}`,
    );
    for (const failure of failures.slice(0, 2) as Array<{ reason?: string; url?: string }>) {
      appendLog(job, `Skipped official page (${failure.reason ?? "unknown"}): ${failure.url ?? ""}`);
    }
    const academic = event.academic as { checked?: number; extracted?: number } | undefined;
    if (academic) {
      job.academicPagesChecked = (job.academicPagesChecked ?? 0) + Number(academic.checked ?? 0);
      job.majorMatchesCount = (job.majorMatchesCount ?? 0) + Number(academic.extracted ?? 0);
    }
  } else if (event.event === "final") {
    const records = rescoreRecords((event.records ?? []) as UniversityRecord[]);
    const errors = (event.errors ?? []) as Array<{ title?: string; error?: string }>;
    const rejected = (event.rejected ?? []) as NonNullable<RunFile["run"]["rejectedCandidates"]>;
    job.status = "completed";
    job.finishedAt = new Date().toISOString();
    job.successCount = records.length;
    job.failureCount = errors.length;
    job.attemptedCount = Number(event.attemptedCount ?? records.length + errors.length + rejected.length);
    job.rejectedCount = rejected.length;
    job.crawlerVersion = Number(event.crawlerVersion ?? job.crawlerVersion ?? 0);
    job.errors = errors.map((error) => `${error.title ?? "record"}: ${error.error ?? "unknown error"}`);
    appendLog(job, `Completed with ${records.length} records`);
    const runFile: RunFile = {
      run: {
        id: job.runId,
        country: job.country,
        countryCode: job.countryCode,
        startedAt: job.startedAt,
        finishedAt: job.finishedAt,
        status: "completed",
        requestedLimit: job.limit,
        discoveredCount: job.discoveredCount,
        recordCount: records.length,
        crawlerVersion: job.crawlerVersion,
        attemptedCount: job.attemptedCount,
        rejectedCount: job.rejectedCount,
        rejectedCandidates: rejected,
      },
      job,
      records,
      audit: [],
    };
    await saveRun(runFile);
  }
}

export async function startScraplingJob(input: {
  countryCode: number;
  limit?: number;
  listPage?: string;
  fetchMode?: ScraplingCrawlConfig["fetchMode"];
  requestTimeout?: number;
  browserTimeoutMs?: number;
  maxOfficialPages?: number;
  maxAcademicPages?: number;
  maxBrowserFallbacks?: number;
  skipGuessedPagesOnFailure?: boolean;
  networkIdle?: boolean;
  disableResources?: boolean;
  realChrome?: boolean;
  solveCloudflare?: boolean;
  majors?: string[];
  majorMode?: MajorCrawlMode;
  baseRunId?: string;
}) {
  const country = getCountryByCode(input.countryCode);
  if (!country) throw new Error(`Unsupported country code: ${input.countryCode}`);
  const limit = Math.min(Math.max(Number(input.limit || 50), 1), 300);
  const config: ScraplingCrawlConfig = {
    fetchMode: input.fetchMode ?? "auto",
    requestTimeout: Math.min(Math.max(Number(input.requestTimeout ?? 8), 3), 90),
    browserTimeoutMs: Math.min(Math.max(Number(input.browserTimeoutMs ?? 12000), 5000), 120000),
    maxOfficialPages: Math.min(Math.max(Number(input.maxOfficialPages ?? 8), 0), 20),
    maxAcademicPages: Math.min(Math.max(Number(input.maxAcademicPages ?? 12), 0), 50),
    maxBrowserFallbacks: Math.min(Math.max(Number(input.maxBrowserFallbacks ?? 2), 0), 10),
    skipGuessedPagesOnFailure: input.skipGuessedPagesOnFailure ?? true,
    networkIdle: input.networkIdle ?? true,
    disableResources: input.disableResources ?? true,
    realChrome: input.realChrome ?? false,
    solveCloudflare: input.solveCloudflare ?? false,
  };
  const runId = `run-${country.code}-${Date.now()}`;
  const job = await saveJob(
    createJob({
      runId,
      country: country.name,
      countryCode: country.code,
      limit,
      listPage: input.listPage || country.listPageCandidates[0],
      config,
      requestedMajors: input.majors ?? [],
      majorMode: input.majorMode ?? "discover",
    }),
  );

  const args = [
    crawlerScript(),
    "--run-id",
    runId,
    "--country-code",
    String(country.code),
    "--country",
    country.name,
    "--limit",
    String(limit),
    "--fetch-mode",
    config.fetchMode,
    "--request-timeout",
    String(config.requestTimeout),
    "--browser-timeout-ms",
    String(config.browserTimeoutMs),
    "--max-official-pages",
    String(config.maxOfficialPages),
    "--max-academic-pages",
    String(config.maxAcademicPages),
    "--max-browser-fallbacks",
    String(config.maxBrowserFallbacks),
    "--majors-json",
    JSON.stringify(input.majors ?? []),
    "--major-mode",
    input.majorMode ?? "discover",
  ];
  if (input.baseRunId) {
    args.push("--base-run-file", path.join(process.cwd(), "data", "runs", `${input.baseRunId}.json`));
  }
  if (config.skipGuessedPagesOnFailure) args.push("--skip-guessed-pages-on-failure");
  if (config.networkIdle) args.push("--network-idle");
  if (config.disableResources) args.push("--disable-resources");
  if (config.realChrome) args.push("--real-chrome");
  if (config.solveCloudflare) args.push("--solve-cloudflare");
  if (input.listPage) args.push("--list-page", input.listPage);

  const child = spawn(pythonCommand(), args, {
    cwd: process.cwd(),
    env: {
      ...process.env,
      PYTHONPATH: [scraplingPath(), process.env.PYTHONPATH].filter(Boolean).join(";"),
      PYTHONIOENCODING: "utf-8",
    },
    windowsHide: true,
  });

  job.pid = child.pid;
  job.status = "running";
  appendLog(job, `Spawned Python crawler pid=${child.pid ?? "unknown"}`);
  await saveJob(job);

  let buffer = "";
  let updateChain = Promise.resolve();
  const enqueueUpdate = (updater: Parameters<typeof updateJob>[1]) => {
    updateChain = updateChain
      .then(() => updateJob(runId, updater))
      .then(() => undefined)
      .catch((error) => {
        console.error(`Unable to update crawl job ${runId}`, error);
      });
  };

  child.stdout.setEncoding("utf-8");
  child.stdout.on("data", (chunk: string) => {
    buffer += chunk;
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      enqueueUpdate(async (current) => {
        try {
          await handleEvent(current, JSON.parse(trimmed));
        } catch {
          appendLog(current, trimmed);
        }
      });
    }
  });

  child.stderr.setEncoding("utf-8");
  child.stderr.on("data", (chunk: string) => {
    enqueueUpdate((current) => {
      const text = chunk.trim();
      if (!text) return;
      if (/\]\s+(INFO|WARNING|ERROR):/.test(text) || /Page\.goto: Download is starting|Connection timed out|ERR_CONNECTION_TIMED_OUT/i.test(text)) {
        appendLog(current, text);
        return;
      }
      current.errors = [...current.errors.slice(-99), text];
      appendLog(current, `stderr: ${text}`);
    });
  });

  child.on("close", (code) => {
    enqueueUpdate((current) => {
      if (current.status !== "completed") {
        current.status = "failed";
        current.finishedAt = new Date().toISOString();
        current.errors = [...current.errors, `Crawler exited before final output with code ${code}`];
        appendLog(current, `Exited with code ${code}`);
      }
    });
  });

  return job;
}
