import { NextResponse } from "next/server";
import { listRuns } from "@/lib/storage/runs";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({ runs: await listRuns() });
}
