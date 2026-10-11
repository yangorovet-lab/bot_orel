// Проверка лендинга в настоящем браузере: node tests/landing.test.mjs [_site/index.html]
import { chromium } from "playwright";
import path from "node:path";
import assert from "node:assert/strict";

const file = "file://" + path.resolve(process.argv[2] || "_site/index.html");
const opts = process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {};
const browser = await chromium.launch(opts);
const iso = (n) => { const d = new Date(); d.setHours(12); d.setDate(d.getDate() + n);
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); };
let failed = 0;
async function test(name, fn) {
  try { await fn(); console.log("✓", name); } catch (e) { failed++; console.log("✗", name, "\n ", e.message); }
}

for (const [label, viewport] of [["desktop", { width: 1280, height: 900 }], ["phone", { width: 375, height: 800 }]]) {
  for (const scheme of ["light", "dark"]) {
    const page = await browser.newPage({ viewport, colorScheme: scheme });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => m.type() === "error" && !/fonts\.(googleapis|gstatic)/.test(m.text()) && errors.push(m.text()));
    await page.goto(file);
    const t = `[${label}/${scheme}]`;

    await test(`${t} нет ошибок JS`, async () => assert.deepEqual(errors, []));
    await test(`${t} нет горизонтальной прокрутки`, async () => {
      const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
      assert.ok(sw <= cw, `scrollWidth ${sw} > ${cw}`);
    });
    await test(`${t} фон body задан явно`, async () => {
      const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      assert.notEqual(bg, "rgba(0, 0, 0, 0)");
    });
    await page.close();
  }
}

const page = await browser.newPage();
await page.goto(file);
const href = (sel) => page.getAttribute(sel, "href");

await test("заголовок страницы", async () => assert.equal(await page.title(), "Орёл ⇄ Москва"));
await test("по умолчанию: завтра, Орёл → Москва", async () => {
  assert.equal(await href("#go"), `https://ticket.rzd.ru/searchresults/v/1/2000140/2000000/${iso(1)}`);
  assert.equal(await page.getAttribute(".chip[aria-pressed=true]", "data-date"), iso(1));
});
await test("кнопка «Сегодня» меняет ссылку", async () => {
  await page.click("text=Сегодня");
  assert.ok((await href("#go")).endsWith(iso(0)));
  assert.equal(await page.textContent(".chip[aria-pressed=true]"), "Сегодня");
});
await test("выбор даты в календаре", async () => {
  await page.fill("#date", iso(10));
  await page.dispatchEvent("#date", "change");
  assert.ok((await href("#go")).endsWith(iso(10)));
  assert.equal(await page.$(".chip[aria-pressed=true]"), null);
});
await test("⇄ меняет направление на Москва → Орёл и обратно", async () => {
  await page.click("#swap");
  assert.equal(await page.textContent("#from"), "Москва");
  assert.ok((await href("#go")).includes("/2000000/2000140/"));
  assert.ok((await href("#yandex")).includes("fromName=" + encodeURIComponent("Москва")));
  await page.click("#swap");
  assert.ok((await href("#go")).includes("/2000140/2000000/"));
});
await test("ссылки открываются в новой вкладке", async () => {
  for (const s of ["#go", "#yandex"]) assert.equal(await page.getAttribute(s, "target"), "_blank");
});
await test("прошлые даты недоступны в календаре", async () => assert.equal(await page.getAttribute("#date", "min"), iso(0)));

await browser.close();
if (failed) { console.log(`\n${failed} тест(ов) упало`); process.exit(1); }
console.log("\nВсе тесты лендинга прошли");
