#!/usr/bin/env python3
"""每月更新入口。

用法：
    cd scripts && python3 build_web_data.py

流程：遍历 data/<国家代码>/ 下的 CSV → 复用 smc_model_v2.py 的
load()/estimate()/pitvals() 估参 → 跑自检 → 把结果写回
index.html 里 DATA:START/DATA:END 之间的 DATASETS 对象。

新增国家 = 在 data/ 下新建一个目录（放 R1/R7/R8 三份 CSV），
并在下面的 COUNTRY_META / SHOCK_DEFAULTS 里补一行——不改其余代码。
"""
import re
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import smc_model_v2 as smc

ROOT = Path(__file__).resolve().parent.parent
RAW_ROOT = ROOT / "data"
HTML_PATH = ROOT / "index.html"

DATA_START = "/* DATA:START — 自动生成，请勿手改。来源：scripts/build_web_data.py */"
DATA_END = "/* DATA:END */"

# 国家展示名——季节性/中断风险/校准映射都是从各国自己的数据估出来的，不能跨国共用
COUNTRY_META = {
    "CN": {"zh": "中国", "en": "China"},
}
# 政策冲击情景的假设：不是从 CSV 估出来的，是主观判断，只需要设一次
SHOCK_DEFAULTS = {
    "CN": {"fromMonth": "2026-08", "defaultP": 0.35, "defaultDur": 2},
}


def mk(ym: str) -> int:
    y, m = ym.split("-")
    return int(y) * 12 + int(m)


def build_dataset(country_dir: Path):
    code = country_dir.name
    raw = str(country_dir) + "/"
    dec, acc, oh = smc.load(raw)
    smc.DEC, smc.ACC, smc.OH = dec, acc, oh
    smc.QSD = 80
    origin = dec.index[-1]
    par = smc.estimate(origin, look=3)
    pv = smc.pitvals()
    cal_map = {a: float(np.clip(np.quantile(pv, a), 0.005, 0.995)) for a in (.10, .25, .50, .75, .90)}

    months = [str(p) for p in dec.index]
    acc_aligned = acc.reindex(dec.index)
    oh_aligned = oh.reindex(dec.index)
    if acc_aligned.isna().any() or oh_aligned.isna().any():
        raise ValueError(f"[{code}] R7/R8 缺少 R1 对应月份的数据，检查下载是否完整")

    ds = {
        "meta": {
            "label": COUNTRY_META.get(code, {"zh": code, "en": code}),
            "updatedTo": months[-1],
            "firstMonth": months[0],
        },
        "series": {
            "months": months,
            "dec": [int(v) for v in dec.values],
            "acc": [int(v) for v in acc_aligned.values],
            "oh": [int(v) for v in oh_aligned.values],
        },
        "params": {
            "mu": round(float(par["mu"]), 2),
            "sd_mu": round(float(par["sd_mu"]), 2),
            "pool": [round(float(v), 4) for v in par["pool"]],
            "accPool": [int(v) for v in acc.tail(12).values],
            "p_enter": round(float(par["p_enter"]), 4),
            "p_exit": round(float(par["p_exit"]), 4),
            "lo": round(float(par["lo"]), 4),
            "seas": {str(k): v for k, v in smc.SEAS.items()},
            "qsd": 80,
            "block": int(smc.BLOCK),
        },
        "calibration": {
            "n": int(len(pv)),
            "map": {f"{k:.2f}": round(v, 3) for k, v in cal_map.items()},
        },
        "shock": SHOCK_DEFAULTS.get(code, {"fromMonth": months[-1], "defaultP": 0.35, "defaultDur": 2}),
    }
    return code, ds


def run_checks(code: str, ds: dict, prev_month_count: Optional[int]):
    s = ds["series"]
    lens = {len(s["months"]), len(s["dec"]), len(s["acc"]), len(s["oh"])}
    assert len(lens) == 1, f"[{code}] 四个数组长度不一致: {lens}"

    ks = [mk(x) for x in s["months"]]
    assert all(b - a == 1 for a, b in zip(ks, ks[1:])), f"[{code}] 月份序列有跳月"

    pool = ds["params"]["pool"]
    pool_mean = sum(pool) / len(pool)
    assert abs(pool_mean - 1.0) <= 0.01, f"[{code}] pool 均值偏离 1.0 过多: {pool_mean:.4f}"

    assert 0 < ds["params"]["lo"] < 1, f"[{code}] lo 超出 (0,1): {ds['params']['lo']}"
    assert 0 < ds["params"]["p_enter"] < 1, f"[{code}] p_enter 超出 (0,1): {ds['params']['p_enter']}"
    assert ds["params"]["mu"] > 0, f"[{code}] mu <= 0"

    mv = list(ds["calibration"]["map"].values())
    assert all(a <= b for a, b in zip(mv, mv[1:])), f"[{code}] 校准映射非单调递增: {mv}"

    if prev_month_count is not None:
        assert len(s["months"]) >= prev_month_count, (
            f"[{code}] 新数据月份数({len(s['months'])}) 少于上次({prev_month_count})，"
            "疑似下载到残缺文件"
        )

    for key in ("dec", "acc", "oh"):
        series = s[key]
        if len(series) >= 2 and series[-2] > 0:
            ratio = series[-1] / series[-2]
            assert ratio < 3.0, (
                f"[{code}] {key} 最新月({series[-1]}) 比上月({series[-2]}) 跳变 {ratio:.1f} 倍，"
                "疑似漏加国籍筛选或数据异常"
            )


def read_prev_datasets(html_text: str):
    """从当前 HTML 里读出旧的 months 数量，用于判断新数据是否变少了。读不到就返回空（首次跑）。"""
    m = re.search(re.escape(DATA_START) + r"(.*?)" + re.escape(DATA_END), html_text, re.S)
    if not m:
        return {}
    block = m.group(1)
    out = {}
    for code_m in re.finditer(r'\b([A-Z]{2}):\s*\{', block):
        code = code_m.group(1)
        months_m = re.search(r'"months":\[([^\]]*)\]', block[code_m.end():code_m.end() + 20000])
        if months_m:
            count = months_m.group(1).count(",") + 1 if months_m.group(1).strip() else 0
            out[code] = count
    return out


def to_js(obj, indent=0) -> str:
    pad = "  " * indent
    pad2 = "  " * (indent + 1)
    if isinstance(obj, dict):
        items = ",\n".join(f'{pad2}{_key(k)}: {to_js(v, indent + 1)}' for k, v in obj.items())
        return "{\n" + items + f"\n{pad}}}"
    if isinstance(obj, list):
        if all(isinstance(v, (int, float)) for v in obj):
            return "[" + ",".join(_num(v) for v in obj) + "]"
        items = ",\n".join(f'{pad2}{to_js(v, indent + 1)}' for v in obj)
        return "[\n" + items + f"\n{pad}]"
    if isinstance(obj, str):
        return '"' + obj.replace('"', '\\"') + '"'
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return _num(obj)
    raise TypeError(type(obj))


_IDENT_RE = re.compile(r'^[A-Za-z_$][A-Za-z0-9_$]*$')


def _key(k):
    # 裸标识符（如 "CN"）不加引号，其余一律加引号——否则 JS 会把 "0.10" 当数字字面量
    # 解析成 0.1，悄悄丢掉尾随的 0（这正是曾经踩过的坑）。
    return k if _IDENT_RE.match(k) else '"' + k.replace('"', '\\"') + '"'


def _num(v):
    if isinstance(v, float) and v == int(v):
        return f"{v:.1f}"
    return repr(v)


def main():
    if not RAW_ROOT.exists():
        sys.exit(f"找不到 {RAW_ROOT}")
    country_dirs = sorted(p for p in RAW_ROOT.iterdir() if p.is_dir())
    if not country_dirs:
        sys.exit(f"{RAW_ROOT} 下没有国家目录（例如 CN/），先按 _README.md 放好 CSV")

    html_text = HTML_PATH.read_text(encoding="utf-8")
    prev_counts = read_prev_datasets(html_text)

    datasets = {}
    summary_lines = []
    for d in country_dirs:
        code, ds = build_dataset(d)
        run_checks(code, ds, prev_counts.get(code))
        datasets[code] = ds
        old_mu = None
        m = re.search(re.escape(code) + r':\s*\{.*?"mu":\s*([\d.]+)', html_text, re.S)
        if m:
            old_mu = float(m.group(1))
        mu_note = f"mu {old_mu:.0f} → {ds['params']['mu']:.0f}" if old_mu is not None else f"mu = {ds['params']['mu']:.0f}"
        cal50 = ds["calibration"]["map"]["0.50"]
        summary_lines.append(
            f"{code} 更新到 {ds['meta']['updatedTo']}：{mu_note} ｜ 校准 P50 {cal50}"
        )

    block = "const DATASETS = " + to_js(datasets, 0) + ";"
    new_section = DATA_START + "\n" + block + "\n" + DATA_END

    pattern = re.compile(re.escape(DATA_START) + r".*?" + re.escape(DATA_END), re.S)
    if pattern.search(html_text):
        new_html = pattern.sub(lambda _m: new_section, html_text, count=1)
    else:
        sys.exit(
            "HTML 里找不到 DATA:START/DATA:END 标记块——先在 <script> 里手工放一对空标记再跑。"
        )

    HTML_PATH.write_text(new_html, encoding="utf-8")
    print("已写入", HTML_PATH)
    for line in summary_lines:
        print(" -", line)


if __name__ == "__main__":
    main()
