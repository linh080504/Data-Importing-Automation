import { NextResponse } from "next/server";
import { z } from "zod";
import { startScraplingJob } from "@/lib/jobs/scrapling-job";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const START_BODY = z.object({
  countryCode: z.coerce.number().int().positive(),
  limit: z.coerce.number().int().min(1).max(300).optional(),
  listPage: z.string().url().optional(),
  fetchMode: z.enum(["auto", "http", "dynamic", "stealthy"]).optional(),
  requestTimeout: z.coerce.number().int().min(3).max(90).optional(),
  browserTimeoutMs: z.coerce.number().int().min(5000).max(120000).optional(),
  maxOfficialPages: z.coerce.number().int().min(0).max(20).optional(),
  maxAcademicPages: z.coerce.number().int().min(0).max(50).optional(),
  maxBrowserFallbacks: z.coerce.number().int().min(0).max(10).optional(),
  skipGuessedPagesOnFailure: z.boolean().optional(),
  networkIdle: z.boolean().optional(),
  disableResources: z.boolean().optional(),
  realChrome: z.boolean().optional(),
  solveCloudflare: z.boolean().optional(),
  majors: z.array(z.string().trim().min(1).max(120)).max(200).optional(),
  majorMode: z.enum(["discover", "verify"]).optional(),
  baseRunId: z.string().regex(/^run-[a-zA-Z0-9_-]+$/).optional(),
});

export async function POST(request: Request) {
  try {
    const body = START_BODY.parse(await request.json());
    const job = await startScraplingJob(body);
    return NextResponse.json({ ok: true, runId: job.runId, job });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to start crawl";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
