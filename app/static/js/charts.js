/**
 * Plotly チャート描画モジュール (charts.js)
 * 
 * 設計書 01_design.md に従い、全画面のインタラクティブな Plotly 図表を描画する。
 */

const Charts = {
  // カラーパレット
  colors: {
    primary: '#2563eb',
    collected: '#ef4444',
    uncollected: '#94a3b8',
    grid: '#f1f5f9',
    text: '#334155',
    accentGreen: '#10b981',
    accentRed: '#ef4444',
    accentAmber: '#f59e0b',
  },

  defaultConfig: {
    responsive: true,
    displayModeBar: false,
  },

  /**
   * ① 全店舗一覧: 口コミ数 × 星評価 散布図
   */
  renderPlacesScatter(elementId, scatterData, onSelectStore) {
    const el = document.getElementById(elementId);
    if (!el || !scatterData || scatterData.length === 0) return;

    // 収集済みと未収集でグループ分け
    const collected = scatterData.filter(d => d.has_reviews);
    const uncollected = scatterData.filter(d => !d.has_reviews);

    const traces = [
      {
        name: '未収集店舗',
        x: uncollected.map(d => d.reviews_count),
        y: uncollected.map(d => d.rating),
        text: uncollected.map(d => `${d.store_name} (${d.prefecture} ${d.city})<br>星: ${d.rating} / 口コミ: ${d.reviews_count}件`),
        customdata: uncollected.map(d => d.store_key),
        mode: 'markers',
        type: 'scatter',
        marker: {
          size: 9,
          color: 'rgba(148, 163, 184, 0.65)',
          line: { color: '#64748b', width: 1 }
        },
        hoverinfo: 'text'
      },
      {
        name: '収集済店舗 (データあり)',
        x: collected.map(d => d.reviews_count),
        y: collected.map(d => d.rating),
        text: collected.map(d => `★【収集済】${d.store_name}<br>星: ${d.rating} / 口コミ: ${d.reviews_count}件`),
        customdata: collected.map(d => d.store_key),
        mode: 'markers',
        type: 'scatter',
        marker: {
          size: 14,
          color: '#ef4444',
          symbol: 'diamond',
          line: { color: '#991b1b', width: 1.5 }
        },
        hoverinfo: 'text'
      }
    ];

    const layout = {
      margin: { t: 30, r: 25, l: 45, b: 45 },
      xaxis: { title: 'Google 口コミ件数', gridcolor: '#f1f5f9', zeroline: false },
      yaxis: { title: '平均評価 (星)', range: [2.5, 5.0], gridcolor: '#f1f5f9' },
      hovermode: 'closest',
      legend: { orientation: 'h', y: 1.15, x: 0.1 }
    };

    Plotly.newPlot(elementId, traces, layout, this.defaultConfig);

    if (onSelectStore && el.removeAllListeners) {
      el.removeAllListeners('plotly_click');
    }
    el.on('plotly_click', (data) => {
      if (data.points && data.points.length > 0) {
        const storeKey = data.points[0].customdata;
        if (storeKey && onSelectStore) {
          onSelectStore(storeKey);
        }
      }
    });
  },

  /**
   * ② 観点マップ: 平均感情 (-2〜+2) × 言及率 (0〜100%)
   */
  renderAspectsScatter(elementId, aspectsData, onSelectAspect) {
    const el = document.getElementById(elementId);
    if (!el || !aspectsData || aspectsData.length === 0) return;

    const xVals = aspectsData.map(d => d.avg_sentiment !== null ? d.avg_sentiment : 0);
    const yVals = aspectsData.map(d => d.mention_rate * 100);
    const sizes = aspectsData.map(d => Math.max(12, Math.min(40, (d.mention_count || 1) * 2.5)));
    const labels = aspectsData.map(d => d.aspect_label);
    const aspectKeys = aspectsData.map(d => d.aspect);

    const colors = aspectsData.map(d => {
      if (d.is_reference) return 'rgba(148, 163, 184, 0.7)';
      if (d.net_sentiment > 0.2) return '#10b981';
      if (d.net_sentiment < -0.2) return '#ef4444';
      return '#f59e0b';
    });

    const trace = {
      x: xVals,
      y: yVals,
      text: labels,
      customdata: aspectKeys,
      mode: 'markers+text',
      textposition: 'top center',
      type: 'scatter',
      marker: {
        size: sizes,
        color: colors,
        line: { color: '#334155', width: 1.5 }
      },
      hovertext: aspectsData.map(d => 
        `<b>${d.aspect_label}</b><br>` +
        `言及率: ${(d.mention_rate * 100).toFixed(1)}% [${(d.mention_rate_ci_lower * 100).toFixed(1)}%, ${(d.mention_rate_ci_upper * 100).toFixed(1)}%]<br>` +
        `平均感情: ${d.avg_sentiment !== null ? d.avg_sentiment.toFixed(2) : '-'}<br>` +
        `ネット感情: ${d.net_sentiment !== null ? d.net_sentiment.toFixed(2) : '-'}<br>` +
        `否定率: ${(d.neg_rate * 100).toFixed(1)}%<br>` +
        `言及数: ${d.mention_count} / ${d.n} 件${d.is_reference ? ' (※参考値)' : ''}`
      ),
      hoverinfo: 'text'
    };

    const layout = {
      margin: { t: 30, r: 30, l: 55, b: 45 },
      xaxis: {
        title: '平均感情 (否定 -2 ← 0 → +2 肯定)',
        range: [-2.2, 2.2],
        zeroline: true,
        zerolinecolor: '#cbd5e1',
        zerolinewidth: 1.5,
        gridcolor: '#f1f5f9'
      },
      yaxis: {
        title: '言及率 (%)',
        range: [0, Math.max(60, Math.max(...yVals) * 1.25)],
        gridcolor: '#f1f5f9'
      },
      shapes: [
        // 左上「要注意・改善優先エリア」の背景ハイライト
        {
          type: 'rect',
          xref: 'x',
          yref: 'y',
          x0: -2.2,
          x1: 0,
          y0: 25,
          y1: 100,
          fillcolor: 'rgba(239, 68, 68, 0.08)',
          line: { width: 0 },
          layer: 'below'
        }
      ],
      annotations: [
        {
          x: -1.1,
          y: Math.max(50, Math.max(...yVals) * 1.1),
          text: '⚠️ 最優先改善領域<br>(高言及・低評価)',
          showarrow: false,
          font: { color: '#991b1b', size: 11 }
        }
      ]
    };

    Plotly.newPlot(elementId, [trace], layout, this.defaultConfig);

    el.on('plotly_click', (data) => {
      if (data.points && data.points.length > 0) {
        const aspectKey = data.points[0].customdata;
        if (aspectKey && onSelectAspect) {
          onSelectAspect(aspectKey);
        }
      }
    });
  },

  /**
   * ③ 低評価の要因: Lift 水平棒グラフ (95% CIつき)
   */
  renderLowRatingLift(elementId, driversData, onSelectAspect) {
    const el = document.getElementById(elementId);
    if (!el || !driversData || driversData.length === 0) return;

    // 表示用に逆順（上から 1 位が出るように）
    const sorted = [...driversData].reverse();

    const labels = sorted.map(d => d.aspect_label);
    const aspectKeys = sorted.map(d => d.aspect);
    const lifts = sorted.map(d => d.lift !== null ? d.lift : 0);

    // エラーバー (95% CI)
    const errMinus = sorted.map(d => (d.lift !== null && d.lift_ci_lower !== null) ? Math.max(0, d.lift - d.lift_ci_lower) : 0);
    const errPlus = sorted.map(d => (d.lift !== null && d.lift_ci_upper !== null) ? Math.max(0, d.lift_ci_upper - d.lift) : 0);

    const colors = sorted.map(d => {
      if (d.lift > 1.2) return '#ef4444';
      if (d.lift >= 0.9) return '#f59e0b';
      return '#3b82f6';
    });

    const trace = {
      x: lifts,
      y: labels,
      customdata: aspectKeys,
      type: 'bar',
      orientation: 'h',
      marker: {
        color: colors,
        line: { color: '#1e293b', width: 1 }
      },
      error_x: {
        type: 'data',
        symmetric: false,
        array: errPlus,
        arrayminus: errMinus,
        color: '#334155',
        thickness: 1.5,
        width: 4
      },
      hovertext: sorted.map(d =>
        `<b>${d.aspect_label}</b><br>` +
        `Lift: ${d.lift !== null ? d.lift.toFixed(2) : '-'}` +
        (d.lift_ci_lower !== null ? ` [${d.lift_ci_lower.toFixed(2)}, ${d.lift_ci_upper.toFixed(2)}]` : '') + `<br>` +
        `低評価否定: ${d.low_negs} / ${d.low_total} 件 (${(d.p_low * 100).toFixed(1)}%)<br>` +
        `全体否定: ${d.all_negs} / ${d.all_total} 件 (${(d.p_all * 100).toFixed(1)}%)`
      ),
      hoverinfo: 'text'
    };

    const maxLift = Math.max(2.5, ...lifts.map(l => isNaN(l) ? 0 : l));

    const layout = {
      margin: { t: 30, r: 35, l: 85, b: 45 },
      xaxis: {
        title: '低評価 Lift (= P(否定言及 | ★1-2) ÷ P(否定言及 | 全体))',
        range: [0, maxLift * 1.2],
        gridcolor: '#f1f5f9'
      },
      shapes: [
        // Lift = 1.0 の基準線
        {
          type: 'line',
          x0: 1.0,
          x1: 1.0,
          y0: -0.5,
          y1: labels.length - 0.5,
          line: { color: '#64748b', width: 2, dash: 'dash' }
        }
      ],
      annotations: [
        {
          x: 1.0,
          y: labels.length - 0.5,
          text: '基準線 (Lift=1.0)',
          showarrow: true,
          arrowhead: 0,
          ax: 40,
          ay: -15,
          font: { size: 10, color: '#64748b' }
        }
      ]
    };

    Plotly.newPlot(elementId, [trace], layout, this.defaultConfig);

    el.on('plotly_click', (data) => {
      if (data.points && data.points.length > 0) {
        const aspectKey = data.points[0].customdata;
        if (aspectKey && onSelectAspect) {
          onSelectAspect(aspectKey);
        }
      }
    });
  },

  /**
   * ⑤ 店舗比較: 店舗 × 観点 ヒートマップ
   */
  renderCompareHeatmap(elementId, compareData) {
    const el = document.getElementById(elementId);
    if (!el || !compareData || !compareData.matrix || compareData.matrix.length === 0) return;

    const zVals = compareData.matrix;
    const xLabels = compareData.aspect_labels;
    const yLabels = compareData.store_names.length > 0 ? compareData.store_names : compareData.stores;

    // 指標に応じたカラースケール
    let colorscale = 'Blues';
    if (compareData.metric === 'net_sentiment') {
      colorscale = 'RdYlGn';
    } else if (compareData.metric === 'neg_rate') {
      colorscale = 'Reds';
    }

    const trace = {
      z: zVals,
      x: xLabels,
      y: yLabels,
      type: 'heatmap',
      colorscale: colorscale,
      hoverongaps: false,
      colorbar: {
        title: compareData.metric === 'mention_rate' ? '言及率' :
               (compareData.metric === 'net_sentiment' ? 'ネット感情' : '値')
      }
    };

    const layout = {
      margin: { t: 30, r: 30, l: 140, b: 60 },
      xaxis: { title: '観点', tickangle: -20 },
      yaxis: { title: '店舗', automargin: true }
    };

    Plotly.newPlot(elementId, [trace], layout, this.defaultConfig);
  },

  /**
   * ⑥ 推移: 月別件数 & 平均星 推移
   */
  renderMonthlyTrend(volElementId, negElementId, monthlyData) {
    const elVol = document.getElementById(volElementId);
    if (!elVol || !monthlyData || monthlyData.length === 0) return;

    const months = monthlyData.map(d => d.year_month);
    const counts = monthlyData.map(d => d.count);
    const avgRatings = monthlyData.map(d => d.avg_rating);

    // 1. 口コミ件数（棒）と平均星（折れ線）
    const traceCount = {
      name: '口コミ件数',
      x: months,
      y: counts,
      type: 'bar',
      marker: { color: 'rgba(59, 130, 246, 0.45)' },
      yaxis: 'y1'
    };

    const traceRating = {
      name: '平均星評価',
      x: months,
      y: avgRatings,
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#f59e0b', width: 2.5 },
      marker: { size: 6 },
      yaxis: 'y2'
    };

    const layoutVol = {
      margin: { t: 30, r: 50, l: 50, b: 45 },
      xaxis: { title: '年月', gridcolor: '#f1f5f9' },
      yaxis: { title: '件数', side: 'left', showgrid: false },
      yaxis2: {
        title: '平均星評価',
        side: 'right',
        overlaying: 'y',
        range: [1.0, 5.0],
        gridcolor: '#f1f5f9'
      },
      legend: { orientation: 'h', y: 1.15 }
    };

    Plotly.newPlot(volElementId, [traceCount, traceRating], layoutVol, this.defaultConfig);

    // 2. 観点別否定率の折れ線推移
    const elNeg = document.getElementById(negElementId);
    if (!elNeg) return;

    const aspects = [
      { key: 'taste', label: '味', color: '#10b981' },
      { key: 'service', label: '接客', color: '#ef4444' },
      { key: 'speed', label: '提供時間', color: '#8b5cf6' },
      { key: 'price', label: '価格', color: '#f59e0b' },
      { key: 'cleanliness', label: '清潔さ', color: '#06b6d4' }
    ];

    const tracesNeg = aspects.map(asp => {
      const colName = `${asp.key}_neg_rate`;
      const rates = monthlyData.map(d => (d[colName] !== null && d[colName] !== undefined) ? d[colName] * 100 : null);
      return {
        name: asp.label,
        x: months,
        y: rates,
        type: 'scatter',
        mode: 'lines+markers',
        line: { color: asp.color, width: 2 },
        connectgaps: true
      };
    });

    const layoutNeg = {
      margin: { t: 30, r: 30, l: 50, b: 45 },
      xaxis: { title: '年月', gridcolor: '#f1f5f9' },
      yaxis: { title: '否定率 (%)', gridcolor: '#f1f5f9', range: [0, 50] },
      legend: { orientation: 'h', y: 1.15 }
    };

    Plotly.newPlot(negElementId, tracesNeg, layoutNeg, this.defaultConfig);
  },

  /**
   * ⑥ スナップショット星推移 (存在時のみ)
   */
  renderSnapshotsHistory(elementId, historyData) {
    const el = document.getElementById(elementId);
    if (!el || !historyData || historyData.length === 0) return;

    const dates = historyData.map(d => d.snapshot_date);
    const ratings = historyData.map(d => d.avg_rating);
    const counts = historyData.map(d => d.total_reviews);

    const traceRating = {
      name: 'Google 全体平均評価',
      x: dates,
      y: ratings,
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#2563eb', width: 2 }
    };

    const layout = {
      margin: { t: 30, r: 30, l: 50, b: 45 },
      xaxis: { title: 'スナップショット取得日' },
      yaxis: { title: '平均評価', range: [3.0, 5.0] }
    };

    Plotly.newPlot(elementId, [traceRating], layout, this.defaultConfig);
  }
};
