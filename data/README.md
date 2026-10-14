# 原始数据说明

## 目录结构

```
data/
  CN/   中国籍 R1/R7/R8 原样导出（当前至 2026-09），及旧文件对照基线
  IN/   将来加国家 = 加一个同结构目录，不改代码
```

## 每月更新步骤

1. 去新西兰移民局的 [Immigration New Zealand 数据集页面](https://www.immigration.govt.nz/about-us/research-and-statistics) 下载三份 CSV：
   - **R1** — `R1_Residence_Decisions_by_Application_Substream_and_Decision_Type.csv`
   - **R7** — `R7_Residence_Accepted_by_Application_Substream.csv`
   - **R8** — `R8_Residence_On_Hand_by_Application_Substream.csv`
2. 导出时筛选 **Nationality = China** 并保持三表 **Applicant Type** 相同。按原名覆盖 `CN/` 中的这三份文件，模型只提取 `SMC Skilled Residence`。旧命名的大流文件仅为 2026-08 历史对照，优先级低，不与新文件相加。
3. `cd scripts && python3 build_web_data.py`
4. 打开 HTML，确认「数据更新到 X」变了，且数字合理。

## ⚠️ 必须知道的隐患：CSV 本身看不出是否按国籍筛选过

当前 CSV 的表头只有 `Date / Application Substream / Decision Type / Count`（R1）或
`Date / Application Substream / Count`（R7、R8）——**没有国籍列**。「已按中国国籍筛选」这件事
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

`build_web_data.py` 导出前还会检查：数据数组等长、批准与拒绝之和等于决定量、月份连续无跳月、`pool` 均值 ≈ 1.0、
`0 < lo < 1`、`0 < p_enter < 1`、`mu > 0`、校准映射单调递增、新数据月份数不少于上次。
任一失败都会中止并报错，不会写出半成品 HTML。

加载器还会拒绝 SMC 统计键重复、非月末日期、非法计数、缺月及三表覆盖不一致。无国籍列也意味着不能仅靠 CSV 证明筛选条件；默认人数统计和只含主申请人的申请数也要在导出页面确认。

本次三份文件的历史对照、SHA-256、三表勾稽差额与模型假设见 [2026-09 核验报告](validation_2026-09.md)。9 月差额 126 未被强行修正。官方 R8 可能包含尚未正式受理的递交记录，不能直接要求三个汇总表严格闭合。
