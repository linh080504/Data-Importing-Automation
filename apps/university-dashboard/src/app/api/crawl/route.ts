import { NextResponse } from "next/server";
import { z } from "zod";
import { startScraplingJob } from "@/lib/jobs/scrapling-job";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const CRAWL_BODY = z.object({
  countryCode: z.coerce.number().int().positive(),
  limit: z.coerce.number().int().min(1).max(300).optional(),
});

export async function POST(request: Request) {
  try {
    const body = CRAWL_BODY.parse(await request.json());
    const job = await startScraplingJob(body);
    return NextResponse.json({ ok: true, runId: job.runId, job });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown crawl error";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
