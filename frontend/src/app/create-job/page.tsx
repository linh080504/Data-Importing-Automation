import Link from "next/link";
import { redirect } from "next/navigation";

import { DashboardLayout } from "@/components/dashboard-layout";
import { ProcessingSubmitButton } from "@/components/processing-submit-button";
import { Card, MetricCard, PageHeader } from "@/components/ui";
import { createCrawlJob, getCountries, getFieldSuggestions, getRecommendedSources, getSources, getTemplates } from "@/lib/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function readValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

async function createJobAction(formData: FormData) {
  "use server";

  const country = String(formData.get("country") ?? "").trim();
  const cleanTemplateId = String(formData.get("templateId") ?? "").trim();
  const sourceIds = formData
    .getAll("sourceIds")
    .map((value) => String(value).trim())
    .filter(Boolean);
  const crawlMode = String(formData.get("crawlMode") ?? "trusted_sources") as "trusted_sources" | "prompt_discovery" | "supplemental_discovery";
  const discoveryPrompt = String(formData.get("discoveryPrompt") ?? "").trim();
  const selectedFocusFields = formData
    .getAll("criticalFields")
    .map((value) => String(value).trim())
    .filter(Boolean);
  const typedFocusFields = String(formData.get("criticalFieldsText") ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const criticalFields = Array.from(new Set(selectedFocusFields.length > 0 ? selectedFocusFields : typedFocusFields));
  const aiAssist = formData.get("aiAssist") === "true";

  const params = new URLSearchParams();
  if (country) {
    params.set("country", country);
  }
  if (cleanTemplateId) {
    params.set("templateId", cleanTemplateId);
  }
  if (sourceIds.length > 0) {
    for (const sourceId of sourceIds) {
      params.append("sourceIds", sourceId);
    }
  }
  if (criticalFields.length > 0) {
    params.set("criticalFields", criticalFields.join(","));
  }
  params.set("aiAssist", aiAssist ? "true" : "false");

  if (!country) {
    params.set("error", "Select a live country from the configured source catalog.");
    redirect(`/create-job?${params.toString()}`);
  }

  if (!cleanTemplateId) {
    params.set("error", "Select a template before creating the job.");
    redirect(`/create-job?${params.toString()}`);
  }

  if (crawlMode === "prompt_discovery" && !discoveryPrompt) {
    params.set("error", "Enter the discovery prompt before creating a prompt-discovery job.");
    redirect(`/create-job?${params.toString()}`);
  }

  if (criticalFields.length < 3 || criticalFields.length > 30) {
    params.set("error", "Choose between 3 and 30 focus fields from the selected import template before creating the job.");
    redirect(`/create-job?${params.toString()}`);
  }

  const result = await createCrawlJob({
    country,
    sourceIds,
    crawlMode,
    discoveryInput:
      crawlMode === "prompt_discovery"
        ? {
            prompt_text: discoveryPrompt,
            prompt_source: "manual",
            seed_sources: sourceIds,
          }
        : {
            selected_source_ids: sourceIds,
          },
    criticalFields,
    cleanTemplateId,
    aiAssist,
  });

  if (!result) {
    params.set("error", "The job could not be processed right now.");
    redirect(`/create-job?${params.toString()}`);
  }

  redirect(`/crawl-jobs/${result.jobId}`);
}

export default async function CreateJobPage({ searchParams }: { searchParams: SearchParams }) {
  const resolvedSearchParams = await searchParams;
  const countries = await getCountries();
  const defaultCountry = countries[0] ?? "";
  const selectedCountry = readValue(resolvedSearchParams.country) ?? defaultCountry;
  const selectedTemplateId = readValue(resolvedSearchParams.templateId);
  const errorMessage = readValue(resolvedSearchParams.error) ?? null;

  const selectedSourceIds = [resolvedSearchParams.sourceIds]
    .flat()
    .flatMap((value) => (Array.isArray(value) ? value : [value]))
    .filter((value): value is string => typeof value === "string" && value.length > 0);
  const selectedCriticalFields = (readValue(resolvedSearchParams.criticalFields) ?? "").split(",").filter(Boolean);
  const selectedCrawlMode = (readValue(resolvedSearchParams.crawlMode) as "trusted_sources" | "prompt_discovery" | "supplemental_discovery" | undefined) ?? "trusted_sources";
  const discoveryPromptValue =
    readValue(resolvedSearchParams.discoveryPrompt) ??
    (selectedCountry
      ? `Find universities and colleges in ${selectedCountry}. Prioritize official and trustworthy sources. Return structured results including name, website, location, admissions, tuition, and quality signals when available.`
      : "Find universities and colleges. Prioritize official and trustworthy sources. Return structured results including name, website, location, admissions, tuition, and quality signals when available.");
  const aiAssist = readValue(resolvedSearchParams.aiAssist) !== "false";

  const [sources, templates, recommendedSources] = await Promise.all([
    selectedCountry ? getSources(selectedCountry) : Promise.resolve([]),
    getTemplates(),
    selectedCountry ? getRecommendedSources(selectedCountry) : Promise.resolve({ country: "", templates: [] }),
  ]);
  const activeTemplateId = selectedTemplateId ?? templates[0]?.id ?? "";
  const activeSourceIds = selectedSourceIds.length > 0 ? selectedSourceIds : sources[0] ? [sources[0].id] : [];
  const suggestions = activeTemplateId ? await getFieldSuggestions(activeTemplateId) : null;
  const activeTemplateColumns = suggestions?.templateColumns ?? [];
  const selectedTemplateCriticalFields = activeTemplateColumns.length > 0 ? selectedCriticalFields.filter((field) => activeTemplateColumns.includes(field)) : selectedCriticalFields;
  const activeCriticalFields = selectedTemplateCriticalFields.length > 0 ? selectedTemplateCriticalFields : (suggestions?.suggestedCriticalFields ?? []);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          eyebrow="Create job"
          title="Create and process a job"
          description="Choose the country, template, collection mode, and focus fields so the backend can crawl evidence before extraction, judging, review, and export."
        />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Available countries" value={String(countries.length)} subtext="Current MVP source coverage" />
          <MetricCard label="Configured sources" value={String(sources.length)} subtext={`Saved in DB for ${selectedCountry}`} />
          <MetricCard label="Templates" value={String(templates.length)} subtext="Import schemas ready to use" />
          <MetricCard label="Suggested fields" value={String(suggestions?.suggestedCriticalFields.length ?? 0)} subtext="Recommended focus fields" />
          <MetricCard label="Trusted plan sources" value={String(recommendedSources.templates.length)} subtext={`Auto-resolved for ${selectedCountry}`} />
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <Card title="Job setup form">
            <form action={createJobAction} className="space-y-5">
              <div className="grid gap-4 md:grid-cols-2">
                <label className="space-y-2 text-sm">
                  <span className="font-semibold text-slate-900">Country</span>
                  <select name="country" defaultValue={selectedCountry} disabled={countries.length === 0} className="w-full rounded-xl border border-slate-300 px-3 py-2 text-slate-900 disabled:bg-slate-100 disabled:text-slate-500">
                    {countries.length === 0 ? <option value="">No live countries configured</option> : null}
                    {countries.map((country) => (
                      <option key={country} value={country}>{country}</option>
                    ))}
                  </select>
                </label>

                <label className="space-y-2 text-sm">
                  <span className="font-semibold text-slate-900">Template</span>
                  <select name="templateId" defaultValue={activeTemplateId} disabled={templates.length === 0} className="w-full rounded-xl border border-slate-300 px-3 py-2 text-slate-900 disabled:bg-slate-100 disabled:text-slate-500">
                    {templates.length === 0 ? <option value="">No templates uploaded yet</option> : null}
                    {templates.map((template) => (
                      <option key={template.id} value={template.id}>{template.templateName}</option>
                    ))}
                  </select>
                  {templates.length === 0 ? (
                    <p className="text-xs leading-5 text-slate-500">
                      Upload a CSV template on the <Link href="/templates" className="font-semibold text-sky-700 underline">Templates page</Link> first.
                    </p>
                  ) : null}
                </label>
              </div>

              <label className="space-y-2 text-sm">
                <span className="font-semibold text-slate-900">Crawl mode</span>
                <select name="crawlMode" defaultValue={selectedCrawlMode} className="w-full rounded-xl border border-slate-300 px-3 py-2 text-slate-900">
                  <option value="trusted_sources">Trusted sources crawl</option>
                  <option value="prompt_discovery">Prompt / PDF discovery</option>
                  <option value="supplemental_discovery">Supplemental coverage crawl</option>
                </select>
                <p className="text-xs leading-5 text-slate-500">
                  Trusted sources crawl uses the country plan to collect live source data, shape it into the template schema, then judge and review it. Prompt / PDF discovery is a separate AI-first flow that generates structured candidates from your strategy prompt before judge and human review. Supplemental coverage crawl extends the live source flow with lower-trust coverage sources. Focus fields tell the crawler and extractor where accuracy matters most; other template fields are kept only when evidence exists.
                </p>
              </label>

              <fieldset className="space-y-2 text-sm">
                <legend className="font-semibold text-slate-900">Trusted-source plan</legend>
                <div className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  {recommendedSources.templates.length > 0 ? (
                    recommendedSources.templates.map((source, index) => (
                      <div key={`${source.country}-${source.name}`} className="rounded-xl bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">
                        <span className="space-y-2 block">
                          <span className="block font-semibold text-slate-900">
                            {source.name}
                            {index === 0 ? <span className="ml-2 rounded-full bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-700">Primary plan</span> : null}
                          </span>
                          <span className="flex flex-wrap gap-2 text-xs">
                            <span className="rounded-full bg-sky-100 px-2 py-0.5 font-semibold text-sky-700">{source.sourceType}</span>
                          </span>
                          <span className="block text-xs leading-5 text-slate-500">
                            {selectedCountry} / {source.supportedFields.length} supported fields
                          </span>
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-xl bg-white px-4 py-3 text-sm text-slate-600 shadow-sm">
                      No trusted-source plan is configured for {selectedCountry} yet.
                    </div>
                  )}
                </div>
                <p className="text-xs leading-5 text-slate-500">
                  In trusted mode, the system automatically applies the configured source strategy for the selected country, collects live rows, shapes them toward the selected template, and only then sends the structured candidates through judge and review.
                </p>
              </fieldset>

              {selectedCrawlMode === "trusted_sources" ? null : (
                <input type="hidden" name="sourceIds" value={activeSourceIds[0] ?? ""} />
              )}

              {selectedCrawlMode === "prompt_discovery" && sources.length > 0
                ? activeSourceIds.map((sourceId) => <input key={sourceId} type="hidden" name="sourceIds" value={sourceId} />)
                : null}

              {selectedCrawlMode === "prompt_discovery" && sources.length === 0 ? (
                <p className="text-xs leading-5 text-slate-500">
                  Prompt mode can still run without saved DB sources; seed sources are optional.
                </p>
              ) : null}

              {selectedCrawlMode === "trusted_sources" && sources.length > 0 ? (
                <div className="rounded-2xl bg-slate-50 p-4 text-xs text-slate-600">
                  Saved DB sources for {selectedCountry}: {sources.map((source) => source.name).join(", ") || "None"}.
                  These are no longer required for job creation when a country plan exists.
                </div>
              ) : null}

              <label className="space-y-2 text-sm">
                <span className="font-semibold text-slate-900">Discovery prompt</span>
                <textarea
                  name="discoveryPrompt"
                  defaultValue={discoveryPromptValue}
                  className="min-h-40 w-full rounded-xl border border-slate-300 px-3 py-2 text-slate-900"
                  placeholder="Paste the country-specific discovery strategy here"
                />
                <p className="text-xs leading-5 text-slate-500">
                  Used only for Prompt / PDF discovery mode. Paste the strategy or PDF-derived prompt here when you want AI to propose structured candidate rows instead of crawling websites directly.
                </p>
              </label>

              <fieldset className="space-y-2 text-sm">
                <legend className="font-semibold text-slate-900">Focus fields</legend>
                {activeTemplateColumns.length > 0 ? (
                  <div className="flex min-w-0 flex-wrap gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-3">
                    {activeTemplateColumns.map((field) => {
                      const isChecked = activeCriticalFields.includes(field);
                      return (
                        <label key={field} className="inline-flex max-w-full cursor-pointer items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm">
                          <input type="checkbox" name="criticalFields" value={field} defaultChecked={isChecked} className="h-3.5 w-3.5 rounded border-slate-300" />
                          <span className="min-w-0 break-all">{field}</span>
                        </label>
                      );
                    })}
                  </div>
                ) : (
                  <input
                    name="criticalFieldsText"
                    defaultValue={activeCriticalFields.join(",")}
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-slate-900"
                    placeholder="name,website,location"
                  />
                )}
                <p className="text-xs leading-5 text-slate-500">
                  Select fields from the CSV import template. The crawler, extractor, and judge prioritize these fields. Other template fields pass through only with source evidence; otherwise they remain blank/null. Current template allows {suggestions?.minFields ?? 3} to {suggestions?.maxFields ?? 30} focus fields.
                </p>
              </fieldset>

              <label className="flex items-center gap-3 text-sm text-slate-700">
                <input type="checkbox" name="aiAssist" value="true" defaultChecked={aiAssist} className="h-4 w-4 rounded border-slate-300" />
                Enable AI assistance for focus field extraction
              </label>

              <div className="rounded-2xl bg-sky-50 p-4 text-sm text-sky-900">
                <p className="font-semibold">Direct processing starts on submit</p>
                <p className="mt-2">This form calls the backend directly. Source-based modes run collect to hash to evidence-backed extraction to judge to review/export. Prompt mode runs prompt discovery to evidence-backed candidate to judge to review/export.</p>
              </div>

              {errorMessage ? <div className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-700">{errorMessage}</div> : null}

              <div className="flex flex-wrap gap-3">
                <ProcessingSubmitButton idleLabel="Create and process job" pendingLabel="Processing job..." />
                <Link href={`/create-job?country=${encodeURIComponent(selectedCountry)}&templateId=${encodeURIComponent(activeTemplateId)}`} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
                  Refresh suggestions
                </Link>
              </div>
            </form>
          </Card>

          <div className="space-y-6">
            <Card title="Suggested focus fields">
              <div className="space-y-3 text-sm text-slate-600">
                {suggestions?.suggestedFieldsDetail.map((field) => (
                  <div key={field.name} className="rounded-2xl border border-slate-200 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-semibold text-slate-900">{field.name}</p>
                      <span className="text-xs font-semibold text-sky-700">{field.score}</span>
                    </div>
                    <p className="mt-2 leading-6">{field.reason}</p>
                  </div>
                )) ?? <p>No suggestion available.</p>}
              </div>
            </Card>

            <Card title="Submission status">
              <p className="text-sm text-slate-600">Choose the right setup, then create the job to start direct backend processing.</p>
            </Card>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
