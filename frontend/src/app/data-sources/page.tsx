import { DashboardLayout } from "@/components/dashboard-layout";
import { Card, MetricCard, PageHeader } from "@/components/ui";
import { getCountries, getJobs, getRecommendedSources, getSources, sourceRoleLabel, sourceTone, updateSourceConfig } from "@/lib/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function readValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function parseFieldMap(value: string): { parsed: Record<string, string | string[]> | null; error: string | null } {
  if (!value.trim()) {
    return { parsed: null, error: null };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return {
      parsed: null,
      error: "field_map must be valid JSON.",
    };
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return {
      parsed: null,
      error: "field_map must be a JSON object.",
    };
  }

  for (const [key, entry] of Object.entries(parsed)) {
    if (!key.trim()) {
      return {
        parsed: null,
        error: "field_map keys must be non-empty strings.",
      };
    }

    if (typeof entry === "string" && entry.trim()) {
      continue;
    }

    if (Array.isArray(entry) && entry.length > 0 && entry.every((item) => typeof item === "string" && item.trim().length > 0)) {
      continue;
    }

    return {
      parsed: null,
      error: "Each field_map value must be a non-empty string or a non-empty array of non-empty strings.",
    };
  }

  return {
    parsed: parsed as Record<string, string | string[]>,
    error: null,
  };
}

function formatFieldMap(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value) ? JSON.stringify(value, null, 2) : "";
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function sourceValue(sourceId: string, editedSourceId: string, editedValue: string, fallbackValue: string) {
  return sourceId === editedSourceId ? editedValue : fallbackValue;
}

function sourceMessage(sourceId: string, targetSourceId: string | null, message: string | null) {
  return sourceId === targetSourceId ? message : null;
}

function fieldMapHelpText() {
  return 'Map source fields into our system fields. Example: {"name":"school_name"} or {"website":["website","homepage"]}';
}

function fieldMapInputClass(error: string | null) {
  return `min-h-32 w-full rounded-xl border px-3 py-2 font-mono text-sm text-slate-900 ${error ? "border-rose-300 bg-rose-50" : "border-slate-300"}`;
}

function selectInputClass() {
  return "w-full rounded-xl border border-slate-300 px-3 py-2 text-slate-900";
}

function textInputClass() {
  return "w-full rounded-xl border border-slate-300 px-3 py-2 text-slate-900";
}

export default async function DataSourcesPage({ searchParams }: { searchParams: SearchParams }) {
  const resolvedSearchParams = await searchParams;
  const submitted = readValue(resolvedSearchParams.submitted) === "1";
  const editedSourceId = readValue(resolvedSearchParams.sourceId) ?? "";
  const editedRole = readValue(resolvedSearchParams.sourceRole) ?? "";
  const editedTrustLevel = readValue(resolvedSearchParams.trustLevel) ?? "";
  const editedSourceType = readValue(resolvedSearchParams.sourceType) ?? "";
  const editedUrlTemplate = readValue(resolvedSearchParams.urlTemplate) ?? "";
  const editedItemsPath = readValue(resolvedSearchParams.itemsPath) ?? "";
  const editedFieldMap = readValue(resolvedSearchParams.fieldMap) ?? "";

  let updateMessage: string | null = null;
  let updateError: string | null = null;
  let updateSourceId: string | null = null;

  if (submitted && editedSourceId) {
    updateSourceId = editedSourceId;
    const parsedFieldMap = parseFieldMap(editedFieldMap);

    if (parsedFieldMap.error) {
      updateError = parsedFieldMap.error;
    } else {
      const result = await updateSourceConfig({
        sourceId: editedSourceId,
        sourceRole: editedRole || null,
        trustLevel: editedTrustLevel || null,
        sourceType: editedSourceType || null,
        urlTemplate: editedUrlTemplate || null,
        itemsPath: editedItemsPath || null,
        fieldMap: parsedFieldMap.parsed,
      });
      if (result) {
        updateMessage = "Source configuration saved.";
      } else {
        updateError = "Source configuration could not be saved right now.";
      }
    }
  }

  const countries = await getCountries();
  const [jobs, sourceGroups, recommendedGroups] = await Promise.all([
    getJobs(),
    Promise.all(countries.map((country) => getSources(country))),
    Promise.all(countries.map((country) => getRecommendedSources(country))),
  ]);
  const sources = sourceGroups.flat();
  const recommendedSources = recommendedGroups.flatMap((group) => group.templates.map((template) => ({ ...template, requestedCountry: group.country })));
  const sourceCountByName = new Map(jobs.map((job) => [job.sourceName, job]));

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          eyebrow="Data sources"
          title="Source coverage and status"
          description="Show operators which source feeds are active, which country they belong to, what each source is used for, and whether its latest crawl job still needs attention."
        />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Active sources" value={String(sources.length)} subtext="Distinct source feeds" />
          <MetricCard label="Countries covered" value={String(countries.length)} subtext="Markets currently configured" />
          <MetricCard label="Jobs attached" value={String(jobs.length)} subtext="Current crawl pipelines" />
          <MetricCard label="Recommended templates" value={String(recommendedSources.length)} subtext="Trusted-source presets by country" />
          <MetricCard label="Need review" value={String(jobs.reduce((sum, job) => sum + job.needReviewCount, 0))} subtext="Flagged records across sources" />
        </div>

        <Card title="Source list">
          <div className="space-y-3">
            {sources.map((source) => {
              const linkedJob = sourceCountByName.get(source.name);
              const config = source.config ?? {};
              const sourceUpdateMessage = sourceMessage(source.id, updateSourceId, updateMessage);
              const sourceUpdateError = sourceMessage(source.id, updateSourceId, updateError);
              const fieldMapValue = sourceValue(source.id, editedSourceId, editedFieldMap, formatFieldMap(config.field_map));
              const sourceTypeValue = sourceValue(source.id, editedSourceId, editedSourceType, stringValue(config.source_type));
              const urlTemplateValue = sourceValue(source.id, editedSourceId, editedUrlTemplate, stringValue(config.url_template));
              const itemsPathValue = sourceValue(source.id, editedSourceId, editedItemsPath, stringValue(config.items_path));
              const roleValue = sourceValue(source.id, editedSourceId, editedRole, source.sourceRole ?? "");
              const trustValue = sourceValue(source.id, editedSourceId, editedTrustLevel, source.trustLevel ?? "");
              return (
                <form key={source.id} className="rounded-2xl border border-slate-200 px-4 py-4" action="/data-sources" method="get">
                  <input type="hidden" name="submitted" value="1" />
                  <input type="hidden" name="sourceId" value={source.id} />
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold text-slate-900">{source.name}</p>
                        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${sourceTone(source)}`}>{sourceRoleLabel(source)}</span>
                        {source.trustLevel ? <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">Trust {source.trustLevel}</span> : null}
                      </div>
                      <p className="mt-1 text-sm text-slate-600">{source.country ?? "Configured source"}</p>
                    </div>
                    <div className="text-sm text-slate-500">
                      {linkedJob ? `${linkedJob.totalRecords} records in latest job` : "No linked job yet"}
                    </div>
                  </div>
                  <p className="mt-3 text-xs text-slate-500">Supported fields: {source.supportedFields.join(", ") || "None listed"}</p>

                  <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                    <label className="space-y-2 text-sm">
                      <span className="font-semibold text-slate-900">Role</span>
                      <select name="sourceRole" defaultValue={roleValue} className={selectInputClass()}>
                        <option value="">Unset</option>
                        <option value="official">Official</option>
                        <option value="reference">Reference</option>
                        <option value="community">Community</option>
                      </select>
                    </label>
                    <label className="space-y-2 text-sm">
                      <span className="font-semibold text-slate-900">Trust level</span>
                      <select name="trustLevel" defaultValue={trustValue} className={selectInputClass()}>
                        <option value="">Unset</option>
                        <option value="high">High</option>
                        <option value="medium">Medium</option>
                        <option value="low">Low</option>
                      </select>
                    </label>
                    <label className="space-y-2 text-sm">
                      <span className="font-semibold text-slate-900">Fetch method</span>
                      <input name="sourceType" defaultValue={sourceTypeValue} className={textInputClass()} placeholder="json_api" />
                      <span className="text-xs text-slate-500">How the system reads this source, for example API, wiki list, or catalog page.</span>
                    </label>
                    <label className="space-y-2 text-sm">
                      <span className="font-semibold text-slate-900">Source URL template</span>
                      <input name="urlTemplate" defaultValue={urlTemplateValue} className={textInputClass()} placeholder="https://example.com/api?country={country_query}" />
                      <span className="text-xs text-slate-500">The real source address. {"{country_query}"} is replaced with the selected country.</span>
                    </label>
                    <label className="space-y-2 text-sm md:col-span-2 xl:col-span-2">
                      <span className="font-semibold text-slate-900">Records path</span>
                      <input name="itemsPath" defaultValue={itemsPathValue} className={textInputClass()} placeholder="payload.rows" />
                      <span className="text-xs text-slate-500">If the source returns nested JSON, this tells the system where the row list lives.</span>
                    </label>
                  </div>

                  <label className="mt-4 block space-y-2 text-sm">
                    <span className="font-semibold text-slate-900">Field mapping</span>
                    <textarea name="fieldMap" defaultValue={fieldMapValue} className={fieldMapInputClass(sourceUpdateError)} placeholder='{"name":"school_name","website":"website_url"}' />
                    <span className="text-xs text-slate-500">{fieldMapHelpText()}</span>
                    {sourceUpdateError ? <span className="text-xs font-medium text-rose-700">{sourceUpdateError}</span> : null}
                    {sourceUpdateMessage ? <span className="text-xs font-medium text-emerald-700">{sourceUpdateMessage}</span> : null}
                  </label>

                  <div className="mt-4 rounded-2xl bg-slate-50 p-4 text-xs leading-6 text-slate-600">
                    <p>
                      This source uses <span className="font-semibold text-slate-900">{sourceTypeValue || "an unset fetch method"}</span>
                      {urlTemplateValue ? <span> and reads from <span className="font-semibold text-slate-900">{urlTemplateValue}</span></span> : null}.
                    </p>
                    <p className="mt-2">
                      The field mapping tells the pipeline how to turn the source response into our university schema.
                    </p>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-3">
                    <button type="submit" className="rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800">
                      Save source config
                    </button>
                  </div>
                </form>
              );
            })}
          </div>
        </Card>

        <Card title="Recommended trusted-source templates">
          <p className="mb-4 text-sm text-slate-600">
            These are suggested source strategies by country. They are presets for operators, not live crawl results.
          </p>
          <div className="space-y-4">
            {recommendedGroups.map((group) => (
              <div key={group.country} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-semibold text-slate-900">{group.country}</p>
                  <span className="text-sm text-slate-500">{group.templates.length} templates</span>
                </div>
                <div className="mt-4 grid gap-3 xl:grid-cols-2">
                  {group.templates.map((template) => (
                    <div key={`${group.country}-${template.name}`} className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold text-slate-900">{template.name}</p>
                        <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-700">{template.sourceType}</span>
                      </div>
                      <p className="mt-2">Supported fields: {template.supportedFields.join(", ") || "None listed"}</p>
                      <p className="mt-2 break-all text-xs text-slate-500">
                        {typeof template.config.url_template === "string"
                          ? template.config.url_template
                          : typeof template.config.url === "string"
                            ? template.config.url
                            : "No URL configured"}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </DashboardLayout>
  );
}
