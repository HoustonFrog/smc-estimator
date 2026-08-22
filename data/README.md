# 原始数据说明

## 目录结构

```
data/
  CN/   中国籍申请人的 R1/R7/R8 三份月度统计
  IN/   将来加国家 = 加一个同结构目录，不改代码
```

## 每月更新步骤

1. 去新西兰移民局的 [Immigration New Zealand 数据集页面](https://www.immigration.govt.nz/about-us/research-and-statistics) 下载三份 CSV：
   - **R1** — Residence Decisions by Decision Type and Application Substream
   - **R7** — Residence Accepted by Application Stream
   - **R8** — Residence On Hand by Application Stream
2. 导出时筛选 **Nationality = China**，覆盖写入 `CN/` 目录下的同名文件。
3. `cd scripts && python3 build_web_data.py`
4. 打开 index.html，确认「数据更新到 X」变了，且数字合理。

## ⚠️ 必须知道的隐患：CSV 本身看不出是否按国籍筛选过

这三份 CSV 的表头只有 `Date / Decision Type / Application Substream / Count`（R1）或
`Date / Application Stream / Count`（R7、R8）——**没有国籍列**。「已按中国国籍筛选」这件事
完全发生在移民局网站导出页面上，导出完成后的文件里没有任何字段能证明这一点。

也就是说：如果将来重新下载时忘记勾选国籍筛选，`build_web_data.py` **不会因为「缺字段」
而报错**——它会正常读到一份全口径（所有国籍）的数据，安静地算出一套错误但格式完全合法的
参数，页面照常渲染，只是所有答案都不对。

已经做的两道防线：

1. **目录名 `CN/` 本身承担这个信息**——这也是把 `data/` 按国家分目录、而不是拿
   文件名区分的第二个理由。
2. **`build_web_data.py` 的自检里有一条粗判**：新数据某个月的 dec/acc/oh 只要比上个月跳变
   超过 3 倍，就会中止并报错（漏加国籍筛选通常会让数量级跳变好几倍，因为全国数据比单一国
   籍的数据大得多）。这条检查能兜住「完全忘记筛选」的情况，但兜不住「筛选到了另一个跟中国
   量级接近的国家」——所以下载时仍然要肉眼确认页面上的筛选条件是 China，不要只依赖自检。

## 其他自检

`build_web_data.py` 导出前还会检查：4 个数组等长、月份连续无跳月、`pool` 均值 ≈ 1.0、
`0 < lo < 1`、`0 < p_enter < 1`、`mu > 0`、校准映射单调递增、新数据月份数不少于上次。
任一失败都会中止并报错，不会写出半成品 HTML。
