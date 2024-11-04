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
		this.initToggleButton();
		window.addEventListener('resize', () => {
			this.resize();
		});
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

	// 初始化切换按钮
	initToggleButton() {
		const rightPanel = document.getElementById('visualizationPanel');
		const toggleBtn = document.createElement('button');
		toggleBtn.className = 'toggle-panel-btn';
		toggleBtn.innerHTML = '◄';  // 默认收起状态，箭头朝左
		toggleBtn.onclick = () => this.togglePanel();
		rightPanel.insertBefore(toggleBtn, rightPanel.firstChild);
	},

	// 切换面板
	togglePanel() {
		const rightPanel = document.getElementById('visualizationPanel');
		const toggleBtn = rightPanel.querySelector('.toggle-panel-btn');
		const isExpanded = rightPanel.classList.toggle('expanded');

		// 更新按钮箭头方向：展开时箭头朝右，收起时箭头朝左
		toggleBtn.innerHTML = isExpanded ? '►' : '◄';

		// 如果展开了面板，需要重新调整图表大小
		if (isExpanded) {
			// 给一点延迟，等待 CSS 过渡效果完成
			setTimeout(() => {
				this.resize();
			}, 300);
		}
	},

	// 处理搜索结果
	handleSearchResult(data) {
		console.log('Visualization handling data:', data);

		// 更新各个图表
		if (data.word_cloud) {
			this.updateWordCloud(data.word_cloud);
		}
		if (data.opinion_distribution) {
			this.updateOpinionDistribution(data.opinion_distribution);
		}

		if (!isExpanded) {
			this.togglePanel();
		}
	},

	// 更新词云图
	updateWordCloud(data) {
		if (!data || !data.data || !this.charts.wordCloud) {
			console.log('Skip word cloud update:', { data, chart: !!this.charts.wordCloud });
			return;
		}

		console.log('Updating word cloud with data:', data);

		const option = {
			title: {
				text: data.title || '关键词分布',
				left: 'center'
			},
			tooltip: {
				show: true,
				formatter: function (params) {
					return params.name + ': ' + params.value;
				}
			},
			series: [{
				type: 'wordCloud',
				shape: 'circle',
				keepAspect: false,
				left: 'center',
				top: 'center',
				width: '95%',
				height: '95%',
				sizeRange: [14, 50],  // 调整字体大小范围
				rotationRange: [-45, 45],  // 减小旋转角度范围
				rotationStep: 15,
				gridSize: 15,  // 增加网格大小
				drawOutOfBound: false,
				layoutAnimation: true,
				textStyle: {
					fontFamily: 'sans-serif',
					fontWeight: 'bold',
					color: function () {
						// 使用更鲜艳的颜色
						return 'rgb(' + [
							Math.round(Math.random() * 200 + 55),  // 55-255
							Math.round(Math.random() * 200 + 55),  // 55-255
							Math.round(Math.random() * 200 + 55)   // 55-255
						].join(',') + ')';
					}
				},
				emphasis: {
					textStyle: {
						shadowBlur: 10,
						shadowColor: '#333'
					}
				},
				data: data.data.map(item => ({
					name: item.text,
					value: item.weight,
					textStyle: {
						fontSize: Math.sqrt(item.weight) * 2  // 根据权重动态计算字体大小
					}
				}))
			}]
		};

		try {
			this.charts.wordCloud.setOption(option, true);  // 添加 true 参数强制刷新
			console.log('Word cloud updated successfully');
		} catch (error) {
			console.error('Error updating word cloud:', error);
		}
	},

	// 更新观点分布图
	updateOpinionDistribution(data) {
		if (!data || !data.data || !this.charts.opinionDistribution) {
			console.log('Skip opinion distribution update:', { data, chart: !!this.charts.opinionDistribution });
			return;
		}

		const option = {
			title: {
				text: data.title || '观点分布'
			},
			tooltip: {
				trigger: 'item',
				formatter: '{b}: {c} ({d}%)'
			},
			series: [{
				type: 'pie',
				radius: '65%',
				data: data.data.map(item => ({
					name: item.name,
					value: item.value
				})),
				emphasis: {
					itemStyle: {
						shadowBlur: 10,
						shadowOffsetX: 0,
						shadowColor: 'rgba(0, 0, 0, 0.5)'
					}
				}
			}]
		};

		this.charts.opinionDistribution.setOption(option);
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
		const rightPanel = document.getElementById('visualizationPanel');
		if (rightPanel.classList.contains('expanded')) {
			Object.values(this.charts).forEach(chart => {
				if (chart) {
					try {
						chart.resize();
					} catch (error) {
						console.error('Error resizing chart:', error);
					}
				}
			});
		}
	}
};

// 监听窗口大小变化
window.addEventListener('resize', () => Visualization.resize()); 