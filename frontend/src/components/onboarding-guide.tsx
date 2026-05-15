"use client";

import { useCallback, useState } from "react";

const STORAGE_KEY = "beyonddegree_onboarding_dismissed";

const steps = [
  { number: 1, tab: "Overview", description: "Xem tổng quan dữ liệu, kiểm tra sources và chất lượng crawl." },
  { number: 2, tab: "Review Queue", description: "Duyệt các record cần review, quyết định chấp nhận hoặc chỉnh sửa." },
  { number: 3, tab: "Clean Data", description: "Kiểm tra dữ liệu đã clean, xem field nào còn thiếu." },
  { number: 4, tab: "Export", description: "Xuất file CSV/XLSX hoặc import trực tiếp vào BeyondDegree." },
];

function getInitialState(): boolean {
  if (typeof window === "undefined") return true;
  return localStorage.getItem(STORAGE_KEY) !== "true";
}

export function OnboardingGuide() {
  const [isVisible, setIsVisible] = useState(getInitialState);

  const dismiss = useCallback(() => {
    setIsVisible(false);
    localStorage.setItem(STORAGE_KEY, "true");
  }, []);

  const reopen = useCallback(() => {
    setIsVisible(true);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  if (!isVisible) {
    return (
      <button
        type="button"
        onClick={reopen}
        className="inline-flex items-center gap-1.5 rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700 transition hover:bg-sky-100"
        title="Mở lại hướng dẫn sử dụng"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM8.94 6.94a.75.75 0 11-1.06-1.06 3 3 0 114.24 4.24.75.75 0 01-.16.67l-.012.011-.01.01A4.5 4.5 0 019.5 13.5a.75.75 0 01-1.5 0 4.5 4.5 0 011.617-3.447c.164-.159.19-.225.19-.303a1.5 1.5 0 00-1.867-1.31zM10 15a1 1 0 100 2 1 1 0 000-2z" clipRule="evenodd" />
        </svg>
        Hướng dẫn
      </button>
    );
  }

  return (
    <div className="rounded-2xl border border-sky-200 bg-sky-50 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-sky-900">📋 Quy chuẩn sử dụng dashboard (Step by step)</h3>
          <p className="mt-1 text-xs text-sky-700">Làm theo thứ tự từ trái sang phải để đảm bảo chất lượng dữ liệu.</p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="rounded-lg px-3 py-1.5 text-xs font-semibold text-sky-700 transition hover:bg-sky-100"
        >
          Đã hiểu, ẩn
        </button>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {steps.map((step) => (
          <div key={step.number} className="rounded-xl bg-white px-4 py-3 shadow-sm">
            <p className="text-sm font-semibold text-slate-900">
              <span className="mr-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-sky-600 text-xs text-white">
                {step.number}
              </span>
              {step.tab}
            </p>
            <p className="mt-1.5 text-xs leading-5 text-slate-600">{step.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
