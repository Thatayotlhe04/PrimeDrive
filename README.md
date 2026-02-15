# PrimeDrive Botswana — PWA

## What's in this folder

```
index.html          — Main app (your full PrimeDrive site)
manifest.json       — PWA manifest (app name, icons, theme)
sw.js               — Service worker (offline caching)
offline.html        — Fallback page when offline
icons/              — App icons in all required sizes
```

## How to deploy

### Option 1: Netlify (free, recommended)
1. Go to https://app.netlify.com
2. Sign up / log in with GitHub or email
3. Drag and drop this entire folder onto the Netlify dashboard
4. Done — you'll get a URL like `https://primedrive.netlify.app`
5. To use your own domain (primedrivebotswana.com), go to Domain Settings and add it

### Option 2: Vercel (free)
1. Go to https://vercel.com
2. Sign up, click "Add New Project"
3. Upload this folder
4. Custom domain setup available in project settings

### Option 3: GitHub Pages (free)
1. Create a GitHub repo
2. Push all these files to the `main` branch
3. Go to Settings > Pages > Source: main branch
4. Your site will be at `https://yourusername.github.io/repo-name`

## Important notes

- The PWA **must** be served over HTTPS for the service worker to work
  (Netlify, Vercel, and GitHub Pages all do this automatically)
- The install prompt only appears in browsers that support PWA
  (Chrome, Edge, Samsung Internet, Firefox on Android)
- On iOS/Safari, users tap Share > "Add to Home Screen" instead
  (the app shows them instructions for this automatically)

## How users install it

**Android**: A banner appears at the bottom saying "Install PrimeDrive". 
They tap Install, and the app appears on their home screen.

**iPhone**: The app shows a hint telling them to tap Share > Add to Home Screen.

## Updating the app

Just replace the files on your hosting. Users will get the new version 
next time they open the app (the service worker handles this).

If you make a big update, change `CACHE_NAME` in `sw.js` from 
`'primedrive-v1'` to `'primedrive-v2'` so old caches get cleared.
