import { notFound } from "next/navigation";

import { DashboardLayout } from "@/components/dashboard-layout";
import { JobDetailContent } from "@/components/job-detail-content";
import { getActivityItems, getCleanData, getExportReadiness, getJobHeader, getJobOverview, getReviewQueue } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function CrawlJobDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ jobId: string }>;
  searchParams: Promise<{ tab?: string; record?: string; reviewPage?: string; recordPage?: string; rawRecord?: string }>;
}) {
  const [{ jobId }, resolvedSearchParams] = await Promise.all([params, searchParams]);
  const requestedTab = resolvedSearchParams.tab ?? "overview";
  const activeTab = ["overview", "review", "clean", "export", "import", "activity"].includes(requestedTab) ? requestedTab : "overview";
  const selectedRecordId = resolvedSearchParams.record;
  const selectedRawRecordId = resolvedSearchParams.rawRecord;
  const reviewPage = Math.max(1, Number.parseInt(resolvedSearchParams.reviewPage ?? "1", 10) || 1);
  const crawledRecordPage = Math.max(1, Number.parseInt(resolvedSearchParams.recordPage ?? "1", 10) || 1);
  const jobHeader = await getJobHeader(jobId);

  if (!jobHeader) {
    notFound();
  }

  const [reviewQueue, overviewData, cleanData, activityItems, exportReadiness] = await Promise.all([
    activeTab === "review" ? getReviewQueue(jobId, selectedRecordId, reviewPage) : Promise.resolve(null),
    activeTab === "overview" ? getJobOverview(jobId, { selectedRawRecordId, crawledRecordPage }) : Promise.resolve(null),
    activeTab === "clean" ? getCleanData(jobId) : Promise.resolve(null),
    activeTab === "activity" ? getActivityItems(jobId) : Promise.resolve([]),
    activeTab === "export" || activeTab === "import" ? getExportReadiness(jobId) : Promise.resolve(null),
  ]);

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
