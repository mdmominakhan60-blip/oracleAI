// Точечный контраст-чек экрана auth-required: вычисляем фактические цвета getComputedStyle
import { chromium } from 'playwright-core';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', reducedMotion: 'reduce', ignoreHTTPSErrors: true, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
const page = await context.newPage();
await page.goto('https://localhost:3443/', { waitUntil: 'networkidle', timeout: 20000 });
await page.waitForTimeout(1200);
const data = await page.evaluate(() => {
  const lum = (r,g,b) => { const f=c=>{c/=255; return c<=0.03928?c/12.92:Math.pow((c+0.055)/1.055,2.4)}; return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b); };
  const parse = s => { const m=s.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/); return m?{r:+m[1],g:+m[2],b:+m[3],a:m[4]?+m[4]:1}:null; };
  const blend = (fg,bg) => ({r:fg.r*fg.a+bg.r*(1-fg.a),g:fg.g*fg.a+bg.g*(1-fg.a),b:fg.b*fg.a+bg.b*(1-fg.a)});
  const ratio = (a,b)=>{const l1=lum(a.r,a.g,a.b),l2=lum(b.r,b.g,b.b);const[h,l]=l1>l2?[l1,l2]:[l2,l1];return (h+0.05)/(l+0.05)};
  function bgOf(el){ let n=el; while(n){ const c=parse(getComputedStyle(n).backgroundColor); if(c && c.a>0){ return c.a<1&&n.parentElement? blend(c,bgOf(n.parentElement)):c; } n=n.parentElement; } return {r:10,g:9,b:32}; }
  const sels = ['.soft-empty__title','.soft-empty__copy','.btn.btn-primary','.user-name','.brand-title'];
  return sels.map(s=>{ const el=document.querySelector(s); if(!el) return s+': not found';
    const cs=getComputedStyle(el); const fg=parse(cs.color); const bg=bgOf(el); const r=ratio(fg,bg);
    return `${s}: color=${cs.color} bg=rgb(${bg.r|0},${bg.g|0},${bg.b|0}) fontSize=${cs.fontSize} fontWeight=${cs.fontWeight} ratio=${r.toFixed(2)}:1 ${r>=4.5?'AA-PASS':(r>=3?'AA-LARGE-only':'FAIL')}`; });
});
console.log(data.join('\n'));
await browser.close();
