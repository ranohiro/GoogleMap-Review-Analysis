/**
 * 口コミ分析ツール フロントエンド アプリケーション (app.js)
 * 
 * BFF API と連携し、SPA 画面の描画・状態管理・ドリルダウン操作を行う。
 */

const App = {
  state: {
    currentTab: 'overview',
    filters: {
      stores: [],
      period_start: null,
      period_end: null,
      ratings: [1, 2, 3, 4, 5],
      languages: [],
      has_text: true,
      exclude_estimated_time: false,
      brand: null,
      query: null,
    },
    meta: null,
    selectedAspect: 'taste',
    subtopicSentiment: 'neg',
    reviewsPage: 1,
    reviewsPageSize: 15,
    compareMetric: 'mention_rate',
    compareShrinkage: false,
  },

  async init() {
    this.bindEvents();
    await this.loadMeta();
    await this.loadFilterOptions();
    this.syncFromUrl();
    this.loadCurrentTab();
  },

  bindEvents() {
    // タブ切り替え
    document.querySelectorAll('.nav-item').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const tab = e.currentTarget.dataset.tab;
        this.switchTab(tab);
      });
    });

    // フィルター適用
    document.getElementById('btn-apply-filters').addEventListener('click', () => {
      this.readFilterInputs();
      this.syncToUrl();
      this.loadCurrentTab();
    });

    // フィルターリセット
    document.getElementById('btn-reset-filters').addEventListener('click', () => {
      this.resetFilters();
      this.syncToUrl();
      this.loadCurrentTab();
    });

    // サブトピックの感情切り替えボタン (Screen ②)
    document.querySelectorAll('.btn-toggle').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.btn-toggle').forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        this.state.subtopicSentiment = e.currentTarget.dataset.sentiment;
        this.loadSubtopics(this.state.selectedAspect);
      });
    });

    // 口コミ検索 (Screen ④)
    document.getElementById('btn-search-reviews').addEventListener('click', () => {
      this.state.reviewsPage = 1;
      this.loadReviews();
    });

    document.getElementById('review-search-query').addEventListener('keyup', (e) => {
      if (e.key === 'Enter') {
        this.state.reviewsPage = 1;
        this.loadReviews();
      }
    });

    // CSV エクスポート
    document.getElementById('btn-export-csv').addEventListener('click', () => {
      this.exportCsv();
    });

    // ページネーション (Screen ④)
    document.getElementById('btn-page-prev').addEventListener('click', () => {
      if (this.state.reviewsPage > 1) {
        this.state.reviewsPage--;
        this.loadReviews();
      }
    });

    document.getElementById('btn-page-next').addEventListener('click', () => {
      this.state.reviewsPage++;
      this.loadReviews();
    });

    // 店舗比較コントロール (Screen ⑤)
    document.getElementById('compare-metric-select').addEventListener('change', (e) => {
      this.state.compareMetric = e.target.value;
      this.loadCompare();
    });

    document.getElementById('compare-shrinkage-toggle').addEventListener('change', (e) => {
      this.state.compareShrinkage = e.target.checked;
      this.loadCompare();
    });

    // 前後比較実行 (Screen ⑥)
    document.getElementById('btn-run-before-after').addEventListener('click', () => {
      this.loadTrends();
    });
  },

  async loadMeta() {
    try {
      const res = await fetch('/api/meta');
      const data = await res.json();
      this.state.meta = data;

      document.getElementById('meta-prompt-version').textContent = data.prompt_version || '-';
      document.getElementById('meta-data-mtime').textContent = data.reviews_tagged_mtime || data.reviews_raw_mtime || '-';
      document.getElementById('header-total-reviews').textContent = (data.total_reviews || 0).toLocaleString();

      const badge = document.getElementById('data-status-badge');
      if (data.has_tagged_data) {
        badge.textContent = `タグ付済 (${data.tagged_reviews}件)`;
        badge.className = 'badge-status ready';
      } else {
        badge.textContent = 'タグ付け未実行 (生データ)';
        badge.className = 'badge-status';
      }

      // 口コミ検索の観点ドロップダウン生成
      const aspectSelect = document.getElementById('review-search-aspect');
      aspectSelect.innerHTML = '<option value="">すべての観点</option>';
      for (const [key, label] of Object.entries(data.aspects || {})) {
        const opt = document.createElement('option');
        opt.value = key;
        opt.textContent = label;
        aspectSelect.appendChild(opt);
      }
    } catch (err) {
      console.error('Meta loading failed:', err);
    }
  },

  async loadFilterOptions() {
    try {
      const res = await fetch('/api/filters/options');
      const data = await res.json();

      // 店舗セレクトボックス
      const storeSelect = document.getElementById('filter-store');
      storeSelect.innerHTML = '<option value="">全店舗 (統合表示)</option>';
      (data.stores || []).forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.store_key;
        opt.textContent = `${s.store_name} (${s.review_count}件)`;
        storeSelect.appendChild(opt);
      });

      // 言語セレクトボックス
      const langSelect = document.getElementById('filter-lang');
      langSelect.innerHTML = '<option value="">すべての言語</option>';
      (data.languages || []).forEach(l => {
        const opt = document.createElement('option');
        opt.value = l;
        opt.textContent = l === 'ja' ? '日本語 (ja)' : (l === 'en' ? '英語 (en)' : l);
        langSelect.appendChild(opt);
      });

      if (data.min_date) document.getElementById('filter-date-start').min = data.min_date;
      if (data.max_date) document.getElementById('filter-date-end').max = data.max_date;
    } catch (err) {
      console.error('Filter options loading failed:', err);
    }
  },

  readFilterInputs() {
    const storeVal = document.getElementById('filter-store').value;
    this.state.filters.stores = storeVal ? [storeVal] : [];

    const ratings = [];
    document.querySelectorAll('input[name="rating-filter"]:checked').forEach(cb => {
      ratings.push(parseInt(cb.value, 10));
    });
    this.state.filters.ratings = ratings;

    const langVal = document.getElementById('filter-lang').value;
    this.state.filters.languages = langVal ? [langVal] : [];

    this.state.filters.period_start = document.getElementById('filter-date-start').value || null;
    this.state.filters.period_end = document.getElementById('filter-date-end').value || null;
    this.state.filters.has_text = document.getElementById('filter-has-text').checked;
    this.state.filters.exclude_estimated_time = document.getElementById('filter-exclude-estimated').checked;
  },

  resetFilters() {
    document.getElementById('filter-store').value = '';
    document.querySelectorAll('input[name="rating-filter"]').forEach(cb => cb.checked = true);
    document.getElementById('filter-lang').value = '';
    document.getElementById('filter-date-start').value = '';
    document.getElementById('filter-date-end').value = '';
    document.getElementById('filter-has-text').checked = true;
    document.getElementById('filter-exclude-estimated').checked = false;
    this.readFilterInputs();
  },

  syncToUrl() {
    const params = new URLSearchParams();
    params.set('tab', this.state.currentTab);
    if (this.state.filters.stores.length > 0) params.set('store', this.state.filters.stores[0]);
    window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`);
  },

  syncFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    if (tab && ['overview', 'aspects', 'low_rating', 'search', 'compare', 'trends'].includes(tab)) {
      this.switchTab(tab, false);
    }
    const store = params.get('store');
    if (store) {
      document.getElementById('filter-store').value = store;
      this.state.filters.stores = [store];
    }
  },

  switchTab(tab, updateUrl = true) {
    this.state.currentTab = tab;
    document.querySelectorAll('.nav-item').forEach(b => {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
    document.querySelectorAll('.view-panel').forEach(p => {
      p.classList.toggle('active', p.id === `view-${tab}`);
    });

    const titles = {
      overview: '① 全店舗一覧',
      aspects: '② 観点マップ',
      low_rating: '③ 低評価の要因',
      search: '④ 口コミ検索',
      compare: '⑤ 店舗比較',
      trends: '⑥ 推移',
    };
    document.getElementById('page-title').textContent = titles[tab] || '口コミ分析';

    if (updateUrl) this.syncToUrl();
    this.loadCurrentTab();
  },

  loadCurrentTab() {
    switch (this.state.currentTab) {
      case 'overview':
        this.loadOverview();
        break;
      case 'aspects':
        this.loadAspects();
        break;
      case 'low_rating':
        this.loadLowRating();
        break;
      case 'search':
        this.loadReviews();
        break;
      case 'compare':
        this.loadCompare();
        break;
      case 'trends':
        this.loadTrends();
        break;
    }
  },

  // --- ① 全店舗一覧 ---
  async loadOverview() {
    try {
      const res = await fetch('/api/overview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.state.filters),
      });
      const data = await res.json();

      // サマリー数値
      document.getElementById('overview-total-stores').textContent = (data.summary.total_stores || 0).toLocaleString();
      document.getElementById('overview-collected-stores').textContent = (data.summary.collected_stores || 0).toLocaleString();
      document.getElementById('overview-avg-rating').textContent = data.summary.overall_avg_rating ? `★ ${data.summary.overall_avg_rating.toFixed(2)}` : '-';
      document.getElementById('header-avg-rating').textContent = data.summary.overall_avg_rating ? `★ ${data.summary.overall_avg_rating.toFixed(2)}` : '-';

      // 散布図描画
      Charts.renderPlacesScatter('chart-places-scatter', data.scatter, (storeKey) => {
        // 店舗クリック時に店舗比較へ誘導
        document.getElementById('filter-store').value = storeKey;
        this.state.filters.stores = [storeKey];
        this.switchTab('compare');
      });

      // 都道府県テーブル描画
      const tbody = document.getElementById('overview-pref-tbody');
      tbody.innerHTML = '';
      (data.prefectures || []).forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${p.prefecture}</strong></td>
          <td>${p.store_count} 店</td>
          <td>${p.avg_rating !== null ? `★ ${p.avg_rating.toFixed(2)}` : '-'}</td>
          <td>${p.total_reviews.toLocaleString()} 件</td>
          <td>${p.collected_count > 0 ? `<span class="badge-status ready">${p.collected_count}店 収集済</span>` : '<span class="text-muted">未収集</span>'}</td>
        `;
        tbody.appendChild(tr);
      });

      // 未特定店舗
      const unSec = document.getElementById('overview-unmatched-section');
      const unList = document.getElementById('overview-unmatched-list');
      if (data.unmatched_stores && data.unmatched_stores.length > 0) {
        unSec.style.display = 'block';
        unList.innerHTML = '';
        data.unmatched_stores.forEach(s => {
          const li = document.createElement('li');
          li.textContent = `${s.store_name} (${s.store_key}: ${s.area}) - 収集件数: ${s.review_count}件`;
          unList.appendChild(li);
        });
      } else {
        unSec.style.display = 'none';
      }
    } catch (err) {
      console.error('Overview loading failed:', err);
    }
  },

  // --- ② 観点マップ ---
  async loadAspects() {
    try {
      const res = await fetch('/api/aspects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.state.filters),
      });
      const data = await res.json();

      const banner = document.getElementById('aspects-untagged-banner');
      if (!data.has_tagged_data) {
        banner.style.display = 'block';
      } else {
        banner.style.display = 'none';
      }

      // 散布図描画
      Charts.renderAspectsScatter('chart-aspects-scatter', data.aspects, (aspectKey) => {
        this.state.selectedAspect = aspectKey;
        this.loadSubtopics(aspectKey);
      });

      // 観点一覧テーブル
      const tbody = document.getElementById('aspects-summary-tbody');
      tbody.innerHTML = '';
      (data.aspects || []).forEach(a => {
        const tr = document.createElement('tr');
        const refBadge = a.is_reference ? '<span class="badge-ref">参考値</span>' : '';
        tr.innerHTML = `
          <td><strong>${a.aspect_label}</strong></td>
          <td>${a.mention_count} / ${a.n} 件</td>
          <td>${(a.mention_rate * 100).toFixed(1)}% [${(a.mention_rate_ci_lower * 100).toFixed(1)}%, ${(a.mention_rate_ci_upper * 100).toFixed(1)}%]</td>
          <td>${a.avg_sentiment !== null ? `${a.avg_sentiment > 0 ? '+' : ''}${a.avg_sentiment.toFixed(2)}` : '-'}</td>
          <td>${a.net_sentiment !== null ? `${a.net_sentiment > 0 ? '+' : ''}${a.net_sentiment.toFixed(2)}` : '-'}</td>
          <td>${(a.neg_rate * 100).toFixed(1)}%</td>
          <td>${refBadge || '<span class="text-muted">通常</span>'}</td>
        `;
        tr.style.cursor = 'pointer';
        tr.addEventListener('click', () => {
          this.state.selectedAspect = a.aspect;
          this.loadSubtopics(a.aspect);
        });
        tbody.appendChild(tr);
      });

      // 初期観点のサブトピック取得
      if (data.aspects && data.aspects.length > 0) {
        const current = data.aspects.find(a => a.aspect === this.state.selectedAspect) || data.aspects[0];
        this.loadSubtopics(current.aspect);
      }
    } catch (err) {
      console.error('Aspects loading failed:', err);
    }
  },

  async loadSubtopics(aspectKey) {
    try {
      this.state.selectedAspect = aspectKey;
      const res = await fetch('/api/aspects/subtopics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filters: this.state.filters,
          aspect: aspectKey,
          sentiment: this.state.subtopicSentiment,
          k: 10,
        }),
      });
      const data = await res.json();

      document.getElementById('subtopic-panel-title').textContent = `「${data.aspect_label}」の具体的な言及対象`;
      document.getElementById('subtopic-panel-desc').textContent = `${this.state.subtopicSentiment === 'neg' ? '不満 (否定)' : '好評 (肯定)'} の言及頻度ランキング`;

      const tbody = document.getElementById('aspects-subtopics-tbody');
      tbody.innerHTML = '';
      if (!data.subtopics || data.subtopics.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">該当する具体的な言及対象はありません</td></tr>';
        return;
      }

      data.subtopics.forEach(s => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${s.subtopic}</strong></td>
          <td>${s.count} 件</td>
          <td>${(s.percentage * 100).toFixed(1)}%</td>
          <td>${(s.verbatim_rate * 100).toFixed(0)}% (${s.verbatim_count}/${s.count})</td>
        `;
        tbody.appendChild(tr);
      });
    } catch (err) {
      console.error('Subtopics loading failed:', err);
    }
  },

  // --- ③ 低評価の要因 ---
  async loadLowRating() {
    try {
      const res = await fetch('/api/low-rating', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.state.filters),
      });
      const data = await res.json();

      this.lowRatingData = data;

      // Lift 棒グラフ
      Charts.renderLowRatingLift('chart-low-rating-lift', data.drivers, (aspectKey) => {
        this.renderEvidenceList(aspectKey);
      });

      // 1位の観点をデフォルト選択
      if (data.drivers && data.drivers.length > 0) {
        const topAspect = data.drivers[0].aspect;
        this.renderEvidenceList(topAspect);
      }
    } catch (err) {
      console.error('Low rating loading failed:', err);
    }
  },

  renderEvidenceList(aspectKey) {
    if (!this.lowRatingData || !this.lowRatingData.aspect_evidence) return;
    const list = this.lowRatingData.aspect_evidence[aspectKey] || [];
    const aspectLabel = (this.state.meta && this.state.meta.aspects && this.state.meta.aspects[aspectKey]) || aspectKey;

    document.getElementById('evidence-panel-title').textContent = `「${aspectLabel}」の低評価 原文・根拠`;
    document.getElementById('evidence-panel-count').textContent = `${list.length} 件`;

    const container = document.getElementById('evidence-quotes-container');
    container.innerHTML = '';

    if (list.length === 0) {
      container.innerHTML = '<div class="text-center text-muted p-4">この観点に関する低評価（★1〜2）の根拠文はありません</div>';
      return;
    }

    list.forEach(item => {
      const div = document.createElement('div');
      div.className = 'evidence-item';

      const fullText = item.review_text || '';
      const quote = item.evidence || '';
      let highlighted = fullText;
      if (quote && fullText.includes(quote)) {
        highlighted = fullText.replace(quote, `<mark class="highlight-evidence">${quote}</mark>`);
      }

      div.innerHTML = `
        <div class="evidence-item-header">
          <span class="rating-stars">★${item.rating}</span>
          <span class="review-store-badge">${item.store_name}</span>
          <span class="review-date-badge">${item.post_time}</span>
        </div>
        <div class="evidence-quote">抜粋: 「${quote}」</div>
        <div class="evidence-context">${highlighted}</div>
      `;
      container.appendChild(div);
    });
  },

  // --- ④ 口コミ検索 ---
  async loadReviews() {
    try {
      const query = document.getElementById('review-search-query').value;
      const aspect = document.getElementById('review-search-aspect').value;
      const sentiment = document.getElementById('review-search-sentiment').value;

      const payload = {
        filters: { ...this.state.filters, query: query || null },
        aspect: aspect || null,
        sentiment_filter: sentiment || null,
        page: this.state.reviewsPage,
        page_size: this.state.reviewsPageSize,
      };

      const res = await fetch('/api/reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      document.getElementById('search-total-count').textContent = data.total.toLocaleString();
      document.getElementById('search-page-indicator').textContent = `ページ ${data.page} / ${data.total_pages}`;

      // ページボタン制御
      document.getElementById('btn-page-prev').disabled = (data.page <= 1);
      document.getElementById('btn-page-next').disabled = (data.page >= data.total_pages);

      const container = document.getElementById('reviews-list-container');
      container.innerHTML = '';

      if (!data.reviews || data.reviews.length === 0) {
        container.innerHTML = '<div class="text-center text-muted p-4">条件に合致する口コミはありません</div>';
        return;
      }

      data.reviews.forEach(r => {
        const card = document.createElement('div');
        card.className = 'review-card';

        // 観点タグ
        let tagsHtml = '';
        (r.aspects || []).forEach(a => {
          const sentClass = a.sentiment > 0 ? 'pos' : (a.sentiment < 0 ? 'neg' : 'neu');
          const sentSign = a.sentiment > 0 ? `+${a.sentiment}` : a.sentiment;
          tagsHtml += `<span class="aspect-tag ${sentClass}">${a.aspect_label} (${sentSign}): ${a.subtopic || a.evidence}</span>`;
        });

        // 根拠のハイライト処理
        let textContent = r.review_text || '<span class="text-muted">(本文なし評価)</span>';
        if (r.review_text && r.aspects) {
          r.aspects.forEach(a => {
            if (a.evidence && a.evidence_verbatim && textContent.includes(a.evidence)) {
              textContent = textContent.replace(a.evidence, `<mark class="highlight-evidence">${a.evidence}</mark>`);
            }
          });
        }

        // オーナー返信
        let replyHtml = '';
        if (r.has_owner_reply && r.owner_reply) {
          replyHtml = `<div class="review-owner-reply-box"><strong>オーナーからの返信:</strong> ${r.owner_reply}</div>`;
        }

        card.innerHTML = `
          <div class="review-card-header">
            <span class="rating-stars">${'★'.repeat(r.rating || 0)}${'☆'.repeat(5 - (r.rating || 0))} (${r.rating})</span>
            <span class="review-store-badge">${r.store_name}</span>
            <span class="review-date-badge">${r.post_time ? r.post_time.substring(0, 10) : (r.relative_time || '-')}</span>
          </div>
          <div class="review-text-content">${textContent}</div>
          ${tagsHtml ? `<div class="review-aspect-tags">${tagsHtml}</div>` : ''}
          ${replyHtml}
        `;
        container.appendChild(card);
      });
    } catch (err) {
      console.error('Reviews loading failed:', err);
    }
  },

  async exportCsv() {
    const query = document.getElementById('review-search-query').value;
    const aspect = document.getElementById('review-search-aspect').value;
    const sentiment = document.getElementById('review-search-sentiment').value;

    const payload = {
      filters: { ...this.state.filters, query: query || null },
      aspect: aspect || null,
      sentiment_filter: sentiment || null,
      page: 1,
      page_size: 10000,
    };

    const res = await fetch('/api/reviews/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `reviews_export_${new Date().toISOString().substring(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  },

  // --- ⑤ 店舗比較 ---
  async loadCompare() {
    try {
      const res = await fetch('/api/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filters: this.state.filters,
          metric: this.state.compareMetric,
          use_shrinkage: this.state.compareShrinkage,
        }),
      });
      const data = await res.json();

      Charts.renderCompareHeatmap('chart-compare-heatmap', data);

      // 返信率サマリー表
      const tbody = document.getElementById('compare-reply-tbody');
      tbody.innerHTML = '';
      (data.reply_rates || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${r.store_name}</strong> (${r.store_key})</td>
          <td>${r.total_reviews} 件</td>
          <td>${r.mean_rating !== null ? `★ ${r.mean_rating.toFixed(2)}` : '-'}</td>
          <td>${(r.reply_rate * 100).toFixed(1)}% [${(r.reply_rate_ci_lower * 100).toFixed(1)}%, ${(r.reply_rate_ci_upper * 100).toFixed(1)}%]</td>
          <td>${(r.low_reply_rate * 100).toFixed(1)}%</td>
          <td>${r.median_reply_days !== null ? `${r.median_reply_days} 日` : '-'}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch (err) {
      console.error('Compare loading failed:', err);
    }
  },

  // --- ⑥ 推移 ---
  async loadTrends() {
    try {
      const splitDate = document.getElementById('trend-split-date').value || null;
      const res = await fetch('/api/trends', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filters: this.state.filters,
          exclude_estimated: true,
          split_date: splitDate,
        }),
      });
      const data = await res.json();

      document.getElementById('trends-excluded-count').textContent = (data.excluded_estimated_count || 0).toLocaleString();

      Charts.renderMonthlyTrend('chart-monthly-volume-rating', 'chart-monthly-aspect-neg', data.monthly);

      // 前後比較の描画
      const baContainer = document.getElementById('before-after-results-container');
      if (data.before_after && data.before_after.before && data.before_after.after) {
        baContainer.style.display = 'grid';
        const b = data.before_after.before.ratings;
        const a = data.before_after.after.ratings;

        baContainer.innerHTML = `
          <div class="period-summary-card">
            <div class="period-title">📅 基準日以前 (&lt; ${data.before_after.split_date})</div>
            <p>口コミ数: <strong>${b.total_reviews}</strong> 件</p>
            <p>平均星: <strong>${b.mean_rating !== null ? `★ ${b.mean_rating}` : '-'}</strong></p>
            <p>本文あり率: ${(b.has_text_rate * 100).toFixed(1)}%</p>
          </div>
          <div class="period-summary-card">
            <div class="period-title">📅 基準日以降 (&gt;= ${data.before_after.split_date})</div>
            <p>口コミ数: <strong>${a.total_reviews}</strong> 件</p>
            <p>平均星: <strong>${a.mean_rating !== null ? `★ ${a.mean_rating}` : '-'}</strong></p>
            <p>本文あり率: ${(a.has_text_rate * 100).toFixed(1)}%</p>
          </div>
        `;
      } else {
        baContainer.style.display = 'none';
      }

      // スナップショット履歴
      const snapCard = document.getElementById('snapshot-history-card');
      if (data.has_multiple_snapshots && data.snapshots_history.length >= 2) {
        snapCard.style.display = 'block';
        Charts.renderSnapshotsHistory('chart-snapshots-history', data.snapshots_history);
      } else {
        snapCard.style.display = 'none';
      }
    } catch (err) {
      console.error('Trends loading failed:', err);
    }
  },
};

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
