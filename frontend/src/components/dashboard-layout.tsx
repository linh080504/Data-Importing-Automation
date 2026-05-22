"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

const navItems = [
  { 
    href: "/dashboard", 
    label: "Dashboard",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4zM14 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2v-4z" />
      </svg>
    )
  },
  { 
    href: "/create-job", 
    label: "Create Job",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    )
  },
  { 
    href: "/crawl-jobs", 
    label: "Crawl Jobs",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3 3L22 4" />
      </svg>
    )
  },
  { 
    href: "/templates", 
    label: "Templates",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H3a2 2 0 01-2-2V5a2 2 0 012-2h14a2 2 0 012 2v14a2 2 0 01-2 2z" />
      </svg>
    )
  },
  { 
    href: "/data-sources", 
    label: "Data Sources",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
      </svg>
    )
  },
  { 
    href: "/activity", 
    label: "Activity Logs",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    )
  },
];

export function DashboardLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen w-full overflow-x-hidden bg-slate-50 text-slate-900">
      <div className="grid min-h-screen w-full min-w-0 lg:grid-cols-[260px_minmax(0,1fr)]">
        {/* SIDEBAR */}
        <aside className="border-r border-slate-200 bg-white px-5 py-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2.5 px-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-indigo-600 text-white font-extrabold text-sm shadow-sm">
                BD
              </span>
              <div>
                <p className="text-[10px] font-extrabold uppercase tracking-[0.24em] text-sky-600">BeyondDegree</p>
                <h1 className="text-sm font-extrabold tracking-tight text-slate-900 leading-none mt-0.5">
                  Operations Suite
                </h1>
              </div>
            </div>
            
            <nav className="mt-10 space-y-1.5">
              {navItems.map((item) => {
                const isActive = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-3 rounded-xl px-4 py-3 text-xs font-bold uppercase tracking-wider transition-all duration-200 ${
                      isActive
                        ? "bg-sky-50 text-sky-700 border border-sky-200/60 shadow-sm"
                        : "text-slate-500 border border-transparent hover:bg-slate-50 hover:text-slate-900"
                    }`}
                  >
                    <span className={`transition-transform duration-200 ${isActive ? "text-sky-700 scale-110" : "text-slate-400"}`}>
                      {item.icon}
                    </span>
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>
          
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-[11px] text-slate-500 leading-relaxed">
            <span className="font-bold text-slate-800 block mb-1">⚡ Automation Core</span>
            Non-technical friendly workflow engineered for automated university data importing.
          </div>
        </aside>

        {/* WORKSPACE AREA */}
        <div className="flex min-h-screen min-w-0 flex-col bg-slate-50/30">
          <header className="border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur-md sticky top-0 z-30">
            <div className="flex min-w-0 flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <p className="text-[10px] font-extrabold uppercase tracking-widest text-sky-600">University data operations</p>
                <p className="text-base font-extrabold text-slate-900 tracking-tight mt-0.5">
                  Review, clean, and export import-ready records
                </p>
              </div>
              <div className="max-w-full rounded-full border border-slate-200 bg-slate-100 px-4 py-1.5 text-xs font-bold text-slate-600 backdrop-blur-sm shadow-inner uppercase tracking-wider">
                Non-Technical Workflow
              </div>
            </div>
          </header>
          <main className="min-w-0 flex-1 overflow-x-hidden px-4 py-6 sm:px-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
