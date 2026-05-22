import Link from "next/link";
import { type ReactNode } from "react";

import { type JobStatus, type StepStatus } from "@/lib/types";

const statusTone: Record<JobStatus, string> = {
  QUEUED: "bg-slate-100 text-slate-700 border border-slate-200",
  CRAWLING: "bg-sky-50 text-sky-700 border border-sky-200",
  EXTRACTING: "bg-indigo-50 text-indigo-700 border border-indigo-200",
  NEEDS_REVIEW: "bg-amber-50 text-amber-700 border border-amber-200 animate-pulse",
  CLEANING: "bg-violet-50 text-violet-700 border border-violet-200",
  READY_TO_EXPORT: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  EXPORTED: "bg-green-50 text-green-700 border border-green-200",
  FAILED: "bg-rose-50 text-rose-700 border border-rose-200",
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
    <div className="mb-6 flex min-w-0 flex-col gap-4 lg:flex-row lg:items-end lg:justify-between border-b border-slate-200 pb-6">
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-sky-600">{eyebrow}</p>
        <h2 className="mt-2 break-words text-3xl font-extrabold tracking-tight text-slate-900">{title}</h2>
        <p className="mt-2 max-w-3xl break-words text-sm leading-6 text-slate-500">{description}</p>
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
    <div className="group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-sky-300 hover:shadow-md">
      <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-sky-500/5 blur-xl group-hover:bg-sky-500/10 transition-all duration-300" />
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 group-hover:text-slate-600 transition-colors">{label}</p>
      <p className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900">
        {value}
      </p>
      {subtext ? <p className="mt-2 text-xs leading-relaxed text-slate-500 group-hover:text-slate-600 transition-colors">{subtext}</p> : null}
    </div>
  );
}

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${statusTone[status]}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function Card({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition-all duration-300 hover:border-slate-300/80">
      <div className="mb-5 flex min-w-0 items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <h3 className="min-w-0 break-words text-lg font-bold tracking-tight text-slate-900">{title}</h3>
        {aside ? <div className="shrink-0">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-2 w-full rounded-full bg-slate-100 border border-slate-200">
      <div className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-600 transition-all duration-500" style={{ width: `${value}%` }} />
    </div>
  );
}

export function Stepper({
  steps,
}: {
  steps: { key: string; label: string; status: StepStatus }[];
}) {
  const toneByStatus: Record<StepStatus, string> = {
    completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    current: "bg-sky-50 text-sky-700 border-sky-200 shadow-sm animate-pulse",
    pending: "bg-slate-50 text-slate-400 border-slate-200",
    blocked: "bg-rose-50 text-rose-700 border-rose-200",
  };

  return (
    <div className="flex min-w-0 flex-wrap gap-3">
      {steps.map((step, index) => (
        <div key={step.key} className="flex min-w-0 items-center gap-3">
          <div className={`flex h-9 items-center rounded-xl border px-4 text-xs font-bold uppercase tracking-wider transition-all duration-300 ${toneByStatus[step.status]}`}>
            <span className="mr-1.5 opacity-60">{index + 1}.</span> {step.label}
          </div>
          {index < steps.length - 1 ? <div className="hidden h-px w-6 bg-slate-200 md:block" /> : null}
        </div>
      ))}
    </div>
  );
}

export function LinkButton({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center justify-center rounded-xl bg-sky-600 px-5 py-2.5 text-sm font-bold text-white shadow-sm transition-all duration-300 hover:bg-sky-700 hover:shadow active:translate-y-0"
    >
      {children}
    </Link>
  );
}

export function DonutStat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 text-center shadow-sm">
      <div
        className="mx-auto flex h-24 w-24 items-center justify-center rounded-full border-[10px] border-slate-100 text-2xl font-extrabold text-slate-800 relative"
        style={{ 
          borderTopColor: "#0284c7", 
          borderRightColor: "#4f46e5",
          borderBottomColor: "#e2e8f0",
          borderLeftColor: "#e2e8f0",
        }}
      >
        {value}%
      </div>
      <p className="mt-4 text-sm font-bold text-slate-800">{label}</p>
      {hint ? <p className="mt-1 text-xs leading-relaxed text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function PriorityBadge({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-700 border border-amber-200/50" title={label ?? "Priority field"}>
      <svg className="h-2.5 w-2.5 text-amber-600" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
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
