import fs from "node:fs";
import path from "node:path";

const measurementId = "G-T2TS9NCN2N";
const marker = "portfolio-consent-analytics";
const ignored = new Set([".git", ".github", "node_modules", ".tmp", "reports", "test-results"]);
const root = path.resolve(process.argv[2] || ".");

function walk(directory) {
  return fs.readdirSync(directory, {withFileTypes:true}).flatMap((entry) => {
    if (ignored.has(entry.name)) return [];
    const target = path.join(directory, entry.name);
    return entry.isDirectory() ? walk(target) : entry.isFile() && entry.name.endsWith(".html") ? [target] : [];
  });
}

const head = `<!-- portfolio-consent-analytics -->
<script>
(function(w,d,id){
  var key='portfolio-analytics-consent-v1';
  function load(){
    if(w.__portfolioAnalyticsLoaded)return;
    w.__portfolioAnalyticsLoaded=true;
    w.dataLayer=w.dataLayer||[];
    w.gtag=w.gtag||function(){w.dataLayer.push(arguments);};
    w.gtag('js',new Date());
    w.gtag('config',id,{anonymize_ip:true});
    var s=d.createElement('script');
    s.async=true;
    s.src='https://www.googletagmanager.com/gtag/js?id='+encodeURIComponent(id);
    d.head.appendChild(s);
  }
  w.portfolioAnalyticsConsent={
    grant:function(){try{localStorage.setItem(key,'granted');}catch(e){} load(); var n=d.getElementById('portfolio-analytics-consent');if(n)n.remove();},
    deny:function(){try{localStorage.setItem(key,'denied');}catch(e){} var n=d.getElementById('portfolio-analytics-consent');if(n)n.remove();}
  };
  try{if(localStorage.getItem(key)==='granted')load();}catch(e){}
})(window,document,'G-T2TS9NCN2N');
</script>`;

const banner = `<div id="portfolio-analytics-consent" role="dialog" aria-label="Analytics preference" style="position:fixed;z-index:2147483647;right:16px;bottom:16px;max-width:390px;padding:16px;border:1px solid #d0d7de;border-radius:12px;background:#fff;color:#1f2328;font:14px/1.45 system-ui,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.18)">
  <strong style="display:block;margin-bottom:6px">Optional analytics</strong>
  <span>Allow anonymous usage measurement with Google Analytics? No analytics request is sent before you accept.</span>
  <span style="display:flex;gap:8px;margin-top:12px">
    <button type="button" onclick="portfolioAnalyticsConsent.grant()" style="padding:7px 12px;border:0;border-radius:8px;background:#0969da;color:#fff;cursor:pointer">Allow</button>
    <button type="button" onclick="portfolioAnalyticsConsent.deny()" style="padding:7px 12px;border:1px solid #d0d7de;border-radius:8px;background:#fff;color:#1f2328;cursor:pointer">No thanks</button>
  </span>
</div>
<script>(function(){try{if(localStorage.getItem('portfolio-analytics-consent-v1')){var n=document.getElementById('portfolio-analytics-consent');if(n)n.remove();}}catch(e){}})();</script>`;

if (!fs.existsSync(root)) throw new Error(`Missing analytics target: ${root}`);
const files = walk(root);
if (!files.length) throw new Error(`No HTML files below ${root}`);
let changed = 0;
for (const file of files) {
  let html = fs.readFileSync(file, "utf8");
  if (html.includes(marker)) continue;
  if (/googletagmanager\.com\/(?:gtag\/js|gtm\.js)|GTM-[A-Z0-9]+|gtag\s*\(/i.test(html)) {
    throw new Error(`Existing analytics/tag manager detected in ${file}; refusing duplicate installation`);
  }
  if (!/<\/head>/i.test(html) || !/<body(?:\s[^>]*)?>/i.test(html)) throw new Error(`Missing head/body in ${file}`);
  html = html.replace(/<\/head>/i, `${head}\n</head>`);
  html = html.replace(/<body(?:\s[^>]*)?>/i, (opening) => `${opening}\n${banner}`);
  fs.writeFileSync(file, html);
  changed += 1;
}
for (const file of files) {
  const html = fs.readFileSync(file, "utf8");
  const loaders = (html.match(/googletagmanager\.com\/gtag\/js/g) || []).length;
  if (!html.includes(marker) || loaders !== 1) throw new Error(`Analytics invariant failed for ${file}: marker=${html.includes(marker)} loaders=${loaders}`);
}
console.log(`analytics_id=${measurementId} html=${files.length} changed=${changed} duplicate_loaders=0`);
