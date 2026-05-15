import Link from "next/link";

import { DashboardLayout } from "@/components/dashboard-layout";
import { JobsTable } from "@/components/jobs-table";
import { Card, MetricCard, PageHeader } from "@/components/ui";
import { getJobs } from "@/lib/api";

const createJobHref = "/create-job";

export default async function DashboardPage() {
  const jobs = await getJobs();
  const totalRecords = jobs.reduce((sum, job) => sum + job.totalRecords, 0);
  const readyRecords = jobs.reduce((sum, job) => sum + job.cleanRecords, 0);
  const reviewRecords = jobs.reduce((sum, job) => sum + job.needReviewCount, 0);
  const averageQuality = jobs.length
    ? Math.round(jobs.reduce((sum, job) => sum + (job.qualityScore ?? 0), 0) / jobs.length)
    : 0;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          eyebrow="Dashboard"
          title="Crawl job health at a glance"
          description="Help non-technical operators see what is ready, what needs review, and what should happen next."
          action={
            <Link
              href={createJobHref}
              className="inline-flex items-center rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800"
            >
              Create crawl job
            </Link>
          }
        />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Jobs in progress" value={String(jobs.length)} subtext="Tracked crawl jobs" />
          <MetricCard label="Records collected" value={String(totalRecords)} subtext="Rows currently in the workflow" />
          <MetricCard label="Ready records" value={String(readyRecords)} subtext="Clean rows available for export" />
          <MetricCard label="Average quality" value={`${averageQuality}%`} subtext={`${reviewRecords} rows still need attention`} />
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <Card title="Active crawl jobs">
            <JobsTable jobs={jobs} />
          </Card>

          <Card title="Operator focus today">
            <div className="space-y-4 text-sm text-slate-600">
              <div className="rounded-2xl bg-amber-50 p-4">
                <p className="font-semibold text-slate-900">Review flagged records first</p>
                <p className="mt-2 leading-6">
                  Start with the jobs that still have missing or low-confidence values before export.
                </p>
              </div>
              <div className="rounded-2xl bg-emerald-50 p-4">
                <p className="font-semibold text-slate-900">Export-ready jobs can move forward</p>
                <p className="mt-2 leading-6">
                  Once the checklist is clear, export the clean file and upload it into BeyondDegree admin.
                </p>
              </div>
              <div className="rounded-2xl bg-sky-50 p-4">
                <p className="font-semibold text-slate-900">Need a new crawl?</p>
                <p className="mt-2 leading-6">
                  Create a new crawl job when you need to start another source-template workflow.
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  );
}
