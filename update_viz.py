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

    # Latest structure
    all_asset_names = sorted(asset_data.keys(), key=lambda x: (asset_market[x], x))
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
    
    # Prepare Stacked Bar Data
    all_series_data = []
    
    # Calculate average values including cash
    all_items_to_sort = []
    for name in all_asset_names:
        avg = sum(asset_data[name].get(d, {}).get('val', 0) for d in dates) / len(dates)
        all_items_to_sort.append({'name': name, 'avg': avg, 'is_cash': False})
    
    avg_cash = sum(cash.get(d, 0) for d in dates) / len(dates)
    all_items_to_sort.append({'name': '现金', 'avg': avg_cash, 'is_cash': True})
    
    # Sort: Largest average value at the bottom (first in the series list)
    sorted_items = sorted(all_items_to_sort, key=lambda x: x['avg'], reverse=True)
    
    stacked_series = []
    for item in sorted_items:
        name = item['name']
        data_over_time = []
        
        if item['is_cash']:
            for d in dates:
                val = round(cash.get(d, 0.0), 1)
                total_day = totals.get(d, 0)
                ratio = val / total_day if total_day > 0 else 0
                data_over_time.append({"value": val if ratio >= hide_threshold else None, "qty": 0, "ratio": ratio, "is_new": False})
        else:
            prev_qty = 0
            for d in dates:
                val = round(asset_data[name].get(d, {}).get('val', 0), 1)
                qty = asset_data[name].get(d, {}).get('qty', 0)
                total_day = totals.get(d, 0)
                ratio = val / total_day if total_day > 0 else 0
                is_new = bool(prev_qty == 0 and qty > 0)
                prev_qty = qty
                data_over_time.append({"value": val if ratio >= hide_threshold else None, "qty": qty, "ratio": ratio, "is_new": is_new})
            
        if any(i["value"] is not None for i in data_over_time):
            s_obj = {
                "name": name,
                "type": "bar",
                "stack": "Total",
                "emphasis": {"focus": "series"},
                "label": {"show": True},
                "data": data_over_time
            }
            if not item['is_cash']:
                s_obj["label"]["rich"] = {"qty": {"fontSize": 11, "color": "#eee"}}
            stacked_series.append(s_obj)

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
            body {{ font-family: 'Noto Serif SC', serif; padding: 40px 20px; background-color: #f4eee1; color: #2c251d; background-image: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0IiBoZWlnaHQ9IjQiPjxyZWN0IHdpZHRoPSI0IiBoZWlnaHQ9IjQiIGZpbGw9IiNmNGVlZTEiLz48cmVjdCB3aWR0aD0iMSIgaGVpZ2h0PSIxIiBmaWxsPSJyZ2JhKDAsMCwwLDAuMDUpIi8+PC9zdmc+'); }}
            .container {{ max-width: 1400px; margin: 0 auto; background: #fffcf5; padding: 40px; border-radius: 4px; box-shadow: inset 0 0 10px rgba(0,0,0,0.05), 0 4px 15px rgba(0,0,0,0.08); border: 2px solid #8c7355; position: relative; }}
            .container::before {{ content: ""; position: absolute; top: 6px; left: 6px; right: 6px; bottom: 6px; border: 1px solid #d4c2a5; pointer-events: none; }}
            h2, h3 {{ color: #8c2620; font-weight: 900; text-align: center; border-bottom: 2px solid #8c2620; padding-bottom: 10px; margin-bottom: 30px; letter-spacing: 2px; }}
            h3 {{ color: #3b3126; border-bottom: 1px solid #8c7355; margin-top: 50px; font-size: 1.4em; }}
            .chart-row {{ display: flex; flex-wrap: wrap; gap: 30px; margin-bottom: 40px; }}
            .chart-container {{ flex: 1; min-width: 350px; height: 600px; background: transparent; padding: 0; }}
            .full-width-chart {{ width: 100%; height: {chart_cfg['heightVh']}vh; margin-bottom: 40px; background: transparent; padding: 0; box-sizing: border-box; }}
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
        const assetData = {json.dumps(chart_asset_data)};
        const stackedSeries = {json.dumps(stacked_series)};
        const arrowData = {json.dumps(arrow_data)};
        const arrowLength = {chart_cfg.get('liquidationArrowLength', 120)};
        const showDetails = {'true' if show_details else 'false'};
        const defaultVisibleBars = {default_visible_bars};
        
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
                    let qtyStr = params.data.qty ? '<br/>持股: ' + params.data.qty : '';
                    let ratioStr = params.data.ratio ? '<br/>占比: ' + (params.data.ratio * 100).toFixed(1) + '%' : '';
                    return params.seriesName + '<br/>市值: ' + params.data.value + '万' + qtyStr + ratioStr;
                }}
            }},
            legend: {{ top: 30,left:100, type: 'scroll', textStyle: {{ color: '#3b3126', fontWeight: 600 }} }},
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
                        shadowColor: 'rgba(0, 0, 0, 0.3)',
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

        // Step Change Chart (Stacked)
        const stepChart = echarts.init(document.getElementById('stepChart'));
        stepChart.setOption({{
            title: {{ text: '调仓效果拆解', left: 'center', textStyle: {{ color: '#8c2620' }} }},
            toolbox: {{
                right: 20,
                feature: {{
                    saveAsImage: {{ title: '保存', name: '调仓效果拆解', pixelRatio: 2, iconStyle: {{ borderColor: '#8c2620' }} }}
                }}
            }},
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
            toolbox: {{
                right: 20,
                feature: {{
                    saveAsImage: {{ title: '保存', name: '市场分布', pixelRatio: 2, iconStyle: {{ borderColor: '#8c2620' }} }}
                }}
            }},
            tooltip: {{ trigger: 'item', formatter: '{{b}}: {{c}}万 ({{d}}%)' }},
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
                emphasis: {{ itemStyle: {{ shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' }} }}
            }}]
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
