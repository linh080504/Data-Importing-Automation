import { DashboardLayout } from "@/components/dashboard-layout";
import { Card, MetricCard, PageHeader } from "@/components/ui";
import { getActivityItems, getJobs } from "@/lib/api";
import { activityItems as fallbackActivityItems } from "@/lib/mock-data";

export default async function ActivityPage() {
  const jobs = await getJobs();
  const firstJobId = jobs[0]?.id;
  const items = firstJobId ? await getActivityItems(firstJobId) : fallbackActivityItems;
  const successCount = items.filter((item) => item.type === "success").length;
  const warningCount = items.filter((item) => item.type === "warning").length;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <PageHeader
          eyebrow="Activity"
          title="Recent workflow activity"
          description="Give operators a simple log of what just happened across crawling, review, and export so they can decide the next action quickly."
        />

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Events" value={String(items.length)} subtext="Recent system activity" />
          <MetricCard label="Successful steps" value={String(successCount)} subtext="Completed without operator action" />
          <MetricCard label="Warnings" value={String(warningCount)} subtext="Need follow-up attention" />
          <MetricCard label="Latest event" value={items[0]?.time ?? "—"} subtext={items[0]?.title ?? "No activity yet"} />
        </div>

        <Card title="Activity log">
          <div className="space-y-4">
            {items.map((item) => (
              <div key={item.id} className="flex items-start justify-between gap-4 rounded-2xl border border-slate-200 px-4 py-4">
                <div>
                  <p className="font-semibold text-slate-900">{item.title}</p>
                  <p className="mt-1 text-sm text-slate-600">{item.detail}</p>
                </div>
                <div className="text-right text-sm text-slate-500">
                  <p>{item.time}</p>
                  <p className="mt-1 uppercase tracking-wide">{item.type}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </DashboardLayout>
  );
}
