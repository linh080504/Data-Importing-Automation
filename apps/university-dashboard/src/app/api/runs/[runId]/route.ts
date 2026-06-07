import { NextResponse } from "next/server";
import { loadRun } from "@/lib/storage/runs";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ runId: string }> }) {
  try {
    const { runId } = await context.params;
    return NextResponse.json(await loadRun(runId));
  } catch {
    return NextResponse.json({ error: "Run not found" }, { status: 404 });
  }
}
