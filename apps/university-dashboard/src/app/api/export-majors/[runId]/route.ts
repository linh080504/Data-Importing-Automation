import { buildMajorCsv, majorExportBlockReason, validateMajorCsvHeader } from "@/lib/csv/major-export";
import { loadRun } from "@/lib/storage/runs";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await context.params;
    if (!validateMajorCsvHeader()) return new Response("Major CSV header order mismatch", { status: 500 });
    const runFile = await loadRun(runId);
    const blocked = majorExportBlockReason(runFile.run.crawlerVersion, runFile.records);
    if (blocked) return new Response(blocked, { status: 409 });
    const csv = buildMajorCsv(
      runFile.records,
      runFile.job?.requestedMajors ?? [],
      runFile.job?.majorMode ?? "verify",
    );
    return new Response(csv, {
      status: 200,
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="University_Majors_Verified.csv"',
      },
    });
  } catch {
    return new Response("Run not found", { status: 404 });
  }
}
