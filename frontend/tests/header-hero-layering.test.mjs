import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

function read(relativePath) {
  return readFileSync(resolve(process.cwd(), relativePath), 'utf8');
}

function getRuleBody(css, selector) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = css.match(new RegExp(`${escapedSelector}\\s*\\{([\\s\\S]*?)\\}`));
  expect(match, `missing selector: ${selector}`).toBeTruthy();
  return match[1];
}

describe('home page hero layering', () => {
  it('does not use internal padding-top to create header spacing', () => {
    const homeCss = read('src/styles/pages/home.css');
    const heroSection = getRuleBody(homeCss, '.hero-section');
    expect(heroSection).not.toMatch(/padding-top\s*:/);
    expect(heroSection).toMatch(
      /margin-top:\s*calc\(\s*-1\s*\*\s*\(var\(--site-header-top,\s*16px\)\s*\+\s*var\(--site-header-height,\s*60px\)/
    );
  });

  it('adds a background layer for non page-padded home layouts', () => {
    const homeCss = read('src/styles/pages/home.css');
    const mainAreaHomePage = getRuleBody(homeCss, '.main-area > .page:not(.page-padded)');
    const mainAreaHomePageBefore = getRuleBody(
      homeCss,
      '.main-area > .page:not(.page-padded)::before'
    );
    expect(mainAreaHomePage).toMatch(/position:\s*relative/);
    expect(mainAreaHomePageBefore).toMatch(/radial-gradient/);
  });

  it('keeps the hero vignette non-interactive', () => {
    const homeCss = read('src/styles/pages/home.css');
    const heroVignette = getRuleBody(homeCss, '.hero-vignette');
    expect(heroVignette).toMatch(/pointer-events:\s*none/);
  });

  it('adds a top blend layer between the header and background image', () => {
    const homeCss = read('src/styles/pages/home.css');
    const heroTopBlend = getRuleBody(homeCss, '.hero-section::before');
    expect(heroTopBlend).toMatch(/linear-gradient/);
    expect(heroTopBlend).toMatch(/pointer-events:\s*none/);
  });

  it('renders the row header as a glass card', () => {
    const homeCss = read('src/styles/pages/home.css');
    const rowHeader = getRuleBody(homeCss, '.row-header');
    expect(rowHeader).toMatch(/backdrop-filter:\s*blur/);
    expect(rowHeader).toMatch(/border-radius/);
    expect(rowHeader).toMatch(/background:\s*linear-gradient/);
  });

  it('syncs header metrics into CSS custom properties', () => {
    const appVue = read('src/App.vue');
    expect(appVue).toMatch(/--site-header-height/);
    expect(appVue).toMatch(/--site-header-top/);
  });
});
