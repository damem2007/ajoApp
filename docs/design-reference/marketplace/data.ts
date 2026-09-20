export type Currency = "CAD" | "USD" | "NGN";

export type Frequency =
  | "Weekly"
  | "Bi-weekly"
  | "Monthly"
  | "Quarterly";

export type Category =
  | "Travel"
  | "Education"
  | "Family"
  | "Community"
  | "Business";

export interface Circle {
  id: number;
  name: string;
  category: Category;
  payout: number;
  currency: Currency;
  freq: Frequency;
  rounds: number;
  slotsTotal: number;
  slotsFilled: number;
  trust: string;
  nextDays: number; // days until next payout round
}

export const CATEGORIES: Array<Category | "All"> = [
  "All",
  "Travel",
  "Education",
  "Family",
  "Community",
  "Business",
];

// Replace with a real API call (e.g. `GET /api/circles`) once wired up.
export const MOCK_CIRCLES: Circle[] = [
  {
    id: 1,
    name: "Next step circle",
    category: "Travel",
    payout: 1200,
    currency: "CAD",
    freq: "Monthly",
    rounds: 6,
    slotsTotal: 6,
    slotsFilled: 3,
    trust: "Verified organizer",
    nextDays: 9,
  },
  {
    id: 2,
    name: "Shared goals circle",
    category: "Family",
    payout: 2000,
    currency: "CAD",
    freq: "Bi-weekly",
    rounds: 8,
    slotsTotal: 8,
    slotsFilled: 6,
    trust: "Verified organizer",
    nextDays: 2,
  },
  {
    id: 3,
    name: "Community circle",
    category: "Community",
    payout: 1500,
    currency: "CAD",
    freq: "Quarterly",
    rounds: 6,
    slotsTotal: 6,
    slotsFilled: 2,
    trust: "12 members strong",
    nextDays: 38,
  },
  {
    id: 4,
    name: "Campus fund circle",
    category: "Education",
    payout: 800,
    currency: "CAD",
    freq: "Monthly",
    rounds: 4,
    slotsTotal: 4,
    slotsFilled: 3,
    trust: "Verified organizer",
    nextDays: 4,
  },
  {
    id: 5,
    name: "Homecoming circle",
    category: "Family",
    payout: 3000,
    currency: "CAD",
    freq: "Monthly",
    rounds: 10,
    slotsTotal: 10,
    slotsFilled: 5,
    trust: "9 members strong",
    nextDays: 15,
  },
  {
    id: 6,
    name: "Founders' circle",
    category: "Business",
    payout: 5000,
    currency: "USD",
    freq: "Monthly",
    rounds: 8,
    slotsTotal: 8,
    slotsFilled: 7,
    trust: "Verified organizer",
    nextDays: 1,
  },
  {
    id: 7,
    name: "Summer trip circle",
    category: "Travel",
    payout: 900,
    currency: "CAD",
    freq: "Weekly",
    rounds: 6,
    slotsTotal: 6,
    slotsFilled: 1,
    trust: "Verified organizer",
    nextDays: 20,
  },
  {
    id: 8,
    name: "Tuition bridge circle",
    category: "Education",
    payout: 1800,
    currency: "USD",
    freq: "Monthly",
    rounds: 9,
    slotsTotal: 9,
    slotsFilled: 4,
    trust: "14 members strong",
    nextDays: 12,
  },
  {
    id: 9,
    name: "Neighbours circle",
    category: "Community",
    payout: 1000,
    currency: "CAD",
    freq: "Bi-weekly",
    rounds: 5,
    slotsTotal: 5,
    slotsFilled: 4,
    trust: "Verified organizer",
    nextDays: 3,
  },
];

export function formatPayout(amount: number, currency: Currency): string {
  const symbol = currency === "USD" ? "US$" : currency === "NGN" ? "\u20A6" : "CA$";
  return `${symbol}${amount.toLocaleString()}`;
}
