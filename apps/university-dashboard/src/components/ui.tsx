import clsx from "clsx";
import type { ReactNode } from "react";

export function Panel({
  title,
  meta,
  actions,
  children,
  className,
}: {
  title: string;
  meta?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={clsx("rounded-lg border border-stone-200 bg-white shadow-sm", className)}>
      <header className="flex min-h-12 items-center justify-between gap-3 border-b border-stone-200 px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-stone-900">{title}</h2>
          {meta ? <p className="mt-0.5 truncate text-xs text-stone-500">{meta}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Button({
  children,
  variant = "default",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "danger" }) {
  return (
    <button
      className={clsx(
        "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border px-3 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "border-emerald-700 bg-emerald-700 text-white hover:bg-emerald-800",
        variant === "danger" && "border-red-300 bg-white text-red-700 hover:border-red-500",
        variant === "default" && "border-stone-300 bg-white text-stone-800 hover:border-stone-500",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5">
      <span className="text-xs font-semibold text-stone-500">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "min-h-9 w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 outline-none focus:border-teal-700 focus:ring-2 focus:ring-teal-100";
