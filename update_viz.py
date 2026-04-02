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
            "showLabelDetails": True,
            "defaultVisibleBars": 6
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
    default_visible_bars = chart_cfg.get('defaultVisibleBars', 6)
    
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
    day_snapshots = {}
    
    for date in dates:
        day_df = df[df['日期'] == date]
        # Keep relevant columns for snapshots
        snapshot_cols = ['市场', '公司名称', '当前价', '盈亏%', '持有数量', '当前(万)', '现金(万)', '收益(万)', '收益率(%)']
        # Check which of these exist in df
        actual_cols = [c for c in snapshot_cols if c in day_df.columns]
        day_snapshots[date] = day_df[actual_cols].fillna('').to_dict('records')

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

    # Latest structure
    all_asset_names = sorted(asset_data.keys(), key=lambda x: (asset_market[x], x))
    latest_date = dates[-1]
    latest_df = df[df['日期'] == latest_date]
    latest_assets = latest_df[latest_df['公司名称'].notna() & (latest_df['公司名称'] != '汇总')]
    
    market_dist = {}
    market_to_assets = {}
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
        if market not in market_to_assets:
            market_to_assets[market] = []
        market_to_assets[market].append({"name": name, "value": val})
        asset_dist.append((name, val))
    
    # Add cash to market dist
    c = cash.get(latest_date, 0.0)
    if c > 0:
        market_dist['现金'] = c
        market_to_assets['现金'] = [{"name": "现金", "value": c}]
    
    # Calculate detailed assets for each market
    chart_market_details = {}
    for market, assets in market_to_assets.items():
        m_total = market_dist[market]
        detailed_assets = []
        for a in sorted(assets, key=lambda x: x['value'], reverse=True):
            if a['value'] > 0:
                p = (a['value'] / m_total * 100) if m_total > 0 else 0
                detailed_assets.append({
                    "name": a['name'],
                    "value": round(a['value'], 1),
                    "percent": round(p, 1)
                })
        chart_market_details[market] = detailed_assets

    # Prepare data for charts
    chart_dates = dates
    chart_totals = [round(totals[d], 1) for d in dates]
    
    # Decomposed changes
    trade_contributions = [0]
    market_contributions = [0]
    rebalance_info = {} # { date: { efficiency: 0, turnover: 0, trade_vol: 0 } }
    
    for i in range(1, len(dates)):
        d1 = dates[i-1]
        d2 = dates[i]
        
        step_trade = 0
        step_market = 0
        trade_vol = 0
        
        # Cash change is always trading
        cash_diff = cash.get(d2, 0) - cash.get(d1, 0)
        step_trade += cash_diff
        trade_vol += abs(cash_diff)
        
        # Hypo value: what if we didn't trade? (Sum of prev_qty * curr_price + prev_cash)
        hypo_val = cash.get(d1, 0)
        
        for name in all_asset_names:
            prev = asset_data[name].get(d1, {'val': 0.0, 'qty': 0.0, 'unit': 0.0})
            curr = asset_data[name].get(d2, {'val': 0.0, 'qty': 0.0, 'unit': 0.0})
            
            qty_diff = curr['qty'] - prev['qty']
            hypo_val += prev['qty'] * curr['unit']
            
            if prev['qty'] == 0 and curr['qty'] > 0:
                step_trade += curr['val']
                trade_vol += abs(curr['val'])
            elif curr['qty'] == 0 and prev['qty'] > 0:
                step_trade -= prev['val']
                trade_vol += abs(prev['val'])
            else:
                t_val = qty_diff * prev['unit']
                step_trade += t_val
                step_market += curr['qty'] * (curr['unit'] - prev['unit'])
                trade_vol += abs(t_val)
        
        trade_contributions.append(round(step_trade, 1))
        market_contributions.append(round(step_market, 1))
        
        # Efficiency = Actual Total - Hypothetical Total
        eff = totals[d2] - hypo_val
        turn = (trade_vol / totals[d1] * 100) if totals[d1] > 0 else 0
        
        rebalance_info[d2] = {
            "prev_date": d1,
            "efficiency": round(eff, 2),
            "turnover": round(turn, 1),
            "trade_vol": round(trade_vol, 2)
        }

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
    
    # Prepare Stacked Bar Data (Per-bar sorting: Largest at the bottom)
    # We create series by "Rank" (Rank 1 is bottom, Rank 2 is next...)
    # This allows each bar to be sorted independently.
    
    # Prepare Stacked Bar Data (One series per asset - Fixed order)
    color_palette = ['#8c2620', '#4b6a53', '#c07844', '#5c4e3e', '#8c7355', '#3b3126', '#a43a3a', '#667863', '#d4c2a5', '#e3d9c6']
    name_to_color = {}
    for i, name in enumerate(all_asset_names + ['现金']):
        name_to_color[name] = color_palette[i % len(color_palette)]

    stacked_series = []
    for name in all_asset_names + ['现金']:
        data_for_asset = []
        for d in dates:
            if name == '现金':
                val = cash.get(d, 0.0)
                qty = 0
            else:
                info = asset_data.get(name, {}).get(d, {})
                val = info.get('val', 0.0)
                qty = info.get('qty', 0)
            
            if val > 0:
                data_for_asset.append({
                    "name": name,
                    "value": round(val, 1),
                    "qty": qty,
                    "ratio": val / totals[d] if totals[d] > 0 else 0,
                    "itemStyle": {"color": name_to_color[name], "borderColor": "#fffcf5", "borderWidth": 1}
                })
            else:
                data_for_asset.append({"value": None})
        
        stacked_series.append({
            "name": name,
            "type": "bar",
            "stack": "Total",
            "emphasis": {"focus": "series"},
            "label": {"show": True},
            "data": data_for_asset
        })

    arrow_data = []
    # Use the names from asset_data for arrow calculations
    for name in all_asset_names:
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

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>投资组合可视化 - 雕版风</title>
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;900&display=swap');
            body {{ font-family: 'Noto Serif SC', serif; padding: 40px 20px; background-color: #fbfaf7; color: #2c251d; background-image: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0IiBoZWlnaHQ9IjQiPjxyZWN0IHdpZHRoPSI0IiBoZWlnaHQ9IjQiIGZpbGw9IiNmYmZhZjciLz48cmVjdCB3aWR0aD0iMSIgaGVpZ2h0PSIxIiBmaWxsPSJyZ2JhKDAsMCwwLDAuMDMpIi8+PC9zdmc+'); }}
            .container {{ max-width: 1400px; margin: 0 auto; background: #ffffff; padding: 40px; border-radius: 4px; box-shadow: inset 0 0 10px rgba(0,0,0,0.02), 0 4px 15px rgba(0,0,0,0.05); border: 2px solid #8c7355; position: relative; }}
            .container::before {{ content: ""; position: absolute; top: 6px; left: 6px; right: 6px; bottom: 6px; border: 1px solid #d4c2a5; pointer-events: none; }}
            h2, h3 {{ color: #8c2620; font-weight: 900; text-align: center; border-bottom: 2px solid #8c2620; padding-bottom: 10px; margin-bottom: 30px; letter-spacing: 2px; }}
            h3 {{ color: #3b3126; border-bottom: 1px solid #8c7355; margin-top: 50px; font-size: 1.4em; }}
            .chart-row {{ display: flex; flex-wrap: wrap; gap: 30px; margin-bottom: 40px; }}
            .chart-container {{ flex: 1; min-width: 350px; height: 600px; background: transparent; padding: 0; }}
            .full-width-chart {{ width: 100%; height: {chart_cfg['heightVh']}vh; margin-bottom: 40px; background: transparent; padding: 0; box-sizing: border-box; }}
            
            /* Rebalance Detail Panel */
            .detail-panel {{ margin-top: 40px; border: 1px solid #8c7355; padding: 20px; background: #fdfdfb; display: none; }}
            .detail-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #8c2620; margin-bottom: 15px; padding-bottom: 10px; }}
            .detail-header h4 {{ margin: 0; color: #8c2620; font-size: 1.4em; }}
            .detail-stats {{ display: flex; gap: 20px; font-weight: bold; }}
            .stat-item {{ background: #fbfaf7; padding: 5px 15px; border-radius: 4px; border: 1px solid #d4c2a5; }}
            .detail-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            .detail-table th {{ background: #8c7355; color: white; text-align: left; padding: 10px; }}
            .detail-table td {{ padding: 8px; border-bottom: 1px solid #d4c2a5; font-size: 0.9em; }}
            .text-right {{ text-align: right !important; }}
            .tables-row {{ display: flex; gap: 20px; overflow-x: auto; margin-top: 15px; }}
            .table-container {{ flex: 1; min-width: 450px; }}
            .table-container h5 {{ color: #8c7355; margin: 0 0 10px 0; border-left: 4px solid #8c2620; padding-left: 10px; }}
            .row-summary {{ background-color: #fbfaf7; font-weight: bold; border-top: 2px solid #8c7355; }}
            .row-summary td {{ color: #8c2620; }}
            .val-up {{ color: #a43a3a; font-weight: bold; }}
            .val-down {{ color: #4b6a53; font-weight: bold; }}

            /* Calendar controls */
            .calendar-wrapper {{ position: relative; margin-bottom: 30px; }}
            .calendar-nav {{ position: absolute; top: 0; left: 0; right: 0; display: flex; justify-content: space-between; align-items: center; z-index: 10; pointer-events: none; }}
            .nav-btn {{ pointer-events: auto; background: #8c7355; color: white; border: none; border-radius: 4px; padding: 4px 12px; cursor: pointer; font-family: 'Noto Serif SC', serif; font-weight: bold; transition: all 0.2s; }}
            .nav-btn:hover {{ background: #8c2620; transform: scale(1.05); }}
            .nav-btn:active {{ transform: scale(0.95); }}

            /* Hide ECharts default loading/border */
            canvas {{ outline: none; }}
        </style>
    </head>
    <body>
    <div class="container">
        <h2>投资组合调仓展示 (当前总市值: {total_val:.1f}万)</h2>
        
        <div class="calendar-wrapper">
            <div class="calendar-nav">
                <button id="prevYearBtn" class="nav-btn" onclick="changeYear(-1)">← 上一年</button>
                <button id="nextYearBtn" class="nav-btn" onclick="changeYear(1)">下一年 →</button>
            </div>
            <div id="calendarChart" style="width: 100%; height: 180px; margin-bottom: 20px;"></div>
        </div>

        <div id="rebalanceDetail" class="detail-panel" style="margin-bottom: 40px;">
            <div class="detail-header">
                <h4 id="detailDate">调仓对比</h4>
                <div class="detail-stats" style="opacity:0;">
                    <div class="stat-item">交易额: <span id="statVol">0</span>万</div>
                    <div class="stat-item">换手率: <span id="statTurn">0</span>%</div>
                    <div class="stat-item">调仓贡献: <span id="statEff">0</span>万</div>
                </div>
            </div>

            <div class="tables-row">
                <div class="table-container">
                    <h5 id="prevDateTitle">上期持仓</h5>
                    <table class="detail-table">
                        <thead id="prevHead"></thead>
                        <tbody id="prevBody"></tbody>
                    </table>
                </div>
                <div class="table-container">
                    <h5 id="currDateTitle">当期持仓</h5>
                    <table class="detail-table">
                        <thead id="currHead"></thead>
                        <tbody id="currBody"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <div id="stackChart" class="full-width-chart"></div>
        
        <div class="chart-row">
            <div id="trendChart" class="chart-container"></div>
        </div>

        <div class="chart-row">
            <div id="marketChart" class="chart-container"></div>
        </div>

        <div class="chart-row">
            <div id="assetChart" class="chart-container"></div>
        </div>
    </div>

    <script>
        // Data from Python
        const dates = {json.dumps(chart_dates)};
        const totals = {json.dumps(chart_totals)};
        const trades = {json.dumps(trade_contributions)};
        const marketFlucts = {json.dumps(market_contributions)};
        const marketData = {json.dumps(chart_market_data)};
        const marketDetails = {json.dumps(chart_market_details)};
        const assetData = {json.dumps(chart_asset_data)};
        const stackedSeries = {json.dumps(stacked_series)};
        const arrowData = {json.dumps(arrow_data)};
        const rebalanceInfo = {json.dumps(rebalance_info)};
        const daySnapshots = {json.dumps(day_snapshots)};
        const arrowLength = {chart_cfg.get('liquidationArrowLength', 120)};
        const showDetails = {'true' if show_details else 'false'};
        const defaultVisibleBars = {default_visible_bars};
        
        // 0. Calendar Chart
        const calendarChart = echarts.init(document.getElementById('calendarChart'));
        const calendarData = dates.map(d => [d, 1]);
        const allYears = dates.map(d => new Date(d).getFullYear());
        const minYear = Math.min(...allYears);
        const maxYear = Math.max(...allYears);
        let currentDisplayedYear = maxYear;
        
        function updateCalendar(year) {{
            document.getElementById('prevYearBtn').style.visibility = (year > minYear) ? 'visible' : 'hidden';
            document.getElementById('nextYearBtn').style.visibility = (year < maxYear) ? 'visible' : 'hidden';

            const graphData = [];
            const monthMarkers = [];
            const monthStartWeeks = [];
            let lastMonth = -1;

            // Start from Jan 1st of the year
            const start = new Date(year, 0, 1);
            const end = new Date(year, 11, 31);
            
            let current = new Date(start);
            while (current <= end) {{
                const dayOfWeek = current.getDay(); 
                
                if (dayOfWeek !== 0 && dayOfWeek !== 6) {{
                    const m = current.getMonth();
                    const d = current.getDate();
                    const dateStr = `${{year}}/${{m + 1}}/${{d}}`;
                    const dateStrAlt = `${{year}}-${{String(m + 1).padStart(2, '0')}}-${{String(d).padStart(2, '0')}}`;
                    const dateStrAlt2 = `${{year}}/${{String(m + 1).padStart(2, '0')}}/${{String(d).padStart(2, '0')}}`;
                    const isHighlight = dates.some(dt => dt === dateStr || dt === dateStrAlt || dt === dateStrAlt2);
                    
                    const firstDayOfYear = new Date(year, 0, 1);
                    const pastDays = Math.floor((current - firstDayOfYear) / (24 * 60 * 60 * 1000));
                    const weekIdx = Math.floor((pastDays + (firstDayOfYear.getDay() + 6) % 7) / 7);
                    const yIdx = dayOfWeek - 1; 

                    graphData.push([weekIdx, yIdx, d, isHighlight, dateStr, m]);

                    if (m !== lastMonth) {{
                        monthStartWeeks.push(weekIdx);
                        let leftPos = 6 + (weekIdx / 53 * 90);
                        if (m === 11) leftPos -= 1; 
                        
                        monthMarkers.push({{
                            type: 'text',
                            left: leftPos + '%',
                            top: 40,
                            z: 100,
                            style: {{ 
                                text: (m + 1) + '月', 
                                fill: '#8c7355', 
                                font: 'bold 11px "Noto Serif SC"' 
                            }}
                        }});
                        lastMonth = m;
                    }}
                }}
                current.setDate(current.getDate() + 1);
            }}

            calendarChart.setOption({{
                title: {{ text: '年度调仓记录 (' + year + ')', left: 'center', top: 5, textStyle: {{ color: '#8c2620', fontSize: 14 }} }},
                tooltip: {{ 
                    show: true,
                    formatter: function (p) {{ return p.value[4] + (p.value[3] ? ' (Recorded)' : ''); }}
                }},
                grid: {{ top: 65, bottom: 15, left: '6%', right: '4%' }},
                xAxis: {{ type: 'category', show: false }},
                yAxis: {{ 
                    type: 'category', 
                    data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], 
                    inverse: true,
                    axisLine: {{ show: false }},
                    axisTick: {{ show: false }},
                    axisLabel: {{ color: '#8c7355', fontSize: 10, margin: 10 }}
                }},
                graphic: monthMarkers,
                series: [{{
                    type: 'heatmap',
                    data: graphData,
                    itemStyle: {{
                        borderColor: '#ffffff',
                        borderWidth: 2,
                        borderRadius: 2,
                        color: function(p) {{ 
                            if (p.value[3]) return '#8c2620';
                            // Alternate background colors to distinguish months
                            return p.value[5] % 2 === 0 ? '#ebedf0' : '#f6f8fa';
                        }}
                    }},
                    emphasis: {{ disabled: true }}
                }}]
            }}, true);
        }}

        window.changeYear = function(delta) {{
            currentDisplayedYear += delta;
            updateCalendar(currentDisplayedYear);
        }};

        updateCalendar(currentDisplayedYear);

        calendarChart.on('click', function (params) {{
            const dateStr = params.value[4];
            const actualDate = dates.find(d => {{
                const d1 = new Date(d).toDateString();
                const d2 = new Date(dateStr).toDateString();
                return d1 === d2;
            }});
            
            if (actualDate) {{
                showRebalanceDetail(actualDate);
                const idx = dates.indexOf(actualDate);
                if (idx !== -1) {{
                    stackChart.dispatchAction({{
                        type: 'dataZoom',
                        startValue: Math.max(0, idx - 2),
                        endValue: Math.min(dates.length - 1, idx + 2)
                    }});
                }}
            }}
        }});

        // Calculate dataZoom start percentage
        let zoomStart = 0;
        if (dates.length > defaultVisibleBars) {{
            zoomStart = 100 - (defaultVisibleBars / dates.length * 100);
        }}
        
        // Bar width in categories: e.g. 40% -> 0.4. Bar spans from -0.2 to +0.2 relative to category center
        const barWidthVal = parseFloat('{chart_cfg['barWidth']}'.replace('%', '')) / 100;
        const halfBar = barWidthVal / 2;

        let yCenters = {{}};
        dates.forEach((d, dIdx) => {{
            let currentY = 0;
            stackedSeries.forEach(s => {{
                let item = s.data[dIdx];
                let val = item && item.value ? item.value : 0;
                if (val > 0) {{
                    // Use actual asset name from data point
                    if (!yCenters[item.name]) yCenters[item.name] = {{}};
                    yCenters[item.name][d] = currentY + val / 2;
                    currentY += val;
                }}
            }});
        }});

        // 1. Initial Render without markLines
        const stackChart = echarts.init(document.getElementById('stackChart'));
        
        let stackOption = {{
            title: {{ text: '调仓可视化', left: 'center', textStyle: {{ color: '#8c2620', fontSize: 20 }} }},
            toolbox: {{
                right: 20,
                feature: {{
                    saveAsImage: {{ title: '保存为图片', name: '调仓可视化', pixelRatio: 2, iconStyle: {{ borderColor: '#8c2620' }} }}
                }}
            }},
            tooltip: {{ 
                trigger: 'item',
                backgroundColor: 'rgba(59, 49, 38, 0.9)',
                borderColor: '#d4c2a5',
                textStyle: {{ color: '#fffcf5' }},
                formatter: function (params) {{
                    if (!params.data || !params.data.value) return '';
                    let name = params.data.name || params.seriesName;
                    let qtyStr = params.data.qty ? '<br/>持股: ' + params.data.qty : '';
                    let ratioStr = params.data.ratio ? '<br/>占比: ' + (params.data.ratio * 100).toFixed(1) + '%' : '';
                    return name + '<br/>市值: ' + params.data.value + '万' + qtyStr + ratioStr;
                }}
            }},
            legend: {{ show: false }}, // Hide as names are Rank 1, 2...
            grid: {{ left: '3%', right: '4%', bottom: '10%', containLabel: true }},
            dataZoom: [
                {{
                    type: 'slider',
                    show: true,
                    xAxisIndex: [0],
                    start: zoomStart,
                    end: 100,
                    bottom: 5,
                    height: 24,
                    backgroundColor: '#ede4d3',
                    borderColor: '#8c7355',
                    fillerColor: 'rgba(140, 38, 32, 0.15)',
                    textStyle: {{ color: '#3b3126', fontWeight: 'bold' }},
                    dataBackground: {{
                        lineStyle: {{ color: '#d4c2a5', width: 1 }},
                        areaStyle: {{ color: '#e3d9c6', opacity: 0.8 }}
                    }},
                    selectedDataBackground: {{
                        lineStyle: {{ color: '#8c2620', width: 2 }},
                        areaStyle: {{ color: '#8c2620', opacity: 0.2 }}
                    }},
                    handleIcon: 'path://M10.7,11.9H9.3c-1.4,0-2.5-1.1-2.5-2.5V2.5C6.8,1.1,7.9,0,9.3,0h1.4c1.4,0,2.5,1.1,2.5,2.5v6.9C13.2,10.8,12.1,11.9,10.7,11.9z M13.3,24.4H6.7c-1.1,0-2-0.9-2-2v-7.1c0-1.1,0.9-2,2-2h6.6c1.1,0,2,0.9,2,2v7.1C15.3,23.5,14.4,24.4,13.3,24.4z',
                    handleSize: '100%',
                    handleStyle: {{
                        color: '#fffcf5',
                        borderColor: '#8c7355',
                        borderWidth: 2,
                        shadowBlur: 3,
                        shadowColor: 'red',
                        shadowOffsetX: 1,
                        shadowOffsetY: 1
                    }},
                    moveHandleSize: 8,
                    moveHandleStyle: {{
                        color: '#8c2620',
                        opacity: 0.8
                    }}
                }},
                {{
                    type: 'inside',
                    xAxisIndex: [0],
                    start: zoomStart,
                    end: 100
                }}
            ],
            xAxis: [{{ type: 'category', data: dates, axisLine: {{ lineStyle: {{ color: '#8c7355', width: 2 }} }}, axisLabel: {{ color: '#3b3126', fontWeight: 600 }} }}],
            yAxis: [{{ type: 'value', name: '市值 (万)', nameTextStyle: {{ color: '#3b3126', fontWeight: 600 }}, axisLine: {{ show: true, lineStyle: {{ color: '#8c7355', width: 2 }} }}, splitLine: {{ lineStyle: {{ type: 'dashed', color: '#d4c2a5' }} }}, axisLabel: {{ color: '#3b3126', fontWeight: 600 }} }}],
            color: ['#8c2620', '#4b6a53', '#c07844', '#5c4e3e', '#8c7355', '#3b3126', '#a43a3a', '#667863', '#d4c2a5', '#e3d9c6'],
            series: stackedSeries.map(s => {{
                s.barWidth = '{chart_cfg['barWidth']}';
                s.barGap = '{chart_cfg['barGap']}';
                
                s.label.formatter = function(params) {{
                    if (!params.data || !params.data.value) return '';
                    let name = params.data.name || "";
                    let ratio = (params.data.ratio * 100).toFixed(1) + '%';
                    if (params.data.ratio < {label_threshold}) return name;
                    if (!showDetails) return name + ' (' + ratio + ')';
                    let qty = params.data.qty;
                    let qtyLine = name !== "现金" ? ('\\n' + params.data.value + '万 | ' + qty + '股') : ('\\n' + params.data.value + '万');
                    return name + ' (' + ratio + ')' + qtyLine;
                }};
                s.label.rich = {{}};
                s.label.fontSize = {chart_cfg['labelFontSize']};
                return s;
            }})
        }};
        
        // 2. Function to update MarkLines and MarkPoints based on current chart width
        const rightArrowPath = 'path://M0,4 L12,4 L12,0 L24,8 L12,16 L12,12 L0,12 Z';
        
        function updateMarks() {{
            // Use exact ECharts coordinate system and grid to calculate pixel width
            let categoryWidth = 0;
            const model = stackChart.getModel();
            const coordSys = model ? model.getComponent('grid').coordinateSystem : null;
            
            if (coordSys) {{
                const rect = coordSys.getRect();
                const actualGridWidth = rect.width;
                
                const opt = stackChart.getOption();
                let startVal = 0;
                let endVal = dates.length - 1;
                
                if (opt && opt.dataZoom && opt.dataZoom.length > 0) {{
                    // dataZoom provides actual indices of visible range
                    startVal = opt.dataZoom[0].startValue;
                    endVal = opt.dataZoom[0].endValue;
                }}
                
                const visibleItemsCount = endVal - startVal + 1;
                categoryWidth = actualGridWidth / Math.max(1, visibleItemsCount);
            }} else {{
                // fallback during initialization if model isn't fully ready
                categoryWidth = (stackChart.getWidth() * 0.93) / dates.length;
            }}
            
            const barHalfPx = (categoryWidth * barWidthVal) / 2;
            console.log('Exact barHalfPx calculated:', barHalfPx);
            
            let markLineData = [];
            let markPointData = [];

            arrowData.forEach(arr => {{
                let d1Index = dates.indexOf(arr.d1);
                let d2Index = dates.indexOf(arr.d2);
                let y1 = yCenters[arr.name] && yCenters[arr.name][arr.d1];
                let y2 = yCenters[arr.name] && yCenters[arr.name][arr.d2];

                if (arr.is_new) {{
                    if (y2 !== undefined) {{
                        markPointData.push({{
                            coord: [d2Index, y2],
                            symbol: rightArrowPath,
                            symbolSize: [46, 6],
                            symbolOffset: [-barHalfPx - 23, 0],
                            itemStyle: {{ color: '#a43a3a' }},
                            label: {{
                                show: true,
                                position: 'top',
                                formatter: '建',
                                color: '#a43a3a',
                                fontSize: 12,
                                distance: 1
                            }}
                        }});
                    }}
                }} else if (arr.is_liquidation) {{
                    if (y1 !== undefined) {{
                        markPointData.push({{
                            coord: [d1Index, y1],
                            symbol: rightArrowPath,
                            symbolSize: [46, 6],
                            symbolOffset: [barHalfPx + 23, 0],
                            itemStyle: {{ color: '#4b6a53' }},
                            label: {{
                                show: true,
                                position: 'top',
                                formatter: '清',
                                color: '#4b6a53',
                                fontSize: 12,
                                distance: 1
                            }}
                        }});
                    }}
                }} else {{
                    if (y1 !== undefined && y2 !== undefined) {{
                        let action = arr.qty_diff > 0 ? "加仓" : "减仓";
                        let tradeValStr = (arr.trade_val > 0 ? "+" : "") + arr.trade_val.toFixed(1) + "万";
                        let labelText = action + " " + Math.abs(arr.qty_diff) + "股\\n" + tradeValStr;
                        let lineColor = arr.qty_diff > 0 ? "#a43a3a" : "#4b6a53";
                        
                        markLineData.push([
                            {{
                                coord: [arr.d1, y1],
                                lineStyle: {{ color: lineColor, width: 2, type: 'dashed' }}
                            }},
                            {{
                                coord: [arr.d2, y2],
                                value: labelText,
                                label: {{ 
                                    show: true, 
                                    position: 'middle', 
                                    formatter: '{{c}}', 
                                    backgroundColor: "rgba(255, 252, 245, 0.95)", 
                                    borderColor: lineColor,
                                    borderWidth: 1,
                                    padding: [4, 6], 
                                    borderRadius: 4, 
                                    color: lineColor,
                                    fontWeight: 'bold',
                                    fontSize: 12,
                                    lineHeight: 16
                                }}
                            }}
                        ]);
                    }}
                }}
            }});

            if (stackOption.series && stackOption.series.length > 0) {{
                stackOption.series[0].markLine = {{
                    symbol: ['none', 'arrow'],
                    symbolSize: [10, 15],
                    data: markLineData,
                    animation: false
                }};
                stackOption.series[0].markPoint = {{
                    data: markPointData,
                    animation: false
                }};
            }}
            stackChart.setOption({{
                series: stackOption.series
            }});
        }}

        // First render to initialize coordinate system so convertToPixel works
        stackChart.setOption(stackOption);
        
        // Then calculate marks and update
        updateMarks();
        

        const trendChart = echarts.init(document.getElementById('trendChart'));
        trendChart.setOption({{
            title: {{ text: '资产总值变化', left: 'center', textStyle: {{ color: '#8c2620' }} }},
            toolbox: {{
                right: 20,
                feature: {{
                    saveAsImage: {{ title: '保存', name: '资产总值变化', pixelRatio: 2, iconStyle: {{ borderColor: '#8c2620' }} }}
                }}
            }},
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

        // Market Pie Chart
        const marketChart = echarts.init(document.getElementById('marketChart'));
        marketChart.setOption({{
            title: {{ text: '市场分布', left: 'center', textStyle: {{ color: '#8c2620' }} }},
            toolbox: {{
                right: 20,
                feature: {{
                    saveAsImage: {{ title: '保存', name: '市场分布', pixelRatio: 2, iconStyle: {{ borderColor: '#8c2620' }} }}
                }}
            }},
            tooltip: {{ 
                trigger: 'item', 
                backgroundColor: 'rgba(59, 49, 38, 0.9)',
                borderColor: '#d4c2a5',
                textStyle: {{ color: '#fffcf5' }},
                formatter: function(params) {{
                    let market = params.name;
                    let total = params.value;
                    let percent = params.percent;
                    let details = marketDetails[market] || [];
                    
                    let res = `<div style="border-bottom: 1px solid rgba(255,255,255,.3); font-weight: bold; margin-bottom: 5px; padding-bottom: 5px;">${{market}}: ${{total}}万 (${{percent}}%)</div>`;
                    details.forEach(item => {{
                        res += `<div style="display: flex; justify-content: space-between; gap: 20px; font-size: 12px; margin-top: 2px;">
                                    <span>${{item.name}}</span>
                                    <span>${{item.value}}万 (${{item.percent}}%)</span>
                                </div>`;
                    }});
                    return res;
                }}
            }},
            legend: {{ 
                bottom: '0', 
                textStyle: {{ color: '#3b3126' }},
                formatter: function(name) {{
                    let item = marketData.find(d => d.name === name);
                    return name + (item ? ' (' + item.value + '万)' : '');
                }}
            }},
            color: ['#8c2620', '#4b6a53', '#c07844', '#5c4e3e', '#8c7355', '#3b3126', '#a43a3a', '#667863', '#d4c2a5', '#e3d9c6'],
            series: [{{
                type: 'pie',
                radius: ['40%', '75%'],
                avoidLabelOverlap: true,
                itemStyle: {{ borderRadius: 10, borderColor: '#fffcf5', borderWidth: 2 }},
                label: {{ 
                    show: true, 
                    position: 'outside', 
                    formatter: '{{b}}\\n{{c}}万 ({{d}}%)',
                    color: '#3b3126',
                    fontWeight: 'bold',
                    fontSize: 12
                }},
                labelLine: {{ show: true, length: 15, length2: 10 }},
                emphasis: {{ label: {{ show: true, fontSize: 14, fontWeight: 'bold' }} }},
                data: marketData
            }}]
        }});

        // Asset Pie Chart
        const assetChart = echarts.init(document.getElementById('assetChart'));
        assetChart.setOption({{
            title: {{ text: '资产持仓占比', left: 'center', textStyle: {{ color: '#8c2620' }} }},
            toolbox: {{
                right: 20,
                feature: {{
                    saveAsImage: {{ title: '保存', name: '资产持仓占比', pixelRatio: 2, iconStyle: {{ borderColor: '#8c2620' }} }}
                }}
            }},
            tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}万 ({{d}}%)' }},
            legend: {{ 
                bottom: '0', 
                type: 'scroll', 
                textStyle: {{ color: '#3b3126' }},
                formatter: function(name) {{
                    let item = assetData.find(d => d.name === name);
                    return name + (item ? ' (' + item.value + '万)' : '');
                }}
            }},
            color: ['#8c2620', '#4b6a53', '#c07844', '#5c4e3e', '#8c7355', '#3b3126', '#a43a3a', '#667863', '#d4c2a5', '#e3d9c6'],
            series: [{{
                type: 'pie',
                radius: '75%',
                data: assetData,
                itemStyle: {{ borderColor: '#fffcf5', borderWidth: 1 }},
                label: {{
                    show: true,
                    position: 'outside',
                    formatter: '{{b}}\\n{{c}}万 ({{d}}%)',
                    color: '#3b3126',
                    fontWeight: '600',
                    fontSize: 11
                }},
                labelLine: {{ show: true, length: 15, length2: 10 }},
                emphasis: {{ itemStyle: {{ shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'blue' }} }}
            }}]
        }});

        function showRebalanceDetail(date) {{
            const info = rebalanceInfo[date];
            const panel = document.getElementById('rebalanceDetail');
            if (!info) {{
                panel.style.display = 'none';
                return;
            }}

            panel.style.display = 'block';
            document.getElementById('detailDate').innerText = `调仓对比 (${{date}})`;
            document.getElementById('statVol').innerText = info.trade_vol;
            document.getElementById('statTurn').innerText = info.turnover;
            
            const effSpan = document.getElementById('statEff');
            effSpan.innerText = (info.efficiency > 0 ? "+" : "") + info.efficiency;
            effSpan.className = info.efficiency >= 0 ? "val-up" : "val-down";

            const prevDate = info.prev_date;
            document.getElementById('prevDateTitle').innerText = `上期持仓 (${{prevDate}})`;
            document.getElementById('currDateTitle').innerText = `当期持仓 (${{date}})`;

            renderTable('prev', daySnapshots[prevDate]);
            renderTable('curr', daySnapshots[date]);
            
            panel.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
        }}

        function renderTable(prefix, data) {{
            const head = document.getElementById(prefix + 'Head');
            const body = document.getElementById(prefix + 'Body');
            head.innerHTML = '';
            body.innerHTML = '';
            if (!data || data.length === 0) return;

            const numericCols = ['当前价', '盈亏%', '持有数量', '当前(万)', '现金(万)', '收益(万)', '收益率(%)'];

            // Generate header
            const displayCols = Object.keys(data[0]).filter(c => !['收益(万)', '收益率(%)', '现金(万)'].includes(c));
            const trH = document.createElement('tr');
            displayCols.forEach(c => {{
                const th = document.createElement('th');
                th.innerText = c;
                if (numericCols.includes(c)) th.className = 'text-right';
                trH.appendChild(th);
            }});
            head.appendChild(trH);

            // Generate body: Assets first
            data.forEach(row => {{
                if (row['公司名称'] === '汇总' || row['市场'] === '汇总') return; // Skip original summary row
                
                const tr = document.createElement('tr');
                displayCols.forEach(c => {{
                    const td = document.createElement('td');
                    let val = row[c];
                    if (typeof val === 'number' && c !== '持有数量') val = val.toFixed(1);
                    td.innerText = val;
                    if (numericCols.includes(c)) td.className = 'text-right';
                    
                    if (c === '盈亏%' && val) {{
                        if (val.toString().includes('-')) td.classList.add('val-down');
                        else if (parseFloat(val) > 0) td.classList.add('val-up');
                    }}
                    tr.appendChild(td);
                }});
                body.appendChild(tr);
            }});

            // Append Summary Rows at the bottom
            const sumRow = data.find(r => r['公司名称'] === '汇总' || r['市场'] === '汇总');
            if (sumRow) {{
                const sumMetrics = [
                    {{ label: '现金总计', key: '现金(万)', unit: '万' }},
                    {{ label: '当期收益', key: '收益(万)', unit: '万' }},
                    {{ label: '当期收益率', key: '收益率(%)', unit: '' }}
                ];
                
                sumMetrics.forEach(m => {{
                    const tr = document.createElement('tr');
                    tr.className = 'row-summary';
                    
                    const tdLabel = document.createElement('td');
                    tdLabel.innerText = m.label;
                    tdLabel.style.textAlign = 'left';
                    tdLabel.style.paddingRight = '20px';
                    tr.appendChild(tdLabel);
                    
                    const tdVal = document.createElement('td');
                    tdVal.colSpan = displayCols.length - 1;
                    tdVal.className = 'text-right';
                    let val = sumRow[m.key] || '0';
                    tdVal.innerText = val + (m.unit ? ' ' + m.unit : '');
                    
                    if (m.key.includes('收益')) {{
                        if (val.toString().includes('-')) tdVal.classList.add('val-down');
                        else if (parseFloat(val) > 0) tdVal.classList.add('val-up');
                    }}
                    tr.appendChild(tdVal);
                    body.appendChild(tr);
                }});
            }}
        }}

        stackChart.on('click', function(params) {{
            if (params.name) showRebalanceDetail(params.name);
        }});
        
        trendChart.on('click', function(params) {{
            if (params.name) showRebalanceDetail(params.name);
        }});

        // Listen to dataZoom event to recalculate arrow positions when zooming or panning
        let zoomTimeout;
        stackChart.on('dataZoom', function () {{
            clearTimeout(zoomTimeout);
            zoomTimeout = setTimeout(function() {{
                updateMarks();
            }}, 50);
        }});

        window.addEventListener('resize', () => {{
            stackChart.resize();
            updateMarks();
            trendChart.resize();
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
