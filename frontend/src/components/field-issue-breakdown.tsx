"use client";

import { useCallback, useState } from "react";

import { type FieldIssueGroup } from "@/lib/types";

const issueLabelMap: Record<string, string> = {
  missing: "Thiếu dữ liệu",
  empty: "Giá trị rỗng",
  conflict: "Xung đột nguồn",
};

const issueToneMap: Record<string, string> = {
  missing: "bg-rose-50 text-rose-700",
  empty: "bg-amber-50 text-amber-800",
  conflict: "bg-sky-50 text-sky-700",
};

export function FieldIssueBreakdown({ fieldIssues }: { fieldIssues: FieldIssueGroup[] }) {
  const [expandedField, setExpandedField] = useState<string | null>(null);

  const toggle = useCallback((field: string) => {
    setExpandedField((prev) => (prev === field ? null : field));
  }, []);

  if (fieldIssues.length === 0) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
        Không có field nào bị lỗi. Tất cả dữ liệu đều đầy đủ.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {fieldIssues.map((group) => {
        const isOpen = expandedField === group.field;
        return (
          <div key={group.field} className="rounded-xl border border-slate-200 bg-white">
            <button
              type="button"
              onClick={() => toggle(group.field)}
              className="flex w-full items-center justify-between px-4 py-3 text-sm transition hover:bg-slate-50"
            >
              <span className="font-semibold text-slate-900">{group.field}</span>
              <span className="flex items-center gap-2">
                <span className="rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-semibold text-rose-700">
                  {group.issueCount} records
                </span>
                <svg
                  className={`h-4 w-4 text-slate-400 transition ${isOpen ? "rotate-180" : ""}`}
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                </svg>
              </span>
            </button>

            {isOpen ? (
              <div className="border-t border-slate-100 px-4 py-3">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="pb-2 text-left font-medium text-slate-500">Record</th>
                      <th className="pb-2 text-left font-medium text-slate-500">Vấn đề</th>
                      <th className="pb-2 text-left font-medium text-slate-500">Giá trị hiện tại</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.records.map((record) => (
                      <tr key={record.uniqueKey} className="border-b border-slate-50 last:border-0">
                        <td className="py-2 pr-3 font-medium text-slate-800">{record.displayName}</td>
                        <td className="py-2 pr-3">
                          <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${issueToneMap[record.issue] ?? "bg-slate-100 text-slate-700"}`}>
                            {issueLabelMap[record.issue] ?? record.issue}
                          </span>
                        </td>
                        <td className="py-2 text-slate-600">{record.currentValue === null ? "—" : String(record.currentValue)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {group.issueCount > group.records.length ? (
                  <p className="mt-2 text-xs text-slate-500">
                    Hiển thị {group.records.length}/{group.issueCount} records. Xem thêm trong tab Clean Data.
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
