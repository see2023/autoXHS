const Visualization = {
	// 图表实例
	charts: {
		wordCloud: null,
		opinionDistribution: null,
		controversyAnalysis: null,
		minorityInsights: null
	},

	// 初始化
	init() {
		// 初始化各个图表
		this.initCharts();
	},

	// 初始化图表
	initCharts() {
		// 初始化词云图
		this.charts.wordCloud = echarts.init(document.getElementById('wordCloud'));

		// 初始化观点分布图
		this.charts.opinionDistribution = echarts.init(document.getElementById('opinionDistribution'));

		// 初始化争议分析图
		this.charts.controversyAnalysis = echarts.init(document.getElementById('controversyAnalysis'));

		// 初始化少数派观点图
		this.charts.minorityInsights = echarts.init(document.getElementById('minorityInsights'));
	},

	// 处理搜索结果
	handleSearchResult(data) {
		// 显示文字总结
		Chat.addMessage('ai', data.text_summary);

		// 更新各个图表
		this.updateWordCloud(data.word_cloud);
		this.updateOpinionDistribution(data.opinion_distribution);
		this.updateControversyAnalysis(data.controversy_analysis);
		this.updateMinorityInsights(data.minority_insights);
	},

	// 更新词云图
	updateWordCloud(data) {
		// TODO: 实现词云图的更新
	},

	// 更新观点分布图
	updateOpinionDistribution(data) {
		// TODO: 实现观点分布图的更新
	},

	// 更新争议分析图
	updateControversyAnalysis(data) {
		// TODO: 实现争议分析图的更新
	},

	// 更新少数派观点图
	updateMinorityInsights(data) {
		// TODO: 实现少数派观点图的更新
	},

	// 窗口大小改变时重新调整图表大小
	resize() {
		Object.values(this.charts).forEach(chart => {
			if (chart) {
				chart.resize();
			}
		});
	}
};

// 监听窗口大小变化
window.addEventListener('resize', () => Visualization.resize()); 