"use client";

import { useEffect, useMemo, useState } from "react";
import styles from "./Marketplace.module.css";
import SlotRing from "./SlotRing";
import {
  CATEGORIES,
  MOCK_CIRCLES,
  formatPayout,
  type Category,
  type Circle,
  type Currency,
  type Frequency,
} from "./data";

type SortKey = "recommended" | "payout-high" | "slots" | "soonest";

interface FilterState {
  currency: Currency | "";
  freq: Frequency | "";
  min: number;
  max: number;
  rounds: string;
  slots: string;
}

const DEFAULT_FILTERS: FilterState = {
  currency: "",
  freq: "",
  min: 0,
  max: 999999,
  rounds: "",
  slots: "",
};

function activeFilterCount(f: FilterState): number {
  let n = 0;
  if (f.currency) n++;
  if (f.freq) n++;
  if (f.min > 0) n++;
  if (f.max < 999999) n++;
  if (f.rounds) n++;
  if (f.slots) n++;
  return n;
}

export default function Marketplace({
  circles = MOCK_CIRCLES,
}: {
  circles?: Circle[];
}) {
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<Category | "All">("All");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [draftFilters, setDraftFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [sort, setSort] = useState<SortKey>("recommended");
  const [saved, setSaved] = useState<Set<number>>(new Set());

  // One orchestrated skeleton -> content reveal on mount, not a per-card effect.
  useEffect(() => {
    const t = setTimeout(() => setLoading(false), 550);
    return () => clearTimeout(t);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const f = appliedFilters;
    let list = circles.filter((c) => {
      if (category !== "All" && c.category !== category) return false;
      if (q && !(c.name.toLowerCase().includes(q) || c.category.toLowerCase().includes(q)))
        return false;
      if (f.currency && c.currency !== f.currency) return false;
      if (f.freq && c.freq !== f.freq) return false;
      if (c.payout < f.min) return false;
      if (c.payout > f.max) return false;
      if (f.rounds && c.rounds > Number(f.rounds)) return false;
      if (f.slots && c.slotsTotal - c.slotsFilled < Number(f.slots)) return false;
      return true;
    });

    list = [...list];
    if (sort === "payout-high") list.sort((a, b) => b.payout - a.payout);
    else if (sort === "slots")
      list.sort((a, b) => b.slotsTotal - b.slotsFilled - (a.slotsTotal - a.slotsFilled));
    else if (sort === "soonest") list.sort((a, b) => a.nextDays - b.nextDays);

    return list;
  }, [circles, category, query, appliedFilters, sort]);

  function clearAll() {
    setQuery("");
    setCategory("All");
    setDraftFilters(DEFAULT_FILTERS);
    setAppliedFilters(DEFAULT_FILTERS);
    setDrawerOpen(false);
  }

  function toggleSaved(id: number) {
    setSaved((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const filterCount = activeFilterCount(appliedFilters);

  return (
    <section className={styles.marketplace}>
      <div className={styles.head}>
        <div className={styles.headText}>
          <h1>Find a circle that fits your plans</h1>
          <p>
            Browse open circles from the Ajo community. Sign in and meet the
            eligibility requirements to join.
          </p>
        </div>
        <div className={styles.headMeta}>Updated just now</div>
      </div>

      <div className={styles.searchRow}>
        <div className={styles.searchField}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by goal — travel, tuition, home…"
            aria-label="Search circles"
          />
        </div>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnGhost} ${filterCount > 0 ? styles.btnGhostActive : ""}`}
          onClick={() => setDrawerOpen((o) => !o)}
          aria-expanded={drawerOpen}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="4" y1="6" x2="20" y2="6" />
            <line x1="4" y1="12" x2="20" y2="12" />
            <line x1="4" y1="18" x2="20" y2="18" />
            <circle cx="9" cy="6" r="2" fill="currentColor" stroke="none" />
            <circle cx="16" cy="12" r="2" fill="currentColor" stroke="none" />
            <circle cx="10" cy="18" r="2" fill="currentColor" stroke="none" />
          </svg>
          Filters
          {filterCount > 0 && <span className={styles.btnCount}>{filterCount}</span>}
        </button>
      </div>

      <div className={styles.chipRow}>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            className={`${styles.chip} ${category === cat ? styles.chipActive : ""}`}
            onClick={() => setCategory(cat)}
            aria-pressed={category === cat}
          >
            {cat}
          </button>
        ))}
      </div>

      <div className={`${styles.drawer} ${drawerOpen ? styles.drawerOpen : ""}`}>
        <div className={styles.drawerInner}>
          <div className={styles.field}>
            <label htmlFor="f-currency">Currency</label>
            <select
              id="f-currency"
              value={draftFilters.currency}
              onChange={(e) =>
                setDraftFilters((f) => ({ ...f, currency: e.target.value as Currency | "" }))
              }
            >
              <option value="">Any</option>
              <option value="CAD">CAD</option>
              <option value="USD">USD</option>
              <option value="NGN">NGN</option>
            </select>
          </div>
          <div className={styles.field}>
            <label htmlFor="f-freq">Contribution frequency</label>
            <select
              id="f-freq"
              value={draftFilters.freq}
              onChange={(e) =>
                setDraftFilters((f) => ({ ...f, freq: e.target.value as Frequency | "" }))
              }
            >
              <option value="">Any</option>
              <option value="Weekly">Weekly</option>
              <option value="Bi-weekly">Bi-weekly</option>
              <option value="Monthly">Monthly</option>
              <option value="Quarterly">Quarterly</option>
            </select>
          </div>
          <div className={styles.field}>
            <label htmlFor="f-min">Minimum payout</label>
            <select
              id="f-min"
              value={draftFilters.min}
              onChange={(e) => setDraftFilters((f) => ({ ...f, min: Number(e.target.value) }))}
            >
              <option value={0}>Any</option>
              <option value={500}>CA$500+</option>
              <option value={1000}>CA$1,000+</option>
              <option value={2000}>CA$2,000+</option>
            </select>
          </div>
          <div className={styles.field}>
            <label htmlFor="f-max">Maximum payout</label>
            <select
              id="f-max"
              value={draftFilters.max}
              onChange={(e) => setDraftFilters((f) => ({ ...f, max: Number(e.target.value) }))}
            >
              <option value={999999}>Any</option>
              <option value={1000}>Up to CA$1,000</option>
              <option value={2000}>Up to CA$2,000</option>
              <option value={5000}>Up to CA$5,000</option>
            </select>
          </div>
          <div className={styles.field}>
            <label htmlFor="f-rounds">Maximum rounds</label>
            <select
              id="f-rounds"
              value={draftFilters.rounds}
              onChange={(e) => setDraftFilters((f) => ({ ...f, rounds: e.target.value }))}
            >
              <option value="">Any</option>
              <option value="6">Up to 6</option>
              <option value="8">Up to 8</option>
              <option value="12">Up to 12</option>
            </select>
          </div>
          <div className={styles.field}>
            <label htmlFor="f-slots">Minimum slots open</label>
            <select
              id="f-slots"
              value={draftFilters.slots}
              onChange={(e) => setDraftFilters((f) => ({ ...f, slots: e.target.value }))}
            >
              <option value="">Any</option>
              <option value="1">1+</option>
              <option value="2">2+</option>
              <option value="4">4+</option>
            </select>
          </div>
          <div className={styles.drawerActions}>
            <button type="button" className={styles.linkBtn} onClick={clearAll}>
              Clear filters
            </button>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnPrimary}`}
              onClick={() => {
                setAppliedFilters(draftFilters);
                setDrawerOpen(false);
              }}
            >
              Apply filters
            </button>
          </div>
        </div>
      </div>

      <div className={styles.resultsMeta}>
        <div className={styles.resultsCount}>
          <b>{loading ? "–" : filtered.length}</b> circles open
        </div>
        <div className={styles.sortRow}>
          Sort by
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            <option value="recommended">Recommended</option>
            <option value="payout-high">Highest payout</option>
            <option value="slots">Most slots open</option>
            <option value="soonest">Payout soonest</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className={styles.grid}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className={styles.skelCard} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className={styles.empty}>
          <h3>No circles match those filters</h3>
          <p>Try widening your payout range or clearing a filter.</p>
          <button type="button" className={`${styles.btn} ${styles.btnPrimary}`} onClick={clearAll}>
            Clear all filters
          </button>
        </div>
      ) : (
        <div className={styles.grid}>
          {filtered.map((c, idx) => {
            const open = c.slotsTotal - c.slotsFilled;
            const isSaved = saved.has(c.id);
            const urgent = open <= 2;
            return (
              <article key={c.id} className={styles.card} style={{ animationDelay: `${idx * 45}ms` }}>
                <div className={styles.cardTop}>
                  <span className={styles.tag}>{c.category}</span>
                  <button
                    type="button"
                    className={`${styles.favBtn} ${isSaved ? styles.favBtnSaved : ""}`}
                    onClick={() => toggleSaved(c.id)}
                    aria-label={isSaved ? "Remove from saved circles" : "Save this circle"}
                    aria-pressed={isSaved}
                  >
                    <svg viewBox="0 0 24 24" fill={isSaved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                      <path d="M12 21s-6.7-4.35-9.3-8.1C1 10.1 1.6 6.6 4.6 5.2 7 4.1 9.6 5 12 7.7 14.4 5 17 4.1 19.4 5.2c3 1.4 3.6 4.9 1.9 7.7C18.7 16.65 12 21 12 21Z" />
                    </svg>
                  </button>
                </div>

                <div className={styles.cardMid}>
                  <div className={styles.ringWrap}>
                    <SlotRing total={c.slotsTotal} filled={c.slotsFilled} />
                    <div className={styles.ringCenter}>
                      <b>{open}</b>open
                    </div>
                  </div>
                  <div>
                    <p className={styles.cardTitle}>{c.name}</p>
                    <p className={styles.cardSub}>
                      {c.slotsFilled} of {c.slotsTotal} slots filled
                    </p>
                  </div>
                </div>

                <div className={styles.payoutRow}>
                  <span className={styles.payoutAmount}>{formatPayout(c.payout, c.currency)}</span>
                  <span className={styles.payoutLabel}>payout per member</span>
                </div>

                <div className={styles.cardStats}>
                  <div>
                    <span className={styles.statLabel}>Frequency</span>
                    <span className={styles.statValue}>{c.freq}</span>
                  </div>
                  <div>
                    <span className={styles.statLabel}>Rounds</span>
                    <span className={styles.statValue}>{c.rounds}</span>
                  </div>
                  <div>
                    <span className={styles.statLabel}>Next payout</span>
                    <span className={styles.statValue}>{c.nextDays}d</span>
                  </div>
                  <div>
                    <span className={styles.statLabel}>Slots left</span>
                    <span className={styles.statValue}>{open}</span>
                  </div>
                </div>

                <div className={styles.cardFoot}>
                  <div className={styles.trust}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2 4 5v6c0 5 3.4 8.7 8 10 4.6-1.3 8-5 8-10V5l-8-3Z" />
                      <path d="m9 12 2 2 4-4" />
                    </svg>
                    <span>{c.trust}</span>
                  </div>
                  <button type="button" className={`${styles.btn} ${styles.btnPrimary} ${styles.cardCta}`}>
                    Check eligibility
                  </button>
                </div>

                {urgent && (
                  <div className={styles.urgency}>
                    Only {open} spot{open === 1 ? "" : "s"} left — next round starts in{" "}
                    {c.nextDays} day{c.nextDays === 1 ? "" : "s"}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}

      <p className={styles.disclaimer}>Illustrative circles · UI mockup (examples only)</p>
    </section>
  );
}
