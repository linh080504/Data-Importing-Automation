import type { CountryOption } from "@/lib/types";

export const COUNTRIES: CountryOption[] = [
  {
    name: "India",
    code: 356,
    phonePrefix: "+91",
    currencyLabel: "INR",
    defaultFinancials: "INR 50k-250k ($600-3000)",
    listPageCandidates: [
      "List of institutions of higher education in India",
      "List of universities in India",
      "List of colleges in India",
    ],
  },
  {
    name: "United States",
    code: 840,
    phonePrefix: "+1",
    currencyLabel: "USD",
    defaultFinancials: "USD 8k-45k ($8000-45000)",
    listPageCandidates: [
      "List of colleges and universities in the United States",
      "Lists of American institutions of higher education",
    ],
  },
  {
    name: "United Kingdom",
    code: 826,
    phonePrefix: "+44",
    currencyLabel: "GBP",
    defaultFinancials: "GBP 9k-28k ($11000-35000)",
    listPageCandidates: ["List of universities in the United Kingdom"],
  },
  {
    name: "Canada",
    code: 124,
    phonePrefix: "+1",
    currencyLabel: "CAD",
    defaultFinancials: "CAD 7k-35k ($5000-26000)",
    listPageCandidates: ["List of universities in Canada", "List of colleges in Canada"],
  },
  {
    name: "Australia",
    code: 36,
    phonePrefix: "+61",
    currencyLabel: "AUD",
    defaultFinancials: "AUD 10k-42k ($6500-28000)",
    listPageCandidates: ["List of universities in Australia"],
  },
  {
    name: "Germany",
    code: 276,
    phonePrefix: "+49",
    currencyLabel: "EUR",
    defaultFinancials: "EUR 1k-20k ($1100-22000)",
    listPageCandidates: ["List of universities in Germany"],
  },
  {
    name: "France",
    code: 250,
    phonePrefix: "+33",
    currencyLabel: "EUR",
    defaultFinancials: "EUR 1k-18k ($1100-20000)",
    listPageCandidates: ["List of universities in France"],
  },
  {
    name: "Japan",
    code: 392,
    phonePrefix: "+81",
    currencyLabel: "JPY",
    defaultFinancials: "JPY 500k-1500k ($3200-9600)",
    listPageCandidates: ["List of universities in Japan"],
  },
  {
    name: "Singapore",
    code: 702,
    phonePrefix: "+65",
    currencyLabel: "SGD",
    defaultFinancials: "SGD 8k-45k ($5900-33000)",
    listPageCandidates: ["List of universities in Singapore"],
  },
  {
    name: "Vietnam",
    code: 704,
    phonePrefix: "+84",
    currencyLabel: "VND",
    defaultFinancials: "VND 20m-150m ($800-6000)",
    listPageCandidates: ["List of universities in Vietnam"],
  },
];

export function getCountryByCode(code: number | string) {
  const numeric = Number(code);
  return COUNTRIES.find((country) => country.code === numeric);
}

export function getCountryByName(name: string) {
  return COUNTRIES.find((country) => country.name.toLowerCase() === name.toLowerCase());
}
