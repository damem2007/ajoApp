# Ajo marketplace component

Drop the `marketplace/` folder into your `components/` directory.

## 1. Wire up the fonts

This uses Fraunces (display) and Inter (body), matching the rest of the
product. Easiest path with `next/font`, in `app/layout.tsx`:

```tsx
import { Fraunces, Inter } from "next/font/google";

const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces" });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${fraunces.variable} ${inter.variable}`}>
      <body>{children}</body>
    </html>
  );
}
```

Then in `theme.css`, point the tokens at the font variables instead of the
bare family names:

```css
--ajo-font-display: var(--font-fraunces), ui-serif, Georgia, serif;
--ajo-font-body: var(--font-inter), -apple-system, sans-serif;
```

## 2. Import the theme tokens once

Add to the top of `app/globals.css`:

```css
@import "../components/marketplace/theme.css";
```

(Or merge the custom properties into your existing `:root` if you already
have a token file — they're namespaced with `--ajo-` so they won't collide.)

## 3. Use the component

```tsx
import Marketplace from "@/components/marketplace/Marketplace";

export default function MarketplacePage() {
  return <Marketplace />;
}
```

Pass your own data once you have a real endpoint:

```tsx
<Marketplace circles={circlesFromApi} />
```

`circles` must match the `Circle` type in `data.ts`.

## Notes

- Everything is self-contained (component + CSS module + one shared
  `SlotRing` sub-component); no extra npm packages needed.
- The search, category chips, advanced-filter drawer, sort, and the
  save/bookmark toggle are all live and driven by React state — swap the
  `filtered` memo's logic for a server-side query if you'd rather filter
  via an API.
- The skeleton → card reveal on mount is currently a fixed 550ms timer
  standing in for a real fetch; replace `useEffect` in `Marketplace.tsx`
  with your actual data-loading state.
- Light/dark mode is handled via `prefers-color-scheme` plus an optional
  `data-theme="dark"` / `data-theme="light"` override on `<html>` or
  `<body>`, if your app has a manual theme toggle.
