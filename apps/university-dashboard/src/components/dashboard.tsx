"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import {
  AlertTriangle,
  Download,
  FileCheck2,
  Filter,
  Play,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CSV_HEADERS, OPTIONAL_EXPORT_FIELDS, type CsvHeader } from "@/lib/csv/schema";
import { getVerifiedMajorMatches, majorExportBlockReason } from "@/lib/csv/major-export";
import { getExportableRecords } from "@/lib/csv/export";
import { fieldCompleteness, summarizeRecords } from "@/lib/quality/scoring";
import type {
  CountryOption,
  CrawlJob,
  EvidenceType,
  MajorCrawlMode,
  QualityFinding,
  RunFile,
  ScraplingCrawlConfig,
  UniversityExportMode,
  UniversityRecord,
} from "@/lib/types";
import { Button, Field, Panel, inputClass } from "@/components/ui";

const STATUS_COLORS: Record<string, string> = {
  Verified: "#2f7d54",
  Probable: "#1f766f",
  "Needs Review": "#a86f13",
  Risky: "#b63f3a",
};

const SOURCE_COLORS: Record<string, string> = {
  wikipedia: "#1f766f",
  wikidata: "#6656a5",
  official: "#2f7d54",
  official_page: "#3b83bd",
  estimated: "#a86f13",
};

function statusPill(status: string) {
  if (status === "Verified") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (status === "Probable") return "border-teal-200 bg-teal-50 text-teal-800";
  if (status === "Needs Review") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-red-200 bg-red-50 text-red-800";
}

function pctColor(pct: number) {
  if (pct >= 90) return "bg-emerald-700";
  if (pct >= 70) return "bg-teal-700";
  if (pct >= 45) return "bg-amber-600";
  return "bg-red-600";
}

function missingCount(record: UniversityRecord) {
  return CSV_HEADERS.filter((header) => !record[header] && !["id", "global_rank", "contact_person"].includes(header)).length;
}

function allFindings(records: UniversityRecord[]) {
  return records.flatMap((record) => record.quality.findings.map((finding) => ({ ...finding, name: record.name, slug: record.slug })));
}

function chartDataFromCounts(counts: Record<string, number>) {
  return Object.entries(counts).map(([name, value]) => ({ name, value }));
}

function chartHasData(data: Array<{ value: number }>) {
  return data.some((entry) => entry.value > 0);
}

function serializePatch(record: UniversityRecord, draft: Partial<Record<CsvHeader, string>>, reviewStatus: string, reviewer: string, reviewerNote: string) {
  const updates: Record<string, string> = {};
  for (const header of CSV_HEADERS) updates[header] = draft[header] ?? record[header] ?? "";
  updates.reviewStatus = reviewStatus;
  updates.reviewer = reviewer;
  updates.reviewerNote = reviewerNote;
  return updates;
}

export function Dashboard() {
  const [countries, setCountries] = useState<CountryOption[]>([]);
  const [runs, setRuns] = useState<RunFile["run"][]>([]);
  const [runFile, setRunFile] = useState<RunFile | null>(null);
  const [job, setJob] = useState<CrawlJob | null>(null);
  const [countryCode, setCountryCode] = useState("356");
  const [limit, setLimit] = useState(50);
  const [fetchMode, setFetchMode] = useState<ScraplingCrawlConfig["fetchMode"]>("auto");
  const [requestTimeout, setRequestTimeout] = useState(8);
  const [browserTimeoutMs, setBrowserTimeoutMs] = useState(12000);
  const [maxOfficialPages, setMaxOfficialPages] = useState(8);
  const [maxAcademicPages, setMaxAcademicPages] = useState(12);
  const [maxBrowserFallbacks, setMaxBrowserFallbacks] = useState(2);
  const [skipGuessedPagesOnFailure, setSkipGuessedPagesOnFailure] = useState(true);
  const [networkIdle, setNetworkIdle] = useState(true);
  const [disableResources, setDisableResources] = useState(true);
  const [realChrome, setRealChrome] = useState(false);
  const [solveCloudflare, setSolveCloudflare] = useState(false);
  const [majorsText, setMajorsText] = useState("Bioengineering\nFood Engineering\nChemical Engineering\nChemistry");
  const [majorMode, setMajorMode] = useState<MajorCrawlMode>("discover");
  const [exportMode, setExportMode] = useState<UniversityExportMode>("all-valid");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"overview" | "results" | "quality" | "trust" | "review" | "majors" | "export">("overview");
  const [filters, setFilters] = useState({
    search: "",
    status: "",
    scoreBand: "",
    missingField: "",
    source: "",
    risky: "",
    rawBlank: "",
  });
  const [editing, setEditing] = useState<UniversityRecord | null>(null);
  const [draft, setDraft] = useState<Partial<Record<CsvHeader, string>>>({});
  const [reviewStatus, setReviewStatus] = useState("Unreviewed");
  const [reviewer, setReviewer] = useState("local-reviewer");
  const [reviewerNote, setReviewerNote] = useState("");

  const records = useMemo(() => runFile?.records ?? [], [runFile]);
  const summary = useMemo(() => summarizeRecords(records), [records]);
  const completeness = useMemo(() => fieldCompleteness(records), [records]);
  const findings = useMemo(() => allFindings(records), [records]);
  const verifiedMajorMatches = useMemo(
    () => getVerifiedMajorMatches(records, runFile?.job?.requestedMajors ?? [], runFile?.job?.majorMode ?? "verify"),
    [records, runFile?.job?.majorMode, runFile?.job?.requestedMajors],
  );
  const exportableRecords = useMemo(() => getExportableRecords(records, exportMode), [exportMode, records]);
  const universitiesWithoutMajors = useMemo(
    () => records.filter((record) => !(record.majorMatches?.length)).length,
    [records],
  );
  const academicPagesChecked = useMemo(
    () => records.reduce((sum, record) => sum + (record.academicStats?.checked ?? 0), 0),
    [records],
  );
  const majorExportBlocked = useMemo(
    () => (runFile ? majorExportBlockReason(runFile.run.crawlerVersion, records) : ""),
    [records, runFile],
  );
  const universitiesWithMajors = records.length - universitiesWithoutMajors;
  const officialSiteFailed = useMemo(
    () =>
      records.filter(
        (record) =>
          record.officialValidation?.status === "unreachable" ||
          record.officialValidation?.status === "missing",
      ).length,
    [records],
  );

  const statusCounts = useMemo(() => {
    const counts = { Verified: 0, Probable: 0, "Needs Review": 0, Risky: 0 };
    for (const record of records) counts[record.quality.status] += 1;
    return counts;
  }, [records]);
  const statusChartData = useMemo(() => chartDataFromCounts(statusCounts), [statusCounts]);

  const scoreBands = useMemo(() => {
    const counts = { "0-44": 0, "45-69": 0, "70-84": 0, "85-100": 0 };
    for (const record of records) {
      if (record.quality.score < 45) counts["0-44"] += 1;
      else if (record.quality.score < 70) counts["45-69"] += 1;
      else if (record.quality.score < 85) counts["70-84"] += 1;
      else counts["85-100"] += 1;
    }
    return counts;
  }, [records]);
  const scoreBandChartData = useMemo(() => chartDataFromCounts(scoreBands), [scoreBands]);

  const sourceCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const record of records) {
      const sources = new Set(record.evidence.map((entry) => entry.type));
      for (const source of sources) counts[source] = (counts[source] ?? 0) + 1;
      if (!sources.size) counts.none = (counts.none ?? 0) + 1;
    }
    return counts;
  }, [records]);
  const sourceChartData = useMemo(() => chartDataFromCounts(sourceCounts), [sourceCounts]);

  const filteredRecords = useMemo(() => {
    return records.filter((record) => {
      const haystack = `${record.name} ${record.slug} ${record.website} ${record.admissions_contact}`.toLowerCase();
      if (filters.search && !haystack.includes(filters.search.toLowerCase())) return false;
      if (filters.status && record.quality.status !== filters.status) return false;
      if (filters.scoreBand) {
        const [min, max] = filters.scoreBand.split("-").map(Number);
        if (record.quality.score < min || record.quality.score > max) return false;
      }
      if (filters.missingField && record[filters.missingField as CsvHeader]) return false;
      if (filters.source) {
        const types = new Set(record.evidence.map((entry) => entry.type));
        if (filters.source === "none" && types.size) return false;
        if (filters.source !== "none" && !types.has(filters.source as EvidenceType)) return false;
      }
      if (filters.risky === "risky" && record.quality.status !== "Risky") return false;
      if (filters.risky === "duplicate" && !record.quality.riskyFlags.some((flag) => flag.includes("duplicate"))) return false;
      if (filters.risky === "contact" && !record.quality.riskyFlags.some((flag) => flag.includes("contact"))) return false;
      if (filters.risky === "schema" && !record.quality.findings.some((finding) => finding.ruleId.startsWith("csv."))) return false;
      if (filters.rawBlank === "raw-available") {
        const hasRawBlank = CSV_HEADERS.some((header) => !record[header] && Boolean(record.rawFields?.[header]));
        if (!hasRawBlank) return false;
      }
      return true;
    });
  }, [filters, records]);

  const loadRun = useCallback(async (runId: string) => {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/runs/${runId}`);
      if (!response.ok) throw new Error("Unable to load run");
      setRunFile((await response.json()) as RunFile);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load run");
    } finally {
      setBusy(false);
    }
  }, []);

  const loadInitial = useCallback(async () => {
    setError("");
    const [countryPayload, runsPayload] = await Promise.all([
      fetch("/api/countries").then((response) => response.json()),
      fetch("/api/runs").then((response) => response.json()),
    ]);
    setCountries(countryPayload.countries ?? []);
    setRuns(runsPayload.runs ?? []);
    if (runsPayload.runs?.[0]?.id) await loadRun(runsPayload.runs[0].id);
  }, [loadRun]);

  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

  async function startCrawl() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/crawl/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          countryCode: Number(countryCode),
          limit,
          fetchMode,
          requestTimeout,
          browserTimeoutMs,
          maxOfficialPages,
          maxAcademicPages,
          maxBrowserFallbacks,
          skipGuessedPagesOnFailure,
          networkIdle,
          disableResources,
          realChrome,
          solveCloudflare,
          majors: Array.from(new Set(majorsText.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean))),
          majorMode,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Crawl failed");
      setJob(payload.job as CrawlJob);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Crawl failed");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!job?.runId || !["queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/crawl/status/${job.runId}`);
        if (!response.ok) return;
        const payload = await response.json();
        const nextJob = payload.job as CrawlJob;
        setJob(nextJob);
        if (nextJob.status === "completed") {
          await loadRun(nextJob.runId);
          const runsPayload = await fetch("/api/runs").then((item) => item.json());
          setRuns(runsPayload.runs ?? []);
        }
      } catch {
        // Polling failures should not interrupt an active local job.
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job?.runId, job?.status, loadRun]);

  function openEditor(record: UniversityRecord) {
    setEditing(record);
    setDraft(
      CSV_HEADERS.reduce((next, header) => {
        next[header] = record[header];
        return next;
      }, {} as Partial<Record<CsvHeader, string>>),
    );
    setReviewStatus(record.reviewStatus);
    setReviewer(record.reviewer ?? "local-reviewer");
    setReviewerNote(record.reviewerNote ?? "");
  }

  async function saveEditing() {
    if (!runFile || !editing) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/records/${runFile.run.id}/${encodeURIComponent(editing.slug)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          updates: serializePatch(editing, draft, reviewStatus, reviewer, reviewerNote),
          note: reviewerNote,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Save failed");
      setRunFile(payload as RunFile);
      setEditing(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  function downloadCsv() {
    if (!runFile) return;
    window.location.href = `/api/export/${runFile.run.id}?mode=${exportMode}`;
  }

  async function recrawlMajors() {
    if (!runFile) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/crawl/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          countryCode: runFile.run.countryCode,
          limit: runFile.records.length,
          fetchMode,
          requestTimeout,
          browserTimeoutMs,
          maxOfficialPages: 0,
          maxAcademicPages,
          maxBrowserFallbacks,
          skipGuessedPagesOnFailure,
          networkIdle,
          disableResources,
          realChrome,
          solveCloudflare,
          majors: Array.from(new Set(majorsText.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean))),
          majorMode,
          baseRunId: runFile.run.id,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Major recrawl failed");
      setJob(payload.job as CrawlJob);
      setActiveTab("majors");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Major recrawl failed");
    } finally {
      setBusy(false);
    }
  }

  function downloadMajorCsv() {
    if (!runFile || !verifiedMajorMatches.length || majorExportBlocked) return;
    window.location.href = `/api/export-majors/${runFile.run.id}`;
  }

  return (
    <main className="min-h-screen bg-stone-100 text-stone-900">
      <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/95 px-5 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-stone-900 text-sm font-bold text-white">UQ</div>
            <div className="min-w-0">
              <h1 className="truncate text-lg font-bold">University Data Quality</h1>
              <p className="truncate text-xs text-stone-500">
                {runFile ? `${runFile.run.country} - ${runFile.run.recordCount} records - ${runFile.run.id}` : "Next.js crawler dashboard"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={() => void loadInitial()} disabled={busy}>
              <RefreshCw size={16} /> Refresh
            </Button>
            <Button variant="primary" onClick={downloadCsv} disabled={!runFile || busy}>
              <Download size={16} /> CSV
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1800px] gap-4 p-5">
        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            <AlertTriangle className="mr-2 inline h-4 w-4" />
            {error}
          </div>
        ) : null}

        <Panel title="Crawl Control" meta="Crawler runs from the UI and stores local JSON runs">
          <div className="grid gap-3 lg:grid-cols-[1fr_160px_220px_220px]">
            <Field label="Country">
              <select className={inputClass} value={countryCode} onChange={(event) => setCountryCode(event.target.value)}>
                {countries.map((country) => (
                  <option key={country.code} value={country.code}>
                    {country.name} ({country.code})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Limit">
              <input className={inputClass} min={1} max={300} type="number" value={limit} onChange={(event) => setLimit(Number(event.target.value))} />
            </Field>
            <Field label="Saved runs">
              <select className={inputClass} value={runFile?.run.id ?? ""} onChange={(event) => void loadRun(event.target.value)}>
                <option value="">No run selected</option>
                {runs.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.country} - {new Date(run.startedAt).toLocaleString()}
                  </option>
                ))}
              </select>
            </Field>
            <div className="flex items-end">
              <Button className="w-full" variant="primary" onClick={() => void startCrawl()} disabled={busy}>
                <Play size={16} /> {busy ? "Working" : "Start crawl"}
              </Button>
            </div>
          </div>
          <div className="mt-4 grid gap-3 border-t border-stone-200 pt-4 md:grid-cols-2 xl:grid-cols-4">
            <Field label="Scrapling fetch mode">
              <select className={inputClass} value={fetchMode} onChange={(event) => setFetchMode(event.target.value as ScraplingCrawlConfig["fetchMode"])}>
                <option value="auto">auto</option>
                <option value="http">http</option>
                <option value="dynamic">dynamic</option>
                <option value="stealthy">stealthy</option>
              </select>
            </Field>
            <Field label="HTTP timeout (sec)">
              <input className={inputClass} min={3} max={90} type="number" value={requestTimeout} onChange={(event) => setRequestTimeout(Number(event.target.value))} />
            </Field>
            <Field label="Browser timeout (ms)">
              <input className={inputClass} min={5000} max={120000} step={1000} type="number" value={browserTimeoutMs} onChange={(event) => setBrowserTimeoutMs(Number(event.target.value))} />
            </Field>
            <Field label="Official pages max">
              <input className={inputClass} min={0} max={20} type="number" value={maxOfficialPages} onChange={(event) => setMaxOfficialPages(Number(event.target.value))} />
            </Field>
            <Field label="Academic pages max">
              <input className={inputClass} min={0} max={50} type="number" value={maxAcademicPages} onChange={(event) => setMaxAcademicPages(Number(event.target.value))} />
            </Field>
            <Field label="Browser fallback limit">
              <input className={inputClass} min={0} max={10} type="number" value={maxBrowserFallbacks} onChange={(event) => setMaxBrowserFallbacks(Number(event.target.value))} />
            </Field>
          </div>
          <div className="mt-3 flex flex-wrap gap-3">
            <Toggle label="Skip guessed failures" checked={skipGuessedPagesOnFailure} onChange={setSkipGuessedPagesOnFailure} />
            <Toggle label="Network idle" checked={networkIdle} onChange={setNetworkIdle} />
            <Toggle label="Disable resources" checked={disableResources} onChange={setDisableResources} />
            <Toggle label="Real Chrome" checked={realChrome} onChange={setRealChrome} />
            <Toggle label="Solve Cloudflare" checked={solveCloudflare} onChange={setSolveCloudflare} />
          </div>
          <div className="mt-3 grid max-w-4xl gap-3 md:grid-cols-[240px_1fr]">
            <Field label="Major crawl mode">
              <select className={inputClass} value={majorMode} onChange={(event) => setMajorMode(event.target.value as MajorCrawlMode)}>
                <option value="discover">Discover all majors</option>
                <option value="verify">Verify selected majors</option>
              </select>
            </Field>
            <Field label={majorMode === "verify" ? "Majors to verify (one per line)" : "Major filter (unused in discover mode)"}>
              <textarea
                className={`${inputClass} min-h-28`}
                value={majorsText}
                onChange={(event) => setMajorsText(event.target.value)}
                disabled={majorMode === "discover"}
                placeholder={"Bioengineering\nFood Engineering\nChemical Engineering\nChemistry"}
              />
            </Field>
          </div>
        </Panel>

        {job ? (
          <Panel
            title="Scrapling Crawl Job"
            meta={`${job.status} - ${job.successCount}/${job.limit} valid records - ${job.failureCount} failed - ${job.rejectedCount ?? 0} country rejected`}
          >
            <div className="grid gap-3 lg:grid-cols-[280px_1fr]">
              <div className="rounded-md border border-stone-200 bg-stone-50 p-3">
                <div className="text-xs font-semibold text-stone-500">Run</div>
                <div className="mt-1 break-all font-mono text-xs text-stone-800">{job.runId}</div>
                <div className="mt-3 text-xs font-semibold text-stone-500">Current</div>
                <div className="mt-1 text-sm text-stone-900">{job.current || "Waiting"}</div>
                <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                  Discovered from Wikipedia list: {job.discoveredCount || 0}. This is not all institutions in the country.
                </div>
                {job.config ? (
                  <div className="mt-3 rounded-md border border-stone-200 bg-white p-2 text-xs text-stone-700">
                    <div className="font-bold text-stone-900">Scrapling config</div>
                    <div className="mt-1">mode: {job.config.fetchMode}</div>
                    <div>http: {job.config.requestTimeout}s</div>
                    <div>browser: {job.config.browserTimeoutMs}ms</div>
                    <div>official pages: {job.config.maxOfficialPages}</div>
                    <div>academic pages: {job.config.maxAcademicPages}</div>
                    <div>browser fallback: {job.config.maxBrowserFallbacks}</div>
                    <div>crawler version: {job.crawlerVersion ?? "legacy"}</div>
                  </div>
                ) : null}
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-stone-200">
                  <div
                    className="h-full rounded-full bg-emerald-700"
                    style={{ width: `${Math.min(100, ((job.successCount + job.failureCount) / Math.max(1, job.discoveredCount || job.limit)) * 100)}%` }}
                  />
                </div>
              </div>
              <div className="max-h-48 overflow-auto rounded-md border border-stone-200 bg-stone-950 p-3 font-mono text-xs text-stone-100">
                {(job.logs.length ? job.logs : ["No logs yet"]).slice(-80).map((line, index) => (
                  <div key={`${line}-${index}`} className="whitespace-pre-wrap break-words">
                    {line}
                  </div>
                ))}
                {job.errors.map((line, index) => (
                  <div key={`err-${line}-${index}`} className="whitespace-pre-wrap break-words text-red-300">
                    {line}
                  </div>
                ))}
              </div>
            </div>
          </Panel>
        ) : null}

        <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-8">
          {[
            ["Institutions", summary.total, "records"],
            ["Countries", summary.countries, "codes"],
            ["Verified", summary.verified, "high confidence"],
            ["Probable", summary.probable, "usable"],
            ["Needs Review", summary.needsReview, "manual"],
            ["Risky", summary.risky, "blocked"],
            ["Completeness", `${summary.completenessScore}%`, "average"],
            ["Export Ready", summary.exportReady, `${summary.exportBlocked} blocked`],
          ].map(([label, value, meta]) => (
            <div key={label} className="rounded-lg border border-stone-200 bg-white p-3 shadow-sm">
              <div className="truncate text-xs font-semibold text-stone-500">{label}</div>
              <div className="mt-2 text-2xl font-bold">{value}</div>
              <div className="mt-1 text-xs text-stone-500">{meta}</div>
            </div>
          ))}
        </div>

        <nav className="flex gap-2 overflow-x-auto">
          {[
            ["overview", "Overview"],
            ["results", "CSV Fields"],
            ["quality", "Data Quality"],
            ["trust", "Trust & Evidence"],
            ["review", "Review Queue"],
            ["majors", "Majors"],
            ["export", "Export Center"],
          ].map(([key, label]) => (
            <button
              key={key}
              className={`rounded-md border px-3 py-2 text-sm font-semibold ${
                activeTab === key ? "border-stone-900 bg-white text-stone-900" : "border-transparent text-stone-500 hover:bg-white"
              }`}
              onClick={() => setActiveTab(key as typeof activeTab)}
            >
              {label}
            </button>
          ))}
        </nav>

        {activeTab === "overview" ? (
          <div className="grid gap-4 xl:grid-cols-3">
            <Panel title="Status Distribution" meta={`${records.length} records`}>
              <ChartShell data={statusChartData}>
                <PieChart>
                  <Pie data={statusChartData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={86}>
                    {statusChartData.map((entry) => (
                      <Cell key={entry.name} fill={STATUS_COLORS[entry.name]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ChartShell>
            </Panel>
            <Panel title="Score Bands">
              <ChartShell data={scoreBandChartData}>
                <BarChart data={scoreBandChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#6656a5" />
                </BarChart>
              </ChartShell>
            </Panel>
            <Panel title="Source Mix">
              <ChartShell data={sourceChartData}>
                <BarChart data={sourceChartData} layout="vertical" margin={{ left: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" allowDecimals={false} />
                  <YAxis dataKey="name" type="category" width={92} />
                  <Tooltip />
                  <Bar dataKey="value">
                    {sourceChartData.map((entry) => (
                      <Cell key={entry.name} fill={SOURCE_COLORS[entry.name] ?? "#65736b"} />
                    ))}
                  </Bar>
                </BarChart>
              </ChartShell>
            </Panel>
          </div>
        ) : null}

        {activeTab === "results" ? (
          <Panel
            title="CSV Field Table"
            meta={`${CSV_HEADERS.length} fixed import fields - ${filteredRecords.length} shown`}
            actions={
              <Button variant="primary" onClick={downloadCsv} disabled={!runFile}>
                <Download size={16} /> CSV
              </Button>
            }
          >
            <div className="mb-4 flex flex-wrap items-end gap-3">
              <div className="w-full sm:w-80 xl:w-96">
                <Field label="Search">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-stone-400" />
                  <input
                    className={`${inputClass} pl-9`}
                    value={filters.search}
                    onChange={(event) => setFilters({ ...filters, search: event.target.value })}
                    placeholder="Name, slug, website, contact"
                  />
                </div>
                </Field>
              </div>
              <div className="w-44">
                <FilterSelect
                  label="Status"
                  value={filters.status}
                  onChange={(value) => setFilters({ ...filters, status: value })}
                  options={["Verified", "Probable", "Needs Review", "Risky"]}
                />
              </div>
              <div className="w-56">
                <FilterSelect
                  label="Missing field"
                  value={filters.missingField}
                  onChange={(value) => setFilters({ ...filters, missingField: value })}
                  options={[...CSV_HEADERS]}
                />
              </div>
              <div className="w-28">
                <Button
                  className="w-full"
                  onClick={() => setFilters({ search: "", status: "", scoreBand: "", missingField: "", source: "", risky: "", rawBlank: "" })}
                >
                  <Filter size={16} /> Clear
                </Button>
              </div>
            </div>
            <CsvFieldsTable records={filteredRecords} onEdit={openEditor} />
          </Panel>
        ) : null}

        {activeTab === "quality" ? (
          <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
            <Panel title="Field Completeness">
              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {completeness.map((field) => (
                  <div key={field.field} className="rounded-md border border-stone-200 bg-stone-50 p-3">
                    <div className="truncate text-xs font-semibold text-stone-700">{field.field}</div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-stone-200">
                      <div className={`h-full ${pctColor(field.pct)}`} style={{ width: `${field.pct}%` }} />
                    </div>
                    <div className="mt-2 text-xs text-stone-500">{field.pct}% present - {field.missing} missing</div>
                  </div>
                ))}
              </div>
            </Panel>
            <Panel title="Schema & Outliers" meta={`${findings.length} findings`}>
              <FindingList findings={findings.filter((finding) => finding.ruleId.startsWith("csv.") || finding.ruleId.startsWith("outlier.")).slice(0, 80)} />
            </Panel>
          </div>
        ) : null}

        {activeTab === "trust" ? (
          <div className="grid gap-4 xl:grid-cols-2">
            <Panel title="Evidence Confidence">
              <ChartShell data={statusChartData} height={300}>
                <BarChart data={statusChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value">
                    {statusChartData.map((entry) => (
                      <Cell key={entry.name} fill={STATUS_COLORS[entry.name]} />
                    ))}
                  </Bar>
                </BarChart>
              </ChartShell>
            </Panel>
            <Panel title="Risk Flags">
              <FindingList findings={findings.filter((finding) => /contact|duplicate|evidence|estimate/.test(finding.ruleId)).slice(0, 80)} />
            </Panel>
          </div>
        ) : null}

        {activeTab === "review" ? (
          <div className="grid gap-4 xl:grid-cols-[300px_1fr]">
            <Panel title="Filters">
              <div className="grid gap-3">
                <Field label="Search">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-stone-400" />
                    <input className={`${inputClass} pl-9`} value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} />
                  </div>
                </Field>
                <FilterSelect label="Status" value={filters.status} onChange={(value) => setFilters({ ...filters, status: value })} options={["Verified", "Probable", "Needs Review", "Risky"]} />
                <FilterSelect label="Score band" value={filters.scoreBand} onChange={(value) => setFilters({ ...filters, scoreBand: value })} options={["85-100", "70-84", "45-69", "0-44"]} />
                <FilterSelect label="Missing field" value={filters.missingField} onChange={(value) => setFilters({ ...filters, missingField: value })} options={[...CSV_HEADERS]} />
                <FilterSelect label="Source" value={filters.source} onChange={(value) => setFilters({ ...filters, source: value })} options={["official", "wikidata", "wikipedia", "none"]} />
                <FilterSelect label="Risk" value={filters.risky} onChange={(value) => setFilters({ ...filters, risky: value })} options={["risky", "duplicate", "contact", "schema"]} />
                <FilterSelect label="Raw data" value={filters.rawBlank} onChange={(value) => setFilters({ ...filters, rawBlank: value })} options={["raw-available"]} />
                <Button onClick={() => setFilters({ search: "", status: "", scoreBand: "", missingField: "", source: "", risky: "", rawBlank: "" })}>
                  <Filter size={16} /> Clear
                </Button>
              </div>
            </Panel>
            <Panel title="Review Queue" meta={`${filteredRecords.length} shown`}>
              <RecordsTable records={filteredRecords} onEdit={openEditor} />
            </Panel>
          </div>
        ) : null}

        {activeTab === "majors" ? (
          <Panel
            title="Verified University Majors"
            meta={`${verifiedMajorMatches.length} matches - ${academicPagesChecked} academic pages checked - ${universitiesWithoutMajors} universities with no majors`}
            actions={
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void recrawlMajors()} disabled={!runFile || busy}>
                  <RefreshCw size={16} /> Crawl majors again
                </Button>
                <Button variant="primary" onClick={downloadMajorCsv} disabled={!runFile || !verifiedMajorMatches.length || Boolean(majorExportBlocked)}>
                  <Download size={16} /> Download Major CSV
                </Button>
              </div>
            }
          >
            <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <Metric icon={<Search size={18} />} label="Attempted" value={runFile?.run.attemptedCount ?? records.length} />
              <Metric icon={<FileCheck2 size={18} />} label="With majors" value={universitiesWithMajors} />
              <Metric icon={<AlertTriangle size={18} />} label="Zero majors" value={universitiesWithoutMajors} />
              <Metric icon={<AlertTriangle size={18} />} label="Official failed" value={officialSiteFailed} />
              <Metric icon={<Filter size={18} />} label="Country rejected" value={runFile?.run.rejectedCount ?? 0} />
            </div>
            {majorExportBlocked ? (
              <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                {majorExportBlocked}
              </div>
            ) : null}
            <MajorMatchesTable matches={verifiedMajorMatches} />
          </Panel>
        ) : null}

        {activeTab === "export" ? (
          <Panel title="Export Center" meta="University and major CSV downloads">
            <div className="mb-4 grid gap-3 md:grid-cols-3">
              <Metric icon={<FileCheck2 size={18} />} label="Header order" value="Valid" />
              <Metric icon={<ShieldCheck size={18} />} label="Exportable" value={summary.exportReady} />
              <Metric icon={<AlertTriangle size={18} />} label="Blocked" value={summary.exportBlocked} />
            </div>
            <div className="mb-4 grid gap-3 md:grid-cols-2">
              <div className="rounded-md border border-stone-200 bg-stone-50 p-4">
                <div className="text-sm font-bold">University_Import_Clean.csv</div>
                <div className="mt-1 text-xs text-stone-500">{exportableRecords.length} valid university rows</div>
                <select className={`${inputClass} mt-3`} value={exportMode} onChange={(event) => setExportMode(event.target.value as UniversityExportMode)}>
                  <option value="all-valid">All valid records</option>
                  <option value="approved-only">Approved only</option>
                </select>
                <Button className="mt-3" variant="primary" onClick={downloadCsv} disabled={!runFile}>
                  <Download size={16} /> Download University CSV
                </Button>
                {runFile && !exportableRecords.length ? (
                  <div className="mt-2 text-xs text-amber-700">
                    No rows satisfy the selected export mode. Check core fields, invalid URLs, duplicate slugs, or review status.
                  </div>
                ) : null}
              </div>
              <div className="rounded-md border border-stone-200 bg-stone-50 p-4">
                <div className="text-sm font-bold">University_Majors_Verified.csv</div>
                <div className="mt-1 text-xs text-stone-500">{verifiedMajorMatches.length} verified university-major rows</div>
                <Button className="mt-3" variant="primary" onClick={downloadMajorCsv} disabled={!runFile || !verifiedMajorMatches.length || Boolean(majorExportBlocked)}>
                  <Download size={16} /> Download Major CSV
                </Button>
                {majorExportBlocked ? <div className="mt-2 text-xs text-amber-700">{majorExportBlocked}</div> : null}
              </div>
            </div>
            <RecordsTable records={[...records].sort((a, b) => Number(b.quality.exportReady) - Number(a.quality.exportReady)).slice(0, 200)} onEdit={openEditor} compact />
          </Panel>
        ) : null}
      </div>

      {editing ? (
        <div className="fixed inset-0 z-40">
          <button className="absolute inset-0 bg-stone-950/35" aria-label="Close editor" onClick={() => setEditing(null)} />
          <aside className="absolute right-0 top-0 grid h-full w-full max-w-4xl grid-rows-[auto_1fr_auto] border-l border-stone-200 bg-white shadow-2xl">
            <header className="flex items-start justify-between gap-4 border-b border-stone-200 p-4">
              <div className="min-w-0">
                <h2 className="break-words text-base font-bold">{editing.name}</h2>
                <p className="mt-1 font-mono text-xs text-stone-500">{editing.slug}</p>
              </div>
              <Button onClick={() => setEditing(null)}>
                <X size={16} /> Close
              </Button>
            </header>
            <div className="overflow-auto p-4">
              <div className="mb-4 grid gap-4 lg:grid-cols-2">
                <Panel title="Quality" meta={`${editing.quality.score}/100`}>
                  <div className={`inline-flex rounded-full border px-3 py-1 text-xs font-bold ${statusPill(editing.quality.status)}`}>
                    {editing.quality.status}
                  </div>
                  <div className="mt-3 grid gap-2">
                    {Object.entries(editing.quality.components).map(([key, value]) => (
                      <div key={key} className="grid grid-cols-[190px_1fr_42px] items-center gap-2 text-xs">
                        <span className="truncate text-stone-500">{key}</span>
                        <div className="h-2 rounded-full bg-stone-200">
                          <div className="h-full rounded-full bg-teal-700" style={{ width: `${Math.min(100, Number(value) * 5)}%` }} />
                        </div>
                        <strong className="text-right">{value}</strong>
                      </div>
                    ))}
                  </div>
                </Panel>
                <Panel title="Evidence">
                  <div className="grid gap-2">
                    {editing.evidence.length ? editing.evidence.map((entry) => (
                      <a key={`${entry.type}-${entry.url}`} className="break-all text-sm text-teal-700 hover:underline" href={entry.url} target="_blank" rel="noreferrer">
                        {entry.type}: {entry.url}
                      </a>
                    )) : <p className="text-sm text-stone-500">No evidence links</p>}
                  </div>
                  {editing.countryValidation ? (
                    <div className="mt-3 rounded-md border border-stone-200 bg-stone-50 p-3 text-xs">
                      <div className="font-bold">Country: {editing.countryValidation.status}</div>
                      <div className="mt-1">{editing.countryValidation.reason}</div>
                    </div>
                  ) : null}
                  {editing.officialValidation ? (
                    <div className="mt-2 rounded-md border border-stone-200 bg-stone-50 p-3 text-xs">
                      <div className="font-bold">Official site: {editing.officialValidation.status}</div>
                      <div className="mt-1">{editing.officialValidation.reason}</div>
                    </div>
                  ) : null}
                </Panel>
              </div>
              {editing.officialPageFailures?.length ? (
                <div className="mb-4">
                  <Panel title="Official Page Failures" meta={`${editing.officialPageFailures.length} skipped pages`}>
                    <div className="grid max-h-48 gap-2 overflow-auto">
                      {editing.officialPageFailures.map((failure) => (
                        <div key={`${failure.url}-${failure.reason}`} className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                          <div className="font-bold">{failure.reason}{failure.guessed ? " - guessed URL" : ""}{failure.browserAttempted ? " - browser tried" : ""}</div>
                          <div className="mt-1 break-all">{failure.url}</div>
                        </div>
                      ))}
                    </div>
                  </Panel>
                </div>
              ) : null}
              <div className="mb-4">
                <Panel title="Raw Evidence vs Export" meta="Raw source values are preserved even when export values are blank">
                  <RawEvidenceGrid record={editing} />
                </Panel>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                {CSV_HEADERS.map((header) => (
                  <Field key={header} label={header}>
                    {["description", "campus_student_life"].includes(header) ? (
                      <textarea className={`${inputClass} min-h-24`} value={draft[header] ?? ""} onChange={(event) => setDraft({ ...draft, [header]: event.target.value })} />
                    ) : (
                      <input className={inputClass} value={draft[header] ?? ""} onChange={(event) => setDraft({ ...draft, [header]: event.target.value })} />
                    )}
                  </Field>
                ))}
                <FilterSelect label="review_status" value={reviewStatus} onChange={setReviewStatus} options={["Unreviewed", "Approved", "Needs Review", "Risky", "Rejected"]} />
                <Field label="reviewer">
                  <input className={inputClass} value={reviewer} onChange={(event) => setReviewer(event.target.value)} />
                </Field>
                <Field label="reviewer_note">
                  <textarea className={`${inputClass} min-h-24`} value={reviewerNote} onChange={(event) => setReviewerNote(event.target.value)} />
                </Field>
              </div>
              <div className="mt-4">
                <Panel title="Findings">
                  <FindingList findings={editing.quality.findings} />
                </Panel>
              </div>
            </div>
            <footer className="flex justify-end border-t border-stone-200 p-4">
              <Button variant="primary" onClick={() => void saveEditing()} disabled={busy}>
                <Save size={16} /> Save
              </Button>
            </footer>
          </aside>
        </div>
      ) : null}
    </main>
  );
}

function ChartShell({
  children,
  data,
  height = 250,
}: {
  children: ReactElement;
  data: Array<{ value: number }>;
  height?: number;
}) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
  }, []);
  if (!ready || !chartHasData(data)) {
    return (
      <div
        style={{ height, minHeight: height, minWidth: 0, width: "100%" }}
        className="grid place-items-center rounded-md border border-dashed border-stone-300 bg-stone-50 text-sm text-stone-500"
      >
        No chart data
      </div>
    );
  }
  return (
    <div style={{ height, minHeight: height, minWidth: 0, width: "100%" }}>
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="rounded-md border border-stone-200 bg-stone-50 p-3">
      <div className="flex items-center gap-2 text-xs font-semibold text-stone-500">{icon}{label}</div>
      <div className="mt-2 text-2xl font-bold">{value}</div>
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="inline-flex items-center gap-2 rounded-md border border-stone-200 bg-white px-3 py-2 text-sm font-semibold text-stone-700">
      <input className="h-4 w-4 accent-stone-900" type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      {label}
    </label>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <Field label={label}>
      <select className={inputClass} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </Field>
  );
}

function RecordsTable({ records, onEdit, compact = false }: { records: UniversityRecord[]; onEdit: (record: UniversityRecord) => void; compact?: boolean }) {
  if (!records.length) {
    return <div className="grid min-h-40 place-items-center rounded-md border border-dashed border-stone-300 bg-stone-50 text-sm text-stone-500">No records</div>;
  }
  return (
    <div className="overflow-auto rounded-md border border-stone-200">
      <table className="w-full min-w-[1180px] border-collapse bg-white text-sm">
        <thead className="bg-stone-50 text-xs text-stone-500">
          <tr>
            <th className="px-3 py-2 text-left">Institution</th>
            <th className="px-3 py-2 text-left">Score</th>
            <th className="px-3 py-2 text-left">Status</th>
            <th className="px-3 py-2 text-left">Review</th>
            <th className="px-3 py-2 text-left">Missing</th>
            <th className="px-3 py-2 text-left">Evidence</th>
            <th className="px-3 py-2 text-left">Website</th>
            <th className="px-3 py-2 text-left">Action</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.slug} className="border-t border-stone-100">
              <td className="max-w-sm px-3 py-3">
                <div className="font-semibold text-stone-900">{record.name}</div>
                <div className="mt-1 font-mono text-xs text-stone-500">{record.slug}</div>
              </td>
              <td className="px-3 py-3 font-bold">{record.quality.score}</td>
              <td className="px-3 py-3">
                <span className={`inline-flex rounded-full border px-2 py-1 text-xs font-bold ${statusPill(record.quality.status)}`}>
                  {record.quality.status}
                </span>
              </td>
              <td className="px-3 py-3">{record.reviewStatus}</td>
              <td className="px-3 py-3">{missingCount(record)}</td>
              <td className="px-3 py-3">{Array.from(new Set(record.evidence.map((entry) => entry.type))).join(", ") || "none"}</td>
              <td className="px-3 py-3">
                {record.website ? <a className="text-teal-700 hover:underline" href={record.website} target="_blank" rel="noreferrer">open</a> : <span className="text-stone-400">blank</span>}
              </td>
              <td className="px-3 py-3">
                <Button onClick={() => onEdit(record)}>{compact ? "Open" : "Edit"}</Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CsvFieldsTable({ records, onEdit }: { records: UniversityRecord[]; onEdit: (record: UniversityRecord) => void }) {
  if (!records.length) {
    return (
      <div className="grid min-h-40 place-items-center rounded-md border border-dashed border-stone-300 bg-stone-50 text-sm text-stone-500">
        No records. Start a crawl or load a saved run.
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {records.map((record) => (
        <article key={record.slug} className="rounded-lg border border-stone-200 bg-white">
          <header className="flex flex-wrap items-start justify-between gap-3 border-b border-stone-200 px-4 py-3">
            <div className="min-w-0">
              <h3 className="break-words text-sm font-bold text-stone-900">{record.name}</h3>
              <p className="mt-1 break-all font-mono text-xs text-stone-500">{record.slug}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="rounded-md bg-stone-100 px-2 py-1 text-xs font-bold text-stone-700">{record.quality.score}/100</span>
              <span className={`inline-flex rounded-full border px-2 py-1 text-xs font-bold ${statusPill(record.quality.status)}`}>
                {record.quality.status}
              </span>
              <Button onClick={() => onEdit(record)}>Edit</Button>
            </div>
          </header>
          <div className="grid gap-2 p-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {CSV_HEADERS.map((header) => {
              const value = record[header];
              const rawValue = record.rawFields?.[header];
              const sourceUrl = record.fieldSources?.[header] ?? record.sourceUrls?.[header];
              const warnings = record.fieldWarnings?.[header] ?? [];
              const importantMissing = !value && !OPTIONAL_EXPORT_FIELDS.has(header);
              return (
                <div
                  key={`${record.slug}-${header}`}
                  className={`min-w-0 rounded-md border p-2 ${importantMissing ? "border-amber-200 bg-amber-50" : "border-stone-200 bg-stone-50"}`}
                >
                  <div className="break-all font-mono text-[11px] font-bold text-stone-500">{header}</div>
                  <div className={`mt-1 min-h-5 break-words text-sm leading-5 ${value ? "text-stone-900" : "text-stone-400"}`}>
                    {value || "blank"}
                  </div>
                  {!value && rawValue ? (
                    <div className="mt-2 rounded border border-blue-200 bg-blue-50 p-1.5 text-xs text-blue-900">
                      <div className="font-semibold">Raw source value</div>
                      <div className="mt-0.5 break-words">{rawValue}</div>
                    </div>
                  ) : null}
                  {sourceUrl ? (
                    <a className="mt-1 block truncate text-xs text-teal-700 hover:underline" href={sourceUrl} target="_blank" rel="noreferrer">
                      source
                    </a>
                  ) : null}
                  {warnings.length ? <div className="mt-1 text-xs text-amber-800">{warnings[0]}</div> : null}
                </div>
              );
            })}
          </div>
        </article>
      ))}
    </div>
  );
}

function RawEvidenceGrid({ record }: { record: UniversityRecord }) {
  const rows = CSV_HEADERS.map((header) => ({
    header,
    exportValue: record[header],
    rawValue: record.rawFields?.[header] ?? "",
    source: record.fieldSources?.[header] ?? record.sourceUrls?.[header] ?? "",
    evidence: record.fieldEvidence?.[header],
    warnings: record.fieldWarnings?.[header] ?? [],
  })).filter((row) => row.rawValue || row.source || row.evidence || row.warnings.length);

  if (!rows.length) {
    return <div className="grid min-h-32 place-items-center rounded-md border border-dashed border-stone-300 bg-stone-50 text-sm text-stone-500">No raw field evidence</div>;
  }

  return (
    <div className="grid gap-2">
      {rows.map((row) => (
        <div key={row.header} className="grid gap-2 rounded-md border border-stone-200 bg-stone-50 p-3 lg:grid-cols-[180px_1fr_1fr]">
          <div className="font-mono text-xs font-bold text-stone-600">{row.header}</div>
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase text-stone-400">Export value</div>
            <div className={`mt-1 break-words text-sm ${row.exportValue ? "text-stone-900" : "text-stone-400"}`}>{row.exportValue || "blank"}</div>
          </div>
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase text-stone-400">Raw / source / warning</div>
            <div className={`mt-1 break-words text-sm ${row.rawValue ? "text-stone-900" : "text-stone-400"}`}>{row.rawValue || "blank"}</div>
            {row.source ? (
              <a className="mt-1 block truncate text-xs text-teal-700 hover:underline" href={row.source} target="_blank" rel="noreferrer">
                {row.source}
              </a>
            ) : null}
            {row.evidence ? (
              <div className="mt-1 text-xs text-stone-600">
                <span className="font-semibold">{row.evidence.rule}</span>: {row.evidence.evidenceText}
              </div>
            ) : null}
            {row.warnings.map((warning) => (
              <div key={warning} className="mt-1 text-xs text-amber-800">{warning}</div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function MajorMatchesTable({ matches }: { matches: ReturnType<typeof getVerifiedMajorMatches> }) {
  if (!matches.length) {
    return (
      <div className="grid min-h-40 place-items-center rounded-md border border-dashed border-stone-300 bg-stone-50 text-sm text-stone-500">
        No verified major matches. Add majors before starting a new crawl.
      </div>
    );
  }
  return (
    <div className="overflow-auto rounded-md border border-stone-200">
      <table className="w-full border-collapse bg-white text-sm">
        <thead className="bg-stone-50 text-xs text-stone-600">
          <tr>
            <th className="px-3 py-2 text-left">University Name</th>
            <th className="px-3 py-2 text-left">Major Name</th>
            <th className="px-3 py-2 text-left">Source URL (Optional)</th>
          </tr>
        </thead>
        <tbody>
          {matches.map((match, index) => (
            <tr key={`${match.universityName}-${match.majorName}-${index}`} className="border-t border-stone-100">
              <td className="px-3 py-3 font-semibold">{match.universityName}</td>
              <td className="px-3 py-3">{match.majorName}</td>
              <td className="px-3 py-3">
                {match.sourceUrl ? <a className="break-all text-teal-700 hover:underline" href={match.sourceUrl} target="_blank" rel="noreferrer">{match.sourceUrl}</a> : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FindingList({ findings }: { findings: Array<QualityFinding & { name?: string; slug?: string }> }) {
  if (!findings.length) {
    return <div className="grid min-h-32 place-items-center rounded-md border border-dashed border-stone-300 bg-stone-50 text-sm text-stone-500">No findings</div>;
  }
  return (
    <div className="grid max-h-[430px] gap-2 overflow-auto">
      {findings.map((finding, index) => (
        <div key={`${finding.ruleId}-${finding.field}-${index}`} className="rounded-md border border-l-4 border-stone-200 border-l-amber-500 bg-stone-50 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${finding.severity === "critical" ? "bg-red-100 text-red-800" : finding.severity === "major" ? "bg-amber-100 text-amber-800" : "bg-teal-100 text-teal-800"}`}>
              {finding.severity}
            </span>
            <span className="font-mono text-xs text-stone-500">{finding.ruleId}</span>
          </div>
          <div className="mt-1 text-sm font-semibold text-stone-800">{finding.name ?? finding.field}</div>
          <div className="mt-1 text-xs text-stone-500">{finding.message}</div>
        </div>
      ))}
    </div>
  );
}
