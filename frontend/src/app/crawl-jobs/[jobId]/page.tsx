import { notFound } from "next/navigation";

import { DashboardLayout } from "@/components/dashboard-layout";
import { JobDetailContent } from "@/components/job-detail-content";
import { getActivityItems, getCleanData, getExportReadiness, getJobHeader, getJobOverview, getReviewQueue } from "@/lib/api";

export default async function CrawlJobDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ jobId: string }>;
  searchParams: Promise<{ tab?: string; record?: string }>;
}) {
  const [{ jobId }, resolvedSearchParams] = await Promise.all([params, searchParams]);
  const activeTab = resolvedSearchParams.tab ?? "overview";
  const selectedRecordId = resolvedSearchParams.record;
  const [jobHeader, reviewQueue, overviewData, cleanData, activityItems, exportReadiness] = await Promise.all([
    getJobHeader(jobId),
    getReviewQueue(jobId, selectedRecordId),
    getJobOverview(jobId),
    getCleanData(jobId),
    getActivityItems(jobId),
    getExportReadiness(jobId),
  ]);

  if (!jobHeader) {
    notFound();
  }

  return (
    <DashboardLayout>
      <JobDetailContent
        activeTab={activeTab}
        jobHeader={jobHeader}
        reviewQueue={reviewQueue}
        overviewData={overviewData}
        cleanData={cleanData}
        activityItems={activityItems}
        exportReadiness={exportReadiness}
      />
    </DashboardLayout>
  );
}
