import Link from "next/link";

import { type JobListItem } from "@/lib/types";
import { ProgressBar, StatusBadge } from "@/components/ui";

const nextActionTone: Record<JobListItem["nextAction"]["type"], string> = {
  review: "bg-amber-100 text-amber-800",
  export: "bg-emerald-100 text-emerald-800",
  progress: "bg-sky-100 text-sky-700",
  view: "bg-slate-100 text-slate-700",
};

const nextActionHrefByType: Record<JobListItem["nextAction"]["type"], string> = {
  review: "review",
  export: "export",
  progress: "overview",
  view: "overview",
};

export function JobsTable({ jobs }: { jobs: JobListItem[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-slate-500">
          <tr>
            <th className="px-4 py-3 font-semibold">Job</th>
            <th className="px-4 py-3 font-semibold">Status</th>
            <th className="px-4 py-3 font-semibold">Progress</th>
            <th className="px-4 py-3 font-semibold">Quality</th>
            <th className="px-4 py-3 font-semibold">Next action</th>
            <th className="px-4 py-3 font-semibold">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {jobs.map((job) => (
            <tr key={job.id} className="align-top">
              <td className="px-4 py-4">
                <div className="space-y-1">
                  <Link href={`/crawl-jobs/${job.id}`} className="font-semibold text-slate-950 hover:text-sky-700">
                    {job.jobName}
                  </Link>
                  <p className="text-slate-500">{job.sourceName}</p>
                  <p className="text-xs text-slate-400">Template: {job.templateName}</p>
                </div>
              </td>
              <td className="px-4 py-4">
                <StatusBadge status={job.status} />
              </td>
              <td className="px-4 py-4">
                <div className="w-40 space-y-2">
                  <p className="font-semibold text-slate-700">{job.progressPercent}% complete</p>
                  <ProgressBar value={job.progressPercent} />
                  <p className="text-xs text-slate-500">
                    {job.cleanRecords}/{job.totalRecords} records ready
                  </p>
                </div>
              </td>
              <td className="px-4 py-4">
                <p className="font-semibold text-slate-900">
                  {job.qualityScore === null ? "—" : `${job.qualityScore}%`}
                </p>
                <p className="text-xs text-slate-500">{job.needReviewCount} need review</p>
              </td>
              <td className="px-4 py-4">
                <Link
                  href={`/crawl-jobs/${job.id}?tab=${nextActionHrefByType[job.nextAction.type]}`}
                  className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold transition hover:opacity-80 ${nextActionTone[job.nextAction.type]}`}
                >
                  {job.nextAction.label}
                </Link>
              </td>
              <td className="px-4 py-4 text-slate-500">{job.updatedAt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
