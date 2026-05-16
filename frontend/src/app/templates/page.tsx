import Link from "next/link";
import { DashboardLayout } from "@/components/dashboard-layout";
import { Card, MetricCard, PageHeader } from "@/components/ui";
import { deleteTemplate, getJobs, getTemplates, uploadTemplate } from "@/lib/api";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

async function uploadTemplateAction(formData: FormData) {
  "use server";

  const templateName = String(formData.get("templateName") ?? "").trim();
  const file = formData.get("file");
  const templateNameParam = encodeURIComponent(templateName);

  if (!templateName) {
    redirect("/templates?error=Enter%20a%20template%20name.");
  }

  if (!(file instanceof File) || file.size === 0) {
    redirect(`/templates?templateName=${templateNameParam}&error=${encodeURIComponent("Choose a CSV template file.")}`);
  }

  const result = await uploadTemplate(templateName, file);

  if (result.error) {
    redirect(`/templates?templateName=${templateNameParam}&error=${encodeURIComponent(result.error)}`);
  }

  redirect(`/templates?success=${encodeURIComponent(`Uploaded ${templateName}.`)}`);
}

async function deleteTemplateAction(formData: FormData) {
  "use server";

  const templateId = String(formData.get("templateId") ?? "").trim();
  if (!templateId) {
    redirect(`/templates?error=${encodeURIComponent("Template ID is missing.")}`);
  }

  const result = await deleteTemplate(templateId);
  if (result.error) {
    redirect(`/templates?error=${encodeURIComponent(result.error)}`);
  }

  redirect(`/templates?success=${encodeURIComponent(result.message ?? "Template deleted.")}`);
}

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

function readValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function TemplatesPage({ searchParams }: { searchParams: SearchParams }) {
  const resolvedSearchParams = await searchParams;
  const successMessage = readValue(resolvedSearchParams.success) ?? null;
  const errorMessage = readValue(resolvedSearchParams.error) ?? null;
  const templateNameValue = readValue(resolvedSearchParams.templateName) ?? "";

  const [templates, jobs] = await Promise.all([getTemplates(), getJobs()]);
  const activeTemplate = templates[0];
  const templateName = activeTemplate?.templateName ?? "No template";
  const jobsUsingActiveTemplate = activeTemplate ? jobs.filter((job) => job.templateName === activeTemplate.templateName) : [];
  const activeJobs = jobsUsingActiveTemplate.length;
  const rowsExportReady = jobsUsingActiveTemplate
    .filter((job) => job.status === "READY_TO_EXPORT" || job.status === "EXPORTED")
    .reduce((sum, job) => sum + job.cleanRecords, 0);
  const templateChecks = [
    {
      key: "catalog_loaded",
      label: "Template catalog loaded",
      status: templates.length > 0 ? "pass" : "warning",
    },
    {
      key: "active_template",
      label: "Active template selected",
      status: activeTemplate ? "pass" : "warning",
    },
    {
      key: "jobs_mapped",
      label: "Jobs mapped to active template",
      status: activeJobs > 0 ? "pass" : "warning",
    },
    {
      key: "ready_rows",
      label: "Ready rows from live jobs",
      status: rowsExportReady > 0 ? "pass" : "warning",
    },
  ];

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          eyebrow="Templates"
          title="Import template readiness"
          description="Help operators see which template is active, what fields matter, and what must be complete before BeyondDegree import."
        />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Active template" value={templateName} subtext={activeTemplate?.fileName ?? "Current export schema"} />
          <MetricCard label="Template count" value={String(templates.length)} subtext="Schemas available for new jobs" />
          <MetricCard label="Rows export-ready" value={String(rowsExportReady)} subtext="From live jobs using the active template" />
          <MetricCard label="Jobs using template" value={String(activeJobs)} subtext="Crawl jobs mapped to this schema" />
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <Card title="Upload template CSV">
            <form action={uploadTemplateAction} className="space-y-4">
              <label className="block space-y-2 text-sm">
                <span className="font-semibold text-slate-900">Template name</span>
                <input
                  name="templateName"
                  required
                  defaultValue={templateNameValue}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-slate-900"
                  placeholder="University_Import_Clean-8"
                />
              </label>

              <label className="block space-y-2 text-sm">
                <span className="font-semibold text-slate-900">CSV file</span>
                <input
                  name="file"
                  type="file"
                  required
                  accept=".csv,text/csv"
                  className="block w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 file:mr-4 file:rounded-lg file:border-0 file:bg-sky-50 file:px-3 file:py-2 file:font-semibold file:text-sky-700 hover:file:bg-sky-100"
                />
                <p className="text-xs leading-5 text-slate-500">Upload a clean-template CSV header, not crawled source data.</p>
                <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                  <Link href="/sample-template.csv" className="inline-flex items-center rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
                    Download sample CSV
                  </Link>
                  <span>Starter columns: name, website, location, admissions_page_link, slug.</span>
                </div>
              </label>

              {errorMessage ? <div className="rounded-2xl bg-rose-50 p-4 text-sm text-rose-700">{errorMessage}</div> : null}
              {successMessage ? <div className="rounded-2xl bg-emerald-50 p-4 text-sm text-emerald-900">{successMessage}</div> : null}

              <button type="submit" className="rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800">
                Upload template
              </button>
            </form>
          </Card>

          <Card title="Template checklist">
            <div className="space-y-3">
              {templateChecks.map((item) => (
                <div key={item.key} className="flex items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-sm">
                  <span className="text-slate-700">{item.label}</span>
                  <span className="font-semibold text-slate-900">{item.status}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Template catalog">
            <div className="space-y-3 text-sm text-slate-600">
              {templates.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-4 text-sm text-slate-600">
                  No templates uploaded yet. Upload a CSV above, then return to create-job to select it.
                </div>
              ) : null}
              {templates.map((template) => (
                <div key={template.id} className="rounded-2xl border border-slate-200 px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-slate-900">{template.templateName}</p>
                      <p className="mt-1">{template.fileName}</p>
                      <p className="mt-1 text-xs text-slate-500">{template.columnCount} columns</p>
                    </div>
                    <form action={deleteTemplateAction}>
                      <input type="hidden" name="templateId" value={template.id} />
                      <button type="submit" className="rounded-xl border border-rose-300 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-50">
                        Delete
                      </button>
                    </form>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  );
}
