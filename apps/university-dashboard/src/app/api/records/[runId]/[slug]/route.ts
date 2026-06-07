import { NextResponse } from "next/server";
import { z } from "zod";
import { patchRecord } from "@/lib/storage/runs";

export const dynamic = "force-dynamic";

const PATCH_BODY = z.object({
  updates: z.record(z.unknown()).default({}),
  note: z.string().optional(),
});

export async function PATCH(request: Request, context: { params: Promise<{ runId: string; slug: string }> }) {
  try {
    const { runId, slug } = await context.params;
    const body = PATCH_BODY.parse(await request.json());
    const runFile = await patchRecord(runId, decodeURIComponent(slug), body.updates, body.note ?? "");
    return NextResponse.json(runFile);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unable to update record";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
