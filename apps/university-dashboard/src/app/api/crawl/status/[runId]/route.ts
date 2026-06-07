import { NextResponse } from "next/server";
import { loadJob, updateJob } from "@/lib/jobs/storage";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function pidIsAlive(pid?: number) {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export async function GET(_request: Request, context: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await context.params;
    let job = await loadJob(runId);
    if ((job.status === "running" || job.status === "queued") && job.pid && !pidIsAlive(job.pid)) {
      job = await updateJob(runId, (current) => {
        if (current.status !== "running" && current.status !== "queued") return;
        current.status = "failed";
        current.finishedAt = new Date().toISOString();
        const message = `Crawler process pid=${current.pid} is no longer running before final output`;
        if (!current.errors.includes(message)) current.errors = [...current.errors, message];
        current.logs = [...current.logs.slice(-199), `${new Date().toISOString()} ${message}`];
      });
    }
    return NextResponse.json({ ok: true, job });
  } catch {
    return NextResponse.json({ error: "Job not found" }, { status: 404 });
  }
}
