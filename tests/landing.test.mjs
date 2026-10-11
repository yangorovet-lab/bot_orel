// Проверка лендинга в настоящем браузере с подменённым API.
// Сборка: API_URL=https://api.test/trains sh scripts/build_landing.sh && node tests/landing.test.mjs
import { chromium } from "playwright";
import path from "node:path";
import assert from "node:assert/strict";

const file = "file://" + path.resolve(process.argv[2] || "_site/index.html");
const browser = await chromium.launch();
const iso = (n) => { const d = new Date(); d.setHours(12); d.setDate(d.getDate() + n);
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); };
let failed = 0;
async function test(name, fn) {
  try { await fn(); console.log("✓", name); } catch (e) { failed++; console.log("✗", name, "\n ", e.message); }
}

const SAMPLE = (q) => ({
  from: q.get("from"), to: q.get("to"), date: q.get("date"), updated: q.get("date") + "T08:31:00",
  buy_url: `https://ticket.rzd.ru/searchresults/v/1/${q.get("from")}/${q.get("to")}/${q.get("date")}`,
  trains: [
    { train: "016А", name: "", dep: q.get("date") + "T01:20", arr: q.get("date") + "T06:05",
      cars: [{ type: "КУПЕ", seats: 2, price: 3200 }] },
    { train: "742В", name: "Ласточка", dep: q.get("date") + "T07:10", arr: q.get("date") + "T10:40",
      cars: [{ type: "СИДЯЧИЙ", seats: 17, price: 1300 }, { type: "БИЗНЕС", seats: 1, price: 4100 }] },
  ],
});

// mode: ok | empty | error | slow
async function openPage(opts = {}, mode = "ok") {
  const page = await browser.newPage(opts);
  const errors = [], requests = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && !/fonts\.(googleapis|gstatic)|Failed to load resource/.test(m.text()) && errors.push(m.text()));
  await page.route("https://api.test/**", async (route) => {
    const q = new URL(route.request().url()).searchParams;
    requests.push(Object.fromEntries(q));
    const headers = { "Access-Control-Allow-Origin": "*" };
    if (page._mode === "error") return route.fulfill({ status: 502, headers, json: { error: "РЖД не ответил, попробуйте через минуту" } });
    if (page._mode === "empty") return route.fulfill({ headers, json: { ...SAMPLE(q), trains: [] } });
    return route.fulfill({ headers, json: SAMPLE(q) });
  });
  page._mode = mode;
  await page.goto(file);
  return { page, errors, requests };
}

for (const [label, viewport] of [["desktop", { width: 1280, height: 900 }], ["phone", { width: 375, height: 800 }]]) {
  for (const scheme of ["light", "dark"]) {
    const { page, errors } = await openPage({ viewport, colorScheme: scheme });
    await page.waitForSelector(".train");
    const t = `[${label}/${scheme}]`;
    await test(`${t} нет ошибок JS`, async () => assert.deepEqual(errors, []));
    await test(`${t} нет горизонтальной прокрутки`, async () => {
      const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
      assert.ok(sw <= cw, `scrollWidth ${sw} > ${cw}`);
    });
    await test(`${t} фон body задан явно`, async () => {
      assert.notEqual(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), "rgba(0, 0, 0, 0)");
    });
    await page.close();
  }
}

{
  const { page, requests } = await openPage();
  await page.waitForSelector(".train");
  await test("заголовок страницы", async () => assert.equal(await page.title(), "Орёл ⇄ Москва"));
  await test("при открытии грузит места на завтра, Орёл → Москва", async () => {
    assert.deepEqual(requests[0], { from: "2000140", to: "2000000", date: iso(1) });
  });
  await test("показывает поезда со временем, длительностью и местами", async () => {
    const rows = await page.$$eval(".train", (els) => els.map((e) => e.innerText.replace(/\s+/g, " ")));
    assert.equal(rows.length, 2);
    assert.match(rows[1], /07:10 → 10:40/);
    assert.match(rows[1], /3 ч 30 мин · 742В · Ласточка/);
    assert.match(rows[1], /Сидячий 17 мест · от 1\s?300 ₽/);
    assert.match(rows[1], /Бизнес 1 место/);
    assert.match(rows[0], /Купе 2 места/);
    assert.match(await page.textContent(".results"), /2 поезда со свободными местами/);
    assert.match(await page.textContent("#updated"), /обновлено в 08:31/);
  });
  await test("поезд ведёт на РЖД в новой вкладке", async () => {
    const a = await page.$(".train");
    assert.equal(await a.getAttribute("href"), `https://ticket.rzd.ru/searchresults/v/1/2000140/2000000/${iso(1)}`);
    assert.equal(await a.getAttribute("target"), "_blank");
  });
  await test("смена даты перезагружает места", async () => {
    await page.click("text=Сегодня");
    await page.waitForFunction((d) => document.querySelector(".train")?.href.endsWith(d), iso(0));
    assert.equal(requests.at(-1).date, iso(0));
  });
  await test("⇄ грузит обратное направление Москва → Орёл", async () => {
    await page.click("#swap");
    await page.waitForFunction(() => document.querySelector(".train")?.href.includes("/2000000/2000140/"));
    assert.equal(requests.at(-1).from, "2000000");
    assert.equal(await page.textContent("#from"), "Москва");
  });
  await test("кнопка «Обновить» запрашивает заново", async () => {
    const n = requests.length;
    await page.click("#refresh");
    await page.waitForFunction(() => document.querySelector(".train"));
    assert.equal(requests.length, n + 1);
  });
  await test("прошлые даты недоступны в календаре", async () => assert.equal(await page.getAttribute("#date", "min"), iso(0)));
  await page.close();
}

{
  const { page } = await openPage({}, "empty");
  await page.waitForSelector(".state");
  await test("нет мест: понятное сообщение без листа ожидания", async () => {
    assert.match(await page.textContent(".state"), /Свободных мест нет/);
    assert.equal(await page.$(".train"), null);
  });
  await page.close();
}

{
  const { page } = await openPage({}, "error");
  await page.waitForSelector(".state");
  await test("ошибка сервера: текст ошибки и кнопка на РЖД", async () => {
    const txt = await page.textContent(".state");
    assert.match(txt, /Не получилось загрузить места/);
    assert.match(txt, /РЖД не ответил/);
    assert.ok((await page.getAttribute(".state a", "href")).startsWith("https://ticket.rzd.ru/searchresults/v/1/2000140/2000000/"));
  });
  await page.close();
}

await browser.close();
if (failed) { console.log(`\n${failed} тест(ов) упало`); process.exit(1); }
console.log("\nВсе тесты лендинга прошли");
