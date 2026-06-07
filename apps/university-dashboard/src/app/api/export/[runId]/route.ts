import { loadRun } from "@/lib/storage/runs";
import { buildUniversityCsv, validateCsvHeader } from "@/lib/csv/export";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await context.params;
    const mode = new URL(_request.url).searchParams.get("mode") === "approved-only" ? "approved-only" : "all-valid";
    if (!validateCsvHeader()) return new Response("CSV header order mismatch", { status: 500 });
    const runFile = await loadRun(runId);
    const csv = buildUniversityCsv(runFile.records, mode);
    return new Response(csv, {
      status: 200,
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="University_Import_Clean.csv"',
      },
    });
  } catch {
    return new Response("Run not found", { status: 404 });
  }
}
