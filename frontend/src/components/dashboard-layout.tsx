import Link from "next/link";
import { ReactNode } from "react";

const navItems = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/create-job", label: "Create Job" },
  { href: "/crawl-jobs", label: "Crawl Jobs" },
  { href: "/templates", label: "Templates" },
  { href: "/data-sources", label: "Data Sources" },
  { href: "/activity", label: "Activity Logs" },
];

export function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="grid min-h-screen lg:grid-cols-[260px_1fr]">
        <aside className="border-r border-slate-200 bg-slate-900 px-5 py-6 text-white">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-sky-300">BeyondDegree</p>
            <h1 className="mt-2 text-xl font-semibold leading-tight">
              Data Automation Dashboard
            </h1>
          </div>
          <nav className="mt-10 space-y-2">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="block rounded-xl px-4 py-3 text-sm font-medium text-slate-200 transition hover:bg-slate-800 hover:text-white"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>
        <div className="flex min-h-screen flex-col">
          <header className="border-b border-slate-200 bg-white px-6 py-4">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-sm font-medium text-slate-500">University data operations</p>
                <p className="text-lg font-semibold text-slate-900">
                  Review, clean, and export import-ready records
                </p>
              </div>
              <div className="rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-600">
                Non-technical friendly workflow for BeyondDegree imports
              </div>
            </div>
          </header>
          <main className="flex-1 px-6 py-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
