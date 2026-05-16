import Link from "next/link";
import { type ReactNode } from "react";

import { type JobStatus, type StepStatus } from "@/lib/types";

const statusTone: Record<JobStatus, string> = {
  QUEUED: "bg-slate-100 text-slate-700",
  CRAWLING: "bg-sky-100 text-sky-700",
  EXTRACTING: "bg-indigo-100 text-indigo-700",
  NEEDS_REVIEW: "bg-amber-100 text-amber-800",
  CLEANING: "bg-violet-100 text-violet-700",
  READY_TO_EXPORT: "bg-emerald-100 text-emerald-800",
  EXPORTED: "bg-green-100 text-green-800",
  FAILED: "bg-rose-100 text-rose-700",
};

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex min-w-0 flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        <p className="text-sm font-semibold uppercase tracking-[0.24em] text-sky-700">{eyebrow}</p>
        <h2 className="mt-2 break-words text-3xl font-semibold text-slate-950">{title}</h2>
        <p className="mt-2 max-w-3xl break-words text-sm leading-6 text-slate-600">{description}</p>
      </div>
      {action ? <div className="min-w-0 max-w-full shrink-0">{action}</div> : null}
    </div>
  );
}

export function MetricCard({
  label,
  value,
  subtext,
}: {
  label: string;
  value: string;
  subtext?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-3 text-3xl font-semibold text-slate-950">{value}</p>
      {subtext ? <p className="mt-2 text-sm text-slate-600">{subtext}</p> : null}
    </div>
  );
}

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${statusTone[status]}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function Card({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex min-w-0 items-start justify-between gap-4">
        <h3 className="min-w-0 break-words text-lg font-semibold text-slate-950">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-2 w-full rounded-full bg-slate-200">
      <div className="h-2 rounded-full bg-sky-600" style={{ width: `${value}%` }} />
    </div>
  );
}

export function Stepper({
  steps,
}: {
  steps: { key: string; label: string; status: StepStatus }[];
}) {
  const toneByStatus: Record<StepStatus, string> = {
    completed: "bg-emerald-600 text-white border-emerald-600",
    current: "bg-sky-600 text-white border-sky-600",
    pending: "bg-white text-slate-500 border-slate-300",
    blocked: "bg-rose-100 text-rose-700 border-rose-200",
  };

  return (
    <div className="flex min-w-0 flex-wrap gap-3">
      {steps.map((step, index) => (
        <div key={step.key} className="flex min-w-0 items-center gap-3">
          <div className={`flex h-9 items-center rounded-full border px-4 text-sm font-semibold ${toneByStatus[step.status]}`}>
            {index + 1}. {step.label}
          </div>
          {index < steps.length - 1 ? <div className="hidden h-px w-6 bg-slate-300 md:block" /> : null}
        </div>
      ))}
    </div>
  );
}

export function LinkButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center rounded-xl bg-sky-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-800"
    >
      {children}
    </Link>
  );
}

export function DonutStat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-center">
      <div
        className="mx-auto flex h-24 w-24 items-center justify-center rounded-full border-[10px] border-sky-200 text-2xl font-semibold text-sky-900"
        style={{ borderTopColor: "#0369a1", borderRightColor: "#7dd3fc" }}
      >
        {value}%
      </div>
      <p className="mt-3 text-sm font-semibold text-slate-900">{label}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function PriorityBadge({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-700" title={label ?? "Priority field"}>
      <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.286 3.957a1 1 0 00.95.69h4.163c.969 0 1.371 1.24.588 1.81l-3.37 2.448a1 1 0 00-.364 1.118l1.287 3.957c.3.921-.755 1.688-1.54 1.118l-3.37-2.448a1 1 0 00-1.176 0l-3.37 2.448c-.784.57-1.838-.197-1.539-1.118l1.287-3.957a1 1 0 00-.364-1.118L2.062 9.384c-.783-.57-.38-1.81.588-1.81h4.163a1 1 0 00.95-.69l1.286-3.957z" />
      </svg>
      {label ?? "Priority"}
    </span>
  );
}

export function PriorityColumnHeader({ children, isPriority }: { children: ReactNode; isPriority: boolean }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      {children}
      {isPriority ? <PriorityBadge /> : null}
    </span>
  );
}
