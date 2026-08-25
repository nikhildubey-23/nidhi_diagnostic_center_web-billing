# Responsive Design Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all pages fully responsive across mobile (320px+), tablet (640px+), laptop (1024px+), and desktop (1280px+) screen sizes.

**Architecture:** Tailwind utility tuning — add/fix responsive breakpoint classes directly in existing Jinja2 HTML templates. No new dependencies. Smooth Alpine.js transitions for mobile menu and admin sidebar.

**Tech Stack:** Flask (Jinja2), Tailwind CSS 3.4, Alpine.js

## Global Constraints

- Tailwind CSS 3.4.17 — no config changes needed, existing `content` paths cover all templates
- Alpine.js already loaded via `vendor/alpine.min.js`
- No new dependencies
- Preserve existing Tailwind utility patterns (`sm:`, `md:`, `lg:` prefixes)
- Breakpoints: `sm` = 640px, `md` = 768px, `lg` = 1024px

## File Structure

| File | Responsibility |
|------|---------------|
| `app/templates/website/base.html` | Mobile menu animation, footer responsive grid, flash overflow |
| `app/templates/website/home.html` | Hero padding, map aspect ratio |
| `app/templates/website/contact.html` | Map aspect ratio |
| `app/templates/admin/base.html` | Sidebar animation + backdrop overlay |
| 7 admin sub-templates | Add `overflow-x-auto` wrapper to tables |

---

### Task 1: Website Base Template — Mobile Menu Animation + Footer

**Files:**
- Modify: `app/templates/website/base.html`

**Interfaces:**
- Consumes: Alpine.js `open` variable (already defined on header)
- Produces: Smoothly animated mobile menu, responsive footer grid

- [ ] **Step 1: Add smooth transition to mobile menu**

Replace the mobile menu `<nav>` (line 43) with an animated version:

```html
<nav x-show="open" x-cloak
     x-transition:enter="transition ease-out duration-200"
     x-transition:enter-start="opacity-0 -translate-y-2"
     x-transition:enter-end="opacity-100 translate-y-0"
     x-transition:leave="transition ease-in duration-150"
     x-transition:leave-start="opacity-100 translate-y-0"
     x-transition:leave-end="opacity-0 -translate-y-2"
     class="space-y-1 border-t py-3 text-sm font-medium text-slate-700 md:hidden">
```

- [ ] **Step 2: Animate hamburger icon to X when open**

Replace the hamburger button (line 39) with an animated version:

```html
<button class="md:hidden p-2 text-slate-600" @click="open = !open" aria-label="Menu">
  <svg x-show="!open" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/></svg>
  <svg x-show="open" x-cloak class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
</button>
```

- [ ] **Step 3: Make footer responsive**

Replace the footer grid (line 73) to stack on mobile:

```html
<div class="mx-auto grid max-w-6xl gap-8 px-4 py-12 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
```

- [ ] **Step 4: Add overflow-hidden to flash messages**

Replace the flash messages wrapper (line 55):

```html
<div class="mx-auto w-full max-w-6xl overflow-hidden px-4">
```

- [ ] **Step 5: Visual verification**

Open the site in a browser, resize to 375px width. Verify:
- Hamburger icon animates to X when menu opens
- Menu slides down smoothly
- Footer shows as single column
- Flash messages don't overflow

---

### Task 2: Home Page — Hero Padding + Map Aspect Ratio

**Files:**
- Modify: `app/templates/website/home.html`

**Interfaces:**
- Consumes: existing Tailwind classes
- Produces: responsive hero section, naturally sizing map

- [ ] **Step 1: Reduce hero section padding on mobile**

Replace the hero section's padding (line 7):

```html
<div class="relative mx-auto grid max-w-6xl items-center gap-10 px-4 py-10 sm:py-16 lg:grid-cols-2 lg:py-24">
```

- [ ] **Step 2: Make the Hours+Contact+Map section map responsive**

Replace the map iframe container (line 145):

```html
<div class="lg:col-span-2 overflow-hidden rounded-xl border border-slate-200">
  <iframe title="Location map" src="{{ get_setting('map_embed_url') }}" class="aspect-video w-full" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe>
</div>
```

- [ ] **Step 3: Visual verification**

Open home page, resize to 375px. Verify:
- Hero section has comfortable padding on mobile
- Map iframe sizes naturally based on viewport width
- Layout stacks correctly on mobile, goes 2-col on lg+

---

### Task 3: Contact Page — Map Aspect Ratio

**Files:**
- Modify: `app/templates/website/contact.html`

**Interfaces:**
- Consumes: existing Tailwind classes
- Produces: responsive map on contact page

- [ ] **Step 1: Replace fixed-height map with aspect-video**

Replace the map iframe container (line 46):

```html
<div class="lg:col-span-3 overflow-hidden rounded-xl border border-slate-200">
  <iframe title="Location map" src="{{ get_setting('map_embed_url') }}" class="aspect-video w-full" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe>
</div>
```

- [ ] **Step 2: Visual verification**

Open contact page at 375px width. Verify:
- Map stacks above form on mobile
- Map uses natural aspect ratio, not fixed height
- Layout goes side-by-side on lg+

---

### Task 4: Admin Sidebar Animation + Backdrop

**Files:**
- Modify: `app/templates/admin/base.html`

**Interfaces:**
- Consumes: Alpine.js `sidebar` variable (already defined)
- Produces: smooth sidebar toggle with backdrop overlay

- [ ] **Step 1: Add smooth transition to sidebar**

Replace the sidebar `<aside>` (line 5) with:

```html
<aside class="fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-slate-200 bg-brand-950 text-slate-200 transition-transform duration-300 ease-in-out lg:translate-x-0"
       :class="sidebar ? 'translate-x-0' : '-translate-x-full'">
```

- [ ] **Step 2: Add backdrop overlay when sidebar is open on mobile**

Add this div right after the `</aside>` closing tag (after line 60):

```html
<!-- Backdrop overlay for mobile sidebar -->
<div x-show="sidebar" x-cloak
     @click="sidebar = false"
     class="fixed inset-0 z-20 bg-black/50 lg:hidden"
     x-transition:enter="transition ease-out duration-300"
     x-transition:enter-start="opacity-0"
     x-transition:enter-end="opacity-100"
     x-transition:leave="transition ease-in duration-200"
     x-transition:leave-start="opacity-100"
     x-transition:leave-end="opacity-0">
</div>
```

- [ ] **Step 3: Visual verification**

Open admin panel, resize to 375px. Verify:
- Sidebar slides in/out smoothly
- Backdrop appears when sidebar is open
- Clicking backdrop closes sidebar
- On desktop (lg+), sidebar is always visible, backdrop hidden

---

### Task 5: Admin Table Responsive Wrapping

**Files:**
- Modify: `app/templates/admin/bookings/detail.html`
- Modify: `app/templates/admin/patients/profile.html`
- Modify: `app/templates/admin/invoices/print.html`
- Modify: `app/templates/admin/finreports/index.html`
- Modify: `app/templates/admin/services/index.html`
- Modify: `app/templates/admin/invoices/edit_draft.html`
- Modify: `app/templates/admin/settings/faqs.html`

**Interfaces:**
- Consumes: existing `<table>` elements
- Produces: horizontally scrollable tables on small screens

- [ ] **Step 1: Add overflow-x-auto to bookings/detail.html**

Wrap the table at line 96 in:

```html
<div class="overflow-x-auto">
  <table ...existing table content... >
  </table>
</div>
```

- [ ] **Step 2: Add overflow-x-auto to patients/profile.html**

Wrap each of the 3 tables (lines 45, 64, 82) in:

```html
<div class="overflow-x-auto">
  <table ...existing table content... >
  </table>
</div>
```

- [ ] **Step 3: Add overflow-x-auto to invoices/print.html**

Wrap the table at line 24 in:

```html
<div class="overflow-x-auto">
  <table ...existing table content... >
  </table>
</div>
```

- [ ] **Step 4: Add overflow-x-auto to finreports/index.html**

Wrap each of the 2 tables (lines 44, 57) in:

```html
<div class="overflow-x-auto">
  <table ...existing table content... >
  </table>
</div>
```

- [ ] **Step 5: Add overflow-x-auto to services/index.html**

Wrap the table at line 22 in:

```html
<div class="overflow-x-auto">
  <table ...existing table content... >
  </table>
</div>
```

- [ ] **Step 6: Add overflow-x-auto to invoices/edit_draft.html**

Wrap the table at line 12 in:

```html
<div class="overflow-x-auto">
  <table ...existing table content... >
  </table>
</div>
```

- [ ] **Step 7: Add overflow-x-auto to settings/faqs.html**

Wrap the table at line 10 in:

```html
<div class="overflow-x-auto">
  <table ...existing table content... >
  </table>
</div>
```

- [ ] **Step 8: Visual verification**

Open admin panel pages at 375px width. Verify:
- Tables scroll horizontally when wider than viewport
- No content is clipped or hidden
- Desktop layout unchanged

---

### Task 6: Services + About Page Card Overflow

**Files:**
- Modify: `app/templates/website/services.html`
- Modify: `app/templates/website/about.html`

**Interfaces:**
- Consumes: existing card elements
- Produces: cards that handle text overflow gracefully

- [ ] **Step 1: Add overflow-hidden to service cards**

In `services.html`, the card div (line 22) already has `card flex h-full flex-col p-5`. No change needed — the `card` class already has `rounded-xl` and the grid containers handle overflow. Verify visually.

- [ ] **Step 2: Add overflow-hidden to about page cards**

In `about.html`, add `overflow-hidden` to the mission card (line 14):

```html
<div class="card overflow-hidden p-7">
```

And to the technology card (line 19):

```html
<div class="card overflow-hidden p-7">
```

- [ ] **Step 3: Visual verification**

Open services and about pages at various widths. Verify:
- No text or content overflows card boundaries
- Layout is clean at all breakpoints

---

### Task 7: Final Rebuild and Verification

**Files:**
- None (CSS rebuild only)

- [ ] **Step 1: Rebuild Tailwind CSS**

Run: `npx tailwindcss -i app/static/css/src/input.css -o app/static/css/app.css --minify`

- [ ] **Step 2: Full responsive audit**

Open all 9 website pages and the admin panel. Test at these widths:
- 375px (iPhone SE)
- 640px (tablet portrait)
- 768px (tablet landscape)
- 1024px (laptop)
- 1280px (desktop)

Verify for each page:
- No horizontal scrollbar (except admin tables which scroll internally)
- All content is readable and properly sized
- Navigation works on mobile
- Forms are usable on all sizes
- Maps resize naturally
- Footer stacks properly

- [ ] **Step 3: Commit all changes**

```bash
git add -A
git commit -m "feat: improve responsive design across all pages

- Animated mobile menu with hamburger-to-X transition
- Smooth admin sidebar with backdrop overlay
- Responsive footer grid (1-col mobile, 2-col tablet, 4-col desktop)
- Map iframes use aspect-video instead of fixed min-h
- Added overflow-x-auto to 7 admin tables for mobile scrolling
- Reduced hero section padding on mobile
- Added overflow-hidden to about page cards"
```
