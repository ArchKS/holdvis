import pandas as pd
import numpy as np
import os
import json
import config as cfg

def load_config():
    default_config = {
        "chartConfig": {
            "barWidth": "40%",
            "barGap": "30%",
            "labelFontSize": 12,
            "labelThreshold": 0.04,
            "hideThreshold": 0.01,
            "heightVh": 200,
            "liquidationArrowLength": 120,
            "showLabelDetails": True
        }
    }
    try:
        if hasattr(cfg, 'CHART_CONFIG'):
            for k, v in cfg.CHART_CONFIG.items():
                default_config["chartConfig"][k] = v
    except Exception as e:
        print(f"Error loading config.py: {e}. Using defaults.")
    return default_config

def generate_html():
    config = load_config()
    chart_cfg = config['chartConfig']
    label_threshold = chart_cfg['labelThreshold']
    hide_threshold = chart_cfg.get('hideThreshold', 0.01)
    show_details = chart_cfg.get('showLabelDetails', True)
    
    # Read the CSV file
    try:
        # Use sep=None to detect separator, engine='python'
        df = pd.read_csv('assets.csv', sep=',', skip_blank_lines=True)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # Filter out empty rows or headers repeated
    df = df[df['日期'].notna()]
    df = df[df['日期'] != '日期']
    
    # Identify dates
    dates = df['日期'].unique().tolist()
    
    # Assets dictionary to store data per date
    # { asset_name: { date: { 'val': val, 'qty': qty, 'unit': unit } } }
    asset_data = {}
    asset_market = {}
    
    # Store totals and cash per date
    totals = {}
    cash = {}
    
    for date in dates:
        day_df = df[df['日期'] == date]
        
        # Get individual assets
        assets_df = day_df[day_df['公司名称'].notna() & (day_df['公司名称'] != '汇总')]
        
        day_total_assets = 0
        for _, row in assets_df.iterrows():
            name = row['公司名称']
            market = row['市场']
            try:
                val = float(row['当前(万)'])
            except:
                val = 0.0
            try:
                # Remove commas if any and convert to float
                qty_str = str(row['持有数量']).replace(',', '')
                qty = float(qty_str)
            except:
                qty = 0.0
            try:
                # Parse current price
                price_str = str(row['当前价']).replace(',', '')
                # Extract numeric part
                import re
                price_match = re.search(r'[\d\.]+', price_str)
                price = float(price_match.group()) if price_match else 0.0
            except:
                price = 0.0
                
            unit = val / qty if qty > 0 else 0
            
            if name not in asset_data:
                asset_data[name] = {}
            asset_data[name][date] = {'val': val, 'qty': qty, 'unit': unit, 'price': price, 'price_str': str(row['当前价'])}
            asset_market[name] = market
            day_total_assets += val
            
        # Get summary row
        summary_row = day_df[day_df['市场'] == '汇总']
        if not summary_row.empty:
            try:
                c = float(summary_row.iloc[0]['现金(万)'])
            except:
                c = 0.0
            cash[date] = c
            totals[date] = day_total_assets + c
        else:
            cash[date] = 0.0
            totals[date] = day_total_assets

    # Create the HTML table rows
    all_asset_names = sorted(asset_data.keys(), key=lambda x: (asset_market[x], x))
    table_rows_html = ""
    
    # Find max change to scale the custom bars
    max_change_val = 0.1
    for name in all_asset_names:
        prev_item = None
        for date in dates:
            item = asset_data[name].get(date, {'val': 0.0, 'qty': 0.0, 'unit': 0.0})
            if prev_item is not None:
                if prev_item['qty'] == 0 and item['qty'] > 0:
                    t = item['val']
                    m = 0
                elif item['qty'] == 0 and prev_item['qty'] > 0:
                    t = -prev_item['val']
                    m = 0
                else:
                    t = (item['qty'] - prev_item['qty']) * prev_item['unit']
                    m = item['qty'] * (item['unit'] - prev_item['unit'])
                max_change_val = max(max_change_val, abs(t), abs(m))
            prev_item = item

    for name in all_asset_names:
        market = asset_market[name]
        row_html = f'<tr><td class="market">{market}</td><td class="asset-name">{name}</td>'
        
        prev_item = None
        for date in dates:
            item = asset_data[name].get(date, {'val': 0.0, 'qty': 0.0, 'unit': 0.0, 'price': 0.0, 'price_str': '-'})
            val = item['val']
            qty = item['qty']
            price_str = item['price_str']
            
            content_html = f'<div class="cell-val">{val:.1f}万</div>'
            if qty > 0:
                content_html += f'<div class="cell-sub">数: {qty:g} | 价: {price_str}</div>'
                
            details = ""
            if prev_item is not None:
                prev_val = prev_item['val']
                change = val - prev_val
                
                # Decompose change
                trade_effect = 0
                market_effect = 0
                
                if prev_item['qty'] == 0 and item['qty'] > 0:
                    trade_effect = val
                    market_effect = 0
                elif item['qty'] == 0 and prev_item['qty'] > 0:
                    trade_effect = -prev_val
                    market_effect = 0
                else:
                    trade_effect = (item['qty'] - prev_item['qty']) * prev_item['unit']
                    market_effect = item['qty'] * (item['unit'] - prev_item['unit'])
                
                qty_diff = item['qty'] - prev_item['qty']
                
                # Render custom horizontal bars
                if abs(trade_effect) > 0.01 or abs(market_effect) > 0.01:
                    details += '<div class="custom-bar-container">'
                    
                    if abs(trade_effect) > 0.01:
                        action = "加仓" if trade_effect > 0 else "减仓"
                        width = min(abs(trade_effect) / max_change_val * 100, 100)
                        bg_color = "#c07844" if trade_effect > 0 else "#a43a3a"
                        
                        details += f'''
                        <div class="custom-bar-row">
                            <span class="cb-label">交易</span>
                            <div class="cb-track">
                                <div class="cb-fill {'cb-right' if trade_effect > 0 else 'cb-left'}" style="width: {width}%; background: {bg_color};"></div>
                            </div>
                            <span class="cb-val" style="color: {bg_color}">{trade_effect:+.1f}</span>
                        </div>
                        '''
                        
                    if abs(market_effect) > 0.01:
                        width = min(abs(market_effect) / max_change_val * 100, 100)
                        bg_color = "#4b6a53" if market_effect > 0 else "#667863"
                        
                        details += f'''
                        <div class="custom-bar-row">
                            <span class="cb-label">市场</span>
                            <div class="cb-track">
                                <div class="cb-fill {'cb-right' if market_effect > 0 else 'cb-left'}" style="width: {width}%; background: {bg_color};"></div>
                            </div>
                            <span class="cb-val" style="color: {bg_color}">{market_effect:+.1f}</span>
                        </div>
                        '''
                        
                    details += '</div>'
                
            if details:
                content_html += f'<div class="cell-details">{details}</div>'
                
            row_html += f'<td>{content_html}</td>'
            prev_item = item
        
        row_html += "</tr>"
        table_rows_html += row_html

    # Add Cash row
    cash_row = '<tr><td class="market">-</td><td class="asset-name">现金</td>'
    prev_cash = None
    for date in dates:
        val = cash.get(date, 0.0)
        content_html = f'<div class="cell-val">{val:.1f}万</div>'
        
        details = ""
        if prev_cash is not None:
            change = val - prev_cash
            if abs(change) > 0.01:
                cls = "positive" if change > 0 else "negative"
                details += f'<div class="cell-action {cls}">[变动] {change:+.1f}万</div>'
        
        if details:
            content_html += f'<div class="cell-details">{details}</div>'
            
        cash_row += f'<td>{content_html}</td>'
        prev_cash = val
    cash_row += "</tr>"
    table_rows_html += cash_row

    # Add Total row
    total_row_html = '<tr class="total-row"><td class="market">汇总</td><td class="asset-name">总资产</td>'
    prev_total = None
    for date in dates:
        val = totals.get(date, 0.0)
        content_html = f'<div class="cell-val">{val:.1f}万</div>'
        
        details = ""
        if prev_total is not None:
            change = val - prev_total
            if abs(change) > 0.01:
                cls = "positive" if change > 0 else "negative"
                details += f'<div class="cell-action {cls}">[变动] {change:+.1f}万</div>'
                
        if details:
            content_html += f'<div class="cell-details">{details}</div>'
            
        total_row_html += f'<td>{content_html}</td>'
        prev_total = val
    total_row_html += "</tr>"
    table_rows_html += total_row_html

    # Header with dates
    header_html = '<tr><th>市场</th><th>资产名称</th>'
    for date in dates:
        header_html += f'<th class="date-header">{date}</th>'
    header_html += '</tr>'

    # Latest structure
    latest_date = dates[-1]
    latest_df = df[df['日期'] == latest_date]
    latest_assets = latest_df[latest_df['公司名称'].notna() & (latest_df['公司名称'] != '汇总')]
    
    market_dist = {}
    asset_dist = []
    
    total_val = totals[latest_date]
    
    for _, row in latest_assets.iterrows():
        name = row['公司名称']
        market = row['市场']
        try:
            val = float(row['当前(万)'])
        except:
            val = 0.0
        
        market_dist[market] = market_dist.get(market, 0.0) + val
        asset_dist.append((name, val))
    
    # Add cash to market dist
    c = cash.get(latest_date, 0.0)
    if c > 0:
        market_dist['现金'] = c
    
    market_dist_html = "<ul>"
    for m, v in sorted(market_dist.items(), key=lambda x: x[1], reverse=True):
        percent = (v / total_val * 100) if total_val > 0 else 0
        market_dist_html += f'<li>{m}: {v:.1f}万 ({percent:.1f}%)</li>'
    market_dist_html += "</ul>"
    
    asset_dist_html = "<ul>"
    for n, v in sorted(asset_dist, key=lambda x: x[1], reverse=True):
        percent = (v / total_val * 100) if total_val > 0 else 0
        asset_dist_html += f'<li>{n}: {v:.1f}万 ({percent:.1f}%)</li>'
    # Add cash to asset list html
    if c > 0:
        percent = (c / total_val * 100) if total_val > 0 else 0
        asset_dist_html += f'<li>现金: {c:.1f}万 ({percent:.1f}%)</li>'
    asset_dist_html += "</ul>"

    # Prepare data for charts
    chart_dates = dates
    chart_totals = [round(totals[d], 1) for d in dates]
    
    # Decomposed changes
    trade_contributions = [0]
    market_contributions = [0]
    
    for i in range(1, len(dates)):
        d1 = dates[i-1]
        d2 = dates[i]
        
        step_trade = 0
        step_market = 0
        
        # Cash change is always trading
        step_trade += cash.get(d2, 0) - cash.get(d1, 0)
        
        for name in all_asset_names:
            prev = asset_data[name].get(d1, {'val': 0.0, 'qty': 0.0, 'unit': 0.0})
            curr = asset_data[name].get(d2, {'val': 0.0, 'qty': 0.0, 'unit': 0.0})
            
            if prev['qty'] == 0 and curr['qty'] > 0:
                step_trade += curr['val']
            elif curr['qty'] == 0 and prev['qty'] > 0:
                step_trade -= prev['val']
            else:
                step_trade += (curr['qty'] - prev['qty']) * prev['unit']
                step_market += curr['qty'] * (curr['unit'] - prev['unit'])
        
        trade_contributions.append(round(step_trade, 1))
        market_contributions.append(round(step_market, 1))

    # Market data (latest)
    chart_market_data = []
    for m, v in sorted(market_dist.items(), key=lambda x: x[1], reverse=True):
        if v > 0:
            chart_market_data.append({"name": m, "value": round(v, 1)})
            
    chart_asset_data = []
    for n, v in sorted(asset_dist, key=lambda x: x[1], reverse=True):
        if v > 0:
            chart_asset_data.append({"name": n, "value": round(v, 1)})
            
    latest_cash = cash.get(latest_date, 0.0)
    if latest_cash > 0:
        chart_asset_data.append({"name": "现金", "value": round(latest_cash, 1)})
        chart_asset_data = sorted(chart_asset_data, key=lambda x: x['value'], reverse=True)
    
    # Prepare Stacked Bar Data (Top Assets over time)
    stacked_series = []
    # Sort names by average value to put largest on bottom
    avg_vals = {name: sum(asset_data[name].get(d, {}).get('val', 0) for d in dates)/len(dates) for name in all_asset_names}
    sorted_for_stack = sorted(all_asset_names, key=lambda x: avg_vals[x], reverse=True)
    
    arrow_data = []
    for name in sorted_for_stack:
        for i in range(1, len(dates)):
            d1 = dates[i-1]
            d2 = dates[i]
            prev = asset_data[name].get(d1, {'val': 0.0, 'qty': 0.0, 'unit': 0.0})
            curr = asset_data[name].get(d2, {'val': 0.0, 'qty': 0.0, 'unit': 0.0})
            qty_diff = curr['qty'] - prev['qty']
            
            # Open position, Liquidation, or Normal change
            if prev['qty'] == 0 and curr['qty'] > 0:
                arrow_data.append({
                    "name": name,
                    "d1": d1,
                    "d2": d2,
                    "qty_diff": curr['qty'],
                    "trade_val": curr['val'],
                    "is_new": True,
                    "is_liquidation": False
                })
            elif curr['qty'] == 0 and prev['qty'] > 0:
                arrow_data.append({
                    "name": name,
                    "d1": d1,
                    "d2": d2,
                    "qty_diff": -prev['qty'],
                    "trade_val": -prev['val'],
                    "is_new": False,
                    "is_liquidation": True
                })
            elif qty_diff != 0 and prev['val'] > 0 and curr['val'] > 0:
                trade_val = qty_diff * prev['unit']
                arrow_data.append({
                    "name": name,
                    "d1": d1,
                    "d2": d2,
                    "qty_diff": qty_diff,
                    "trade_val": trade_val,
                    "is_new": False,
                    "is_liquidation": False
                })
                
    for name in sorted_for_stack:
        data_over_time = []
        prev_qty = 0
        for d in dates:
            val = round(asset_data[name].get(d, {}).get('val', 0), 1)
            qty = asset_data[name].get(d, {}).get('qty', 0)
            total_day = totals.get(d, 0)
            ratio = val / total_day if total_day > 0 else 0
            
            is_new = bool(prev_qty == 0 and qty > 0)
            prev_qty = qty
            
            # Hide items < threshold by using None
            data_over_time.append({"value": val if ratio >= hide_threshold else None, "qty": qty, "ratio": ratio, "is_new": is_new})
            
        if any(item["value"] is not None for item in data_over_time):
            stacked_series.append({
                "name": name,
                "type": "bar",
                "stack": "Total",
                "emphasis": {"focus": "series"},
                "label": {
                    "show": True,
                    "rich": {
                        "qty": {
                            "fontSize": 11,
                            "color": "#eee"
                        }
                    }
                },
                "data": data_over_time
            })
            
    # Add Cash to stacked
    cash_over_time = []
    for d in dates:
        val = round(cash.get(d, 0.0), 1)
        total_day = totals.get(d, 0)
        ratio = val / total_day if total_day > 0 else 0
        cash_over_time.append({"value": val if ratio >= hide_threshold else None, "qty": 0, "ratio": ratio, "is_new": False})
        
    stacked_series.append({
        "name": "现金",
        "type": "bar",
        "stack": "Total",
        "emphasis": {"focus": "series"},
        "label": {
            "show": True
        },
        "data": cash_over_time
    })

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>投资组合可视化 - 雕版风</title>
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;900&display=swap');
            body {{ font-family: 'Noto Serif SC', serif; padding: 40px 20px; background-color: #f4eee1; color: #2c251d; background-image: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0IiBoZWlnaHQ9IjQiPjxyZWN0IHdpZHRoPSI0IiBoZWlnaHQ9IjQiIGZpbGw9IiNmNGVlZTEiLz48cmVjdCB3aWR0aD0iMSIgaGVpZ2h0PSIxIiBmaWxsPSJyZ2JhKDAsMCwwLDAuMDUpIi8+PC9zdmc+'); }}
            .container {{ max-width: 1400px; margin: 0 auto; background: #fffcf5; padding: 40px; border-radius: 4px; box-shadow: inset 0 0 10px rgba(0,0,0,0.05), 0 4px 15px rgba(0,0,0,0.08); border: 2px solid #8c7355; position: relative; }}
            .container::before {{ content: ""; position: absolute; top: 6px; left: 6px; right: 6px; bottom: 6px; border: 1px solid #d4c2a5; pointer-events: none; }}
            h2, h3 {{ color: #8c2620; font-weight: 900; text-align: center; border-bottom: 2px solid #8c2620; padding-bottom: 10px; margin-bottom: 30px; letter-spacing: 2px; }}
            h3 {{ color: #3b3126; border-bottom: 1px solid #8c7355; margin-top: 50px; font-size: 1.4em; }}
            .chart-row {{ display: flex; flex-wrap: wrap; gap: 30px; margin-bottom: 40px; }}
            .chart-container {{ flex: 1; min-width: 350px; height: 400px; background: transparent; padding: 0; }}
            .full-width-chart {{ width: 100%; height: {chart_cfg['heightVh']}vh; margin-bottom: 40px; background: transparent; padding: 0; box-sizing: border-box; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; font-size: 0.95em; border: 2px solid #3b3126; }}
            th, td {{ border: 1px solid #8c7355; padding: 15px 12px; text-align: left; vertical-align: top; }}
            th {{ background-color: #ede4d3; text-align: center; font-weight: 900; position: sticky; top: 0; z-index: 10; color: #8c2620; border-bottom: 2px solid #3b3126; }}
            .asset-name {{ font-weight: 900; background-color: #f7f1e3; white-space: nowrap; color: #3b3126; border-right: 2px solid #8c7355; }}
            .market {{ text-align: center; font-size: 0.9em; color: #8c2620; width: 40px; font-weight: 600; }}
            .positive {{ color: #a43a3a; font-weight: bold; }}
            .negative {{ color: #4b6a53; font-weight: bold; }}
            .total-row {{ font-weight: 900; background-color: #ede4d3; border-top: 2px solid #3b3126; color: #8c2620; }}
            .date-header {{ min-width: 240px; font-family: monospace; font-size: 1.1em; }}
            .cell-val {{ font-size: 1.2em; font-weight: 900; margin-bottom: 6px; text-align: right; color: #1a1611; }}
            .cell-sub {{ font-size: 0.85em; color: #5c4e3e; margin-bottom: 8px; text-align: right; border-bottom: 1px dashed #c2ab8c; padding-bottom: 6px; }}
            .cell-details {{ margin-top: 8px; }}
            .custom-bar-container {{ width: 100%; font-size: 0.8em; margin-top: 10px; }}
            .custom-bar-row {{ display: flex; align-items: center; margin-bottom: 6px; height: 16px; }}
            .cb-label {{ width: 32px; color: #5c4e3e; flex-shrink: 0; font-weight: 600; }}
            .cb-track {{ flex: 1; height: 8px; background: #e3d9c6; margin: 0 6px; display: flex; position: relative; border: 1px solid #bba382; }}
            .cb-fill {{ height: 100%; }}
            .cb-left {{ position: absolute; right: 50%; }}
            .cb-right {{ position: absolute; left: 50%; }}
            .cb-track::after {{ content: ''; position: absolute; left: 50%; top: -3px; bottom: -3px; width: 1px; background: #3b3126; }}
            .cb-val {{ width: 40px; text-align: right; font-weight: 900; flex-shrink: 0; }}
            .summary-info {{ display: flex; gap: 60px; margin-top: 30px; font-size: 1.1em; }}
            .summary-item ul {{ list-style: none; padding-left: 0; }}
            .summary-item li {{ margin-bottom: 12px; border-bottom: 1px dashed #d4c2a5; padding-bottom: 6px; display: flex; justify-content: space-between; }}
            /* Hide ECharts default loading/border */
            canvas {{ outline: none; }}
        </style>
    </head>
    <body>
    <div class="container">
        <h2>投资组合调仓展示 (当前总市值: {total_val:.1f}万)</h2>
        
        <div id="stackChart" class="full-width-chart"></div>
        
        <div class="chart-row">
            <div id="trendChart" class="chart-container"></div>
            <div id="stepChart" class="chart-container"></div>
        </div>

        <div class="chart-row">
            <div id="marketChart" class="chart-container"></div>
            <div id="assetChart" class="chart-container"></div>
        </div>

        <h3>调仓历史明细 (多维度拆解)</h3>
        <div style="overflow-x: auto; max-height: 800px;">
            <table>
                <thead>
                    {header_html}
                </thead>
                <tbody>
                    {table_rows_html}
                </tbody>
            </table>
        </div>
        
        <h3>持仓结构明细 ({latest_date})</h3>
        <div class="summary-info">
            <div class="summary-item">
                <h4>市场分布</h4>
                {market_dist_html}
            </div>
            <div class="summary-item">
                <h4>持仓资产</h4>
                {asset_dist_html}
            </div>
        </div>
    </div>

    <script>
        // Data from Python
        const dates = {json.dumps(chart_dates)};
        const totals = {json.dumps(chart_totals)};
        const trades = {json.dumps(trade_contributions)};
        const marketFlucts = {json.dumps(market_contributions)};
        const marketData = {json.dumps(chart_market_data)};
        const assetData = {json.dumps(chart_asset_data)};
        const stackedSeries = {json.dumps(stacked_series)};
        const arrowData = {json.dumps(arrow_data)};
        const arrowLength = {chart_cfg.get('liquidationArrowLength', 120)};
        const showDetails = {'true' if show_details else 'false'};

        let yCenters = {{}};
        dates.forEach((d, dIdx) => {{
            let currentY = 0;
            stackedSeries.forEach(s => {{
                if (!yCenters[s.name]) yCenters[s.name] = {{}};
                let item = s.data[dIdx];
                let val = item && item.value ? item.value : 0;
                if (val > 0) {{
                    yCenters[s.name][d] = currentY + val / 2;
                    currentY += val;
                }}
            }});
        }});

        // 1. Initial Render without markLines
        const stackChart = echarts.init(document.getElementById('stackChart'));
        
        let stackOption = {{
            title: {{ text: '各标的市值随时间的长期变化 (堆积柱状图)', left: 'center', textStyle: {{ color: '#8c2620', fontSize: 20 }} }},
            tooltip: {{ 
                trigger: 'item',
                backgroundColor: 'rgba(59, 49, 38, 0.9)',
                borderColor: '#d4c2a5',
                textStyle: {{ color: '#fffcf5' }},
                formatter: function (params) {{
                    if (!params.data || !params.data.value) return '';
                    let qtyStr = params.data.qty ? '<br/>持股: ' + params.data.qty : '';
                    let ratioStr = params.data.ratio ? '<br/>占比: ' + (params.data.ratio * 100).toFixed(1) + '%' : '';
                    return params.seriesName + '<br/>市值: ' + params.data.value + '万' + qtyStr + ratioStr;
                }}
            }},
            legend: {{ top: 35, type: 'scroll', textStyle: {{ color: '#3b3126', fontWeight: 600 }} }},
            grid: {{ left: '3%', right: '4%', bottom: '10%', containLabel: true }},
            dataZoom: [
                {{
                    type: 'slider',
                    show: true,
                    xAxisIndex: [0],
                    start: 0,
                    end: 100, // Default show all, user can zoom
                    bottom: 15,
                    borderColor: '#8c7355',
                    fillerColor: 'rgba(140, 38, 32, 0.2)',
                    textStyle: {{ color: '#3b3126' }}
                }},
                {{
                    type: 'inside',
                    xAxisIndex: [0],
                    start: 0,
                    end: 100
                }}
            ],
            xAxis: [{{ type: 'category', data: dates, axisLine: {{ lineStyle: {{ color: '#8c7355', width: 2 }} }}, axisLabel: {{ color: '#3b3126', fontWeight: 600 }} }}],
            yAxis: [{{ type: 'value', name: '市值 (万)', nameTextStyle: {{ color: '#3b3126', fontWeight: 600 }}, axisLine: {{ show: true, lineStyle: {{ color: '#8c7355', width: 2 }} }}, splitLine: {{ lineStyle: {{ type: 'dashed', color: '#d4c2a5' }} }}, axisLabel: {{ color: '#3b3126', fontWeight: 600 }} }}],
            color: ['#8c2620', '#4b6a53', '#c07844', '#5c4e3e', '#8c7355', '#3b3126', '#a43a3a', '#667863', '#d4c2a5', '#e3d9c6'],
            series: stackedSeries.map(s => {{
                s.barWidth = '{chart_cfg['barWidth']}';
                s.barGap = '{chart_cfg['barGap']}';
                
                s.data = s.data.map(item => {{
                    if (item) {{
                        return {{
                            ...item,
                            itemStyle: {{ borderColor: '#fffcf5', borderWidth: 1 }}
                        }};
                    }}
                    return item;
                }});

                if (s.name !== "现金") {{
                    s.label.formatter = function(params) {{
                        if (!params.data || !params.data.value) return '';
                        let ratio = (params.data.ratio * 100).toFixed(1) + '%';
                        if (params.data.ratio < {label_threshold}) return params.seriesName;
                        if (!showDetails) return params.seriesName + ' (' + ratio + ')';
                        let qty = params.data.qty;
                        return params.seriesName + ' (' + ratio + ')\\n' + params.data.value + '万 | ' + qty + '股';
                    }};
                    s.label.rich = {{}};
                    s.label.fontSize = {chart_cfg['labelFontSize']};
                }} else {{
                    s.label.formatter = function(params) {{
                        if (!params.data || !params.data.value) return '';
                        let ratio = (params.data.ratio * 100).toFixed(1) + '%';
                        if (params.data.ratio < {label_threshold}) return params.seriesName;
                        if (!showDetails) return params.seriesName + ' (' + ratio + ')';
                        return params.seriesName + ' (' + ratio + ')\\n' + params.data.value + '万';
                    }};
                    s.label.fontSize = {chart_cfg['labelFontSize']};
                }}
                return s;
            }})
        }};
        
        // 2. Add MarkLines right into stackOption
        let markLineData = [];
        let markPointData = [];
        // SVG path for a blocky arrow pointing right, colored dynamically
        const rightArrowPath = 'path://M0,4 L12,4 L12,0 L24,8 L12,16 L12,12 L0,12 Z';

        arrowData.forEach(arr => {{
            let d1Index = dates.indexOf(arr.d1);
            let d2Index = dates.indexOf(arr.d2);
            let y1 = yCenters[arr.name] && yCenters[arr.name][arr.d1];
            let y2 = yCenters[arr.name] && yCenters[arr.name][arr.d2];

            if (arr.is_new) {{
                // Point from left edge into the bar
                if (y2 !== undefined) {{
                    markPointData.push({{
                        coord: [d2Index, y2],
                        symbol: rightArrowPath,
                        symbolSize: [36, 20],
                        symbolOffset: [-45, 0], // offset left
                        itemStyle: {{ color: '#a43a3a' }},
                        label: {{
                            show: true,
                            position: 'top',
                            formatter: '建',
                            color: '#a43a3a',
                            fontSize: 18,
                            fontWeight: 'bold',
                            distance: 2
                        }}
                    }});
                }}
            }} else if (arr.is_liquidation) {{
                // Point from the right edge out of the d1 bar
                if (y1 !== undefined) {{
                    markPointData.push({{
                        coord: [d1Index, y1],
                        symbol: rightArrowPath,
                        symbolSize: [36, 20],
                        symbolOffset: [45, 0], // offset right
                        itemStyle: {{ color: '#a43a3a' }},
                        label: {{
                            show: true,
                            position: 'top',
                            formatter: '清',
                            color: '#a43a3a',
                            fontSize: 18,
                            fontWeight: 'bold',
                            distance: 2
                        }}
                    }});
                }}
            }} else {{
                // Normal add / reduce -> dashed line
                if (y1 !== undefined && y2 !== undefined) {{
                    let d2Val = arr.d2;
                    let y2Val = y2;
                    let labelPos = 'middle';

                    let action = arr.qty_diff > 0 ? "加仓" : "减仓";
                    let tradeValStr = (arr.trade_val > 0 ? "+" : "") + arr.trade_val.toFixed(1) + "万";
                    let labelText = action + " " + Math.abs(arr.qty_diff) + "股\\n" + tradeValStr;
                    
                    let lineColor = arr.qty_diff > 0 ? "#a43a3a" : "#4b6a53";
                    let bgColor = "rgba(255, 252, 245, 0.95)";
                    let textColor = lineColor;
                    let borderColor = lineColor;
                    
                    markLineData.push([
                        {{
                            coord: [arr.d1, y1],
                            lineStyle: {{ color: lineColor, width: 2, type: 'dashed' }}
                        }},
                        {{
                            coord: [d2Val, y2Val],
                            value: labelText,
                            label: {{ 
                                show: true, 
                                position: labelPos, 
                                formatter: '{{c}}', 
                                backgroundColor: bgColor, 
                                borderColor: borderColor,
                                borderWidth: 1,
                                padding: [4, 6], 
                                borderRadius: 4, 
                                color: textColor,
                                fontWeight: 'bold',
                                fontSize: 12,
                                lineHeight: 16
                            }}
                        }}
                    ]);
                }}
            }}
        }});

        if (markLineData.length > 0 && stackedSeries.length > 0) {{
            stackOption.series[0].markLine = {{
                symbol: ['none', 'arrow'],
                symbolSize: [10, 15],
                animation: true,
                data: markLineData
            }};
        }}
        
        if (markPointData.length > 0 && stackedSeries.length > 0) {{
            stackOption.series[0].markPoint = {{
                data: markPointData,
                animation: true
            }};
        }}

        stackChart.setOption(stackOption);

        const trendChart = echarts.init(document.getElementById('trendChart'));
        trendChart.setOption({{
            title: {{ text: '资产总值变化', left: 'center', textStyle: {{ color: '#8c2620' }} }},
            tooltip: {{ trigger: 'axis' }},
            xAxis: {{ type: 'category', data: dates, axisLine: {{ lineStyle: {{ color: '#8c7355' }} }} }},
            yAxis: {{ type: 'value', name: '万', axisLine: {{ lineStyle: {{ color: '#8c7355' }} }}, splitLine: {{ lineStyle: {{ type: 'dashed', color: '#d4c2a5' }} }} }},
            series: [{{
                data: totals,
                type: 'line',
                smooth: true,
                areaStyle: {{ opacity: 0.1, color: '#8c2620' }},
                label: {{ show: true, position: 'top', color: '#3b3126' }},
                lineStyle: {{ width: 3, color: '#8c2620' }},
                itemStyle: {{ color: '#8c2620' }}
            }}]
        }});

        // Step Change Chart (Stacked)
        const stepChart = echarts.init(document.getElementById('stepChart'));
        stepChart.setOption({{
            title: {{ text: '调仓效果拆解', left: 'center', textStyle: {{ color: '#8c2620' }} }},
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
            legend: {{ bottom: '0', textStyle: {{ color: '#3b3126' }} }},
            xAxis: {{ type: 'category', data: dates, axisLine: {{ lineStyle: {{ color: '#8c7355' }} }} }},
            yAxis: {{ type: 'value', name: '万', axisLine: {{ lineStyle: {{ color: '#8c7355' }} }}, splitLine: {{ lineStyle: {{ type: 'dashed', color: '#d4c2a5' }} }} }},
            series: [
                {{
                    name: '交易变动(调仓/买卖)',
                    type: 'bar',
                    stack: 'total',
                    data: trades,
                    itemStyle: {{ color: '#c07844' }}
                }},
                {{
                    name: '市场损益(股价变动)',
                    type: 'bar',
                    stack: 'total',
                    data: marketFlucts,
                    itemStyle: {{ color: (p) => p.value >= 0 ? '#4b6a53' : '#667863' }}
                }}
            ]
        }});

        // Market Pie Chart
        const marketChart = echarts.init(document.getElementById('marketChart'));
        marketChart.setOption({{
            title: {{ text: '市场分布', left: 'center', textStyle: {{ color: '#8c2620' }} }},
            tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}万 ({{d}}%)' }},
            legend: {{ bottom: '0', textStyle: {{ color: '#3b3126' }} }},
            series: [{{
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: false,
                itemStyle: {{ borderRadius: 10, borderColor: '#fffcf5', borderWidth: 2 }},
                label: {{ show: false, position: 'center' }},
                emphasis: {{ label: {{ show: true, fontSize: 16, fontWeight: 'bold', color: '#3b3126' }} }},
                data: marketData
            }}]
        }});

        // Asset Pie Chart
        const assetChart = echarts.init(document.getElementById('assetChart'));
        assetChart.setOption({{
            title: {{ text: '资产持仓占比', left: 'center', textStyle: {{ color: '#8c2620' }} }},
            tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}万 ({{d}}%)' }},
            legend: {{ bottom: '0', type: 'scroll', textStyle: {{ color: '#3b3126' }} }},
            series: [{{
                type: 'pie',
                radius: '70%',
                data: assetData,
                itemStyle: {{ borderColor: '#fffcf5', borderWidth: 1 }},
                emphasis: {{ itemStyle: {{ shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' }} }}
            }}]
        }});

        window.addEventListener('resize', () => {{
            stackChart.resize();
            trendChart.resize();
            stepChart.resize();
            marketChart.resize();
            assetChart.resize();
        }});
    </script>
    </body>
    </html>
    """
    
    with open('portfolio_visualization.html', 'w', encoding='utf-8') as f:
        f.write(full_html)
    print("Successfully generated portfolio_visualization.html")

if __name__ == "__main__":
    generate_html()
