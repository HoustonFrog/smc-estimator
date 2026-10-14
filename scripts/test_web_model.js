// 直接运行交互工具中的模型，检查新情景、控件依赖和日期边界。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');
new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
const start = html.indexOf('/* DATA:START');
const end = html.indexOf('/* ---------- 状态 ---------- */');
const code = html.slice(start, end) + '\n' + html.match(/function KSTR\(k\)\{[^\n]*\}/)[0] + `
globalThis.M = {DATASETS, ctxFor, plan, simulate, sortAsc, qt, estQueue, DN,
  acceptanceMean: typeof acceptanceMean === 'function' ? acceptanceMean : null,
  acceptedAt: typeof acceptedAt === 'function' ? acceptedAt : null};`;
const sandbox = {Intl, Math, Date, Int32Array};
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const M = sandbox.M;
assert.equal(typeof M.acceptanceMean, 'function', '网页必须采用显式的受理量逐步回落情景');
assert.equal(typeof M.acceptedAt, 'function');
const ds = M.DATASETS.CN, ctx = M.ctxFor('CN');
assert.equal(ds.meta.updatedTo, '2026-09');
assert.equal(ds.series.dec.at(-1), 84);
assert.equal(ds.series.acc.at(-1), 792);
assert.equal(ds.series.oh.at(-1), 2010);
assert.equal(ds.params.mu, 240);
assert.equal(ds.params.initialDisrupted, true);
assert.equal(ds.params.arrivals.baseline, 201);
assert.equal(M.acceptanceMean(ds, 0, 3), 792);
assert.equal(M.acceptanceMean(ds, 3, 3), 496.5);
assert.equal(M.acceptanceMean(ds, 6, 6), 496.5);
assert.equal(M.acceptedAt(ds, ctx, ctx.LASTK + 3, 201, 3), 496.5);
assert.ok(M.acceptanceMean(ds, 3, 6) > M.acceptanceMean(ds, 3, 3));

const future = M.plan(ds, ctx, '2027-03-15');
const fast = M.estQueue(ds, ctx, 0.35, 2, 240, future, 1);
const slow = M.estQueue(ds, ctx, 0.35, 2, 240, future, 6);
assert.ok(slow > fast, '受理量回落更慢时，后续递交者前面的积压必须增加');

const synthetic = JSON.parse(JSON.stringify(ds));
Object.assign(synthetic.params, {pool:[1,1,1,1,1,1], sd_mu:0, qsd:0, p_enter:0, p_exit:0, lo:0.3});
const options = {mode:'past', queue:720, joinKey:ctx.START, subDay:M.DN(2026,10,1),
  shockP:0, shockDur:2, mu:240, minService:0, nPaths:20, seed:99, H:3};
assert.ok(Array.from(M.simulate(synthetic, ctx, options)).every(d => d === 999999),
  '低产能状态不能在数据截止月后自动清零');
synthetic.params.p_exit = 1;
assert.ok(Array.from(M.simulate(synthetic, ctx, options)).every(d => d < 999999),
  '暂时低产能应能恢复正常，而非永久保持低产能');

const early = M.plan(ds, ctx, '2026-08-22');
const late = M.plan(ds, ctx, '2026-08-26');
assert.ok(late.queue - early.queue > 800, '8/24 政策日拆分必须保留');
assert.ok(M.plan(ds, ctx, '2023-12-01').mode);
assert.ok(M.plan(ds, ctx, '2028-02-29').mode);
assert.ok(M.plan(ds, ctx, '2028-03-01').err !== undefined);
for (const date of ['2026-09-15','2026-10-14','2027-03-15']) {
  const pl = M.plan(ds, ctx, date);
  const o = {...options, ...pl, shockP:0.35, nPaths:20000, H:54, halfLife:3};
  const sorted = M.sortAsc(M.simulate(ds, ctx, o));
  const iso = n => n >= 999999 ? 'censored' : new Date(n * 86400000).toISOString().slice(0,10);
  console.log(JSON.stringify({date, queue:pl.mode==='past'?pl.queue:M.estQueue(ds,ctx,0.35,2,240,pl,3),
    p10:iso(M.qt(sorted,0.1)),p50:iso(M.qt(sorted,0.5)),p90:iso(M.qt(sorted,0.9))}));
}
console.log('PASS: webpage model, arrival-speed sensitivity, capacity recovery, policy split, date bounds.');

// 执行页面真实事件绑定，使用最小 DOM 桩，不干预用户正在使用的浏览器。
const elements = new Map();
function element(tag) {
  return {tag, value:'', checked:false, events:{}, attrs:{}, children:[], style:{},
    parentElement:{getBoundingClientRect(){return {width:340};}},
    get firstChild(){return this.children[0];},
    addEventListener(name, fn){this.events[name]=fn;},
    setAttribute(name,value){this.attrs[name]=String(value);},
    appendChild(child){this.children.push(child);return child;},
    removeChild(child){this.children.splice(this.children.indexOf(child),1);}};
}
const document = {createElementNS(ns,tag){return element(tag);},getElementById(id) {
  if (!elements.has(id)) elements.set(id, element(id));
  return elements.get(id);
}};
const uiSandbox = {Intl, Math, Date, Int32Array, window:{addEventListener(){}}, document};
vm.createContext(uiSandbox);
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\ninit\(\);\n/, `
Object.assign(STR.zh,I18N_ZH);
globalThis.UI = {S, bindEvents, opts, ctxFor, plan, DATASETS,
  historyRows:typeof historyRows==='function'?historyRows:null,
  renderHistory:typeof renderHistory==='function'?renderHistory:null,
  setSchedule(fn) {schedule=fn;}};
`);
vm.runInContext(script, uiSandbox);
const UI = uiSandbox.UI;
let updates = 0;
UI.setSchedule(() => updates++);
UI.bindEvents();
elements.get('s-half').events.input({target:{value:'6'}});
assert.equal(UI.S.halfLife, 6);
assert.equal(updates, 1);
const uiCtx = UI.ctxFor('CN');
assert.equal(UI.opts(uiCtx, UI.plan(UI.DATASETS.CN,uiCtx,'2027-03-15'),20).halfLife, 6);
elements.get('s-mu').events.input({target:{value:'300'}});
elements.get('reset').events.click();
assert.equal(UI.S.halfLife, 3);
assert.equal(UI.S.mu, 240);
assert.equal(elements.get('s-half').value, 3);
assert.equal(elements.get('s-mu').value, 240);
console.log('PASS: real input callbacks update simulation options; reset restores generated defaults.');

assert.equal(typeof UI.historyRows,'function','需要最新六个月实际数据图表');
assert.equal(typeof UI.renderHistory,'function');
assert.ok(html.indexOf('id="s-answer"')<html.indexOf('id="s-history"'));
assert.ok(html.indexOf('id="s-history"')<html.indexOf('id="s-explainer"'),
  '历史图必须放在“这个数是怎么来的”之前');
const history = UI.historyRows(UI.DATASETS.CN);
assert.equal(history.length,6);
assert.equal(history[0].month,'2026-04');
assert.equal(history[5].month,'2026-09');
assert.equal(history[5].approved,78);
assert.equal(history[5].declined,6);
assert.equal(history[5].oh,2010);
assert.equal(history[5].dec,84);
const snapshot=JSON.stringify(history);
UI.S.halfLife=12;UI.S.mu=300;
assert.equal(JSON.stringify(UI.historyRows(UI.DATASETS.CN)),snapshot,
  '预测参数不能改变历史实际数据');
const flatten = node => [node,...node.children.flatMap(flatten)];
for(const width of [340,740]){
  for(const id of ['history-flow','history-stock'])
    document.getElementById(id).parentElement.getBoundingClientRect=()=>({width});
  UI.renderHistory();
  const flow=flatten(elements.get('history-flow'));
  const stock=flatten(elements.get('history-stock'));
  assert.equal(flow.filter(e=>e.attrs.class==='history-bar').length,12);
  assert.equal(stock.filter(e=>e.attrs.class==='history-dot').length,6);
  assert.equal(elements.get('history-flow').attrs['data-axis-min'],'0');
  assert.equal(elements.get('history-stock').attrs['data-axis-min'],'0');
  assert.ok(!JSON.stringify([...flow,...stock].map(e=>e.attrs)).includes('NaN'));
  flow.filter(e=>e.attrs.role==='button').at(-1).events.click({});
  assert.match(elements.get('history-flow-detail').textContent,/批准.*78/);
  assert.match(elements.get('history-flow-detail').textContent,/拒绝.*6/);
}
console.log('PASS: chart placement, six actual months, decision breakdown, responsive SVGs and interaction.');
