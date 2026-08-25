# Responsive Design Improvements — Nidhi Diagnostic

**Date:** 2026-08-25
**Approach:** Tailwind utility tuning — fix responsive classes directly in templates

## Goal

Make the Nidhi Diagnostic website (9 public pages + 14 admin pages) fully responsive across all screen sizes: mobile phones (320px+), tablets (640px+), laptops (1024px+), and desktops (1280px+).

## Current State

- Flask + Tailwind CSS 3.4 + Alpine.js
- Already has basic `sm:`/`md:`/`lg:` breakpoint usage
- Mobile hamburger menu exists but lacks animation
- Admin sidebar has toggle but no backdrop overlay
- Map iframes use fixed `min-h` values
- Tables in admin lack horizontal scroll on mobile

## Changes by File

### 1. `app/templates/website/base.html`

- **Mobile menu:** Add Alpine.js `x-transition` for smooth slide-down. Change hamburger icon to animate to X when open.
- **Footer:** On mobile (`<640px`), use single-column layout. At `sm:`, switch to 2-column grid. Keep `lg:grid-cols-4` for desktop.
- **Flash messages:** Add `overflow-hidden` class to prevent text overflow.

### 2. `app/templates/website/home.html`

- **Hero section:** Reduce vertical padding on mobile: `py-10 sm:py-16 lg:py-24`. Keep `lg:grid-cols-2` for hero+form.
- **Map iframe (Hours section):** Replace `min-h-[320px]` with `aspect-video` for natural responsive height. Keep `lg:col-span-2`.
- **Stats row (`dl`):** Already `grid-cols-3` with `max-w-md` — works well. No change needed.
- **Services grid:** Already `sm:grid-cols-2 lg:grid-cols-3` — works well.

### 3. `app/templates/website/contact.html`

- **Map iframe:** Replace `min-h-[420px]` with `aspect-video`. On mobile, the map stacks above/below the form (already uses `lg:grid-cols-5`).

### 4. `app/templates/website/services.html`

- **Cards:** Add `overflow-hidden` to prevent text overflow in edge cases.

### 5. `app/templates/website/about.html`

- **Cards:** Add `overflow-hidden` to mission/technology cards.

### 6. `app/templates/website/category.html`

- **Sidebar:** Already stacks on mobile (`lg:grid-cols-3`). No major changes needed.

### 7. `app/templates/website/book.html`

- Already responsive with `sm:grid-cols-2` and `p-6 sm:p-8`. No changes needed.

### 8. `app/templates/website/book_status.html`

- Already simple and responsive. No changes needed.

### 9. `app/templates/website/book_success.html`

- Already centered and responsive. No changes needed.

### 10. `app/templates/admin/base.html`

- **Sidebar:** Add `transition-transform duration-300` for smooth slide. Add backdrop overlay (`x-show="sidebar"` on mobile) — clicking overlay closes sidebar.
- **Top bar:** Global search already `hidden sm:block`. Keep as-is.
- **Page content:** Already `p-4 sm:p-6 lg:p-8`. Good.

### 11. Admin sub-templates with tables

- Wrap all `<table>` elements in `<div class="overflow-x-auto">` to enable horizontal scrolling on small screens.

## Files to Modify

| # | File | Priority |
|---|------|----------|
| 1 | `app/templates/website/base.html` | High |
| 2 | `app/templates/website/home.html` | High |
| 3 | `app/templates/website/contact.html` | Medium |
| 4 | `app/templates/admin/base.html` | High |
| 5 | `app/templates/website/services.html` | Low |
| 6 | `app/templates/website/about.html` | Low |
| 7 | Admin sub-templates (tables) | Medium |

## Verification

- Open site in browser, resize from 320px to 1440px width
- Check all 9 website pages render correctly at each breakpoint
- Check admin sidebar toggles smoothly on mobile
- Check admin tables scroll horizontally on narrow screens
- Check map iframes resize naturally
- Run `npx tailwindcss -i app/static/css/src/input.css -o app/static/css/app.css` to rebuild CSS if needed
