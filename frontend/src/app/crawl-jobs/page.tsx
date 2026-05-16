import Link from "next/link";

import { DashboardLayout } from "@/components/dashboard-layout";
import { JobsTable } from "@/components/jobs-table";
import { Card, PageHeader } from "@/components/ui";
import { getJobs } from "@/lib/api";

export const dynamic = "force-dynamic";

const createJobHref = "/create-job";

export default async function CrawlJobsPage() {
  const jobs = await getJobs();

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          eyebrow="Crawl jobs"
          title="Track and manage crawl jobs"
          description="Open a job to review the data, understand quality, clean issues, and export the final file."
          action={
            <Link
              href={createJobHref}
              className="inline-flex items-center rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-800"
            >
              Create crawl job
            </Link>
          }
        />

        <Card title="All crawl jobs">
          <JobsTable jobs={jobs} />
        </Card>
      </div>
    </DashboardLayout>
  );
}
