"use client";

import { useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

const tabs = [
  { key: "overview", label: "Overview" },
  { key: "review", label: "Review Queue" },
  { key: "clean", label: "Clean Data" },
  { key: "export", label: "Export" },
  { key: "import", label: "Import" },
  { key: "activity", label: "Activity" },
];

export function JobTabs() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") ?? "overview";

  const params = useMemo(() => new URLSearchParams(searchParams.toString()), [searchParams]);

  return (
    <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-4">
      {tabs.map((tab) => {
        const active = activeTab === tab.key;
        return (
          <button
            key={tab.key}
            type="button"
            onClick={() => {
              params.set("tab", tab.key);
              router.replace(`${pathname}?${params.toString()}`);
            }}
            className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
              active
                ? "bg-sky-700 text-white"
                : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
