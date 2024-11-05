const Visualization = {
	// 图表实例
	charts: {
		wordCloud: null,
		opinionDistribution: null,
		controversyAnalysis: null
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
		if (data.controversy_analysis) {
			this.updateControversyAnalysis(data.controversy_analysis);
		}

		// 如果面板未展开，则展开它
		const rightPanel = document.getElementById('visualizationPanel');
		if (!rightPanel.classList.contains('expanded')) {
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
				// 确保图表大小合适
				width: '90%',
				height: '90%',
				// 设置词云图的中心位置
				left: 'center',
				top: 'center',
				// 设置词云图的大小范围
				sizeRange: [12, 50],
				// 设置旋转角度范围
				rotationRange: [-45, 45],
				// 设置字体
				textStyle: {
					fontFamily: 'sans-serif',
					fontWeight: 'bold'
				},
				// 设置布局
				layoutAnimation: false,
				gridSize: 6,
				// 设置词云数据
				data: data.data.map(item => ({
					name: item.text,
					value: item.weight,
					// 根据权重设置字体大小和颜色
					textStyle: {
						fontSize: Math.max(12, Math.min(50, item.weight / 2)),
						color: function () {
							const colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
								'#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'];
							return colors[Math.floor(Math.random() * colors.length)];
						}()
					}
				}))
			}]
		};

		try {
			// 先清空之前的配置
			this.charts.wordCloud.clear();
			// 设置新的配置
			this.charts.wordCloud.setOption(option, true);
			console.log('Word cloud updated successfully');

			// 强制重绘
			setTimeout(() => {
				this.charts.wordCloud.resize();
			}, 0);
		} catch (error) {
			console.error('Error updating word cloud:', error);
		}
	},

	// 更新观点分布图 - 使用气泡图
	updateOpinionDistribution(data) {
		if (!data || !data.data || !this.charts.opinionDistribution) {
			return;
		}

		const option = {
			title: {
				text: data.title || '主要观点分布',
				left: 'center'
			},
			tooltip: {
				trigger: 'item',
				formatter: function (params) {
					return `${params.data.content}<br/>
							支持度: ${params.data.value[0]}%<br/>
							可信度: ${params.data.value[1]}%<br/>
							影响力: ${params.data.value[2]}`;
				}
			},
			legend: {
				right: '5%',
				top: '15%',
				orient: 'vertical'
			},
			grid: {
				left: '8%',
				right: '15%',
				top: '15%',
				bottom: '10%',
				containLabel: true
			},
			xAxis: {
				type: 'value',
				name: '支持度(%)',
				max: 100,
				splitLine: {
					show: true,
					lineStyle: {
						type: 'dashed'
					}
				}
			},
			yAxis: {
				type: 'value',
				name: '可信度(%)',
				max: 100,
				splitLine: {
					show: true,
					lineStyle: {
						type: 'dashed'
					}
				}
			},
			series: [{
				type: 'scatter',
				data: data.data.map(item => ({
					name: item.content.length > 20 ? item.content.substring(0, 20) + '...' : item.content,
					value: [
						item.support_level,  // x轴：支持度
						item.confidence,     // y轴：可信度
						item.influence_score // 气泡大小：影响力
					],
					content: item.content,
					itemStyle: {
						// 使用渐变色
						color: new echarts.graphic.LinearGradient(0, 0, 1, 1, [
							{
								offset: 0,
								color: 'rgba(91, 143, 249, 0.8)'
							},
							{
								offset: 1,
								color: 'rgba(91, 143, 249, 0.2)'
							}
						])
					}
				})),
				symbolSize: function (data) {
					// 根据影响力确定气泡大小，最小20，最大50
					return Math.max(20, Math.min(50, data[2] * 0.4));
				},
				label: {
					show: true,
					formatter: function (param) {
						return param.name;
					},
					position: 'right',
					fontSize: 12
				},
				emphasis: {
					focus: 'series',
					label: {
						show: true,
						formatter: function (param) {
							return param.data.content;
						},
						position: 'top'
					}
				}
			}]
		};

		this.charts.opinionDistribution.setOption(option);
	},

	// 更新争议分析图 - 使用分组条形图
	updateControversyAnalysis(data) {
		if (!data || !data.data || !this.charts.controversyAnalysis) {
			return;
		}

		const option = {
			title: {
				text: data.title || '主要争议点',
				left: 'center'
			},
			tooltip: {
				trigger: 'axis',
				axisPointer: { type: 'shadow' },
				formatter: function (params) {
					const data = params[0].data;
					return `${data.topic}<br/>
							${params[0].seriesName}: ${params[0].value}%<br/>
							${data.supporting_view}<br/><br/>
							${params[1].seriesName}: ${params[1].value}%<br/>
							${data.opposing_view}<br/>
							讨论热度: ${data.discussion_heat}`;
				}
			},
			legend: {
				data: ['支持', '反对'],
				top: 30
			},
			grid: {
				left: '3%',
				right: '4%',
				bottom: '3%',
				containLabel: true
			},
			xAxis: {
				type: 'value',
				max: 100,
				name: '比例(%)'
			},
			yAxis: {
				type: 'category',
				data: data.data.map(item => item.topic),
				axisLabel: {
					width: 200,
					overflow: 'break'
				}
			},
			series: [
				{
					name: '支持',
					type: 'bar',
					stack: 'total',
					data: data.data.map(item => ({
						value: item.support_ratio,
						topic: item.topic,
						supporting_view: item.supporting_view,
						opposing_view: item.opposing_view,
						discussion_heat: item.discussion_heat,
						itemStyle: {
							// 使用讨论热度调整透明度
							color: `rgba(91, 191, 95, ${item.discussion_heat / 100})`
						}
					})),
					label: {
						show: true,
						position: 'inside',
						formatter: '{c}%'
					}
				},
				{
					name: '反对',
					type: 'bar',
					stack: 'total',
					data: data.data.map(item => ({
						value: 100 - item.support_ratio,
						topic: item.topic,
						supporting_view: item.supporting_view,
						opposing_view: item.opposing_view,
						discussion_heat: item.discussion_heat,
						itemStyle: {
							color: `rgba(214, 69, 65, ${item.discussion_heat / 100})`
						}
					})),
					label: {
						show: true,
						position: 'inside',
						formatter: '{c}%'
					}
				}
			]
		};

		this.charts.controversyAnalysis.setOption(option);
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