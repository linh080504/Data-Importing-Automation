import { NextResponse } from "next/server";
import { COUNTRIES } from "@/lib/countries";

export async function GET() {
  return NextResponse.json({ countries: COUNTRIES });
}
