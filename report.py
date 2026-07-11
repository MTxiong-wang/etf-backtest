# -*- coding: utf-8 -*-
"""
HTML 报告生成器：把回测扫描结果渲染成一个**自包含的 HTML 文件**（替代 PNG 热力图）。

相比图片的优势：表格可读、可复制、无字体渲染问题，且品种盈利矩阵可在
「收益率%」与「盈利(万元)」两个视图间一键切换。配色用 A 股红涨惯例
（正/盈利=红，负/亏损=蓝，不用绿色）。
"""

from typing import Dict, List, Tuple


# ------------------------------------------------------------------
# 颜色辅助
# ------------------------------------------------------------------

def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _signed_bg(value, vlim):
    """正→红、负→蓝，透明度按 |value|/vlim 缩放；返回内联 style 片段。"""
    if value is None or not vlim:
        return ""
    a = _clamp(abs(value) / vlim, 0.08, 0.85)
    color = "190,40,40" if value >= 0 else "40,90,190"
    return f"background:rgba({color},{a:.2f});"


def _pos_bg(value, vmax):
    """正值红色渐变（越大越红）。"""
    if value is None or not vmax:
        return ""
    a = _clamp(value / vmax, 0.08, 0.85)
    return f"background:rgba(190,40,40,{a:.2f});"


def _neg_bg(value, vmin):
    """负值蓝色渐变（越接近 vmin 越深）。value、vmin 均为负数。"""
    if value is None or not vmin:
        return ""
    a = _clamp(value / vmin, 0.08, 0.85)
    return f"background:rgba(40,90,190,{a:.2f});"


# ------------------------------------------------------------------
# 主入口
# ------------------------------------------------------------------

def generate_report_html(
    params: Dict,
    strategies: List[Dict],
    per_strategy: Dict[Tuple[str, str, float], Dict],
    name_by_code: Dict[str, str],
    holdings_order: List[str],
    save_path: str,
):
    """
    生成自包含 HTML 报告。

    Args:
        params: ``{start,end,initial_capital,rf,monitor_step,benchmark_name,
            band_ratios,absolute_thresholds}``。
        strategies: 策略总览行列表（含末尾基准行），每项含 portfolio/mode/threshold/
            final/total_return/annualized/max_drawdown/volatility/sharpe/calmar/rebalance_count。
        per_strategy: ``{(portfolio,mode,thr): {code: {profit,value,cost,return_pct}}}``（18 个网格策略）。
        name_by_code: 规范代码 -> 标的短名。
        holdings_order: 标的代码行顺序（17）。
        save_path: HTML 输出路径。
    """
    body = []
    body.append(_html_header(params))
    body.append(_section_overview(strategies))
    body.append(_section_risk(strategies))
    body.append(_section_ranking(strategies))
    body.append(_section_matrix(per_strategy, name_by_code, holdings_order))
    body.append(_section_engines(per_strategy, name_by_code))
    body.append(_html_footer())

    html = "<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>" \
           "<meta name='viewport' content='width=device-width,initial-scale=1'>" \
           f"<title>ETF 组合回测报告</title><style>{_CSS}</style></head><body>" \
           + "\n".join(body) + _JS + "</body></html>"

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 报告已保存至: {save_path}")


# ------------------------------------------------------------------
# 各区块
# ------------------------------------------------------------------

def _html_header(params):
    bench = params.get("benchmark_name", "")
    return f"""
<h1>ETF 组合回测扫描报告</h1>
<div class='params'>
  <span><b>区间</b> {params['start']} ~ {params['end']}</span>
  <span><b>初始资金</b> ¥{params['initial_capital']:,.0f}</span>
  <span><b>无风险利率</b> {params['rf']:.2%}</span>
  <span><b>监控步长</b> {params['monitor_step']}</span>
  <span><b>基准</b> {bench}</span>
  <span><b>阈值网格</b> band {params.get('band_ratios')} / absolute {params.get('absolute_thresholds')}</span>
</div>
<p class='hint'>配色：红=盈利/上涨，蓝=亏损/下跌（A 股红涨惯例）。</p>"""


def _section_overview(strategies):
    rows = [s for s in strategies if s.get("mode") != "buy_hold"]
    vmax_ann = max((r.get("annualized") or 0) for r in rows) or 1
    vmax_sharpe = max((r.get("sharpe") or 0) for r in rows) or 1
    vmin_dd = min((r.get("max_drawdown") or 0) for r in rows) or -1

    out = ["<h2>1. 策略总览</h2>",
           "<div class='wrap'><table>",
           "<thead><tr><th class='name'>组合</th><th>模式</th><th>阈值</th>"
           "<th>期末资产</th><th>总收益</th><th>年化</th><th>最大回撤</th>"
           "<th>波动率</th><th>夏普</th><th>索提诺</th><th>卡玛</th><th>胜率</th><th>调仓</th></tr></thead><tbody>"]

    def is_bench(s):
        return s.get("mode") == "buy_hold"

    for s in strategies:
        out.append("<tr" + (" class='bench'" if is_bench(s) else "") + ">")
        out.append(f"<td class='name'>{s['portfolio']}</td><td>{s['mode']}</td>"
                   f"<td>{s['threshold']}</td>")
        out.append(_cell_money(s.get("final")))
        out.append(_cell_pct(s.get("total_return")))
        out.append(_cell_pct(s.get("annualized"), _pos_bg(s.get("annualized"), vmax_ann)))
        out.append(_cell_pct(s.get("max_drawdown"), _neg_bg(s.get("max_drawdown"), vmin_dd)))
        out.append(_cell_pct(s.get("volatility")))
        out.append(_cell_num(s.get("sharpe"), _pos_bg(s.get("sharpe"), vmax_sharpe), 2))
        out.append(_cell_num(s.get("sortino"), None, 2))
        out.append(_cell_num(s.get("calmar"), None, 2))
        out.append(_cell_pct(s.get("win_rate")))
        out.append(_cell_int(s.get("rebalance_count")))
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def _section_risk(strategies):
    """风险指标小表：日 VaR/CVaR(95%) + 盈亏比。"""
    rows = [s for s in strategies if s.get("mode") != "buy_hold"]
    out = ["<h2>2. 风险指标 <span class='muted'>(日 VaR/CVaR 95%、盈亏比)</span></h2>",
           "<div class='wrap'><table>",
           "<thead><tr><th class='name'>组合</th><th>模式</th><th>阈值</th>"
           "<th>VaR(95%,日)</th><th>CVaR(95%,日)</th><th>盈亏比</th></tr></thead><tbody>"]
    for s in rows:
        out.append("<tr>")
        out.append(f"<td class='name'>{s['portfolio']}</td><td>{s['mode']}</td><td>{s['threshold']}</td>")
        out.append(_cell_pct(s.get("var_95")))
        out.append(_cell_pct(s.get("cvar_95")))
        out.append(_cell_num(s.get("profit_loss_ratio"), None, 2))
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def _section_ranking(strategies):
    rows = [s for s in strategies if s.get("mode") != "buy_hold"]
    by_sharpe = sorted(rows, key=lambda s: s.get("sharpe") or -9e9, reverse=True)[:3]
    by_return = sorted(rows, key=lambda s: s.get("annualized") or -9e9, reverse=True)[:3]

    def block(title, items, metric, fmt):
        cells = "".join(
            f"<tr><td class='name'>{s['portfolio']}</td><td>{s['mode']}</td><td>{s['threshold']}</td>"
            f"<td>{fmt(s.get(metric))}</td><td>夏普{s.get('sharpe'):.2f}</td>"
            f"<td>回撤{s.get('max_drawdown'):.1%}</td><td>调仓{s.get('rebalance_count')}</td></tr>"
            for s in items
        )
        return f"<h4>{title}</h4><table><thead><tr><th class='name'>组合</th><th>模式</th>" \
               f"<th>阈值</th><th>{metric}</th><th></th><th></th><th></th></tr></thead>" \
               f"<tbody>{cells}</tbody></table>"

    out = ["<h2>3. 排名</h2><div class='rank'>"]
    out.append(block("夏普 Top 3", by_sharpe, "annualized", lambda v: f"年化 {v:.2%}"))
    out.append(block("年化 Top 3", by_return, "annualized", lambda v: f"年化 {v:.2%}"))
    out.append("</div>")
    return "\n".join(out)


def _section_matrix(per_strategy, name_by_code, holdings_order):
    strat_keys = list(per_strategy.keys())
    if not strat_keys:
        return "<h2>3. 品种盈利矩阵</h2><p>无数据。</p>"

    def label(p, md, t):
        return f"{p[:3]}|{'b' if md == 'band' else 'a'}{t}"

    strat_labels = [label(*k) for k in strat_keys]

    # 颜色量程（跨所有单元格）
    all_ret = [h["return_pct"] for ph in per_strategy.values() for h in ph.values()]
    all_prof = [h["profit"] for ph in per_strategy.values() for h in ph.values()]
    vlim_ret = max((abs(v) for v in all_ret), default=1) or 1
    vlim_prof = max((abs(v) for v in all_prof), default=1) or 1

    # 分组表头：按 portfolio 合并列
    groups = []
    for j, (p, *_rest) in enumerate(strat_keys):
        if not groups or groups[-1][0] != p:
            groups.append([p, j, j])
        else:
            groups[-1][2] = j
    head1 = "<tr><th class='name' rowspan='2'>标的</th>"
    for p, j0, j1 in groups:
        head1 += f"<th colspan='{j1 - j0 + 1}'>{p}</th>"
    head1 += "</tr>"
    head2 = "<tr>" + "".join(f"<th>{lbl}</th>" for lbl in strat_labels) + "</tr>"

    # 数据行
    body_rows = []
    for ccode in holdings_order:
        name = name_by_code.get(ccode, ccode)
        cells = [f"<tr><th class='rowname'>{name}</th>"]
        for key in strat_keys:
            ph = per_strategy[key]
            h = ph.get(ccode)
            if h is None:
                cells.append("<td class='na'>—</td>")
                continue
            rt = f"{h['return_pct']:.1f}%"
            pr = f"{h['profit'] / 1e4:.1f}"
            rbg = _signed_bg(h["return_pct"], vlim_ret)
            pbg = _signed_bg(h["profit"], vlim_prof)
            cells.append(
                f"<td data-r='{rt}' data-rbg='{rbg}' data-p='{pr}' data-pbg='{pbg}' "
                f"style='{rbg}'>{rt}</td>"
            )
        cells.append("</tr>")
        body_rows.append("".join(cells))

    return (
        "<h2>4. 品种盈利矩阵 <span class='muted'>(行=标的，列=策略)</span></h2>"
        "<div class='toggle'>"
        "<button class='active' data-metric='r'>收益率 %</button>"
        "<button data-metric='p'>盈利 (万元)</button>"
        "</div>"
        "<div class='wrap'><table class='matrix'>"
        f"<thead>{head1}{head2}</thead><tbody>" + "\n".join(body_rows) + "</tbody></table></div>"
    )


def _section_engines(per_strategy, name_by_code):
    """每个组合在 band±0.5（或其首个 band 策略）下的盈利 Top3 + 最大拖累。"""
    by_port = {}
    for (p, md, t), ph in per_strategy.items():
        if md == "band":
            by_port.setdefault(p, []).append((t, ph))

    out = ["<h2>5. 各组合利润发动机 <span class='muted'>(band ±0.5)</span></h2>",
           "<div class='eng'>"]
    for p in sorted(by_port):
        cands = by_port[p]
        # 优先取 band_ratio 最接近 0.5 的
        _, ph = min(cands, key=lambda x: abs(x[0] - 0.5)) if cands else (None, {})
        total = sum(h["profit"] for h in ph.values())
        items = sorted(ph.items(), key=lambda kv: kv[1]["profit"], reverse=True)
        top = items[:3]
        bot = items[-1:]

        def row(kv):
            c, h = kv
            nm = name_by_code.get(c, c)
            share = (h["profit"] / total * 100) if total > 0 else 0
            return (f"<tr><td class='name'>{nm}</td><td>{h['profit'] / 1e4:.1f}</td>"
                    f"<td>{share:.1f}%</td><td>{h['return_pct']:.1f}%</td></tr>")

        out.append(f"<div class='engcard'><h4>{p}　"
                   f"<span class='muted'>总盈利 ¥{total / 1e4:.1f}万</span></h4>"
                   "<table><thead><tr><th class='name'>标的</th><th>盈利(万)</th>"
                   "<th>占比</th><th>收益率</th></tr></thead><tbody>")
        out.extend(row(kv) for kv in top)
        if bot and bot[0] not in top:
            out.append("<tr class='sep'><td colspan='4'>最大拖累</td></tr>")
            out.extend(row(kv) for kv in bot)
        out.append("</tbody></table></div>")
    out.append("</div>")
    return "\n".join(out)


def _html_footer():
    return ("<div class='footer'>盈利 = 期末市值 − 持有成本（已含分红）。"
            "数据源 xalpha（雪球/东方财富）。本报告由 run_sweep.py 自动生成。</div>")


# ------------------------------------------------------------------
# 单元格格式
# ------------------------------------------------------------------

def _cell_money(v, style=""):
    return f"<td style='{style}'>¥{v:,.0f}</td>" if v is not None else "<td>—</td>"


def _cell_pct(v, style=""):
    return f"<td style='{style}'>{v:.2%}</td>" if v is not None else "<td>—</td>"


def _cell_num(v, style="", nd=2):
    return f"<td style='{style}'>{v:.{nd}f}</td>" if v is not None else "<td>—</td>"


def _cell_int(v, style=""):
    return f"<td style='{style}'>{int(v)}</td>" if v is not None else "<td>—</td>"


# ------------------------------------------------------------------
# CSS / JS
# ------------------------------------------------------------------

_CSS = """
body{font-family:"Microsoft YaHei","PingFang SC",Arial,sans-serif;margin:24px;background:#fafafa;color:#222;line-height:1.5}
h1{color:#9b1c1c;border-bottom:3px solid #9b1c1c;padding-bottom:8px;margin-bottom:6px}
h2{color:#9b1c1c;margin-top:34px;border-left:5px solid #9b1c1c;padding-left:10px}
h4{margin:10px 0 4px;color:#333}
.params{background:#fff;border:1px solid #eee;border-radius:6px;padding:12px 16px;display:flex;flex-wrap:wrap;gap:18px;font-size:14px}
.params b{color:#9b1c1c}
.hint{color:#888;font-size:13px;margin:6px 0}
.muted{color:#999;font-weight:normal;font-size:13px}
.wrap{overflow-x:auto;border:1px solid #eee;border-radius:6px;background:#fff}
table{border-collapse:collapse;font-size:13px;white-space:nowrap}
th,td{border:1px solid #e8e8e8;padding:5px 9px;text-align:right}
th{background:#9b1c1c;color:#fff;position:sticky;top:0;z-index:2}
th.name,td.name,th.rowname{text-align:left}
th.rowname{background:#fff3f3;color:#333;position:sticky;left:0;z-index:3;font-weight:600}
td.na{color:#ccc}
tr.bench td{font-style:italic;color:#555}
tbody tr:nth-child(even) td{background-color:#f6f6f6}
tbody tr:nth-child(even) th.rowname{background-color:#f6f6f6}
.rank,.eng{display:flex;flex-wrap:wrap;gap:18px}
.rank table,.engcard table{font-size:13px}
.engcard{background:#fff;border:1px solid #eee;border-radius:6px;padding:10px 14px}
.engcard h4{color:#9b1c1c}
tr.sep td{background:#f0f0f0;color:#888;font-size:12px;text-align:left}
.toggle{margin:8px 0}
.toggle button{background:#eee;border:1px solid #ccc;border-radius:4px;padding:5px 12px;cursor:pointer;margin-right:6px;font-size:13px}
.toggle button.active{background:#9b1c1c;color:#fff;border-color:#9b1c1c}
table.matrix td{font-size:11px;min-width:46px;text-align:center}
.footer{margin-top:30px;color:#aaa;font-size:12px;border-top:1px solid #eee;padding-top:8px}
"""

_JS = """
<script>
document.querySelectorAll('.toggle button').forEach(function(btn){
  btn.addEventListener('click', function(){
    document.querySelectorAll('.toggle button').forEach(function(b){b.classList.remove('active');});
    btn.classList.add('active');
    var m = btn.dataset.metric;
    document.querySelectorAll('table.matrix td[data-r]').forEach(function(td){
      td.textContent = m === 'r' ? td.dataset.r : td.dataset.p;
      td.style.cssText = m === 'r' ? td.dataset.rbg : td.dataset.pbg;
    });
  });
});
</script>
"""
