import fs from "node:fs";
import path from "node:path";

// Stage only the publisher-authored profile. This does not assert live availability or search eligibility.
const root = process.cwd();
const output = path.resolve(root, process.argv[2] || "_site");
const adoption = JSON.parse(fs.readFileSync(path.join(root, ".arwp/adoption.json"), "utf8"));
const source = path.resolve(root, adoption.profile_source);
if (!source.startsWith(root + path.sep)) throw new Error("Profile source must remain inside this repository");
const profile = JSON.parse(fs.readFileSync(source, "utf8"));
if (profile.profileVersion !== "0.1" || profile.canonicalUrl !== adoption.site_url) throw new Error("Profile and adoption identity differ");
const homepage = path.join(output, "index.html");
if (!fs.existsSync(homepage)) throw new Error(`Build the public homepage first: ${homepage}`);
const destination = path.join(output, "ai/site-profile.json");
fs.mkdirSync(path.dirname(destination), { recursive: true });
if (source !== destination) fs.copyFileSync(source, destination);
const href = new URL("ai/site-profile.json", profile.canonicalUrl).href;
let html = fs.readFileSync(homepage, "utf8");
const marker = "arwp-profile-discovery";
const link = `<link id="${marker}" rel="describedby" type="application/json" href="${href}" title="Agent-Ready Web Profile">`;
if (html.includes(`id="${marker}"`)) {
  html = html.replace(/<link\s[^>]*id="arwp-profile-discovery"[^>]*>/i, link);
} else {
  if (!/<\/head>/i.test(html)) throw new Error("Public homepage has no closing head");
  html = html.replace(/<\/head>/i, `${link}\n</head>`);
}
fs.writeFileSync(homepage, html);
if ((html.match(/id="arwp-profile-discovery"/g) || []).length !== 1) throw new Error("Expected one profile discovery link");
console.log(`ARWP staged: ${path.relative(root, destination)}; discovery=${href}`);
